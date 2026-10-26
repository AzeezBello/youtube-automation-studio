"""Channel profile models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from youtube_studio.domain.models._compat import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class ChannelBrandConfig(BaseModel):
    """Brand and production defaults for a channel."""

    preferred_language: str = "en"
    default_aspect_ratio: str = "16:9"  # or "9:16"
    default_resolution: str = "1920x1080"
    visual_style: str = "vintage_roots"
    metadata_template: dict[str, Any] = Field(default_factory=dict)
    thumbnail_style: dict[str, Any] = Field(default_factory=dict)
    intro_outro_enabled: bool = False
    default_tags: list[str] = Field(default_factory=list)


class Channel(BaseModel):
    """Local channel profile – independent branding, libraries, and settings."""

    id: str = Field(default_factory=_new_id)
    name: str
    platform_channel_id: Optional[str] = None  # YouTube channel ID once connected
    brand_config: ChannelBrandConfig = Field(default_factory=ChannelBrandConfig)
    default_output_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    archived_at: Optional[datetime] = None

    def touch(self) -> None:
        self.updated_at = _utcnow()

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
