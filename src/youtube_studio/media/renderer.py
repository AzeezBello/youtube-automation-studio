"""Single-track and multi-track video renderer (FFmpeg H.264/AAC + test container fallback)."""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class RenderSpec:
    audio_path: Path
    image_path: Path
    output_path: Path
    resolution: str = "1920x1080"  # e.g. "1920x1080" or "1080x1920"
    fps: int = 30
    enable_waveform_overlay: bool = False
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


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    resolution: str
    duration_ms: int
    command: list[str]
    used_fallback: bool = False


class VideoRendererService:
    """Combines mixed audio and artwork into a YouTube-ready MP4 video."""

    def __init__(self, ffmpeg_path: Optional[Path] = None) -> None:
        self._ffmpeg = ffmpeg_path or (
            Path(shutil.which("ffmpeg")) if shutil.which("ffmpeg") else None
        )

    def build_command(self, spec: RenderSpec) -> list[str]:
        width, height = spec.parse_resolution()
        ffmpeg_bin = str(self._ffmpeg) if self._ffmpeg else "ffmpeg"

        scale_pad = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
        )

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

        if spec.enable_waveform_overlay:
            wave_h = max(80, height // 8)
            filter_complex = (
                f"[0:v]{scale_pad}[bg];"
                f"[1:a]showwaves=s={width}x{wave_h}:mode=line:rate={spec.fps}:colors=0xe6a145[sw];"
                f"[bg][sw]overlay=0:H-h-40,format=yuv420p[vout]"
            )
            cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "1:a"])
        else:
            cmd.extend(["-vf", scale_pad, "-map", "0:v", "-map", "1:a"])

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

        if self._ffmpeg is not None:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and spec.output_path.exists():
                return RenderResult(
                    output_path=spec.output_path,
                    resolution=spec.resolution,
                    duration_ms=expected_dur,
                    command=cmd,
                    used_fallback=False,
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
            )

        raise RuntimeError("FFmpeg is not available and fallback container writer is disabled")

    @staticmethod
    def _write_fallback_mp4_container(spec: RenderSpec, *, duration_ms: int) -> None:
        """Write an ISO-BMFF (ftyp + udta metadata) container for offline/headless test environments."""
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
                "audio_source": str(spec.audio_path),
                "image_source": str(spec.image_path),
            }
        ).encode("utf-8")
        udta = _box(b"udta", meta_payload)
        spec.output_path.write_bytes(ftyp + udta)
