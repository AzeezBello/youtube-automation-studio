"""Model Context Protocol (MCP) Server & Client Hub package for YouTube Automation Studio."""

from .client import MCPClientHub
from .protocol import (
    MCP_PROTOCOL_VERSION,
    MCPCallResult,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPServerConfig,
    MCPToolDefinition,
)
from .server import StudioMCPServer

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "MCPCallResult",
    "MCPClientHub",
    "MCPPromptDefinition",
    "MCPResourceDefinition",
    "MCPServerConfig",
    "MCPToolDefinition",
    "StudioMCPServer",
]
