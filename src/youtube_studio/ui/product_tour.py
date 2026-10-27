"""Guided Product Tour banner that walks the user through all 7 workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class TourStop:
    nav_index: int
    title: str
    summary: str
    pro_tip: str


PRODUCT_TOUR_STOPS: tuple[TourStop, ...] = (
    TourStop(
        nav_index=0,
        title="1/7 · Dashboard — Command Center & Quick Actions",
        summary=(
            "Monitor active channels, indexed audio tracks, production projects, and FFmpeg/hardware readiness at a glance."
        ),
        pro_tip="Use the quick-launch buttons on the Dashboard to jump straight into scanning music or creating a mix project.",
    ),
    TourStop(
        nav_index=1,
        title="2/7 · Research Workspace — Topic Discovery & Hand-Off",
        summary=(
            "Search keywords offline or via YouTube Data API v3, group results into TF-IDF topic clusters, and track public watchlists."
        ),
        pro_tip="Select any promising topic and click 'Hand Off to Production →' to automatically create a project with pre-filled metadata.",
    ),
    TourStop(
        nav_index=2,
        title="3/7 · Music Library — Audio Scanner, BPM & Camelot Keys",
        summary=(
            "Recursively scan folders for WAV, MP3, FLAC, M4A, AAC, OGG, AIFF, and OPUS audio files. Extracts duration, BPM, Camelot key, and SHA-256 duplicates."
        ),
        pro_tip="Keep your stems and tracks organized in folders—scanning is incremental and flags exact file duplicates automatically.",
    ),
    TourStop(
        nav_index=3,
        title="4/7 · Production Studio — Harmonic Mixing, Visualizers & Shorts",
        summary=(
            "Build single-track or multi-track timelines with Auto-Cue Silence Trim, Smart Harmonic Sort, Bass-Swap EQ transitions, and audio-reactive visualizers."
        ),
        pro_tip="Enable 'Dynamic Now Playing Overlay' to generate both burned-in track titles and an external .srt subtitle file, or click 'Export 9:16 Short' for vertical highlights.",
    ),
    TourStop(
        nav_index=4,
        title="5/7 · Artwork & Local AI — Thumbnails & SEO Metadata",
        summary=(
            "Generate 3 title candidates, timestamped chapter descriptions, tags, and 16:9 / 9:16 thumbnails using local AI models or procedural brand palettes."
        ),
        pro_tip="Register optional .gguf language models here, or rely on the zero-dependency procedural fallback engine on any hardware.",
    ),
    TourStop(
        nav_index=5,
        title="6/7 · MCP Hub — Bidirectional Model Context Protocol",
        summary=(
            "Expose Studio's 10 tools, 4 studio:// resources, and 2 prompt templates to external AI clients, or connect external stdio/HTTP MCP servers."
        ),
        pro_tip="Use the interactive Tool Playground to test any MCP tool directly from the GUI, or copy the JSON-RPC config snippet for Claude Desktop / Cursor.",
    ),
    TourStop(
        nav_index=6,
        title="7/7 · Settings, Snapshots & Compliance Gate",
        summary=(
            "Manage your Credential Vault API key, create SHA-256 verified SQLite backup snapshots, and run the Pre-Release Compliance Review Gate."
        ),
        pro_tip="Before publishing a release package, click 'Audit Export Manifest…' to verify title/tag limits, chapter order, and media integrity.",
    ),
)


class ProductTourBanner(QFrame):
    """Interactive top banner guiding the user step-by-step through the product tour."""

    def __init__(
        self,
        *,
        on_select_nav: Callable[[int], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ProductTourBanner")
        self._on_select_nav = on_select_nav
        self._current_step = 0
        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        badge = QLabel("GUIDED PRODUCT TOUR")
        badge.setStyleSheet(
            "background-color: #4f46e5; color: #ffffff; padding: 3px 8px; "
            "border-radius: 4px; font-size: 11px; font-weight: bold;"
        )
        top_row.addWidget(badge)

        self.title_lbl = QLabel("")
        self.title_lbl.setObjectName("TourTitle")
        self.title_lbl.setFont(QFont("", 14, QFont.Weight.Bold))
        top_row.addWidget(self.title_lbl, stretch=1)

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.setToolTip("Go to the previous workspace in the Product Tour.")
        self.prev_btn.clicked.connect(self.previous_step)
        top_row.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setObjectName("PrimaryButton")
        self.next_btn.setToolTip("Advance to the next workspace in the Product Tour.")
        self.next_btn.clicked.connect(self.next_step)
        top_row.addWidget(self.next_btn)

        self.close_btn = QPushButton("End Tour ✕")
        self.close_btn.setToolTip("Close the guided Product Tour banner.")
        self.close_btn.clicked.connect(self.stop_tour)
        top_row.addWidget(self.close_btn)

        root.addLayout(top_row)

        self.summary_lbl = QLabel("")
        self.summary_lbl.setObjectName("TourSummary")
        self.summary_lbl.setWordWrap(True)
        root.addWidget(self.summary_lbl)

        self.tip_lbl = QLabel("")
        self.tip_lbl.setObjectName("TourTip")
        self.tip_lbl.setWordWrap(True)
        self.tip_lbl.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.tip_lbl)

    @property
    def current_step(self) -> int:
        return self._current_step

    def start_tour(self, start_index: int = 0) -> None:
        self._current_step = max(0, min(start_index, len(PRODUCT_TOUR_STOPS) - 1))
        self.show()
        self._apply_step()

    def stop_tour(self) -> None:
        self.hide()

    def next_step(self) -> None:
        if self._current_step < len(PRODUCT_TOUR_STOPS) - 1:
            self._current_step += 1
            self._apply_step()
        else:
            self.stop_tour()

    def previous_step(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._apply_step()

    def _apply_step(self) -> None:
        stop = PRODUCT_TOUR_STOPS[self._current_step]
        self.title_lbl.setText(stop.title)
        self.summary_lbl.setText(stop.summary)
        self.tip_lbl.setText(f"💡 <b>Pro Tip:</b> {stop.pro_tip}")
        self.prev_btn.setEnabled(self._current_step > 0)
        if self._current_step == len(PRODUCT_TOUR_STOPS) - 1:
            self.next_btn.setText("Finish Tour ✓")
        else:
            self.next_btn.setText("Next →")
        self._on_select_nav(stop.nav_index)
