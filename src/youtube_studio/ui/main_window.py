"""Main application window – modern dark-studio shell with Onboarding, Product Tour, Empty States & Tooltips."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QFont, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from youtube_studio import __version__
from youtube_studio.config import get_settings
from youtube_studio.domain.services import ChannelService, MediaLibraryService, ProjectService
from youtube_studio.media import FFmpegService
from youtube_studio.storage import session_scope
from youtube_studio.ui.artwork_page import ArtworkPage
from youtube_studio.ui.components import EmptyStateWidget, MetricCard
from youtube_studio.ui.mcp_page import MCPHubPage
from youtube_studio.ui.music_library_page import MusicLibraryPage
from youtube_studio.ui.onboarding_dialog import OnboardingDialog
from youtube_studio.ui.product_tour import ProductTourBanner
from youtube_studio.ui.production_page import ProductionPage
from youtube_studio.ui.research_page import ResearchPage
from youtube_studio.ui.responsive import (
    MOBILE_BREAKPOINT_PX,
    apply_responsive_mode_to_page,
    wrap_in_responsive_scroll,
)
from youtube_studio.ui.settings_page import SettingsPage
from youtube_studio.ui.theme import DARK_STUDIO_STYLESHEET, ThemeManager


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
    """Command center dashboard with KPI cards, empty-state onboarding guide, and quick actions."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_navigate: Optional[Callable[[int], None]] = None,
        on_open_onboarding: Optional[Callable[[], None]] = None,
        on_start_tour: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._on_navigate = on_navigate
        self._on_open_onboarding = on_open_onboarding
        self._on_start_tour = on_start_tour
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        heading = QLabel("Studio Command Center")
        heading.setFont(QFont("", 20, QFont.Weight.Bold))
        layout.addWidget(heading)

        subtitle = QLabel(
            "Local-first multi-channel YouTube research, harmonic mixing, reactive video production, and compliance studio."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(subtitle)

        # KPI Metric Cards Row
        cards_row = QHBoxLayout()
        self.card_channels = MetricCard(
            "Active Channels",
            "0",
            "Brand profiles configured",
            tooltip="Number of active YouTube channel profiles in your local database.",
        )
        self.card_media = MetricCard(
            "Indexed Audio Tracks",
            "0",
            "Ready for harmonic mixing",
            tooltip="Total audio files scanned with BPM, Camelot key, and SHA-256 fingerprint.",
        )
        self.card_projects = MetricCard(
            "Production Projects",
            "0",
            "Single-track & DJ mix timelines",
            tooltip="Total production projects across all channels.",
        )
        self.card_engine = MetricCard(
            "Render Engine",
            "Ready",
            "Checking pipeline…",
            tooltip="Current FFmpeg / fallback media rendering engine status and resource profile.",
        )
        cards_row.addWidget(self.card_channels)
        cards_row.addWidget(self.card_media)
        cards_row.addWidget(self.card_projects)
        cards_row.addWidget(self.card_engine)
        layout.addLayout(cards_row)

        # Empty State Guide (shown when no channels or projects exist yet)
        self.empty_state = EmptyStateWidget(
            title="Welcome to Your Studio — Let's Set Up Your First Release",
            description=(
                "You haven't created a channel or production project yet. Follow the step-by-step Onboarding Flow "
                "or take the Guided Product Tour to explore every workspace."
            ),
            tips=[
                "<b>Step 1 — Onboarding Flow:</b> Create your first channel brand profile and configure your resource profile.",
                "<b>Step 2 — Scan Music Library:</b> Index a local folder of WAV/MP3/FLAC tracks to extract BPM & Camelot keys.",
                "<b>Step 3 — Produce & Package:</b> Sequence a mix in Production, generate 16:9 artwork, and audit via the Compliance Gate.",
            ],
            action_label="Open Step-by-Step Onboarding",
            action_tooltip="Launch the 4-step Onboarding Wizard to set up your first channel and preferences.",
            on_action=lambda: self._on_open_onboarding() if self._on_open_onboarding else None,
            secondary_label="Start Guided Product Tour",
            secondary_tooltip="Take an interactive 7-step tour of all studio workspaces.",
            on_secondary=lambda: self._on_start_tour() if self._on_start_tour else None,
        )
        layout.addWidget(self.empty_state)

        # Quick Actions Bar (2 rows of 3 buttons so it never overflows horizontally)
        quick_group = QGroupBox("Quick Workflow Actions")
        quick_outer = QVBoxLayout(quick_group)
        quick_outer.setSpacing(8)
        quick_row_top = QHBoxLayout()
        quick_row_bottom = QHBoxLayout()

        btn_research = QPushButton("1. Discover Topics (Research)")
        btn_research.setToolTip("Open Research Workspace to search keywords, cluster topics, and save video ideas.")
        btn_research.clicked.connect(lambda: self._nav(1))
        quick_row_top.addWidget(btn_research)

        btn_library = QPushButton("2. Scan Audio (Music Library)")
        btn_library.setToolTip("Open Music Library to scan folders and analyze track BPM & Camelot keys.")
        btn_library.clicked.connect(lambda: self._nav(2))
        quick_row_top.addWidget(btn_library)

        btn_produce = QPushButton("3. Build Mix && Video (Production)")
        btn_produce.setObjectName("PrimaryButton")
        btn_produce.setToolTip("Open Production Studio to sequence tracks, configure visualizers, and render videos.")
        btn_produce.clicked.connect(lambda: self._nav(3))
        quick_row_top.addWidget(btn_produce)

        btn_artwork = QPushButton("4. Generate Artwork && SEO (AI Studio)")
        btn_artwork.setToolTip("Open Artwork & Local AI Studio to generate 16:9 / 9:16 thumbnails and metadata.")
        btn_artwork.clicked.connect(lambda: self._nav(4))
        quick_row_bottom.addWidget(btn_artwork)

        btn_mcp = QPushButton("5. Connect MCP (vidIQ && AI)")
        btn_mcp.setToolTip("Open MCP Hub to connect preconfigured vidIQ, TubeBuddy, Suno, or external MCP servers.")
        btn_mcp.clicked.connect(lambda: self._nav(5))
        quick_row_bottom.addWidget(btn_mcp)

        btn_settings = QPushButton("6. Backup && Compliance Gate")
        btn_settings.setToolTip("Open Settings to manage API credentials, create DB snapshots, and audit export manifests.")
        btn_settings.clicked.connect(lambda: self._nav(6))
        quick_row_bottom.addWidget(btn_settings)

        quick_outer.addLayout(quick_row_top)
        quick_outer.addLayout(quick_row_bottom)
        layout.addWidget(quick_group)

        # Detailed Status Box
        status_group = QGroupBox("System Environment & Database Diagnostics")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel("Loading status…")
        self.status_label.setWordWrap(True)
        self.status_label.setToolTip("Live diagnostics for application paths, FFmpeg status, and database records.")
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_group)

        layout.addStretch()

    def _nav(self, index: int) -> None:
        if self._on_navigate:
            self._on_navigate(index)

    def refresh(self) -> None:
        settings = get_settings()
        ffmpeg = FFmpegService()
        info = ffmpeg.get_info()

        lines = [
            f"<b>Application:</b> {settings.app_name} v{__version__}",
            f"<b>Output directory:</b> {settings.resolved_output_dir()}",
            f"<b>Data directory:</b> {settings.resolved_data_dir()}",
            f"<b>Resource profile:</b> {settings.resource_profile.value}",
        ]
        if info:
            lines.append(f"<b>FFmpeg:</b> {info.ffmpeg_version}")
            lines.append(
                f"<b>Hardware acceleration:</b> {'available' if info.has_hwaccel else 'not detected'}"
            )
            self.card_engine.set_metric(
                "FFmpeg Active",
                f"Profile: {settings.resource_profile.value}",
            )
        else:
            lines.append(
                "<b>FFmpeg:</b> <span style='color:#f39c12'>not found on PATH (WAV/PNG fallback pipeline active)</span>"
            )
            self.card_engine.set_metric(
                "Fallback Active",
                f"Profile: {settings.resource_profile.value}",
            )

        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
                media_files = MediaLibraryService(session).list_media()
                projects = ProjectService(session).list_projects()
            lines.append(f"<b>Active channels:</b> {len(channels)}")
            if channels:
                names = ", ".join(c.name for c in channels[:5])
                lines.append(f"&nbsp;&nbsp;{names}")
            lines.append(f"<b>Indexed media files:</b> {len(media_files)}")
            lines.append(f"<b>Production projects:</b> {len(projects)}")

            self.card_channels.set_metric(
                str(len(channels)),
                ", ".join(c.name for c in channels[:2]) if channels else "Create your first channel",
            )
            self.card_media.set_metric(
                str(len(media_files)),
                "Audio tracks indexed" if media_files else "Scan a music folder to begin",
            )
            self.card_projects.set_metric(
                str(len(projects)),
                "Active mix/video timelines" if projects else "No projects created yet",
            )
            if hasattr(self, "empty_state"):
                self.empty_state.setVisible(len(channels) == 0 or len(projects) == 0)
        except Exception as exc:
            lines.append(f"<b>Database:</b> <span style='color:#e74c3c'>{exc}</span>")

        self.status_label.setText("<br>".join(lines))


