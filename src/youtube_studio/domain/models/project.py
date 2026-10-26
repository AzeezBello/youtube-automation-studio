"""Production project, track timeline, asset, and metadata models."""

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


class ProjectType(str, Enum):
    SINGLE_TRACK = "single_track"
    MIX = "mix"
    COMPILATION = "compilation"
    ALBUM = "album"
    PROMO_CLIP = "promo_clip"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    RENDERED = "rendered"
    PACKAGED = "packaged"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class TransitionType(str, Enum):
    NONE = "none"
    CROSSFADE = "crossfade"
    BASS_SWAP_EQ = "bass_swap_eq"
    HARD_CUT = "hard_cut"


class TransitionConfig(BaseModel):
    transition_type: TransitionType = TransitionType.CROSSFADE
    overlap_ms: int = 3000  # default 3s crossfade when transition_type == CROSSFADE
    curve: str = "tri"  # FFmpeg acrossfade curve (tri, qsin, esin, log, etc.)


class ProjectTrack(BaseModel):
    """A track placed on a project timeline with trim, gain, fade, and transition settings."""

    id: str = Field(default_factory=_new_id)
    project_id: str
    media_file_id: str
    track_order: int
    trim_start_ms: int = 0
    trim_end_ms: Optional[int] = None
    gain_db: float = 0.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    transition_config: TransitionConfig = Field(default_factory=TransitionConfig)

    def effective_duration_ms(self, source_duration_ms: Optional[int]) -> int:
        """Compute trimmed duration in milliseconds given the raw media duration."""
        if source_duration_ms is None or source_duration_ms <= 0:
            if self.trim_end_ms is not None and self.trim_end_ms > self.trim_start_ms:
                return self.trim_end_ms - self.trim_start_ms
            return 0
        end_ms = (
            min(self.trim_end_ms, source_duration_ms)
            if self.trim_end_ms is not None
            else source_duration_ms
        )
        return max(0, end_ms - max(0, self.trim_start_ms))


class AssetType(str, Enum):
    THUMBNAIL = "thumbnail"
    BACKGROUND_IMAGE = "background_image"
    MIXED_AUDIO = "mixed_audio"
    RENDERED_VIDEO = "rendered_video"
    WAVEFORM_IMAGE = "waveform_image"
    PACKAGE_MANIFEST = "package_manifest"


class Asset(BaseModel):
    """A generated or imported project asset with provenance and approval status."""

    id: str = Field(default_factory=_new_id)
    project_id: str
    asset_type: AssetType
    file_path: str
    source_type: str = "generated"  # e.g. "generated", "imported", "template"
    provenance: dict[str, Any] = Field(default_factory=dict)
    checksum: Optional[str] = None
    approved: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


class ChapterEntry(BaseModel):
    """A single YouTube chapter timestamp entry."""

    start_ms: int
    title: str

    def format_timestamp(self) -> str:
        total_seconds = max(0, self.start_ms // 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"


class MetadataDraft(BaseModel):
    """Versioned title, description, tags, and chapter list for a project."""

    id: str = Field(default_factory=_new_id)
    project_id: str
    version: int = 1
    title: Optional[str] = None
    description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    chapters: list[ChapterEntry] = Field(default_factory=list)
    approval_status: str = "draft"  # draft | approved | rejected
    created_at: datetime = Field(default_factory=_utcnow)


class Project(BaseModel):
    id: str = Field(default_factory=_new_id)
    channel_id: str
    name: str
    project_type: ProjectType = ProjectType.SINGLE_TRACK
    status: ProjectStatus = ProjectStatus.DRAFT
    manifest_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()
