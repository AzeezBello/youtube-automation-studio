"""Unit tests for harmonic audio intelligence, visualizers, motion FX & 9:16 Shorts clipper features."""

from __future__ import annotations

import array
import math
import tempfile
import wave
from pathlib import Path

from youtube_studio.domain.models.project import (
    ChapterEntry,
    TransitionConfig,
    TransitionType,
)
from youtube_studio.media.dj_intelligence import DJIntelligenceService
from youtube_studio.media.mixer import AudioMixerService, MixTrackInput
from youtube_studio.media.renderer import (
    RenderSpec,
    VideoRendererService,
    VisualFXConfig,
    VisualizerStyle,
)
from youtube_studio.media.shorts_clipper import ShortsClipperService
from youtube_studio.media.thumbnail import ThumbnailEngine, ThumbnailSpec
from youtube_studio.media.validator import MediaValidator


def _write_padded_wav(
    path: Path,
    *,
    silence_lead_sec: float = 0.5,
    tone_sec: float = 3.0,
    silence_tail_sec: float = 0.5,
    freq_hz: float = 440.0,
) -> Path:
    rate = 8000
    lead = [0] * int(rate * silence_lead_sec)
    tone = [
        int(14000 * math.sin(2.0 * math.pi * freq_hz * i / rate))
        for i in range(int(rate * tone_sec))
    ]
    tail = [0] * int(rate * silence_tail_sec)
    samples = array.array("h", lead + tone + tail)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return path


def test_dj_intelligence_bpm_camelot_and_auto_cue():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        wav_path = _write_padded_wav(
            root / "padded.wav",
            silence_lead_sec=0.5,
            tone_sec=3.0,
            silence_tail_sec=0.5,
        )
        dj = DJIntelligenceService()
        analysis = dj.analyze_track(wav_path, duration_ms=4000, highlight_duration_ms=2000)

        assert 70.0 <= analysis.bpm <= 160.0
        assert analysis.camelot_code[-1] in ("A", "B")
        assert len(analysis.musical_key) >= 3
        # Silence lead (500ms) and silence tail (at 3500ms) should be trimmed by auto-cue
        assert 350 <= analysis.cue_in_ms <= 650
        assert 3350 <= analysis.cue_out_ms <= 3650

        # Harmonic sorting test
        assert dj.camelot_distance("8A", "8A") == 0
        assert dj.camelot_distance("8A", "9A") == 1
        assert dj.camelot_distance("8A", "8B") == 1

        unsorted = [
            ("track_far", 140.0, "2B"),
            ("track_start", 120.0, "8A"),
            ("track_compat", 122.0, "8B"),
        ]
        ordered = dj.harmonic_sort_order(unsorted)
        assert ordered == ["track_start", "track_compat", "track_far"]


def test_bass_swap_eq_crossfade_filtergraph():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        w1 = _write_padded_wav(root / "1.wav", silence_lead_sec=0.0, tone_sec=3.0, silence_tail_sec=0.0)
        w2 = _write_padded_wav(root / "2.wav", silence_lead_sec=0.0, tone_sec=3.0, silence_tail_sec=0.0)

        inputs = [
            MixTrackInput(
                source_path=w1,
                source_duration_ms=3000,
                transition_config=TransitionConfig(
                    transition_type=TransitionType.BASS_SWAP_EQ,
                    overlap_ms=1000,
                ),
            ),
            MixTrackInput(
                source_path=w2,
                source_duration_ms=3000,
                transition_config=TransitionConfig(transition_type=TransitionType.NONE, overlap_ms=0),
            ),
        ]
        mixer = AudioMixerService()
        fg = mixer.build_filter_complex(inputs)
        assert "equalizer=f=90:t=h:w=100:g=-9" in fg
        assert "acrossfade=d=1.000" in fg


def test_pro_studio_visualizers_motion_fx_and_now_playing_overlay():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        audio_path = _write_padded_wav(root / "mix.wav", silence_lead_sec=0.0, tone_sec=4.0, silence_tail_sec=0.0)
        thumb_path = root / "bg.png"
        ThumbnailEngine().render(ThumbnailSpec(title="Echoes Session"), thumb_path)

        chapters = [
            ChapterEntry(start_ms=0, title="King Tubby - Dub Intro"),
            ChapterEntry(start_ms=2000, title="Scientist - Steppers Cut"),
        ]
        spec = RenderSpec(
            audio_path=audio_path,
            image_path=thumb_path,
            output_path=root / "styled_video.mp4",
            resolution="1280x720",
            visualizer_style=VisualizerStyle.BAR_SPECTRUM,
            visual_fx=VisualFXConfig(
                now_playing_overlay=True,
                progress_bar=True,
                slow_zoom=True,
                film_grain=True,
                vignette=True,
            ),
            chapters=chapters,
            duration_ms=4000,
        )

        renderer = VideoRendererService()
        fg, is_complex = renderer.build_video_filtergraph(spec)
        assert is_complex is True
        assert "showfreqs=" in fg
        assert "zoompan=" in fg
        assert "noise=alls=7" in fg
        assert "vignette=PI/5" in fg
        assert "drawtext=text='Now Playing" in fg
        assert "drawbox=" in fg

        res = renderer.render(spec)
        assert res.output_path.exists()
        assert res.srt_path is not None and res.srt_path.exists()
        srt_text = res.srt_path.read_text(encoding="utf-8")
        assert "Now Playing: King Tubby - Dub Intro" in srt_text
        assert "Now Playing: Scientist - Steppers Cut" in srt_text


def test_pro_studio_auto_shorts_clipper_9x16():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source_wav = _write_padded_wav(
            root / "full_track.wav",
            silence_lead_sec=1.0,
            tone_sec=4.0,
            silence_tail_sec=1.0,
        )
        clipper = ShortsClipperService()
        short_res = clipper.create_highlight_short(
            source_wav,
            root / "shorts_out",
            title="Roots Highlight Short",
            subtitle="Echoes of Livity",
            source_duration_ms=6000,
            clip_duration_ms=3000,
        )
        assert short_res.video_path.exists()
        assert short_res.thumbnail_path.exists()
        assert short_res.audio_path.exists()

        validator = MediaValidator()
        v_rep = validator.validate_video(
            short_res.video_path,
            expected_resolution="1080x1920",
        )
        assert v_rep.is_valid, v_rep.errors
        i_rep = validator.validate_image(
            short_res.thumbnail_path,
            expected_width=1080,
            expected_height=1920,
        )
        assert i_rep.is_valid, i_rep.errors
