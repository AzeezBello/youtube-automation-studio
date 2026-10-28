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
    QHeaderView,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio import __version__
from youtube_studio.config import get_settings
from youtube_studio.domain.services import ChannelService, MediaLibraryService, ProjectService
from youtube_studio.media import FFmpegService
from youtube_studio.storage import session_scope
from youtube_studio.ui.artwork_page import ArtworkPage
from youtube_studio.ui.brand_assets import BrandAssetsService
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
from youtube_studio.ui.script_voice_page import ScriptVoicePage
from youtube_studio.ui.settings_page import SettingsPage
from youtube_studio.ui.theme import ThemeManager
from youtube_studio.ui.timeline_editor import TimelineEditorPage


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
    """Minimalist Home Launchpad with '+ New project' Hero Banner, More Tools Grid, Projects & Collapsible Diagnostics."""

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
        self._project_ids: list[str] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(16)

        # Studio Hero Banner Row ('+ New project' Cyan Gradient + Video Studio / Design Studio Cards)
        hero_cards_row = QHBoxLayout()
        hero_cards_row.setSpacing(14)

        self.btn_hero_new_project = QPushButton("＋  New project")
        self.btn_hero_new_project.setMinimumHeight(124)
        self.btn_hero_new_project.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hero_new_project.setStyleSheet(
            "QPushButton { "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #67e8f9, stop:0.55 #06b6d4, stop:1 #0284c7); "
            "color: #042f2e; font-size: 18px; font-weight: bold; border-radius: 12px; border: none; padding: 20px; "
            "} "
            "QPushButton:hover { "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #a5f3fc, stop:0.55 #22d3ee, stop:1 #0369a1); "
            "}"
        )
        self.btn_hero_new_project.setToolTip(
            "Create or edit a project in the 4-Pane Video & Timeline Studio."
        )
        self.btn_hero_new_project.clicked.connect(lambda: self._nav(5))
        hero_cards_row.addWidget(self.btn_hero_new_project, stretch=3)

        right_hero_col = QVBoxLayout()
        right_hero_col.setSpacing(10)

        btn_video_studio = QPushButton("🎬  Video Studio")
        btn_video_studio.setMinimumHeight(57)
        btn_video_studio.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_video_studio.setStyleSheet(
            "QPushButton { background-color: #163042; color: #e0f2fe; font-size: 14px; font-weight: bold; "
            "border: 1px solid #0284c7; border-radius: 10px; padding: 12px 16px; text-align: left; } "
            "QPushButton:hover { background-color: #0c4a6e; }"
        )
        btn_video_studio.setToolTip("Open the 4-Pane Timeline Editor (Media Browser | Player | Details | Multi-Track Timeline).")
        btn_video_studio.clicked.connect(lambda: self._nav(5))
        right_hero_col.addWidget(btn_video_studio)

        btn_design_studio = QPushButton("🎨  Design Studio  [New]")
        btn_design_studio.setMinimumHeight(57)
        btn_design_studio.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_design_studio.setStyleSheet(
            "QPushButton { background-color: #1b1e36; color: #e0e7ff; font-size: 14px; font-weight: bold; "
            "border: 1px solid #4f46e5; border-radius: 10px; padding: 12px 16px; text-align: left; } "
            "QPushButton:hover { background-color: #312e81; }"
        )
        btn_design_studio.setToolTip("Open Artwork & SEO Studio for 16:9 / 9:16 thumbnails, Style Lock, and Ranked Titles.")
        btn_design_studio.clicked.connect(lambda: self._nav(6))
        right_hero_col.addWidget(btn_design_studio)

        hero_cards_row.addLayout(right_hero_col, stretch=2)
        layout.addLayout(hero_cards_row)

        # More Tools Icon Bar (6 Clean Dark-Glass Tiles)
        tools_hdr = QLabel("<b>More tools</b>")
        tools_hdr.setStyleSheet("color: #f8fafc; font-size: 14px;")
        layout.addWidget(tools_hdr)

        tools_row = QHBoxLayout()
        tools_row.setSpacing(10)

        tool_specs = [
            ("🔗\nURL to Brief", "Import YouTube URL metadata & chapters into a Research Brief.", 1),
            ("✂️\nLong video to shorts", "Auto-clip peak 30s 9:16 vertical Shorts.", 4),
            ("✍️\nAI Script & Hook", "Draft 1. Hook → 2. Outline → 3. Full Narration Script.", 3),
            ("🎙\nAI Voiceover", "Synthesize local Male/Female voiceovers with speed control.", 3),
            ("🏆\nTitle Scorer", "Rank 5 title candidates by transparent length, keyword & tone rules.", 6),
            ("🚀\n1-Click Auto-Video", "End-to-end autopilot from audio folder or YouTube URL.", 4),
        ]
        for label_txt, tip_txt, target_idx in tool_specs:
            btn = QPushButton(label_txt)
            btn.setMinimumHeight(68)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip_txt)
            btn.setStyleSheet(
                "QPushButton { background-color: #141824; color: #cbd5e1; border: 1px solid #22293a; "
                "border-radius: 10px; padding: 10px 8px; font-weight: 600; font-size: 12px; } "
                "QPushButton:hover { border-color: #06b6d4; color: #22d3ee; background-color: #192132; }"
            )
            btn.clicked.connect(lambda _checked=False, idx=target_idx: self._nav(idx))
            tools_row.addWidget(btn, stretch=1)

        layout.addLayout(tools_row)

        # Projects Section
        proj_hdr = QLabel("<b>Projects</b>")
        proj_hdr.setStyleSheet("color: #f8fafc; font-size: 14px;")
        layout.addWidget(proj_hdr)

        self.empty_state = EmptyStateWidget(
            title="Project edited will be saved automatically. Start creating your own videos!",
            description=(
                "Click '＋ New project' above, launch the Onboarding Wizard, or take the Guided Product Tour."
            ),
            tips=[
                "<b>Step 1 — Onboarding Flow:</b> Create your first channel brand profile and configure your resource profile.",
                "<b>Step 2 — Script & Voiceover Studio:</b> Draft Hook → Outline → Full Script and synthesize Male/Female voiceover.",
                "<b>Step 3 — Timeline & Video Studio:</b> Arrange clips on the 4-pane timeline, preview on the stage, and export.",
            ],
            action_label="Open Setup",
            action_tooltip="Launch the 4-step Onboarding Wizard to set up your first channel and preferences.",
            on_action=lambda: self._on_open_onboarding() if self._on_open_onboarding else None,
            secondary_label="Product Tour",
            secondary_tooltip="Take an interactive 9-step tour of all studio workspaces.",
            on_secondary=lambda: self._on_start_tour() if self._on_start_tour else None,
        )
        layout.addWidget(self.empty_state)

        self.projects_table = QTableWidget(0, 4)
        self.projects_table.setAlternatingRowColors(True)
        self.projects_table.verticalHeader().setVisible(False)
        self.projects_table.setMaximumHeight(180)
        self.projects_table.setHorizontalHeaderLabels(["Project Name", "Format", "Status", "Action"])
        self.projects_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.projects_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.projects_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.projects_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.projects_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.projects_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.projects_table.itemDoubleClicked.connect(lambda _: self._nav(5))
        layout.addWidget(self.projects_table)

        # Collapsible Bottom Drawer: Studio Diagnostics & Metrics (Starts Collapsed so Home stays super clean!)
        status_group = QGroupBox("Studio Diagnostics & System Environment")
        status_layout = QVBoxLayout(status_group)

        cards_row = QHBoxLayout()
        self.card_channels = MetricCard(
            "Active Channels",
            "0",
            "Brand profiles",
            tooltip="Number of active YouTube channel profiles in your local database.",
        )
        self.card_media = MetricCard(
            "Indexed Audio",
            "0",
            "Ready for mixing",
            tooltip="Total audio files scanned with BPM, Camelot key, and SHA-256 fingerprint.",
        )
        self.card_projects = MetricCard(
            "Projects",
            "0",
            "Timelines",
            tooltip="Total production projects across all channels.",
        )
        self.card_engine = MetricCard(
            "Render Engine",
            "Ready",
            "Checking…",
            tooltip="Current FFmpeg / fallback media rendering engine status and resource profile.",
        )
        cards_row.addWidget(self.card_channels)
        cards_row.addWidget(self.card_media)
        cards_row.addWidget(self.card_projects)
        cards_row.addWidget(self.card_engine)
        status_layout.addLayout(cards_row)

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

            self.projects_table.setRowCount(len(projects))
            self._project_ids = []
            for idx, p in enumerate(projects):
                self._project_ids.append(p.id)
                self.projects_table.setItem(idx, 0, QTableWidgetItem(p.name))
                self.projects_table.setItem(idx, 1, QTableWidgetItem(p.project_type.value))
                self.projects_table.setItem(idx, 2, QTableWidgetItem(p.status.value))
                self.projects_table.setItem(idx, 3, QTableWidgetItem("🎬 Open in Studio"))
            self.projects_table.setVisible(len(projects) > 0)
        except Exception as exc:
            lines.append(f"<b>Database:</b> <span style='color:#e74c3c'>{exc}</span>")

        self.status_label.setText("<br>".join(lines))


