"""CLI entrypoint for running the YouTube Automation Studio HTTP/FastAPI server."""

from __future__ import annotations

import argparse
from typing import Optional

from youtube_studio.api.app import create_api_app, create_fastapi_app, make_stdlib_http_server


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube Automation Studio HTTP / FastAPI Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument(
        "--mode",
        choices=["desktop_local", "saas"],
        default="desktop_local",
        help="Execution mode (desktop_local or saas)",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn

        fapp = create_fastapi_app(run_mode=args.mode)
        if not hasattr(fapp, "dispatch"):
            uvicorn.run(fapp, host=args.host, port=args.port)
            return 0
    except ImportError:
        pass

    api_app = create_api_app(run_mode=args.mode)
    server = make_stdlib_http_server(api_app, host=args.host, port=args.port)
    print(f"YouTube Automation Studio API running on http://{args.host}:{args.port} (mode={args.mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
