"""Auto-Shorts / Reels Clipper: extracts peak-energy 9:16 vertical highlight videos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from youtube_studio.domain.models.project import ChapterEntry, TransitionConfig, TransitionType
from youtube_studio.media.dj_intelligence import DJIntelligenceService
from youtube_studio.media.mixer import AudioMixerService, MixTrackInput
from youtube_studio.media.renderer import (
    RenderSpec,
    VideoRendererService,
    VisualFXConfig,
    VisualizerStyle,
)
from youtube_studio.media.thumbnail import ThumbnailEngine, ThumbnailSpec


@dataclass(frozen=True)
class ShortClipResult:
    video_path: Path
    audio_path: Path
    thumbnail_path: Path
    start_ms: int
    end_ms: int
    duration_ms: int


class ShortsClipperService:
    """Automatically detects the highest-energy segment of a track/mix and renders a 9:16 vertical Short."""

    def __init__(
        self,
        *,
        dj_service: Optional[DJIntelligenceService] = None,
        mixer: Optional[AudioMixerService] = None,
        thumbnail_engine: Optional[ThumbnailEngine] = None,
        renderer: Optional[VideoRendererService] = None,
    ) -> None:
        self._dj = dj_service or DJIntelligenceService()
        self._mixer = mixer or AudioMixerService()
        self._thumbnails = thumbnail_engine or ThumbnailEngine()
        self._renderer = renderer or VideoRendererService()

    def create_highlight_short(
        self,
        source_audio_path: Path,
        output_dir: Path,
        *,
        title: str,
        subtitle: Optional[str] = None,
        palette: str = "warm_earth",
        source_duration_ms: Optional[int] = None,
        clip_duration_ms: int = 30_000,
        visualizer_style: VisualizerStyle = VisualizerStyle.BAR_SPECTRUM,
    ) -> ShortClipResult:
        if not source_audio_path.exists():
            raise FileNotFoundError(f"Source audio not found: {source_audio_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        analysis = self._dj.analyze_track(
            source_audio_path,
            duration_ms=source_duration_ms,
            highlight_duration_ms=clip_duration_ms,
        )
        start_ms = analysis.peak_window_start_ms
        end_ms = analysis.peak_window_end_ms
        eff_dur = max(1000, end_ms - start_ms)

        # 1. Trim peak audio segment with smooth 500ms fade-in/out
        short_audio_path = output_dir / "short_highlight_audio.wav"
        fade_ms = min(500, eff_dur // 4)
        mix_input = MixTrackInput(
            source_path=source_audio_path,
            source_duration_ms=source_duration_ms or end_ms,
            trim_start_ms=start_ms,
            trim_end_ms=end_ms,
            fade_in_ms=fade_ms,
            fade_out_ms=fade_ms,
            transition_config=TransitionConfig(transition_type=TransitionType.NONE, overlap_ms=0),
        )
        mix_res = self._mixer.mix([mix_input], short_audio_path)

        # 2. Render 9:16 vertical thumbnail & background (1080x1920)
        short_thumb_path = output_dir / "short_highlight_9x16.png"
        thumb_spec = ThumbnailSpec(
            title=title,
            subtitle=subtitle,
            badge_text=f"HIGHLIGHT · {analysis.bpm:.0f} BPM · {analysis.camelot_code}",
            palette=palette,
            aspect_ratio="9:16",
            width=1080,
            height=1920,
        )
        self._thumbnails.render(thumb_spec, short_thumb_path)

        # 3. Render 9:16 vertical MP4 video with visualizer + motion FX + progress bar
        short_video_path = output_dir / "short_highlight_9x16.mp4"
        render_spec = RenderSpec(
            audio_path=mix_res.output_path,
            image_path=short_thumb_path,
            output_path=short_video_path,
            resolution="1080x1920",
            visualizer_style=visualizer_style,
            visual_fx=VisualFXConfig(
                now_playing_overlay=True,
                progress_bar=True,
                slow_zoom=True,
                vignette=True,
            ),
            chapters=[ChapterEntry(start_ms=0, title=title)],
            duration_ms=mix_res.duration_ms,
        )
        render_res = self._renderer.render(render_spec)

        return ShortClipResult(
            video_path=render_res.output_path,
            audio_path=mix_res.output_path,
            thumbnail_path=short_thumb_path,
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=mix_res.duration_ms,
        )
