"""Competitor watchlist representation (public metadata only, 30-day retention)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from youtube_studio.research.providers.base import ResearchResult, RetentionClass, utcnow


@dataclass(frozen=True)
class WatchlistEntry:
    source_id: str
    research_project_id: Optional[str]
    channel_external_id: str
    title: str
    custom_url: str
    description: str
    retrieved_at: datetime
    expires_at: Optional[datetime]

    @property
    def is_expired(self) -> bool:
        from youtube_studio.domain.policies.retention import RetentionPolicy

        return RetentionPolicy.is_expired(self.expires_at)

    @classmethod
    def from_research_result(
        cls,
        source_id: str,
        research_project_id: Optional[str],
        result: ResearchResult,
    ) -> WatchlistEntry:
        from youtube_studio.domain.policies.retention import RetentionPolicy

        RetentionPolicy.validate_result(result)
        payload = result.payload
        return cls(
            source_id=source_id,
            research_project_id=research_project_id,
            channel_external_id=str(
                payload.get("channel_id") or result.external_reference or "unknown"
            ),
            title=str(payload.get("title") or "Untitled Channel"),
            custom_url=str(payload.get("custom_url") or ""),
            description=str(payload.get("description") or ""),
            retrieved_at=result.retrieved_at,
            expires_at=result.expires_at(),
        )

    @staticmethod
    def build_manual_result(
        channel_external_id: str,
        title: str,
        *,
        custom_url: str = "",
        description: str = "",
    ) -> ResearchResult:
        """Create a policy-compliant public watchlist result when entered manually offline."""
        now = utcnow()
        res = ResearchResult(
            provider="manual_public_watchlist",
            source_type="competitor_watchlist",
            external_reference=f"youtube:channel:{channel_external_id}",
            retrieved_at=now,
            retention_class=RetentionClass.PUBLIC_API_30D,
            payload={
                "channel_id": channel_external_id,
                "title": title,
                "custom_url": custom_url,
                "description": description,
            },
            provenance={"source": "competitor_watchlist_public_metadata"},
        )
        from youtube_studio.domain.policies.retention import RetentionPolicy

        RetentionPolicy.validate_result(res)
        return res
