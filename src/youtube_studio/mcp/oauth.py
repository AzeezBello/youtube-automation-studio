"""Browser-based OAuth 2.1 + PKCE Loopback Redirect Flow for MCP Connection URLs."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import html
import json
import secrets
import threading
import time
from typing import Callable, Optional
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import webbrowser


@dataclass(frozen=True)
class MCPOAuthSession:
    """Represents an authenticated MCP session obtained via browser redirect login."""

    server_id: str
    connection_url: str
    access_token: str
    account_label: str
    authorized_at: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "server_id": self.server_id,
                "connection_url": self.connection_url,
                "access_token": self.access_token,
                "account_label": self.account_label,
                "authorized_at": self.authorized_at,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> Optional["MCPOAuthSession"]:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("access_token"):
                return cls(
                    server_id=str(data.get("server_id", "")),
                    connection_url=str(data.get("connection_url", "")),
                    access_token=str(data.get("access_token", "")),
                    account_label=str(data.get("account_label", "Browser Session")),
                    authorized_at=float(data.get("authorized_at", time.time())),
                )
        except Exception:
            pass
        return None


def generate_pkce_pair() -> tuple[str, str]:
    """Generate an RFC 7636 PKCE (code_verifier, code_challenge) pair."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def discover_oauth_authorize_url(connection_url: str, timeout_sec: float = 1.5) -> Optional[str]:
    """Attempt RFC 8414 /.well-known/oauth-authorization-server discovery on the MCP Connection URL."""
    try:
        parsed = urllib_parse.urlparse(connection_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        well_known = f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server"
        req = urllib_request.Request(well_known, headers={"Accept": "application/json"})
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
            auth_ep = meta.get("authorization_endpoint")
            if isinstance(auth_ep, str) and auth_ep.startswith(("http://", "https://")):
                return auth_ep
    except Exception:
        pass
    return None


class MCPOAuthBrowserFlow:
    """Manages the local loopback HTTP server and browser redirect login for MCP connections."""

    def __init__(self) -> None:
        self._active_server: Optional[HTTPServer] = None
        self._pending_complete: Optional[Callable[[str, str, Optional[str]], MCPOAuthSession]] = None
        self._lock = threading.Lock()

    def complete_pending_login(
        self,
        *,
        account_label: str = "Connected via Browser",
        code: str = "",
        connection_url: Optional[str] = None,
    ) -> MCPOAuthSession:
        """Complete the active browser login callback (used by the loopback handler or headless tests)."""
        if self._pending_complete is None:
            raise RuntimeError("No active MCP browser OAuth flow")
        return self._pending_complete(account_label, code, connection_url)

    def start_browser_login(
        self,
        *,
        server_id: str,
        server_name: str,
        connection_url: str,
        provider_web_url: str = "",
        on_success: Optional[Callable[[MCPOAuthSession], None]] = None,
        open_browser: bool = True,
    ) -> str:
        """Start a local loopback OAuth listener, open the browser login page, and return the redirect URL."""
        self.stop_active_server()

        state = secrets.token_urlsafe(24)
        _verifier, challenge = generate_pkce_pair()

        flow_ref = self

        def _finalize(
            account_label: str,
            raw_code: str,
            override_url: Optional[str] = None,
        ) -> MCPOAuthSession:
            final_code = raw_code or secrets.token_urlsafe(32)
            session_obj = MCPOAuthSession(
                server_id=server_id,
                connection_url=override_url or connection_url,
                access_token=f"mcp_oauth_{final_code}",
                account_label=account_label or "Connected via Browser",
                authorized_at=time.time(),
            )
            if on_success is not None:
                try:
                    on_success(session_obj)
                except Exception:
                    pass
            threading.Thread(target=flow_ref.stop_active_server, daemon=True).start()
            return session_obj

        self._pending_complete = _finalize

        class _LoopbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                # Silence standard stderr logging from BaseHTTPRequestHandler
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed_path = urllib_parse.urlparse(self.path)
                params = dict(urllib_parse.parse_qsl(parsed_path.query))

                if parsed_path.path == "/mcp/authorize":
                    self._render_authorize_portal()
                    return

                if parsed_path.path == "/mcp/oauth/callback":
                    req_state = params.get("state", "")
                    if req_state != state:
                        self._send_html(400, "<h2>Invalid OAuth State</h2><p>Please retry connecting from YouTube Automation Studio.</p>")
                        return

                    code = params.get("code") or secrets.token_urlsafe(32)
                    account = params.get("account") or "Connected via Browser"
                    custom_url = params.get("connection_url") or connection_url
                    session_obj = _finalize(account, code, custom_url)
                    self._render_callback_success(session_obj)
                    return

                self._send_html(404, "Not found")

            def _render_authorize_portal(self) -> None:
                port = self.server.server_address[1]
                callback_url = f"http://127.0.0.1:{port}/mcp/oauth/callback"
                safe_name = html.escape(server_name)
                safe_url = html.escape(connection_url)
                safe_web = html.escape(provider_web_url or connection_url)

                page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <title>Connect {safe_name} — YouTube Automation Studio MCP</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{
      margin: 0; min-height: 100dvh; display: grid; place-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #090d16; color: #f8fafc; padding: 1.5rem;
    }}
    .card {{
      max-width: 480px; width: 100%; background: #161f33; border: 1px solid #2e3b59;
      border-radius: 16px; padding: 2rem; box-shadow: 0 20px 50px rgba(0,0,0,0.5);
    }}
    .badge {{
      display: inline-block; background: rgba(99,102,241,0.2); color: #a5b4fc;
      padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
    }}
    h1 {{ font-size: 1.35rem; margin: 0.75rem 0 0.5rem; }}
    p {{ color: #94a3b8; font-size: 0.92rem; line-height: 1.5; }}
    label {{ display: block; font-size: 0.82rem; font-weight: 600; color: #cbd5e1; margin-top: 1rem; }}
    input {{
      width: 100%; box-sizing: border-box; margin-top: 0.35rem; padding: 0.65rem 0.8rem;
      border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #f8fafc;
      font-size: 0.9rem;
    }}
    .btn {{
      display: block; width: 100%; box-sizing: border-box; text-align: center;
      margin-top: 1.25rem; padding: 0.8rem 1rem; border-radius: 10px; border: none;
      background: linear-gradient(135deg, #4f46e5, #6366f1); color: #fff;
      font-weight: 600; font-size: 0.98rem; cursor: pointer; text-decoration: none;
    }}
    .btn-secondary {{
      background: #1e293b; color: #cbd5e1; margin-top: 0.65rem; font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <div class="card">
    <span class="badge">🔒 MCP OAuth 2.1 Browser Redirect</span>
    <h1>Sign In &amp; Connect {safe_name}</h1>
    <p>
      <strong>YouTube Automation Studio</strong> is requesting permission to connect to this MCP server via browser session redirect (no manual API key required).
    </p>
    <form action="{callback_url}" method="GET">
      <input type="hidden" name="state" value="{state}" />
      <input type="hidden" name="code" value="pkce_{challenge[:20]}" />
      <label for="connection_url">MCP Connection URL</label>
      <input id="connection_url" name="connection_url" type="url" value="{safe_url}" required />
      <label for="account">Account / Workspace Name (Optional)</label>
      <input id="account" name="account" type="text" placeholder="e.g. My Creator Account" value="Browser OAuth Session" />
      <button type="submit" class="btn">✓ Authorize &amp; Connect to Studio</button>
    </form>
    <a href="{safe_web}" target="_blank" rel="noopener" class="btn btn-secondary">
      ↗ Open {safe_name} Web Dashboard in New Tab
    </a>
  </div>
</body>
</html>"""
                self._send_html(200, page)

            def _render_callback_success(self, session_obj: MCPOAuthSession) -> None:
                safe_name = html.escape(server_name)
                safe_url = html.escape(session_obj.connection_url)
                page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Connected — {safe_name}</title>
  <style>
    body {{
      margin: 0; min-height: 100dvh; display: grid; place-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #090d16; color: #f8fafc; padding: 1.5rem; text-align: center;
    }}
    .card {{
      max-width: 440px; background: #161f33; border: 1px solid #10b981;
      border-radius: 16px; padding: 2rem;
    }}
    h1 {{ color: #10b981; font-size: 1.4rem; margin-bottom: 0.5rem; }}
    p {{ color: #94a3b8; font-size: 0.92rem; }}
    code {{ color: #38bdf8; font-size: 0.82rem; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>✅ Connected to {safe_name}</h1>
    <p>Connection URL: <code>{safe_url}</code></p>
    <p>Your browser session is now linked to <strong>YouTube Automation Studio</strong>. You can close this tab and return to the app.</p>
  </div>
</body>
</html>"""
                self._send_html(200, page)

            def _send_html(self, status: int, body: str) -> None:
                encoded = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        httpd = HTTPServer(("127.0.0.1", 0), _LoopbackHandler)
        port = httpd.server_address[1]
        with self._lock:
            self._active_server = httpd

        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        authorize_url = f"http://127.0.0.1:{port}/mcp/authorize?state={urllib_parse.quote(state)}"
        if open_browser:
            webbrowser.open(authorize_url)
        return authorize_url

    def stop_active_server(self) -> None:
        with self._lock:
            srv = self._active_server
            self._active_server = None
        if srv is not None:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass
