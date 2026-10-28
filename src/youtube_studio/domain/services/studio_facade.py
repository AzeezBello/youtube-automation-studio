"""Headless Studio Application Facade — clean service boundary shared by Desktop (PySide6), MCP, and Web/SaaS (FastAPI)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from youtube_studio import __version__
from youtube_studio.ai.metadata_generator import MetadataGenerationRequest, MetadataGenerator
from youtube_studio.config import HardwareProbe, get_settings
from youtube_studio.domain.models.channel import (
    NICHE_STYLE_PRESETS,
    VOICE_LIBRARY_PRESETS,
    ChannelBrandConfig,
    apply_niche_preset_to_brand_config,
)
from youtube_studio.domain.models.project import ChapterEntry, ProjectType
from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.domain.services.research_service import ResearchService
from youtube_studio.media import FFmpegService
from youtube_studio.media.nle_exporter import NLEExporterService
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.tts_service import LocalTTSService
from youtube_studio.storage import session_scope


class StudioFacade:
    """UI-agnostic application boundary exposing all core Studio workflows to Desktop, CLI, MCP, and FastAPI."""

    def __init__(self, *, run_mode: str = "desktop_local") -> None:
        self.run_mode = run_mode

    def get_health(self) -> dict[str, Any]:
        """Return system health, active run mode, FFmpeg status, hardware profile, and database record counts."""
        settings = get_settings()
        ffmpeg_info = FFmpegService().get_info()
        hw = HardwareProbe().run()

        with session_scope() as session:
            channels = ChannelService(session).list_active()
            projects = ProjectService(session).list_projects()
            media_files = MediaLibraryService(session).list_media()

        return {
            "status": "ok",
            "app_name": settings.app_name,
            "version": __version__,
            "run_mode": self.run_mode,
            "resource_profile": settings.resource_profile.value,
            "output_dir": str(settings.resolved_output_dir()),
            "data_dir": str(settings.resolved_data_dir()),
            "ffmpeg_available": ffmpeg_info is not None,
            "ffmpeg_version": ffmpeg_info.ffmpeg_version if ffmpeg_info else "fallback_engine",
            "hardware": {
                "cpu_count": hw.cpu_count,
                "total_ram_gb": hw.total_ram_gb,
                "recommended_profile": hw.recommended_profile.value,
            },
            "counts": {
                "active_channels": len(channels),
                "projects": len(projects),
                "indexed_media_files": len(media_files),
            },
        }

    def list_presets(self) -> dict[str, Any]:
        """Return all built-in Niche / Style Presets and Voice Library Presets."""
        return {
            "niche_style_presets": [p.model_dump() for p in NICHE_STYLE_PRESETS.values()],
            "voice_library_presets": [v.model_dump() for v in VOICE_LIBRARY_PRESETS.values()],
        }

    def list_channels(self) -> list[dict[str, Any]]:
        """List all active channel profiles and their brand/preset configurations."""
        with session_scope() as session:
            channels = ChannelService(session).list_active()
        return [
            {
                "id": ch.id,
                "name": ch.name,
                "niche_preset": ch.brand_config.niche_preset,
                "default_aspect_ratio": ch.brand_config.default_aspect_ratio,
                "default_resolution": ch.brand_config.default_resolution,
                "target_duration_minutes": ch.brand_config.target_duration_minutes,
                "preferred_voice_preset": ch.brand_config.preferred_voice_preset,
                "voice_speed": ch.brand_config.voice_speed,
                "style_lock": ch.brand_config.style_lock,
                "reference_image_path": ch.brand_config.reference_image_path,
            }
            for ch in channels
        ]

    def create_or_get_channel(
        self,
        name: str,
        *,
        niche_preset: str = "roots_reggae_mix",
        preferred_voice_preset: str = "warm_male_narrator",
        voice_speed: float = 1.0,
    ) -> dict[str, Any]:
        """Create or retrieve a channel profile configured with a Niche Style Preset and Voice Preset."""
        cfg = apply_niche_preset_to_brand_config(niche_preset)
        cfg.preferred_voice_preset = preferred_voice_preset
        cfg.voice_speed = voice_speed
        with session_scope() as session:
            svc = ChannelService(session)
            existing = next(
                (c for c in svc.list_active() if c.name.lower() == name.strip().lower()),
                None,
            )
            if existing is not None:
                ch = svc.update_brand_config(existing.id, cfg)
            else:
                ch = svc.create(name.strip(), brand_config=cfg)
        return {
            "id": ch.id,
            "name": ch.name,
            "niche_preset": ch.brand_config.niche_preset,
            "preferred_voice_preset": ch.brand_config.preferred_voice_preset,
            "target_duration_minutes": ch.brand_config.target_duration_minutes,
        }

    def list_projects(self, *, channel_id: Optional[str] = None) -> list[dict[str, Any]]:
        """List production projects with track counts, computed duration, and latest metadata draft."""
        with session_scope() as session:
            proj_svc = ProjectService(session)
            projects = proj_svc.list_projects(channel_id=channel_id)
            out: list[dict[str, Any]] = []
            for p in projects:
                tracks = proj_svc.list_tracks(p.id)
                dur_ms = proj_svc.compute_total_duration_ms(p.id)
                draft = proj_svc.get_latest_metadata_draft(p.id)
                out.append(
                    {
                        "id": p.id,
                        "channel_id": p.channel_id,
                        "name": p.name,
                        "project_type": p.project_type.value,
                        "status": p.status.value,
                        "track_count": len(tracks),
                        "duration_ms": dur_ms,
                        "seo_title": draft.title if draft else None,
                    }
                )
            return out

    def get_project_details(self, project_id: str) -> dict[str, Any]:
        """Return full project details including tracks, 00:00 chapters, metadata draft, and registered assets."""
        with session_scope() as session:
            proj_svc = ProjectService(session)
            proj = proj_svc.get_project(project_id)
            if proj is None:
                raise ValueError(f"Project not found: {project_id}")
            tracks = proj_svc.list_tracks(project_id)
            chapters = proj_svc.compute_chapters(project_id)
            draft = proj_svc.get_latest_metadata_draft(project_id)
            assets = proj_svc.list_assets(project_id)
            dur_ms = proj_svc.compute_total_duration_ms(project_id)

        return {
            "id": proj.id,
            "channel_id": proj.channel_id,
            "name": proj.name,
            "project_type": proj.project_type.value,
            "status": proj.status.value,
            "duration_ms": dur_ms,
            "track_count": len(tracks),
            "chapters": [
                {"start_ms": c.start_ms, "timestamp": c.format_timestamp(), "title": c.title}
                for c in chapters
            ],
            "metadata_draft": {
                "version": draft.version,
                "title": draft.title,
                "description": draft.description,
                "tags": draft.tags,
                "approval_status": draft.approval_status,
            }
            if draft
            else None,
            "assets": [
                {
                    "id": a.id,
                    "asset_type": a.asset_type.value,
                    "file_path": a.file_path,
                    "approved": a.approved,
                }
                for a in assets
            ],
        }

    def import_youtube_url_brief(
        self,
        video_url_or_id: str,
        *,
        channel_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Import a YouTube video URL into a Research Project Brief + Idea."""
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            target_ch_id = channel_id or ap.ensure_active_channel()[0]
            r_proj, idea, meta = ResearchService(session).import_from_video_url(
                target_ch_id,
                video_url_or_id,
            )
        return {
            "channel_id": target_ch_id,
            "research_project_id": r_proj.id,
            "research_project_name": r_proj.name,
            "idea_id": idea.id,
            "idea_title": idea.title,
            "video_id": meta.get("video_id"),
            "extracted_chapters": meta.get("chapters", []),
            "tags": meta.get("tags", []),
        }

    def score_titles(
        self,
        project_name: str,
        *,
        channel_name: str = "Echoes of Livity",
        niche_preset: str = "roots_reggae_mix",
        seed_keywords: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Generate and rank 5 YouTube title candidates using transparent criteria (Length, Keywords, Tone)."""
        cfg = apply_niche_preset_to_brand_config(niche_preset)
        req = MetadataGenerationRequest(
            project_name=project_name,
            project_type=ProjectType.MIX,
            channel_name=channel_name,
            brand_config=cfg,
            chapters=[ChapterEntry(start_ms=0, title=project_name)],
            keywords=seed_keywords or [],
            candidate_count=5,
        )
        res = MetadataGenerator().generate(req)
        best = res.highest_scoring_title
        return {
            "selected_title": res.title,
            "highest_scoring_title": {
                "title": best.title,
                "total_score": best.total_score,
                "explanation": best.explanation,
                "length_ok": best.length_ok,
                "matched_keywords": best.matched_keywords,
            }
            if best
            else None,
            "ranked_candidates": [
                {
                    "title": sc.title,
                    "total_score": sc.total_score,
                    "length_score": sc.length_score,
                    "keyword_score": sc.keyword_score,
                    "brand_fit_score": sc.brand_fit_score,
                    "explanation": sc.explanation,
                    "length_ok": sc.length_ok,
                    "matched_keywords": sc.matched_keywords,
                }
                for sc in res.scored_candidates
            ],
            "tags": res.tags,
        }

    def generate_structured_script(
        self,
        topic: str,
        *,
        channel_name: str = "Echoes of Livity",
        tone: str = "warm, conscious roots reggae & dub sound system session",
        target_duration_minutes: int = 15,
    ) -> dict[str, Any]:
        """Generate a 3-step structured script (Hook → Timestamped Outline → Full Narration Script)."""
        draft = MetadataGenerator().generate_structured_script(
            topic,
            channel_name=channel_name,
            tone=tone,
            target_duration_minutes=target_duration_minutes,
        )
        return {
            "topic": topic,
            "hook": draft.hook,
            "outline": draft.outline,
            "full_script": draft.full_script,
            "estimated_word_count": draft.estimated_word_count,
            "target_duration_minutes": draft.target_duration_minutes,
            "extracted_chapters": [
                {"start_ms": c.start_ms, "timestamp": c.format_timestamp(), "title": c.title}
                for c in draft.extracted_chapters
            ],
        }

    def synthesize_voiceover(
        self,
        text: str,
        *,
        preset_key: str = "warm_male_narrator",
        speed: float = 1.0,
        output_filename: Optional[str] = None,
    ) -> dict[str, Any]:
        """Synthesize local AI voiceover WAV and index it into the Music Library."""
        out_dir = get_settings().resolved_data_dir() / "music_library" / "Voiceovers"
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = output_filename or f"voiceover_{preset_key}.wav"
        wav_path = out_dir / fname
        res = LocalTTSService().synthesize(
            text,
            wav_path,
            preset_key=preset_key,
            speed=speed,
        )
        with session_scope() as session:
            info = MediaScanner().inspect_file(res.output_path)
            info.metadata["title"] = f"Voiceover — {res.voice_label}"
            info.metadata["folder"] = "Voiceovers"
            saved = MediaLibraryService(session).upsert(info)
        return {
            "media_file_id": saved.id,
            "output_path": str(res.output_path),
            "duration_ms": res.duration_ms,
            "voice_preset": res.voice_preset_key,
            "voice_label": res.voice_label,
            "gender": res.gender,
            "speed": res.speed,
            "engine_used": res.engine_used,
            "word_count": res.word_count,
        }

    def run_autopilot(
        self,
        *,
        channel_id: Optional[str] = None,
        project_name: Optional[str] = None,
        source_folder: Optional[str | Path] = None,
        library_folder_name: Optional[str] = None,
        youtube_url: Optional[str] = None,
        script_text: Optional[str] = None,
        synthesize_voiceover: bool = False,
        voice_preset: Optional[str] = None,
        voice_speed: float = 1.0,
        niche_preset: Optional[str] = "roots_reggae_mix",
        target_duration_minutes: int = 60,
        output_name: Optional[str] = None,
        render_video: bool = True,
        export_short: bool = True,
    ) -> dict[str, Any]:
        """Execute the 1-Click Express Auto-Pilot workflow and return the package summary."""
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            if youtube_url:
                res = ap.run_autopilot_from_youtube_url(
                    youtube_url,
                    channel_id=channel_id,
                    niche_preset=niche_preset,
                    target_duration_minutes=target_duration_minutes,
                    synthesize_voiceover=synthesize_voiceover,
                    voice_preset=voice_preset,
                    voice_speed=voice_speed,
                    render_video=render_video,
                    export_short=export_short,
                )
            else:
                res = ap.run_autopilot(
                    channel_id=channel_id,
                    project_name=project_name,
                    source_folder=source_folder,
                    library_folder_name=library_folder_name,
                    script_text=script_text,
                    synthesize_voiceover=synthesize_voiceover,
                    voice_preset=voice_preset,
                    voice_speed=voice_speed,
                    niche_preset=niche_preset,
                    target_duration_minutes=target_duration_minutes,
                    output_name=output_name,
                    render_video=render_video,
                    export_short=export_short,
                )
        return {
            "channel_id": res.channel_id,
            "channel_name": res.channel_name,
            "project_id": res.project_id,
            "project_name": res.project_name,
            "project_type": res.project_type,
            "track_count": res.track_count,
            "seo_title": res.seo_title,
            "seo_tags": res.seo_tags,
            "title_score_summary": res.title_score_summary,
            "chapters_text": res.chapters_text,
            "thumbnail_path": str(res.thumbnail_path) if res.thumbnail_path else None,
            "output_dir": str(res.output_dir) if res.output_dir else None,
            "manifest_path": str(res.manifest_path) if res.manifest_path else None,
            "short_video_path": str(res.short_video_path) if res.short_video_path else None,
            "voiceover_path": str(res.voiceover_path) if res.voiceover_path else None,
            "nle_fcpxml_path": str(res.nle_fcpxml_path) if res.nle_fcpxml_path else None,
            "executed_steps": res.executed_steps,
        }

    def run_daily_channel_autopilot(
        self,
        *,
        channel_name: str = "Echoes of Livity",
        niche_preset: str = "roots_reggae_mix",
        voice_preset: str = "warm_male_narrator",
        source_folder: Optional[str | Path] = None,
        library_folder_name: Optional[str] = None,
        youtube_url: Optional[str] = None,
        script_text: Optional[str] = None,
        synthesize_voiceover: bool = False,
        target_duration_minutes: int = 60,
        render_video: bool = True,
        export_short: bool = True,
    ) -> dict[str, Any]:
        """Locked daily personal workflow: ensure channel + preset -> research/audio -> script/voice -> mix/render -> ready-to-upload package."""
        ch = self.create_or_get_channel(
            channel_name,
            niche_preset=niche_preset,
            preferred_voice_preset=voice_preset,
        )
        return self.run_autopilot(
            channel_id=ch["id"],
            source_folder=source_folder,
            library_folder_name=library_folder_name,
            youtube_url=youtube_url,
            script_text=script_text,
            synthesize_voiceover=synthesize_voiceover,
            voice_preset=voice_preset,
            niche_preset=niche_preset,
            target_duration_minutes=target_duration_minutes,
            render_video=render_video,
            export_short=export_short,
        )

