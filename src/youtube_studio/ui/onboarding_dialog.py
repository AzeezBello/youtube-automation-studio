"""Step-by-step first-run Onboarding Flow wizard for YouTube Automation Studio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.config import HardwareProbe, get_settings
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.services import ChannelService
from youtube_studio.media.thumbnail import PALETTES
from youtube_studio.security.vault import CredentialVault
from youtube_studio.storage import session_scope


class OnboardingDialog(QDialog):
    """Multi-step onboarding flow introducing the app and guiding initial setup."""

    TOTAL_STEPS = 4

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_start_tour: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome — YouTube Automation Studio Setup")
        self.resize(680, 480)
        self._on_start_tour = on_start_tour
        self._on_completed = on_completed
        self._vault = CredentialVault()
        self._build_ui()
        self._update_step_ui()

    @staticmethod
    def state_file_path() -> Path:
        return get_settings().resolved_data_dir() / "onboarding_state.json"

    @classmethod
    def is_onboarding_completed(cls) -> bool:
        path = cls.state_file_path()
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return bool(data.get("completed", False))
        except Exception:
            return False

    @classmethod
    def mark_onboarding_completed(cls, completed: bool = True) -> None:
        path = cls.state_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"completed": completed}, indent=2), encoding="utf-8")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Step indicator header
        top_row = QHBoxLayout()
        self.step_badge = QLabel("Step 1 of 4")
        self.step_badge.setStyleSheet(
            "background-color: #312e81; color: #c7d2fe; padding: 4px 10px; "
            "border-radius: 12px; font-weight: bold;"
        )
        top_row.addWidget(self.step_badge)
        top_row.addStretch()

        self.skip_btn = QPushButton("Skip Intro")
        self.skip_btn.setToolTip("Skip the onboarding wizard and go directly to the studio.")
        self.skip_btn.clicked.connect(self._on_finish)
        top_row.addWidget(self.skip_btn)
        root.addLayout(top_row)

        # Stacked steps
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_step_welcome())
        self.stack.addWidget(self._build_step_channel())
        self.stack.addWidget(self._build_step_hardware_and_api())
        self.stack.addWidget(self._build_step_ready())
        root.addWidget(self.stack, stretch=1)

        # Bottom navigation bar
        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("← Back")
        self.prev_btn.setToolTip("Return to the previous onboarding step.")
        self.prev_btn.clicked.connect(self._on_prev)
        nav_row.addWidget(self.prev_btn)

        nav_row.addStretch()

        self.next_btn = QPushButton("Next Step →")
        self.next_btn.setObjectName("PrimaryButton")
        self.next_btn.setToolTip("Proceed to the next onboarding step.")
        self.next_btn.clicked.connect(self._on_next)
        nav_row.addWidget(self.next_btn)

        root.addLayout(nav_row)

    def _build_step_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Welcome to YouTube Automation Studio")
        title.setFont(QFont("", 20, QFont.Weight.Bold))
        layout.addWidget(title)

        sub = QLabel(
            "Your self-contained, local-first desktop studio for multi-channel YouTube research, "
            "harmonic audio mixing, reactive video production, MCP connectors, and AI metadata packaging."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet("font-size: 14px;")
        layout.addWidget(sub)

        group = QGroupBox("How the 6-Stage Creator Pipeline Works")
        g_layout = QVBoxLayout(group)
        steps_html = (
            "<ol style='line-height: 1.55;'>"
            "<li><b>Research Workspace:</b> Discover high-demand topics, cluster keywords locally, "
            "and hand off saved ideas into production projects.</li>"
            "<li><b>Music Library:</b> Scan your local audio folders (WAV, MP3, FLAC, M4A, AAC, OGG) "
            "with automatic BPM, Camelot key, waveform, and duplicate detection.</li>"
            "<li><b>Production Studio:</b> Sequence tracks with smart harmonic ordering, auto-silence "
            "cue trimming, bass-swap EQ crossfades, audio visualizers, and 9:16 Short highlights.</li>"
            "<li><b>Artwork & Local AI:</b> Generate 16:9 & 9:16 thumbnails and SEO titles/chapters/tags "
            "using local models or zero-dependency procedural templates.</li>"
            "<li><b>MCP Hub (Browser Login):</b> Connect preconfigured vidIQ, TubeBuddy, Suno, ElevenLabs & more "
            "via Connection URL + Browser Redirect (no API keys required).</li>"
            "<li><b>100% Manual Publishing Control:</b> Audit your export manifest through the Compliance "
            "Review Gate and upload on your own schedule.</li>"
            "</ol>"
        )
        lbl = QLabel(steps_html)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        g_layout.addWidget(lbl)
        layout.addWidget(group)
        layout.addStretch()
        return page

    def _build_step_channel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Create Your First Channel Profile")
        title.setFont(QFont("", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        sub = QLabel(
            "Each channel profile stores its own visual palette, default resolution, and tag templates "
            "so you can manage multiple brands from one studio."
        )
        sub.setWordWrap(True)
        layout.addWidget(sub)

        form_group = QGroupBox("Channel Brand Profile")
        form = QFormLayout(form_group)

        self.channel_name_input = QLineEdit()
        self.channel_name_input.setPlaceholderText("e.g. Deep Dub Collective or Lo-Fi Study Beats")
        self.channel_name_input.setToolTip("Enter a display name for your YouTube channel profile.")
        form.addRow("Channel Name:", self.channel_name_input)

        self.channel_palette_combo = QComboBox()
        self.channel_palette_combo.addItems(list(PALETTES.keys()))
        self.channel_palette_combo.setToolTip(
            "Select the default color palette used when rendering thumbnails and background artwork."
        )
        form.addRow("Default Artwork Palette:", self.channel_palette_combo)

        self.channel_tags_input = QLineEdit()
        self.channel_tags_input.setPlaceholderText("e.g. deep dubstep, 140 bpm, bass mix, full session")
        self.channel_tags_input.setToolTip(
            "Comma-separated tags automatically included in new metadata drafts for this channel."
        )
        form.addRow("Default Genre Tags:", self.channel_tags_input)

        self.create_channel_btn = QPushButton("+ Save Channel Profile")
        self.create_channel_btn.setObjectName("AccentButton")
        self.create_channel_btn.setToolTip("Create and save this channel profile to the local SQLite database.")
        self.create_channel_btn.clicked.connect(self._on_create_channel_clicked)
        form.addRow(self.create_channel_btn)

        self.channel_status_lbl = QLabel("")
        self.channel_status_lbl.setStyleSheet("color: #10b981; font-weight: 600;")
        form.addRow(self.channel_status_lbl)

        layout.addWidget(form_group)
        layout.addStretch()
        return page

    def _build_step_hardware_and_api(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("System Hardware & MCP / Research Setup")
        title.setFont(QFont("", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        hw_group = QGroupBox("Detected Local Hardware Profile")
        hw_layout = QVBoxLayout(hw_group)
        try:
            hw = HardwareProbe(get_settings().resolved_data_dir()).run()
            hw_text = (
                f"<b>OS / Arch:</b> {hw.os_name} ({hw.architecture})<br>"
                f"<b>CPU & Memory:</b> {hw.cpu_count} cores · {hw.total_ram_gb:.1f} GB RAM · "
                f"{hw.free_disk_gb:.1f} GB free disk<br>"
                f"<b>FFmpeg HW Acceleration:</b> {'Available' if hw.has_ffmpeg_hwaccel else 'Software / PCM Fallback'}<br>"
                f"<b>Recommended Profile:</b> <span style='color:#6366f1'>{hw.recommended_profile.value}</span>"
            )
        except Exception as exc:
            hw_text = f"Hardware probe summary: {exc}"
        hw_lbl = QLabel(hw_text)
        hw_lbl.setWordWrap(True)
        hw_layout.addWidget(hw_lbl)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Folder:"))
        self.onboarding_output_input = QLineEdit()
        self.onboarding_output_input.setText(str(get_settings().resolved_output_dir()))
        self.onboarding_output_input.setToolTip(
            "Default output folder where rendered videos, mixes, Shorts, and release packages are saved."
        )
        out_row.addWidget(self.onboarding_output_input, stretch=1)

        browse_out_btn = QPushButton("📁 Browse…")
        browse_out_btn.setToolTip("Select where your rendered videos and release packages should be saved.")
        browse_out_btn.clicked.connect(self._on_browse_onboarding_output)
        out_row.addWidget(browse_out_btn)
        hw_layout.addLayout(out_row)

        layout.addWidget(hw_group)

        api_group = QGroupBox("MCP Browser Redirects & Optional YouTube Data API v3 Key")
        api_layout = QVBoxLayout(api_group)
        api_desc = QLabel(
            "Preconfigured MCP connectors (vidIQ, TubeBuddy, Suno, ElevenLabs, etc.) use Browser Login Redirects "
            "in the MCP Hub with no API keys required. Optionally, you can also save a YouTube Data API v3 key below."
        )
        api_desc.setWordWrap(True)
        api_desc.setStyleSheet("color: #64748b;")
        api_layout.addWidget(api_desc)

        api_row = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Paste YouTube Data API v3 key (optional)…")
        self.api_key_input.setToolTip("Stored securely in your OS Keychain / Credential Vault.")
        api_row.addWidget(self.api_key_input, stretch=1)

        save_key_btn = QPushButton("Save Key")
        save_key_btn.setToolTip("Save the API key into the encrypted Credential Vault.")
        save_key_btn.clicked.connect(self._on_save_api_key)
        api_row.addWidget(save_key_btn)
        api_layout.addLayout(api_row)

        self.api_status_lbl = QLabel("")
        self.api_status_lbl.setStyleSheet("color: #10b981; font-weight: 600;")
        api_layout.addWidget(self.api_status_lbl)

        layout.addWidget(api_group)
        layout.addStretch()
        return page

    def _build_step_ready(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("You're Ready to Create!")
        title.setFont(QFont("", 20, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel(
            "Your local database and workspace directories are initialized. "
            "Would you like to take a quick interactive Product Tour of the 7 studio workspaces?"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px;")
        layout.addWidget(desc)

        tour_box = QGroupBox("Guided Product Tour & Next Steps")
        t_layout = QVBoxLayout(tour_box)

        self.chk_launch_tour = QCheckBox("Start the interactive 7-step Guided Product Tour now (Recommended)")
        self.chk_launch_tour.setChecked(True)
        self.chk_launch_tour.setToolTip(
            "Walks you through Dashboard, Research, Music Library, Production, Artwork, MCP Hub, and Settings."
        )
        t_layout.addWidget(self.chk_launch_tour)

        tips = QLabel(
            "• Hover over any button, dropdown, or setting to see helpful <b>Tooltips</b>.<br>"
            "• Blank tables automatically show an <b>Empty State Guide</b> with tips and quick actions.<br>"
            "• Switch between <b>Dark Mode</b> and <b>Light Mode</b> anytime from the top header bar."
        )
        tips.setWordWrap(True)
        tips.setStyleSheet("color: #64748b; margin-top: 6px;")
        t_layout.addWidget(tips)

        layout.addWidget(tour_box)
        layout.addStretch()
        return page

    def _on_create_channel_clicked(self) -> None:
        name = self.channel_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Channel Name Required", "Please enter a channel name first.")
            return
        palette = self.channel_palette_combo.currentText()
        tags = [t.strip() for t in self.channel_tags_input.text().split(",") if t.strip()]
        brand = ChannelBrandConfig(
            visual_style=palette,
            default_tags=tags or ["music mix", "full session"],
            thumbnail_style={"palette": palette, "motif": "vinyl_and_sound_system"},
        )
        try:
            with session_scope() as session:
                ch = ChannelService(session).create(name, brand=brand)
            self.channel_status_lbl.setText(f"✓ Created channel '{ch.name}' ({palette})")
            self.channel_name_input.clear()
        except Exception as exc:
            QMessageBox.critical(self, "Could Not Create Channel", str(exc))

    def _on_browse_onboarding_output(self) -> None:
        current = self.onboarding_output_input.text().strip() or str(get_settings().resolved_output_dir())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Default Output Folder for Videos & Packages",
            current,
        )
        if not chosen:
            return
        saved = get_settings().set_output_dir(chosen)
        self.onboarding_output_input.setText(str(saved))

    def _on_save_api_key(self) -> None:
        key = self.api_key_input.text().strip()
        if not key:
            return
        self._vault.set_secret("youtube_data_api_key", key)
        self.api_key_input.clear()
        self.api_status_lbl.setText("✓ API key saved to Credential Vault.")

    def _on_prev(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            self._update_step_ui()

    def _on_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 1 and self.channel_name_input.text().strip():
            # Auto-save channel if user typed a name and clicked Next directly
            self._on_create_channel_clicked()
        if idx == 2 and hasattr(self, "onboarding_output_input"):
            raw_out = self.onboarding_output_input.text().strip()
            if raw_out:
                try:
                    get_settings().set_output_dir(raw_out)
                except Exception:
                    pass
        if idx < self.TOTAL_STEPS - 1:
            self.stack.setCurrentIndex(idx + 1)
            self._update_step_ui()
        else:
            self._on_finish()

    def _on_finish(self) -> None:
        self.mark_onboarding_completed(True)
        launch_tour = self.chk_launch_tour.isChecked()
        if self._on_completed:
            self._on_completed()
        self.accept()
        if launch_tour and self._on_start_tour:
            self._on_start_tour()

    def _update_step_ui(self) -> None:
        idx = self.stack.currentIndex()
        self.step_badge.setText(f"Step {idx + 1} of {self.TOTAL_STEPS}")
        self.prev_btn.setEnabled(idx > 0)
        if idx == self.TOTAL_STEPS - 1:
            self.next_btn.setText("Finish & Open Studio ✓")
        else:
            self.next_btn.setText("Next Step →")
