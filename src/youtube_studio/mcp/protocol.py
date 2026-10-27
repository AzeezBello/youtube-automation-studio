"""Model Context Protocol (MCP 2024-11-05) data structures and JSON-RPC 2.0 helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

MCP_PROTOCOL_VERSION = "2024-11-05"


@dataclass(frozen=True)
class MCPToolDefinition:
    """Metadata and JSON Schema for an exposed MCP Tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    sample_arguments: dict[str, Any] = field(default_factory=dict)

    def to_mcp_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass(frozen=True)
class MCPResourceDefinition:
    """Metadata for an exposed MCP Resource URI."""

    uri: str
    name: str
    description: str
    mime_type: str = "application/json"

    def to_mcp_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass(frozen=True)
class MCPPromptDefinition:
    """Metadata for a reusable MCP Prompt template."""

    name: str
    description: str
    arguments: list[dict[str, Any]] = field(default_factory=list)

    def to_mcp_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


@dataclass
class MCPServerConfig:
    """Configuration for a built-in, preconfigured preset, or external MCP server connection."""

    id: str
    name: str
    transport: str = "stdio"  # "builtin" | "preset" | "stdio" | "http"
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    enabled: bool = True
    description: str = ""
    category: str = "General"
    auth_env_var: Optional[str] = None
    auth_label: str = "API Key / Account Token"
    docs_url: str = ""
    is_preset: bool = False
    account_connected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Unnamed MCP Server")),
            transport=str(data.get("transport", "stdio")),
            command=data.get("command"),
            args=[str(x) for x in data.get("args", [])],
            env={str(k): str(v) for k, v in (data.get("env") or {}).items()},
            url=data.get("url"),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description", "")),
            category=str(data.get("category", "General")),
            auth_env_var=data.get("auth_env_var"),
            auth_label=str(data.get("auth_label", "API Key / Account Token")),
            docs_url=str(data.get("docs_url", "")),
            is_preset=bool(data.get("is_preset", False)),
            account_connected=bool(data.get("account_connected", False)),
        )


@dataclass(frozen=True)
class MCPCallResult:
    """Normalized result from calling an MCP tool, resource, or prompt."""

    is_error: bool
    text: str
    structured_data: dict[str, Any] = field(default_factory=dict)

    def to_mcp_tool_result(self) -> dict[str, Any]:
        return {
            "isError": self.is_error,
            "content": [{"type": "text", "text": self.text}],
            "structuredContent": self.structured_data,
        }
