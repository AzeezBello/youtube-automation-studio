"""Waveform peak extraction, audio fingerprinting, and waveform image rendering."""

from __future__ import annotations

import array
import hashlib
import math
import shutil
import struct
import subprocess
import wave
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class WaveformData:
    peaks: list[float]  # Normalized [0.0, 1.0] peak envelope
    rms: float
    fingerprint: str  # Compact hex fingerprint of normalized energy bins
    bins: int


class WaveformGenerator:
    """Computes normalized peak envelopes, compact fingerprints, and PNG waveform renders."""

    def __init__(self, ffmpeg_path: Optional[Path] = None) -> None:
        self._ffmpeg = ffmpeg_path or (
            Path(shutil.which("ffmpeg")) if shutil.which("ffmpeg") else None
        )

    def analyze(self, audio_path: Path, *, bins: int = 64) -> WaveformData:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        samples = self._read_pcm_samples(audio_path)
        if samples:
            peaks, rms = self._compute_peaks_and_rms(samples, bins=bins)
        else:
            peaks, rms = self._fallback_peaks_from_bytes(audio_path, bins=bins)

        fingerprint = self._compute_fingerprint(peaks)
        return WaveformData(peaks=peaks, rms=round(rms, 4), fingerprint=fingerprint, bins=bins)

    def render_waveform_png(
        self,
        waveform: WaveformData,
        output_path: Path,
        *,
        width: int = 800,
        height: int = 160,
        fg_rgb: tuple[int, int, int] = (230, 161, 69),
        bg_rgb: tuple[int, int, int] = (24, 24, 28),
    ) -> Path:
        """Render a waveform overview PNG to disk (uses Pillow if available, pure-Python PNG fallback)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (width, height), color=bg_rgb)
            draw = ImageDraw.Draw(img)
            mid_y = height // 2
            num_bars = max(1, len(waveform.peaks))
            bar_step = max(1.0, width / num_bars)
            bar_w = max(1, int(bar_step * 0.7))

            for idx, peak in enumerate(waveform.peaks):
                x0 = int(idx * bar_step)
                x1 = min(width - 1, x0 + bar_w)
                half_h = max(1, int(peak * (height * 0.44)))
                draw.rectangle([x0, mid_y - half_h, x1, mid_y + half_h], fill=fg_rgb)

            img.save(output_path, format="PNG")
            return output_path
        except ImportError:
            return self._write_minimal_png(
                output_path,
                width=width,
                height=height,
                peaks=waveform.peaks,
                fg_rgb=fg_rgb,
                bg_rgb=bg_rgb,
            )

    def _read_pcm_samples(self, audio_path: Path) -> Optional[array.array[int]]:
        # Fast path for standard 16-bit PCM WAV files using stdlib wave
        if audio_path.suffix.lower() == ".wav":
            try:
                with wave.open(str(audio_path), "rb") as wf:
                    sampwidth = wf.getsampwidth()
                    nframes = wf.getnframes()
                    raw = wf.readframes(min(nframes, 8000 * 600))
                    if sampwidth == 2 and len(raw) >= 2:
                        arr = array.array("h")
                        arr.frombytes(raw[: len(raw) - (len(raw) % 2)])
                        return arr
            except Exception:
                pass

        # Decode via FFmpeg into 8kHz mono 16-bit signed PCM if FFmpeg is available
        if self._ffmpeg is not None:
            try:
                cmd = [
                    str(self._ffmpeg),
                    "-v",
                    "quiet",
                    "-i",
                    str(audio_path),
                    "-f",
                    "s16le",
                    "-ac",
                    "1",
                    "-ar",
                    "8000",
                    "-",
                ]
                res = subprocess.run(cmd, capture_output=True, check=False, timeout=30)
                if res.returncode == 0 and len(res.stdout) >= 2:
                    raw = res.stdout
                    arr = array.array("h")
                    arr.frombytes(raw[: len(raw) - (len(raw) % 2)])
                    return arr
            except Exception:
                pass
        return None

    @staticmethod
    def _compute_peaks_and_rms(
        samples: array.array[int],
        *,
        bins: int,
    ) -> tuple[list[float], float]:
        total = len(samples)
        if total == 0:
            return [0.0] * bins, 0.0

        step = max(1, total // bins)
        peaks: list[float] = []
        sum_sq = 0.0
        counted = 0

        for i in range(bins):
            start = i * step
            end = min(total, start + step) if i < bins - 1 else total
            if start >= total:
                peaks.append(0.0)
                continue
            window = samples[start:end]
            if not window:
                peaks.append(0.0)
                continue
            max_abs = max(abs(x) for x in window) / 32768.0
            peaks.append(round(min(1.0, max_abs), 4))
            # Subsample within window for fast RMS
            stride = max(1, len(window) // 64)
            for s in window[::stride]:
                norm = s / 32768.0
                sum_sq += norm * norm
                counted += 1

        rms = math.sqrt(sum_sq / max(1, counted))
        return peaks, min(1.0, rms)

    @staticmethod
    def _fallback_peaks_from_bytes(audio_path: Path, *, bins: int) -> tuple[list[float], float]:
        data = audio_path.read_bytes()
        if not data:
            return [0.0] * bins, 0.0
        step = max(1, len(data) // bins)
        peaks: list[float] = []
        for i in range(bins):
            chunk = data[i * step : (i + 1) * step]
            if not chunk:
                peaks.append(0.0)
                continue
            digest = hashlib.sha256(chunk).digest()
            val = digest[0] / 255.0
            peaks.append(round(val, 4))
        rms = sum(peaks) / max(1, len(peaks))
        return peaks, rms

    @staticmethod
    def _compute_fingerprint(peaks: list[float]) -> str:
        """Quantize peaks into 4-bit nibbles and hash/encode into a compact hex fingerprint."""
        quantized = bytes(min(15, max(0, int(round(p * 15)))) for p in peaks)
        return hashlib.sha256(quantized).hexdigest()[:32]

    @staticmethod
    def _write_minimal_png(
        output_path: Path,
        *,
        width: int,
        height: int,
        peaks: list[float],
        fg_rgb: tuple[int, int, int],
        bg_rgb: tuple[int, int, int],
    ) -> Path:
        """Pure-Python valid RGB PNG writer used when Pillow is not installed."""
        mid_y = height // 2
        num_bars = max(1, len(peaks))
        rows = bytearray()
        for y in range(height):
            rows.append(0)  # Filter type 0 (None)
            dist = abs(y - mid_y) / max(1.0, height * 0.44)
            for x in range(width):
                bin_idx = min(num_bars - 1, int((x / max(1, width)) * num_bars))
                if dist <= peaks[bin_idx]:
                    rows.extend(fg_rgb)
                else:
                    rows.extend(bg_rgb)

        def _chunk(chunk_type: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        compressed = zlib.compress(bytes(rows), level=6)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", compressed)
            + _chunk(b"IEND", b"")
        )
        output_path.write_bytes(png_bytes)
        return output_path