class MainWindow(QMainWindow):
    NAV_ITEMS = [
        ("🏠  Home", "dashboard", "Home Launchpad with New Project hero, More Tools, and saved projects."),
        ("🔍  Research", "research", "YouTube URL to Research Brief importer, keyword discovery, and topic clustering."),
        ("🎵  Music Library", "music_library", "Scan local audio folders, inspect BPM & Camelot keys, and find duplicates."),
        ("✍️  Script & Voice", "script_voice", "3-step Script Builder (Hook → Outline → Full Script), file upload, and Local TTS Voiceover Studio."),
        ("🚀  Auto-Pilot", "production", "1-Click Express Auto-Pilot, harmonic mixing, visualizers, and video/Shorts rendering."),
        ("🎬  Video Studio", "timeline_editor", "4-pane nonlinear video & audio editor: Media/Effects browser, Player stage, Details inspector & Timeline."),
        ("🎨  Design Studio", "artwork", "Explainable 5-Title Scorer, Reference Image Style Lock, and 16:9 / 9:16 thumbnail generator."),
        ("🔌  MCP Hub", "mcp_hub", "Connect AI agents via the built-in Studio MCP Server or manage external MCP servers."),
        ("⚙️  Settings", "settings", "Manage Credential Vault API keys, SQLite snapshots, and Compliance Review Gate."),
    ]

    def __init__(self) -> None:
        super().__init__()
        settings = get_settings()
        self.setWindowTitle(f"{settings.app_name} v{__version__}")
        try:
            self.setWindowIcon(BrandAssetsService.get_app_icon())
        except Exception:
            pass
        self._is_mobile_mode: Optional[bool] = None
        self.setMinimumSize(360, 500)
        self._build_ui()
        self._build_menu()
        self.apply_theme(ThemeManager.get_preference())
        self._apply_initial_screen_geometry()
        self._update_responsive_mode(force=True)
        self.statusBar().showMessage(
            "Tip: Click '☰' to toggle the sidebar, '🏠 Home' for the Launchpad, or click any section header (▼/▶) to collapse it."
        )

        # Automatically trigger onboarding wizard on first interactive launch
        QTimer.singleShot(150, self._maybe_show_first_run_onboarding)

    def _apply_initial_screen_geometry(self) -> None:
        """Size and center the window within the user's available screen geometry (respecting macOS Menu Bar & Dock)."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_w = min(1160, max(380, int(avail.width() * 0.90)))
            target_h = min(720, max(500, int(avail.height() * 0.86)))
            self.resize(target_w, target_h)
            x = avail.x() + max(0, (avail.width() - target_w) // 2)
            y = avail.y() + max(0, (avail.height() - target_h) // 2)
            self.move(x, y)
        else:
            self.resize(1100, 680)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setMinimumSize(340, 440)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top Header Bar with Sidebar Toggle (☰), Quick Home Button (🏠), Brand Emblem, Theme, Onboarding & Tour
        header = QFrame()
        header.setObjectName("TopHeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 7, 12, 7)
        header_layout.setSpacing(8)

        self.btn_menu_toggle = QPushButton("☰")
        self.btn_menu_toggle.setFixedWidth(34)
        self.btn_menu_toggle.setToolTip("Collapse or expand the left navigation sidebar for maximum workspace room.")
        self.btn_menu_toggle.clicked.connect(self._toggle_nav_visibility)
        header_layout.addWidget(self.btn_menu_toggle)

        self.btn_home = QPushButton("🏠 Home")
        self.btn_home.setToolTip("Return to the Home Launchpad.")
        self.btn_home.clicked.connect(self._go_home)
        header_layout.addWidget(self.btn_home)

        self.brand_icon_label = QLabel()
        self.brand_icon_label.setPixmap(BrandAssetsService.get_header_icon_pixmap(24))
        self.brand_icon_label.setFixedSize(24, 24)
        self.brand_icon_label.setToolTip("YouTube Automation Studio — Official App Emblem")
        header_layout.addWidget(self.brand_icon_label)

        self.brand_title = QLabel("YouTube Automation Studio")
        self.brand_title.setFont(QFont("", 13, QFont.Weight.Bold))
        self.brand_title.setStyleSheet("color: #f8fafc;")
        header_layout.addWidget(self.brand_title)

        self.version_badge = QLabel(f"v{__version__}")
        self.version_badge.setObjectName("VersionBadge")
        header_layout.addWidget(self.version_badge)
        header_layout.addStretch()

        self.btn_theme = QPushButton("☀️ Light")
        self.btn_theme.setToolTip("Switch between Dark Mode and Light Mode.")
        self.btn_theme.clicked.connect(self.toggle_theme)
        header_layout.addWidget(self.btn_theme)

        self.btn_onboarding = QPushButton("✦ Setup")
        self.btn_onboarding.setToolTip(
            "Open the step-by-step Onboarding Flow to configure your channel, hardware profile, and API key."
        )
        self.btn_onboarding.clicked.connect(self.open_onboarding_dialog)
        header_layout.addWidget(self.btn_onboarding)

        self.btn_tour = QPushButton("🧭 Tour")
        self.btn_tour.setObjectName("PrimaryButton")
        self.btn_tour.setToolTip(
            "Launch the interactive 9-step Guided Product Tour across all studio workspaces."
        )
        self.btn_tour.clicked.connect(self.start_product_tour)
        header_layout.addWidget(self.btn_tour)

        outer.addWidget(header)

        # Main workspace area (Collapsible Left Sidebar + Scrollable Content column)
        self.workspace_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.workspace_row.setContentsMargins(0, 0, 0, 0)
        self.workspace_row.setSpacing(0)

        # Clean, slim navigation sidebar (collapsible with ☰; auto-hides when launching tools from Home)
        self.nav = QListWidget()
        self.nav.setObjectName("SideNav")
        self.nav.setFixedWidth(164)
        self.nav.setSpacing(2)
        self.nav.setToolTip("Switch workspaces (click ☰ above to collapse sidebar).")
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
        right_container.setContentsMargins(8, 6, 8, 6)
        right_container.setSpacing(4)

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
                on_navigate=self._navigate_from_dashboard,
                on_open_onboarding=self.open_onboarding_dialog,
                on_start_tour=self.start_product_tour,
            ),
            "research": ResearchPage(),
            "music_library": MusicLibraryPage(),
            "script_voice": ScriptVoicePage(),
            "production": ProductionPage(),
            "timeline_editor": TimelineEditorPage(),
            "artwork": ArtworkPage(),
            "mcp_hub": MCPHubPage(),
            "settings": SettingsPage(),
        }
        for _, key, _ in self.NAV_ITEMS:
            scroll_wrapper = wrap_in_responsive_scroll(self.pages[key], parent=self.stack)
            self.stack.addWidget(scroll_wrapper)
        for key in ("dashboard", "research", "script_voice", "production", "timeline_editor", "artwork"):
            page = self.pages.get(key)
            if page is not None and hasattr(page, "refresh"):
                page.refresh()
        right_container.addWidget(self.stack, stretch=1)

        self.workspace_row.addLayout(right_container, stretch=1)
        outer.addLayout(self.workspace_row, stretch=1)

    def _go_home(self) -> None:
        self.nav.setVisible(True)
        self.nav.setCurrentRow(0)

    def _navigate_from_dashboard(self, index: int) -> None:
        """When launching a studio tool from the Home Launchpad, auto-collapse the sidebar for full-screen focus."""
        if 0 <= index < self.nav.count():
            self.nav.setCurrentRow(index)
            if index > 0 and not self.tour_banner.isVisible():
                self.nav.setVisible(False)

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
            self.nav.setFixedHeight(44)
            self.version_badge.setVisible(False)
            self.brand_title.setText("YT Studio")
        else:
            self.workspace_row.setDirection(QBoxLayout.Direction.LeftToRight)
            self.nav.setFlow(QListView.Flow.TopToBottom)
            self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.nav.setFixedWidth(164)
            self.nav.setMinimumHeight(0)
            self.nav.setMaximumHeight(16777215)
            self.version_badge.setVisible(True)
            self.brand_title.setText("YouTube Automation Studio")

        for page in self.pages.values():
            apply_responsive_mode_to_page(page, is_mobile)

    def apply_theme(self, mode: str) -> None:
        """Apply 'dark', 'light', or 'system' theme to the application window and persist preference."""
        saved = ThemeManager.set_preference(mode)
        effective = ThemeManager.resolve_effective_theme(saved)
        qss = ThemeManager.get_stylesheet(saved)
        ThemeManager.apply_palette(saved)
        self.setStyleSheet(qss)
        app = QApplication.instance()
        if app is not None and hasattr(app, "setStyleSheet"):
            app.setStyleSheet(qss)  # type: ignore[attr-defined]
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
        toggle_nav_action = QAction("Toggle &Sidebar (☰)", self)
        toggle_nav_action.triggered.connect(self._toggle_nav_visibility)
        view_menu.addAction(toggle_nav_action)

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
        self.nav.setVisible(True)
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
