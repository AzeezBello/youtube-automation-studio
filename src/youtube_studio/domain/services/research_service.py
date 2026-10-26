"""Research workspace service – projects, provenance sources, watchlist, ideas, and production hand-off."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from youtube_studio.domain.models.project import MetadataDraft, Project, ProjectType
from youtube_studio.domain.models.research import ResearchProject, ResearchSource, SavedIdea
from youtube_studio.domain.policies.retention import RetentionPolicy
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.research.clustering import TopicClusterer
from youtube_studio.research.providers.base import ResearchResult, RetentionClass
from youtube_studio.research.watchlist import WatchlistEntry
from youtube_studio.storage.orm import ResearchProjectORM, ResearchSourceORM, SavedIdeaORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResearchService:
    """Manages research projects, policy-compliant sources, watchlists, saved ideas, and production hand-off."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Research Projects
    # ------------------------------------------------------------------

    def create_research_project(
        self,
        name: str,
        *,
        channel_id: Optional[str] = None,
        brief: Optional[str] = None,
    ) -> ResearchProject:
        now = _utcnow()
        domain = ResearchProject(
            channel_id=channel_id,
            name=name,
            brief=brief,
            status="active",
            created_at=now,
            updated_at=now,
        )
        orm = ResearchProjectORM(
            id=domain.id,
            channel_id=domain.channel_id,
            name=domain.name,
            brief=domain.brief,
            status=domain.status,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def get_research_project(self, project_id: str) -> Optional[ResearchProject]:
        orm = self._session.get(ResearchProjectORM, project_id)
        return self._project_to_domain(orm) if orm else None

    def list_research_projects(self, channel_id: Optional[str] = None) -> list[ResearchProject]:
        stmt = select(ResearchProjectORM).order_by(ResearchProjectORM.updated_at.desc())
        if channel_id is not None:
            stmt = stmt.where(ResearchProjectORM.channel_id == channel_id)
        return [self._project_to_domain(o) for o in self._session.scalars(stmt)]

    def update_research_project(
        self,
        project_id: str,
        *,
        name: Optional[str] = None,
        brief: Optional[str] = None,
        status: Optional[str] = None,
    ) -> ResearchProject:
        orm = self._session.get(ResearchProjectORM, project_id)
        if orm is None:
            raise ValueError(f"ResearchProject {project_id} not found")
        if name is not None:
            orm.name = name
        if brief is not None:
            orm.brief = brief
        if status is not None:
            orm.status = status
        orm.updated_at = _utcnow()
        self._session.flush()
        return self._project_to_domain(orm)

    # ------------------------------------------------------------------
    # Research Sources & Retention Policy Enforcement
    # ------------------------------------------------------------------

    def record_source(
        self,
        result: ResearchResult,
        *,
        research_project_id: Optional[str] = None,
    ) -> ResearchSource:
        RetentionPolicy.validate_result(result)
        expires_at = result.expires_at() or RetentionPolicy.compute_expires_at(
            result.retrieved_at, result.retention_class
        )
        domain = ResearchSource(
            research_project_id=research_project_id,
            provider=result.provider,
            source_type=result.source_type,
            external_reference=result.external_reference,
            retrieved_at=result.retrieved_at,
            retention_class=result.retention_class.value,
            expires_at=expires_at,
            provenance=result.provenance,
            payload=result.payload,
        )
        combined_json = json.dumps(
            {
                "provenance": domain.provenance,
                "payload": domain.payload,
            }
        )
        orm = ResearchSourceORM(
            id=domain.id,
            research_project_id=domain.research_project_id,
            provider=domain.provider,
            source_type=domain.source_type,
            external_reference=domain.external_reference,
            retrieved_at=domain.retrieved_at,
            retention_class=domain.retention_class,
            expires_at=domain.expires_at,
            provenance_json=combined_json,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def list_sources(
        self,
        research_project_id: Optional[str] = None,
        *,
        source_type: Optional[str] = None,
        include_expired: bool = False,
        now: Optional[datetime] = None,
    ) -> list[ResearchSource]:
        stmt = select(ResearchSourceORM).order_by(ResearchSourceORM.retrieved_at.desc())
        if research_project_id is not None:
            stmt = stmt.where(ResearchSourceORM.research_project_id == research_project_id)
        if source_type is not None:
            stmt = stmt.where(ResearchSourceORM.source_type == source_type)

        items = [self._source_to_domain(o) for o in self._session.scalars(stmt)]
        if include_expired:
            return items
        return [
            s for s in items if not RetentionPolicy.is_expired(s.expires_at, now=now)
        ]

    def purge_expired_sources(self, *, now: Optional[datetime] = None) -> int:
        """Delete all expired research sources (e.g., public_api_30d past 30 days)."""
        ref = now or _utcnow()
        stmt = select(ResearchSourceORM).where(ResearchSourceORM.expires_at.is_not(None))
        purged = 0
        for orm in list(self._session.scalars(stmt)):
            if RetentionPolicy.is_expired(orm.expires_at, now=ref):
                self._session.delete(orm)
                purged += 1
        if purged > 0:
            self._session.flush()
        return purged

    # ------------------------------------------------------------------
    # Competitor Watchlist (Public Metadata Only)
    # ------------------------------------------------------------------

    def add_to_watchlist(
        self,
        channel_external_id: str,
        title: str,
        *,
        research_project_id: Optional[str] = None,
        custom_url: str = "",
        description: str = "",
    ) -> WatchlistEntry:
        res = WatchlistEntry.build_manual_result(
            channel_external_id=channel_external_id,
            title=title,
            custom_url=custom_url,
            description=description,
        )
        return self.add_watchlist_result(res, research_project_id=research_project_id)

    def add_watchlist_result(
        self,
        result: ResearchResult,
        *,
        research_project_id: Optional[str] = None,
    ) -> WatchlistEntry:
        watchlist_res = ResearchResult(
            provider=result.provider,
            source_type="competitor_watchlist",
            external_reference=result.external_reference,
            retrieved_at=result.retrieved_at,
            retention_class=RetentionClass.PUBLIC_API_30D,
            payload=result.payload,
            provenance=result.provenance,
        )
        source = self.record_source(watchlist_res, research_project_id=research_project_id)
        return WatchlistEntry.from_research_result(
            source.id,
            research_project_id,
            watchlist_res,
        )

    def list_watchlist(
        self,
        research_project_id: Optional[str] = None,
        *,
        include_expired: bool = False,
    ) -> list[WatchlistEntry]:
        sources = self.list_sources(
            research_project_id=research_project_id,
            source_type="competitor_watchlist",
            include_expired=include_expired,
        )
        entries: list[WatchlistEntry] = []
        for s in sources:
            entries.append(
                WatchlistEntry(
                    source_id=s.id,
                    research_project_id=s.research_project_id,
                    channel_external_id=str(
                        s.payload.get("channel_id") or s.external_reference or "unknown"
                    ),
                    title=str(s.payload.get("title") or "Untitled Channel"),
                    custom_url=str(s.payload.get("custom_url") or ""),
                    description=str(s.payload.get("description") or ""),
                    retrieved_at=s.retrieved_at,
                    expires_at=s.expires_at,
                )
            )
        return entries

    # ------------------------------------------------------------------
    # Saved Ideas & Production Brief Hand-Off
    # ------------------------------------------------------------------

    def save_idea(
        self,
        title: str,
        *,
        channel_id: Optional[str] = None,
        research_project_id: Optional[str] = None,
        rationale: Optional[str] = None,
        evidence: Optional[list[dict[str, Any]]] = None,
    ) -> SavedIdea:
        domain = SavedIdea(
            channel_id=channel_id,
            research_project_id=research_project_id,
            title=title,
            rationale=rationale,
            evidence=evidence or [],
            status="idea",
            created_at=_utcnow(),
        )
        orm = SavedIdeaORM(
            id=domain.id,
            channel_id=domain.channel_id,
            research_project_id=domain.research_project_id,
            title=domain.title,
            rationale=domain.rationale,
            evidence_json=json.dumps(domain.evidence),
            status=domain.status,
            created_at=domain.created_at,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def get_idea(self, idea_id: str) -> Optional[SavedIdea]:
        orm = self._session.get(SavedIdeaORM, idea_id)
        return self._idea_to_domain(orm) if orm else None

    def list_ideas(
        self,
        *,
        channel_id: Optional[str] = None,
        research_project_id: Optional[str] = None,
    ) -> list[SavedIdea]:
        stmt = select(SavedIdeaORM).order_by(SavedIdeaORM.created_at.desc())
        if channel_id is not None:
            stmt = stmt.where(SavedIdeaORM.channel_id == channel_id)
        if research_project_id is not None:
            stmt = stmt.where(SavedIdeaORM.research_project_id == research_project_id)
        return [self._idea_to_domain(o) for o in self._session.scalars(stmt)]

    def handoff_idea_to_production(
        self,
        idea_id: str,
        *,
        channel_id: Optional[str] = None,
        project_type: ProjectType = ProjectType.MIX,
    ) -> tuple[Project, MetadataDraft]:
        """Convert a SavedIdea + ResearchProject brief into a Production Project and initial MetadataDraft."""
        idea_orm = self._session.get(SavedIdeaORM, idea_id)
        if idea_orm is None:
            raise ValueError(f"SavedIdea {idea_id} not found")
        idea = self._idea_to_domain(idea_orm)

        research_proj = (
            self.get_research_project(idea.research_project_id)
            if idea.research_project_id
            else None
        )
        resolved_channel_id = (
            channel_id
            or idea.channel_id
            or (research_proj.channel_id if research_proj else None)
        )
        if not resolved_channel_id:
            raise ValueError("Cannot hand off idea without a target channel_id")

        channel = ChannelService(self._session).get(resolved_channel_id)
        base_tags = list(channel.brand_config.default_tags) if channel else []

        # Extract topic keywords from idea title + rationale
        clusterer = TopicClusterer()
        synthetic_res = ResearchResult(
            provider="user_idea",
            source_type="saved_idea",
            external_reference=idea.id,
            retrieved_at=idea.created_at,
            retention_class=RetentionClass.USER_AUTHORED,
            payload={"title": idea.title, "description": idea.rationale or ""},
        )
        extracted_kw = clusterer.extract_keywords([synthetic_res], top_k=6)
        combined_tags = list(dict.fromkeys(base_tags + extracted_kw))

        # Build initial production brief description
        desc_sections: list[str] = [idea.title]
        if idea.rationale:
            desc_sections.append(f"Production Brief / Rationale:\n{idea.rationale}")
        if research_proj and research_proj.brief:
            desc_sections.append(f"Research Project Notes ({research_proj.name}):\n{research_proj.brief}")

        proj_svc = ProjectService(self._session)
        prod_project = proj_svc.create_project(
            resolved_channel_id,
            idea.title,
            project_type=project_type,
        )
        draft = proj_svc.save_metadata_draft(
            prod_project.id,
            title=idea.title,
            description="\n\n".join(desc_sections),
            tags=combined_tags,
            chapters=[],
            approval_status="draft",
        )

        idea_orm.status = "in_production"
        self._session.flush()
        return prod_project, draft

    # ------------------------------------------------------------------
    # Mappers
    # ------------------------------------------------------------------

    @staticmethod
    def _project_to_domain(orm: ResearchProjectORM) -> ResearchProject:
        return ResearchProject(
            id=orm.id,
            channel_id=orm.channel_id,
            name=orm.name,
            brief=orm.brief,
            status=orm.status,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def _source_to_domain(orm: ResearchSourceORM) -> ResearchSource:
        decoded = json.loads(orm.provenance_json or "{}")
        if "payload" in decoded and "provenance" in decoded:
            provenance = decoded["provenance"]
            payload = decoded["payload"]
        else:
            provenance = decoded
            payload = {}
        return ResearchSource(
            id=orm.id,
            research_project_id=orm.research_project_id,
            provider=orm.provider,
            source_type=orm.source_type,
            external_reference=orm.external_reference,
            retrieved_at=orm.retrieved_at,
            retention_class=orm.retention_class,
            expires_at=orm.expires_at,
            provenance=provenance,
            payload=payload,
        )

    @staticmethod
    def _idea_to_domain(orm: SavedIdeaORM) -> SavedIdea:
        return SavedIdea(
            id=orm.id,
            channel_id=orm.channel_id,
            research_project_id=orm.research_project_id,
            title=orm.title,
            rationale=orm.rationale,
            evidence=json.loads(orm.evidence_json or "[]"),
            status=orm.status,
            created_at=orm.created_at,
        )