class MainWindow(QMainWindow):
    NAV_ITEMS = [
        ("Dashboard", "dashboard", "Overview of channels, media library, projects, and quick actions."),
        ("Research", "research", "Keyword discovery, topic clustering, watchlists, and production hand-off."),
        ("Music Library", "music_library", "Scan local audio folders, inspect BPM & Camelot keys, and find duplicates."),
        ("Production", "production", "Build harmonic mixes, apply transitions & visualizers, and render videos/Shorts."),
        ("Artwork", "artwork", "Generate 16:9 / 9:16 thumbnails and SEO metadata with local AI or templates."),
        ("MCP Hub", "mcp_hub", "Connect AI agents via the built-in Studio MCP Server or manage external MCP servers."),
        ("Settings", "settings", "Manage Credential Vault API keys, SQLite snapshots, and Compliance Review Gate."),
    ]

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.setWindowTitle(f"{settings.app_name} v{__version__}")
        self._is_mobile_mode: Optional[bool] = None
        self.setMinimumSize(360, 500)
        self._build_ui()
        self._build_menu()
        self.apply_theme(ThemeManager.get_preference())
        self._apply_initial_screen_geometry()
        self._update_responsive_mode(force=True)
        self.statusBar().showMessage(
            "Ready — Hover over any control for tooltips, or click 'Product Tour' above."
        )

        # Automatically trigger onboarding wizard on first interactive launch
        QTimer.singleShot(150, self._maybe_show_first_run_onboarding)

    def _apply_initial_screen_geometry(self) -> None:
        """Size and center the window within the user's available screen geometry (respecting macOS Menu Bar & Dock)."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_w = min(1120, max(380, int(avail.width() * 0.88)))
            target_h = min(680, max(500, int(avail.height() * 0.85)))
            self.resize(target_w, target_h)
            x = avail.x() + max(0, (avail.width() - target_w) // 2)
            y = avail.y() + max(0, (avail.height() - target_h) // 2)
            self.move(x, y)
        else:
            self.resize(1040, 660)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setMinimumSize(340, 440)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top Header Bar with Hamburger Menu, Responsive Viewport Switcher, Onboarding & Product Tour controls
        header = QFrame()
        header.setObjectName("TopHeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)

        self.btn_menu_toggle = QPushButton("☰")
        self.btn_menu_toggle.setFixedWidth(36)
        self.btn_menu_toggle.setToolTip("Show or hide the workspace navigation bar (useful on compact/mobile screens).")
        self.btn_menu_toggle.clicked.connect(self._toggle_nav_visibility)
        header_layout.addWidget(self.btn_menu_toggle)

        self.brand_title = QLabel("🎬  YouTube Automation Studio")
        self.brand_title.setFont(QFont("", 14, QFont.Weight.Bold))
        self.brand_title.setStyleSheet("color: #f8fafc;")
        header_layout.addWidget(self.brand_title)

        self.version_badge = QLabel(f"v{__version__} · Local-First Pro Studio")
        self.version_badge.setObjectName("VersionBadge")
        header_layout.addWidget(self.version_badge)
        header_layout.addStretch()

        self.btn_theme = QPushButton("☀️ Light")
        self.btn_theme.setToolTip("Switch between Dark Mode and Light Mode (or choose System in the View menu).")
        self.btn_theme.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.btn_theme)

        self.btn_onboarding = QPushButton("✦ Onboarding Setup")
        self.btn_onboarding.setToolTip(
            "Open the step-by-step Onboarding Flow to configure your channel, hardware profile, and API key."
        )
        self.btn_onboarding.clicked.connect(self.open_onboarding_dialog)
        header_layout.addWidget(self.btn_onboarding)

        self.btn_tour = QPushButton("🧭 Start Product Tour")
        self.btn_tour.setObjectName("PrimaryButton")
        self.btn_tour.setToolTip(
            "Launch the interactive 7-step Guided Product Tour across all studio workspaces."
        )
        self.btn_tour.clicked.connect(self.start_product_tour)
        header_layout.addWidget(self.btn_tour)

        outer.addWidget(header)

        # Main workspace area (Sidebar/TopBar + Scrollable Content column)
        self.workspace_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.workspace_row.setContentsMargins(0, 0, 0, 0)
        self.workspace_row.setSpacing(0)

        # Navigation (adapts between Left Vertical Sidebar on Desktop and Top Horizontal Bar on Mobile)
        self.nav = QListWidget()
        self.nav.setObjectName("SideNav")
        self.nav.setFixedWidth(190)
        self.nav.setSpacing(3)
        self.nav.setToolTip("Switch between the 7 studio workspaces.")
        for label, _, tip in self.NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setToolTip(tip)
            item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.workspace_row.addWidget(self.nav)

        # Right side: Guided Product Tour Banner + Scroll-Wrapped Stacked Pages
        right_container = QVBoxLayout()
        right_container.setContentsMargins(10, 8, 10, 8)
        right_container.setSpacing(6)

        self.tour_banner = ProductTourBanner(
            on_select_nav=self._select_nav_from_tour,
            parent=self,
        )
        right_container.addWidget(self.tour_banner)

        self.stack = QStackedWidget()
        self.stack.setMinimumSize(280, 220)
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.pages: dict[str, QWidget] = {
            "dashboard": DashboardPage(
                on_navigate=self.nav.setCurrentRow,
                on_open_onboarding=self.open_onboarding_dialog,
                on_start_tour=self.start_product_tour,
            ),
            "research": ResearchPage(),
            "music_library": MusicLibraryPage(),
            "production": ProductionPage(),
            "artwork": ArtworkPage(),
            "mcp_hub": MCPHubPage(),
            "settings": SettingsPage(),
        }
        for _, key, _ in self.NAV_ITEMS:
            scroll_wrapper = wrap_in_responsive_scroll(self.pages[key], parent=self.stack)
            self.stack.addWidget(scroll_wrapper)
        # Ensure Dashboard & Research reflect any channel synced by MCPHubPage on launch
        for key in ("dashboard", "research", "production", "artwork"):
            page = self.pages.get(key)
            if page is not None and hasattr(page, "refresh"):
                page.refresh()
        right_container.addWidget(self.stack, stretch=1)

        self.workspace_row.addLayout(right_container, stretch=1)
        outer.addLayout(self.workspace_row, stretch=1)

    def _toggle_nav_visibility(self) -> None:
        self.nav.setVisible(not self.nav.isVisible())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive_mode()

    def _update_responsive_mode(self, *, force: bool = False) -> None:
        is_mobile = self.width() < MOBILE_BREAKPOINT_PX
        if not force and self._is_mobile_mode == is_mobile:
            return
        self._is_mobile_mode = is_mobile

        if is_mobile:
            self.workspace_row.setDirection(QBoxLayout.Direction.TopToBottom)
            self.nav.setFlow(QListView.Flow.LeftToRight)
            self.nav.setWrapping(False)
            self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.nav.setMinimumWidth(0)
            self.nav.setMaximumWidth(16777215)
            self.nav.setFixedHeight(48)
            self.version_badge.setVisible(False)
            self.brand_title.setText("🎬 YT Studio")
            self.btn_onboarding.setText("✦ Setup")
            self.btn_tour.setText("🧭 Tour")
        else:
            self.workspace_row.setDirection(QBoxLayout.Direction.LeftToRight)
            self.nav.setFlow(QListView.Flow.TopToBottom)
            self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.nav.setFixedWidth(190)
            self.nav.setMinimumHeight(0)
            self.nav.setMaximumHeight(16777215)
            self.version_badge.setVisible(True)
            self.brand_title.setText("🎬  YouTube Automation Studio")
            self.btn_onboarding.setText("✦ Onboarding Setup")
            self.btn_tour.setText("🧭 Start Product Tour")

        for page in self.pages.values():
            apply_responsive_mode_to_page(page, is_mobile)

    def apply_theme(self, mode: str) -> None:
        """Apply 'dark', 'light', or 'system' theme to the application window and persist preference."""
        saved = ThemeManager.set_preference(mode)
        effective = ThemeManager.resolve_effective_theme(saved)
        self.setStyleSheet(ThemeManager.get_stylesheet(saved))
        if effective == "light":
            self.brand_title.setStyleSheet("color: #0f172a;")
            self.btn_theme.setText("🌙 Dark")
        else:
            self.brand_title.setStyleSheet("color: #f8fafc;")
            self.btn_theme.setText("☀️ Light")

    def toggle_theme(self) -> None:
        """Toggle between Dark Mode and Light Mode."""
        current_effective = ThemeManager.resolve_effective_theme()
        next_mode = "light" if current_effective == "dark" else "dark"
        self.apply_theme(next_mode)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = menubar.addMenu("&View")
        dark_action = QAction("🌙 &Dark Mode", self)
        dark_action.triggered.connect(lambda: self.apply_theme("dark"))
        view_menu.addAction(dark_action)

        light_action = QAction("☀️ &Light Mode", self)
        light_action.triggered.connect(lambda: self.apply_theme("light"))
        view_menu.addAction(light_action)

        system_action = QAction("💻 &Follow System Theme", self)
        system_action.triggered.connect(lambda: self.apply_theme("system"))
        view_menu.addAction(system_action)

        help_menu = menubar.addMenu("&Help")
        onboarding_action = QAction("&Onboarding Setup Wizard…", self)
        onboarding_action.triggered.connect(self.open_onboarding_dialog)
        help_menu.addAction(onboarding_action)

        tour_action = QAction("Start &Guided Product Tour", self)
        tour_action.triggered.connect(self.start_product_tour)
        help_menu.addAction(tour_action)

        help_menu.addSeparator()
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _maybe_show_first_run_onboarding(self) -> None:
        if QApplication.platformName() == "offscreen":
            return
        if not OnboardingDialog.is_onboarding_completed():
            self.open_onboarding_dialog()

    def open_onboarding_dialog(self) -> OnboardingDialog:
        dlg = OnboardingDialog(
            self,
            on_start_tour=self.start_product_tour,
            on_completed=self._refresh_all_pages,
        )
        dlg.setStyleSheet(ThemeManager.get_stylesheet())
        if QApplication.platformName() != "offscreen":
            dlg.exec()
        return dlg

    def start_product_tour(self) -> None:
        self.tour_banner.start_tour(0)

    def _select_nav_from_tour(self, index: int) -> None:
        if 0 <= index < self.nav.count():
            self.nav.setCurrentRow(index)

    def _refresh_all_pages(self) -> None:
        for page in self.pages.values():
            if hasattr(page, "refresh"):
                page.refresh()  # type: ignore[attr-defined]

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
            key = self.NAV_ITEMS[index][1]
            page = self.pages.get(key)
            if hasattr(page, "refresh"):
                page.refresh()  # type: ignore[attr-defined]

    def _show_about(self) -> None:
        settings = get_settings()
        QMessageBox.about(
            self,
            "About",
            f"<b>{settings.app_name}</b><br>"
            f"Version {__version__}<br><br>"
            "Local-first multi-channel YouTube research & production studio.<br>"
            "No mandatory third-party SEO or paid AI subscription.",
        )
