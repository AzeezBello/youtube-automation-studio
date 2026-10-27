"""FFmpeg / FFprobe detection and basic interrogation."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from youtube_studio.config import get_settings


@dataclass(frozen=True)
class FFmpegInfo:
    ffmpeg_path: Path
    ffprobe_path: Path
    ffmpeg_version: str
    ffprobe_version: str
    has_hwaccel: bool


class FFmpegService:
    """Locates and validates FFmpeg binaries; provides probe helpers."""

    def __init__(
        self,
        ffmpeg_path: Optional[Path] = None,
        ffprobe_path: Optional[Path] = None,
    ) -> None:
        settings = get_settings()
        self._ffmpeg = ffmpeg_path or settings.ffmpeg_path or self._find_binary("ffmpeg")
        self._ffprobe = ffprobe_path or settings.ffprobe_path or self._find_binary("ffprobe")

    @staticmethod
    def _find_binary(name: str) -> Optional[Path]:
        found = shutil.which(name)
        if found:
            return Path(found)
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            candidate = Path(prefix) / name
            if candidate.exists():
                return candidate
        if name == "ffmpeg":
            try:
                import imageio_ffmpeg

                exe = imageio_ffmpeg.get_ffmpeg_exe()
                if exe and Path(exe).exists():
                    return Path(exe)
            except Exception:
                pass
        return None

    @property
    def is_available(self) -> bool:
        return self._ffmpeg is not None and self._ffmpeg.exists()

    def get_info(self) -> Optional[FFmpegInfo]:
        if not self.is_available or self._ffmpeg is None:
            return None
        probe_bin = self._ffprobe or self._ffmpeg
        ffmpeg_ver = self._run_version(self._ffmpeg)
        ffprobe_ver = self._run_version(probe_bin)
        has_hw = self._detect_hwaccel()
        return FFmpegInfo(
            ffmpeg_path=self._ffmpeg,
            ffprobe_path=probe_bin,
            ffmpeg_version=ffmpeg_ver,
            ffprobe_version=ffprobe_ver,
            has_hwaccel=has_hw,
        )

    def probe(self, media_path: Path) -> dict[str, Any]:
        if not self.is_available or self._ffprobe is None:
            raise RuntimeError("FFprobe is not available")
        cmd = [
            str(self._ffprobe),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"FFprobe failed: {result.stderr.strip()}")
        return json.loads(result.stdout)

    def duration_ms(self, media_path: Path) -> Optional[int]:
        try:
            data = self.probe(media_path)
            fmt = data.get("format", {})
            duration = fmt.get("duration")
            if duration is not None:
                return int(float(duration) * 1000)
        except Exception:
            pass
        if self._ffmpeg is not None and self._ffmpeg.exists():
            try:
                import re

                res = subprocess.run(
                    [str(self._ffmpeg), "-i", str(media_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                )
                m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr or "")
                if m:
                    hrs = int(m.group(1))
                    mins = int(m.group(2))
                    secs = float(m.group(3))
                    return int((hrs * 3600 + mins * 60 + secs) * 1000)
            except Exception:
                pass
        return None

    def _run_version(self, binary: Path) -> str:
        try:
            result = subprocess.run(
                [str(binary), "-version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
            return first_line.strip() or "unknown"
        except Exception:
            return "unknown"

    def _detect_hwaccel(self) -> bool:
        if self._ffmpeg is None:
            return False
        try:
            result = subprocess.run(
                [str(self._ffmpeg), "-hwaccels"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            lines = (result.stdout or "").lower().splitlines()
            # Skip the header line
            accels = [ln.strip() for ln in lines[1:] if ln.strip()]
            return len(accels) > 0
        except Exception:
            return False
