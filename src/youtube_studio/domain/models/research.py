"""Research domain models – provenance-aware."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from youtube_studio.domain.models._compat import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class ResearchProject(BaseModel):
    id: str = Field(default_factory=_new_id)
    channel_id: Optional[str] = None
    name: str
    brief: Optional[str] = None
    status: str = "draft"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ResearchSource(BaseModel):
    """A single retrieved data point with policy classification."""

    id: str = Field(default_factory=_new_id)
    research_project_id: Optional[str] = None
    provider: str  # e.g. "youtube_data_api"
    source_type: str  # e.g. "search_result", "channel_snippet"
    external_reference: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=_utcnow)
    retention_class: str  # e.g. "public_api_30d", "user_authored", "authorized"
    expires_at: Optional[datetime] = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class SavedIdea(BaseModel):
    id: str = Field(default_factory=_new_id)
    channel_id: Optional[str] = None
    research_project_id: Optional[str] = None
    title: str
    rationale: Optional[str] = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "idea"
    created_at: datetime = Field(default_factory=_utcnow)
