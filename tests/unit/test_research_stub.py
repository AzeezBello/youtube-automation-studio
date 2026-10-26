"""Unit tests for StubResearchProvider."""

from __future__ import annotations

from youtube_studio.research.providers.stub import StubResearchProvider
from youtube_studio.research.providers.base import RetentionClass


def test_stub_search_returns_results():
    provider = StubResearchProvider()
    assert provider.name == "stub"
    results = provider.search("roots reggae mix", max_results=3)
    assert len(results) == 3
    for r in results:
        assert r.provider == "stub"
        assert r.retention_class == RetentionClass.TRANSIENT
        assert "title" in r.payload
        assert r.expires_at() is not None
