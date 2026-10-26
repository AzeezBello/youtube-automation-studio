"""End-to-end integration test for P1 music-to-video production & stage recovery."""

from __future__ import annotations

import array
import json
import math
import os
import tempfile
import wave
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.job import JobStatus
from youtube_studio.domain.models.project import (
    ProjectStatus,
    ProjectType,
    TransitionConfig,
    TransitionType,
)
from youtube_studio.domain.services import (
    ChannelService,
    MediaLibraryService,
    ProjectService,
)
from youtube_studio.jobs.runner import ProductionJobRunner
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.storage import orm  # noqa: F401
from youtube_studio.storage.database import Base


def _write_wav(path: Path, duration_sec: float = 3.0, freq: float = 440.0) -> Path:
    rate = 8000
    frames = int(rate * duration_sec)
    data = array.array(
        "h",
        [int(10000 * math.sin(2.0 * math.pi * freq * i / rate)) for i in range(frames)],
    )
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(data.tobytes())
    return path


@pytest.fixture()
def session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.close()
    engine.dispose()
    Path(path).unlink(missing_ok=True)


def test_full_production_pipeline_and_stage_recovery(session):
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        music_dir = workspace / "music"
        music_dir.mkdir()
        _write_wav(music_dir / "01_roots_intro.wav", duration_sec=4.0, freq=432.0)
        _write_wav(music_dir / "02_dubplate_step.wav", duration_sec=4.0, freq=528.0)

        # 1. Create channel
        ch_svc = ChannelService(session)
        channel = ch_svc.create(
            "Echoes of Livity",
            brand=ChannelBrandConfig(
                default_aspect_ratio="16:9",
                default_resolution="1280x720",
                default_tags=["roots reggae", "dub"],
                thumbnail_style={"palette": "warm_earth", "motif": "vinyl_and_sound_system"},
            ),
        )

        # 2. Scan media folder into library
        media_svc = MediaLibraryService(session)
        scan_summary = MediaScanner().scan_directory(
            music_dir,
            channel_id=channel.id,
            media_service=media_svc,
        )
        assert len(scan_summary.scanned_files) == 2

        # 3. Create project & arrange tracks with crossfade
        proj_svc = ProjectService(session)
        project = proj_svc.create_project(
            channel.id,
            "Roots & Culture Session #1",
            project_type=ProjectType.MIX,
        )
        t1 = proj_svc.add_track(
            project.id,
            scan_summary.scanned_files[0].id,
            fade_in_ms=500,
            transition_config=TransitionConfig(
                transition_type=TransitionType.CROSSFADE,
                overlap_ms=1000,
            ),
        )
        t2 = proj_svc.add_track(
            project.id,
            scan_summary.scanned_files[1].id,
            fade_out_ms=500,
            transition_config=TransitionConfig(transition_type=TransitionType.NONE, overlap_ms=0),
        )

        # Verify chapters (Track 1 @ 00:00, Track 2 @ 00:03 due to 1s crossfade on 4s track)
        chapters = proj_svc.compute_chapters(project.id)
        assert len(chapters) == 2
        assert chapters[0].format_timestamp() == "00:00"
        assert chapters[1].format_timestamp() == "00:03"
        assert proj_svc.compute_total_duration_ms(project.id) == 7000

        # Test track reordering and restoring order
        reordered = proj_svc.reorder_tracks(project.id, [t2.id, t1.id])
        assert [r.id for r in reordered] == [t2.id, t1.id]
        proj_svc.reorder_tracks(project.id, [t1.id, t2.id])
        session.commit()

        # 4. Enqueue production job & simulate interruption at render_video
        out_dir = workspace / "output"
        runner = ProductionJobRunner(session)
        job = runner.enqueue_production_job(project.id, output_dir=out_dir)
        session.commit()

        with pytest.raises(RuntimeError, match="Simulated failure at stage 'render_video'"):
            runner.run_job(job.id, fail_at_stage="render_video")

        # Verify intermediate stages were checkpointed
        failed_job = runner._jobs.get(job.id)
        assert failed_job is not None
        assert failed_job.status == JobStatus.FAILED
        assert failed_job.output_data["completed_stages"] == [
            "validate_inputs",
            "mix_audio",
            "generate_thumbnail",
        ]
        assert (out_dir / "mixed_audio.wav").exists()
        assert (out_dir / "thumbnail.png").exists()

        # 5. Resume the failed job – earlier stages must be reused!
        summary = runner.run_job(job.id)
        assert summary.job.status == JobStatus.COMPLETED
        assert summary.reused_stages == [
            "validate_inputs",
            "mix_audio",
            "generate_thumbnail",
        ]
        assert summary.executed_stages == [
            "render_video",
            "validate_output",
            "package",
        ]
        assert summary.manifest_path is not None and summary.manifest_path.exists()

        manifest = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
        assert manifest["project_id"] == project.id
        assert len(manifest["metadata_draft"]["chapters"]) == 2

        updated_project = proj_svc.get_project(project.id)
        assert updated_project is not None
        assert updated_project.status == ProjectStatus.PACKAGED
