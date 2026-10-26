"""Local AI model registry domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from youtube_studio.domain.models._compat import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class ModelCapability(str, Enum):
    TEXT_GENERATION = "text_generation"
    EMBEDDING = "embedding"
    IMAGE_GENERATION = "image_generation"


class RegisteredModel(BaseModel):
    """Metadata for a locally stored AI model weight file or directory."""

    id: str = Field(default_factory=_new_id)
    name: str
    version: str = "1.0"
    path: str
    license: Optional[str] = None
    size_bytes: Optional[int] = None
    compatibility_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

    def exists_on_disk(self) -> bool:
        return Path(self.path).expanduser().exists()

    def estimated_ram_required_gb(self) -> float:
        """Estimate RAM needed to load the model in GB (size * 1.25 overhead, minimum 1.0 GB)."""
        if self.size_bytes is None or self.size_bytes <= 0:
            return 2.0
        return round(max(1.0, (self.size_bytes / (1024**3)) * 1.25), 2)

    def check_hardware_compatibility(
        self,
        *,
        total_ram_gb: float,
    ) -> tuple[bool, str]:
        if not self.exists_on_disk():
            return False, f"Model file not found on disk: {self.path}"
        required_gb = self.estimated_ram_required_gb()
        available_budget_gb = max(1.0, total_ram_gb - 2.0)
        if required_gb > available_budget_gb:
            return (
                False,
                f"Model requires ~{required_gb:.1f} GB RAM, exceeding safe budget "
                f"({available_budget_gb:.1f} GB available on {total_ram_gb:.1f} GB system)",
            )
        return (
            True,
            f"Compatible (~{required_gb:.1f} GB required on {total_ram_gb:.1f} GB system)",
        )
