"""Application factory."""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication

from youtube_studio.config import get_settings
from youtube_studio.storage import get_engine
from youtube_studio.storage.orm import Base
from youtube_studio.ui import MainWindow


def create_app(argv: Optional[list[str]] = None) -> QApplication:
    """Create and configure the QApplication + ensure DB schema exists."""
    settings = get_settings()
    settings.ensure_directories()

    # Ensure tables exist (simple bootstrap; Alembic used for real migrations)
    engine = get_engine()
    Base.metadata.create_all(engine)

    app = QApplication(argv or sys.argv)
    app.setApplicationName(settings.app_name)
    app.setApplicationVersion(settings.app_version)
    app.setOrganizationName("YouTube Automation Studio")
    return app


def run() -> int:
    app = create_app()
    window = MainWindow()
    window.show()
    return app.exec()
