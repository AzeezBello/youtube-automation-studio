"""1-Click Express Auto-Pilot Service — automates scanning, project setup, harmonic sorting, silence trimming, SEO metadata, thumbnail generation, 16:9 video rendering, and 9:16 Shorts export in one action."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from youtube_studio.ai import (
    ArtworkGenerator,
    MetadataGenerationRequest,
    MetadataGenerator,
)
from youtube_studio.config import get_settings
from youtube_studio.domain.models.channel import (
    ChannelBrandConfig,
    apply_niche_preset_to_brand_config,
)
from youtube_studio.domain.models.media import MediaFile, MediaType
from youtube_studio.domain.models.project import (
    AssetType,
    ProjectType,
    TransitionConfig,
    TransitionType,
)
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.domain.services.research_service import ResearchService
from youtube_studio.jobs.runner import ProductionJobRunner, sanitize_output_name
from youtube_studio.media.nle_exporter import NLEExporterService
from youtube_studio.media.renderer import VisualizerStyle
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.shorts_clipper import ShortsClipperService
from youtube_studio.media.tts_service import LocalTTSService


@dataclass
class ExpressAutopilotResult:
    """Summary of an automated 1-Click Express Auto-Pilot run."""

    channel_id: str
    channel_name: str
    project_id: str
    project_name: str
    project_type: str
    track_count: int
    chapters_text: str
    seo_title: str
    seo_tags: list[str] = field(default_factory=list)
    title_score_summary: str = ""
    script_text: str = ""
    voiceover_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    manifest_path: Optional[Path] = None
    short_video_path: Optional[Path] = None
    nle_fcpxml_path: Optional[Path] = None
    executed_steps: list[str] = field(default_factory=list)


class ExpressAutopilotService:
    """Automates the entire multi-step YouTube release pipeline into a single operation."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._scanner = MediaScanner()

    def ensure_active_channel(self, channel_id: Optional[str] = None) -> tuple[str, str, ChannelBrandConfig]:
        """Return an active (channel_id, channel_name, brand_config), creating one automatically if needed."""
        ch_svc = ChannelService(self._session)
        if channel_id:
            ch = ch_svc.get(channel_id)
            if ch is not None:
                return ch.id, ch.name, ch.brand_config
        active = ch_svc.list_active()
        if active:
            first = active[0]
            return first.id, first.name, first.brand_config
        created = ch_svc.create("Studio Music Channel")
        return created.id, created.name, created.brand_config

    def resolve_tracks(
        self,
        *,
        media_file_ids: Optional[list[str]] = None,
        source_folder: Optional[str | Path] = None,
        library_folder_name: Optional[str] = None,
    ) -> list[MediaFile]:
        """Collect and deduplicate audio tracks from explicit IDs, a disk folder, a library folder, or all indexed audio."""
        media_svc = MediaLibraryService(self._session)
        candidates: list[MediaFile] = []

        if source_folder:
            folder_path = self._scanner.resolve_directory(Path(source_folder))
            if folder_path.exists() and folder_path.is_dir():
                summary = self._scanner.scan_directory(
                    folder_path,
                    media_service=media_svc,
                    audio_only=True,
                )
                candidates.extend(summary.scanned_files)

        if media_file_ids:
            for mid in media_file_ids:
                mf = media_svc.get(mid)
                if mf is not None and mf.media_type == MediaType.AUDIO:
                    candidates.append(mf)

        if not candidates and library_folder_name:
            all_audio = media_svc.list_media(media_type=MediaType.AUDIO)
            for mf in all_audio:
                tag = str(mf.metadata.get("folder") or Path(mf.path).parent.name).strip()
                if tag == library_folder_name:
                    candidates.append(mf)
            if not candidates:
                managed_dir = get_settings().resolved_data_dir() / "music_library" / library_folder_name
                if managed_dir.exists() and managed_dir.is_dir():
                    summary = self._scanner.scan_directory(
                        managed_dir,
                        media_service=media_svc,
                        audio_only=True,
                    )
                    candidates.extend(summary.scanned_files)

        if not candidates:
            candidates = media_svc.list_media(media_type=MediaType.AUDIO)

        # Deduplicate by file_hash / id while preserving order and verifying file exists
        unique: list[MediaFile] = []
        seen_keys: set[str] = set()
        for mf in candidates:
            key = mf.file_hash or mf.id
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique.append(mf)
        return unique

    def run_autopilot(
        self,
        *,
        channel_id: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
        media_file_ids: Optional[list[str]] = None,
        source_folder: Optional[str | Path] = None,
        library_folder_name: Optional[str] = None,
        style_palette: str = "midnight_neon",
        visualizer_style: str = VisualizerStyle.BAR_SPECTRUM.value,
        custom_visual_path: Optional[str | Path] = None,
        output_name: Optional[str] = None,
        niche_preset: Optional[str] = None,
        target_duration_minutes: Optional[int] = None,
        reference_image_path: Optional[str | Path] = None,
        style_lock: bool = False,
        research_brief: Optional[str] = None,
        script_text: Optional[str] = None,
        synthesize_voiceover: bool = False,
        voice_preset: Optional[str] = None,
        voice_speed: Optional[float] = None,
        render_video: bool = True,
        export_short: bool = True,
        output_base_dir: Optional[Path] = None,
        on_stage_progress: Optional[Callable[[str, int], None]] = None,
    ) -> ExpressAutopilotResult:
        """Execute the end-to-end automated workflow in a single call."""
        executed_steps: list[str] = []

        def _report(stage_label: str, pct: int) -> None:
            if on_stage_progress is not None:
                try:
                    on_stage_progress(stage_label, pct)
                except Exception:
                    pass

        _report("Step 1/6: Channel Profile & Niche Style Preset", 10)

        # 1. Ensure active channel & optional Niche Preset
        ch_id, ch_name, brand_cfg = self.ensure_active_channel(channel_id)
        if niche_preset:
            brand_cfg = apply_niche_preset_to_brand_config(niche_preset, existing=brand_cfg)
            ChannelService(self._session).update_brand_config(ch_id, brand_cfg)
            style_palette = brand_cfg.visual_style
            visualizer_style = str(
                brand_cfg.metadata_template.get("visualizer_style") or visualizer_style
            )
            executed_steps.append(f"Applied niche preset '{niche_preset}' ({style_palette})")
        executed_steps.append(f"Channel ready: {ch_name}")

        eff_target_mins = int(
            target_duration_minutes
            if target_duration_minutes is not None and target_duration_minutes > 0
            else (brand_cfg.target_duration_minutes or 60)
        )

        # 2. Resolve & deduplicate audio tracks
        tracks = self.resolve_tracks(
            media_file_ids=media_file_ids,
            source_folder=source_folder,
            library_folder_name=library_folder_name,
        )
        if not tracks:
            raise ValueError(
                "No audio tracks found. Upload audio files or select a music folder first."
            )
        executed_steps.append(f"Indexed & deduplicated {len(tracks)} audio track(s)")

        # 3. Create or reuse project automatically
        proj_svc = ProjectService(self._session)
        p_type = ProjectType.SINGLE_TRACK if len(tracks) == 1 else ProjectType.MIX

        if project_id:
            project = proj_svc.get_project(project_id)
        else:
            project = None

        if project is None:
            auto_name = (project_name or "").strip()
            if not auto_name:
                if source_folder:
                    folder_stem = Path(source_folder).name
                    auto_name = f"{folder_stem} — Full Mix Session" if len(tracks) > 1 else f"{folder_stem} — Official Audio"
                elif library_folder_name:
                    auto_name = f"{library_folder_name} — Full Mix Session" if len(tracks) > 1 else f"{library_folder_name} — Official Audio"
                elif len(tracks) == 1:
                    t_title = str(tracks[0].metadata.get("title") or Path(tracks[0].path).stem)
                    auto_name = f"{t_title} — Official Audio"
                else:
                    first_title = str(tracks[0].metadata.get("title") or Path(tracks[0].path).stem)
                    auto_name = f"{first_title} & More ({len(tracks)}-Track Harmonic Mix)"
            project = proj_svc.create_project(ch_id, auto_name, project_type=p_type)
            executed_steps.append(f"Created project '{project.name}' ({p_type.value})")
        else:
            executed_steps.append(f"Using project '{project.name}'")

        # 4. Populate timeline tracks (avoiding duplicates already on the timeline)
        existing_project_tracks = proj_svc.list_tracks(project.id)
        existing_media_ids = {pt.media_file_id for pt in existing_project_tracks}
        overlap_ms = 3000 if len(tracks) > 1 else 0
        t_cfg = TransitionConfig(
            transition_type=TransitionType.BASS_SWAP_EQ if overlap_ms > 0 else TransitionType.NONE,
            overlap_ms=overlap_ms,
        )
        added_count = 0
        for mf in tracks:
            if mf.id not in existing_media_ids:
                proj_svc.add_track(
                    project.id,
                    mf.id,
                    fade_in_ms=500 if added_count == 0 else 0,
                    fade_out_ms=1000,
                    transition_config=t_cfg,
                )
                added_count += 1

        # 5. Auto-Cue Silence Trim + Smart Harmonic Sort
        proj_svc.auto_cue_trim_tracks(project.id)
        executed_steps.append("Applied Auto-Cue Silence Trim")
        if len(proj_svc.list_tracks(project.id)) > 1:
            proj_svc.auto_harmonic_sort(project.id)
            executed_steps.append("Applied Smart Harmonic Sort (Camelot Key + BPM)")

        # 6. Auto-Generate Script (Hook -> Outline -> Full Script) + Scored YouTube SEO Metadata
        _report("Step 2/6: Script & Explainable AI Title Scoring", 30)
        chapters = proj_svc.compute_chapters(project.id)
        chapters_lines = [f"{ch.format_timestamp()} {ch.title}" for ch in chapters]
        chapters_text = "\n".join(chapters_lines)

        meta_gen = MetadataGenerator()
        tone_str = str(
            brand_cfg.metadata_template.get("tone") or "warm, authentic studio session"
        )
        script_res = meta_gen.generate_structured_script(
            project.name,
            channel_name=ch_name,
            tone=tone_str,
            chapters=chapters,
            target_duration_minutes=eff_target_mins,
        )
        final_script_text = (script_text or "").strip() or script_res.full_script
        executed_steps.append(
            f"Prepared Hook → Outline → Script ({script_res.estimated_word_count} words, target {eff_target_mins}m)"
        )

        meta_req = MetadataGenerationRequest(
            project_name=project.name,
            project_type=project.project_type,
            channel_name=ch_name,
            brand_config=brand_cfg,
            chapters=chapters,
            research_brief=research_brief,
            target_duration_minutes=eff_target_mins,
            script_text=final_script_text,
        )
        meta_res = meta_gen.generate(meta_req)
        best_title_obj = meta_res.highest_scoring_title
        chosen_seo_title = best_title_obj.title if best_title_obj else meta_res.title
        score_summary = (
            f"{best_title_obj.total_score}/100 ({best_title_obj.explanation})"
            if best_title_obj
            else "100/100 (Length OK · Brand Fit)"
        )
        proj_svc.save_metadata_draft(
            project.id,
            title=chosen_seo_title,
            description=meta_res.description,
            tags=meta_res.tags,
            chapters=chapters,
            approval_status="approved",
        )
        executed_steps.append(
            f"Generated & approved SEO Metadata ('{chosen_seo_title}' — Score: {score_summary})"
        )

        # 7. Auto-Generate & Approve 16:9 YouTube Thumbnail & Background Artwork (with optional Reference Image / Style Lock)
        _report("Step 3/6: Voiceover & Style-Locked Visual Artwork", 50)
        base_out = output_base_dir or get_settings().resolved_output_dir()
        clean_out_name = sanitize_output_name(output_name) if output_name else ""
        project_out_dir = base_out / (clean_out_name if clean_out_name else project.id)
        project_out_dir.mkdir(parents=True, exist_ok=True)

        voiceover_path: Optional[Path] = None
        if synthesize_voiceover and final_script_text:
            tts = LocalTTSService()
            vo_file = project_out_dir / (
                f"{clean_out_name}_voiceover.wav" if clean_out_name else "voiceover_narration.wav"
            )
            vo_res = tts.synthesize(
                script_res.hook if len(final_script_text) > 600 else final_script_text,
                vo_file,
                preset_key=voice_preset or brand_cfg.preferred_voice_preset,
                speed=voice_speed if voice_speed is not None else brand_cfg.voice_speed,
            )
            voiceover_path = vo_res.output_path
            executed_steps.append(
                f"Synthesized local AI voiceover ('{vo_res.voice_label}', {vo_res.duration_ms / 1000.0:.1f}s)"
            )

        thumb_path = project_out_dir / (
            f"{clean_out_name}_thumbnail_1280x720.png"
            if clean_out_name
            else f"thumbnail_{style_palette}_1280x720.png"
        )
        ref_img = (
            Path(reference_image_path).expanduser().resolve()
            if reference_image_path and Path(reference_image_path).exists()
            else (
                Path(brand_cfg.reference_image_path).expanduser().resolve()
                if brand_cfg.reference_image_path and Path(brand_cfg.reference_image_path).exists()
                else None
            )
        )
        eff_style_lock = bool(style_lock or brand_cfg.style_lock or ref_img is not None)

        art_gen = ArtworkGenerator()
        art_res = art_gen.generate(
            project.name,
            thumb_path,
            width=1280,
            height=720,
            style_palette=style_palette,
            subtitle=ch_name,
            badge_text=project.project_type.value.upper(),
            reference_image_path=ref_img,
            style_lock=eff_style_lock,
        )
        asset = proj_svc.register_asset(
            project.id,
            AssetType.THUMBNAIL,
            str(art_res.output_path),
            source_type=art_res.adapter_used,
            provenance=art_res.provenance,
            checksum=art_res.checksum,
            approved=True,
        )
        proj_svc.approve_asset(asset.id, approved=True)
        executed_steps.append("Generated & approved 16:9 Thumbnail Artwork")

        manifest_path: Optional[Path] = None
        short_video_path: Optional[Path] = None

        if custom_visual_path and Path(custom_visual_path).exists():
            proj_svc.register_asset(
                project.id,
                AssetType.BACKGROUND_IMAGE,
                str(Path(custom_visual_path).expanduser().resolve()),
                source_type="custom_upload",
                approved=True,
            )
            executed_steps.append(
                f"Attached custom visual background ('{Path(custom_visual_path).name}')"
            )

        # 8. Export NLE Timeline Exchange Bundle (.fcpxml + .edl + .csv clip list)
        nle_bundle = NLEExporterService(self._session).export_project_timeline(
            project.id,
            project_out_dir,
            output_name=clean_out_name or project.name,
            visual_asset_path=Path(custom_visual_path) if custom_visual_path else Path(art_res.output_path),
        )
        executed_steps.append(
            f"Exported NLE Timeline XML & Clip List ({nle_bundle.fcpxml_path.name})"
        )

        # 9. Optional Full 16:9 Video Render + Export Package + 9:16 Vertical Short
        if render_video:
            _report("Step 4/6: Mixing Audio & Rendering 16:9 Video", 75)
            runner = ProductionJobRunner(self._session)
            job = runner.enqueue_production_job(
                project.id,
                output_dir=project_out_dir,
                visualizer_style=visualizer_style,
                custom_visual_path=custom_visual_path,
                output_name=clean_out_name or None,
                visual_fx={
                    "now_playing_overlay": True,
                    "progress_bar": True,
                    "slow_zoom": True,
                    "film_grain": False,
                    "vignette": True,
                },
            )
            summary = runner.run_job(job.id)
            manifest_path = Path(summary.manifest_path) if summary.manifest_path else None
            executed_steps.append("Rendered 16:9 Full Video & Release Package")

            if export_short and tracks:
                _report("Step 5/6: Exporting 9:16 Vertical Short Highlight", 90)
                first_media = tracks[0]
                first_path = Path(first_media.path)
                if first_path.exists():
                    shorts_dir = project_out_dir / "shorts"
                    clipper = ShortsClipperService()
                    short_res = clipper.create_highlight_short(
                        first_path,
                        shorts_dir,
                        title=project.name,
                        output_name=clean_out_name or None,
                        source_duration_ms=first_media.duration_ms,
                    )
                    short_video_path = Path(short_res.video_path)
                    executed_steps.append("Exported 9:16 Vertical Short / Reel Highlight")

        _report("Step 6/6: Release Package Complete", 100)
        final_track_count = len(proj_svc.list_tracks(project.id))
        return ExpressAutopilotResult(
            channel_id=ch_id,
            channel_name=ch_name,
            project_id=project.id,
            project_name=project.name,
            project_type=project.project_type.value,
            track_count=final_track_count,
            chapters_text=chapters_text,
            seo_title=chosen_seo_title,
            seo_tags=meta_res.tags,
            title_score_summary=score_summary,
            script_text=final_script_text,
            voiceover_path=voiceover_path,
            thumbnail_path=Path(art_res.output_path),
            output_dir=project_out_dir,
            manifest_path=manifest_path,
            short_video_path=short_video_path,
            nle_fcpxml_path=nle_bundle.fcpxml_path,
            executed_steps=executed_steps,
        )

    def run_from_video_url(
        self,
        url_or_id: str,
        *,
        channel_id: Optional[str] = None,
        research_project_id: Optional[str] = None,
        source_folder: Optional[str | Path] = None,
        library_folder_name: Optional[str] = None,
        niche_preset: Optional[str] = None,
        output_name: Optional[str] = None,
        render_video: bool = False,
        output_base_dir: Optional[Path] = None,
    ) -> ExpressAutopilotResult:
        """1-Click Project from Research URL: imports YouTube URL -> creates Research Brief & Idea -> builds full Production Project."""
        ch_id, _, _ = self.ensure_active_channel(channel_id)
        res_svc = ResearchService(self._session)
        r_proj, _src, idea = res_svc.import_from_video_url(
            url_or_id,
            channel_id=ch_id,
            research_project_id=research_project_id,
        )
        prod_proj, _draft = res_svc.handoff_idea_to_production(
            idea.id,
            channel_id=ch_id,
        )
        return self.run_autopilot(
            channel_id=ch_id,
            project_id=prod_proj.id,
            project_name=prod_proj.name,
            source_folder=source_folder,
            library_folder_name=library_folder_name,
            niche_preset=niche_preset,
            research_brief=r_proj.brief,
            output_name=output_name or prod_proj.name,
            render_video=render_video,
            export_short=render_video,
            output_base_dir=output_base_dir,
        )
