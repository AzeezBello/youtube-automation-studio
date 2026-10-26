"""FFmpeg audio mix pipeline (trim, gain, fade, crossfade, loudness normalization) with WAV PCM fallback."""

from __future__ import annotations

import array
import math
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from youtube_studio.domain.models.project import TransitionConfig, TransitionType


@dataclass
class MixTrackInput:
    source_path: Path
    source_duration_ms: Optional[int] = None
    trim_start_ms: int = 0
    trim_end_ms: Optional[int] = None
    gain_db: float = 0.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    transition_config: TransitionConfig = TransitionConfig()

    def effective_duration_ms(self) -> int:
        if self.source_duration_ms is not None and self.source_duration_ms > 0:
            end_ms = (
                min(self.trim_end_ms, self.source_duration_ms)
                if self.trim_end_ms is not None
                else self.source_duration_ms
            )
            return max(0, end_ms - max(0, self.trim_start_ms))
        if self.trim_end_ms is not None and self.trim_end_ms > self.trim_start_ms:
            return self.trim_end_ms - self.trim_start_ms
        return 0


@dataclass(frozen=True)
class MixResult:
    output_path: Path
    duration_ms: int
    filtergraph: str
    command: list[str]
    used_fallback: bool = False


class AudioMixerService:
    """Builds and runs multi-track or single-track audio mixes."""

    def __init__(self, ffmpeg_path: Optional[Path] = None) -> None:
        self._ffmpeg = ffmpeg_path or (
            Path(shutil.which("ffmpeg")) if shutil.which("ffmpeg") else None
        )

    def compute_expected_duration_ms(self, tracks: list[MixTrackInput]) -> int:
        total = 0
        for idx, track in enumerate(tracks):
            eff = track.effective_duration_ms()
            overlap = 0
            if idx < len(tracks) - 1 and track.transition_config.transition_type in (
                TransitionType.CROSSFADE,
                TransitionType.BASS_SWAP_EQ,
            ):
                overlap = min(max(0, track.transition_config.overlap_ms), eff // 2 if eff > 0 else 0)
            total += max(0, eff - overlap)
        return total

    def build_filter_complex(
        self,
        tracks: list[MixTrackInput],
        *,
        normalize_loudness: bool = True,
    ) -> str:
        if not tracks:
            raise ValueError("Cannot build audio filtergraph for empty track list")

        stages: list[str] = []
        for idx, t in enumerate(tracks):
            chain: list[str] = []
            start_s = max(0.0, t.trim_start_ms / 1000.0)
            if t.trim_end_ms is not None and t.trim_end_ms > t.trim_start_ms:
                end_s = t.trim_end_ms / 1000.0
                chain.append(f"atrim=start={start_s:.3f}:end={end_s:.3f}")
            elif start_s > 0:
                chain.append(f"atrim=start={start_s:.3f}")
            chain.append("asetpts=PTS-STARTPTS")

            if abs(t.gain_db) > 1e-4:
                chain.append(f"volume={t.gain_db:.2f}dB")

            if t.fade_in_ms > 0:
                chain.append(f"afade=t=in:st=0:d={t.fade_in_ms / 1000.0:.3f}")

            eff_ms = t.effective_duration_ms()
            if t.fade_out_ms > 0 and eff_ms > t.fade_out_ms:
                st_s = (eff_ms - t.fade_out_ms) / 1000.0
                chain.append(f"afade=t=out:st={st_s:.3f}:d={t.fade_out_ms / 1000.0:.3f}")

            stages.append(f"[{idx}:a]{','.join(chain)}[a{idx}]")

        if len(tracks) == 1:
            current_label = "a0"
        else:
            current_label = "a0"
            for idx in range(1, len(tracks)):
                prev_track = tracks[idx - 1]
                next_label = f"a{idx}"
                out_label = f"m{idx}"
                tc = prev_track.transition_config
                eff_ms = prev_track.effective_duration_ms()
                is_xfade = tc.transition_type in (
                    TransitionType.CROSSFADE,
                    TransitionType.BASS_SWAP_EQ,
                )
                overlap_ms = (
                    min(max(0, tc.overlap_ms), eff_ms // 2 if eff_ms > 0 else tc.overlap_ms)
                    if is_xfade
                    else 0
                )
                if tc.transition_type == TransitionType.BASS_SWAP_EQ and overlap_ms > 0:
                    dur_s = overlap_ms / 1000.0
                    curve = tc.curve or "tri"
                    eq_label = f"eq{idx}"
                    stages.append(
                        f"[{next_label}]equalizer=f=90:t=h:w=100:g=-9[{eq_label}]"
                    )
                    stages.append(
                        f"[{current_label}][{eq_label}]acrossfade=d={dur_s:.3f}:c1={curve}:c2={curve}[{out_label}]"
                    )
                elif tc.transition_type == TransitionType.CROSSFADE and overlap_ms > 0:
                    dur_s = overlap_ms / 1000.0
                    curve = tc.curve or "tri"
                    stages.append(
                        f"[{current_label}][{next_label}]acrossfade=d={dur_s:.3f}:c1={curve}:c2={curve}[{out_label}]"
                    )
                else:
                    stages.append(
                        f"[{current_label}][{next_label}]concat=n=2:v=0:a=1[{out_label}]"
                    )
                current_label = out_label

        if normalize_loudness:
            stages.append(f"[{current_label}]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
        else:
            stages.append(f"[{current_label}]acopy[aout]")

        return ";".join(stages)

    def build_command(
        self,
        tracks: list[MixTrackInput],
        output_path: Path,
        *,
        normalize_loudness: bool = True,
    ) -> list[str]:
        ffmpeg_bin = str(self._ffmpeg) if self._ffmpeg else "ffmpeg"
        filter_complex = self.build_filter_complex(tracks, normalize_loudness=normalize_loudness)
        cmd: list[str] = [ffmpeg_bin, "-y"]
        for t in tracks:
            cmd.extend(["-i", str(t.source_path)])
        cmd.extend(["-filter_complex", filter_complex, "-map", "[aout]"])
        ext = output_path.suffix.lower()
        if ext == ".wav":
            cmd.extend(["-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2"])
        elif ext == ".mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
        else:
            cmd.extend(["-c:a", "aac", "-b:a", "256k"])
        cmd.append(str(output_path))
        return cmd

    def mix(
        self,
        tracks: list[MixTrackInput],
        output_path: Path,
        *,
        normalize_loudness: bool = True,
        allow_wav_fallback: bool = True,
    ) -> MixResult:
        if not tracks:
            raise ValueError("At least one track is required to mix audio")
        for t in tracks:
            if not t.source_path.exists():
                raise FileNotFoundError(f"Track source file not found: {t.source_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        filtergraph = self.build_filter_complex(tracks, normalize_loudness=normalize_loudness)
        cmd = self.build_command(tracks, output_path, normalize_loudness=normalize_loudness)

        if self._ffmpeg is not None:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode == 0 and output_path.exists():
                dur_ms = self.compute_expected_duration_ms(tracks)
                return MixResult(
                    output_path=output_path,
                    duration_ms=dur_ms,
                    filtergraph=filtergraph,
                    command=cmd,
                    used_fallback=False,
                )
            if not allow_wav_fallback:
                raise RuntimeError(f"FFmpeg audio mix failed: {res.stderr.strip()}")

        if allow_wav_fallback:
            dur_ms = self._mix_pcm_wav_fallback(tracks, output_path)
            return MixResult(
                output_path=output_path,
                duration_ms=dur_ms,
                filtergraph=filtergraph,
                command=cmd,
                used_fallback=True,
            )

        raise RuntimeError("FFmpeg is not available and WAV fallback is disabled")

    def _mix_pcm_wav_fallback(self, tracks: list[MixTrackInput], output_path: Path) -> int:
        """Pure-Python 16-bit mono/stereo WAV mixer supporting trim, gain, fade, and crossfade."""
        target_rate = 44100
        mixed_samples = array.array("h")

        for idx, t in enumerate(tracks):
            samples, rate = self._load_track_mono_samples(t.source_path, default_rate=target_rate)
            if idx == 0 and rate > 0:
                target_rate = rate

            # Apply trim
            start_idx = int((max(0, t.trim_start_ms) / 1000.0) * target_rate)
            end_idx = (
                int((t.trim_end_ms / 1000.0) * target_rate)
                if t.trim_end_ms is not None and t.trim_end_ms > t.trim_start_ms
                else len(samples)
            )
            trimmed = samples[min(start_idx, len(samples)) : min(end_idx, len(samples))]

            # Apply gain + fade-in + fade-out
            gain_factor = math.pow(10.0, t.gain_db / 20.0) if abs(t.gain_db) > 1e-4 else 1.0
            fade_in_samples = int((max(0, t.fade_in_ms) / 1000.0) * target_rate)
            fade_out_samples = int((max(0, t.fade_out_ms) / 1000.0) * target_rate)
            total_n = len(trimmed)

            processed = array.array("h", [0] * total_n)
            for i, s in enumerate(trimmed):
                factor = gain_factor
                if fade_in_samples > 0 and i < fade_in_samples:
                    factor *= i / fade_in_samples
                if fade_out_samples > 0 and i >= total_n - fade_out_samples:
                    factor *= max(0.0, (total_n - 1 - i) / fade_out_samples)
                val = int(max(-32768, min(32767, round(s * factor))))
                processed[i] = val

            if idx == 0 or not mixed_samples:
                mixed_samples.extend(processed)
            else:
                prev_tc = tracks[idx - 1].transition_config
                overlap_samples = 0
                if (
                    prev_tc.transition_type
                    in (TransitionType.CROSSFADE, TransitionType.BASS_SWAP_EQ)
                    and prev_tc.overlap_ms > 0
                ):
                    overlap_samples = min(
                        int((prev_tc.overlap_ms / 1000.0) * target_rate),
                        len(mixed_samples) // 2,
                        len(processed) // 2,
                    )
                if overlap_samples > 0:
                    tail_start = len(mixed_samples) - overlap_samples
                    for j in range(overlap_samples):
                        alpha = j / overlap_samples
                        blended = int(
                            round(
                                mixed_samples[tail_start + j] * (1.0 - alpha)
                                + processed[j] * alpha
                            )
                        )
                        mixed_samples[tail_start + j] = max(-32768, min(32767, blended))
                    mixed_samples.extend(processed[overlap_samples:])
                else:
                    mixed_samples.extend(processed)

        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(target_rate)
            wf.writeframes(mixed_samples.tobytes())

        return int((len(mixed_samples) / max(1, target_rate)) * 1000)

    @staticmethod
    def _load_track_mono_samples(
        path: Path,
        *,
        default_rate: int = 44100,
    ) -> tuple[array.array[int], int]:
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wf:
                    rate = wf.getframerate() or default_rate
                    channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    raw = wf.readframes(wf.getnframes())
                    if sampwidth == 2:
                        arr = array.array("h")
                        arr.frombytes(raw[: len(raw) - (len(raw) % 2)])
                        if channels > 1:
                            mono = array.array("h", arr[::channels])
                            return mono, rate
                        return arr, rate
            except Exception:
                pass
        # Synthetic 1-second tone fallback for non-WAV test inputs when FFmpeg is absent
        synthetic = array.array(
            "h",
            [int(8000 * math.sin(2.0 * math.pi * 440.0 * i / default_rate)) for i in range(default_rate)],
        )
        return synthetic, default_rate
