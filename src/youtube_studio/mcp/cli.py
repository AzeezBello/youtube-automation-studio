"""CLI entrypoint for the YouTube Automation Studio MCP Server (stdio JSON-RPC 2.0)."""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from youtube_studio.mcp.server import StudioMCPServer


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="youtube-studio-mcp",
        description="YouTube Automation Studio — Model Context Protocol (MCP) Server",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the mcpServers JSON configuration snippet for external MCP hosts and exit.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print all exposed Studio MCP tools as JSON and exit.",
    )
    args = parser.parse_args(argv)

    server = StudioMCPServer()
    if args.print_config:
        sys.stdout.write(server.get_host_config_json() + "\n")
        return 0
    if args.list_tools:
        import json

        tools_json = json.dumps([t.to_mcp_dict() for t in server.list_tools()], indent=2)
        sys.stdout.write(tools_json + "\n")
        return 0

    server.serve_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
