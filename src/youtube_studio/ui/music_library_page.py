"""Music Library UI page – scan directories, inspect BPM & Camelot key, search tracks, and detect duplicates."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.domain.models.media import MediaType
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget


class MusicLibraryPage(QWidget):
    """Interactive music library browser with BPM/Camelot key analysis & duplicate detection."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scanner = MediaScanner()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Music Library & Harmonic Analyzer")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        layout.addWidget(heading)

        subtitle = QLabel(
            "Index local audio folders, inspect tempo (BPM) & Camelot keys (1A–12B), and identify exact file duplicates."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        layout.addWidget(subtitle)

        # Toolbar: Scan folder + Search
        toolbar = QHBoxLayout()
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select or enter a music folder path to scan…")
        self.folder_input.setToolTip(
            "Path to a local directory containing WAV, MP3, FLAC, M4A, AAC, or OGG files."
        )
        toolbar.addWidget(self.folder_input, stretch=2)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.setToolTip("Open a folder picker dialog to choose your music directory.")
        self.browse_btn.clicked.connect(self._on_browse)
        toolbar.addWidget(self.browse_btn)

        self.scan_btn = QPushButton("Scan Folder")
        self.scan_btn.setObjectName("PrimaryButton")
        self.scan_btn.setToolTip(
            "Recursively scan the selected directory, compute waveform fingerprints, "
            "estimate BPM & Camelot keys, and index tracks in SQLite."
        )
        self.scan_btn.clicked.connect(self._on_scan)
        toolbar.addWidget(self.scan_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by title, artist, or path…")
        self.search_input.setToolTip("Type to filter indexed audio tracks in real time.")
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self.search_input, stretch=1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Reload the music library table from the local database.")
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)

        layout.addLayout(toolbar)

        self.summary_label = QLabel("0 tracks indexed")
        self.summary_label.setStyleSheet("color: #94a3b8; font-weight: 500;")
        layout.addWidget(self.summary_label)

        # Empty State Guide (visible when library has 0 tracks)
        self.empty_state = EmptyStateWidget(
            title="Your Music Library is Empty",
            description=(
                "No audio tracks have been indexed yet. Point the scanner at any folder containing your tracks or stems "
                "to populate the library."
            ),
            tips=[
                "<b>Supported Formats:</b> WAV, MP3, FLAC, M4A, AAC, and OGG are indexed recursively.",
                "<b>Harmonic & Tempo Analysis:</b> Every track is automatically analyzed for BPM, Camelot key (1A–12B), and intro/outro silence cues.",
                "<b>Duplicate Protection:</b> SHA-256 content hashing flags duplicate audio files across folders.",
            ],
            action_label="Browse & Scan Music Folder…",
            action_tooltip="Choose a local music folder and scan its audio tracks immediately.",
            on_action=self._on_browse_and_scan,
        )
        layout.addWidget(self.empty_state)

        # Track table
        self.table = QTableWidget(0, 7)
        self.table.setAlternatingRowColors(True)
        self.table.setToolTip(
            "Indexed audio tracks with duration, estimated BPM, Camelot wheel key, and duplicate status."
        )
        self.table.setHorizontalHeaderLabels(
            ["Title", "Artist", "Duration", "BPM / Key (Camelot)", "Format", "Status", "Path"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, stretch=1)

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
        folder = Path(raw_path).expanduser()
        if not folder.exists() or not folder.is_dir():
            QMessageBox.warning(self, "Scan Folder", f"Directory does not exist:\n{folder}")
            return

        try:
            with session_scope() as session:
                media_svc = MediaLibraryService(session)
                summary = self._scanner.scan_directory(folder, media_service=media_svc)
            self.refresh()
            QMessageBox.information(
                self,
                "Scan Complete",
                f"Scanned {len(summary.scanned_files)} audio file(s).\n"
                f"Duplicate groups detected: {len(summary.duplicates_by_hash)}\n"
                f"Errors: {len(summary.errors)}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Scan Failed", str(exc))

    def refresh(self) -> None:
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        try:
            with session_scope() as session:
                svc = MediaLibraryService(session)
                items = svc.list_media(media_type=MediaType.AUDIO, query=query or None)
                duplicates = svc.find_duplicates()
        except Exception as exc:
            self.summary_label.setText(f"Database error: {exc}")
            return

        dup_hashes = set(duplicates.keys())
        self.summary_label.setText(
            f"{len(items)} audio track(s) shown · {len(dup_hashes)} duplicate hash group(s)"
        )

        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(len(items) == 0 and not query)

        self.table.setRowCount(len(items))
        for row_idx, item in enumerate(items):
            title = str(item.metadata.get("title") or Path(item.path).stem)
            artist = str(item.metadata.get("artist") or "—")
            dur_str = self._format_duration(item.duration_ms)
            bpm = item.metadata.get("bpm")
            camelot = item.metadata.get("camelot_code")
            bpm_key_str = f"{bpm} BPM · {camelot}" if bpm and camelot else "—"
            ext = str(item.metadata.get("extension") or Path(item.path).suffix).upper()
            is_dup = bool(item.file_hash and item.file_hash in dup_hashes)
            status = "Duplicate" if is_dup else "Ready"

            self.table.setItem(row_idx, 0, QTableWidgetItem(title))
            self.table.setItem(row_idx, 1, QTableWidgetItem(artist))
            self.table.setItem(row_idx, 2, QTableWidgetItem(dur_str))
            self.table.setItem(row_idx, 3, QTableWidgetItem(bpm_key_str))
            self.table.setItem(row_idx, 4, QTableWidgetItem(ext))
            self.table.setItem(row_idx, 5, QTableWidgetItem(status))
            self.table.setItem(row_idx, 6, QTableWidgetItem(item.path))

    @staticmethod
    def _format_duration(duration_ms: Optional[int]) -> str:
        if duration_ms is None or duration_ms <= 0:
            return "—"
        total_sec = duration_ms // 1000
        mins = total_sec // 60
        secs = total_sec % 60
        return f"{mins:02d}:{secs:02d}"
