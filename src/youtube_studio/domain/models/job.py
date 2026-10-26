"""Persistent job / work-item models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from youtube_studio.domain.models._compat import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    SCAN_LIBRARY = "scan_library"
    MIX_AUDIO = "mix_audio"
    RENDER_VIDEO = "render_video"
    GENERATE_THUMBNAIL = "generate_thumbnail"
    GENERATE_METADATA = "generate_metadata"
    RESEARCH_QUERY = "research_query"
    ANALYTICS_SYNC = "analytics_sync"
    UPLOAD = "upload"
    PACKAGE = "package"
    VALIDATE = "validate"


class Job(BaseModel):
    id: str = Field(default_factory=_new_id)
    channel_id: Optional[str] = None
    project_id: Optional[str] = None
    job_type: JobType
    stage: Optional[str] = None
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0  # 0.0 – 1.0
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[dict[str, Any]] = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def mark_running(self, stage: Optional[str] = None) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = self.started_at or _utcnow()
        if stage:
            self.stage = stage

    def mark_completed(self, output: Optional[dict[str, Any]] = None) -> None:
        self.status = JobStatus.COMPLETED
        self.progress = 1.0
        self.completed_at = _utcnow()
        if output:
            self.output_data.update(output)

    def mark_failed(self, error: dict[str, Any]) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = _utcnow()
        self.retry_count += 1
