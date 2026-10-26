"""Research provider contracts – every source must declare retention class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional


class RetentionClass(str, Enum):
    """How long / under what rules the data may be stored."""

    USER_AUTHORED = "user_authored"  # indefinite, user-controlled
    PUBLIC_API_30D = "public_api_30d"  # YouTube public data ≤ 30 days
    AUTHORIZED = "authorized"  # channel-owner analytics while connected
    TRANSIENT = "transient"  # do not persist beyond the session


@dataclass
class ResearchResult:
    provider: str
    source_type: str
    external_reference: Optional[str]
    retrieved_at: datetime
    retention_class: RetentionClass
    payload: dict[str, Any]
    provenance: dict[str, Any] = field(default_factory=dict)

    def expires_at(self) -> Optional[datetime]:
        if self.retention_class == RetentionClass.PUBLIC_API_30D:
            return self.retrieved_at + timedelta(days=30)
        if self.retention_class == RetentionClass.TRANSIENT:
            return self.retrieved_at
        return None


class ResearchProvider(ABC):
    """Abstract interface for any research data source."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def search(self, query: str, *, max_results: int = 25) -> list[ResearchResult]:
        """Return search results with full provenance."""
        ...

    def is_available(self) -> bool:
        return True


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
