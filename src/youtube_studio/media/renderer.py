"""Single-track and multi-track video renderer with CapCut-style visualizers, motion FX, and Now-Playing overlays."""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from youtube_studio.domain.models.project import ChapterEntry


class VisualizerStyle(str, Enum):
    NONE = "none"
    LINE_WAVE = "line_wave"
    BAR_SPECTRUM = "bar_spectrum"
    MIRRORED_STEREO = "mirrored_stereo"
    DUB_OSCILLOSCOPE = "dub_oscilloscope"


@dataclass(frozen=True)
class VisualFXConfig:
    now_playing_overlay: bool = False
    progress_bar: bool = False
    slow_zoom: bool = False
    film_grain: bool = False
    vignette: bool = False
    spinning_vinyl: bool = False


@dataclass(frozen=True)
class RenderSpec:
    audio_path: Path
    image_path: Path
    output_path: Path
    resolution: str = "1920x1080"  # e.g. "1920x1080" or "1080x1920"
    fps: int = 30
    enable_waveform_overlay: bool = False
    visualizer_style: VisualizerStyle = VisualizerStyle.NONE
    visual_fx: VisualFXConfig = field(default_factory=VisualFXConfig)
    chapters: list[ChapterEntry] = field(default_factory=list)
    duration_ms: Optional[int] = None
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "256k"

    def parse_resolution(self) -> tuple[int, int]:
        parts = self.resolution.lower().split("x")
        if len(parts) != 2:
            raise ValueError(f"Invalid resolution '{self.resolution}'; expected WIDTHxHEIGHT")
        w, h = int(parts[0]), int(parts[1])
        if w <= 0 or h <= 0:
            raise ValueError(f"Resolution dimensions must be positive: {self.resolution}")
        return w, h

    def effective_visualizer_style(self) -> VisualizerStyle:
        if self.visualizer_style != VisualizerStyle.NONE:
            return self.visualizer_style
        if self.enable_waveform_overlay:
            return VisualizerStyle.LINE_WAVE
        return VisualizerStyle.NONE


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    resolution: str
    duration_ms: int
    command: list[str]
    used_fallback: bool = False
    srt_path: Optional[Path] = None


