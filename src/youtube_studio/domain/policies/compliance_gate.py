"""Pre-export and pre-release YouTube API & package compliance review gate."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from youtube_studio.ai.metadata_generator import (
    MAX_YOUTUBE_TAGS_TOTAL_CHARS,
    MAX_YOUTUBE_TITLE_LENGTH,
)
from youtube_studio.domain.models.project import ChapterEntry
from youtube_studio.domain.policies.retention import (
    PROHIBITED_DERIVED_METRIC_KEYS,
    RetentionPolicy,
)
from youtube_studio.media.validator import MediaValidator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ComplianceCheckItem:
    name: str
    passed: bool
    details: str


@dataclass
class ComplianceGateReport:
    passed: bool
    checked_at: datetime = field(default_factory=_utcnow)
    checks: list[ComplianceCheckItem] = field(default_factory=list)

    @property
    def blocking_reasons(self) -> list[str]:
        return [f"{c.name}: {c.details}" for c in self.checks if not c.passed]


class ComplianceReviewGate:
    """Audits package manifests, metadata, chapter rules, and API retention compliance."""

    def __init__(self, validator: Optional[MediaValidator] = None) -> None:
        self._validator = validator or MediaValidator()

    def review_package_manifest(
        self,
        manifest_path: Path,
        *,
        active_source_expiries: Optional[list[Optional[datetime]]] = None,
    ) -> ComplianceGateReport:
        checks: list[ComplianceCheckItem] = []

        if not manifest_path.exists():
            return ComplianceGateReport(
                passed=False,
                checks=[
                    ComplianceCheckItem(
                        name="manifest_exists",
                        passed=False,
                        details=f"Package manifest not found: {manifest_path}",
                    )
                ],
            )

        data: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks.append(
            ComplianceCheckItem(
                name="manifest_exists",
                passed=True,
                details=f"Loaded manifest for project '{data.get('project_name', 'unknown')}'",
            )
        )

        # 1. Check prohibited derived competitor metric keys
        forbidden = self._scan_forbidden_keys(data)
        checks.append(
            ComplianceCheckItem(
                name="no_prohibited_derived_metrics",
                passed=len(forbidden) == 0,
                details="No prohibited derived API metrics found"
                if not forbidden
                else f"Forbidden keys detected: {sorted(forbidden)}",
            )
        )

        # 2. Check API retention expiration window
        if active_source_expiries is not None:
            expired_count = sum(
                1 for exp in active_source_expiries if RetentionPolicy.is_expired(exp)
            )
            checks.append(
                ComplianceCheckItem(
                    name="api_retention_30d_clean",
                    passed=expired_count == 0,
                    details="All stored API research sources are within 30-day retention window"
                    if expired_count == 0
                    else f"{expired_count} expired research source(s) require purging",
                )
            )

        # 3. Validate metadata draft (title, tags, chapter rules)
        draft = data.get("metadata_draft", {})
        title = str(draft.get("title") or "").strip()
        title_ok = 1 <= len(title) <= MAX_YOUTUBE_TITLE_LENGTH
        checks.append(
            ComplianceCheckItem(
                name="youtube_title_bounds",
                passed=title_ok,
                details=f"Title length {len(title)}/{MAX_YOUTUBE_TITLE_LENGTH} chars"
                if title_ok
                else f"Invalid title length ({len(title)} chars; must be 1–{MAX_YOUTUBE_TITLE_LENGTH})",
            )
        )

        tags = [str(t) for t in draft.get("tags", [])]
        tags_chars = sum(len(t) for t in tags) + max(0, len(tags) - 1)
        tags_ok = tags_chars <= MAX_YOUTUBE_TAGS_TOTAL_CHARS
        checks.append(
            ComplianceCheckItem(
                name="youtube_tags_budget",
                passed=tags_ok,
                details=f"Tags total {tags_chars}/{MAX_YOUTUBE_TAGS_TOTAL_CHARS} chars"
                if tags_ok
                else f"Tags exceed {MAX_YOUTUBE_TAGS_TOTAL_CHARS} chars ({tags_chars})",
            )
        )

        raw_chapters = draft.get("chapters", [])
        chapters = [
            ChapterEntry(start_ms=int(c.get("start_ms", 0)), title=str(c.get("title", "")))
            for c in raw_chapters
        ]
        ch_ok, ch_msg = self.validate_youtube_chapters(chapters)
        checks.append(
            ComplianceCheckItem(
                name="youtube_chapters_format",
                passed=ch_ok,
                details=ch_msg,
            )
        )

        # 4. Validate output media artifacts (video, audio, thumbnail)
        artifacts = data.get("artifacts", {})
        video_file = Path(artifacts["rendered_video"]) if "rendered_video" in artifacts else None
        thumb_file = Path(artifacts["thumbnail"]) if "thumbnail" in artifacts else None

        if video_file is not None:
            v_rep = self._validator.validate_video(
                video_file,
                expected_resolution=data.get("resolution"),
            )
            checks.append(
                ComplianceCheckItem(
                    name="rendered_video_valid",
                    passed=v_rep.is_valid,
                    details="Rendered video stream and resolution verified"
                    if v_rep.is_valid
                    else "; ".join(v_rep.errors),
                )
            )
        else:
            checks.append(
                ComplianceCheckItem(
                    name="rendered_video_valid",
                    passed=False,
                    details="Manifest is missing 'rendered_video' artifact",
                )
            )

        if thumb_file is not None:
            i_rep = self._validator.validate_image(thumb_file)
            checks.append(
                ComplianceCheckItem(
                    name="thumbnail_valid",
                    passed=i_rep.is_valid,
                    details=f"Thumbnail image verified ({i_rep.width}x{i_rep.height})"
                    if i_rep.is_valid
                    else "; ".join(i_rep.errors),
                )
            )
        else:
            checks.append(
                ComplianceCheckItem(
                    name="thumbnail_valid",
                    passed=False,
                    details="Manifest is missing 'thumbnail' artifact",
                )
            )

        all_passed = all(c.passed for c in checks)
        return ComplianceGateReport(passed=all_passed, checks=checks)

    @staticmethod
    def validate_youtube_chapters(chapters: list[ChapterEntry]) -> tuple[bool, str]:
        """Verify chapters start at 00:00 and are strictly ascending."""
        if not chapters:
            return True, "No chapters specified (single-segment video)"
        if chapters[0].start_ms != 0:
            return False, f"First chapter must start at 00:00 (got {chapters[0].start_ms}ms)"
        for i in range(1, len(chapters)):
            if chapters[i].start_ms <= chapters[i - 1].start_ms:
                return (
                    False,
                    f"Chapters must be strictly ascending (chapter {i + 1} at {chapters[i].start_ms}ms "
                    f"<= chapter {i} at {chapters[i - 1].start_ms}ms)",
                )
        return True, f"{len(chapters)} chapter(s) verified starting at 00:00"

    @classmethod
    def _scan_forbidden_keys(cls, obj: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if str(k).lower() in PROHIBITED_DERIVED_METRIC_KEYS:
                    found.add(str(k).lower())
                found.update(cls._scan_forbidden_keys(v))
        elif isinstance(obj, list):
            for item in obj:
                found.update(cls._scan_forbidden_keys(item))
        return found
