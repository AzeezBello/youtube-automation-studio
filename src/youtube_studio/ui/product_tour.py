"""Guided Product Tour banner that walks the user through all 9 studio workspaces."""

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
        title="1/9 · Dashboard — Command Center, New Project Hero & More Tools",
        summary=(
            "Start a new project in 1 click, launch Video Studio or Design Studio, access AI tools, and view all saved projects."
        ),
        pro_tip="Click the cyan '+ New project' banner or any tool tile under 'More tools' to jump straight into a workflow.",
    ),
    TourStop(
        nav_index=1,
        title="2/9 · Research Workspace — YouTube URL Briefs & Topic Discovery",
        summary=(
            "Paste any YouTube video URL to import public metadata and chapters into a Research Brief, or search keywords and cluster topics."
        ),
        pro_tip="Click '🚀 1-Click Auto-Pilot from URL' to turn any reference video URL into a complete studio project automatically.",
    ),
    TourStop(
        nav_index=2,
        title="3/9 · Music Library — Audio Scanner, BPM & Camelot Keys",
        summary=(
            "Recursively scan folders for WAV, MP3, FLAC, M4A, AAC, OGG, AIFF, and OPUS audio files. Extracts duration, BPM, Camelot key, and SHA-256 duplicates."
        ),
        pro_tip="Keep your stems and tracks organized in folders—scanning is incremental and flags exact file duplicates automatically.",
    ),
    TourStop(
        nav_index=3,
        title="4/9 · Script & Voiceover Studio — Hook → Outline → Full Script + Local TTS",
        summary=(
            "Draft structured scripts in 3 steps (Hook, Timestamped Outline, Full Narration), upload .txt/.md/.srt files, and synthesize Male/Female voiceovers."
        ),
        pro_tip="Use the Voice Library table to audition Male or Female presets with custom speed (0.50x–2.00x) and append voiceovers directly to your timeline.",
    ),
    TourStop(
        nav_index=4,
        title="5/9 · Production Studio — 1-Click Auto-Pilot, Harmonic Mixing & Shorts",
        summary=(
            "Build single-track or multi-track timelines with Auto-Cue Silence Trim, Smart Harmonic Sort, Bass-Swap EQ transitions, and audio-reactive visualizers."
        ),
        pro_tip="Set a custom Output Name and Niche Style Preset, or click '🚀 1-Click Auto-Produce Full Video + Short' for hands-free production.",
    ),
    TourStop(
        nav_index=5,
        title="6/9 · Timeline Editor — 4-Pane Pro Video Stage, Inspector & EditPilot",
        summary=(
            "Browse Media/Audio/Text/Effects/Transitions/Filters on the left, preview on the 16:9 or 9:16 Player stage, inspect clip trims on the right, and scrub the multi-track timeline."
        ),
        pro_tip="Click '✦ EditPilot' in the timeline bar to auto-load and harmonic-sort tracks, or click '↗ Export' to save .fcpxml, .edl, and .csv clip lists.",
    ),
    TourStop(
        nav_index=6,
        title="7/9 · Artwork & SEO — Explainable Title Scorer, Style Lock & Thumbnails",
        summary=(
            "Generate 5 ranked title candidates with transparent criteria (Length, Keywords, Tone), chapter descriptions, and 16:9 / 9:16 thumbnails with Reference Image Style Lock."
        ),
        pro_tip="Lock your channel's color palette and backdrop blend to any reference image using the '🔒 Style Lock' checkbox.",
    ),
    TourStop(
        nav_index=7,
        title="8/9 · MCP Hub — Bidirectional Model Context Protocol",
        summary=(
            "Expose Studio's 10 tools, 4 studio:// resources, and 2 prompt templates to external AI clients, or connect external stdio/HTTP MCP servers."
        ),
        pro_tip="Use the interactive Tool Playground to test any MCP tool directly from the GUI, or copy the JSON-RPC config snippet for Claude Desktop / Cursor.",
    ),
    TourStop(
        nav_index=8,
        title="9/9 · Settings, Snapshots & Compliance Gate",
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
