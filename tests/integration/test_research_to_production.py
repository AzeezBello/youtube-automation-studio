"""End-to-end integration test for P2 research workspace, retention purge, and production hand-off."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.project import ProjectType
from youtube_studio.domain.services import (
    ChannelService,
    ProjectService,
    ResearchService,
)
from youtube_studio.jobs.retention_runner import RetentionJobRunner
from youtube_studio.research.providers.base import ResearchResult, RetentionClass
from youtube_studio.storage import orm  # noqa: F401
from youtube_studio.storage.database import Base


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


def test_research_retention_purge_and_production_handoff(session):
    ch_svc = ChannelService(session)
    channel = ch_svc.create(
        "Echoes of Livity",
        brand=ChannelBrandConfig(default_tags=["roots reggae", "dub"]),
    )

    res_svc = ResearchService(session)
    rp = res_svc.create_research_project(
        "1970s Steppers & Dub Research",
        channel_id=channel.id,
        brief="Focus on deep bassline steppers from 1976-1979 with chapter timestamps.",
    )

    now = datetime.now(timezone.utc)
    # 1. Record a fresh public API search result (expires in 30 days)
    fresh_res = ResearchResult(
        provider="youtube_data_api",
        source_type="search_result",
        external_reference="youtube:video:fresh_01",
        retrieved_at=now,
        retention_class=RetentionClass.PUBLIC_API_30D,
        payload={"title": "1978 Roots Steppers Mix", "channel_title": "Dub Vault"},
    )
    res_svc.record_source(fresh_res, research_project_id=rp.id)

    # 2. Record a 35-day-old public API search result (already expired)
    old_time = now - timedelta(days=35)
    expired_res = ResearchResult(
        provider="youtube_data_api",
        source_type="search_result",
        external_reference="youtube:video:expired_01",
        retrieved_at=old_time,
        retention_class=RetentionClass.PUBLIC_API_30D,
        payload={"title": "Old Cached Video", "channel_title": "Old Channel"},
    )
    res_svc.record_source(expired_res, research_project_id=rp.id)

    # 3. Add a competitor watchlist channel
    watch_entry = res_svc.add_to_watchlist(
        "UC_STEPPERS_01",
        "Steppers Sound System",
        research_project_id=rp.id,
        custom_url="@stepperssound",
    )
    assert watch_entry.title == "Steppers Sound System"
    assert len(res_svc.list_watchlist(research_project_id=rp.id)) == 1

    # Active sources should exclude the expired one even before purge
    active_sources = res_svc.list_sources(research_project_id=rp.id, include_expired=False)
    all_sources = res_svc.list_sources(research_project_id=rp.id, include_expired=True)
    assert len(active_sources) == 2
    assert len(all_sources) == 3

    # 4. Run RetentionJobRunner to purge expired records from SQLite
    ret_runner = RetentionJobRunner(session)
    cleanup_job, purged_count = ret_runner.run_cleanup(now=now)
    assert purged_count == 1
    assert cleanup_job.output_data["purged_sources_count"] == 1
    assert len(res_svc.list_sources(research_project_id=rp.id, include_expired=True)) == 2

    # 5. Save an idea and hand it off to Production
    idea = res_svc.save_idea(
        "Heavyweight 1978 Steppers Dub Session",
        channel_id=channel.id,
        research_project_id=rp.id,
        rationale="Strong audience demand for late-70s militant steppers mixes.",
        evidence=[{"external_reference": "youtube:video:fresh_01"}],
    )
    session.commit()

    prod_project, draft = res_svc.handoff_idea_to_production(
        idea.id,
        project_type=ProjectType.MIX,
    )
    session.commit()

    assert prod_project.channel_id == channel.id
    assert prod_project.name == "Heavyweight 1978 Steppers Dub Session"
    assert prod_project.project_type == ProjectType.MIX

    assert draft.title == "Heavyweight 1978 Steppers Dub Session"
    assert "roots reggae" in draft.tags
    assert "steppers" in draft.tags
    assert "Focus on deep bassline steppers" in (draft.description or "")

    updated_idea = res_svc.get_idea(idea.id)
    assert updated_idea is not None
    assert updated_idea.status == "in_production"

    # Verify the project is visible in ProjectService
    proj_svc = ProjectService(session)
    assert proj_svc.get_project(prod_project.id) is not None
