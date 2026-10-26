"""Persistent job queue service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from youtube_studio.domain.models.job import Job, JobStatus, JobType
from youtube_studio.storage.orm import JobORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        job_type: JobType,
        *,
        channel_id: Optional[str] = None,
        project_id: Optional[str] = None,
        input_data: Optional[dict[str, Any]] = None,
        stage: Optional[str] = None,
    ) -> Job:
        now = _utcnow()
        domain = Job(
            job_type=job_type,
            channel_id=channel_id,
            project_id=project_id,
            stage=stage,
            status=JobStatus.QUEUED,
            input_data=input_data or {},
            created_at=now,
        )
        orm = self._to_orm(domain)
        self._session.add(orm)
        self._session.flush()
        return domain

    def get(self, job_id: str) -> Optional[Job]:
        orm = self._session.get(JobORM, job_id)
        return self._to_domain(orm) if orm else None

    def list_by_status(self, status: JobStatus, limit: int = 50) -> list[Job]:
        stmt = (
            select(JobORM)
            .where(JobORM.status == status.value)
            .order_by(JobORM.created_at)
            .limit(limit)
        )
        return [self._to_domain(o) for o in self._session.scalars(stmt)]

    def update(self, job: Job) -> Job:
        orm = self._session.get(JobORM, job.id)
        if orm is None:
            raise ValueError(f"Job {job.id} not found")
        orm.stage = job.stage
        orm.status = job.status.value
        orm.progress = job.progress
        orm.input_json = json.dumps(job.input_data)
        orm.output_json = json.dumps(job.output_data)
        orm.error_json = json.dumps(job.error) if job.error else None
        orm.retry_count = job.retry_count
        orm.started_at = job.started_at
        orm.completed_at = job.completed_at
        self._session.flush()
        return job

    def mark_running(self, job_id: str, stage: Optional[str] = None) -> Job:
        job = self.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        job.mark_running(stage)
        return self.update(job)

    def mark_completed(self, job_id: str, output: Optional[dict[str, Any]] = None) -> Job:
        job = self.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        job.mark_completed(output)
        return self.update(job)

    def mark_failed(self, job_id: str, error: dict[str, Any]) -> Job:
        job = self.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        job.mark_failed(error)
        return self.update(job)

    @staticmethod
    def _to_orm(job: Job) -> JobORM:
        return JobORM(
            id=job.id,
            channel_id=job.channel_id,
            project_id=job.project_id,
            job_type=job.job_type.value,
            stage=job.stage,
            status=job.status.value,
            progress=job.progress,
            input_json=json.dumps(job.input_data),
            output_json=json.dumps(job.output_data),
            error_json=json.dumps(job.error) if job.error else None,
            retry_count=job.retry_count,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    @staticmethod
    def _to_domain(orm: JobORM) -> Job:
        return Job(
            id=orm.id,
            channel_id=orm.channel_id,
            project_id=orm.project_id,
            job_type=JobType(orm.job_type),
            stage=orm.stage,
            status=JobStatus(orm.status),
            progress=orm.progress,
            input_data=json.loads(orm.input_json or "{}"),
            output_data=json.loads(orm.output_json or "{}"),
            error=json.loads(orm.error_json) if orm.error_json else None,
            retry_count=orm.retry_count,
            created_at=orm.created_at,
            started_at=orm.started_at,
            completed_at=orm.completed_at,
        )
