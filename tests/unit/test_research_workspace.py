"""Unit tests for P2 research workspace (YouTube API quota adapter, retention policy, clustering, watchlist)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from youtube_studio.domain.policies.retention import (
    ComplianceViolationError,
    RetentionPolicy,
)
from youtube_studio.research.clustering import TopicClusterer
from youtube_studio.research.providers.base import ResearchResult, RetentionClass
from youtube_studio.research.providers.youtube_api import (
    QUOTA_COST_CHANNELS_LIST,
    QUOTA_COST_SEARCH_LIST,
    QuotaExceededError,
    QuotaTracker,
    YouTubeDataAPIProvider,
)
from youtube_studio.research.watchlist import WatchlistEntry


def test_quota_tracker_enforces_daily_budget():
    tracker = QuotaTracker(daily_budget=250)
    assert tracker.remaining_units == 250
    assert tracker.can_afford(100) is True

    tracker.consume(100, endpoint="search.list")
    tracker.consume(100, endpoint="search.list")
    assert tracker.used_units == 200
    assert tracker.remaining_units == 50
    assert tracker.can_afford(100) is False

    try:
        tracker.consume(100, endpoint="search.list")
        raise AssertionError("Expected QuotaExceededError")
    except QuotaExceededError:
        pass


def test_youtube_api_provider_search_and_channel_metadata():
    def fake_http_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
        if url.endswith("/search"):
            return {
                "items": [
                    {
                        "id": {"videoId": "vid_001"},
                        "snippet": {
                            "title": "King Tubby Dubplate Session 1976",
                            "description": "Heavyweight vintage roots reggae dub mix",
                            "channelId": "UC_DUB_01",
                            "channelTitle": "Roots Archive",
                            "publishedAt": "2026-10-01T12:00:00Z",
                        },
                    }
                ]
            }
        if url.endswith("/channels"):
            return {
                "items": [
                    {
                        "id": params["id"],
                        "snippet": {
                            "title": "Roots Archive",
                            "description": "Curated roots & dub vinyl selections",
                            "customUrl": "@rootsarchive",
                            "publishedAt": "2020-01-01T00:00:00Z",
                            "country": "JM",
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected URL: {url}")

    quota = QuotaTracker(daily_budget=1000)
    provider = YouTubeDataAPIProvider(
        api_key="test-key-123",
        quota_tracker=quota,
        http_get=fake_http_get,
    )
    assert provider.is_available() is True

    results = provider.search("king tubby dub", max_results=5)
    assert len(results) == 1
    r0 = results[0]
    assert r0.provider == "youtube_data_api"
    assert r0.retention_class == RetentionClass.PUBLIC_API_30D
    assert r0.external_reference == "youtube:video:vid_001"
    assert r0.expires_at() is not None
    assert quota.used_units == QUOTA_COST_SEARCH_LIST

    ch_res = provider.fetch_channel_public_metadata("UC_DUB_01")
    assert ch_res.source_type == "channel_snippet"
    assert ch_res.payload["custom_url"] == "@rootsarchive"
    assert quota.used_units == QUOTA_COST_SEARCH_LIST + QUOTA_COST_CHANNELS_LIST


def test_retention_policy_rejects_prohibited_derived_metrics():
    now = datetime.now(timezone.utc)
    bad_result = ResearchResult(
        provider="youtube_data_api",
        source_type="search_result",
        external_reference="youtube:video:123",
        retrieved_at=now,
        retention_class=RetentionClass.PUBLIC_API_30D,
        payload={
            "title": "Test Video",
            "vidiq_score": 95,
            "competitor_score": 88,
        },
    )
    try:
        RetentionPolicy.validate_result(bad_result)
        raise AssertionError("Expected ComplianceViolationError")
    except ComplianceViolationError as exc:
        assert "competitor_score" in str(exc) or "vidiq_score" in str(exc)

    exp = RetentionPolicy.compute_expires_at(now, RetentionClass.PUBLIC_API_30D)
    assert exp is not None
    assert RetentionPolicy.is_expired(exp, now=now + timedelta(days=29)) is False
    assert RetentionPolicy.is_expired(exp, now=now + timedelta(days=31)) is True


def test_topic_clusterer_groups_related_results():
    now = datetime.now(timezone.utc)
    items = [
        ResearchResult(
            provider="stub",
            source_type="search_result",
            external_reference="1",
            retrieved_at=now,
            retention_class=RetentionClass.TRANSIENT,
            payload={
                "title": "Roots Reggae Vinyl Dub Mix 1977",
                "description": "Classic roots reggae sound system dubplate",
            },
        ),
        ResearchResult(
            provider="stub",
            source_type="search_result",
            external_reference="2",
            retrieved_at=now,
            retention_class=RetentionClass.TRANSIENT,
            payload={
                "title": "Heavyweight Roots Reggae Sound System Dub",
                "description": "Vintage vinyl dub selection",
            },
        ),
        ResearchResult(
            provider="stub",
            source_type="search_result",
            external_reference="3",
            retrieved_at=now,
            retention_class=RetentionClass.TRANSIENT,
            payload={
                "title": "Cyberpunk Synthwave Night Drive Retro",
                "description": "Electronic analog synth arpeggio",
            },
        ),
    ]
    clusterer = TopicClusterer(similarity_threshold=0.20)
    clusters = clusterer.cluster(items)
    assert len(clusters) == 2
    keywords = clusterer.extract_keywords(items, top_k=5)
    assert "reggae" in keywords or "roots" in keywords


def test_watchlist_entry_creation():
    res = WatchlistEntry.build_manual_result(
        "UC_ROOTS_99",
        "Echoes Selector",
        custom_url="@echoesselector",
        description="Roots vinyl mixes",
    )
    entry = WatchlistEntry.from_research_result("src-1", "rp-1", res)
    assert entry.channel_external_id == "UC_ROOTS_99"
    assert entry.title == "Echoes Selector"
    assert entry.is_expired is False
