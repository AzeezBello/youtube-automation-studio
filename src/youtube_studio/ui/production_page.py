"""Production UI page – harmonic/cue tools, visual FX, audio visualizers & Shorts clipper."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.config import get_settings
from youtube_studio.domain.models.media import MediaType
from youtube_studio.domain.models.project import ProjectType, TransitionConfig, TransitionType
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.jobs.runner import ProductionJobRunner
from youtube_studio.media.renderer import VisualizerStyle
from youtube_studio.media.shorts_clipper import ShortsClipperService
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget


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

        root.addLayout(selector_row)

        # Empty State Guide (displayed when no tracks are in the current timeline)
        self.empty_state = EmptyStateWidget(
            title="No Tracks in Your Project Timeline Yet",
            description=(
                "Create or select a channel and project above, then add audio tracks from your Music Library "
                "to build a single-track video or multi-track harmonic mix."
            ),
            tips=[
                "<b>Smart Harmonic Sort:</b> Automatically orders tracks by Camelot Wheel compatibility (1A–12B) and gradual BPM progression.",
                "<b>Auto-Cue Silence Trim:</b> Strips dead air at the start and end of every track for tight transitions.",
                "<b>Bass-Swap EQ & Visualizers:</b> Eliminates low-end frequency clash during crossfades and renders multi-band spectrum visuals.",
            ],
            action_label="+ Create Project",
            action_tooltip="Create a new production project for the selected channel.",
            on_action=self._on_new_project,
            secondary_label="+ Add Track to Timeline",
            secondary_tooltip="Pick an indexed audio track from your Music Library and add it to the timeline.",
            on_secondary=self._on_add_track,
        )
        root.addWidget(self.empty_state)

        # Main split: Left = Timeline tracks & smart tools, Right = Track Editor + Visual FX + Produce
        body = QHBoxLayout()

        left_col = QVBoxLayout()
        track_btns_top = QHBoxLayout()
        add_track_btn = QPushButton("Add Track…")
        add_track_btn.setObjectName("AccentButton")
        add_track_btn.setToolTip("Add an indexed audio track from the Music Library into this project's timeline.")
        add_track_btn.clicked.connect(self._on_add_track)
        track_btns_top.addWidget(add_track_btn)

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
        auto_cue_btn = QPushButton("Auto-Cue Silence Trim")
        auto_cue_btn.setToolTip(
            "Automatically detect and trim leading/trailing silence on all tracks in this project."
        )
        auto_cue_btn.clicked.connect(self._on_auto_cue_trim)
        track_btns_bottom.addWidget(auto_cue_btn)

        harmonic_btn = QPushButton("Smart Harmonic Sort (BPM+Key)")
        harmonic_btn.setToolTip(
            "Reorder tracks for smooth Camelot Wheel harmonic compatibility and gradual tempo progression."
        )
        harmonic_btn.clicked.connect(self._on_harmonic_sort)
        track_btns_bottom.addWidget(harmonic_btn)

        left_col.addLayout(track_btns_bottom)

        self.tracks_table = QTableWidget(0, 7)
        self.tracks_table.setAlternatingRowColors(True)
        self.tracks_table.setToolTip(
            "Project timeline tracks. Select any row to edit its trim, gain, fade, and transition settings on the right."
        )
        self.tracks_table.setHorizontalHeaderLabels(
            ["#", "Track", "BPM / Key", "Trim (ms)", "Gain (dB)", "Fade In/Out", "Transition"]
        )
        self.tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tracks_table.itemSelectionChanged.connect(self._on_track_selected)
        left_col.addWidget(self.tracks_table, stretch=1)

        body.addLayout(left_col, stretch=3)

        # Right column: Track Editor + Visual FX + Chapter Preview + Produce / Shorts buttons
        right_col = QVBoxLayout()
        editor_group = QGroupBox("Selected Track & Harmonic Transition Settings")
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

        # Video Styling & Visualizer FX Group
        fx_group = QGroupBox("Video Styling, Overlays & Audio Visualizer FX")
        fx_layout = QFormLayout(fx_group)

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

        right_col.addWidget(chapters_group, stretch=1)
        body.addLayout(right_col, stretch=2)

        root.addLayout(body, stretch=1)

    def refresh(self) -> None:
        if hasattr(self, "output_dir_input"):
            self.output_dir_input.setText(str(get_settings().resolved_output_dir()))
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
        self._reload_tracks()

    def _reload_tracks(self) -> None:
        project_id = self.current_project_id()
        self.tracks_table.setRowCount(0)
        self._track_ids = []
        self.chapters_preview.setPlainText("")
        if not project_id:
            if hasattr(self, "empty_state"):
                self.empty_state.setVisible(True)
            return

        with session_scope() as session:
            proj_svc = ProjectService(session)
            media_svc = MediaLibraryService(session)
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

        lines = [f"Estimated Total Duration: {total_ms / 1000.0:.1f}s", "", "Chapters:"]
        for ch in chapters:
            lines.append(f"{ch.format_timestamp()} {ch.title}")
        self.chapters_preview.setPlainText("\n".join(lines))

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
            QMessageBox.warning(self, "New Project", "Please create or select a channel first.")
            return
        name, ok = QInputDialog.getText(self, "New Project", "Project name:")
        if not ok or not name.strip():
            return
        types = [t.value for t in ProjectType]
        chosen, ok_type = QInputDialog.getItem(
            self, "Project Type", "Select project type:", types, 0, False
        )
        if not ok_type:
            return
        with session_scope() as session:
            ProjectService(session).create_project(
                channel_id,
                name.strip(),
                project_type=ProjectType(chosen),
            )
        self._reload_projects()

    def _on_add_track(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Add Track", "Please create or select a project first.")
            return
        with session_scope() as session:
            media_items = MediaLibraryService(session).list_media(media_type=MediaType.AUDIO)
        if not media_items:
            QMessageBox.information(
                self,
                "Add Track",
                "No audio tracks found in the Music Library. Scan a folder in Music Library first.",
            )
            return
        labels = [
            f"{m.metadata.get('title') or Path(m.path).name} ({m.path})" for m in media_items
        ]
        chosen, ok = QInputDialog.getItem(
            self, "Add Track to Timeline", "Select audio track:", labels, 0, False
        )
        if not ok:
            return
        selected_media = media_items[labels.index(chosen)]
        with session_scope() as session:
            ProjectService(session).add_track(project_id, selected_media.id)
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

    def _on_run_production(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Production", "Please select a project first.")
            return
        base_out = self._resolve_and_save_output_base()
        project_out_dir = base_out / project_id
        vis_style = self.visualizer_combo.currentText()
        fx_payload = {
            "now_playing_overlay": self.chk_now_playing.isChecked(),
            "progress_bar": self.chk_progress.isChecked(),
            "slow_zoom": self.chk_zoom.isChecked(),
            "film_grain": self.chk_vintage.isChecked(),
            "vignette": self.chk_vintage.isChecked(),
        }
        try:
            with session_scope() as session:
                runner = ProductionJobRunner(session)
                job = runner.enqueue_production_job(
                    project_id,
                    output_dir=project_out_dir,
                    visualizer_style=vis_style,
                    visual_fx=fx_payload,
                )
                summary = runner.run_job(job.id)
            self._reload_projects()
            QMessageBox.information(
                self,
                "Production Complete",
                f"Project packaged successfully!\n\n"
                f"Output directory: {summary.output_dir}\n"
                f"Manifest: {summary.manifest_path}\n"
                f"Executed stages: {', '.join(summary.executed_stages)}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Production Failed", str(exc))

    def _on_export_short_highlight(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Short Clipper", "Please select a project first.")
            return
        base_out = self._resolve_and_save_output_base()
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
                out_dir = base_out / project_id / "shorts"
                clipper = ShortsClipperService()
                short_res = clipper.create_highlight_short(
                    source_path,
                    out_dir,
                    title=proj.name,
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