class VideoRendererService:
    """Combines mixed audio, artwork, multi-style visualizers, motion FX, and chapter overlays into MP4."""

    def __init__(self, ffmpeg_path: Optional[Path] = None) -> None:
        self._ffmpeg = ffmpeg_path or (
            Path(shutil.which("ffmpeg")) if shutil.which("ffmpeg") else None
        )

    def build_video_filtergraph(self, spec: RenderSpec) -> tuple[str, bool]:
        """
        Return (filter_expression, is_filter_complex).
        Builds the complete FFmpeg video filter chain including motion FX, visualizers,
        Now-Playing chapter titles, and progress bar.
        """
        width, height = spec.parse_resolution()
        vis = spec.effective_visualizer_style()
        fx = spec.visual_fx

        bg_filters: list[str] = [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        ]
        if fx.slow_zoom:
            bg_filters.append(
                f"zoompan=z='min(zoom+0.0004,1.12)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={spec.fps}"
            )
        if fx.spinning_vinyl:
            bg_filters.append("rotate='0.15*t:ow=rotw(0):oh=roth(0):c=none'")
        if fx.film_grain:
            bg_filters.append("noise=alls=7:allf=t+u")
        if fx.vignette:
            bg_filters.append("vignette=PI/5")

        # Post-composite overlays (Now Playing chapter text + Progress Bar)
        post_filters: list[str] = []
        total_sec = max(1.0, (spec.duration_ms or 60_000) / 1000.0)

        if fx.now_playing_overlay and spec.chapters:
            for idx, ch in enumerate(spec.chapters):
                start_s = max(0.0, ch.start_ms / 1000.0)
                end_s = (
                    max(start_s + 0.5, spec.chapters[idx + 1].start_ms / 1000.0)
                    if idx + 1 < len(spec.chapters)
                    else total_sec
                )
                safe_title = self._escape_drawtext(f"Now Playing: {ch.title}")
                post_filters.append(
                    f"drawtext=text='{safe_title}':x=48:y=48:fontsize=28:fontcolor=white:"
                    f"box=1:boxcolor=black@0.55:boxborderw=10:enable='between(t,{start_s:.2f},{end_s:.2f})'"
                )

        if fx.progress_bar:
            bar_h = max(6, height // 120)
            post_filters.append(
                f"drawbox=x=0:y=ih-{bar_h}:w='iw*(t/{total_sec:.2f})':h={bar_h}:color=0xe6a145@0.9:t=fill"
            )

        post_filters.append("format=yuv420p")

        if vis == VisualizerStyle.NONE:
            full_vf = ",".join(bg_filters + post_filters)
            return full_vf, False

        wave_h = max(90, height // 7)
        if vis == VisualizerStyle.BAR_SPECTRUM:
            vis_filter = f"showfreqs=s={width}x{wave_h}:mode=bar:fscale=log:colors=0xe6a145"
        elif vis == VisualizerStyle.MIRRORED_STEREO:
            vis_filter = (
                f"showwaves=s={width}x{wave_h}:mode=p2p:rate={spec.fps}:split_channels=1:colors=0xe6a145|0xb84b29"
            )
        elif vis == VisualizerStyle.DUB_OSCILLOSCOPE:
            vis_filter = (
                f"showwaves=s={width}x{wave_h}:mode=cline:rate={spec.fps}:colors=0xebe63e"
            )
        else:
            vis_filter = (
                f"showwaves=s={width}x{wave_h}:mode=line:rate={spec.fps}:colors=0xe6a145"
            )

        bg_chain = ",".join(bg_filters)
        post_chain = ",".join(post_filters)
        fc = (
            f"[0:v]{bg_chain}[bg];"
            f"[1:a]{vis_filter}[sw];"
            f"[bg][sw]overlay=0:H-h-36,{post_chain}[vout]"
        )
        return fc, True

    def build_command(self, spec: RenderSpec) -> list[str]:
        spec.parse_resolution()
        ffmpeg_bin = str(self._ffmpeg) if self._ffmpeg else "ffmpeg"
        filter_str, is_complex = self.build_video_filtergraph(spec)

        cmd: list[str] = [
            ffmpeg_bin,
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(spec.fps),
            "-i",
            str(spec.image_path),
            "-i",
            str(spec.audio_path),
        ]

        if is_complex:
            cmd.extend(["-filter_complex", filter_str, "-map", "[vout]", "-map", "1:a"])
        else:
            cmd.extend(["-vf", filter_str, "-map", "0:v", "-map", "1:a"])

        cmd.extend(
            [
                "-c:v",
                spec.video_codec,
                "-tune",
                "stillimage",
                "-c:a",
                spec.audio_codec,
                "-b:a",
                spec.audio_bitrate,
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-shortest",
                str(spec.output_path),
            ]
        )
        return cmd

    def render(
        self,
        spec: RenderSpec,
        *,
        allow_fallback: bool = True,
    ) -> RenderResult:
        if not spec.audio_path.exists():
            raise FileNotFoundError(f"Audio input not found: {spec.audio_path}")
        if not spec.image_path.exists():
            raise FileNotFoundError(f"Image input not found: {spec.image_path}")

        spec.parse_resolution()
        spec.output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = self.build_command(spec)
        expected_dur = spec.duration_ms or 1000

        srt_path: Optional[Path] = None
        if spec.visual_fx.now_playing_overlay and spec.chapters:
            srt_path = spec.output_path.with_suffix(".srt")
            self.write_now_playing_srt(spec.chapters, expected_dur, srt_path)

        if self._ffmpeg is not None and self._ffmpeg.exists():
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and spec.output_path.exists():
                return RenderResult(
                    output_path=spec.output_path,
                    resolution=spec.resolution,
                    duration_ms=expected_dur,
                    command=cmd,
                    used_fallback=False,
                    srt_path=srt_path,
                )
            if not allow_fallback:
                raise RuntimeError(f"FFmpeg video render failed: {res.stderr.strip()}")

        if allow_fallback:
            self._write_fallback_mp4_container(spec, duration_ms=expected_dur)
            return RenderResult(
                output_path=spec.output_path,
                resolution=spec.resolution,
                duration_ms=expected_dur,
                command=cmd,
                used_fallback=True,
                srt_path=srt_path,
            )

        raise RuntimeError("FFmpeg is not available and fallback container writer is disabled")

    @classmethod
    def write_now_playing_srt(
        cls,
        chapters: list[ChapterEntry],
        total_duration_ms: int,
        output_srt_path: Path,
    ) -> Path:
        """Write a SubRip (.srt) subtitle file displaying 'Now Playing: <Title>' for each chapter."""
        blocks: list[str] = []
        for idx, ch in enumerate(chapters):
            start_ms = max(0, ch.start_ms)
            end_ms = (
                max(start_ms + 500, chapters[idx + 1].start_ms)
                if idx + 1 < len(chapters)
                else max(start_ms + 1000, total_duration_ms)
            )
            blocks.append(
                f"{idx + 1}\n"
                f"{cls._format_srt_time(start_ms)} --> {cls._format_srt_time(end_ms)}\n"
                f"Now Playing: {ch.title}\n"
            )
        output_srt_path.write_text("\n".join(blocks), encoding="utf-8")
        return output_srt_path

    @staticmethod
    def _format_srt_time(ms: int) -> str:
        ms = max(0, ms)
        hours = ms // 3_600_000
        rem = ms % 3_600_000
        mins = rem // 60_000
        rem = rem % 60_000
        secs = rem // 1000
        millis = rem % 1000
        return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _escape_drawtext(text: str) -> str:
        cleaned = re.sub(r"['\"\\:%]", "", text)
        return cleaned.strip()

    @staticmethod
    def _write_fallback_mp4_container(spec: RenderSpec, *, duration_ms: int) -> None:
        width, height = spec.parse_resolution()

        def _box(box_type: bytes, payload: bytes) -> bytes:
            return struct.pack(">I", 8 + len(payload)) + box_type + payload

        ftyp = _box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2avc1mp41")
        meta_payload = json.dumps(
            {
                "generator": "youtube-automation-studio-fallback",
                "video_codec": spec.video_codec,
                "audio_codec": spec.audio_codec,
                "width": width,
                "height": height,
                "fps": spec.fps,
                "duration_ms": duration_ms,
                "visualizer_style": spec.effective_visualizer_style().value,
                "visual_fx": asdict(spec.visual_fx),
                "audio_source": str(spec.audio_path),
                "image_source": str(spec.image_path),
            }
        ).encode("utf-8")
        udta = _box(b"udta", meta_payload)
        spec.output_path.write_bytes(ftyp + udta)
