"""Production UI page – VirtualDJ harmonic/cue tools, CapCut visual FX & Shorts clipper."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
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


class ProductionPage(QWidget):
    """Interactive production workspace with VirtualDJ smart mixing & CapCut video styling."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel_ids: list[str] = []
        self._project_ids: list[str] = []
        self._track_ids: list[str] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        heading = QLabel("Production Workspace (VirtualDJ Mixing + CapCut Video Studio)")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        # Top bar: Channel & Project selectors
        selector_row = QHBoxLayout()
        selector_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        selector_row.addWidget(self.channel_combo, stretch=1)

        new_channel_btn = QPushButton("+ Channel")
        new_channel_btn.clicked.connect(self._on_new_channel)
        selector_row.addWidget(new_channel_btn)

        selector_row.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        selector_row.addWidget(self.project_combo, stretch=1)

        new_project_btn = QPushButton("+ Project")
        new_project_btn.clicked.connect(self._on_new_project)
        selector_row.addWidget(new_project_btn)

        root.addLayout(selector_row)

        # Main split: Left = Timeline tracks & VirtualDJ smart tools, Right = Track Editor + CapCut Visuals + Produce
        body = QHBoxLayout()

        left_col = QVBoxLayout()
        track_btns = QHBoxLayout()
        add_track_btn = QPushButton("Add Track…")
        add_track_btn.clicked.connect(self._on_add_track)
        track_btns.addWidget(add_track_btn)

        move_up_btn = QPushButton("Up")
        move_up_btn.clicked.connect(lambda: self._on_move_track(-1))
        track_btns.addWidget(move_up_btn)

        move_down_btn = QPushButton("Down")
        move_down_btn.clicked.connect(lambda: self._on_move_track(1))
        track_btns.addWidget(move_down_btn)

        remove_track_btn = QPushButton("Remove")
        remove_track_btn.clicked.connect(self._on_remove_track)
        track_btns.addWidget(remove_track_btn)

        auto_cue_btn = QPushButton("Auto-Cue Silence Trim")
        auto_cue_btn.clicked.connect(self._on_auto_cue_trim)
        track_btns.addWidget(auto_cue_btn)

        harmonic_btn = QPushButton("Smart Harmonic Sort (BPM+Key)")
        harmonic_btn.clicked.connect(self._on_harmonic_sort)
        track_btns.addWidget(harmonic_btn)

        left_col.addLayout(track_btns)

        self.tracks_table = QTableWidget(0, 7)
        self.tracks_table.setHorizontalHeaderLabels(
            ["#", "Track", "BPM / Key", "Trim (ms)", "Gain (dB)", "Fade In/Out", "Transition"]
        )
        self.tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tracks_table.itemSelectionChanged.connect(self._on_track_selected)
        left_col.addWidget(self.tracks_table, stretch=1)

        body.addLayout(left_col, stretch=3)

        # Right column: Track Editor + CapCut Visual FX + Chapter Preview + Produce / Shorts buttons
        right_col = QVBoxLayout()
        editor_group = QGroupBox("Selected Track & VirtualDJ Transition Settings")
        form = QFormLayout(editor_group)

        self.trim_start_spin = QSpinBox()
        self.trim_start_spin.setRange(0, 36_000_000)
        self.trim_start_spin.setSingleStep(500)
        form.addRow("Trim Start (ms):", self.trim_start_spin)

        self.trim_end_spin = QSpinBox()
        self.trim_end_spin.setRange(0, 36_000_000)
        self.trim_end_spin.setSingleStep(500)
        self.trim_end_spin.setSpecialValueText("Full Length (0)")
        form.addRow("Trim End (ms):", self.trim_end_spin)

        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(-24.0, 24.0)
        self.gain_spin.setSingleStep(0.5)
        form.addRow("Gain (dB):", self.gain_spin)

        self.fade_in_spin = QSpinBox()
        self.fade_in_spin.setRange(0, 60_000)
        self.fade_in_spin.setSingleStep(500)
        form.addRow("Fade In (ms):", self.fade_in_spin)

        self.fade_out_spin = QSpinBox()
        self.fade_out_spin.setRange(0, 60_000)
        self.fade_out_spin.setSingleStep(500)
        form.addRow("Fade Out (ms):", self.fade_out_spin)

        self.transition_type_combo = QComboBox()
        self.transition_type_combo.addItems(
            [
                TransitionType.CROSSFADE.value,
                TransitionType.BASS_SWAP_EQ.value,
                TransitionType.NONE.value,
            ]
        )
        form.addRow("Transition Mode:", self.transition_type_combo)

        self.crossfade_spin = QSpinBox()
        self.crossfade_spin.setRange(0, 30_000)
        self.crossfade_spin.setSingleStep(500)
        self.crossfade_spin.setValue(3000)
        form.addRow("Overlap (ms):", self.crossfade_spin)

        apply_track_btn = QPushButton("Save Track Parameters")
        apply_track_btn.clicked.connect(self._on_save_track_params)
        form.addRow(apply_track_btn)

        right_col.addWidget(editor_group)

        # CapCut Visual FX Group
        fx_group = QGroupBox("CapCut Video Styling & Visualizer FX")
        fx_layout = QFormLayout(fx_group)

        self.visualizer_combo = QComboBox()
        self.visualizer_combo.addItems([v.value for v in VisualizerStyle])
        fx_layout.addRow("Audio Visualizer:", self.visualizer_combo)

        self.chk_now_playing = QCheckBox("Dynamic 'Now Playing' Track Title Overlay (Synced to Chapters)")
        self.chk_now_playing.setChecked(True)
        fx_layout.addRow(self.chk_now_playing)

        self.chk_progress = QCheckBox("Animated Bottom Playback Progress Bar")
        self.chk_progress.setChecked(True)
        fx_layout.addRow(self.chk_progress)

        self.chk_zoom = QCheckBox("Ken Burns Slow Zoom / Pan Motion")
        fx_layout.addRow(self.chk_zoom)

        self.chk_vintage = QCheckBox("Vintage Film Grain & Warm Vignette")
        fx_layout.addRow(self.chk_vintage)

        right_col.addWidget(fx_group)

        # Chapters & Action Buttons
        chapters_group = QGroupBox("Generated Chapters & Export Actions")
        chapters_layout = QVBoxLayout(chapters_group)
        self.chapters_preview = QPlainTextEdit()
        self.chapters_preview.setReadOnly(True)
        chapters_layout.addWidget(self.chapters_preview)

        self.produce_btn = QPushButton("Run Full Production Pipeline (Mix → Thumbnail → Video → Package)")
        self.produce_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self.produce_btn.clicked.connect(self._on_run_production)
        chapters_layout.addWidget(self.produce_btn)

        self.shorts_btn = QPushButton("Export 9:16 Short / Reel Highlight (Peak 30s Auto-Clipper)")
        self.shorts_btn.clicked.connect(self._on_export_short_highlight)
        chapters_layout.addWidget(self.shorts_btn)

        right_col.addWidget(chapters_group, stretch=1)
        body.addLayout(right_col, stretch=2)

        root.addLayout(body, stretch=1)

    def refresh(self) -> None:
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
            return

        with session_scope() as session:
            proj_svc = ProjectService(session)
            media_svc = MediaLibraryService(session)
            tracks = proj_svc.list_tracks(project_id)
            chapters = proj_svc.compute_chapters(project_id)
            total_ms = proj_svc.compute_total_duration_ms(project_id)

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

    def _on_run_production(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Production", "Please select a project first.")
            return
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
                out_dir = get_settings().resolved_data_dir() / "jobs" / project_id / "shorts"
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
