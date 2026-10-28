"""Main application window – modern dark-studio shell with Onboarding, Product Tour, Empty States & Tooltips."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
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
            ("🎵\nMusic Library", "Scan local audio folders, BPM, Camelot keys & duplicates.", 2),
            ("✍️\nScript & Voice", "Draft Hook → Outline → Script & synthesize Male/Female TTS.", 3),
            ("✂️\nLong video to shorts", "Auto-clip peak 30s 9:16 vertical Shorts.", 4),
            ("🚀\n1-Click Auto-Video", "End-to-end autopilot from audio folder or YouTube URL.", 4),
            ("🏆\nTitle Scorer", "Rank 5 title candidates by transparent length, keyword & tone rules.", 6),
            ("🔌\nMCP Hub", "Connect AI agents via the built-in Studio MCP Server.", 7),
            ("⚙️\nSettings", "Credential Vault API keys, SQLite backups & Compliance Gate.", 8),
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
            "Tip: Use '🏠 Home', the top Workspace selector, or the '◫' layout menu to switch tools — no sidebar clutter!"
        )

        # Automatically trigger onboarding wizard on first interactive launch
        QTimer.singleShot(150, self._maybe_show_first_run_onboarding)

    def _apply_initial_screen_geometry(self) -> None:
        """Size and center the window within the user's available screen geometry (respecting macOS Menu Bar & Dock)."""
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            target_w = min(1220, max(380, int(avail.width() * 0.92)))
            target_h = min(740, max(500, int(avail.height() * 0.88)))
            self.resize(target_w, target_h)
            x = avail.x() + max(0, (avail.width() - target_w) // 2)
            y = avail.y() + max(0, (avail.height() - target_h) // 2)
            self.move(x, y)
        else:
            self.resize(1160, 700)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setMinimumSize(340, 440)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sidebar-free Top Studio Bar:
        # Left: [🏠 Home] [Workspace ▾] Auto saved | Center: Active Project / Workspace Title | Right: [◫ ▾] [⌨] [💎 Local Pro] [↗ Share] [↑ Export]
        header = QFrame()
        header.setObjectName("TopHeaderBar")
        header.setStyleSheet(
            "QFrame#TopHeaderBar { background-color: #0e1015; border-bottom: 1px solid #1e2433; }"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        header_layout.setSpacing(8)

        self.brand_icon_label = QLabel()
        self.brand_icon_label.setPixmap(BrandAssetsService.get_header_icon_pixmap(22))
        self.brand_icon_label.setFixedSize(22, 22)
        self.brand_icon_label.setToolTip("YouTube Automation Studio")
        header_layout.addWidget(self.brand_icon_label)

        self.btn_home = QPushButton("🏠 Home")
        self.btn_home.setToolTip("Return to the Home Launchpad.")
        self.btn_home.clicked.connect(self._go_home)
        header_layout.addWidget(self.btn_home)

        self.workspace_combo = QComboBox()
        self.workspace_combo.setMinimumWidth(155)
        self.workspace_combo.setToolTip("Switch directly to any Studio Workspace (sidebar-free navigation).")
        for label, _, _ in self.NAV_ITEMS:
            self.workspace_combo.addItem(label)
        self.workspace_combo.currentIndexChanged.connect(self._on_workspace_combo_changed)
        header_layout.addWidget(self.workspace_combo)

        self.lbl_autosave_top = QLabel("Auto saved")
        self.lbl_autosave_top.setStyleSheet("color: #64748b; font-size: 11px; border: none;")
        header_layout.addWidget(self.lbl_autosave_top)

        header_layout.addStretch(1)

        # Centered Project / Workspace Title (matches '1028 (1)' in the center of the top bar)
        self.brand_title = QLabel("YouTube Automation Studio")
        self.brand_title.setFont(QFont("", 12, QFont.Weight.Bold))
        self.brand_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_title.setStyleSheet("color: #f8fafc; border: none;")
        header_layout.addWidget(self.brand_title)

        header_layout.addStretch(1)

        # Layout & View Dropdown Button (◫ ▾)
        self.btn_menu_toggle = QPushButton("◫ ▾")
        self.btn_menu_toggle.setToolTip("Toggle workspace panes (Media, Details, Timeline), Theme, or Setup Wizard.")
        layout_menu = QMenu(self)
        act_left = layout_menu.addAction("◧ Toggle Left Media Browser")
        act_left.triggered.connect(lambda: self._toggle_timeline_pane("left"))
        act_right = layout_menu.addAction("◨ Toggle Right Details Pane")
        act_right.triggered.connect(lambda: self._toggle_timeline_pane("right"))
        act_bottom = layout_menu.addAction("⬓ Toggle Bottom Timeline Dock")
        act_bottom.triggered.connect(lambda: self._toggle_timeline_pane("bottom"))
        layout_menu.addSeparator()
        act_theme = layout_menu.addAction("☀️ / 🌙 Toggle Light / Dark Theme")
        act_theme.triggered.connect(self.toggle_theme)
        act_setup = layout_menu.addAction("✦ Onboarding Setup Wizard…")
        act_setup.triggered.connect(self.open_onboarding_dialog)
        self.btn_menu_toggle.setMenu(layout_menu)
        header_layout.addWidget(self.btn_menu_toggle)

        # Hidden theme/onboarding buttons retained as attributes for backward compatibility
        self.btn_theme = QPushButton("☀️ Light")
        self.btn_theme.setVisible(False)
        self.btn_onboarding = QPushButton("✦ Setup")
        self.btn_onboarding.setVisible(False)

        # Keyboard / Guided Tour Button (⌨)
        self.btn_tour = QPushButton("⌨")
        self.btn_tour.setFixedWidth(32)
        self.btn_tour.setToolTip(
            "Launch the interactive 9-step Guided Product Tour across all studio workspaces."
        )
        self.btn_tour.clicked.connect(self.start_product_tour)
        header_layout.addWidget(self.btn_tour)

        # Pro Pill Badge
        self.version_badge = QLabel("💎 Local Pro")
        self.version_badge.setObjectName("VersionBadge")
        self.version_badge.setStyleSheet(
            "background-color: #1e1b4b; color: #c4b5fd; padding: 4px 10px; "
            "border-radius: 6px; font-size: 11px; font-weight: bold; border: 1px solid #4338ca;"
        )
        header_layout.addWidget(self.version_badge)

        # Share Button (↗ Share)
        self.btn_share = QPushButton("↗ Share")
        self.btn_share.setToolTip("Open the output package folder in Finder / File Explorer.")
        self.btn_share.clicked.connect(self._on_share_clicked)
        header_layout.addWidget(self.btn_share)

        # Cyan Export Button (↑ Export)
        self.btn_export_main = QPushButton("↑ Export")
        self.btn_export_main.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_main.setStyleSheet(
            "QPushButton { background-color: #00d4e5; color: #042f2e; font-weight: bold; "
            "padding: 5px 14px; border-radius: 6px; border: none; } "
            "QPushButton:hover { background-color: #22d3ee; }"
        )
        self.btn_export_main.setToolTip(
            "Export active project timeline (.fcpxml / .edl / .csv) or render ready-to-upload video package."
        )
        self.btn_export_main.clicked.connect(self._on_export_main_clicked)
        header_layout.addWidget(self.btn_export_main)

        outer.addWidget(header)

        # Main workspace area (100% Full-Width Content — NO Left Sidebar!)
        self.workspace_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.workspace_row.setContentsMargins(0, 0, 0, 0)
        self.workspace_row.setSpacing(0)

        # Hidden QListWidget kept off-layout purely for programmatic state/signal compatibility
        self.nav = QListWidget(self)
        self.nav.setObjectName("SideNav")
        self.nav.setVisible(False)
        for label, _, tip in self.NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setToolTip(tip)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        # Full-width content container: Guided Product Tour Banner + Scroll-Wrapped Stacked Pages
        right_container = QVBoxLayout()
        right_container.setContentsMargins(6, 4, 6, 4)
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
        self.nav.setCurrentRow(0)

    def _navigate_from_dashboard(self, index: int) -> None:
        if 0 <= index < self.nav.count():
            self.nav.setCurrentRow(index)

    def _on_workspace_combo_changed(self, index: int) -> None:
        if 0 <= index < self.nav.count() and self.nav.currentRow() != index:
            self.nav.setCurrentRow(index)

    def _toggle_nav_visibility(self) -> None:
        """Sidebar is permanently removed; open the workspace switcher dropdown instead."""
        self.workspace_combo.showPopup()

    def _toggle_timeline_pane(self, which: str) -> None:
        te = self.pages.get("timeline_editor")
        if te is None:
            return
        if which == "left" and hasattr(te, "btn_toggle_left_pane"):
            te.btn_toggle_left_pane.toggle()  # type: ignore[attr-defined]
        elif which == "right" and hasattr(te, "btn_toggle_right_pane"):
            te.btn_toggle_right_pane.toggle()  # type: ignore[attr-defined]
        elif which == "bottom" and hasattr(te, "btn_toggle_bottom_dock"):
            te.btn_toggle_bottom_dock.toggle()  # type: ignore[attr-defined]

    def _on_share_clicked(self) -> None:
        out_dir = get_settings().resolved_output_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

    def _on_export_main_clicked(self) -> None:
        # If not currently on Video Studio or Auto-Pilot, trigger Video Studio export if a project exists, else jump to Video Studio
        te = self.pages.get("timeline_editor")
        if self.stack.currentIndex() == 5 and te is not None and hasattr(te, "_on_export_timeline_package"):
            te._on_export_timeline_package()  # type: ignore[attr-defined]
        else:
            self.nav.setCurrentRow(5)
            if te is not None and hasattr(te, "_on_export_timeline_package"):
                te._on_export_timeline_package()  # type: ignore[attr-defined]

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive_mode()

    def _update_responsive_mode(self, *, force: bool = False) -> None:
        is_mobile = self.width() < MOBILE_BREAKPOINT_PX
        if not force and self._is_mobile_mode == is_mobile:
            return
        self._is_mobile_mode = is_mobile
        self.nav.setVisible(False)
        self.version_badge.setVisible(not is_mobile)
        self.lbl_autosave_top.setVisible(not is_mobile)

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
        export_action = QAction("↑ &Export Project / Package…", self)
        export_action.triggered.connect(self._on_export_main_clicked)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        workspace_menu = menubar.addMenu("&Workspace")
        for idx, (label, _, _) in enumerate(self.NAV_ITEMS):
            act = QAction(label, self)
            act.triggered.connect(lambda _checked=False, i=idx: self.nav.setCurrentRow(i))
            workspace_menu.addAction(act)

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
        self.nav.setVisible(False)
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
            if hasattr(self, "workspace_combo") and self.workspace_combo.currentIndex() != index:
                self.workspace_combo.blockSignals(True)
                self.workspace_combo.setCurrentIndex(index)
                self.workspace_combo.blockSignals(False)
            label, key, _ = self.NAV_ITEMS[index]
            page = self.pages.get(key)
            if hasattr(page, "refresh"):
                page.refresh()  # type: ignore[attr-defined]
            # Update centered header title to active project name in Video Studio, or workspace name otherwise
            if key == "timeline_editor" and hasattr(page, "project_combo"):
                proj_txt = page.project_combo.currentText().strip()  # type: ignore[attr-defined]
                self.brand_title.setText(proj_txt if proj_txt else "Video Studio — 1028 (1)")
            elif key == "dashboard":
                self.brand_title.setText("YouTube Automation Studio")
            else:
                self.brand_title.setText(label.strip())

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
