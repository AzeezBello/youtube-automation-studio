"""Data retention and YouTube API compliance policy enforcement."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from youtube_studio.research.providers.base import ResearchResult, RetentionClass

MAX_PUBLIC_API_RETENTION_DAYS = 30

# Prohibited derived/proprietary metric keys on public API payloads (PRD §6 compliance)
PROHIBITED_DERIVED_METRIC_KEYS = frozenset(
    {
        "competitor_score",
        "viral_score",
        "vidiq_score",
        "engagement_velocity_score",
        "proprietary_rank",
        "predicted_cpm",
    }
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ComplianceViolationError(ValueError):
    """Raised when a research payload or retention window violates API compliance policy."""


class RetentionPolicy:
    """Enforces retention windows and restricts prohibited derived metrics on API data."""

    @staticmethod
    def compute_expires_at(
        retrieved_at: datetime,
        retention_class: RetentionClass | str,
    ) -> Optional[datetime]:
        rc = (
            retention_class
            if isinstance(retention_class, RetentionClass)
            else RetentionClass(retention_class)
        )
        if rc == RetentionClass.PUBLIC_API_30D:
            return retrieved_at + timedelta(days=MAX_PUBLIC_API_RETENTION_DAYS)
        if rc == RetentionClass.TRANSIENT:
            return retrieved_at
        return None

    @classmethod
    def validate_result(cls, result: ResearchResult) -> None:
        """Verify that a ResearchResult complies with retention and non-derived metric policies."""
        if result.retention_class == RetentionClass.PUBLIC_API_30D:
            exp = result.expires_at()
            max_exp = result.retrieved_at + timedelta(days=MAX_PUBLIC_API_RETENTION_DAYS, seconds=1)
            if exp is None or exp > max_exp:
                raise ComplianceViolationError(
                    "public_api_30d data must have an expiration ≤ 30 days from retrieval"
                )
        cls.validate_payload_keys(result.payload, result.retention_class)
        cls.validate_payload_keys(result.provenance, result.retention_class)

    @classmethod
    def validate_payload_keys(
        cls,
        data: dict[str, Any],
        retention_class: RetentionClass | str,
    ) -> None:
        rc_val = (
            retention_class.value
            if isinstance(retention_class, RetentionClass)
            else str(retention_class)
        )
        if rc_val == RetentionClass.PUBLIC_API_30D.value:
            forbidden = PROHIBITED_DERIVED_METRIC_KEYS.intersection(
                {k.lower() for k in data.keys()}
            )
            if forbidden:
                raise ComplianceViolationError(
                    f"Prohibited derived metric keys in public API data: {sorted(forbidden)}"
                )

    @staticmethod
    def is_expired(expires_at: Optional[datetime], *, now: Optional[datetime] = None) -> bool:
        if expires_at is None:
            return False
        ref = now or utcnow()
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        return expires_at <= ref
