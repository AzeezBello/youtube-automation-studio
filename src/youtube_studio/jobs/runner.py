"""Stage-aware production job runner with checkpointing and intermediate artifact reuse."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from youtube_studio.config import get_settings
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.job import Job, JobType
from youtube_studio.domain.models.project import AssetType, ProjectStatus
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.job_service import JobService
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.media.mixer import AudioMixerService, MixTrackInput
from youtube_studio.media.renderer import (
    RenderSpec,
    VideoRendererService,
    VisualFXConfig,
    VisualizerStyle,
)
from youtube_studio.media.thumbnail import ThumbnailEngine, ThumbnailSpec
from youtube_studio.media.validator import MediaValidator

PRODUCTION_STAGES: tuple[tuple[str, float], ...] = (
    ("validate_inputs", 0.15),
    ("mix_audio", 0.40),
    ("generate_thumbnail", 0.60),
    ("render_video", 0.85),
    ("validate_output", 0.95),
    ("package", 1.00),
)


@dataclass
class ProductionRunSummary:
    job: Job
    project_id: str
    output_dir: Path
    reused_stages: list[str] = field(default_factory=list)
    executed_stages: list[str] = field(default_factory=list)
    manifest_path: Optional[Path] = None


class ProductionJobRunner:
    """Executes and resumes multi-stage music-to-video production jobs."""

    def __init__(
        self,
        session: Session,
        *,
        mixer: Optional[AudioMixerService] = None,
        thumbnail_engine: Optional[ThumbnailEngine] = None,
        renderer: Optional[VideoRendererService] = None,
        validator: Optional[MediaValidator] = None,
    ) -> None:
        self._session = session
        self._jobs = JobService(session)
        self._projects = ProjectService(session)
        self._channels = ChannelService(session)
        self._media = MediaLibraryService(session)
        self._mixer = mixer or AudioMixerService()
        self._thumbnails = thumbnail_engine or ThumbnailEngine()
        self._renderer = renderer or VideoRendererService()
        self._validator = validator or MediaValidator()

    def enqueue_production_job(
        self,
        project_id: str,
        *,
        output_dir: Optional[Path] = None,
        enable_waveform_overlay: bool = False,
        visualizer_style: str = "none",
        visual_fx: Optional[dict[str, bool]] = None,
    ) -> Job:
        project = self._projects.get_project(project_id)
        if project is None:
            raise ValueError(f"Project {project_id} not found")

        settings = get_settings()
        resolved_out = (
            output_dir.expanduser().resolve()
            if output_dir is not None
            else (settings.resolved_data_dir() / "jobs" / project_id)
        )
        return self._jobs.enqueue(
            JobType.PACKAGE,
            channel_id=project.channel_id,
            project_id=project.id,
            stage="validate_inputs",
            input_data={
                "output_dir": str(resolved_out),
                "enable_waveform_overlay": enable_waveform_overlay,
                "visualizer_style": visualizer_style,
                "visual_fx": visual_fx or {},
            },
        )

    def run_job(
        self,
        job_id: str,
        *,
        on_progress: Optional[Callable[[str, float], None]] = None,
        fail_at_stage: Optional[str] = None,
    ) -> ProductionRunSummary:
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        if not job.project_id:
            raise ValueError(f"Job {job_id} has no associated project_id")

        project = self._projects.get_project(job.project_id)
        if project is None:
            raise ValueError(f"Project {job.project_id} not found")

        channel = self._channels.get(project.channel_id)
        brand = channel.brand_config if channel else ChannelBrandConfig()

        settings = get_settings()
        out_dir_str = job.input_data.get("output_dir")
        out_dir = (
            Path(out_dir_str).expanduser().resolve()
            if out_dir_str
            else (settings.resolved_data_dir() / "jobs" / project.id)
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        summary = ProductionRunSummary(job=job, project_id=project.id, output_dir=out_dir)

        completed_stages: list[str] = list(job.output_data.get("completed_stages", []))
        artifacts: dict[str, str] = dict(job.output_data.get("artifacts", {}))

        self._projects.update_project_status(project.id, ProjectStatus.IN_PROGRESS)
        current_stage = "validate_inputs"

        try:
            for stage_name, stage_progress in PRODUCTION_STAGES:
                current_stage = stage_name
                job = self._jobs.mark_running(job.id, stage=stage_name)
                if on_progress:
                    on_progress(stage_name, job.progress)

                if fail_at_stage == stage_name:
                    raise RuntimeError(f"Simulated failure at stage '{stage_name}'")

                if self._can_reuse_stage(stage_name, completed_stages, artifacts):
                    summary.reused_stages.append(stage_name)
                    job.progress = stage_progress
                    self._jobs.update(job)
                    continue

                if stage_name == "validate_inputs":
                    mix_inputs = self._stage_validate_inputs(project.id)
                    artifacts["track_count"] = str(len(mix_inputs))

                elif stage_name == "mix_audio":
                    mix_inputs = self._stage_validate_inputs(project.id)
                    mixed_path = out_dir / "mixed_audio.wav"
                    mix_res = self._mixer.mix(mix_inputs, mixed_path)
                    artifacts["mixed_audio"] = str(mix_res.output_path)
                    artifacts["mixed_duration_ms"] = str(mix_res.duration_ms)
                    self._projects.register_asset(
                        project.id,
                        AssetType.MIXED_AUDIO,
                        str(mix_res.output_path),
                        provenance={"filtergraph": mix_res.filtergraph},
                        approved=True,
                    )

                elif stage_name == "generate_thumbnail":
                    palette = str(brand.thumbnail_style.get("palette", "warm_earth"))
                    motif = str(brand.thumbnail_style.get("motif", "vinyl_and_sound_system"))
                    res_w, res_h = self._parse_resolution(brand.default_resolution)

                    thumb_path = out_dir / "thumbnail.png"
                    thumb_spec = ThumbnailSpec(
                        title=project.name,
                        subtitle=channel.name if channel else "YouTube Automation Studio",
                        badge_text=project.project_type.value.replace("_", " ").upper(),
                        palette=palette,
                        aspect_ratio=brand.default_aspect_ratio,
                        motif=motif,
                    )
                    thumb_res = self._thumbnails.render(thumb_spec, thumb_path)
                    artifacts["thumbnail"] = str(thumb_res.output_path)
                    self._projects.register_asset(
                        project.id,
                        AssetType.THUMBNAIL,
                        str(thumb_res.output_path),
                        checksum=thumb_res.checksum,
                        provenance={"palette": thumb_res.palette},
                        approved=True,
                    )

                    bg_path = out_dir / "background.png"
                    bg_spec = ThumbnailSpec(
                        title=project.name,
                        subtitle=channel.name if channel else None,
                        palette=palette,
                        aspect_ratio=brand.default_aspect_ratio,
                        width=res_w,
                        height=res_h,
                        motif=motif,
                    )
                    bg_res = self._thumbnails.render(bg_spec, bg_path)
                    artifacts["background"] = str(bg_res.output_path)
                    self._projects.register_asset(
                        project.id,
                        AssetType.BACKGROUND_IMAGE,
                        str(bg_res.output_path),
                        checksum=bg_res.checksum,
                        approved=True,
                    )

                elif stage_name == "render_video":
                    mixed_audio_path = Path(artifacts["mixed_audio"])
                    bg_image_path = Path(artifacts.get("background") or artifacts["thumbnail"])
                    video_path = out_dir / "video.mp4"
                    expected_dur = int(artifacts.get("mixed_duration_ms", "1000"))
                    vis_str = str(job.input_data.get("visualizer_style", "none"))
                    fx_dict = dict(job.input_data.get("visual_fx", {}))
                    chapters = self._projects.compute_chapters(project.id)
                    render_spec = RenderSpec(
                        audio_path=mixed_audio_path,
                        image_path=bg_image_path,
                        output_path=video_path,
                        resolution=brand.default_resolution,
                        enable_waveform_overlay=bool(
                            job.input_data.get("enable_waveform_overlay", False)
                        ),
                        visualizer_style=VisualizerStyle(vis_str)
                        if vis_str in {v.value for v in VisualizerStyle}
                        else VisualizerStyle.NONE,
                        visual_fx=VisualFXConfig(
                            now_playing_overlay=bool(fx_dict.get("now_playing_overlay", False)),
                            progress_bar=bool(fx_dict.get("progress_bar", False)),
                            slow_zoom=bool(fx_dict.get("slow_zoom", False)),
                            film_grain=bool(fx_dict.get("film_grain", False)),
                            vignette=bool(fx_dict.get("vignette", False)),
                            spinning_vinyl=bool(fx_dict.get("spinning_vinyl", False)),
                        ),
                        chapters=chapters,
                        duration_ms=expected_dur,
                    )
                    render_res = self._renderer.render(render_spec)
                    if render_res.srt_path and render_res.srt_path.exists():
                        artifacts["now_playing_srt"] = str(render_res.srt_path)
                    artifacts["rendered_video"] = str(render_res.output_path)
                    self._projects.register_asset(
                        project.id,
                        AssetType.RENDERED_VIDEO,
                        str(render_res.output_path),
                        provenance={"resolution": render_res.resolution},
                        approved=True,
                    )
                    self._projects.update_project_status(project.id, ProjectStatus.RENDERED)

                elif stage_name == "validate_output":
                    video_path = Path(artifacts["rendered_video"])
                    audio_path = Path(artifacts["mixed_audio"])
                    thumb_path = Path(artifacts["thumbnail"])
                    expected_dur = int(artifacts.get("mixed_duration_ms", "1000"))

                    v_rep = self._validator.validate_video(
                        video_path,
                        expected_duration_ms=expected_dur,
                        expected_resolution=brand.default_resolution,
                    )
                    if not v_rep.is_valid:
                        raise RuntimeError(f"Video validation failed: {'; '.join(v_rep.errors)}")

                    a_rep = self._validator.validate_audio(
                        audio_path,
                        expected_duration_ms=expected_dur,
                    )
                    if not a_rep.is_valid:
                        raise RuntimeError(f"Audio validation failed: {'; '.join(a_rep.errors)}")

                    i_rep = self._validator.validate_image(thumb_path)
                    if not i_rep.is_valid:
                        raise RuntimeError(
                            f"Thumbnail validation failed: {'; '.join(i_rep.errors)}"
                        )

                elif stage_name == "package":
                    chapters = self._projects.compute_chapters(project.id)
                    chapter_lines = [f"{c.format_timestamp()} {c.title}" for c in chapters]
                    description = (
                        f"{project.name}\n\nTracklist:\n" + "\n".join(chapter_lines)
                        if chapter_lines
                        else project.name
                    )
                    draft = self._projects.save_metadata_draft(
                        project.id,
                        title=project.name,
                        description=description,
                        tags=list(brand.default_tags),
                        chapters=chapters,
                        approval_status="draft",
                    )

                    manifest_path = out_dir / "package_manifest.json"
                    manifest_payload: dict[str, Any] = {
                        "project_id": project.id,
                        "channel_id": project.channel_id,
                        "project_name": project.name,
                        "project_type": project.project_type.value,
                        "resolution": brand.default_resolution,
                        "aspect_ratio": brand.default_aspect_ratio,
                        "artifacts": artifacts,
                        "metadata_draft": {
                            "id": draft.id,
                            "version": draft.version,
                            "title": draft.title,
                            "description": draft.description,
                            "tags": draft.tags,
                            "chapters": [
                                {"start_ms": c.start_ms, "timestamp": c.format_timestamp(), "title": c.title}
                                for c in draft.chapters
                            ],
                        },
                    }
                    manifest_path.write_text(
                        json.dumps(manifest_payload, indent=2),
                        encoding="utf-8",
                    )
                    artifacts["package_manifest"] = str(manifest_path)
                    summary.manifest_path = manifest_path
                    self._projects.register_asset(
                        project.id,
                        AssetType.PACKAGE_MANIFEST,
                        str(manifest_path),
                        approved=True,
                    )
                    self._projects.update_project_status(
                        project.id,
                        ProjectStatus.PACKAGED,
                        manifest_path=str(manifest_path),
                    )

                if stage_name not in completed_stages:
                    completed_stages.append(stage_name)
                summary.executed_stages.append(stage_name)

                job.progress = stage_progress
                job.output_data["completed_stages"] = list(completed_stages)
                job.output_data["artifacts"] = dict(artifacts)
                self._jobs.update(job)
                self._session.commit()

            job = self._jobs.mark_completed(
                job.id,
                output={
                    "completed_stages": completed_stages,
                    "artifacts": artifacts,
                },
            )
            self._session.commit()
            summary.job = job
            return summary

        except Exception as exc:
            job.output_data["completed_stages"] = list(completed_stages)
            job.output_data["artifacts"] = dict(artifacts)
            self._jobs.update(job)
            failed_job = self._jobs.mark_failed(
                job.id,
                error={"stage": current_stage, "message": str(exc)},
            )
            self._session.commit()
            summary.job = failed_job
            raise

    def _stage_validate_inputs(self, project_id: str) -> list[MixTrackInput]:
        tracks = self._projects.list_tracks(project_id)
        if not tracks:
            raise ValueError(f"Project {project_id} has no tracks to produce")

        mix_inputs: list[MixTrackInput] = []
        for pt in tracks:
            media = self._media.get(pt.media_file_id)
            if media is None:
                raise ValueError(f"MediaFile {pt.media_file_id} not found in library")
            media_path = Path(media.path)
            if not media_path.exists():
                raise FileNotFoundError(f"Media file missing on disk: {media_path}")
            mix_inputs.append(
                MixTrackInput(
                    source_path=media_path,
                    source_duration_ms=media.duration_ms,
                    trim_start_ms=pt.trim_start_ms,
                    trim_end_ms=pt.trim_end_ms,
                    gain_db=pt.gain_db,
                    fade_in_ms=pt.fade_in_ms,
                    fade_out_ms=pt.fade_out_ms,
                    transition_config=pt.transition_config,
                )
            )
        return mix_inputs

    @staticmethod
    def _can_reuse_stage(
        stage_name: str,
        completed_stages: list[str],
        artifacts: dict[str, str],
    ) -> bool:
        if stage_name not in completed_stages:
            return False
        required_keys: dict[str, tuple[str, ...]] = {
            "validate_inputs": (),
            "mix_audio": ("mixed_audio",),
            "generate_thumbnail": ("thumbnail", "background"),
            "render_video": ("rendered_video",),
            "validate_output": ("rendered_video", "mixed_audio", "thumbnail"),
            "package": ("package_manifest",),
        }
        for key in required_keys.get(stage_name, ()):
            file_str = artifacts.get(key)
            if not file_str:
                return False
            p = Path(file_str)
            if not p.exists() or p.stat().st_size == 0:
                return False
        return True

    @staticmethod
    def _parse_resolution(resolution: str) -> tuple[int, int]:
        parts = resolution.lower().split("x")
        if len(parts) == 2:
            try:
                return int(parts[0]), int(parts[1])
            except ValueError:
                pass
        return 1920, 1080
