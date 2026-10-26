"""Retention enforcement job runner – purges expired public_api_30d and transient research records."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from youtube_studio.domain.models.job import Job, JobType
from youtube_studio.domain.services.job_service import JobService
from youtube_studio.domain.services.research_service import ResearchService


class RetentionJobRunner:
    """Runs and logs scheduled or on-demand API data retention cleanup jobs."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._jobs = JobService(session)
        self._research = ResearchService(session)

    def run_cleanup(self, *, now: Optional[datetime] = None) -> tuple[Job, int]:
        job = self._jobs.enqueue(
            JobType.VALIDATE,
            stage="purge_expired_research_sources",
            input_data={"policy": "public_api_30d"},
        )
        self._jobs.mark_running(job.id, stage="purge_expired_research_sources")
        purged_count = self._research.purge_expired_sources(now=now)
        completed_job = self._jobs.mark_completed(
            job.id,
            output={"purged_sources_count": purged_count},
        )
        self._session.commit()
        return completed_job, purged_count
