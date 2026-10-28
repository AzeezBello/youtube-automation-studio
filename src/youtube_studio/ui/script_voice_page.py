"""Dedicated Script, Narration & Local AI Voiceover (TTS) Studio page."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.ai import LlamaCppTextAdapter, MetadataGenerator
from youtube_studio.config import HardwareProbe, get_settings
from youtube_studio.domain.models.channel import (
    NICHE_STYLE_PRESETS,
    VOICE_LIBRARY_PRESETS,
    apply_niche_preset_to_brand_config,
)
from youtube_studio.domain.models.media import MediaType
from youtube_studio.domain.models.project import ProjectType, TransitionConfig, TransitionType
from youtube_studio.domain.services import (
    ChannelService,
    MediaLibraryService,
    ModelRegistryService,
    ProjectService,
)
from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.tts_service import LocalTTSService
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget


class ScriptVoicePage(QWidget):
    """Dedicated workspace for Structured Script Building (Hook → Outline → Full Script) & Local AI Voiceover (TTS)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel_ids: list[str] = []
        self._project_ids: list[str] = []
        self._model_paths: list[Optional[str]] = []
        self._voiceover_paths: list[Path] = []
        self._hw_report = HardwareProbe().run()

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.9)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.durationChanged.connect(self._on_player_duration_changed)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = QLabel("✍️ Script, Narration & AI Voiceover Studio")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        subtitle = QLabel(
            "Draft structured scripts (1. Hook → 2. Timestamped Outline → 3. Full Narration), upload .txt/.md/.srt scripts, "
            "and synthesize local Male/Female voiceovers with adjustable speed."
        )
        subtitle.setStyleSheet("color: #94a3b8;")
        root.addWidget(subtitle)

        # Top Selector Bar
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setToolTip("Select the active YouTube channel profile.")
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        top_row.addWidget(self.channel_combo, stretch=1)

        top_row.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Select the production project to attach scripts and voiceovers.")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_row.addWidget(self.project_combo, stretch=1)

        top_row.addWidget(QLabel("Niche Style:"))
        self.niche_preset_combo = QComboBox()
        for preset in NICHE_STYLE_PRESETS.values():
            self.niche_preset_combo.addItem(f"🎨 {preset.label}", preset.key)
        self.niche_preset_combo.setToolTip("Apply a Niche / Style Preset to set script tone and target video duration.")
        self.niche_preset_combo.currentIndexChanged.connect(self._on_niche_preset_changed)
        top_row.addWidget(self.niche_preset_combo)

        top_row.addWidget(QLabel("Target Length:"))
        self.target_length_spin = QSpinBox()
        self.target_length_spin.setRange(1, 240)
        self.target_length_spin.setValue(15)
        self.target_length_spin.setSuffix(" min")
        self.target_length_spin.setToolTip("Target video duration in minutes (estimates script word count at ~140 words/min).")
        self.target_length_spin.valueChanged.connect(lambda _: self._update_script_metrics())
        top_row.addWidget(self.target_length_spin)

        top_row.addWidget(QLabel("Local LM:"))
        self.model_combo = QComboBox()
        self.model_combo.setToolTip("Choose a local GGUF language model or the zero-dependency Template Engine.")
        top_row.addWidget(self.model_combo)
        root.addLayout(top_row)

        # Empty State Widget
        self.empty_state = EmptyStateWidget(
            title="Build Your Narration Script & Synthesize Local Voiceover",
            description=(
                "Use the 3-step Script Builder (1. Hook → 2. Outline → 3. Full Script), paste/upload a script file, "
                "or synthesize a Male/Female voiceover track directly into your project."
            ),
            tips=[
                "<b>Step 1 → Step 2 → Step 3:</b> Generate an attention-grabbing 15s Hook, build a timestamped chapter Outline, and expand into a full script.",
                "<b>Script Upload (.txt / .md / .srt):</b> Automatically extracts 00:00 chapter timestamps and syncs them to your project description.",
                "<b>Local-First Voice Library:</b> Choose Male or Female voice presets with speed control (0.50x–2.00x) and zero paid API requirement.",
            ],
            action_label="✍️ Draft Full Script (Steps 1→3)",
            action_tooltip="Generate Hook, Timestamped Outline, and Full Narration Script for the current project.",
            on_action=self._on_generate_full_script,
            secondary_label="🔊 Synthesize Voiceover (Local TTS)",
            secondary_tooltip="Synthesize the script into a local WAV voiceover using the selected voice preset.",
            on_secondary=lambda: self._on_synthesize_voiceover(add_to_timeline=False),
        )
        root.addWidget(self.empty_state)

        # Main Two-Column Body
        body = QHBoxLayout()

        # Left Column: Structured 3-Step Script Builder & Upload
        script_group = QGroupBox("Structured Script Builder (Hook → Outline → Full Narration) & File Upload")
        script_layout = QVBoxLayout(script_group)

        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Topic / Episode Headline:"))
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("e.g. Roots Reggae & Dubplates — Studio Session Story…")
        self.topic_input.setToolTip("Topic or episode title used to guide Hook, Outline, and Full Script generation.")
        topic_row.addWidget(self.topic_input, stretch=1)

        self.btn_upload_script = QPushButton("📄 Upload Script (.txt/.md/.srt)…")
        self.btn_upload_script.setToolTip("Load a script file from disk and extract 00:00 chapter timestamps.")
        self.btn_upload_script.clicked.connect(self._on_upload_script_file)
        topic_row.addWidget(self.btn_upload_script)
        script_layout.addLayout(topic_row)

        # Step 1: Hook
        step1_hdr = QHBoxLayout()
        step1_hdr.addWidget(QLabel("<b>Step 1 — Opening Hook (00:00–00:15):</b>"))
        step1_hdr.addStretch(1)
        self.btn_gen_hook = QPushButton("⚡ 1. Generate Hook")
        self.btn_gen_hook.setToolTip("Generate a 15-second opening hook tailored to your channel's tone.")
        self.btn_gen_hook.clicked.connect(self._on_generate_hook)
        step1_hdr.addWidget(self.btn_gen_hook)
        script_layout.addLayout(step1_hdr)

        self.hook_edit = QPlainTextEdit()
        self.hook_edit.setPlaceholderText("00:00 Opening hook to capture listener/viewer attention in the first 15 seconds…")
        self.hook_edit.setMaximumHeight(68)
        self.hook_edit.textChanged.connect(self._update_script_metrics)
        script_layout.addWidget(self.hook_edit)

        # Step 2: Outline
        step2_hdr = QHBoxLayout()
        step2_hdr.addWidget(QLabel("<b>Step 2 — Timestamped Section Outline:</b>"))
        step2_hdr.addStretch(1)
        self.btn_gen_outline = QPushButton("📋 2. Build Outline from Chapters")
        self.btn_gen_outline.setToolTip("Build a structured timestamped section outline from your project chapters.")
        self.btn_gen_outline.clicked.connect(self._on_generate_outline)
        step2_hdr.addWidget(self.btn_gen_outline)
        script_layout.addLayout(step2_hdr)

        self.outline_edit = QPlainTextEdit()
        self.outline_edit.setPlaceholderText("00:00 Intro & Hook\n02:30 Section 1 — Track / Story Breakdown…")
        self.outline_edit.setMaximumHeight(92)
        self.outline_edit.textChanged.connect(self._update_script_metrics)
        script_layout.addWidget(self.outline_edit)

        # Step 3: Full Script
        step3_hdr = QHBoxLayout()
        step3_hdr.addWidget(QLabel("<b>Step 3 — Full Narration / Host Script:</b>"))
        step3_hdr.addStretch(1)
        self.btn_gen_full = QPushButton("✍️ 3. Draft Full Script")
        self.btn_gen_full.setObjectName("PrimaryButton")
        self.btn_gen_full.setToolTip("Combine Hook + Outline + Project Chapters into a full narration script.")
        self.btn_gen_full.clicked.connect(self._on_generate_full_script)
        step3_hdr.addWidget(self.btn_gen_full)
        script_layout.addLayout(step3_hdr)

        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText(
            "Paste, upload, or generate your full narration script here. Include 00:00 timestamps to auto-sync chapters…"
        )
        self.script_edit.textChanged.connect(self._update_script_metrics)
        script_layout.addWidget(self.script_edit, stretch=1)

        # Metrics + Save Row
        footer_row = QHBoxLayout()
        self.metrics_label = QLabel("0 words · Est. Speaking Time: 00:00 · 0 Chapters · Target: ~2100 words (15 min)")
        self.metrics_label.setStyleSheet(
            "color: #22d3ee; background: rgba(6, 182, 212, 0.10); border: 1px solid rgba(6, 182, 212, 0.30); "
            "border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 600;"
        )
        footer_row.addWidget(self.metrics_label, stretch=1)

        self.btn_save_script = QPushButton("💾 Save Script & Sync Chapters to Project")
        self.btn_save_script.setObjectName("AccentButton")
        self.btn_save_script.setToolTip("Save this script into the project's Metadata Draft and sync extracted 00:00 chapters.")
        self.btn_save_script.clicked.connect(self._on_save_script_to_project)
        footer_row.addWidget(self.btn_save_script)
        script_layout.addLayout(footer_row)

        body.addWidget(script_group, stretch=3)

        # Right Column: Voice Library (Male/Female, Speed) + TTS Synthesizer + Preview Player
        voice_group = QGroupBox("🎙 Voice Library (Male/Female, Speed) & Local AI Voiceover Studio")
        voice_layout = QVBoxLayout(voice_group)

        voice_form = QFormLayout()
        self.voice_preset_combo = QComboBox()
        for vp in VOICE_LIBRARY_PRESETS.values():
            self.voice_preset_combo.addItem(
                f"🎙 {vp.label} [{vp.gender.title()} · {vp.base_wpm} WPM]",
                vp.key,
            )
        self.voice_preset_combo.setToolTip("Choose a local Male or Female voice preset (persisted per channel).")
        self.voice_preset_combo.currentIndexChanged.connect(self._on_voice_preset_selected)
        voice_form.addRow("Voice Preset:", self.voice_preset_combo)

        speed_row = QHBoxLayout()
        self.voice_speed_spin = QDoubleSpinBox()
        self.voice_speed_spin.setRange(0.50, 2.00)
        self.voice_speed_spin.setSingleStep(0.05)
        self.voice_speed_spin.setValue(1.00)
        self.voice_speed_spin.setSuffix("x")
        self.voice_speed_spin.setToolTip("Speaking speed multiplier (0.50x slow to 2.00x fast).")
        self.voice_speed_spin.valueChanged.connect(lambda _: self._update_script_metrics())
        speed_row.addWidget(self.voice_speed_spin)

        self.lbl_voice_details = QLabel("Gender: Male · Base Rate: 165 WPM · Local Engine Ready")
        self.lbl_voice_details.setStyleSheet("color: #94a3b8; font-size: 11px;")
        speed_row.addWidget(self.lbl_voice_details, stretch=1)
        voice_form.addRow("Speaking Speed:", speed_row)
        voice_layout.addLayout(voice_form)

        # Voice Library Preset Reference Table
        self.voice_table = QTableWidget(len(VOICE_LIBRARY_PRESETS), 4)
        self.voice_table.setAlternatingRowColors(True)
        self.voice_table.verticalHeader().setVisible(False)
        self.voice_table.setMaximumHeight(155)
        self.voice_table.setHorizontalHeaderLabels(["Preset", "Gender", "Base WPM", "Tone / Style"])
        self.voice_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.voice_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.voice_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.voice_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.voice_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.voice_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row_idx, vp in enumerate(VOICE_LIBRARY_PRESETS.values()):
            self.voice_table.setItem(row_idx, 0, QTableWidgetItem(vp.label))
            self.voice_table.setItem(row_idx, 1, QTableWidgetItem(vp.gender.title()))
            self.voice_table.setItem(row_idx, 2, QTableWidgetItem(f"{vp.base_wpm} WPM"))
            self.voice_table.setItem(row_idx, 3, QTableWidgetItem(vp.description))
        self.voice_table.itemSelectionChanged.connect(self._on_voice_table_row_clicked)
        voice_layout.addWidget(self.voice_table)

        synth_btns = QHBoxLayout()
        self.btn_synthesize = QPushButton("🔊 Synthesize Voiceover (WAV)")
        self.btn_synthesize.setObjectName("PrimaryButton")
        self.btn_synthesize.setToolTip("Synthesize the script into a WAV file in Music Library ('Voiceovers' folder).")
        self.btn_synthesize.clicked.connect(lambda: self._on_synthesize_voiceover(add_to_timeline=False))
        synth_btns.addWidget(self.btn_synthesize)

        self.btn_synth_and_add = QPushButton("➕ Synthesize & Add to Timeline")
        self.btn_synth_and_add.setObjectName("AccentButton")
        self.btn_synth_and_add.setToolTip("Synthesize the voiceover and immediately append it to the current project timeline.")
        self.btn_synth_and_add.clicked.connect(lambda: self._on_synthesize_voiceover(add_to_timeline=True))
        synth_btns.addWidget(self.btn_synth_and_add)
        voice_layout.addLayout(synth_btns)

        # Built-in Voiceover Audio Preview Player
        player_box = QGroupBox("🎧 Voiceover Audition & Generated Voiceovers")
        player_layout = QVBoxLayout(player_box)

        transport = QHBoxLayout()
        self.btn_play_vo = QPushButton("▶ Play Voiceover")
        self.btn_play_vo.clicked.connect(self._toggle_vo_playback)
        transport.addWidget(self.btn_play_vo)

        self.btn_stop_vo = QPushButton("⏹ Stop")
        self.btn_stop_vo.clicked.connect(self._stop_vo_playback)
        transport.addWidget(self.btn_stop_vo)

        self.vo_slider = QSlider(Qt.Orientation.Horizontal)
        self.vo_slider.setRange(0, 1000)
        self.vo_slider.sliderMoved.connect(self._on_vo_slider_moved)
        transport.addWidget(self.vo_slider, stretch=1)

        self.lbl_vo_time = QLabel("00:00 / 00:00")
        self.lbl_vo_time.setStyleSheet("color: #22d3ee; font-family: monospace; font-weight: bold;")
        transport.addWidget(self.lbl_vo_time)
        player_layout.addLayout(transport)

        self.vo_history_table = QTableWidget(0, 3)
        self.vo_history_table.setAlternatingRowColors(True)
        self.vo_history_table.verticalHeader().setVisible(False)
        self.vo_history_table.setHorizontalHeaderLabels(["Voiceover File", "Duration", "Path"])
        self.vo_history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.vo_history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.vo_history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.vo_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.vo_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.vo_history_table.itemSelectionChanged.connect(self._on_vo_history_selected)
        player_layout.addWidget(self.vo_history_table, stretch=1)

        voice_layout.addWidget(player_box, stretch=1)
        body.addWidget(voice_group, stretch=2)

        root.addLayout(body, stretch=1)

    def refresh(self) -> None:
        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
                models = ModelRegistryService(session).list_models()
        except Exception:
            return

        self.model_combo.clear()
        self._model_paths = [None]
        self.model_combo.addItem("Template Engine (Built-in)")
        for m in models:
            ok, _ = ModelRegistryService.check_hardware_compatibility(m, hardware=self._hw_report)
            badge = "Ready" if ok else "Check RAM"
            self.model_combo.addItem(f"{m.name} [{badge}]")
            self._model_paths.append(m.path)

        prev_ch = self.current_channel_id()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self._channel_ids = []
        for ch in channels:
            self.channel_combo.addItem(ch.name)
            self._channel_ids.append(ch.id)
        if prev_ch in self._channel_ids:
            self.channel_combo.setCurrentIndex(self._channel_ids.index(prev_ch))
        self.channel_combo.blockSignals(False)
        self._reload_projects()
        self._reload_voiceover_history()

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

    def _on_channel_changed(self, _idx: int) -> None:
        ch_id = self.current_channel_id()
        if ch_id:
            try:
                with session_scope() as session:
                    ch = ChannelService(session).get(ch_id)
                if ch is not None:
                    vp_idx = self.voice_preset_combo.findData(ch.brand_config.preferred_voice_preset)
                    if vp_idx >= 0:
                        self.voice_preset_combo.setCurrentIndex(vp_idx)
                    self.voice_speed_spin.setValue(float(ch.brand_config.voice_speed or 1.0))
                    if ch.brand_config.target_duration_minutes:
                        self.target_length_spin.setValue(int(ch.brand_config.target_duration_minutes))
            except Exception:
                pass
        self._reload_projects()

    def _reload_projects(self) -> None:
        ch_id = self.current_channel_id()
        prev_proj = self.current_project_id()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self._project_ids = []
        if ch_id:
            with session_scope() as session:
                projects = ProjectService(session).list_projects(channel_id=ch_id)
            for p in projects:
                self.project_combo.addItem(p.name)
                self._project_ids.append(p.id)
            if prev_proj in self._project_ids:
                self.project_combo.setCurrentIndex(self._project_ids.index(prev_proj))
        self.project_combo.blockSignals(False)
        self._on_project_changed(self.project_combo.currentIndex())

    def _on_project_changed(self, _idx: int) -> None:
        proj_id = self.current_project_id()
        if not proj_id:
            self.empty_state.setVisible(True)
            return
        with session_scope() as session:
            proj_svc = ProjectService(session)
            proj = proj_svc.get_project(proj_id)
            draft = proj_svc.get_latest_metadata_draft(proj_id)
        if proj and not self.topic_input.text().strip():
            self.topic_input.setText(proj.name)
        has_script = bool(self.script_edit.toPlainText().strip() or (draft and draft.description))
        self.empty_state.setVisible(not has_script)
        self._update_script_metrics()

    def _on_niche_preset_changed(self, _idx: int) -> None:
        preset_key = str(self.niche_preset_combo.currentData() or "roots_reggae_mix")
        preset = NICHE_STYLE_PRESETS.get(preset_key)
        if preset is None:
            return
        self.target_length_spin.setValue(preset.target_duration_minutes)
        ch_id = self.current_channel_id()
        if ch_id:
            with session_scope() as session:
                ch_svc = ChannelService(session)
                ch = ch_svc.get(ch_id)
                if ch:
                    cfg = apply_niche_preset_to_brand_config(preset_key, existing=ch.brand_config)
                    ch_svc.update_brand_config(ch_id, cfg)
        self._update_script_metrics()

    def _on_voice_preset_selected(self, idx: int) -> None:
        if idx < 0:
            return
        preset_key = str(self.voice_preset_combo.itemData(idx) or "warm_male_narrator")
        vp = VOICE_LIBRARY_PRESETS.get(preset_key)
        if vp:
            self.lbl_voice_details.setText(
                f"Gender: {vp.gender.title()} · Base Rate: {vp.base_wpm} WPM · {vp.description}"
            )
        self._update_script_metrics()

    def _on_voice_table_row_clicked(self) -> None:
        row = self.voice_table.currentRow()
        if 0 <= row < self.voice_preset_combo.count():
            self.voice_preset_combo.setCurrentIndex(row)

    def _active_metadata_generator(self) -> MetadataGenerator:
        model_idx = self.model_combo.currentIndex()
        model_path_str = (
            self._model_paths[model_idx] if 0 <= model_idx < len(self._model_paths) else None
        )
        primary = LlamaCppTextAdapter(Path(model_path_str)) if model_path_str else None
        return MetadataGenerator(primary_adapter=primary)

    def _resolve_context(self) -> tuple[str, str, str, int, list]:
        topic = self.topic_input.text().strip() or "Studio Feature Session"
        ch_name = "YouTube Automation Studio"
        tone = "warm, authentic studio session"
        target_mins = int(self.target_length_spin.value())
        chapters = []
        ch_id = self.current_channel_id()
        proj_id = self.current_project_id()
        with session_scope() as session:
            if ch_id:
                ch = ChannelService(session).get(ch_id)
                if ch:
                    ch_name = ch.name
                    tone = str(ch.brand_config.metadata_template.get("tone") or tone)
            if proj_id:
                proj_svc = ProjectService(session)
                proj = proj_svc.get_project(proj_id)
                if proj and not self.topic_input.text().strip():
                    topic = proj.name
                chapters = proj_svc.compute_chapters(proj_id)
        return topic, ch_name, tone, target_mins, chapters

    def _on_generate_hook(self) -> None:
        topic, ch_name, tone, target_mins, _ = self._resolve_context()
        hook = self._active_metadata_generator().generate_hook(
            topic,
            channel_name=ch_name,
            tone=tone,
            target_duration_minutes=target_mins,
        )
        self.hook_edit.setPlainText(hook)
        self.empty_state.setVisible(False)
        self._update_script_metrics()

    def _on_generate_outline(self) -> None:
        topic, _, _, target_mins, chapters = self._resolve_context()
        hook_text = self.hook_edit.toPlainText().strip()
        outline = self._active_metadata_generator().generate_outline(
            topic,
            hook=hook_text,
            chapters=chapters,
            target_duration_minutes=target_mins,
        )
        self.outline_edit.setPlainText(outline)
        self.empty_state.setVisible(False)
        self._update_script_metrics()

    def _on_generate_full_script(self) -> None:
        topic, ch_name, tone, target_mins, chapters = self._resolve_context()
        draft = self._active_metadata_generator().generate_structured_script(
            topic,
            channel_name=ch_name,
            tone=tone,
            chapters=chapters,
            target_duration_minutes=target_mins,
        )
        self.hook_edit.setPlainText(draft.hook)
        self.outline_edit.setPlainText(draft.outline)
        self.script_edit.setPlainText(draft.full_script)
        self.empty_state.setVisible(False)
        self._update_script_metrics()

    def _on_upload_script_file(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Upload Script / Narration File",
            str(Path.home()),
            "Script Files (*.txt *.md *.srt);;All Files (*)",
        )
        if not chosen:
            return
        text = Path(chosen).read_text(encoding="utf-8", errors="replace")
        self.script_edit.setPlainText(text)
        chapters, _ = MetadataGenerator.parse_script_text(text)
        if chapters:
            self.outline_edit.setPlainText(
                "\n".join(f"{c.format_timestamp()} {c.title}" for c in chapters)
            )
        self.empty_state.setVisible(False)
        self._update_script_metrics()
        QMessageBox.information(
            self,
            "Script Loaded",
            f"Loaded '{Path(chosen).name}' ({len(text.split())} words, {len(chapters)} timestamped chapters extracted).",
        )

    def _update_script_metrics(self) -> None:
        full_text = self.script_edit.toPlainText().strip()
        if not full_text:
            full_text = "\n\n".join(
                p for p in (self.hook_edit.toPlainText().strip(), self.outline_edit.toPlainText().strip()) if p
            )
        words = len(full_text.split()) if full_text else 0
        preset_key = str(self.voice_preset_combo.currentData() or "warm_male_narrator")
        vp = VOICE_LIBRARY_PRESETS.get(preset_key)
        base_wpm = vp.base_wpm if vp else 160
        eff_wpm = max(60.0, base_wpm * float(self.voice_speed_spin.value()))
        est_sec = int(round((words / eff_wpm) * 60.0)) if words > 0 else 0
        mm, ss = est_sec // 60, est_sec % 60
        chapters, _ = MetadataGenerator.parse_script_text(full_text)
        target_mins = int(self.target_length_spin.value())
        target_words = target_mins * 140
        self.metrics_label.setText(
            f"{words} words · Est. Voiceover: {mm:02d}:{ss:02d} ({int(eff_wpm)} WPM) · "
            f"{len(chapters)} Chapters · Target: ~{target_words} words ({target_mins} min)"
        )

    def _ensure_channel_and_project(self) -> tuple[str, str]:
        ch_id = self.current_channel_id()
        proj_id = self.current_project_id()
        created = False
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            if not ch_id:
                ch_id, _, _ = ap.ensure_active_channel()
                created = True
            if not proj_id:
                title = self.topic_input.text().strip() or "Narrated Studio Session"
                proj = ProjectService(session).create_project(
                    ch_id, title, project_type=ProjectType.MIX
                )
                proj_id = proj.id
                created = True
        if created:
            self.refresh()
        return ch_id, proj_id

    def _on_save_script_to_project(self) -> None:
        _, proj_id = self._ensure_channel_and_project()
        script_body = self.script_edit.toPlainText().strip()
        if not script_body:
            self._on_generate_full_script()
            script_body = self.script_edit.toPlainText().strip()
        chapters, summary = MetadataGenerator.parse_script_text(script_body)
        with session_scope() as session:
            proj_svc = ProjectService(session)
            proj = proj_svc.get_project(proj_id)
            existing = proj_svc.get_latest_metadata_draft(proj_id)
            title = (existing.title if existing and existing.title else None) or (
                proj.name if proj else "Studio Session"
            )
            tags = existing.tags if existing else ["studio", "narration", "youtube"]
            ch_block = (
                "\n".join(f"{c.format_timestamp()} {c.title}" for c in chapters)
                if chapters
                else "00:00 Intro"
            )
            desc = f"{summary}\n\nChapters:\n{ch_block}\n\n---\nFull Script:\n{script_body}".strip()
            draft = proj_svc.save_metadata_draft(
                proj_id,
                title=title,
                description=desc,
                tags=tags,
                chapters=chapters if chapters else None,
                approval_status="approved",
            )
        QMessageBox.information(
            self,
            "Script & Chapters Saved",
            f"Saved script ({len(script_body.split())} words) and {len(chapters)} chapter timestamps "
            f"to Metadata Draft v{draft.version}.",
        )

    def _on_synthesize_voiceover(self, *, add_to_timeline: bool = False) -> None:
        ch_id, proj_id = self._ensure_channel_and_project()
        raw_script = self.script_edit.toPlainText().strip()
        if not raw_script:
            self._on_generate_full_script()
            raw_script = self.script_edit.toPlainText().strip()
        if not raw_script:
            QMessageBox.warning(self, "Voiceover", "Enter or generate a script first.")
            return

        preset_key = str(self.voice_preset_combo.currentData() or "warm_male_narrator")
        speed = float(self.voice_speed_spin.value())
        out_dir = get_settings().resolved_data_dir() / "music_library" / "Voiceovers"
        out_dir.mkdir(parents=True, exist_ok=True)
        wav_path = out_dir / f"voiceover_{proj_id[:8]}_{preset_key}.wav"

        try:
            vo_res = LocalTTSService().synthesize(
                raw_script,
                wav_path,
                preset_key=preset_key,
                speed=speed,
            )
            with session_scope() as session:
                if ch_id:
                    ch_svc = ChannelService(session)
                    ch = ch_svc.get(ch_id)
                    if ch:
                        cfg = ch.brand_config.model_copy(deep=True)
                        cfg.preferred_voice_preset = preset_key
                        cfg.voice_speed = speed
                        ch_svc.update_brand_config(ch_id, cfg)
                media_svc = MediaLibraryService(session)
                info = MediaScanner().inspect_file(vo_res.output_path)
                info.metadata["title"] = f"Voiceover — {vo_res.voice_label}"
                info.metadata["folder"] = "Voiceovers"
                saved_media = media_svc.upsert(info)
                if add_to_timeline and proj_id:
                    ProjectService(session).add_track(
                        proj_id,
                        saved_media.id,
                        transition_config=TransitionConfig(
                            transition_type=TransitionType.CROSSFADE,
                            overlap_ms=1500,
                        ),
                    )
            self._reload_voiceover_history()
            self._load_vo_into_player(vo_res.output_path)
            timeline_msg = "\n  ✓ Added to Project Timeline!" if add_to_timeline else ""
            QMessageBox.information(
                self,
                "Voiceover Synthesized",
                f"Synthesized local AI voiceover ({vo_res.duration_ms / 1000.0:.1f}s, {vo_res.word_count} words):\n"
                f"  Voice: {vo_res.voice_label} ({vo_res.speed:.2f}x)\n"
                f"  Engine: {vo_res.engine_used}\n"
                f"  File: {vo_res.output_path}{timeline_msg}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Voiceover Synthesis Failed", str(exc))

    def _reload_voiceover_history(self) -> None:
        self.vo_history_table.setRowCount(0)
        self._voiceover_paths = []
        try:
            with session_scope() as session:
                all_audio = MediaLibraryService(session).list_media(media_type=MediaType.AUDIO)
        except Exception:
            return
        vo_items = [
            m
            for m in all_audio
            if str(m.metadata.get("folder") or "") == "Voiceovers"
            or "voiceover" in Path(m.path).name.lower()
        ]
        self.vo_history_table.setRowCount(len(vo_items))
        for idx, m in enumerate(vo_items):
            p = Path(m.path)
            self._voiceover_paths.append(p)
            title = str(m.metadata.get("title") or p.stem)
            dur_s = (m.duration_ms or 0) / 1000.0
            self.vo_history_table.setItem(idx, 0, QTableWidgetItem(title))
            self.vo_history_table.setItem(idx, 1, QTableWidgetItem(f"{dur_s:.1f}s"))
            self.vo_history_table.setItem(idx, 2, QTableWidgetItem(str(p)))

    def _on_vo_history_selected(self) -> None:
        row = self.vo_history_table.currentRow()
        if 0 <= row < len(self._voiceover_paths):
            self._load_vo_into_player(self._voiceover_paths[row])

    def _load_vo_into_player(self, path: Path) -> None:
        if path.exists():
            self._player.setSource(QUrl.fromLocalFile(str(path)))

    def _toggle_vo_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.btn_play_vo.setText("▶ Play Voiceover")
            return
        if self._player.source().isEmpty() and self._voiceover_paths:
            self._load_vo_into_player(self._voiceover_paths[0])
        self._player.play()
        self.btn_play_vo.setText("⏸ Pause")

    def _stop_vo_playback(self) -> None:
        self._player.stop()
        self.btn_play_vo.setText("▶ Play Voiceover")

    def _on_vo_slider_moved(self, val: int) -> None:
        dur = self._player.duration()
        if dur > 0:
            self._player.setPosition(int((val / 1000.0) * dur))

    def _on_player_position_changed(self, pos_ms: int) -> None:
        dur = max(1, self._player.duration())
        self.vo_slider.blockSignals(True)
        self.vo_slider.setValue(int((pos_ms / dur) * 1000))
        self.vo_slider.blockSignals(False)
        self._update_vo_time_label(pos_ms, dur)

    def _on_player_duration_changed(self, dur_ms: int) -> None:
        self._update_vo_time_label(self._player.position(), max(1, dur_ms))

    def _update_vo_time_label(self, pos_ms: int, dur_ms: int) -> None:
        p_s = max(0, int(pos_ms) // 1000)
        d_s = max(0, int(dur_ms) // 1000)
        self.lbl_vo_time.setText(f"{p_s // 60:02d}:{p_s % 60:02d} / {d_s // 60:02d}:{d_s % 60:02d}")
