"""1-Click Express Auto-Pilot Service — automates scanning, project setup, harmonic sorting, silence trimming, SEO metadata, thumbnail generation, 16:9 video rendering, and 9:16 Shorts export in one action."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from youtube_studio.ai import (
    ArtworkGenerator,
    MetadataGenerationRequest,
    MetadataGenerator,
)
from youtube_studio.config import get_settings
from youtube_studio.domain.models.channel import ChannelBrandConfig
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
from youtube_studio.jobs.runner import ProductionJobRunner, sanitize_output_name
from youtube_studio.media.renderer import VisualizerStyle
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.shorts_clipper import ShortsClipperService


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
    thumbnail_path: Optional[Path] = None
    output_dir: Optional[Path] = None
    manifest_path: Optional[Path] = None
    short_video_path: Optional[Path] = None
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
        render_video: bool = True,
        export_short: bool = True,
        output_base_dir: Optional[Path] = None,
    ) -> ExpressAutopilotResult:
        """Execute the end-to-end automated workflow in a single call."""
        executed_steps: list[str] = []

        # 1. Ensure active channel
        ch_id, ch_name, brand_cfg = self.ensure_active_channel(channel_id)
        executed_steps.append(f"Channel ready: {ch_name}")

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

        # 6. Auto-Generate YouTube SEO Metadata (Title, Chapters, Description, Tags)
        chapters = proj_svc.compute_chapters(project.id)
        chapters_lines = [f"{ch.format_timestamp()} {ch.title}" for ch in chapters]
        chapters_text = "\n".join(chapters_lines)

        meta_gen = MetadataGenerator()
        meta_req = MetadataGenerationRequest(
            project_name=project.name,
            project_type=project.project_type,
            channel_name=ch_name,
            brand_config=brand_cfg,
            chapters=chapters,
        )
        meta_res = meta_gen.generate(meta_req)
        proj_svc.save_metadata_draft(
            project.id,
            title=meta_res.title,
            description=meta_res.description,
            tags=meta_res.tags,
            approval_status="approved",
        )
        executed_steps.append(f"Generated & approved SEO Metadata ('{meta_res.title}')")

        # 7. Auto-Generate & Approve 16:9 YouTube Thumbnail & Background Artwork
        base_out = output_base_dir or get_settings().resolved_output_dir()
        clean_out_name = sanitize_output_name(output_name) if output_name else ""
        project_out_dir = base_out / (clean_out_name if clean_out_name else project.id)
        project_out_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = project_out_dir / (
            f"{clean_out_name}_thumbnail_1280x720.png"
            if clean_out_name
            else f"thumbnail_{style_palette}_1280x720.png"
        )

        art_gen = ArtworkGenerator()
        art_res = art_gen.generate(
            project.name,
            thumb_path,
            width=1280,
            height=720,
            style_palette=style_palette,
            subtitle=ch_name,
            badge_text=project.project_type.value.upper(),
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

        # 8. Optional Full 16:9 Video Render + Export Package + 9:16 Vertical Short
        if render_video:
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

        final_track_count = len(proj_svc.list_tracks(project.id))
        return ExpressAutopilotResult(
            channel_id=ch_id,
            channel_name=ch_name,
            project_id=project.id,
            project_name=project.name,
            project_type=project.project_type.value,
            track_count=final_track_count,
            chapters_text=chapters_text,
            seo_title=meta_res.title,
            seo_tags=meta_res.tags,
            thumbnail_path=Path(art_res.output_path),
            output_dir=project_out_dir,
            manifest_path=manifest_path,
            short_video_path=short_video_path,
            executed_steps=executed_steps,
        )
