"""Media file models."""

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


class MediaType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    OTHER = "other"


class MediaFile(BaseModel):
    id: str = Field(default_factory=_new_id)
    channel_id: Optional[str] = None
    path: str
    file_hash: Optional[str] = None
    media_type: MediaType = MediaType.AUDIO
    duration_ms: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_scanned_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)
