"""Unit tests for JobService."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from youtube_studio.domain.models.job import JobStatus, JobType
from youtube_studio.domain.services.job_service import JobService
from youtube_studio.storage.database import Base
from youtube_studio.storage import orm  # noqa: F401


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


def test_enqueue_and_lifecycle(session):
    svc = JobService(session)
    job = svc.enqueue(
        JobType.RENDER_VIDEO,
        input_data={"source": "/tmp/track.mp3"},
        stage="validate",
    )
    session.commit()

    assert job.status == JobStatus.QUEUED
    queued = svc.list_by_status(JobStatus.QUEUED)
    assert len(queued) == 1

    running = svc.mark_running(job.id, stage="mix")
    session.commit()
    assert running.status == JobStatus.RUNNING
    assert running.stage == "mix"

    done = svc.mark_completed(job.id, output={"path": "/tmp/out.mp4"})
    session.commit()
    assert done.status == JobStatus.COMPLETED
    assert done.progress == 1.0
    assert done.output_data["path"] == "/tmp/out.mp4"
