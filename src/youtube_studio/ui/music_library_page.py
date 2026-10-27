"""Music Library UI page – create folders, upload audio files, preview/play tracks, edit metadata, and manage library."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.config import get_settings
from youtube_studio.domain.models.media import MediaFile, MediaType
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.media.scanner import AUDIO_EXTS, MediaScanner
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget


class MusicLibraryPage(QWidget):
    """Interactive music library browser with folder creation, audio upload, built-in preview player, and track management."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scanner = MediaScanner()
        self._media_items: list[MediaFile] = []
        self._current_playing_path: Optional[str] = None
        self._slider_dragging: bool = False
        self._afplay_proc: Optional[subprocess.Popen] = None

        # QtMultimedia audio player for in-app track preview
        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.8)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.durationChanged.connect(self._on_player_duration_changed)
        self._player.playbackStateChanged.connect(self._on_player_state_changed)

        self._ensure_default_folders()
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Managed Music Library Folders
    # ------------------------------------------------------------------
    @staticmethod
    def _managed_library_root() -> Path:
        root = get_settings().resolved_data_dir() / "music_library"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _ensure_default_folders(self) -> None:
        root = self._managed_library_root()
        (root / "General Uploads").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name.strip()).strip(". ")
        return cleaned or "Untitled Folder"

    def list_library_folders(self) -> list[Path]:
        """Return all managed subdirectories under the studio music_library root."""
        root = self._managed_library_root()
        folders = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
        if not folders:
            default_dir = root / "General Uploads"
            default_dir.mkdir(parents=True, exist_ok=True)
            folders.append(default_dir)
        return folders

    def create_library_folder(self, folder_name: str) -> Path:
        """Create a named folder inside the managed Music Library root and refresh the UI filter."""
        safe_name = self._sanitize_folder_name(folder_name)
        target = self._managed_library_root() / safe_name
        target.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "folder_input"):
            self.folder_input.setText(str(target))
        self.refresh()
        if hasattr(self, "folder_filter_combo"):
            idx = self.folder_filter_combo.findData(safe_name)
            if idx >= 0:
                self.folder_filter_combo.setCurrentIndex(idx)
        return target

    def upload_audio_files(
        self,
        file_paths: list[str | Path],
        *,
        folder_name: Optional[str] = None,
        copy_to_library: bool = True,
    ) -> list[MediaFile]:
        """Import one or more audio files into the specified Music Library folder and index them in SQLite."""
        selected_folder_name = (
            self._sanitize_folder_name(folder_name)
            if folder_name
            else self._active_target_folder_name()
        )
        target_dir = self._managed_library_root() / selected_folder_name
        target_dir.mkdir(parents=True, exist_ok=True)

        uploaded: list[MediaFile] = []
        with session_scope() as session:
            svc = MediaLibraryService(session)
            for raw_src in file_paths:
                src = Path(raw_src).expanduser().resolve()
                if not src.exists() or not src.is_file():
                    continue
                if src.suffix.lower() not in AUDIO_EXTS:
                    continue

                if copy_to_library:
                    dest = target_dir / src.name
                    if dest.resolve() != src.resolve():
                        if dest.exists():
                            # Avoid overwriting a different file with the same name
                            stem = src.stem
                            suffix = src.suffix
                            counter = 2
                            while dest.exists() and dest.resolve() != src.resolve():
                                dest = target_dir / f"{stem}_{counter}{suffix}"
                                counter += 1
                        shutil.copy2(src, dest)
                    final_path = dest
                else:
                    final_path = src

                media = self._scanner.inspect_file(final_path)
                media.metadata["folder"] = selected_folder_name
                saved = svc.upsert(media)
                uploaded.append(saved)

        self.refresh()
        return uploaded

    def _active_target_folder_name(self) -> str:
        if hasattr(self, "folder_filter_combo"):
            data = str(self.folder_filter_combo.currentData() or "").strip()
            if data and not data.startswith("path:"):
                return data
        return "General Uploads"

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Music Library & Harmonic Analyzer")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        layout.addWidget(heading)

        subtitle = QLabel(
            "Create music folders, upload audio tracks, preview/play tracks with live scrubbing, "
            "inspect BPM & Camelot keys (1A–12B), and manage or remove tracks."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(subtitle)

        # Row 1: Folder / Collection Filter + Create Folder + Upload Audio Files + Search
        folder_bar = QHBoxLayout()
        folder_bar.addWidget(QLabel("Library Folder:"))

        self.folder_filter_combo = QComboBox()
        self.folder_filter_combo.setMinimumWidth(210)
        self.folder_filter_combo.setToolTip(
            "Filter the music library by folder/collection, or select the target folder before uploading audio files."
        )
        self.folder_filter_combo.currentIndexChanged.connect(self._on_folder_filter_changed)
        folder_bar.addWidget(self.folder_filter_combo)

        self.create_folder_btn = QPushButton("📁 + Create Folder…")
        self.create_folder_btn.setToolTip(
            "Create a new named folder inside your Music Library to organize uploaded tracks and stems."
        )
        self.create_folder_btn.clicked.connect(self._on_create_folder_dialog)
        folder_bar.addWidget(self.create_folder_btn)

        self.upload_files_btn = QPushButton("⬆️ Upload Audio Files…")
        self.upload_files_btn.setObjectName("PrimaryButton")
        self.upload_files_btn.setToolTip(
            "Select one or more audio files (MP3, WAV, FLAC, M4A, AAC, OGG, AIFF, OPUS) to upload into the active Music Library folder."
        )
        self.upload_files_btn.clicked.connect(self._on_upload_audio_dialog)
        folder_bar.addWidget(self.upload_files_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by title, artist, folder, BPM, or key…")
        self.search_input.setToolTip("Type to filter indexed audio tracks in real time.")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        folder_bar.addWidget(self.search_input, stretch=1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload the music library table from the local database.")
        self.refresh_btn.clicked.connect(self.refresh)
        folder_bar.addWidget(self.refresh_btn)

        layout.addLayout(folder_bar)

        # Row 2: Scan External Folder Toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Scan Folder:"))
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select or enter any local folder path to scan in bulk…")
        self.folder_input.setToolTip(
            "Path to a local directory containing WAV, MP3, FLAC, M4A, AAC, OGG, AIFF, or OPUS audio files."
        )
        toolbar.addWidget(self.folder_input, stretch=2)

        self.browse_btn = QPushButton("Browse Folder…")
        self.browse_btn.setToolTip("Open a folder picker dialog to choose a music directory on disk.")
        self.browse_btn.clicked.connect(self._on_browse)
        toolbar.addWidget(self.browse_btn)

        self.scan_btn = QPushButton("Scan Folder")
        self.scan_btn.setToolTip(
            "Recursively scan the selected directory, compute waveform fingerprints, "
            "estimate BPM & Camelot keys, and index tracks in SQLite."
        )
        self.scan_btn.clicked.connect(self._on_scan)
        toolbar.addWidget(self.scan_btn)

        layout.addLayout(toolbar)

        # Row 3: Audio Preview Player & Track Management Actions
        player_box = QGroupBox("Audio Preview Player & Track Management")
        player_layout = QVBoxLayout(player_box)
        player_layout.setContentsMargins(12, 8, 12, 8)
        player_layout.setSpacing(6)

        transport_row = QHBoxLayout()
        self.prev_btn = QPushButton("⏮")
        self.prev_btn.setFixedWidth(38)
        self.prev_btn.setToolTip("Play previous track in the table.")
        self.prev_btn.clicked.connect(self._on_prev_track)
        transport_row.addWidget(self.prev_btn)

        self.play_btn = QPushButton("▶ Play / Preview")
        self.play_btn.setObjectName("PrimaryButton")
        self.play_btn.setToolTip(
            "Play or preview the selected audio track (you can also double-click any row in the table)."
        )
        self.play_btn.clicked.connect(self.play_selected_track)
        transport_row.addWidget(self.play_btn)

        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setToolTip("Pause or resume current track playback.")
        self.pause_btn.clicked.connect(self.pause_playback)
        transport_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setToolTip("Stop audio preview playback and reset position.")
        self.stop_btn.clicked.connect(self.stop_playback)
        transport_row.addWidget(self.stop_btn)

        self.next_btn = QPushButton("⏭")
        self.next_btn.setFixedWidth(38)
        self.next_btn.setToolTip("Play next track in the table.")
        self.next_btn.clicked.connect(self._on_next_track)
        transport_row.addWidget(self.next_btn)

        self.now_playing_label = QLabel("Ready to preview — select a track or double-click any row")
        self.now_playing_label.setStyleSheet("color: #38bdf8; font-weight: 600; margin-left: 8px;")
        transport_row.addWidget(self.now_playing_label, stretch=1)

        transport_row.addWidget(QLabel("🔊"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(95)
        self.volume_slider.setToolTip("Adjust preview playback volume (0–100%).")
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        transport_row.addWidget(self.volume_slider)

        player_layout.addLayout(transport_row)

        # Scrub slider + time indicator
        scrub_row = QHBoxLayout()
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.setToolTip("Drag to scrub/seek through the currently playing track.")
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        scrub_row.addWidget(self.position_slider, stretch=1)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #94a3b8; font-family: monospace;")
        scrub_row.addWidget(self.time_label)
        player_layout.addLayout(scrub_row)

        # Track management action buttons
        actions_row = QHBoxLayout()

        self.edit_track_btn = QPushButton("✏️ Edit Title / Artist")
        self.edit_track_btn.setToolTip("Edit the selected track's title, artist, or folder collection.")
        self.edit_track_btn.clicked.connect(self._on_edit_selected_track)
        actions_row.addWidget(self.edit_track_btn)

        self.move_folder_btn = QPushButton("📂 Move to Folder…")
        self.move_folder_btn.setToolTip("Assign or move the selected track(s) into a Music Library folder.")
        self.move_folder_btn.clicked.connect(self._on_move_to_folder_dialog)
        actions_row.addWidget(self.move_folder_btn)

        self.send_to_production_btn = QPushButton("➕ Send to Production")
        self.send_to_production_btn.setToolTip(
            "Send the selected track(s) (or all shown tracks) into a Production project with automatic silence trim & harmonic sort."
        )
        self.send_to_production_btn.clicked.connect(self._on_send_to_production)
        actions_row.addWidget(self.send_to_production_btn)

        self.autopilot_produce_btn = QPushButton("🚀 1-Click Auto-Produce Video")
        self.autopilot_produce_btn.setObjectName("AccentButton")
        self.autopilot_produce_btn.setToolTip(
            "Automatically build, harmonic-mix, generate SEO & thumbnail, and render a 16:9 video + 9:16 Short from the selected tracks or folder!"
        )
        self.autopilot_produce_btn.clicked.connect(self._on_autopilot_produce_from_library)
        actions_row.addWidget(self.autopilot_produce_btn)

        self.reveal_btn = QPushButton("🔍 Reveal File")
        self.reveal_btn.setToolTip("Reveal the selected audio file in Finder / File Explorer.")
        self.reveal_btn.clicked.connect(self._on_reveal_selected)
        actions_row.addWidget(self.reveal_btn)

        actions_row.addStretch(1)

        self.remove_dups_btn = QPushButton("🧹 Remove Duplicates")
        self.remove_dups_btn.setToolTip(
            "Automatically remove duplicate track entries that share an identical SHA-256 content hash."
        )
        self.remove_dups_btn.clicked.connect(self._on_remove_duplicates_clicked)
        actions_row.addWidget(self.remove_dups_btn)

        self.remove_btn = QPushButton("🗑 Remove Selected")
        self.remove_btn.setToolTip("Remove the selected track(s) from the Music Library.")
        self.remove_btn.clicked.connect(self._on_remove_selected_clicked)
        actions_row.addWidget(self.remove_btn)

        player_layout.addLayout(actions_row)
        layout.addWidget(player_box)

        self.summary_label = QLabel("0 tracks indexed")
        self.summary_label.setStyleSheet("color: #94a3b8; font-weight: 500;")
        layout.addWidget(self.summary_label)

        # Empty State Guide (visible when library has 0 tracks)
        self.empty_state = EmptyStateWidget(
            title="Your Music Library is Empty",
            description=(
                "Create a folder, upload audio files directly, or scan an existing folder on your computer "
                "to populate the library."
            ),
            tips=[
                "<b>Create Folders & Upload Tracks:</b> Click <b>📁 + Create Folder…</b> or <b>⬆️ Upload Audio Files…</b> above to organize tracks into collections.",
                "<b>Built-in Audio Preview:</b> Select any track and click <b>▶ Play / Preview</b> (or double-click a row) to listen and scrub through the waveform.",
                "<b>Harmonic & Tempo Analysis:</b> Every track is automatically analyzed for BPM, Camelot key (1A–12B), and SHA-256 duplicate protection.",
            ],
            action_label="⬆️ Upload Audio Files…",
            action_tooltip="Select audio files from your computer to upload and index immediately.",
            on_action=self._on_upload_audio_dialog,
        )
        layout.addWidget(self.empty_state)

        # Track table
        self.table = QTableWidget(0, 8)
        self.table.setAlternatingRowColors(True)
        self.table.setToolTip(
            "Double-click any row to preview/play the track. Select one or more rows to move, edit, send to Production, or remove."
        )
        self.table.setHorizontalHeaderLabels(
            ["Title", "Artist", "Folder", "Duration", "BPM / Key (Camelot)", "Format", "Status", "Path"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        layout.addWidget(self.table, stretch=1)

    # ------------------------------------------------------------------
    # Audio Preview & Playback Controls
    # ------------------------------------------------------------------
    def _selected_rows(self) -> list[int]:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if not rows and self.table.currentRow() >= 0:
            rows = [self.table.currentRow()]
        return [r for r in rows if 0 <= r < len(self._media_items)]

    def play_selected_track(self) -> None:
        rows = self._selected_rows()
        if not rows:
            if self._media_items:
                self.table.selectRow(0)
                rows = [0]
            else:
                QMessageBox.information(
                    self,
                    "No Tracks to Preview",
                    "Upload or scan audio tracks first before starting playback.",
                )
                return
        self.play_row(rows[0])

    def play_row(self, row_idx: int) -> bool:
        if row_idx < 0 or row_idx >= len(self._media_items):
            return False
        media = self._media_items[row_idx]
        file_path = Path(media.path)
        if not file_path.exists():
            QMessageBox.warning(
                self,
                "Audio File Missing",
                f"The audio file could not be found on disk:\n{file_path}",
            )
            return False

        self._stop_afplay()
        title = str(media.metadata.get("title") or file_path.stem)
        artist = str(media.metadata.get("artist") or "Unknown Artist")
        bpm = media.metadata.get("bpm")
        camelot = media.metadata.get("camelot_code")
        harmonic_tag = f" · {bpm} BPM ({camelot})" if bpm and camelot else ""

        if (
            self._current_playing_path == str(file_path)
            and self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        ):
            self._player.play()
        else:
            self._current_playing_path = str(file_path)
            self._player.setSource(QUrl.fromLocalFile(str(file_path)))
            self._player.play()

            # Fallback to macOS afplay if QtMultimedia has no audio backend in minimal environments
            if (
                sys.platform == "darwin"
                and self._player.error() != QMediaPlayer.Error.NoError
            ):
                try:
                    self._afplay_proc = subprocess.Popen(
                        ["afplay", str(file_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass

        if media.duration_ms and media.duration_ms > 0:
            self.position_slider.setRange(0, int(media.duration_ms))
            self.time_label.setText(f"00:00 / {self._format_duration(media.duration_ms)}")

        self.now_playing_label.setText(f"▶ Now Playing: {title} — {artist}{harmonic_tag}")
        self.play_btn.setText("▶ Playing")
        return True

    def pause_playback(self) -> None:
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.play_btn.setText("▶ Resume")
            curr = self.now_playing_label.text().replace("▶ Now Playing:", "⏸ Paused:")
            self.now_playing_label.setText(curr)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._player.play()
            self.play_btn.setText("▶ Playing")
            curr = self.now_playing_label.text().replace("⏸ Paused:", "▶ Now Playing:")
            self.now_playing_label.setText(curr)

    def stop_playback(self) -> None:
        self._player.stop()
        self._stop_afplay()
        self._current_playing_path = None
        self.position_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.play_btn.setText("▶ Play / Preview")
        self.now_playing_label.setText("⏹ Playback stopped — select a track or double-click any row")

    def _stop_afplay(self) -> None:
        if self._afplay_proc is not None:
            try:
                self._afplay_proc.terminate()
            except Exception:
                pass
            self._afplay_proc = None

    def _on_prev_track(self) -> None:
        if not self._media_items:
            return
        rows = self._selected_rows()
        curr = rows[0] if rows else 0
        prev_row = (curr - 1) % len(self._media_items)
        self.table.selectRow(prev_row)
        self.play_row(prev_row)

    def _on_next_track(self) -> None:
        if not self._media_items:
            return
        rows = self._selected_rows()
        curr = rows[0] if rows else -1
        next_row = (curr + 1) % len(self._media_items)
        self.table.selectRow(next_row)
        self.play_row(next_row)

    def _on_table_double_clicked(self, row: int, _col: int) -> None:
        self.play_row(row)

    def _on_volume_changed(self, value: int) -> None:
        self._audio_output.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _on_slider_pressed(self) -> None:
        self._slider_dragging = True

    def _on_slider_released(self) -> None:
        self._slider_dragging = False
        self._player.setPosition(self.position_slider.value())

    def _on_slider_moved(self, position_ms: int) -> None:
        dur = self._player.duration() or self.position_slider.maximum()
        self.time_label.setText(
            f"{self._format_duration(position_ms)} / {self._format_duration(dur)}"
        )

    def _on_player_position_changed(self, position_ms: int) -> None:
        if not self._slider_dragging:
            self.position_slider.setValue(int(position_ms))
        dur = self._player.duration() or self.position_slider.maximum()
        self.time_label.setText(
            f"{self._format_duration(position_ms)} / {self._format_duration(dur)}"
        )

    def _on_player_duration_changed(self, duration_ms: int) -> None:
        if duration_ms > 0:
            self.position_slider.setRange(0, int(duration_ms))

    def _on_player_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.StoppedState and self._current_playing_path is None:
            self.play_btn.setText("▶ Play / Preview")

    # ------------------------------------------------------------------
    # Folder Creation, Upload, Move, Edit, Remove & Duplicate Cleanup
    # ------------------------------------------------------------------
    def _on_create_folder_dialog(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Create Music Library Folder",
            "Enter a name for the new Music Library folder (e.g. 'Reggae Dubplates', 'Chillhop Beats', 'Intro Stems'):",
        )
        if not ok or not name.strip():
            return
        folder_path = self.create_library_folder(name.strip())
        QMessageBox.information(
            self,
            "Music Folder Created",
            f"Created Music Library folder:\n{folder_path.name}\n\n"
            f"Location:\n{folder_path}\n\n"
            "You can now click '⬆️ Upload Audio Files…' to add tracks directly into this folder.",
        )

    def _on_upload_audio_dialog(self) -> None:
        ext_globs = " ".join(f"*{ext}" for ext in sorted(AUDIO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files to Upload to Music Library",
            str(Path.home()),
            f"Audio Files ({ext_globs})",
        )
        if not files:
            return
        target_folder = self._active_target_folder_name()
        try:
            uploaded = self.upload_audio_files(files, folder_name=target_folder, copy_to_library=True)
            QMessageBox.information(
                self,
                "Audio Upload Complete",
                f"Uploaded and analyzed {len(uploaded)} audio track(s) into folder '{target_folder}'.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Upload Failed", str(exc))

    def _on_folder_filter_changed(self, _idx: int) -> None:
        data = str(self.folder_filter_combo.currentData() or "")
        if data and not data.startswith("path:"):
            candidate = self._managed_library_root() / data
            if candidate.exists():
                self.folder_input.setText(str(candidate))
        elif data.startswith("path:"):
            self.folder_input.setText(data[len("path:") :])
        self.refresh()

    def remove_selected_tracks(self, *, delete_from_disk: bool = False) -> int:
        """Remove all currently selected rows from the Music Library database (and optionally managed disk copy)."""
        rows = self._selected_rows()
        if not rows:
            return 0
        managed_root = self._managed_library_root().resolve()
        removed = 0
        with session_scope() as session:
            svc = MediaLibraryService(session)
            for r in rows:
                item = self._media_items[r]
                if self._current_playing_path == item.path:
                    self.stop_playback()
                if svc.delete(item.id):
                    removed += 1
                    if delete_from_disk:
                        p = Path(item.path).resolve()
                        if p.exists() and str(p).startswith(str(managed_root)):
                            try:
                                p.unlink()
                            except Exception:
                                pass
        self.refresh()
        return removed

    def _on_remove_selected_clicked(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(
                self,
                "Remove Track",
                "Select one or more tracks in the table first.",
            )
            return
        count = len(rows)
        sample_title = str(
            self._media_items[rows[0]].metadata.get("title")
            or Path(self._media_items[rows[0]].path).stem
        )
        label = f"'{sample_title}'" if count == 1 else f"{count} selected tracks"
        ans = QMessageBox.question(
            self,
            "Remove Selected Track(s)",
            f"Remove {label} from the Music Library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        removed = self.remove_selected_tracks(delete_from_disk=False)
        self.now_playing_label.setText(f"🗑 Removed {removed} track(s) from the Music Library.")

    def remove_duplicate_tracks(self) -> int:
        """Remove duplicate audio tracks sharing the same SHA-256 hash, keeping the first track in each group."""
        with session_scope() as session:
            svc = MediaLibraryService(session)
            removed = svc.remove_duplicates()
        self.refresh()
        return removed

    def _on_remove_duplicates_clicked(self) -> None:
        removed = self.remove_duplicate_tracks()
        if removed == 0:
            QMessageBox.information(
                self,
                "No Duplicates Found",
                "Your Music Library has no duplicate audio files.",
            )
        else:
            QMessageBox.information(
                self,
                "Duplicates Removed",
                f"Removed {removed} duplicate track record(s) from the Music Library.",
            )

    def update_track_metadata(
        self,
        media_id: str,
        *,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        folder: Optional[str] = None,
    ) -> Optional[MediaFile]:
        with session_scope() as session:
            svc = MediaLibraryService(session)
            updated = svc.update_metadata(media_id, title=title, artist=artist, folder=folder)
        self.refresh()
        return updated

    def _on_edit_selected_track(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Edit Track", "Select a track in the table first.")
            return
        media = self._media_items[rows[0]]
        curr_title = str(media.metadata.get("title") or Path(media.path).stem)
        curr_artist = str(media.metadata.get("artist") or "")
        curr_folder = self._resolve_item_folder_label(media)

        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Track Metadata & Folder")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)

        title_edit = QLineEdit(curr_title)
        artist_edit = QLineEdit(curr_artist)
        folder_combo = QComboBox()
        folder_combo.setEditable(True)
        for f_path in self.list_library_folders():
            folder_combo.addItem(f_path.name)
        folder_combo.setCurrentText(curr_folder)

        form.addRow("Track Title:", title_edit)
        form.addRow("Artist / Creator:", artist_edit)
        form.addRow("Library Folder:", folder_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_folder = self._sanitize_folder_name(folder_combo.currentText())
            (self._managed_library_root() / new_folder).mkdir(parents=True, exist_ok=True)
            self.update_track_metadata(
                media.id,
                title=title_edit.text().strip() or curr_title,
                artist=artist_edit.text().strip(),
                folder=new_folder,
            )

    def move_tracks_to_folder(self, media_ids: list[str], folder_name: str) -> int:
        safe_folder = self._sanitize_folder_name(folder_name)
        (self._managed_library_root() / safe_folder).mkdir(parents=True, exist_ok=True)
        moved = 0
        with session_scope() as session:
            svc = MediaLibraryService(session)
            for mid in media_ids:
                if svc.update_metadata(mid, folder=safe_folder) is not None:
                    moved += 1
        self.refresh()
        return moved

    def _on_move_to_folder_dialog(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(
                self,
                "Move to Folder",
                "Select one or more tracks in the table first.",
            )
            return
        folder_names = [p.name for p in self.list_library_folders()]
        chosen, ok = QInputDialog.getItem(
            self,
            "Move Track(s) to Music Folder",
            "Choose an existing Music Library folder or type a new folder name:",
            folder_names,
            0,
            True,
        )
        if not ok or not chosen.strip():
            return
        media_ids = [self._media_items[r].id for r in rows]
        moved = self.move_tracks_to_folder(media_ids, chosen.strip())
        QMessageBox.information(
            self,
            "Moved to Folder",
            f"Assigned {moved} track(s) to folder '{self._sanitize_folder_name(chosen)}'.",
        )

    def _on_send_to_production(self) -> None:
        self._run_library_autopilot(render_video=False)

    def _on_autopilot_produce_from_library(self) -> None:
        self._run_library_autopilot(render_video=True)

    def _run_library_autopilot(self, *, render_video: bool) -> None:
        from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService

        rows = self._selected_rows()
        if rows:
            selected_ids = [self._media_items[r].id for r in rows]
        else:
            selected_ids = [m.id for m in self._media_items]

        if not selected_ids:
            QMessageBox.information(
                self,
                "Music Library",
                "Upload or scan audio tracks first before sending to Production.",
            )
            return

        active_folder = self._active_target_folder_name()
        default_title = (
            f"{active_folder} — Full Mix Session"
            if len(selected_ids) > 1
            else str(self._media_items[0].metadata.get("title") or Path(self._media_items[0].path).stem)
        )
        try:
            with session_scope() as session:
                ap = ExpressAutopilotService(session)
                res = ap.run_autopilot(
                    project_name=default_title,
                    media_file_ids=selected_ids,
                    render_video=render_video,
                    export_short=render_video,
                )
            win = self.window()
            pages_dict = getattr(win, "pages", None)
            if isinstance(pages_dict, dict):
                for page in pages_dict.values():
                    if hasattr(page, "refresh"):
                        try:
                            page.refresh()
                        except Exception:
                            pass
            nav = getattr(win, "nav", None)
            if nav is not None:
                nav.setCurrentRow(3)  # Switch to Production workspace

            if render_video:
                QMessageBox.information(
                    self,
                    "🚀 1-Click Auto-Produce Complete!",
                    f"Built and rendered '{res.project_name}' ({res.track_count} tracks)!\n\n"
                    f"SEO Title: {res.seo_title}\n"
                    f"Output Folder: {res.output_dir}\n"
                    f"9:16 Vertical Short: {res.short_video_path or 'Ready'}",
                )
            else:
                QMessageBox.information(
                    self,
                    "Sent to Production & Auto-Configured",
                    f"Prepared project '{res.project_name}' with {res.track_count} track(s):\n"
                    "  ✓ Auto-Cue Silence Trim applied\n"
                    "  ✓ Smart Harmonic Sort (BPM + Camelot Key) applied\n"
                    "  ✓ YouTube SEO Chapters & 16:9 Thumbnail generated",
                )
        except Exception as exc:
            QMessageBox.critical(self, "Production Setup Failed", str(exc))

    def _on_reveal_selected(self) -> None:
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "Reveal File", "Select a track in the table first.")
            return
        file_path = Path(self._media_items[rows[0]].path)
        if not file_path.exists():
            QMessageBox.warning(self, "File Not Found", f"File does not exist:\n{file_path}")
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(file_path)])
            elif sys.platform.startswith("win"):
                subprocess.Popen(["explorer", f"/select,{file_path}"])
            else:
                subprocess.Popen(["xdg-open", str(file_path.parent)])
        except Exception as exc:
            QMessageBox.warning(self, "Reveal File", str(exc))

    # ------------------------------------------------------------------
    # Directory Scan & Table Refresh
    # ------------------------------------------------------------------
    def _on_browse_and_scan(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder:
            self.folder_input.setText(folder)
            self._on_scan()

    def _on_browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Music Folder")
        if folder:
            self.folder_input.setText(folder)

    def _on_scan(self) -> None:
        raw_path = self.folder_input.text().strip()
        if not raw_path:
            QMessageBox.warning(self, "Scan Folder", "Please select or enter a folder path first.")
            return
        folder = self._scanner.resolve_directory(Path(raw_path))
        if not folder.exists() or not folder.is_dir():
            QMessageBox.warning(self, "Scan Folder", f"Directory does not exist:\n{folder}")
            return

        try:
            with session_scope() as session:
                media_svc = MediaLibraryService(session)
                summary = self._scanner.scan_directory(
                    folder,
                    media_service=media_svc,
                    audio_only=True,
                )
            self.refresh()
            msg_lines = [
                f"Scanned {len(summary.scanned_files)} audio file(s) in:\n{folder}",
                f"Duplicate groups detected: {len(summary.duplicates_by_hash)}",
                f"Errors: {len(summary.errors)}",
            ]
            if summary.errors:
                first_err = next(iter(summary.errors.items()))
                msg_lines.append(f"\nFirst error:\n{first_err[0]}: {first_err[1]}")
            if not summary.scanned_files and summary.skipped_extensions:
                ext_list = ", ".join(f"{k} ({v})" for k, v in sorted(summary.skipped_extensions.items()))
                msg_lines.append(f"\nOther file types found in folder: {ext_list}")

            QMessageBox.information(self, "Scan Complete", "\n".join(msg_lines))
        except Exception as exc:
            QMessageBox.critical(self, "Scan Failed", str(exc))

    def _resolve_item_folder_label(self, item: MediaFile) -> str:
        tagged = str(item.metadata.get("folder") or "").strip()
        if tagged:
            return tagged
        p = Path(item.path)
        return p.parent.name or "Unassigned"

    def _rebuild_folder_filter_combo(self, all_items: list[MediaFile]) -> None:
        if not hasattr(self, "folder_filter_combo"):
            return
        current_data = self.folder_filter_combo.currentData()
        self.folder_filter_combo.blockSignals(True)
        self.folder_filter_combo.clear()
        self.folder_filter_combo.addItem("All Folders & Collections", "")

        seen_folders: set[str] = set()
        for folder_path in self.list_library_folders():
            seen_folders.add(folder_path.name)
            self.folder_filter_combo.addItem(f"📁 {folder_path.name}", folder_path.name)

        for item in all_items:
            folder_label = self._resolve_item_folder_label(item)
            if folder_label and folder_label not in seen_folders:
                seen_folders.add(folder_label)
                self.folder_filter_combo.addItem(f"📂 {folder_label}", folder_label)

        if current_data is not None:
            idx = self.folder_filter_combo.findData(current_data)
            if idx >= 0:
                self.folder_filter_combo.setCurrentIndex(idx)
        self.folder_filter_combo.blockSignals(False)

    def refresh(self) -> None:
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        try:
            with session_scope() as session:
                svc = MediaLibraryService(session)
                all_audio = svc.list_media(media_type=MediaType.AUDIO)
                items = svc.list_media(media_type=MediaType.AUDIO, query=query or None)
                duplicates = svc.find_duplicates()
        except Exception as exc:
            self.summary_label.setText(f"Database error: {exc}")
            return

        self._rebuild_folder_filter_combo(all_audio)

        # Apply folder filter if selected
        active_folder = (
            str(self.folder_filter_combo.currentData() or "").strip()
            if hasattr(self, "folder_filter_combo")
            else ""
        )
        if active_folder:
            items = [
                it for it in items if self._resolve_item_folder_label(it) == active_folder
            ]

        # Also support searching by folder name, BPM, or Camelot key
        if query and not items:
            needle = query.lower()
            for it in all_audio:
                folder_lbl = self._resolve_item_folder_label(it).lower()
                camelot = str(it.metadata.get("camelot_code") or "").lower()
                bpm_str = str(it.metadata.get("bpm") or "").lower()
                if needle in folder_lbl or needle in camelot or needle in bpm_str:
                    if not active_folder or self._resolve_item_folder_label(it) == active_folder:
                        items.append(it)

        self._media_items = items
        dup_hashes = set(duplicates.keys())
        folder_count = len(self.list_library_folders())
        self.summary_label.setText(
            f"{len(items)} audio track(s) shown ({len(all_audio)} total across {folder_count} library folder(s)) "
            f"· {len(dup_hashes)} duplicate hash group(s)"
        )

        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(len(all_audio) == 0 and not query)

        self.table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            title = str(item.metadata.get("title") or Path(item.path).stem)
            artist = str(item.metadata.get("artist") or "—")
            folder_label = self._resolve_item_folder_label(item)
            dur_str = self._format_duration(item.duration_ms)
            bpm = item.metadata.get("bpm")
            camelot = item.metadata.get("camelot_code")
            bpm_key_str = f"{bpm} BPM · {camelot}" if bpm and camelot else "—"
            ext = str(item.metadata.get("extension") or Path(item.path).suffix).upper()
            is_dup = bool(item.file_hash and item.file_hash in dup_hashes)
            status = "Duplicate" if is_dup else "Ready"

            self.table.setItem(row_idx, 0, QTableWidgetItem(title))
            self.table.setItem(row_idx, 1, QTableWidgetItem(artist))
            self.table.setItem(row_idx, 2, QTableWidgetItem(folder_label))
            self.table.setItem(row_idx, 3, QTableWidgetItem(dur_str))
            self.table.setItem(row_idx, 4, QTableWidgetItem(bpm_key_str))
            self.table.setItem(row_idx, 5, QTableWidgetItem(ext))
            self.table.setItem(row_idx, 6, QTableWidgetItem(status))
            self.table.setItem(row_idx, 7, QTableWidgetItem(item.path))

    @staticmethod
    def _format_duration(duration_ms: Optional[int]) -> str:
        if duration_ms is None or duration_ms <= 0:
            return "—"
        total_sec = int(duration_ms) // 1000
        mins = total_sec // 60
        secs = total_sec % 60
        return f"{mins:02d}:{secs:02d}"
