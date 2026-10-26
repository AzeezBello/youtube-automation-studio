"""Quota-aware YouTube Data API v3 research provider (public metadata only, ≤30d retention)."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Callable, Optional

from youtube_studio.research.providers.base import (
    ResearchProvider,
    ResearchResult,
    RetentionClass,
    utcnow,
)
from youtube_studio.security.vault import CredentialVault

YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"
YOUTUBE_API_KEY_SECRET = "youtube_data_api_key"

# Official YouTube Data API v3 endpoint quota costs
QUOTA_COST_SEARCH_LIST = 100
QUOTA_COST_CHANNELS_LIST = 1
QUOTA_COST_VIDEOS_LIST = 1


class QuotaExceededError(RuntimeError):
    """Raised when a YouTube Data API request would exceed the configured daily quota budget."""


class QuotaTracker:
    """Tracks daily YouTube Data API v3 quota consumption and enforces budget limits."""

    def __init__(self, daily_budget: int = 10_000) -> None:
        if daily_budget <= 0:
            raise ValueError("daily_budget must be positive")
        self._daily_budget = daily_budget
        self._current_day: date = date.today()
        self._used_units: int = 0
        self._history: list[dict[str, Any]] = []

    @property
    def daily_budget(self) -> int:
        return self._daily_budget

    @property
    def used_units(self) -> int:
        self._rollover_if_new_day()
        return self._used_units

    @property
    def remaining_units(self) -> int:
        self._rollover_if_new_day()
        return max(0, self._daily_budget - self._used_units)

    @property
    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def can_afford(self, units: int) -> bool:
        self._rollover_if_new_day()
        return (self._used_units + units) <= self._daily_budget

    def consume(self, units: int, *, endpoint: str = "unknown") -> int:
        self._rollover_if_new_day()
        if not self.can_afford(units):
            raise QuotaExceededError(
                f"YouTube API quota exceeded: endpoint '{endpoint}' requires {units} units, "
                f"but only {self.remaining_units}/{self._daily_budget} units remain today."
            )
        self._used_units += units
        self._history.append(
            {
                "endpoint": endpoint,
                "units": units,
                "used_total": self._used_units,
                "timestamp": utcnow().isoformat(),
            }
        )
        return self._used_units

    def _rollover_if_new_day(self) -> None:
        today = date.today()
        if today != self._current_day:
            self._current_day = today
            self._used_units = 0
            self._history.clear()


HttpGetCallable = Callable[[str, dict[str, Any]], dict[str, Any]]


class YouTubeDataAPIProvider(ResearchProvider):
    """Policy-compliant, quota-aware YouTube Data API v3 provider."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        vault: Optional[CredentialVault] = None,
        quota_tracker: Optional[QuotaTracker] = None,
        http_get: Optional[HttpGetCallable] = None,
    ) -> None:
        self._vault = vault
        self._explicit_api_key = api_key
        self.quota = quota_tracker or QuotaTracker()
        self._http_get = http_get or self._default_http_get

    @property
    def name(self) -> str:
        return "youtube_data_api"

    def _resolve_api_key(self) -> Optional[str]:
        if self._explicit_api_key:
            return self._explicit_api_key
        env_key = os.environ.get("YAS_YOUTUBE_API_KEY")
        if env_key:
            return env_key
        if self._vault is not None:
            return self._vault.get_secret(YOUTUBE_API_KEY_SECRET)
        return None

    def is_available(self) -> bool:
        return bool(self._resolve_api_key()) and self.quota.remaining_units > 0

    def search(self, query: str, *, max_results: int = 25) -> list[ResearchResult]:
        api_key = self._resolve_api_key()
        if not api_key:
            raise RuntimeError(
                "YouTube Data API key is not configured (set YAS_YOUTUBE_API_KEY or store in CredentialVault)"
            )

        self.quota.consume(QUOTA_COST_SEARCH_LIST, endpoint="search.list")
        params: dict[str, Any] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max(1, min(50, max_results)),
            "key": api_key,
        }
        raw = self._http_get(f"{YOUTUBE_API_BASE_URL}/search", params)
        now = utcnow()
        results: list[ResearchResult] = []

        for item in raw.get("items", []):
            from youtube_studio.domain.policies.retention import RetentionPolicy

            vid_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            payload = {
                "video_id": vid_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_id": snippet.get("channelId", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
            }
            res = ResearchResult(
                provider=self.name,
                source_type="search_result",
                external_reference=f"youtube:video:{vid_id}" if vid_id else None,
                retrieved_at=now,
                retention_class=RetentionClass.PUBLIC_API_30D,
                payload=payload,
                provenance={
                    "endpoint": "youtube/v3/search",
                    "query": query,
                    "quota_cost": QUOTA_COST_SEARCH_LIST,
                },
            )
            RetentionPolicy.validate_result(res)
            results.append(res)

        return results

    def fetch_channel_public_metadata(self, channel_external_id: str) -> ResearchResult:
        """Fetch public channel snippet & public statistics (1 quota unit) for competitor watchlist."""
        api_key = self._resolve_api_key()
        if not api_key:
            raise RuntimeError("YouTube Data API key is not configured")

        self.quota.consume(QUOTA_COST_CHANNELS_LIST, endpoint="channels.list")
        params: dict[str, Any] = {
            "part": "snippet",
            "id": channel_external_id,
            "key": api_key,
        }
        raw = self._http_get(f"{YOUTUBE_API_BASE_URL}/channels", params)
        items = raw.get("items", [])
        if not items:
            raise ValueError(f"YouTube channel not found: {channel_external_id}")

        item = items[0]
        from youtube_studio.domain.policies.retention import RetentionPolicy

        snippet = item.get("snippet", {})
        now = utcnow()
        res = ResearchResult(
            provider=self.name,
            source_type="channel_snippet",
            external_reference=f"youtube:channel:{channel_external_id}",
            retrieved_at=now,
            retention_class=RetentionClass.PUBLIC_API_30D,
            payload={
                "channel_id": item.get("id", channel_external_id),
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "custom_url": snippet.get("customUrl", ""),
                "published_at": snippet.get("publishedAt", ""),
                "country": snippet.get("country", ""),
            },
            provenance={
                "endpoint": "youtube/v3/channels",
                "quota_cost": QUOTA_COST_CHANNELS_LIST,
            },
        )
        RetentionPolicy.validate_result(res)
        return res

    @staticmethod
    def _default_http_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
        qs = urllib.parse.urlencode(params)
        full_url = f"{url}?{qs}"
        req = urllib.request.Request(full_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
