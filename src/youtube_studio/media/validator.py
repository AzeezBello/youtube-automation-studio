"""Output media validation (duration, codecs, streams, resolution, container integrity)."""

from __future__ import annotations

import json
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from youtube_studio.media.ffmpeg_service import FFmpegService


@dataclass
class ValidationReport:
    is_valid: bool
    path: Path
    size_bytes: int = 0
    has_audio_stream: bool = False
    has_video_stream: bool = False
    audio_codec: Optional[str] = None
    video_codec: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_ms: Optional[int] = None
    errors: list[str] = field(default_factory=list)


class MediaValidator:
    """Validates rendered video, mixed audio, and thumbnail assets before packaging/publishing."""

    def __init__(self, ffmpeg_service: Optional[FFmpegService] = None) -> None:
        self._ffmpeg = ffmpeg_service or FFmpegService()

    def validate_video(
        self,
        video_path: Path,
        *,
        expected_duration_ms: Optional[int] = None,
        duration_tolerance_ms: int = 1500,
        expected_resolution: Optional[str] = None,
    ) -> ValidationReport:
        if not video_path.exists():
            return ValidationReport(
                is_valid=False,
                path=video_path,
                errors=[f"File does not exist: {video_path}"],
            )

        size_bytes = video_path.stat().st_size
        if size_bytes == 0:
            return ValidationReport(
                is_valid=False,
                path=video_path,
                size_bytes=0,
                errors=["Video file is empty (0 bytes)"],
            )

        report = ValidationReport(is_valid=True, path=video_path, size_bytes=size_bytes)

        # 1. Try FFprobe inspection if available and not a fallback container
        probed = False
        if self._ffmpeg.is_available:
            try:
                data = self._ffmpeg.probe(video_path)
                streams = data.get("streams", [])
                fmt = data.get("format", {})
                if streams:
                    probed = True
                    for s in streams:
                        codec_type = s.get("codec_type")
                        if codec_type == "video":
                            report.has_video_stream = True
                            report.video_codec = s.get("codec_name")
                            report.width = int(s["width"]) if "width" in s else None
                            report.height = int(s["height"]) if "height" in s else None
                        elif codec_type == "audio":
                            report.has_audio_stream = True
                            report.audio_codec = s.get("codec_name")
                    if "duration" in fmt:
                        report.duration_ms = int(float(fmt["duration"]) * 1000)
            except Exception:
                probed = False

        # 1b. If ffprobe is absent but ffmpeg is available, inspect streams via `ffmpeg -i`
        if not probed and self._ffmpeg.is_available and self._ffmpeg._ffmpeg is not None:
            try:
                import re
                import subprocess

                res = subprocess.run(
                    [str(self._ffmpeg._ffmpeg), "-i", str(video_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                )
                err = res.stderr or ""
                v_match = re.search(r"Stream\s+#\d+:\d+.*Video:\s*([a-zA-Z0-9_]+).*?,\s*(\d{2,5})x(\d{2,5})", err)
                a_match = re.search(r"Stream\s+#\d+:\d+.*Audio:\s*([a-zA-Z0-9_]+)", err)
                d_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
                if v_match or a_match:
                    probed = True
                    if v_match:
                        report.has_video_stream = True
                        report.video_codec = v_match.group(1)
                        report.width = int(v_match.group(2))
                        report.height = int(v_match.group(3))
                    if a_match:
                        report.has_audio_stream = True
                        report.audio_codec = a_match.group(1)
                    if d_match:
                        hrs = int(d_match.group(1))
                        mins = int(d_match.group(2))
                        secs = float(d_match.group(3))
                        report.duration_ms = int((hrs * 3600 + mins * 60 + secs) * 1000)
            except Exception:
                probed = False

        # 2. Fallback ISO-BMFF (ftyp + udta) inspection
        if not probed:
            self._inspect_mp4_header(video_path, report)

        if not report.has_video_stream:
            report.errors.append("Missing video stream")
        if not report.has_audio_stream:
            report.errors.append("Missing audio stream")

        if expected_resolution and report.width and report.height:
            actual_res = f"{report.width}x{report.height}"
            if actual_res != expected_resolution.lower():
                report.errors.append(
                    f"Resolution mismatch: expected {expected_resolution}, got {actual_res}"
                )

        if (
            expected_duration_ms is not None
            and report.duration_ms is not None
            and abs(report.duration_ms - expected_duration_ms) > duration_tolerance_ms
        ):
            report.errors.append(
                f"Duration mismatch: expected {expected_duration_ms}ms ± {duration_tolerance_ms}ms, "
                f"got {report.duration_ms}ms"
            )

        report.is_valid = len(report.errors) == 0
        return report

    def validate_audio(
        self,
        audio_path: Path,
        *,
        expected_duration_ms: Optional[int] = None,
        duration_tolerance_ms: int = 1500,
    ) -> ValidationReport:
        if not audio_path.exists():
            return ValidationReport(
                is_valid=False,
                path=audio_path,
                errors=[f"Audio file does not exist: {audio_path}"],
            )

        size_bytes = audio_path.stat().st_size
        if size_bytes == 0:
            return ValidationReport(
                is_valid=False,
                path=audio_path,
                size_bytes=0,
                errors=["Audio file is empty (0 bytes)"],
            )

        report = ValidationReport(is_valid=True, path=audio_path, size_bytes=size_bytes)

        if audio_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as wf:
                    rate = wf.getframerate()
                    frames = wf.getnframes()
                    if rate > 0 and frames > 0:
                        report.has_audio_stream = True
                        report.audio_codec = "pcm_s16le"
                        report.duration_ms = int((frames / rate) * 1000)
            except Exception as exc:
                report.errors.append(f"Invalid WAV file: {exc}")

        if not report.has_audio_stream and self._ffmpeg.is_available:
            try:
                data = self._ffmpeg.probe(audio_path)
                for s in data.get("streams", []):
                    if s.get("codec_type") == "audio":
                        report.has_audio_stream = True
                        report.audio_codec = s.get("codec_name")
                dur = data.get("format", {}).get("duration")
                if dur is not None:
                    report.duration_ms = int(float(dur) * 1000)
            except Exception as exc:
                report.errors.append(f"Audio probe failed: {exc}")

        if not report.has_audio_stream:
            report.errors.append("Missing valid audio stream")

        if (
            expected_duration_ms is not None
            and report.duration_ms is not None
            and abs(report.duration_ms - expected_duration_ms) > duration_tolerance_ms
        ):
            report.errors.append(
                f"Audio duration mismatch: expected {expected_duration_ms}ms ± {duration_tolerance_ms}ms, "
                f"got {report.duration_ms}ms"
            )

        report.is_valid = len(report.errors) == 0
        return report

    def validate_image(
        self,
        image_path: Path,
        *,
        expected_width: Optional[int] = None,
        expected_height: Optional[int] = None,
    ) -> ValidationReport:
        if not image_path.exists():
            return ValidationReport(
                is_valid=False,
                path=image_path,
                errors=[f"Image file does not exist: {image_path}"],
            )
        raw = image_path.read_bytes()
        if len(raw) < 24:
            return ValidationReport(
                is_valid=False,
                path=image_path,
                size_bytes=len(raw),
                errors=["Image file is truncated or empty"],
            )

        report = ValidationReport(is_valid=True, path=image_path, size_bytes=len(raw))
        if raw[:8] == b"\x89PNG\r\n\x1a\n" and raw[12:16] == b"IHDR":
            w, h = struct.unpack(">II", raw[16:24])
            report.width = w
            report.height = h
            report.has_video_stream = True
            report.video_codec = "png"
        else:
            try:
                from PIL import Image

                with Image.open(image_path) as img:
                    report.width, report.height = img.size
                    report.has_video_stream = True
                    report.video_codec = (img.format or "image").lower()
            except Exception as exc:
                report.errors.append(f"Unrecognized image format: {exc}")

        if expected_width and report.width != expected_width:
            report.errors.append(f"Image width mismatch: expected {expected_width}, got {report.width}")
        if expected_height and report.height != expected_height:
            report.errors.append(
                f"Image height mismatch: expected {expected_height}, got {report.height}"
            )

        report.is_valid = len(report.errors) == 0
        return report

    @staticmethod
    def _inspect_mp4_header(video_path: Path, report: ValidationReport) -> None:
        raw = video_path.read_bytes()
        if len(raw) < 16 or raw[4:8] != b"ftyp":
            return
        offset = 0
        while offset + 8 <= len(raw):
            box_size = struct.unpack(">I", raw[offset : offset + 4])[0]
            box_type = raw[offset + 4 : offset + 8]
            if box_size < 8 or offset + box_size > len(raw):
                break
            if box_type == b"udta":
                payload = raw[offset + 8 : offset + box_size]
                try:
                    meta = json.loads(payload.decode("utf-8"))
                    report.has_video_stream = True
                    report.has_audio_stream = True
                    report.video_codec = meta.get("video_codec", "h264")
                    report.audio_codec = meta.get("audio_codec", "aac")
                    report.width = meta.get("width")
                    report.height = meta.get("height")
                    report.duration_ms = meta.get("duration_ms")
                except Exception:
                    pass
            offset += box_size
