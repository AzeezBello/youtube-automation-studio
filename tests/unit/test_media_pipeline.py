"""Unit tests for P1 media pipeline (scanner, waveform, mixer, thumbnail, renderer, validator)."""

from __future__ import annotations

import array
import math
import tempfile
import wave
from pathlib import Path

from youtube_studio.domain.models.project import TransitionConfig, TransitionType
from youtube_studio.media.mixer import AudioMixerService, MixTrackInput
from youtube_studio.media.renderer import RenderSpec, VideoRendererService
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.thumbnail import ThumbnailEngine, ThumbnailSpec
from youtube_studio.media.validator import MediaValidator
from youtube_studio.media.waveform import WaveformGenerator


def _write_test_wav(path: Path, *, duration_sec: float = 2.0, freq_hz: float = 440.0) -> Path:
    rate = 8000
    total_frames = int(rate * duration_sec)
    samples = array.array(
        "h",
        [int(12000 * math.sin(2.0 * math.pi * freq_hz * i / rate)) for i in range(total_frames)],
    )
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return path


def test_scanner_and_duplicate_detection():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        t1 = _write_test_wav(root / "track1.wav", duration_sec=2.0, freq_hz=440.0)
        t2 = _write_test_wav(root / "track1_copy.wav", duration_sec=2.0, freq_hz=440.0)
        t3 = _write_test_wav(root / "track2.wav", duration_sec=3.0, freq_hz=528.0)

        scanner = MediaScanner()
        summary = scanner.scan_directory(root)

        assert len(summary.scanned_files) == 3
        assert len(summary.duplicates_by_hash) == 1
        dup_group = next(iter(summary.duplicates_by_hash.values()))
        dup_paths = {Path(m.path) for m in dup_group}
        assert dup_paths == {t1.resolve(), t2.resolve()}

        track3_meta = next(m for m in summary.scanned_files if Path(m.path) == t3.resolve())
        assert track3_meta.duration_ms == 3000
        assert "fingerprint" in track3_meta.metadata
        assert "waveform_peaks" in track3_meta.metadata


def test_waveform_generator_and_png():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wav_path = _write_test_wav(root / "tone.wav", duration_sec=1.5)
        gen = WaveformGenerator()
        wf = gen.analyze(wav_path, bins=32)
        assert len(wf.peaks) == 32
        assert wf.rms > 0.0
        assert len(wf.fingerprint) == 32

        png_path = gen.render_waveform_png(wf, root / "wave.png", width=320, height=80)
        assert png_path.exists()
        validator = MediaValidator()
        rep = validator.validate_image(png_path, expected_width=320, expected_height=80)
        assert rep.is_valid, rep.errors


def test_audio_mixer_filtergraph_and_mix():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        w1 = _write_test_wav(root / "a.wav", duration_sec=4.0, freq_hz=440.0)
        w2 = _write_test_wav(root / "b.wav", duration_sec=4.0, freq_hz=660.0)

        inputs = [
            MixTrackInput(
                source_path=w1,
                source_duration_ms=4000,
                trim_start_ms=500,
                trim_end_ms=3500,
                gain_db=-1.5,
                fade_in_ms=250,
                fade_out_ms=250,
                transition_config=TransitionConfig(
                    transition_type=TransitionType.CROSSFADE,
                    overlap_ms=1000,
                ),
            ),
            MixTrackInput(
                source_path=w2,
                source_duration_ms=4000,
                trim_start_ms=0,
                trim_end_ms=3000,
                gain_db=1.0,
                fade_in_ms=0,
                fade_out_ms=500,
                transition_config=TransitionConfig(transition_type=TransitionType.NONE, overlap_ms=0),
            ),
        ]

        mixer = AudioMixerService()
        fg = mixer.build_filter_complex(inputs)
        assert "atrim=start=0.500:end=3.500" in fg
        assert "acrossfade=d=1.000" in fg
        assert "loudnorm" in fg

        out_wav = root / "mixed.wav"
        res = mixer.mix(inputs, out_wav)
        assert res.output_path.exists()
        # Track 1 effective = 3000ms, Track 2 effective = 3000ms, overlap = 1000ms => ~5000ms
        assert abs(res.duration_ms - 5000) <= 200


def test_thumbnail_renderer_and_validator():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        engine = ThumbnailEngine()
        thumb_path = root / "thumb.png"
        thumb_res = engine.render(
            ThumbnailSpec(
                title="Echoes of Livity – Roots Mix Vol. 1",
                subtitle="Echoes of Livity",
                badge_text="MIX",
                palette="vintage_roots",
                aspect_ratio="16:9",
            ),
            thumb_path,
        )
        assert thumb_res.output_path.exists()
        assert thumb_res.width == 1280
        assert thumb_res.height == 720
        assert len(thumb_res.checksum) == 64

        wav_path = _write_test_wav(root / "audio.wav", duration_sec=2.0)
        video_path = root / "video.mp4"
        renderer = VideoRendererService()
        render_res = renderer.render(
            RenderSpec(
                audio_path=wav_path,
                image_path=thumb_path,
                output_path=video_path,
                resolution="1280x720",
                duration_ms=2000,
            )
        )
        assert render_res.output_path.exists()

        validator = MediaValidator()
        v_rep = validator.validate_video(
            video_path,
            expected_duration_ms=2000,
            expected_resolution="1280x720",
        )
        assert v_rep.is_valid, v_rep.errors
