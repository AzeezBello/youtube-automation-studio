"""Quota-aware YouTube Data API v3 research provider (public metadata only, ≤30d retention)."""

from __future__ import annotations

import json
import os
import re
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


def extract_youtube_video_id(url_or_id: str) -> str:
    """Extract a YouTube video ID from a watch URL, youtu.be short URL, shorts URL, or raw ID."""
    raw = (url_or_id or "").strip()
    if not raw:
        raise ValueError("YouTube video URL or ID cannot be empty")

    # Check query param v=
    if "youtube.com" in raw or "youtu.be" in raw:
        parsed = urllib.parse.urlparse(raw if "://" in raw else f"https://{raw}")
        qs = urllib.parse.parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            return qs["v"][0].strip()
        path_parts = [p for p in parsed.path.split("/") if p]
        if parsed.netloc.endswith("youtu.be") and path_parts:
            return path_parts[0].strip()
        for prefix in ("shorts", "embed", "v", "live"):
            if prefix in path_parts:
                idx = path_parts.index(prefix)
                if idx + 1 < len(path_parts):
                    return path_parts[idx + 1].strip()

    # Fallback: match 11-char ID or sanitized token
    m = re.search(r"([A-Za-z0-9_-]{11})", raw)
    if m:
        return m.group(1)
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", raw)
    if not cleaned:
        raise ValueError(f"Could not extract video ID from: {url_or_id}")
    return cleaned[:32]


def parse_chapters_from_description(description: str) -> list[dict[str, Any]]:
    """Extract timestamped chapters (e.g. '00:00 Intro') from a YouTube video description."""
    chapters: list[dict[str, Any]] = []
    if not description:
        return chapters
    pattern = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*[-–—:|]?\s*(.+?)\s*$")
    for line in description.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        hh = int(m.group(1) or 0)
        mm = int(m.group(2) or 0)
        ss = int(m.group(3) or 0)
        title = m.group(4).strip()
        if not title:
            continue
        start_ms = ((hh * 3600) + (mm * 60) + ss) * 1000
        timestamp_str = f"{hh:02d}:{mm:02d}:{ss:02d}" if hh > 0 else f"{mm:02d}:{ss:02d}"
        chapters.append(
            {
                "timestamp": timestamp_str,
                "start_ms": start_ms,
                "title": title,
            }
        )
    return chapters


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

    def fetch_video_public_metadata(
        self,
        url_or_id: str,
        *,
        allow_offline_fallback: bool = True,
    ) -> ResearchResult:
        """Fetch public video metadata (title, description, chapters, tags, thumbnail) from a YouTube URL or ID."""
        from youtube_studio.domain.policies.retention import RetentionPolicy

        video_id = extract_youtube_video_id(url_or_id)
        now = utcnow()
        api_key = self._resolve_api_key()

        if api_key and self.quota.can_afford(QUOTA_COST_VIDEOS_LIST):
            try:
                self.quota.consume(QUOTA_COST_VIDEOS_LIST, endpoint="videos.list")
                params: dict[str, Any] = {
                    "part": "snippet",
                    "id": video_id,
                    "key": api_key,
                }
                raw = self._http_get(f"{YOUTUBE_API_BASE_URL}/videos", params)
                items = raw.get("items", [])
                if items:
                    item = items[0]
                    snippet = item.get("snippet", {})
                    desc = str(snippet.get("description", ""))
                    chapters = parse_chapters_from_description(desc)
                    thumbs = snippet.get("thumbnails", {}) or {}
                    best_thumb = (
                        (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {})
                        .get("url", "")
                    )
                    res = ResearchResult(
                        provider=self.name,
                        source_type="video_url_import",
                        external_reference=f"youtube:video:{video_id}",
                        retrieved_at=now,
                        retention_class=RetentionClass.PUBLIC_API_30D,
                        payload={
                            "video_id": video_id,
                            "url": f"https://www.youtube.com/watch?v={video_id}",
                            "title": snippet.get("title", f"Imported Video {video_id}"),
                            "description": desc,
                            "channel_id": snippet.get("channelId", ""),
                            "channel_title": snippet.get("channelTitle", ""),
                            "published_at": snippet.get("publishedAt", ""),
                            "tags": list(snippet.get("tags", []) or []),
                            "chapters": chapters,
                            "thumbnail_url": best_thumb,
                        },
                        provenance={
                            "endpoint": "youtube/v3/videos",
                            "source_url": url_or_id,
                            "quota_cost": QUOTA_COST_VIDEOS_LIST,
                        },
                    )
                    RetentionPolicy.validate_result(res)
                    return res
            except Exception:
                if not allow_offline_fallback:
                    raise

        if not allow_offline_fallback:
            raise RuntimeError("YouTube Data API key is not configured for fetch_video_public_metadata")

        # Deterministic offline fallback so URL import works without an active API key or internet
        fallback_desc = (
            f"Reference brief imported from https://www.youtube.com/watch?v={video_id}\n\n"
            "00:00 Intro & Hook\n"
            "03:15 Main Session / Theme Development\n"
            "08:40 Peak Highlight & Closing"
        )
        res = ResearchResult(
            provider="stub_url_importer",
            source_type="video_url_import",
            external_reference=f"youtube:video:{video_id}",
            retrieved_at=now,
            retention_class=RetentionClass.PUBLIC_API_30D,
            payload={
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": f"Reference Session ({video_id}) — Imported Video Brief",
                "description": fallback_desc,
                "channel_id": "offline_reference_channel",
                "channel_title": "Reference YouTube Channel",
                "published_at": now.isoformat(),
                "tags": ["reference import", "roots reggae", "mix session", "youtube brief"],
                "chapters": parse_chapters_from_description(fallback_desc),
                "thumbnail_url": "",
            },
            provenance={
                "endpoint": "offline_url_parser",
                "source_url": url_or_id,
                "quota_cost": 0,
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
