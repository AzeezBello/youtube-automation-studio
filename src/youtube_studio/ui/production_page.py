"""Production UI page – harmonic/cue tools, visual FX, audio visualizers & Shorts clipper."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.config import get_settings
from youtube_studio.domain.models.channel import (
    NICHE_STYLE_PRESETS,
    apply_niche_preset_to_brand_config,
)
from youtube_studio.domain.models.media import MediaType
from youtube_studio.domain.models.project import ProjectType, TransitionConfig, TransitionType
from youtube_studio.domain.services.autopilot_service import (
    ExpressAutopilotResult,
    ExpressAutopilotService,
)
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.jobs.runner import ProductionJobRunner, sanitize_output_name
from youtube_studio.media.nle_exporter import NLEExporterService
from youtube_studio.media.renderer import VisualizerStyle
from youtube_studio.media.shorts_clipper import ShortsClipperService
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget
from youtube_studio.ui.timeline_editor import (
    MultiTrackTimelineWidget,
    TimelineCanvasEditorDialog,
    TimelineClipItem,
)


class ProductionPage(QWidget):
    """Interactive production workspace with harmonic smart mixing, reactive visualizers & video styling."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel_ids: list[str] = []
        self._project_ids: list[str] = []
        self._track_ids: list[str] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = QLabel("Production Studio — Harmonic Mixing & Video Renderer")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        subtitle = QLabel(
            "Arrange multi-track mixes, apply bass-swap EQ transitions, customize audio-reactive visualizers, "
            "and export 16:9 releases or 9:16 vertical Shorts."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # Top bar: Channel & Project selectors
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setToolTip("Select the active YouTube channel profile for this production project.")
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        selector_row.addWidget(self.channel_combo, stretch=1)

        new_channel_btn = QPushButton("+ Channel")
        new_channel_btn.setToolTip("Create a new YouTube channel profile.")
        new_channel_btn.clicked.connect(self._on_new_channel)
        selector_row.addWidget(new_channel_btn)

        selector_row.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Select the production project to edit and render.")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        selector_row.addWidget(self.project_combo, stretch=1)

        new_project_btn = QPushButton("+ Project")
        new_project_btn.setObjectName("PrimaryButton")
        new_project_btn.setToolTip("Create a new single-track, DJ mix, or album project under the selected channel.")
        new_project_btn.clicked.connect(self._on_new_project)
        selector_row.addWidget(new_project_btn)

        selector_row.addWidget(QLabel("Style Preset:"))
        self.niche_preset_combo = QComboBox()
        for preset in NICHE_STYLE_PRESETS.values():
            self.niche_preset_combo.addItem(f"🎨 {preset.label}", preset.key)
        self.niche_preset_combo.setToolTip(
            "Select a Niche / Style Preset to configure aspect ratio, palette, audio visualizer, metadata tone, and target length."
        )
        self.niche_preset_combo.currentIndexChanged.connect(self._on_niche_preset_changed)
        selector_row.addWidget(self.niche_preset_combo)

        selector_row.addWidget(QLabel("Target Length:"))
        self.target_length_spin = QSpinBox()
        self.target_length_spin.setRange(0, 240)
        self.target_length_spin.setSpecialValueText("Auto (Full)")
        self.target_length_spin.setSuffix(" min")
        self.target_length_spin.setValue(60)
        self.target_length_spin.setToolTip(
            "Target video duration in minutes (drives script word count estimate and timeline duration comparison)."
        )
        self.target_length_spin.valueChanged.connect(lambda _: self._reload_tracks())
        selector_row.addWidget(self.target_length_spin)

        root.addLayout(selector_row)

        # ⚡ 1-Click Express Auto-Pilot Bar (Eliminates manual multi-step setup!)
        autopilot_box = QGroupBox(
            "⚡ 1-Click Express Auto-Pilot — Folder / Library → Trim + Harmonic Mix + SEO + Thumbnail + 16:9 Video + 9:16 Short"
        )
        ap_layout = QHBoxLayout(autopilot_box)
        ap_layout.setContentsMargins(12, 8, 12, 8)
        ap_layout.setSpacing(8)

        ap_layout.addWidget(QLabel("Source:"))
        self.autopilot_source_combo = QComboBox()
        self.autopilot_source_combo.setToolTip(
            "Pick a Music Library folder or 'All Indexed Tracks' to automatically build a complete release."
        )
        ap_layout.addWidget(self.autopilot_source_combo, stretch=1)

        self.autopilot_browse_btn = QPushButton("📂 Folder…")
        self.autopilot_browse_btn.setToolTip(
            "Select any folder of audio tracks on your computer and run 1-Click Auto-Pilot immediately."
        )
        self.autopilot_browse_btn.clicked.connect(self._on_autopilot_browse_folder)
        ap_layout.addWidget(self.autopilot_browse_btn)

        self.autopilot_title_input = QLineEdit()
        self.autopilot_title_input.setPlaceholderText("Optional release title…")
        self.autopilot_title_input.setToolTip(
            "Leave blank to automatically name the project from the folder or track title."
        )
        ap_layout.addWidget(self.autopilot_title_input, stretch=1)

        self.autopilot_prepare_btn = QPushButton("⚡ Auto-Setup")
        self.autopilot_prepare_btn.setObjectName("AccentButton")
        self.autopilot_prepare_btn.setToolTip(
            "Automatically creates the project, adds all tracks, trims silence, harmonically sorts by BPM/Key, "
            "generates YouTube SEO chapters/tags, and creates the 16:9 thumbnail so you can review before rendering."
        )
        self.autopilot_prepare_btn.clicked.connect(lambda: self.run_express_autopilot(render_video=False))
        ap_layout.addWidget(self.autopilot_prepare_btn)

        self.autopilot_render_btn = QPushButton("🚀 1-Click Produce")
        self.autopilot_render_btn.setObjectName("PrimaryButton")
        self.autopilot_render_btn.setToolTip(
            "End-to-end automation in 1 click: scans/loads tracks, creates project, trims silence, "
            "harmonically sorts, generates SEO metadata & 16:9 thumbnail, renders full 16:9 MP4 video, "
            "and exports a 9:16 vertical Short into your Output Folder!"
        )
        self.autopilot_render_btn.clicked.connect(lambda: self.run_express_autopilot(render_video=True))
        ap_layout.addWidget(self.autopilot_render_btn)

        root.addWidget(autopilot_box)

        # Empty State Guide (displayed when no tracks are in the current timeline)
        self.empty_state = EmptyStateWidget(
            title="Ready to Build Your Release — Use 1-Click Auto-Pilot Above or Add Tracks",
            description=(
                "Click '🚀 1-Click Auto-Produce Full Video + Short' above to automate everything in one click, "
                "or click '+ Add Tracks / Folder' below to customize your timeline."
            ),
            tips=[
                "<b>⚡ 1-Click Express Auto-Pilot:</b> Automatically creates the project, adds tracks, trims silence, orders by Camelot Key/BPM, generates SEO chapters & 16:9 artwork, and renders your video + Short.",
                "<b>Multi-Track & Folder Import:</b> Add an entire folder or multiple tracks at once — no need to add tracks one by one.",
                "<b>Bass-Swap EQ & Visualizers:</b> Eliminates low-end frequency clash during crossfades and renders multi-band spectrum visuals.",
            ],
            action_label="🚀 1-Click Auto-Produce Full Release",
            action_tooltip="Automatically build, harmonic-mix, generate SEO/artwork, and render the full video + Short.",
            on_action=lambda: self.run_express_autopilot(render_video=True),
            secondary_label="+ Add Tracks / Folder to Timeline",
            secondary_tooltip="Pick multiple tracks or an entire folder from your Music Library and add them to the timeline.",
            on_secondary=self._on_add_track,
        )
        root.addWidget(self.empty_state)

        # Main split: Left = Timeline tracks & smart tools, Right = Track Editor + Visual FX + Produce
        body = QHBoxLayout()

        left_col = QVBoxLayout()
        track_btns_top = QHBoxLayout()
        add_track_btn = QPushButton("+ Add Tracks / Folder…")
        add_track_btn.setObjectName("AccentButton")
        add_track_btn.setToolTip(
            "Select multiple audio tracks or an entire Music Library folder to add to the timeline at once."
        )
        add_track_btn.clicked.connect(self._on_add_track)
        track_btns_top.addWidget(add_track_btn)

        add_all_btn = QPushButton("⚡ Add All Library Tracks")
        add_all_btn.setToolTip(
            "Add all tracks from the selected source folder into the current project, auto-trim silence, and harmonic-sort."
        )
        add_all_btn.clicked.connect(self._on_quick_add_all_tracks)
        track_btns_top.addWidget(add_all_btn)

        move_up_btn = QPushButton("↑ Up")
        move_up_btn.setToolTip("Move the selected track earlier in the timeline order.")
        move_up_btn.clicked.connect(lambda: self._on_move_track(-1))
        track_btns_top.addWidget(move_up_btn)

        move_down_btn = QPushButton("↓ Down")
        move_down_btn.setToolTip("Move the selected track later in the timeline order.")
        move_down_btn.clicked.connect(lambda: self._on_move_track(1))
        track_btns_top.addWidget(move_down_btn)

        remove_track_btn = QPushButton("Remove")
        remove_track_btn.setToolTip("Remove the selected track from this project timeline.")
        remove_track_btn.clicked.connect(self._on_remove_track)
        track_btns_top.addWidget(remove_track_btn)
        left_col.addLayout(track_btns_top)

        track_btns_bottom = QHBoxLayout()
        auto_cue_btn = QPushButton("Auto-Cue Trim")
        auto_cue_btn.setToolTip(
            "Automatically detect and trim leading/trailing silence on all tracks in this project."
        )
        auto_cue_btn.clicked.connect(self._on_auto_cue_trim)
        track_btns_bottom.addWidget(auto_cue_btn)

        harmonic_btn = QPushButton("Harmonic Sort")
        harmonic_btn.setToolTip(
            "Reorder tracks for smooth Camelot Wheel harmonic compatibility and gradual tempo progression."
        )
        harmonic_btn.clicked.connect(self._on_harmonic_sort)
        track_btns_bottom.addWidget(harmonic_btn)

        self.open_timeline_editor_btn = QPushButton("🎬 Video Studio…")
        self.open_timeline_editor_btn.setObjectName("PrimaryButton")
        self.open_timeline_editor_btn.setToolTip(
            "Open the visual nonlinear multi-track timeline & 16:9 / 9:16 video stage canvas editor "
            "to scrub audio, drag clip trim handles, preview overlays/visualizers, and fine-tune transitions."
        )
        self.open_timeline_editor_btn.clicked.connect(self._on_open_timeline_editor)
        track_btns_bottom.addWidget(self.open_timeline_editor_btn)

        left_col.addLayout(track_btns_bottom)

        # Inline Interactive Multi-Track Visual Timeline Strip
        self.mini_timeline = MultiTrackTimelineWidget(
            self,
            on_playhead_scrubbed=self._on_mini_timeline_playhead,
            on_clip_selected=self._on_mini_timeline_clip_selected,
            on_clip_trimmed=self._on_mini_timeline_clip_trimmed,
        )
        self.mini_timeline.setFixedHeight(195)
        self.mini_timeline.setToolTip(
            "Interactive Visual Timeline: click to scrub playhead, click any clip to select it, "
            "or drag the yellow left/right handles on a selected clip to trim its in/out points."
        )
        left_col.addWidget(self.mini_timeline)

        self.tracks_table = QTableWidget(0, 7)
        self.tracks_table.setAlternatingRowColors(True)
        self.tracks_table.verticalHeader().setVisible(False)
        self.tracks_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tracks_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tracks_table.setToolTip(
            "Project timeline tracks. Select any row to edit its trim, gain, fade, and transition settings on the right."
        )
        self.tracks_table.setHorizontalHeaderLabels(
            ["#", "Track", "BPM / Key", "Trim (ms)", "Gain (dB)", "Fade In/Out", "Transition"]
        )
        hdr = self.tracks_table.horizontalHeader()
        hdr.setMinimumSectionSize(28)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tracks_table.setColumnWidth(0, 32)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        for hidden_col in (3, 4, 5):
            self.tracks_table.setColumnHidden(hidden_col, True)
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tracks_table.itemSelectionChanged.connect(self._on_track_selected)
        left_col.addWidget(self.tracks_table, stretch=1)

        body.addLayout(left_col, stretch=3)

        # Right column: Track Editor + Visual FX + Chapter Preview + Produce / Shorts buttons
        right_col = QVBoxLayout()
        editor_group = QGroupBox("Selected Track & Harmonic Transition Settings")
        self.editor_group = editor_group
        form = QFormLayout(editor_group)

        self.trim_start_spin = QSpinBox()
        self.trim_start_spin.setRange(0, 36_000_000)
        self.trim_start_spin.setSingleStep(500)
        self.trim_start_spin.setToolTip("Start offset in milliseconds (trims intro before this point).")
        form.addRow("Trim Start (ms):", self.trim_start_spin)

        self.trim_end_spin = QSpinBox()
        self.trim_end_spin.setRange(0, 36_000_000)
        self.trim_end_spin.setSingleStep(500)
        self.trim_end_spin.setSpecialValueText("Full Length (0)")
        self.trim_end_spin.setToolTip("End offset in milliseconds (0 = play until the end of the track).")
        form.addRow("Trim End (ms):", self.trim_end_spin)

        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(-24.0, 24.0)
        self.gain_spin.setSingleStep(0.5)
        self.gain_spin.setToolTip("Per-track volume adjustment in decibels (dB) before master loudness normalization.")
        form.addRow("Gain (dB):", self.gain_spin)

        self.fade_in_spin = QSpinBox()
        self.fade_in_spin.setRange(0, 60_000)
        self.fade_in_spin.setSingleStep(500)
        self.fade_in_spin.setToolTip("Duration of audio fade-in at the start of the track (in milliseconds).")
        form.addRow("Fade In (ms):", self.fade_in_spin)

        self.fade_out_spin = QSpinBox()
        self.fade_out_spin.setRange(0, 60_000)
        self.fade_out_spin.setSingleStep(500)
        self.fade_out_spin.setToolTip("Duration of audio fade-out at the end of the track (in milliseconds).")
        form.addRow("Fade Out (ms):", self.fade_out_spin)

        self.transition_type_combo = QComboBox()
        self.transition_type_combo.addItems(
            [
                TransitionType.CROSSFADE.value,
                TransitionType.BASS_SWAP_EQ.value,
                TransitionType.NONE.value,
            ]
        )
        self.transition_type_combo.setToolTip(
            "Choose how this track transitions into the next: standard Crossfade, "
            "Bass-Swap EQ (attenuates outgoing sub-bass below 250 Hz), or None."
        )
        form.addRow("Transition Mode:", self.transition_type_combo)

        self.crossfade_spin = QSpinBox()
        self.crossfade_spin.setRange(0, 30_000)
        self.crossfade_spin.setSingleStep(500)
        self.crossfade_spin.setValue(3000)
        self.crossfade_spin.setToolTip("Overlap duration in milliseconds between this track and the next track.")
        form.addRow("Overlap (ms):", self.crossfade_spin)

        apply_track_btn = QPushButton("Save Track Parameters")
        apply_track_btn.setToolTip("Save trim, gain, fade, and transition settings for the selected timeline track.")
        apply_track_btn.clicked.connect(self._on_save_track_params)
        form.addRow(apply_track_btn)

        right_col.addWidget(editor_group)

        # Video Styling, Custom Visual Assets & Visualizer FX Group
        fx_group = QGroupBox("Video Background Asset (Image / Video Loop), Overlays & Visualizer FX")
        fx_layout = QFormLayout(fx_group)

        vis_asset_row = QHBoxLayout()
        self.visual_asset_combo = QComboBox()
        self.visual_asset_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.visual_asset_combo.setMinimumContentsLength(18)
        self.visual_asset_combo.setToolTip(
            "Choose 'Auto-Generated Studio Artwork' or select a custom uploaded Image (.png/.jpg/.webp) "
            "or looping Background Video (.mp4/.mov/.webm) for your release."
        )
        vis_asset_row.addWidget(self.visual_asset_combo, stretch=1)

        self.btn_add_image_asset = QPushButton("🖼 + Image…")
        self.btn_add_image_asset.setToolTip(
            "Upload a custom image (.png, .jpg, .jpeg, .webp) to use as the video background & thumbnail."
        )
        self.btn_add_image_asset.clicked.connect(self._on_upload_image_asset_dialog)
        vis_asset_row.addWidget(self.btn_add_image_asset)

        self.btn_add_video_asset = QPushButton("🎬 + Video…")
        self.btn_add_video_asset.setToolTip(
            "Upload a custom video clip or loop (.mp4, .mov, .webm, .mkv) to loop as the video background."
        )
        self.btn_add_video_asset.clicked.connect(self._on_upload_video_asset_dialog)
        vis_asset_row.addWidget(self.btn_add_video_asset)
        fx_layout.addRow("Visual Asset:", vis_asset_row)

        self.visualizer_combo = QComboBox()
        self.visualizer_combo.addItems([v.value for v in VisualizerStyle])
        self.visualizer_combo.setToolTip(
            "Select the audio-reactive visualizer rendered over the background artwork "
            "(bar_spectrum, mirrored_stereo, dub_oscilloscope, line_wave, or none)."
        )
        fx_layout.addRow("Audio Visualizer:", self.visualizer_combo)

        self.chk_now_playing = QCheckBox("Dynamic 'Now Playing' Track Title Overlay (Synced to Chapters)")
        self.chk_now_playing.setChecked(True)
        self.chk_now_playing.setToolTip(
            "Burns time-synced track titles into the video and exports a companion .srt subtitle file."
        )
        fx_layout.addRow(self.chk_now_playing)

        self.chk_progress = QCheckBox("Animated Bottom Playback Progress Bar")
        self.chk_progress.setChecked(True)
        self.chk_progress.setToolTip("Renders a smooth playback progress bar along the bottom edge of the video.")
        fx_layout.addRow(self.chk_progress)

        self.chk_zoom = QCheckBox("Slow Cinema Zoom / Pan Motion")
        self.chk_zoom.setToolTip("Applies subtle continuous camera zoom/pan so the background never looks static.")
        fx_layout.addRow(self.chk_zoom)

        self.chk_vintage = QCheckBox("Analog Film Grain && Warm Vignette")
        self.chk_vintage.setToolTip("Adds organic film grain texture and subtle edge vignetting.")
        fx_layout.addRow(self.chk_vintage)

        right_col.addWidget(fx_group)

        # Chapters & Action Buttons
        chapters_group = QGroupBox("Generated Chapters, Output Location & Export Actions")
        chapters_layout = QVBoxLayout(chapters_group)
        self.chapters_preview = QPlainTextEdit()
        self.chapters_preview.setReadOnly(True)
        self.chapters_preview.setToolTip(
            "Auto-computed YouTube chapter timestamps (starting at 00:00) accounting for trims and crossfade overlaps."
        )
        chapters_layout.addWidget(self.chapters_preview)

        name_row = QHBoxLayout()
        lbl_name = QLabel("Output Name:")
        lbl_name.setStyleSheet("font-weight: 600;")
        name_row.addWidget(lbl_name)

        self.output_name_input = QLineEdit()
        self.output_name_input.setPlaceholderText(
            "Custom output folder & video filename (e.g. Echoes_of_Livity_Mix_Vol_1)…"
        )
        self.output_name_input.setToolTip(
            "Name for the rendered output subfolder and exported files (<Output Name>.mp4, <Output Name>_audio.wav, "
            "<Output Name>_thumbnail.png, <Output Name>_short_9x16.mp4). Defaults to the project name if left blank."
        )
        name_row.addWidget(self.output_name_input, stretch=1)
        chapters_layout.addLayout(name_row)

        out_row = QHBoxLayout()
        lbl_out = QLabel("Output Folder:")
        lbl_out.setStyleSheet("font-weight: 600;")
        out_row.addWidget(lbl_out)

        self.output_dir_input = QLineEdit()
        self.output_dir_input.setText(str(get_settings().resolved_output_dir()))
        self.output_dir_input.setPlaceholderText("Choose where rendered videos, mixes, Shorts & manifests are saved…")
        self.output_dir_input.setToolTip(
            "Destination directory where rendered 16:9 videos, mixed WAV audio, 9:16 Shorts, and package manifests are saved."
        )
        self.output_dir_input.editingFinished.connect(self._on_output_dir_edited)
        out_row.addWidget(self.output_dir_input, stretch=1)

        self.btn_browse_output = QPushButton("📁 Set Output Folder…")
        self.btn_browse_output.setToolTip("Browse and select a custom folder for your rendered videos and export packages.")
        self.btn_browse_output.clicked.connect(self._on_browse_output_dir)
        out_row.addWidget(self.btn_browse_output)

        self.btn_open_output = QPushButton("↗ Open")
        self.btn_open_output.setToolTip("Open the configured output folder in Finder / File Explorer.")
        self.btn_open_output.clicked.connect(self._on_open_output_dir)
        out_row.addWidget(self.btn_open_output)
        chapters_layout.addLayout(out_row)

        self.produce_btn = QPushButton("Run Full Production Pipeline (Mix → Thumbnail → Video → Package)")
        self.produce_btn.setObjectName("PrimaryButton")
        self.produce_btn.setToolTip(
            "Execute all 6 checkpointed production stages: input validation, audio mixing, "
            "thumbnail generation, video rendering, media verification, and export packaging."
        )
        self.produce_btn.clicked.connect(self._on_run_production)
        chapters_layout.addWidget(self.produce_btn)

        self.shorts_btn = QPushButton("Export 9:16 Short / Reel Highlight (Peak 30s Auto-Clipper)")
        self.shorts_btn.setObjectName("AccentButton")
        self.shorts_btn.setToolTip(
            "Automatically locate the highest-energy 30-second window and render a 1080x1920 vertical Short."
        )
        self.shorts_btn.clicked.connect(self._on_export_short_highlight)
        chapters_layout.addWidget(self.shorts_btn)

        self.export_nle_btn = QPushButton("🎞 Export Project XML & Clip List for External Video Editor")
        self.export_nle_btn.setToolTip(
            "Export Final Cut Pro XML (.fcpxml), CMX 3600 EDL (.edl), and a CSV/JSON clip list "
            "into the output folder and open it for external video editor hand-off."
        )
        self.export_nle_btn.clicked.connect(self._on_export_nle_bundle)
        chapters_layout.addWidget(self.export_nle_btn)

        # Live Generation Stage Progress (Script -> Voice -> Visuals -> Mix/Video -> Package)
        prog_row = QHBoxLayout()
        self.stage_status_label = QLabel("Stage Ready: Script → Voice → Visuals → Mix/Video → Package")
        self.stage_status_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        prog_row.addWidget(self.stage_status_label, stretch=1)

        self.stage_progress_bar = QProgressBar()
        self.stage_progress_bar.setRange(0, 100)
        self.stage_progress_bar.setValue(0)
        self.stage_progress_bar.setFixedWidth(180)
        self.stage_progress_bar.setFixedHeight(14)
        prog_row.addWidget(self.stage_progress_bar)
        chapters_layout.addLayout(prog_row)

        right_col.addWidget(chapters_group, stretch=1)
        body.addLayout(right_col, stretch=2)

        root.addLayout(body, stretch=1)

    @staticmethod
    def _visual_assets_dir() -> Path:
        d = get_settings().resolved_data_dir() / "visual_assets"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_visual_assets(self) -> list[Path]:
        """Return all uploaded custom images and video loops stored in visual_assets/."""
        allowed = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
        d = self._visual_assets_dir()
        return [
            p
            for p in sorted(d.iterdir())
            if p.is_file() and p.suffix.lower() in allowed and not p.name.startswith(".")
        ]

    def upload_visual_asset(self, file_path: str | Path) -> Path:
        """Copy a custom image or video asset into the Studio Visual Assets library and select it."""
        import shutil

        src = Path(file_path).expanduser().resolve()
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"Asset file not found: {src}")
        dest_dir = self._visual_assets_dir()
        dest = dest_dir / src.name
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
        proj_id = self.current_project_id()
        if proj_id:
            from youtube_studio.domain.models.project import AssetType

            with session_scope() as session:
                ProjectService(session).register_asset(
                    proj_id,
                    AssetType.BACKGROUND_IMAGE,
                    str(dest),
                    source_type="custom_upload",
                    approved=True,
                )
        self._rebuild_visual_assets_combo()
        idx = self.visual_asset_combo.findData(str(dest))
        if idx >= 0:
            self.visual_asset_combo.setCurrentIndex(idx)
        return dest

    def selected_visual_asset_path(self) -> Optional[Path]:
        if not hasattr(self, "visual_asset_combo"):
            return None
        raw = str(self.visual_asset_combo.currentData() or "").strip()
        if raw and Path(raw).exists():
            return Path(raw)
        return None

    def _rebuild_visual_assets_combo(self) -> None:
        if not hasattr(self, "visual_asset_combo"):
            return
        prev = self.visual_asset_combo.currentData()
        self.visual_asset_combo.blockSignals(True)
        self.visual_asset_combo.clear()
        self.visual_asset_combo.addItem("✨ Auto-Generated 16:9 Studio Artwork (Default)", "")
        video_exts = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
        for p in self.list_visual_assets():
            icon = "🎬 Video Loop:" if p.suffix.lower() in video_exts else "🖼 Image:"
            self.visual_asset_combo.addItem(f"{icon} {p.name}", str(p))
        if prev is not None:
            idx = self.visual_asset_combo.findData(prev)
            if idx >= 0:
                self.visual_asset_combo.setCurrentIndex(idx)
        self.visual_asset_combo.blockSignals(False)

    def _on_upload_image_asset_dialog(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom Image for Video Background & Thumbnail",
            str(Path.home()),
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
        )
        if not chosen:
            return
        try:
            saved = self.upload_visual_asset(chosen)
            QMessageBox.information(
                self,
                "Image Asset Added",
                f"Added image asset:\n{saved.name}\n\n"
                "It is now selected as the Visual Asset for your video & 1-Click Auto-Pilot.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Image Upload Failed", str(exc))

    def _on_upload_video_asset_dialog(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom Video Clip / Loop for Video Background",
            str(Path.home()),
            "Video Files (*.mp4 *.mov *.webm *.mkv *.m4v *.avi)",
        )
        if not chosen:
            return
        try:
            saved = self.upload_visual_asset(chosen)
            QMessageBox.information(
                self,
                "Video Asset Added",
                f"Added background video loop:\n{saved.name}\n\n"
                "It will seamlessly loop as the visual background for your rendered video!",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Video Upload Failed", str(exc))

    def _rebuild_autopilot_sources(self) -> None:
        if not hasattr(self, "autopilot_source_combo"):
            return
        prev_data = self.autopilot_source_combo.currentData()
        self.autopilot_source_combo.blockSignals(True)
        self.autopilot_source_combo.clear()

        try:
            with session_scope() as session:
                all_audio = MediaLibraryService(session).list_media(media_type=MediaType.AUDIO)
        except Exception:
            all_audio = []

        self.autopilot_source_combo.addItem(
            f"All Indexed Library Tracks ({len(all_audio)} tracks)",
            "",
        )

        seen_folders: set[str] = set()
        lib_root = get_settings().resolved_data_dir() / "music_library"
        if lib_root.exists():
            for p in sorted(lib_root.iterdir()):
                if p.is_dir() and not p.name.startswith("."):
                    seen_folders.add(p.name)
                    count = sum(
                        1
                        for it in all_audio
                        if str(it.metadata.get("folder") or Path(it.path).parent.name) == p.name
                    )
                    self.autopilot_source_combo.addItem(
                        f"📁 {p.name} ({count} tracks)",
                        f"folder:{p.name}",
                    )

        for it in all_audio:
            lbl = str(it.metadata.get("folder") or Path(it.path).parent.name).strip()
            if lbl and lbl not in seen_folders:
                seen_folders.add(lbl)
                count = sum(
                    1
                    for m in all_audio
                    if str(m.metadata.get("folder") or Path(m.path).parent.name).strip() == lbl
                )
                self.autopilot_source_combo.addItem(
                    f"📂 {lbl} ({count} tracks)",
                    f"folder:{lbl}",
                )

        if prev_data is not None:
            idx = self.autopilot_source_combo.findData(prev_data)
            if idx >= 0:
                self.autopilot_source_combo.setCurrentIndex(idx)
        self.autopilot_source_combo.blockSignals(False)

    def refresh(self) -> None:
        if hasattr(self, "output_dir_input"):
            self.output_dir_input.setText(str(get_settings().resolved_output_dir()))
        self._rebuild_autopilot_sources()
        self._rebuild_visual_assets_combo()
        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
        except Exception:
            return

        prev_channel = self.current_channel_id()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self._channel_ids = []
        for ch in channels:
            self.channel_combo.addItem(ch.name)
            self._channel_ids.append(ch.id)
        if prev_channel in self._channel_ids:
            self.channel_combo.setCurrentIndex(self._channel_ids.index(prev_channel))
        self.channel_combo.blockSignals(False)
        self._reload_projects()

    def _on_autopilot_browse_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Music Folder for 1-Click Auto-Pilot",
            str(Path.home()),
        )
        if not chosen:
            return
        self.run_express_autopilot(source_folder=chosen, render_video=True)

    def run_express_autopilot(
        self,
        *,
        source_folder: Optional[str | Path] = None,
        library_folder_name: Optional[str] = None,
        media_file_ids: Optional[list[str]] = None,
        render_video: bool = True,
    ) -> Optional[ExpressAutopilotResult]:
        """Run 1-Click Express Auto-Pilot and select the resulting channel & project in the UI."""
        if not source_folder and not library_folder_name and not media_file_ids:
            raw_data = str(self.autopilot_source_combo.currentData() or "")
            if raw_data.startswith("folder:"):
                library_folder_name = raw_data[len("folder:") :]

        title_override = (
            self.autopilot_title_input.text().strip()
            if hasattr(self, "autopilot_title_input")
            else ""
        )
        custom_out_name = (
            self.output_name_input.text().strip()
            if hasattr(self, "output_name_input")
            else ""
        )
        base_out = self._resolve_and_save_output_base()
        vis_style = self.visualizer_combo.currentText()
        custom_vis = self.selected_visual_asset_path()
        preset_key = (
            str(self.niche_preset_combo.currentData() or "")
            if hasattr(self, "niche_preset_combo")
            else None
        )
        target_mins = (
            int(self.target_length_spin.value())
            if hasattr(self, "target_length_spin")
            else 60
        )

        def _update_ui_stage(label: str, pct: int) -> None:
            if hasattr(self, "stage_status_label"):
                self.stage_status_label.setText(label)
            if hasattr(self, "stage_progress_bar"):
                self.stage_progress_bar.setValue(pct)
            QApplication.processEvents()

        try:
            with session_scope() as session:
                ap = ExpressAutopilotService(session)
                res = ap.run_autopilot(
                    channel_id=self.current_channel_id(),
                    project_name=title_override or custom_out_name or None,
                    media_file_ids=media_file_ids,
                    source_folder=source_folder,
                    library_folder_name=library_folder_name,
                    visualizer_style=vis_style,
                    custom_visual_path=custom_vis,
                    output_name=custom_out_name or title_override or None,
                    niche_preset=preset_key or None,
                    target_duration_minutes=target_mins,
                    render_video=render_video,
                    export_short=render_video,
                    output_base_dir=base_out,
                    on_stage_progress=_update_ui_stage,
                )
        except Exception as exc:
            QMessageBox.critical(self, "1-Click Auto-Pilot", str(exc))
            return None

        self.refresh()
        if res.channel_id in self._channel_ids:
            self.channel_combo.setCurrentIndex(self._channel_ids.index(res.channel_id))
            self._reload_projects()
        if res.project_id in self._project_ids:
            self.project_combo.setCurrentIndex(self._project_ids.index(res.project_id))
            self._reload_tracks()

        self._notify_output_dir_changed()

        steps_summary = "\n".join(f"  ✓ {s}" for s in res.executed_steps)
        if render_video:
            QMessageBox.information(
                self,
                "🚀 1-Click Auto-Pilot Complete!",
                f"Finished building and rendering '{res.project_name}' ({res.track_count} tracks)!\n\n"
                f"Automated Steps Completed:\n{steps_summary}\n\n"
                f"YouTube SEO Title:\n  {res.seo_title}\n\n"
                f"Output Folder:\n  {res.output_dir}\n"
                f"9:16 Vertical Short:\n  {res.short_video_path or 'Included in output folder'}",
            )
        else:
            QMessageBox.information(
                self,
                "⚡ 1-Click Auto-Setup Complete!",
                f"Prepared '{res.project_name}' ({res.track_count} tracks) in 1 click!\n\n"
                f"Automated Steps Completed:\n{steps_summary}\n\n"
                f"You can now review the timeline on the left or click 'Run Full Production Pipeline' to render.",
            )
        return res

    def _ensure_channel_and_project(self, default_name: str = "Studio Mix Session") -> tuple[str, str]:
        """Ensure an active channel and project exist, creating them automatically so the user is never blocked."""
        channel_id = self.current_channel_id()
        project_id = self.current_project_id()
        created_any = False
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            if not channel_id:
                channel_id, _, _ = ap.ensure_active_channel()
                created_any = True
            if not project_id:
                proj = ProjectService(session).create_project(
                    channel_id,
                    default_name,
                    project_type=ProjectType.MIX,
                )
                project_id = proj.id
                created_any = True
        if created_any:
            self.refresh()
            if channel_id in self._channel_ids:
                self.channel_combo.setCurrentIndex(self._channel_ids.index(channel_id))
                self._reload_projects()
            if project_id in self._project_ids:
                self.project_combo.setCurrentIndex(self._project_ids.index(project_id))
        return channel_id, project_id

    def _on_quick_add_all_tracks(self) -> None:
        raw_data = str(self.autopilot_source_combo.currentData() or "")
        folder_filter = raw_data[len("folder:") :] if raw_data.startswith("folder:") else None
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            tracks = ap.resolve_tracks(library_folder_name=folder_filter)
        if not tracks:
            QMessageBox.information(
                self,
                "No Audio Tracks Found",
                "Upload or scan audio tracks in the Music Library first.",
            )
            return
        default_proj_name = f"{folder_filter} — Mix Session" if folder_filter else "Studio Mix Session"
        _, project_id = self._ensure_channel_and_project(default_proj_name)
        with session_scope() as session:
            proj_svc = ProjectService(session)
            existing_ids = {pt.media_file_id for pt in proj_svc.list_tracks(project_id)}
            t_cfg = TransitionConfig(
                transition_type=TransitionType.BASS_SWAP_EQ if len(tracks) > 1 else TransitionType.NONE,
                overlap_ms=3000 if len(tracks) > 1 else 0,
            )
            for mf in tracks:
                if mf.id not in existing_ids:
                    proj_svc.add_track(project_id, mf.id, transition_config=t_cfg)
            proj_svc.auto_cue_trim_tracks(project_id)
            if len(proj_svc.list_tracks(project_id)) > 1:
                proj_svc.auto_harmonic_sort(project_id)
        self._reload_tracks()

    def current_channel_id(self) -> Optional[str]:
        idx = self.channel_combo.currentIndex()
        if 0 <= idx < len(self._channel_ids):
            return self._channel_ids[idx]
        return None

    def current_project_id(self) -> Optional[str]:
        idx = self.project_combo.currentIndex()
        if 0 <= idx < len(self._project_ids):
            return self._project_ids[idx]
        return None

    def _on_channel_changed(self, _index: int) -> None:
        self._reload_projects()

    def _on_niche_preset_changed(self, _index: int) -> None:
        if not hasattr(self, "niche_preset_combo"):
            return
        preset_key = str(self.niche_preset_combo.currentData() or "roots_reggae_mix")
        preset = NICHE_STYLE_PRESETS.get(preset_key)
        if preset is None:
            return
        if hasattr(self, "visualizer_combo"):
            idx = self.visualizer_combo.findText(preset.visualizer_style)
            if idx >= 0:
                self.visualizer_combo.setCurrentIndex(idx)
        if hasattr(self, "target_length_spin"):
            self.target_length_spin.blockSignals(True)
            self.target_length_spin.setValue(preset.target_duration_minutes)
            self.target_length_spin.blockSignals(False)
        ch_id = self.current_channel_id()
        if ch_id:
            try:
                with session_scope() as session:
                    ch_svc = ChannelService(session)
                    ch = ch_svc.get(ch_id)
                    if ch:
                        updated_cfg = apply_niche_preset_to_brand_config(
                            preset_key, existing=ch.brand_config
                        )
                        ch_svc.update_brand_config(ch_id, updated_cfg)
            except Exception:
                pass
        self._reload_tracks()

    def _reload_projects(self) -> None:
        channel_id = self.current_channel_id()
        prev_project = self.current_project_id()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self._project_ids = []
        if channel_id:
            with session_scope() as session:
                projects = ProjectService(session).list_projects(channel_id=channel_id)
            for p in projects:
                self.project_combo.addItem(f"{p.name} [{p.status.value}]")
                self._project_ids.append(p.id)
            if prev_project in self._project_ids:
                self.project_combo.setCurrentIndex(self._project_ids.index(prev_project))
        self.project_combo.blockSignals(False)
        self._reload_tracks()

    def _on_project_changed(self, _index: int) -> None:
        project_id = self.current_project_id()
        if project_id and hasattr(self, "output_name_input"):
            with session_scope() as session:
                proj = ProjectService(session).get_project(project_id)
            if proj is not None:
                self.output_name_input.setText(proj.name)
        self._reload_tracks()

    def _reload_tracks(self) -> None:
        project_id = self.current_project_id()
        self.tracks_table.setRowCount(0)
        self._track_ids = []
        self.chapters_preview.setPlainText("")
        if hasattr(self, "mini_timeline"):
            self.mini_timeline.set_timeline_data([])
        if not project_id:
            if hasattr(self, "empty_state"):
                self.empty_state.setVisible(True)
            return

        clip_items: list[TimelineClipItem] = []
        with session_scope() as session:
            proj_svc = ProjectService(session)
            media_svc = MediaLibraryService(session)
            proj = proj_svc.get_project(project_id)
            if (
                proj is not None
                and hasattr(self, "output_name_input")
                and not self.output_name_input.text().strip()
            ):
                self.output_name_input.setText(proj.name)
            tracks = proj_svc.list_tracks(project_id)
            chapters = proj_svc.compute_chapters(project_id)
            total_ms = proj_svc.compute_total_duration_ms(project_id)

            if hasattr(self, "empty_state"):
                self.empty_state.setVisible(len(tracks) == 0)

            self.tracks_table.setRowCount(len(tracks))
            for idx, pt in enumerate(tracks):
                self._track_ids.append(pt.id)
                media = media_svc.get(pt.media_file_id)
                title = (
                    str(media.metadata.get("title") or Path(media.path).name)
                    if media
                    else pt.media_file_id
                )
                artist = str(media.metadata.get("artist") or "") if media else ""
                dur_ms = int(media.duration_ms or 60_000) if media else 60_000
                bpm = media.metadata.get("bpm") if media else None
                camelot = media.metadata.get("camelot_code") if media else None
                bpm_key_str = f"{bpm} · {camelot}" if bpm and camelot else "—"
                trim_str = f"{pt.trim_start_ms} – {pt.trim_end_ms or 'end'}"
                fade_str = f"{pt.fade_in_ms} / {pt.fade_out_ms}"
                tc = pt.transition_config
                trans_str = (
                    f"{tc.transition_type.value} ({tc.overlap_ms}ms)"
                    if tc.transition_type != TransitionType.NONE
                    else "none"
                )
                self.tracks_table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
                self.tracks_table.setItem(idx, 1, QTableWidgetItem(title))
                self.tracks_table.setItem(idx, 2, QTableWidgetItem(bpm_key_str))
                self.tracks_table.setItem(idx, 3, QTableWidgetItem(trim_str))
                self.tracks_table.setItem(idx, 4, QTableWidgetItem(f"{pt.gain_db:+.1f}"))
                self.tracks_table.setItem(idx, 5, QTableWidgetItem(fade_str))
                self.tracks_table.setItem(idx, 6, QTableWidgetItem(trans_str))

                seed_str = f"{title}:{pt.media_file_id}"
                peaks: list[float] = []
                for b in range(40):
                    h = sum((ord(ch) * (b + 3 + j)) for j, ch in enumerate(seed_str))
                    peaks.append(0.22 + 0.72 * ((h % 100) / 100.0))
                clip_items.append(
                    TimelineClipItem(
                        track_id=pt.id,
                        media_file_id=pt.media_file_id,
                        title=title,
                        artist=artist,
                        file_path=str(media.path) if media else "",
                        source_duration_ms=max(1000, dur_ms),
                        trim_start_ms=int(pt.trim_start_ms or 0),
                        trim_end_ms=int(pt.trim_end_ms) if pt.trim_end_ms else None,
                        gain_db=float(pt.gain_db or 0.0),
                        fade_in_ms=int(pt.fade_in_ms or 0),
                        fade_out_ms=int(pt.fade_out_ms or 0),
                        overlap_ms=int(tc.overlap_ms or 0),
                        transition_type=tc.transition_type.value,
                        bpm=float(bpm) if bpm is not None else None,
                        camelot_code=str(camelot) if camelot else None,
                        peaks=peaks,
                    )
                )

        if hasattr(self, "mini_timeline"):
            vis_path = self.selected_visual_asset_path()
            vis_lbl = vis_path.name if vis_path else "Studio Artwork / Video Loop"
            self.mini_timeline.set_timeline_data(clip_items, visual_label=vis_lbl)

        target_mins = (
            int(self.target_length_spin.value())
            if hasattr(self, "target_length_spin")
            else 0
        )
        cur_mins = total_ms / 60_000.0
        target_str = (
            f" · Target Length: {target_mins} min (Est. Script: ~{target_mins * 140} words)"
            if target_mins > 0
            else " · Target Length: Auto (Full Mix)"
        )
        lines = [
            f"Estimated Total Duration: {total_ms / 1000.0:.1f}s ({cur_mins:.1f} min){target_str}",
            "",
            "Chapters:",
        ]
        for ch in chapters:
            lines.append(f"{ch.format_timestamp()} {ch.title}")
        self.chapters_preview.setPlainText("\n".join(lines))

    def _on_mini_timeline_playhead(self, _playhead_ms: int) -> None:
        pass

    def _on_mini_timeline_clip_selected(self, idx: int) -> None:
        if 0 <= idx < self.tracks_table.rowCount():
            self.tracks_table.selectRow(idx)

    def _on_mini_timeline_clip_trimmed(
        self, idx: int, trim_start_ms: int, trim_end_ms: Optional[int]
    ) -> None:
        if 0 <= idx < len(self._track_ids):
            self.tracks_table.selectRow(idx)
            self.trim_start_spin.setValue(trim_start_ms)
            self.trim_end_spin.setValue(int(trim_end_ms or 0))
            self._on_save_track_params()

    def _on_open_timeline_editor(self) -> None:
        _, project_id = self._ensure_channel_and_project("Studio Mix Session")
        if not project_id:
            return
        dlg = TimelineCanvasEditorDialog(
            self,
            project_id=project_id,
            visual_asset_path=self.selected_visual_asset_path(),
            visualizer_style=self.visualizer_combo.currentText(),
            on_saved=self._reload_tracks,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._reload_tracks()

    def _on_new_channel(self) -> None:
        name, ok = QInputDialog.getText(self, "New Channel", "Channel name:")
        if not ok or not name.strip():
            return
        with session_scope() as session:
            ChannelService(session).create(name.strip())
        self.refresh()

    def _on_new_project(self) -> None:
        channel_id = self.current_channel_id()
        if not channel_id:
            with session_scope() as session:
                channel_id, _, _ = ExpressAutopilotService(session).ensure_active_channel()
            self.refresh()
            if channel_id in self._channel_ids:
                self.channel_combo.setCurrentIndex(self._channel_ids.index(channel_id))

        dlg = QDialog(self)
        dlg.setWindowTitle("Create Production Project")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)

        name_edit = QLineEdit("New Mix Session")
        name_edit.selectAll()
        type_combo = QComboBox()
        for t in ProjectType:
            type_combo.addItem(t.value.replace("_", " ").title(), t.value)
        type_combo.setCurrentIndex(1 if len(ProjectType) > 1 else 0)

        form.addRow("Project Name:", name_edit)
        form.addRow("Project Format:", type_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        proj_name = name_edit.text().strip() or "New Mix Session"
        chosen_type = str(type_combo.currentData() or ProjectType.MIX.value)
        with session_scope() as session:
            created = ProjectService(session).create_project(
                channel_id,
                proj_name,
                project_type=ProjectType(chosen_type),
            )
        self._reload_projects()
        if created.id in self._project_ids:
            self.project_combo.setCurrentIndex(self._project_ids.index(created.id))

    def _on_add_track(self) -> None:
        _, project_id = self._ensure_channel_and_project("Studio Mix Session")
        with session_scope() as session:
            media_items = MediaLibraryService(session).list_media(media_type=MediaType.AUDIO)
        if not media_items:
            QMessageBox.information(
                self,
                "Add Track",
                "No audio tracks found in the Music Library. Upload audio files or scan a folder in Music Library first.",
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Add Audio Tracks / Folder to Timeline")
        dlg.setMinimumSize(640, 440)
        vlayout = QVBoxLayout(dlg)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Filter by Folder:"))
        folder_combo = QComboBox()
        folder_combo.addItem("All Folders & Collections", "")
        seen_folders: set[str] = set()
        for m in media_items:
            f_lbl = str(m.metadata.get("folder") or Path(m.path).parent.name).strip()
            if f_lbl and f_lbl not in seen_folders:
                seen_folders.add(f_lbl)
                folder_combo.addItem(f"📁 {f_lbl}", f_lbl)
        top_bar.addWidget(folder_combo, stretch=1)

        btn_select_all = QPushButton("Select All Shown")
        btn_clear_all = QPushButton("Clear")
        top_bar.addWidget(btn_select_all)
        top_bar.addWidget(btn_clear_all)
        vlayout.addLayout(top_bar)

        track_list = QListWidget()
        track_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        vlayout.addWidget(track_list, stretch=1)

        def _populate_list() -> None:
            active_folder = str(folder_combo.currentData() or "")
            track_list.clear()
            for m in media_items:
                f_lbl = str(m.metadata.get("folder") or Path(m.path).parent.name).strip()
                if active_folder and f_lbl != active_folder:
                    continue
                title = str(m.metadata.get("title") or Path(m.path).stem)
                bpm = m.metadata.get("bpm")
                camelot = m.metadata.get("camelot_code")
                harmonic = f" · {bpm} BPM · {camelot}" if bpm and camelot else ""
                item = QListWidgetItem(f"{title}  [{f_lbl}{harmonic}]")
                item.setData(Qt.ItemDataRole.UserRole, m.id)
                item.setCheckState(Qt.CheckState.Checked)
                track_list.addItem(item)

        folder_combo.currentIndexChanged.connect(lambda _: _populate_list())
        btn_select_all.clicked.connect(
            lambda: [
                track_list.item(i).setCheckState(Qt.CheckState.Checked)
                for i in range(track_list.count())
            ]
        )
        btn_clear_all.clicked.connect(
            lambda: [
                track_list.item(i).setCheckState(Qt.CheckState.Unchecked)
                for i in range(track_list.count())
            ]
        )
        _populate_list()

        chk_auto_smart = QCheckBox(
            "Automatically apply Silence Trim & Smart Harmonic Sort (BPM + Camelot Key) after adding"
        )
        chk_auto_smart.setChecked(True)
        vlayout.addWidget(chk_auto_smart)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        vlayout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        chosen_ids: list[str] = []
        for i in range(track_list.count()):
            it = track_list.item(i)
            if it.checkState() == Qt.CheckState.Checked or it.isSelected():
                chosen_ids.append(str(it.data(Qt.ItemDataRole.UserRole)))

        if not chosen_ids:
            return

        with session_scope() as session:
            proj_svc = ProjectService(session)
            t_cfg = TransitionConfig(
                transition_type=TransitionType.BASS_SWAP_EQ if len(chosen_ids) > 1 else TransitionType.NONE,
                overlap_ms=3000 if len(chosen_ids) > 1 else 0,
            )
            for mid in chosen_ids:
                proj_svc.add_track(project_id, mid, transition_config=t_cfg)
            if chk_auto_smart.isChecked():
                proj_svc.auto_cue_trim_tracks(project_id)
                if len(proj_svc.list_tracks(project_id)) > 1:
                    proj_svc.auto_harmonic_sort(project_id)
        self._reload_tracks()

    def _on_move_track(self, delta: int) -> None:
        project_id = self.current_project_id()
        row = self.tracks_table.currentRow()
        if not project_id or row < 0 or row >= len(self._track_ids):
            return
        target = row + delta
        if target < 0 or target >= len(self._track_ids):
            return
        ordered = list(self._track_ids)
        ordered[row], ordered[target] = ordered[target], ordered[row]
        with session_scope() as session:
            ProjectService(session).reorder_tracks(project_id, ordered)
        self._reload_tracks()
        self.tracks_table.selectRow(target)

    def _on_remove_track(self) -> None:
        row = self.tracks_table.currentRow()
        if row < 0 or row >= len(self._track_ids):
            return
        track_id = self._track_ids[row]
        with session_scope() as session:
            ProjectService(session).remove_track(track_id)
        self._reload_tracks()

    def _on_auto_cue_trim(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            return
        with session_scope() as session:
            ProjectService(session).auto_cue_trim_tracks(project_id)
        self._reload_tracks()
        QMessageBox.information(
            self,
            "Auto-Cue Trim Applied",
            "Updated track start/end trims using detected non-silent cue points.",
        )

    def _on_harmonic_sort(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            return
        with session_scope() as session:
            ProjectService(session).auto_harmonic_sort(project_id)
        self._reload_tracks()
        QMessageBox.information(
            self,
            "Harmonic Sort Applied",
            "Reordered timeline tracks for Camelot key compatibility and smooth BPM progression.",
        )

    def _on_track_selected(self) -> None:
        project_id = self.current_project_id()
        row = self.tracks_table.currentRow()
        if not project_id or row < 0 or row >= len(self._track_ids):
            return
        track_id = self._track_ids[row]
        with session_scope() as session:
            tracks = ProjectService(session).list_tracks(project_id)
        match = next((t for t in tracks if t.id == track_id), None)
        if not match:
            return
        if hasattr(self, "editor_group") and hasattr(self.editor_group, "set_collapsed"):
            self.editor_group.set_collapsed(False)  # type: ignore[attr-defined]
        self.trim_start_spin.setValue(match.trim_start_ms)
        self.trim_end_spin.setValue(match.trim_end_ms or 0)
        self.gain_spin.setValue(match.gain_db)
        self.fade_in_spin.setValue(match.fade_in_ms)
        self.fade_out_spin.setValue(match.fade_out_ms)
        self.transition_type_combo.setCurrentText(match.transition_config.transition_type.value)
        self.crossfade_spin.setValue(match.transition_config.overlap_ms)

    def _on_save_track_params(self) -> None:
        project_id = self.current_project_id()
        row = self.tracks_table.currentRow()
        if not project_id or row < 0 or row >= len(self._track_ids):
            return
        track_id = self._track_ids[row]
        with session_scope() as session:
            svc = ProjectService(session)
            tracks = svc.list_tracks(project_id)
            match = next((t for t in tracks if t.id == track_id), None)
            if not match:
                return
            match.trim_start_ms = self.trim_start_spin.value()
            end_val = self.trim_end_spin.value()
            match.trim_end_ms = end_val if end_val > 0 else None
            match.gain_db = float(self.gain_spin.value())
            match.fade_in_ms = self.fade_in_spin.value()
            match.fade_out_ms = self.fade_out_spin.value()
            overlap = self.crossfade_spin.value()
            t_type = TransitionType(self.transition_type_combo.currentText())
            match.transition_config = TransitionConfig(
                transition_type=t_type if overlap > 0 else TransitionType.NONE,
                overlap_ms=overlap,
            )
            svc.update_track(match)
        self._reload_tracks()
        self.tracks_table.selectRow(row)

    def _resolve_and_save_output_base(self) -> Path:
        settings = get_settings()
        raw = self.output_dir_input.text().strip() if hasattr(self, "output_dir_input") else ""
        if raw:
            saved = settings.set_output_dir(raw)
            self.output_dir_input.setText(str(saved))
            self._notify_output_dir_changed()
            return saved
        return settings.resolved_output_dir()

    def _on_output_dir_edited(self) -> None:
        raw = self.output_dir_input.text().strip()
        if raw:
            try:
                saved = get_settings().set_output_dir(raw)
                self.output_dir_input.setText(str(saved))
                self._notify_output_dir_changed()
            except Exception as exc:
                QMessageBox.warning(self, "Invalid Output Folder", str(exc))

    def _on_browse_output_dir(self) -> None:
        current = self.output_dir_input.text().strip() or str(get_settings().resolved_output_dir())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Output Location for Videos, Mixes & Release Packages",
            current,
        )
        if not chosen:
            return
        saved = get_settings().set_output_dir(chosen)
        self.output_dir_input.setText(str(saved))
        self._notify_output_dir_changed()

    def _on_open_output_dir(self) -> None:
        base = self._resolve_and_save_output_base()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(base)))

    def _notify_output_dir_changed(self) -> None:
        win = self.window()
        pages_dict = getattr(win, "pages", None)
        if isinstance(pages_dict, dict):
            for key in ("settings", "artwork", "dashboard"):
                page = pages_dict.get(key)
                if page is not None and hasattr(page, "refresh"):
                    try:
                        page.refresh()
                    except Exception:
                        pass

    def _resolve_clean_output_name(self, project_id: str) -> str:
        """Resolve a filesystem-safe output folder and file stem from Output Name input or project title."""
        raw = self.output_name_input.text().strip() if hasattr(self, "output_name_input") else ""
        if not raw:
            with session_scope() as session:
                proj = ProjectService(session).get_project(project_id)
            if proj is not None and proj.name.strip():
                raw = proj.name.strip()
        return sanitize_output_name(raw) if raw else project_id

    def _on_run_production(self) -> None:
        channel_id = self.current_channel_id()
        if not channel_id:
            QMessageBox.warning(
                self,
                "Channel Profile Required",
                "Please select or create a Channel Profile before packaging a release.",
            )
            return
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Production", "Please select a project first.")
            return
        base_out = self._resolve_and_save_output_base()
        clean_out_name = self._resolve_clean_output_name(project_id)
        project_out_dir = base_out / clean_out_name
        vis_style = self.visualizer_combo.currentText()
        custom_vis = self.selected_visual_asset_path()
        fx_payload = {
            "now_playing_overlay": self.chk_now_playing.isChecked(),
            "progress_bar": self.chk_progress.isChecked(),
            "slow_zoom": self.chk_zoom.isChecked(),
            "film_grain": self.chk_vintage.isChecked(),
            "vignette": self.chk_vintage.isChecked(),
        }
        try:
            if hasattr(self, "stage_status_label"):
                self.stage_status_label.setText("Running Pipeline: Validating → Mixing → Visuals → Rendering → Packaging…")
            if hasattr(self, "stage_progress_bar"):
                self.stage_progress_bar.setValue(35)
            QApplication.processEvents()
            with session_scope() as session:
                runner = ProductionJobRunner(session)
                job = runner.enqueue_production_job(
                    project_id,
                    output_dir=project_out_dir,
                    visualizer_style=vis_style,
                    visual_fx=fx_payload,
                    custom_visual_path=custom_vis,
                    output_name=clean_out_name,
                )
                summary = runner.run_job(job.id)
                NLEExporterService(session).export_project_timeline(
                    project_id,
                    project_out_dir,
                    output_name=clean_out_name,
                    visual_asset_path=custom_vis,
                )
            if hasattr(self, "stage_status_label"):
                self.stage_status_label.setText(f"Completed: {clean_out_name}.mp4 + NLE XML packaged!")
            if hasattr(self, "stage_progress_bar"):
                self.stage_progress_bar.setValue(100)
            self._reload_projects()
            QMessageBox.information(
                self,
                "Production Complete",
                f"Project packaged successfully as '{clean_out_name}'!\n\n"
                f"Output directory: {summary.output_dir}\n"
                f"Video file: {Path(summary.output_dir) / f'{clean_out_name}.mp4'}\n"
                f"NLE Timeline XML: {Path(summary.output_dir) / f'{clean_out_name}_timeline.fcpxml'}\n"
                f"Manifest: {summary.manifest_path}\n"
                f"Executed stages: {', '.join(summary.executed_stages)}",
            )
        except Exception as exc:
            if hasattr(self, "stage_status_label"):
                self.stage_status_label.setText("Pipeline Error — Check settings and try again")
            QMessageBox.critical(self, "Production Failed", str(exc))

    def _on_export_nle_bundle(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Export Timeline XML", "Please select a project first.")
            return
        base_out = self._resolve_and_save_output_base()
        clean_out_name = self._resolve_clean_output_name(project_id)
        out_dir = base_out / clean_out_name
        custom_vis = self.selected_visual_asset_path()
        try:
            with session_scope() as session:
                bundle = NLEExporterService(session).export_project_timeline(
                    project_id,
                    out_dir,
                    output_name=clean_out_name,
                    visual_asset_path=custom_vis,
                )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(bundle.output_dir)))
            QMessageBox.information(
                self,
                "Timeline Exported for External Video Editor",
                f"Exported {bundle.clip_count}-track timeline package to:\n  {bundle.output_dir}\n\n"
                f"• FCPXML Timeline: {bundle.fcpxml_path.name}\n"
                f"• CMX 3600 EDL: {bundle.edl_path.name}\n"
                f"• CSV Clip List: {bundle.csv_clip_list_path.name}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Timeline XML Export Failed", str(exc))

    def _on_export_short_highlight(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Short Clipper", "Please select a project first.")
            return
        base_out = self._resolve_and_save_output_base()
        clean_out_name = self._resolve_clean_output_name(project_id)
        try:
            with session_scope() as session:
                proj_svc = ProjectService(session)
                media_svc = MediaLibraryService(session)
                proj = proj_svc.get_project(project_id)
                tracks = proj_svc.list_tracks(project_id)
                if not proj or not tracks:
                    QMessageBox.warning(
                        self, "Short Clipper", "Add at least one track to the project first."
                    )
                    return
                first_media = media_svc.get(tracks[0].media_file_id)
                if not first_media:
                    return
                source_path = Path(first_media.path)
                out_dir = base_out / clean_out_name / "shorts"
                clipper = ShortsClipperService()
                short_res = clipper.create_highlight_short(
                    source_path,
                    out_dir,
                    title=proj.name,
                    output_name=clean_out_name,
                    source_duration_ms=first_media.duration_ms,
                )
            QMessageBox.information(
                self,
                "9:16 Highlight Short Exported",
                f"Extracted peak highlight ({short_res.start_ms}ms – {short_res.end_ms}ms):\n\n"
                f"Video (1080x1920): {short_res.video_path}\n"
                f"Thumbnail: {short_res.thumbnail_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Short Export Failed", str(exc))
