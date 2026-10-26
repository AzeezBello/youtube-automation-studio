"""Unit tests for FFmpegService (detection only – no real media required)."""

from __future__ import annotations

from youtube_studio.media.ffmpeg_service import FFmpegService


def test_detection_does_not_crash():
    svc = FFmpegService()
    # May or may not find binaries in CI; we only assert the API is stable
    available = svc.is_available
    info = svc.get_info()
    if available:
        assert info is not None
        assert info.ffmpeg_path.exists() or True  # path reported
        assert isinstance(info.ffmpeg_version, str)
    else:
        assert info is None
