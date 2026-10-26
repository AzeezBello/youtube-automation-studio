"""Production UI page – manage projects, track timelines, chapters, and video rendering jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
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

from youtube_studio.domain.models.media import MediaType
from youtube_studio.domain.models.project import ProjectType, TransitionConfig, TransitionType
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.jobs.runner import ProductionJobRunner
from youtube_studio.storage import session_scope


class ProductionPage(QWidget):
    """Interactive P1 production workspace for single-track and multi-track DJ mix videos."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel_ids: list[str] = []
        self._project_ids: list[str] = []
        self._track_ids: list[str] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        heading = QLabel("Production Workspace")
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

        # Main split: Left = Timeline tracks & controls, Right = Track parameters & Chapters
        body = QHBoxLayout()

        left_col = QVBoxLayout()
        track_btns = QHBoxLayout()
        add_track_btn = QPushButton("Add Library Track…")
        add_track_btn.clicked.connect(self._on_add_track)
        track_btns.addWidget(add_track_btn)

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(lambda: self._on_move_track(-1))
        track_btns.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(lambda: self._on_move_track(1))
        track_btns.addWidget(move_down_btn)

        remove_track_btn = QPushButton("Remove Track")
        remove_track_btn.clicked.connect(self._on_remove_track)
        track_btns.addWidget(remove_track_btn)

        left_col.addLayout(track_btns)

        self.tracks_table = QTableWidget(0, 6)
        self.tracks_table.setHorizontalHeaderLabels(
            ["#", "Track", "Trim (ms)", "Gain (dB)", "Fade In/Out (ms)", "Crossfade (ms)"]
        )
        self.tracks_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tracks_table.itemSelectionChanged.connect(self._on_track_selected)
        left_col.addWidget(self.tracks_table, stretch=1)

        body.addLayout(left_col, stretch=3)

        # Right column: Track Editor + Chapter Preview + Produce button
        right_col = QVBoxLayout()
        editor_group = QGroupBox("Selected Track Settings")
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

        self.crossfade_spin = QSpinBox()
        self.crossfade_spin.setRange(0, 30_000)
        self.crossfade_spin.setSingleStep(500)
        self.crossfade_spin.setValue(3000)
        form.addRow("Crossfade Overlap (ms):", self.crossfade_spin)

        apply_track_btn = QPushButton("Save Track Parameters")
        apply_track_btn.clicked.connect(self._on_save_track_params)
        form.addRow(apply_track_btn)

        right_col.addWidget(editor_group)

        chapters_group = QGroupBox("Generated Chapters & Package Status")
        chapters_layout = QVBoxLayout(chapters_group)
        self.chapters_preview = QPlainTextEdit()
        self.chapters_preview.setReadOnly(True)
        chapters_layout.addWidget(self.chapters_preview)

        self.produce_btn = QPushButton("Run Production Pipeline (Mix → Thumbnail → Video → Package)")
        self.produce_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        self.produce_btn.clicked.connect(self._on_run_production)
        chapters_layout.addWidget(self.produce_btn)

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
                trim_str = f"{pt.trim_start_ms} – {pt.trim_end_ms or 'end'}"
                fade_str = f"{pt.fade_in_ms} / {pt.fade_out_ms}"
                xfade_str = (
                    str(pt.transition_config.overlap_ms)
                    if pt.transition_config.transition_type == TransitionType.CROSSFADE
                    else "0"
                )
                self.tracks_table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
                self.tracks_table.setItem(idx, 1, QTableWidgetItem(title))
                self.tracks_table.setItem(idx, 2, QTableWidgetItem(trim_str))
                self.tracks_table.setItem(idx, 3, QTableWidgetItem(f"{pt.gain_db:+.1f}"))
                self.tracks_table.setItem(idx, 4, QTableWidgetItem(fade_str))
                self.tracks_table.setItem(idx, 5, QTableWidgetItem(xfade_str))

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
        self.crossfade_spin.setValue(
            match.transition_config.overlap_ms
            if match.transition_config.transition_type == TransitionType.CROSSFADE
            else 0
        )

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
            match.transition_config = TransitionConfig(
                transition_type=TransitionType.CROSSFADE if overlap > 0 else TransitionType.NONE,
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
        try:
            with session_scope() as session:
                runner = ProductionJobRunner(session)
                job = runner.enqueue_production_job(project_id)
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
