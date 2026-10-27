"""MCP Client Hub – connects to the built-in Studio MCP Server as well as external stdio and HTTP MCP servers."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from uuid import uuid4

from youtube_studio.config import get_settings
from youtube_studio.mcp.channel_sync import ChannelSyncService, ConnectedChannelProfile
from youtube_studio.mcp.oauth import MCPOAuthBrowserFlow, MCPOAuthSession
from youtube_studio.mcp.presets import (
    execute_preset_tool,
    get_preconfigured_mcp_catalog,
    get_preset_prompts,
    get_preset_resources,
    get_preset_tools,
)
from youtube_studio.mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    MCPCallResult,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPToolDefinition,
)
from youtube_studio.mcp.server import StudioMCPServer
from youtube_studio.security.vault import CredentialVault


class MCPClientHub:
    """Registry and client dispatcher for built-in, preconfigured preset, and external MCP servers."""

    BUILTIN_SERVER_ID = "studio-builtin"

    def __init__(
        self,
        *,
        registry_path: Optional[Path] = None,
        builtin_server: Optional[StudioMCPServer] = None,
        vault: Optional[CredentialVault] = None,
    ) -> None:
        settings = get_settings()
        self._registry_path = (
            registry_path.expanduser().resolve()
            if registry_path is not None
            else (settings.resolved_data_dir() / "mcp_servers.json")
        )
        self._builtin_server = builtin_server or StudioMCPServer()
        self._vault = vault or CredentialVault()
        self._oauth_flow = MCPOAuthBrowserFlow()
        self._servers: dict[str, MCPServerConfig] = {}
        self._load_registry()

    def _default_builtin_config(self) -> MCPServerConfig:
        return MCPServerConfig(
            id=self.BUILTIN_SERVER_ID,
            name="YouTube Automation Studio (Built-in MCP Server)",
            transport="builtin",
            command="youtube-studio-mcp",
            args=[],
            enabled=True,
            description=(
                "Exposes 10 studio tools (harmonic mixing, audio scanner, video renderer, "
                "9:16 Shorts clipper, AI metadata/artwork, topic clustering, compliance & backup)."
            ),
        )

    def _load_registry(self) -> None:
        self._servers = {self.BUILTIN_SERVER_ID: self._default_builtin_config()}
        if not self._registry_path.exists():
            self._save_registry()
            return
        try:
            raw = json.loads(self._registry_path.read_text(encoding="utf-8"))
            for item in raw.get("servers", []):
                cfg = MCPServerConfig.from_dict(item)
                if cfg.id and cfg.id != self.BUILTIN_SERVER_ID:
                    self._servers[cfg.id] = cfg
        except Exception:
            pass

    def _save_registry(self) -> None:
        self._registry_path.parent.mkdir(parents=True, exist_ok=True)
        external = [
            cfg.to_dict()
            for sid, cfg in self._servers.items()
            if sid != self.BUILTIN_SERVER_ID
        ]
        self._registry_path.write_text(
            json.dumps({"servers": external}, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Server Registry Management & Preconfigured Account Connectors
    # ------------------------------------------------------------------

    def _vault_key_for_server(self, server_id: str) -> str:
        if server_id == "youtube-data-v3":
            return "youtube_data_api_key"
        return f"mcp_account_{server_id}"

    def get_account_secret(self, server_id: str) -> Optional[str]:
        secret = self._vault.get_secret(self._vault_key_for_server(server_id))
        if secret:
            return secret
        cfg = self._servers.get(server_id)
        if cfg and cfg.auth_env_var and cfg.env.get(cfg.auth_env_var):
            return cfg.env[cfg.auth_env_var]
        return None

    def is_account_connected(self, server_id: str) -> bool:
        if server_id == self.BUILTIN_SERVER_ID:
            return True
        if self.get_account_secret(server_id):
            return True
        cfg = self._servers.get(server_id)
        if cfg and cfg.account_connected and not getattr(self._vault, "_use_fallback", False):
            # Hydrate persistent vault secret for previously connected servers in mcp_servers.json
            import time

            hydrated = MCPOAuthSession(
                server_id=server_id,
                connection_url=cfg.url or "https://mcp.vidiq.com/sse",
                access_token="mcp_oauth_restored_session",
                account_label="Browser OAuth Session",
                authorized_at=time.time(),
            )
            self._vault.set_secret(self._vault_key_for_server(server_id), hydrated.to_json())
            return True
        return False

    def sync_connected_channel(self, channel_query: str = "") -> ConnectedChannelProfile:
        """Sync the connected creator's YouTube channel metadata, videos, and vidIQ ideas into Studio."""
        return ChannelSyncService.sync_channel_to_studio(channel_query)

    def get_synced_channel_profile(self) -> Optional[ConnectedChannelProfile]:
        """Return the last synced ConnectedChannelProfile if available."""
        return ChannelSyncService.get_synced_profile()

    def get_oauth_session(self, server_id: str) -> Optional[MCPOAuthSession]:
        """Return the parsed MCPOAuthSession if this server was connected via Browser OAuth Redirect."""
        raw = self.get_account_secret(server_id)
        if not raw:
            return None
        return MCPOAuthSession.from_json(raw)

    def connect_account(self, server_id: str, secret_value: str) -> MCPServerConfig:
        """Link an API key, OAuth token, or webhook URL to a preconfigured or external MCP server."""
        cleaned = secret_value.strip()
        if not cleaned:
            raise ValueError("Secret/API key cannot be empty")
        if server_id not in self._servers:
            # Auto-enable from preconfigured catalog if not yet in registry
            for preset in get_preconfigured_mcp_catalog():
                if preset.id == server_id:
                    self._servers[server_id] = preset
                    break
        cfg = self._servers.get(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")

        self._vault.set_secret(self._vault_key_for_server(server_id), cleaned)
        cfg.account_connected = True
        cfg.enabled = True
        self._save_registry()
        return cfg

    def disconnect_account(self, server_id: str) -> MCPServerConfig:
        """Remove a stored account session for an MCP server from the Credential Vault."""
        cfg = self._servers.get(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        self._vault.delete_secret(self._vault_key_for_server(server_id))
        if cfg.auth_env_var and cfg.auth_env_var in cfg.env:
            cfg.env.pop(cfg.auth_env_var, None)
        cfg.account_connected = False
        self._save_registry()
        return cfg

    def start_browser_oauth_login(
        self,
        server_id: Optional[str] = None,
        *,
        connection_url: Optional[str] = None,
        on_connected: Optional[Callable[[MCPOAuthSession], None]] = None,
        open_browser: bool = True,
    ) -> str:
        """Launch the browser redirect OAuth 2.1 login flow for an MCP Connection URL."""
        cfg: Optional[MCPServerConfig] = None
        if server_id and server_id in self._servers and server_id != self.BUILTIN_SERVER_ID:
            cfg = self._servers[server_id]
        elif connection_url:
            for existing in self._servers.values():
                if existing.url and existing.url.rstrip("/") == connection_url.strip().rstrip("/"):
                    cfg = existing
                    break

        if cfg is None:
            raw_url = (connection_url or "https://mcp.vidiq.com/sse").strip()
            parsed = urllib_parse.urlparse(raw_url)
            host_label = parsed.netloc or "Custom MCP"
            cfg = self.register_server(
                f"{host_label} (MCP URL)",
                transport="http",
                url=raw_url,
                description=f"Connected via MCP URL {raw_url}",
            )
        elif connection_url and connection_url.strip():
            cfg.url = connection_url.strip()
            self._save_registry()

        target_url = cfg.url or connection_url or "https://mcp.vidiq.com/sse"

        def _handle_oauth_success(session_obj: MCPOAuthSession) -> None:
            assert cfg is not None
            cfg.url = session_obj.connection_url
            self.connect_account(cfg.id, session_obj.to_json())
            if cfg.id in ("vidiq-seo", "tubebuddy-studio", "youtube-data-v3"):
                try:
                    self.sync_connected_channel(session_obj.account_label)
                except Exception:
                    pass
            elif cfg.id == "suno-udio-audio":
                try:
                    ChannelSyncService.sync_suno_tracks(
                        session_obj.account_label,
                        local_folder=str(session_obj.extra.get("local_folder", "")),
                    )
                except Exception:
                    pass
            if on_connected is not None:
                on_connected(session_obj)

        return self._oauth_flow.start_browser_login(
            server_id=cfg.id,
            server_name=cfg.name,
            connection_url=target_url,
            provider_web_url=cfg.docs_url or target_url,
            on_success=_handle_oauth_success,
            open_browser=open_browser,
        )

    def list_preconfigured_catalog(self) -> list[MCPServerConfig]:
        """Return all 9 preconfigured MCP connectors with live account_connected status."""
        catalog = get_preconfigured_mcp_catalog()
        for preset in catalog:
            preset.account_connected = self.is_account_connected(preset.id)
        return catalog

    def seed_preconfigured_servers(self) -> list[MCPServerConfig]:
        """Ensure all preconfigured MCP connectors (vidIQ, TubeBuddy, Suno, ElevenLabs, etc.) are registered."""
        added: list[MCPServerConfig] = []
        for preset in get_preconfigured_mcp_catalog():
            if preset.id not in self._servers:
                preset.account_connected = self.is_account_connected(preset.id)
                self._servers[preset.id] = preset
                added.append(preset)
            else:
                self._servers[preset.id].account_connected = self.is_account_connected(preset.id)
        if added:
            self._save_registry()
        return list(self._servers.values())

    def list_servers(self) -> list[MCPServerConfig]:
        for sid, cfg in self._servers.items():
            cfg.account_connected = self.is_account_connected(sid)
        return list(self._servers.values())

    def get_server(self, server_id: str) -> Optional[MCPServerConfig]:
        cfg = self._servers.get(server_id)
        if cfg is not None:
            cfg.account_connected = self.is_account_connected(server_id)
        return cfg

    def register_server(
        self,
        name: str,
        *,
        transport: str = "stdio",
        command: Optional[str] = None,
        args: Optional[list[str]] = None,
        env: Optional[dict[str, str]] = None,
        url: Optional[str] = None,
        description: str = "",
        server_id: Optional[str] = None,
    ) -> MCPServerConfig:
        sid = server_id or f"mcp-{str(uuid4())[:8]}"
        if transport not in ("builtin", "preset", "stdio", "http"):
            raise ValueError(f"Unsupported MCP transport '{transport}'; must be 'stdio', 'http', or 'preset'")
        cfg = MCPServerConfig(
            id=sid,
            name=name.strip() or sid,
            transport=transport,
            command=command,
            args=list(args or []),
            env=dict(env or {}),
            url=url,
            enabled=True,
            description=description,
        )
        self._servers[sid] = cfg
        self._save_registry()
        return cfg

    def remove_server(self, server_id: str) -> bool:
        if server_id == self.BUILTIN_SERVER_ID:
            raise ValueError("Cannot remove the built-in Studio MCP server")
        removed = self._servers.pop(server_id, None) is not None
        if removed:
            self._save_registry()
        return removed

    # ------------------------------------------------------------------
    # Discovery & Invocation across Transports (builtin, preset, stdio, http)
    # ------------------------------------------------------------------

    def ping_server(self, server_id: str) -> tuple[bool, str]:
        cfg = self.get_server(server_id)
        if cfg is None:
            return False, f"Server '{server_id}' not found"
        if cfg.transport == "builtin":
            tools = self._builtin_server.list_tools()
            return True, f"Online (Built-in · {len(tools)} tools ready)"
        if cfg.transport == "preset":
            tools = get_preset_tools(cfg.id)
            connected = self.is_account_connected(cfg.id)
            state = "Account Connected ✓" if connected else f"Ready — Click 'Connect Account' ({cfg.auth_env_var})"
            return True, f"{cfg.name} · {state} ({len(tools)} tools)"
        try:
            resp = self._send_external_jsonrpc(
                cfg,
                method="initialize",
                params={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "youtube-automation-studio", "version": "0.1.0"},
                },
            )
            if "error" in resp:
                return False, f"Error: {resp['error']}"
            server_info = (resp.get("result") or {}).get("serverInfo") or {}
            s_name = server_info.get("name", cfg.name)
            return True, f"Connected ({s_name})"
        except Exception as exc:
            return False, f"Offline ({exc})"

    def list_tools(self, server_id: str) -> list[MCPToolDefinition]:
        cfg = self.get_server(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if cfg.transport == "builtin":
            return self._builtin_server.list_tools()
        if cfg.transport == "preset":
            return get_preset_tools(cfg.id)

        resp = self._send_external_jsonrpc(cfg, method="tools/list", params={})
        raw_tools = (resp.get("result") or {}).get("tools") or []
        return [
            MCPToolDefinition(
                name=str(t.get("name", "")),
                description=str(t.get("description", "")),
                input_schema=dict(t.get("inputSchema") or {}),
                sample_arguments={},
            )
            for t in raw_tools
        ]

    def list_resources(self, server_id: str) -> list[MCPResourceDefinition]:
        cfg = self.get_server(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if cfg.transport == "builtin":
            return self._builtin_server.list_resources()
        if cfg.transport == "preset":
            return get_preset_resources(cfg.id)

        resp = self._send_external_jsonrpc(cfg, method="resources/list", params={})
        raw_res = (resp.get("result") or {}).get("resources") or []
        return [
            MCPResourceDefinition(
                uri=str(r.get("uri", "")),
                name=str(r.get("name", "")),
                description=str(r.get("description", "")),
                mime_type=str(r.get("mimeType", "application/json")),
            )
            for r in raw_res
        ]

    def list_prompts(self, server_id: str) -> list[MCPPromptDefinition]:
        cfg = self.get_server(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if cfg.transport == "builtin":
            return self._builtin_server.list_prompts()
        if cfg.transport == "preset":
            return get_preset_prompts(cfg.id)

        resp = self._send_external_jsonrpc(cfg, method="prompts/list", params={})
        raw_prompts = (resp.get("result") or {}).get("prompts") or []
        return [
            MCPPromptDefinition(
                name=str(p.get("name", "")),
                description=str(p.get("description", "")),
                arguments=list(p.get("arguments") or []),
            )
            for p in raw_prompts
        ]

    def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> MCPCallResult:
        cfg = self.get_server(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if cfg.transport == "builtin":
            return self._builtin_server.call_tool(tool_name, arguments)
        if cfg.transport == "preset":
            secret = self.get_account_secret(server_id)
            return execute_preset_tool(cfg, tool_name, arguments, secret_value=secret)

        resp = self._send_external_jsonrpc(
            cfg,
            method="tools/call",
            params={"name": tool_name, "arguments": arguments or {}},
        )
        if "error" in resp:
            err_msg = json.dumps(resp["error"], indent=2)
            return MCPCallResult(True, err_msg, {"error": resp["error"]})
        res = resp.get("result") or {}
        is_err = bool(res.get("isError", False))
        content_items = res.get("content") or []
        text = "\n".join(str(c.get("text", "")) for c in content_items if isinstance(c, dict))
        if not text:
            text = json.dumps(res, indent=2)
        structured = dict(res.get("structuredContent") or res)
        return MCPCallResult(is_err, text, structured)

    def read_resource(self, server_id: str, uri: str) -> MCPCallResult:
        cfg = self.get_server(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if cfg.transport == "builtin":
            return self._builtin_server.read_resource(uri)
        if cfg.transport == "preset":
            connected = self.is_account_connected(server_id)
            payload = {
                "server_id": cfg.id,
                "name": cfg.name,
                "category": cfg.category,
                "auth_env_var": cfg.auth_env_var,
                "account_connected": connected,
                "uri": uri,
            }
            return MCPCallResult(False, json.dumps(payload, indent=2), payload)

        resp = self._send_external_jsonrpc(
            cfg,
            method="resources/read",
            params={"uri": uri},
        )
        res = resp.get("result") or {}
        contents = res.get("contents") or []
        text = "\n".join(str(c.get("text", "")) for c in contents if isinstance(c, dict))
        return MCPCallResult("error" in resp, text or json.dumps(resp, indent=2), res)

    def get_prompt(
        self,
        server_id: str,
        prompt_name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> MCPCallResult:
        cfg = self.get_server(server_id)
        if cfg is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if cfg.transport == "builtin":
            return self._builtin_server.get_prompt(prompt_name, arguments)
        if cfg.transport == "preset":
            topic = str((arguments or {}).get("topic", "Roots & Dub Mix Release"))
            text = (
                f"Workflow Prompt for {cfg.name} ({prompt_name}):\n"
                f"Target Topic: {topic}\n"
                f"1. Run {', '.join(t.name for t in get_preset_tools(cfg.id))} on {cfg.name}.\n"
                f"2. Pipe the output into YouTube Automation Studio's Production & Artwork pipeline."
            )
            return MCPCallResult(False, text, {"prompt": prompt_name, "text": text})

        resp = self._send_external_jsonrpc(
            cfg,
            method="prompts/get",
            params={"name": prompt_name, "arguments": arguments or {}},
        )
        res = resp.get("result") or {}
        return MCPCallResult("error" in resp, json.dumps(res, indent=2), res)

    # ------------------------------------------------------------------
    # Low-Level External Transport Helpers (stdio & HTTP JSON-RPC)
    # ------------------------------------------------------------------

    @staticmethod
    def _send_external_jsonrpc(
        cfg: MCPServerConfig,
        *,
        method: str,
        params: dict[str, Any],
        timeout_sec: float = 10.0,
    ) -> dict[str, Any]:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "youtube-automation-studio", "version": "0.1.0"},
            },
        }
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        target_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": method,
            "params": params,
        }

        if cfg.transport == "stdio":
            if not cfg.command:
                raise ValueError(f"MCP stdio server '{cfg.name}' has no command configured")
            cmd = [cfg.command, *cfg.args]
            env = {**os.environ, **cfg.env}
            if method == "initialize":
                stdin_payload = json.dumps(init_req) + "\n"
                expected_id = 1
            else:
                stdin_payload = (
                    json.dumps(init_req)
                    + "\n"
                    + json.dumps(init_notif)
                    + "\n"
                    + json.dumps(target_req)
                    + "\n"
                )
                expected_id = 2

            proc = subprocess.run(
                cmd,
                input=stdin_payload,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_sec,
                check=False,
            )
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            for line in reversed(lines):
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict) and parsed.get("id") == expected_id:
                        return parsed
                except Exception:
                    continue
            if lines:
                try:
                    return json.loads(lines[-1])
                except Exception:
                    pass
            raise RuntimeError(
                f"No valid JSON-RPC response from stdio server '{cfg.name}' "
                f"(exit={proc.returncode}, stderr={proc.stderr.strip()[:200]})"
            )

        if cfg.transport == "http":
            if not cfg.url:
                raise ValueError(f"MCP HTTP server '{cfg.name}' has no URL configured")
            body = json.dumps(target_req).encode("utf-8")
            req = urllib_request.Request(
                cfg.url,
                data=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
                raw_bytes = resp.read()
                return json.loads(raw_bytes.decode("utf-8"))

        raise ValueError(f"Unsupported transport: {cfg.transport}")
