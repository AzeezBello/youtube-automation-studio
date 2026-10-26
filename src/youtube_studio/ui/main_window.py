"""Main application window – navigation shell."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from youtube_studio import __version__
from youtube_studio.config import get_settings
from youtube_studio.media import FFmpegService
from youtube_studio.storage import session_scope
from youtube_studio.domain.services import ChannelService


class PlaceholderPage(QWidget):
    def __init__(self, title: str, description: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        body = QLabel(description)
        body.setWordWrap(True)
        body.setStyleSheet("color: #aaa;")
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addStretch()


class DashboardPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel("Dashboard")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        layout.addWidget(heading)

        self.status_label = QLabel("Loading status…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch()
        self.refresh()

    def refresh(self) -> None:
        settings = get_settings()
        ffmpeg = FFmpegService()
        info = ffmpeg.get_info()

        lines = [
            f"<b>Application:</b> {settings.app_name} v{__version__}",
            f"<b>Data directory:</b> {settings.resolved_data_dir()}",
            f"<b>Resource profile:</b> {settings.resource_profile.value}",
        ]
        if info:
            lines.append(f"<b>FFmpeg:</b> {info.ffmpeg_version}")
            lines.append(f"<b>Hardware acceleration:</b> {'available' if info.has_hwaccel else 'not detected'}")
        else:
            lines.append("<b>FFmpeg:</b> <span style='color:#e74c3c'>not found on PATH</span>")

        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
            lines.append(f"<b>Active channels:</b> {len(channels)}")
            if channels:
                names = ", ".join(c.name for c in channels[:5])
                lines.append(f"&nbsp;&nbsp;{names}")
        except Exception as exc:
            lines.append(f"<b>Database:</b> <span style='color:#e74c3c'>{exc}</span>")

        self.status_label.setText("<br>".join(lines))


class MainWindow(QMainWindow):
    NAV_ITEMS = [
        ("Dashboard", "dashboard"),
        ("Research", "research"),
        ("Music Library", "music_library"),
        ("Production", "production"),
        ("Artwork", "artwork"),
        ("Analytics", "analytics"),
        ("Publishing", "publishing"),
        ("Settings", "settings"),
    ]

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.setWindowTitle(f"{settings.app_name}")
        self.resize(1200, 750)
        self._build_ui()
        self._build_menu()
        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        # Side navigation
        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        self.nav.setSpacing(2)
        for label, _ in self.NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        root.addWidget(self.nav)

        # Pages
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {
            "dashboard": DashboardPage(),
            "research": PlaceholderPage(
                "Research Workspace",
                "Keyword discovery, competitor watchlists, and content briefs.\n"
                "Public YouTube data is retained according to API policy (≤ 30 days).",
            ),
            "music_library": PlaceholderPage(
                "Music Library",
                "Scan folders, detect duplicates, build playlists, and prepare tracks for production.",
            ),
            "production": PlaceholderPage(
                "Production",
                "Single-track videos, DJ mixes, compilations, waveform visualizers, and render queue.",
            ),
            "artwork": PlaceholderPage(
                "Artwork & Thumbnails",
                "Local image generation (when hardware permits), templates, and approval workflow.",
            ),
            "analytics": PlaceholderPage(
                "Channel Analytics",
                "Authorized YouTube Analytics reports only. No fabricated metrics.",
            ),
            "publishing": PlaceholderPage(
                "Publishing",
                "Upload preparation, privacy controls, scheduling, and explicit user approval gates.",
            ),
            "settings": PlaceholderPage(
                "Settings",
                "FFmpeg paths, model locations, resource profile, data directory, and credentials.",
            ),
        }
        for key, _ in self.NAV_ITEMS:
            self.stack.addWidget(self.pages[key])
        root.addWidget(self.stack, stretch=1)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            if index == 0:
                dashboard = self.pages["dashboard"]
                if isinstance(dashboard, DashboardPage):
                    dashboard.refresh()

    def _show_about(self) -> None:
        settings = get_settings()
        QMessageBox.about(
            self,
            "About",
            f"<b>{settings.app_name}</b><br>"
            f"Version {__version__}<br><br>"
            "Local-first multi-channel YouTube research & production studio.<br>"
            "No mandatory vidIQ or paid AI subscription.",
        )
