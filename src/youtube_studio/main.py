"""CLI / desktop entry point."""

from __future__ import annotations

import sys

from youtube_studio.app import run


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
