"""Artwork, Thumbnails & Local AI Studio UI page (P3)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFont
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.ai import (
    ArtworkGenerator,
    LlamaCppTextAdapter,
    MetadataGenerationRequest,
    MetadataGenerator,
)
from youtube_studio.config import HardwareProbe, get_settings
from youtube_studio.domain.models.channel import (
    VOICE_LIBRARY_PRESETS,
    ChannelBrandConfig,
)
from youtube_studio.domain.models.project import AssetType
from youtube_studio.domain.services import (
    ChannelService,
    MediaLibraryService,
    ModelRegistryService,
    ProjectService,
)
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.thumbnail import PALETTES
from youtube_studio.media.tts_service import LocalTTSService
from youtube_studio.storage import session_scope
from youtube_studio.ui.components import EmptyStateWidget


class ArtworkPage(QWidget):
    """Interactive workspace for local AI model registry, metadata generation, and thumbnail/artwork creation."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel_ids: list[str] = []
        self._project_ids: list[str] = []
        self._model_paths: list[Optional[str]] = []
        self._asset_ids: list[str] = []
        self._hw_report = HardwareProbe().run()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        heading = QLabel("Artwork, Thumbnails & Local AI Studio")
        heading.setFont(QFont("", 18, QFont.Weight.Bold))
        root.addWidget(heading)

        # Hardware & Model Registry Bar
        hw_label = QLabel(
            f"Hardware: {self._hw_report.cpu_count} CPU cores · {self._hw_report.total_ram_gb} GB RAM · "
            f"Recommended profile: {self._hw_report.recommended_profile.value}"
        )
        hw_label.setStyleSheet("color: #94a3b8;")
        hw_label.setToolTip("Detected local hardware specifications used to validate local AI model compatibility.")
        root.addWidget(hw_label)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setToolTip("Select the channel profile whose brand style and projects you want to edit.")
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        top_row.addWidget(self.channel_combo, stretch=1)

        top_row.addWidget(QLabel("Project:"))
        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Select the production project for metadata and thumbnail generation.")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_row.addWidget(self.project_combo, stretch=1)

        top_row.addWidget(QLabel("Local LM:"))
        self.model_combo = QComboBox()
        self.model_combo.setToolTip(
            "Select a registered local GGUF language model or use the built-in Template Fallback."
        )
        top_row.addWidget(self.model_combo, stretch=1)

        reg_model_btn = QPushButton("+ Register Local Model…")
        reg_model_btn.setToolTip(
            "Register a local .gguf, .safetensors, or .onnx model weight file and verify RAM compatibility."
        )
        reg_model_btn.clicked.connect(self._on_register_model)
        top_row.addWidget(reg_model_btn)

        root.addLayout(top_row)

        # Empty State Guide (visible when the selected project has no generated assets yet)
        self.empty_state = EmptyStateWidget(
            title="No Project Thumbnails or Artwork Generated Yet",
            description=(
                "Select a channel and project above, then generate SEO metadata drafts (titles, chapters, tags) "
                "and 16:9 or 9:16 thumbnails—with zero cloud subscription required."
            ),
            tips=[
                "<b>Zero-Dependency Fallback:</b> Even without a local LLM or diffusion GPU, the built-in template and procedural engines generate ready-to-use titles and vinyl/gradient artwork.",
                "<b>Chapter Timestamps Included:</b> Descriptions automatically include 00:00 formatted tracklist chapters from your Production timeline.",
                "<b>16:9 & 9:16 Aspect Ratios:</b> Render standard 1280x720 YouTube thumbnails or 1080x1920 vertical covers.",
            ],
            action_label="Generate SEO Metadata",
            action_tooltip="Generate 3 title candidates, chapter description, and tags for the current project.",
            on_action=self._on_generate_metadata,
            secondary_label="Generate Thumbnail & Artwork",
            secondary_tooltip="Render a 16:9 or 9:16 thumbnail image for the current project.",
            on_secondary=self._on_generate_artwork,
        )
        root.addWidget(self.empty_state)

        # Split body: Left = Metadata Studio, Right = Artwork & Thumbnail Studio
        body = QHBoxLayout()

        # Left column: Local AI Metadata + Explainable Title Scorer + Hook/Outline/Script + Voiceover
        meta_group = QGroupBox("Local AI Metadata, Explainable Title Scorer & Script / Voiceover Studio")
        meta_layout = QVBoxLayout(meta_group)

        gen_meta_btn = QPushButton("✨ Generate 5 Ranked Titles (Explainable Score) + Description + Tags")
        gen_meta_btn.setObjectName("PrimaryButton")
        gen_meta_btn.setToolTip(
            "Generate 5 YouTube title candidates ranked by transparent rules (length, seed keywords, channel tone), "
            "timestamped chapter description, and tags (≤500 chars)."
        )
        gen_meta_btn.clicked.connect(self._on_generate_metadata)
        meta_layout.addWidget(gen_meta_btn)

        self.best_title_label = QLabel(
            "🏆 Highest Scoring Title: Click 'Generate 5 Ranked Titles' above (evaluated by transparent length, keyword & tone rules — never fake CTR)"
        )
        self.best_title_label.setWordWrap(True)
        self.best_title_label.setStyleSheet(
            "color: #fcd34d; background: rgba(250, 204, 21, 0.10); border: 1px solid rgba(250, 204, 21, 0.35); "
            "border-radius: 6px; padding: 6px 10px; font-size: 12px; font-weight: 600;"
        )
        meta_layout.addWidget(self.best_title_label)

        meta_form = QFormLayout()
        self.candidates_combo = QComboBox()
        self.candidates_combo.setToolTip(
            "Ranked title options with explainable criteria (Length OK, Seed Keywords, Channel Tone)."
        )
        self.candidates_combo.currentIndexChanged.connect(self._on_candidate_combo_changed)
        meta_form.addRow("Ranked Titles:", self.candidates_combo)

        self.title_input = QLineEdit()
        self.title_input.setToolTip("Final YouTube video title (enforced ≤ 100 characters).")
        meta_form.addRow("Selected Title:", self.title_input)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("comma, separated, tags")
        self.tags_input.setToolTip("Comma-separated YouTube tags (total budget ≤ 500 characters).")
        meta_form.addRow("Tags (≤500 chars):", self.tags_input)

        meta_layout.addLayout(meta_form)

        # Structured Hook -> Outline -> Full Script + Paste/Upload + Voiceover (TTS)
        script_hdr = QHBoxLayout()
        script_hdr.addWidget(QLabel("Structured Script (Hook → Outline → Full Script) / Narration:"))
        self.btn_step_hook = QPushButton("1. Hook")
        self.btn_step_hook.setToolTip("Generate a 15-second opening hook tailored to the channel tone.")
        self.btn_step_hook.clicked.connect(self._on_generate_hook_step)
        script_hdr.addWidget(self.btn_step_hook)

        self.btn_step_outline = QPushButton("2. Outline")
        self.btn_step_outline.setToolTip("Build a timestamped section outline from your hook and project chapters.")
        self.btn_step_outline.clicked.connect(self._on_generate_outline_step)
        script_hdr.addWidget(self.btn_step_outline)

        self.btn_step_full_script = QPushButton("3. Full Script")
        self.btn_step_full_script.setObjectName("AccentButton")
        self.btn_step_full_script.setToolTip("Draft the full narration / host script timed to your project's target duration.")
        self.btn_step_full_script.clicked.connect(self._on_generate_full_script_step)
        script_hdr.addWidget(self.btn_step_full_script)

        self.btn_upload_script = QPushButton("📄 Upload Script…")
        self.btn_upload_script.setToolTip(
            "Upload a .txt, .md, or .srt script file to attach narration and automatically extract 00:00 chapters."
        )
        self.btn_upload_script.clicked.connect(self._on_upload_script_file)
        script_hdr.addWidget(self.btn_upload_script)
        meta_layout.addLayout(script_hdr)

        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText(
            "Optional: Paste or generate Hook → Outline → Full Narration Script here (or upload a .txt/.md/.srt file)…"
        )
        self.script_edit.setMaximumHeight(110)
        meta_layout.addWidget(self.script_edit)

        # Voice Library (Male/Female, Speed) + Local AI Voiceover (TTS)
        tts_row = QHBoxLayout()
        tts_row.addWidget(QLabel("Voice Preset:"))
        self.voice_preset_combo = QComboBox()
        for vp in VOICE_LIBRARY_PRESETS.values():
            self.voice_preset_combo.addItem(f"🎙 {vp.label} [{vp.gender.title()}]", vp.key)
        self.voice_preset_combo.setToolTip(
            "Select a local-first male or female voice preset (stored per channel; zero mandatory paid API)."
        )
        tts_row.addWidget(self.voice_preset_combo, stretch=1)

        tts_row.addWidget(QLabel("Speed:"))
        self.voice_speed_spin = QDoubleSpinBox()
        self.voice_speed_spin.setRange(0.5, 2.0)
        self.voice_speed_spin.setSingleStep(0.05)
        self.voice_speed_spin.setValue(1.0)
        self.voice_speed_spin.setSuffix("x")
        tts_row.addWidget(self.voice_speed_spin)

        self.btn_synthesize_tts = QPushButton("🔊 Synthesize Voiceover (Local TTS)")
        self.btn_synthesize_tts.setObjectName("AccentButton")
        self.btn_synthesize_tts.setToolTip(
            "Synthesize the script above into a local WAV voiceover file and add it to the project & Music Library."
        )
        self.btn_synthesize_tts.clicked.connect(self._on_synthesize_voiceover)
        tts_row.addWidget(self.btn_synthesize_tts)
        meta_layout.addLayout(tts_row)

        meta_layout.addWidget(QLabel("Description (with Chapters):"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setToolTip("Full YouTube video description including 00:00 tracklist chapters and hashtags.")
        meta_layout.addWidget(self.desc_edit, stretch=1)

        save_meta_btn = QPushButton("Save New Metadata Draft Version")
        save_meta_btn.setToolTip("Save an immutable versioned MetadataDraft record for this project.")
        save_meta_btn.clicked.connect(self._on_save_metadata_draft)
        meta_layout.addWidget(save_meta_btn)

        body.addWidget(meta_group, stretch=1)

        # Right column: Artwork & Thumbnail Generator
        art_group = QGroupBox("Thumbnail & Artwork Generator (Local Diffusion / Procedural Fallback)")
        art_layout = QVBoxLayout(art_group)

        art_form = QFormLayout()
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("Enter thumbnail title or visual prompt…")
        self.prompt_input.setToolTip("Headline text or visual prompt rendered on the thumbnail artwork.")
        art_form.addRow("Title / Prompt:", self.prompt_input)

        self.palette_combo = QComboBox()
        self.palette_combo.addItems(list(PALETTES.keys()))
        self.palette_combo.setToolTip("Select the color gradient and typography palette for the thumbnail.")
        art_form.addRow("Brand Palette:", self.palette_combo)

        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["16:9 (1280x720)", "9:16 (1080x1920)"])
        self.aspect_combo.setToolTip("Choose 16:9 for standard YouTube videos or 9:16 for YouTube Shorts.")
        art_form.addRow("Aspect Ratio:", self.aspect_combo)

        ref_row = QHBoxLayout()
        self.ref_image_input = QLineEdit()
        self.ref_image_input.setPlaceholderText("Optional reference image path to lock palette & visual style…")
        self.ref_image_input.setToolTip(
            "Upload or select a reference image to extract its color palette and composite it into generated thumbnails."
        )
        ref_row.addWidget(self.ref_image_input, stretch=1)

        self.btn_pick_ref_image = QPushButton("🖼 Reference…")
        self.btn_pick_ref_image.setToolTip("Pick a reference image (.png, .jpg, .webp) for Style Lock.")
        self.btn_pick_ref_image.clicked.connect(self._on_pick_reference_image)
        ref_row.addWidget(self.btn_pick_ref_image)
        art_form.addRow("Reference Image:", ref_row)

        self.chk_style_lock = QCheckBox("🔒 Lock Thumbnail Palette && Visual Layout to Reference Image")
        self.chk_style_lock.setToolTip(
            "When checked, locks the channel's thumbnail color palette and backdrop blend to the selected Reference Image."
        )
        art_form.addRow("Style Lock:", self.chk_style_lock)

        art_out_row = QHBoxLayout()
        self.art_output_input = QLineEdit()
        self.art_output_input.setText(str(get_settings().resolved_output_dir()))
        self.art_output_input.setToolTip("Destination directory where generated thumbnails and artwork are saved.")
        art_out_row.addWidget(self.art_output_input, stretch=1)

        self.btn_browse_art_out = QPushButton("📁 Browse…")
        self.btn_browse_art_out.setToolTip("Choose a custom output directory for generated thumbnails and artwork.")
        self.btn_browse_art_out.clicked.connect(self._on_browse_art_output)
        art_out_row.addWidget(self.btn_browse_art_out)
        art_form.addRow("Output Folder:", art_out_row)

        art_layout.addLayout(art_form)

        art_btns_row = QHBoxLayout()
        gen_art_btn = QPushButton("Generate Thumbnail && Artwork")
        gen_art_btn.setObjectName("AccentButton")
        gen_art_btn.setToolTip("Render and register a new PNG thumbnail asset for the selected project.")
        gen_art_btn.clicked.connect(self._on_generate_artwork)
        art_btns_row.addWidget(gen_art_btn)

        self.upload_custom_asset_btn = QPushButton("🖼/🎬 + Upload Custom Image or Video Asset…")
        self.upload_custom_asset_btn.setObjectName("PrimaryButton")
        self.upload_custom_asset_btn.setToolTip(
            "Upload your own image (.png, .jpg, .webp) or background video loop (.mp4, .mov, .webm) "
            "to use in your project and video renderer."
        )
        self.upload_custom_asset_btn.clicked.connect(self._on_upload_custom_asset)
        art_btns_row.addWidget(self.upload_custom_asset_btn)
        art_layout.addLayout(art_btns_row)

        self.assets_table = QTableWidget(0, 4)
        self.assets_table.setAlternatingRowColors(True)
        self.assets_table.setToolTip("Generated visual and media assets registered to this project.")
        self.assets_table.setHorizontalHeaderLabels(["Type", "Approved", "Adapter", "File Path"])
        self.assets_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.assets_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.assets_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        art_layout.addWidget(self.assets_table, stretch=1)

        approve_btn = QPushButton("Approve Selected Asset for Publishing")
        approve_btn.setToolTip("Mark the selected thumbnail/artwork asset as approved for the release package.")
        approve_btn.clicked.connect(self._on_approve_asset)
        art_layout.addWidget(approve_btn)

        body.addWidget(art_group, stretch=1)
        root.addLayout(body, stretch=1)

    def refresh(self) -> None:
        if hasattr(self, "art_output_input"):
            self.art_output_input.setText(str(get_settings().resolved_output_dir()))
        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
                models = ModelRegistryService(session).list_models()
        except Exception:
            return

        # Populate models combo
        self.model_combo.clear()
        self._model_paths = [None]
        self.model_combo.addItem("Template Fallback (Built-in)")
        for m in models:
            ok, _note = ModelRegistryService.check_hardware_compatibility(
                m, hardware=self._hw_report
            )
            badge = "Ready" if ok else "Check RAM/Path"
            self.model_combo.addItem(f"{m.name} v{m.version} [{badge}]")
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
        prev_proj = self.current_project_id()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self._project_ids = []
        if channel_id:
            with session_scope() as session:
                projects = ProjectService(session).list_projects(channel_id=channel_id)
            for p in projects:
                self.project_combo.addItem(p.name)
                self._project_ids.append(p.id)
            if prev_proj in self._project_ids:
                self.project_combo.setCurrentIndex(self._project_ids.index(prev_proj))
        self.project_combo.blockSignals(False)
        self._reload_project_details()

    def _on_project_changed(self, _index: int) -> None:
        self._reload_project_details()

    def _reload_project_details(self) -> None:
        project_id = self.current_project_id()
        self.assets_table.setRowCount(0)
        self._asset_ids = []
        if not project_id:
            if hasattr(self, "empty_state"):
                self.empty_state.setVisible(True)
            return

        with session_scope() as session:
            proj_svc = ProjectService(session)
            project = proj_svc.get_project(project_id)
            draft = proj_svc.get_latest_metadata_draft(project_id)
            assets = proj_svc.list_assets(project_id)

        if hasattr(self, "empty_state"):
            self.empty_state.setVisible(len(assets) == 0)

        if project and not self.prompt_input.text().strip():
            self.prompt_input.setText(project.name)

        if draft:
            self.title_input.setText(draft.title or "")
            self.tags_input.setText(", ".join(draft.tags))
            self.desc_edit.setPlainText(draft.description or "")

        self.assets_table.setRowCount(len(assets))
        for idx, asset in enumerate(assets):
            self._asset_ids.append(asset.id)
            adapter_str = str(asset.provenance.get("adapter") or asset.source_type)
            self.assets_table.setItem(idx, 0, QTableWidgetItem(asset.asset_type.value))
            self.assets_table.setItem(
                idx, 1, QTableWidgetItem("Approved" if asset.approved else "Pending")
            )
            self.assets_table.setItem(idx, 2, QTableWidgetItem(adapter_str))
            self.assets_table.setItem(idx, 3, QTableWidgetItem(asset.file_path))

    def _on_register_model(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Local Model Weight File",
            "",
            "Model Files (*.gguf *.safetensors *.onnx *.bin *.pt *.pth);;All Files (*)",
        )
        if not file_path:
            return
        p = Path(file_path)
        name, ok = QInputDialog.getText(
            self, "Register Local Model", "Model display name:", text=p.stem
        )
        if not ok or not name.strip():
            return
        with session_scope() as session:
            svc = ModelRegistryService(session)
            model = svc.register_model(name.strip(), p)
            compatible, note = svc.check_hardware_compatibility(model, hardware=self._hw_report)
        self.refresh()
        status = "Compatible" if compatible else "Warning"
        QMessageBox.information(self, f"Model Registered ({status})", note)

    def _on_generate_metadata(self) -> None:
        project_id = self.current_project_id()
        channel_id = self.current_channel_id()
        if not project_id or not channel_id:
            QMessageBox.warning(self, "Metadata", "Please select a channel and project first.")
            return

        model_idx = self.model_combo.currentIndex()
        model_path_str = (
            self._model_paths[model_idx] if 0 <= model_idx < len(self._model_paths) else None
        )
        primary_adapter = (
            LlamaCppTextAdapter(Path(model_path_str)) if model_path_str else None
        )
        generator = MetadataGenerator(primary_adapter=primary_adapter)

        with session_scope() as session:
            ch = ChannelService(session).get(channel_id)
            proj_svc = ProjectService(session)
            proj = proj_svc.get_project(project_id)
            chapters = proj_svc.compute_chapters(project_id)
            if not proj:
                return
            req = MetadataGenerationRequest(
                project_name=proj.name,
                project_type=proj.project_type,
                channel_name=ch.name if ch else "YouTube Automation Studio",
                brand_config=ch.brand_config if ch else ChannelBrandConfig(),
                chapters=chapters,
                script_text=self.script_edit.toPlainText().strip() or None,
                candidate_count=5,
            )
            res = generator.generate(req)

        self.candidates_combo.blockSignals(True)
        self.candidates_combo.clear()
        if res.scored_candidates:
            for sc in res.scored_candidates:
                label = f"[{sc.total_score}/100 · {sc.explanation}] {sc.title}"
                self.candidates_combo.addItem(label, sc.title)
        else:
            for t in res.title_candidates:
                self.candidates_combo.addItem(t, t)
        self.candidates_combo.blockSignals(False)

        best = res.highest_scoring_title
        if best is not None:
            self.best_title_label.setText(
                f"🏆 Highest Scoring Title ({best.total_score}/100 — {best.explanation}):  {best.title}"
            )
            self.title_input.setText(best.title)
        else:
            self.title_input.setText(res.title)
        self.tags_input.setText(", ".join(res.tags))
        self.desc_edit.setPlainText(res.description)

    def _on_candidate_combo_changed(self, idx: int) -> None:
        if idx < 0:
            return
        raw_title = self.candidates_combo.itemData(idx)
        self.title_input.setText(str(raw_title or self.candidates_combo.currentText()))

    def _on_generate_hook_step(self) -> None:
        proj_id = self.current_project_id()
        ch_id = self.current_channel_id()
        topic = self.title_input.text().strip() or self.prompt_input.text().strip() or "Featured Session"
        ch_name = "Studio Channel"
        tone = "warm, authentic studio session"
        target_mins = 15
        if ch_id:
            with session_scope() as session:
                ch = ChannelService(session).get(ch_id)
                if ch:
                    ch_name = ch.name
                    tone = str(ch.brand_config.metadata_template.get("tone") or tone)
                    target_mins = int(ch.brand_config.target_duration_minutes or 15)
                if proj_id:
                    proj = ProjectService(session).get_project(proj_id)
                    if proj and not self.title_input.text().strip():
                        topic = proj.name
        hook = MetadataGenerator().generate_hook(
            topic,
            channel_name=ch_name,
            tone=tone,
            target_duration_minutes=target_mins,
        )
        self.script_edit.setPlainText(hook)

    def _on_generate_outline_step(self) -> None:
        proj_id = self.current_project_id()
        ch_id = self.current_channel_id()
        topic = self.title_input.text().strip() or self.prompt_input.text().strip() or "Featured Session"
        chapters = []
        target_mins = 15
        with session_scope() as session:
            if ch_id:
                ch = ChannelService(session).get(ch_id)
                if ch:
                    target_mins = int(ch.brand_config.target_duration_minutes or 15)
            if proj_id:
                chapters = ProjectService(session).compute_chapters(proj_id)
        current_text = self.script_edit.toPlainText().strip()
        outline = MetadataGenerator().generate_outline(
            topic,
            hook=current_text,
            chapters=chapters,
            target_duration_minutes=target_mins,
        )
        combined = f"{current_text}\n\n{outline}".strip() if current_text else outline
        self.script_edit.setPlainText(combined)

    def _on_generate_full_script_step(self) -> None:
        proj_id = self.current_project_id()
        ch_id = self.current_channel_id()
        topic = self.title_input.text().strip() or self.prompt_input.text().strip() or "Featured Session"
        ch_name = "Studio Channel"
        tone = "warm, authentic studio session"
        target_mins = 15
        chapters = []
        with session_scope() as session:
            if ch_id:
                ch = ChannelService(session).get(ch_id)
                if ch:
                    ch_name = ch.name
                    tone = str(ch.brand_config.metadata_template.get("tone") or tone)
                    target_mins = int(ch.brand_config.target_duration_minutes or 15)
            if proj_id:
                proj_svc = ProjectService(session)
                proj = proj_svc.get_project(proj_id)
                if proj and not self.title_input.text().strip():
                    topic = proj.name
                chapters = proj_svc.compute_chapters(proj_id)
        draft = MetadataGenerator().generate_structured_script(
            topic,
            channel_name=ch_name,
            tone=tone,
            chapters=chapters,
            target_duration_minutes=target_mins,
        )
        self.script_edit.setPlainText(draft.full_script)

    def _on_upload_script_file(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Upload Script / Narration Text File",
            str(Path.home()),
            "Script Files (*.txt *.md *.srt);;All Files (*)",
        )
        if not chosen:
            return
        text = Path(chosen).read_text(encoding="utf-8", errors="replace")
        self.script_edit.setPlainText(text)
        chapters, _ = MetadataGenerator.parse_script_text(text)
        if chapters:
            ch_lines = "\n".join(f"{c.format_timestamp()} {c.title}" for c in chapters)
            cur_desc = self.desc_edit.toPlainText().strip()
            self.desc_edit.setPlainText(
                f"{cur_desc}\n\nExtracted Script Chapters:\n{ch_lines}".strip()
            )
        QMessageBox.information(
            self,
            "Script Uploaded",
            f"Loaded script '{Path(chosen).name}' ({len(text.split())} words, {len(chapters)} timestamped chapters detected).",
        )

    def _on_synthesize_voiceover(self) -> None:
        raw_script = self.script_edit.toPlainText().strip()
        if not raw_script:
            self._on_generate_full_script_step()
            raw_script = self.script_edit.toPlainText().strip()
        if not raw_script:
            QMessageBox.warning(self, "Voiceover (TTS)", "Enter or generate a script first.")
            return

        preset_key = str(self.voice_preset_combo.currentData() or "warm_male_narrator")
        speed = float(self.voice_speed_spin.value())
        out_dir = get_settings().resolved_data_dir() / "music_library" / "Voiceovers"
        out_dir.mkdir(parents=True, exist_ok=True)
        proj_id = self.current_project_id() or "studio"
        wav_path = out_dir / f"voiceover_{proj_id[:8]}_{preset_key}.wav"

        try:
            tts = LocalTTSService()
            vo_res = tts.synthesize(
                raw_script,
                wav_path,
                preset_key=preset_key,
                speed=speed,
            )
            with session_scope() as session:
                ch_id = self.current_channel_id()
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
                media_svc.upsert(info)
            QMessageBox.information(
                self,
                "Local AI Voiceover Synthesized",
                f"Synthesized voiceover ({vo_res.duration_ms / 1000.0:.1f}s, {vo_res.word_count} words):\n"
                f"  Voice: {vo_res.voice_label} ({vo_res.speed:.2f}x)\n"
                f"  Engine: {vo_res.engine_used}\n"
                f"  Saved to Music Library ('Voiceovers'):\n  {vo_res.output_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Voiceover Synthesis Failed", str(exc))

    def _on_pick_reference_image(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference Image for Style Lock",
            str(Path.home()),
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not chosen:
            return
        self.ref_image_input.setText(chosen)
        self.chk_style_lock.setChecked(True)

    def _on_save_metadata_draft(self) -> None:
        project_id = self.current_project_id()
        if not project_id:
            QMessageBox.warning(self, "Save Draft", "Please select a project first.")
            return
        tags = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        with session_scope() as session:
            proj_svc = ProjectService(session)
            draft = proj_svc.save_metadata_draft(
                project_id,
                title=self.title_input.text().strip() or None,
                description=self.desc_edit.toPlainText().strip() or None,
                tags=tags,
                approval_status="approved",
            )
        QMessageBox.information(
            self,
            "Metadata Saved",
            f"Saved Metadata Draft v{draft.version} for project.",
        )

    def _on_browse_art_output(self) -> None:
        current = self.art_output_input.text().strip() or str(get_settings().resolved_output_dir())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder for Thumbnails & Artwork",
            current,
        )
        if not chosen:
            return
        saved = get_settings().set_output_dir(chosen)
        self.art_output_input.setText(str(saved))

    def _on_generate_artwork(self) -> None:
        project_id = self.current_project_id()
        channel_id = self.current_channel_id()
        if not project_id or not channel_id:
            QMessageBox.warning(self, "Artwork", "Please select a channel and project first.")
            return

        prompt = self.prompt_input.text().strip() or "Untitled Session"
        palette = self.palette_combo.currentText()
        is_vertical = self.aspect_combo.currentIndex() == 1
        width, height = (1080, 1920) if is_vertical else (1280, 720)

        settings = get_settings()
        raw_out = self.art_output_input.text().strip() if hasattr(self, "art_output_input") else ""
        base_out = settings.set_output_dir(raw_out) if raw_out else settings.resolved_output_dir()
        out_dir = base_out / project_id
        out_path = out_dir / f"thumbnail_{palette}_{width}x{height}.png"

        try:
            with session_scope() as session:
                ch = ChannelService(session).get(channel_id)
                proj_svc = ProjectService(session)
                proj = proj_svc.get_project(project_id)
                ref_raw = self.ref_image_input.text().strip() if hasattr(self, "ref_image_input") else ""
                ref_path = Path(ref_raw).expanduser().resolve() if ref_raw and Path(ref_raw).exists() else None
                style_locked = bool(self.chk_style_lock.isChecked()) if hasattr(self, "chk_style_lock") else False
                if ch and (ref_path or style_locked):
                    cfg = ch.brand_config.model_copy(deep=True)
                    cfg.reference_image_path = str(ref_path) if ref_path else cfg.reference_image_path
                    cfg.style_lock = style_locked
                    ChannelService(session).update_brand_config(channel_id, cfg)

                art_gen = ArtworkGenerator()
                res = art_gen.generate(
                    prompt,
                    out_path,
                    width=width,
                    height=height,
                    style_palette=palette,
                    subtitle=ch.name if ch else None,
                    badge_text=proj.project_type.value.upper() if proj else "MIX",
                    reference_image_path=ref_path,
                    style_lock=style_locked,
                )
                proj_svc.register_asset(
                    project_id,
                    AssetType.THUMBNAIL,
                    str(res.output_path),
                    source_type=res.adapter_used,
                    provenance=res.provenance,
                    checksum=res.checksum,
                    approved=False,
                )
            self._reload_project_details()
        except Exception as exc:
            QMessageBox.critical(self, "Artwork Generation Failed", str(exc))

    def _on_upload_custom_asset(self) -> None:
        import shutil
        from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService

        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom Image or Video Asset",
            str(Path.home()),
            "Visual Assets (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.mp4 *.mov *.webm *.mkv *.m4v)",
        )
        if not chosen:
            return
        src = Path(chosen).expanduser().resolve()
        if not src.exists():
            return

        dest_dir = get_settings().resolved_data_dir() / "visual_assets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)

        project_id = self.current_project_id()
        with session_scope() as session:
            if not project_id:
                ap = ExpressAutopilotService(session)
                ch_id, _, _ = ap.ensure_active_channel(self.current_channel_id())
                proj = ProjectService(session).create_project(ch_id, src.stem)
                project_id = proj.id
            proj_svc = ProjectService(session)
            proj_svc.register_asset(
                project_id,
                AssetType.BACKGROUND_IMAGE,
                str(dest),
                source_type="custom_upload",
                approved=True,
            )
            if src.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                proj_svc.register_asset(
                    project_id,
                    AssetType.THUMBNAIL,
                    str(dest),
                    source_type="custom_upload",
                    approved=True,
                )
        self.refresh()
        self._reload_project_details()
        QMessageBox.information(
            self,
            "Custom Asset Uploaded & Approved",
            f"Uploaded and approved '{dest.name}' for your project!\n"
            "It will automatically be used as the visual background when rendering your video.",
        )

    def _on_approve_asset(self) -> None:
        row = self.assets_table.currentRow()
        if row < 0 or row >= len(self._asset_ids):
            QMessageBox.warning(self, "Approve Asset", "Select an asset row first.")
            return
        asset_id = self._asset_ids[row]
        with session_scope() as session:
            ProjectService(session).approve_asset(asset_id, approved=True)
        self._reload_project_details()
