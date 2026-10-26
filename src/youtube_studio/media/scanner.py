"""Recursive media library scanner (MP3/WAV/FLAC/M4A/AAC/OGG + images/videos)."""

from __future__ import annotations

import hashlib
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from youtube_studio.domain.models.media import MediaFile, MediaType
from youtube_studio.media.ffmpeg_service import FFmpegService
from youtube_studio.media.waveform import WaveformGenerator

if TYPE_CHECKING:
    from youtube_studio.domain.services.media_service import MediaLibraryService

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ScanSummary:
    scanned_files: list[MediaFile] = field(default_factory=list)
    duplicates_by_hash: dict[str, list[MediaFile]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class MediaScanner:
    """Scans directories recursively, extracts audio metadata/duration/waveforms, and detects duplicates."""

    def __init__(
        self,
        *,
        ffmpeg_service: Optional[FFmpegService] = None,
        waveform_generator: Optional[WaveformGenerator] = None,
        include_waveforms: bool = True,
    ) -> None:
        self._ffmpeg = ffmpeg_service or FFmpegService()
        self._waveform = waveform_generator or WaveformGenerator()
        self._include_waveforms = include_waveforms

    def scan_directory(
        self,
        root_dir: Path,
        *,
        channel_id: Optional[str] = None,
        media_service: Optional[MediaLibraryService] = None,
        audio_only: bool = True,
    ) -> ScanSummary:
        root = root_dir.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {root}")

        summary = ScanSummary()
        by_hash: dict[str, list[MediaFile]] = {}

        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            media_type = self._classify_extension(file_path.suffix)
            if media_type is None:
                continue
            if audio_only and media_type != MediaType.AUDIO:
                continue

            try:
                media_file = self.inspect_file(file_path, channel_id=channel_id)
                if media_service is not None:
                    media_file = media_service.upsert(media_file)
                summary.scanned_files.append(media_file)
                if media_file.file_hash:
                    by_hash.setdefault(media_file.file_hash, []).append(media_file)
            except Exception as exc:
                summary.errors[str(file_path)] = str(exc)

        summary.duplicates_by_hash = {h: group for h, group in by_hash.items() if len(group) > 1}
        return summary

    def inspect_file(
        self,
        file_path: Path,
        *,
        channel_id: Optional[str] = None,
    ) -> MediaFile:
        resolved = file_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {resolved}")

        media_type = self._classify_extension(resolved.suffix) or MediaType.OTHER
        file_hash = self._compute_sha256(resolved)
        stat = resolved.stat()

        metadata: dict[str, Any] = {
            "filename": resolved.name,
            "extension": resolved.suffix.lower(),
            "size_bytes": stat.st_size,
            "title": resolved.stem,
        }
        duration_ms: Optional[int] = None

        if media_type == MediaType.AUDIO:
            dur, tags = self._extract_audio_info(resolved)
            duration_ms = dur
            metadata.update(tags)
            if self._include_waveforms:
                try:
                    wf = self._waveform.analyze(resolved, bins=32)
                    metadata["waveform_peaks"] = wf.peaks
                    metadata["waveform_rms"] = wf.rms
                    metadata["fingerprint"] = wf.fingerprint
                except Exception:
                    pass

        return MediaFile(
            channel_id=channel_id,
            path=str(resolved),
            file_hash=file_hash,
            media_type=media_type,
            duration_ms=duration_ms,
            metadata=metadata,
            last_scanned_at=_utcnow(),
        )

    def _extract_audio_info(self, path: Path) -> tuple[Optional[int], dict[str, Any]]:
        info: dict[str, Any] = {}
        duration_ms: Optional[int] = None

        # 1. Standard library wave module for .wav files
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    channels = wf.getnchannels()
                    if rate > 0:
                        duration_ms = int((frames / rate) * 1000)
                    info["sample_rate"] = rate
                    info["channels"] = channels
            except Exception:
                pass

        # 2. Mutagen metadata & duration extraction (if installed)
        try:
            import mutagen

            audio = mutagen.File(str(path), easy=True)
            if audio is not None:
                if getattr(audio, "info", None) is not None:
                    length = getattr(audio.info, "length", None)
                    if length is not None and duration_ms is None:
                        duration_ms = int(float(length) * 1000)
                    sample_rate = getattr(audio.info, "sample_rate", None)
                    if sample_rate:
                        info["sample_rate"] = int(sample_rate)
                    bitrate = getattr(audio.info, "bitrate", None)
                    if bitrate:
                        info["bitrate"] = int(bitrate)
                if audio.tags:
                    for key in ("title", "artist", "album", "genre", "date"):
                        val = audio.tags.get(key)
                        if val:
                            info[key] = val[0] if isinstance(val, list) else str(val)
        except Exception:
            pass

        # 3. FFprobe fallback
        if duration_ms is None and self._ffmpeg.is_available:
            duration_ms = self._ffmpeg.duration_ms(path)

        return duration_ms, info

    @staticmethod
    def _classify_extension(ext: str) -> Optional[MediaType]:
        lower = ext.lower()
        if lower in AUDIO_EXTENSIONS:
            return MediaType.AUDIO
        if lower in IMAGE_EXTENSIONS:
            return MediaType.IMAGE
        if lower in VIDEO_EXTENSIONS:
            return MediaType.VIDEO
        return None

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
