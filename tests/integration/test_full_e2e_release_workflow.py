"""Full end-to-end integration test with real synthesized media across P0-P5."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
import tempfile
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

from youtube_studio.ai.image_adapter import ArtworkGenerator
from youtube_studio.ai.metadata_generator import MetadataGenerationRequest, MetadataGenerator
from youtube_studio.domain.models.project import (
    ChapterEntry,
    ProjectType,
    TransitionConfig,
    TransitionType,
)
from youtube_studio.domain.policies.compliance_gate import ComplianceReviewGate
from youtube_studio.media.dj_intelligence import DJIntelligenceService
from youtube_studio.media.mixer import AudioMixerService, MixTrackInput
from youtube_studio.media.renderer import (
    RenderSpec,
    VideoRendererService,
    VisualFXConfig,
    VisualizerStyle,
)
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.shorts_clipper import ShortsClipperService
from youtube_studio.media.validator import MediaValidator
from youtube_studio.media.waveform import WaveformGenerator
from youtube_studio.storage.backup import BackupService


def _synthesize_wav(
    path: Path,
    duration_sec: float = 2.5,
    freq_hz: float = 110.0,
    pulse_bpm: float = 140.0,
    leading_silence_sec: float = 0.2,
    sample_rate: int = 22050,
) -> Path:
    """Create a real 16-bit stereo WAV file with a rhythmic pulse and bass tone."""
    total_frames = int(duration_sec * sample_rate)
    silence_frames = int(leading_silence_sec * sample_rate)
    beat_period = 60.0 / pulse_bpm
    frames = bytearray()

    for i in range(total_frames):
        if i < silence_frames:
            sample = 0
        else:
            t = (i - silence_frames) / sample_rate
            beat_phase = (t % beat_period) / beat_period
            envelope = 0.85 if beat_phase < 0.35 else 0.25
            val = math.sin(2.0 * math.pi * freq_hz * t) * envelope
            sample = max(-32767, min(32767, int(val * 26000)))
        frames.extend(struct.pack("<hh", sample, sample))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))
    return path


class TestFullE2EReleaseWorkflow(unittest.TestCase):
    """Verifies the complete P0-P5 creator workflow using real audio/image/video artifacts."""

    def test_end_to_end_creator_release_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            music_dir = workspace / "music"
            output_dir = workspace / "output"
            music_dir.mkdir()
            output_dir.mkdir()

            # 1. Synthesize two real WAV tracks
            track_a = _synthesize_wav(
                music_dir / "01_sub_invocation.wav",
                duration_sec=2.5,
                freq_hz=110.0,  # A2
                pulse_bpm=140.0,
                leading_silence_sec=0.2,
            )
            track_b = _synthesize_wav(
                music_dir / "02_obsidian_echo.wav",
                duration_sec=2.5,
                freq_hz=164.81,  # E3 (harmonic 5th)
                pulse_bpm=140.0,
                leading_silence_sec=0.15,
            )

            # 2. Scan media library & extract waveform peaks
            scanner = MediaScanner()
            scanned = scanner.scan_directory(music_dir)
            self.assertEqual(len(scanned.scanned_files), 2)

            waveform_gen = WaveformGenerator()
            wf_a = waveform_gen.analyze(track_a, bins=32)
            self.assertEqual(len(wf_a.peaks), 32)
            self.assertGreater(max(wf_a.peaks), 0.1)

            # 3. Run VirtualDJ Intelligence (BPM, Camelot key, cue points, harmonic sort)
            dj = DJIntelligenceService(waveform_generator=waveform_gen)
            analysis_a = dj.analyze_track(track_a, duration_ms=2500, highlight_duration_ms=1200)
            analysis_b = dj.analyze_track(track_b, duration_ms=2500, highlight_duration_ms=1200)
            self.assertTrue(analysis_a.camelot_code.endswith(("A", "B")))
            self.assertGreaterEqual(analysis_a.cue_in_ms, 50)

            ordered_ids = dj.harmonic_sort_order(
                [
                    ("track_a", analysis_a.bpm, analysis_a.camelot_code),
                    ("track_b", analysis_b.bpm, analysis_b.camelot_code),
                ]
            )
            self.assertEqual(len(ordered_ids), 2)

            # 4. Mix tracks using Bass-Swap EQ transition & compute chapters
            mixer = AudioMixerService()
            mixed_wav = output_dir / "master_mix.wav"
            mix_inputs = [
                MixTrackInput(
                    source_path=track_a,
                    source_duration_ms=2500,
                    trim_start_ms=analysis_a.cue_in_ms,
                    trim_end_ms=analysis_a.cue_out_ms,
                    transition_config=TransitionConfig(
                        transition_type=TransitionType.BASS_SWAP_EQ,
                        overlap_ms=300,
                    ),
                ),
                MixTrackInput(
                    source_path=track_b,
                    source_duration_ms=2500,
                    trim_start_ms=analysis_b.cue_in_ms,
                    trim_end_ms=analysis_b.cue_out_ms,
                    transition_config=TransitionConfig(
                        transition_type=TransitionType.NONE,
                        overlap_ms=0,
                    ),
                ),
            ]
            mix_result = mixer.mix(mix_inputs, mixed_wav, normalize_loudness=True)
            self.assertTrue(mix_result.output_path.exists())
            self.assertGreater(mix_result.duration_ms, 1000)

            chapters = [
                ChapterEntry(start_ms=0, title="Sub Invocation"),
                ChapterEntry(
                    start_ms=max(500, mix_inputs[0].effective_duration_ms() - 300),
                    title="Obsidian Echo",
                ),
            ]

            # 5. Generate Local AI Metadata & 16:9 Procedural Artwork Thumbnail
            meta_gen = MetadataGenerator()
            metadata_pkg = meta_gen.generate(
                MetadataGenerationRequest(
                    project_name="Sub Invocation Session Vol. 1",
                    project_type=ProjectType.MIX,
                    channel_name="Deep 140 Collective",
                    chapters=chapters,
                    keywords=["deep dubstep", "140 bpm", "bass music"],
                )
            )
            self.assertGreaterEqual(len(metadata_pkg.title_candidates), 3)
            self.assertIn("00:00 Sub Invocation", metadata_pkg.description)

            artwork_gen = ArtworkGenerator()
            thumbnail_path = output_dir / "thumbnail.png"
            img_res = artwork_gen.generate(
                "SUB INVOCATION",
                thumbnail_path,
                width=1280,
                height=720,
                style_palette="dub_obsidian",
                subtitle="140 BPM HARMONIC SESSION",
            )
            self.assertTrue(img_res.output_path.exists())

            # 6. Render Master Video with CapCut Bar Spectrum, VisualFX & .srt Subtitles
            renderer = VideoRendererService()
            video_path = output_dir / "release_video.mp4"
            visual_fx = VisualFXConfig(
                now_playing_overlay=True,
                progress_bar=True,
                slow_zoom=True,
                film_grain=True,
                vignette=True,
                spinning_vinyl=True,
            )
            render_res = renderer.render(
                RenderSpec(
                    audio_path=mixed_wav,
                    image_path=thumbnail_path,
                    output_path=video_path,
                    resolution="1920x1080",
                    visualizer_style=VisualizerStyle.BAR_SPECTRUM,
                    visual_fx=visual_fx,
                    chapters=chapters,
                    duration_ms=mix_result.duration_ms,
                )
            )
            self.assertTrue(render_res.output_path.exists())
            self.assertIsNotNone(render_res.srt_path)
            self.assertTrue(render_res.srt_path.exists())

            # 7. Extract 9:16 Vertical Short Highlight Clip
            clipper = ShortsClipperService(
                dj_service=dj,
                mixer=mixer,
                renderer=renderer,
            )
            short_dir = output_dir / "shorts"
            short_res = clipper.create_highlight_short(
                source_audio_path=mixed_wav,
                output_dir=short_dir,
                title="SUB INVOCATION DROP",
                subtitle="Deep 140 Collective",
                source_duration_ms=mix_result.duration_ms,
                clip_duration_ms=1200,
                visualizer_style=VisualizerStyle.BAR_SPECTRUM,
            )
            self.assertTrue(short_res.video_path.exists())
            self.assertTrue(short_res.thumbnail_path.exists())

            # 8. Validate media artifacts & run Pre-Release Compliance Review Gate
            validator = MediaValidator()
            self.assertTrue(validator.validate_audio(mixed_wav).is_valid)
            self.assertTrue(validator.validate_image(thumbnail_path).is_valid)
            self.assertTrue(
                validator.validate_video(
                    render_res.output_path,
                    expected_resolution="1920x1080",
                ).is_valid
            )

            manifest_path = output_dir / "package_manifest.json"
            manifest_payload = {
                "project_name": "Sub Invocation Session Vol. 1",
                "resolution": "1920x1080",
                "metadata_draft": {
                    "title": metadata_pkg.title,
                    "description": metadata_pkg.description,
                    "tags": metadata_pkg.tags,
                    "chapters": [
                        {"start_ms": c.start_ms, "title": c.title} for c in chapters
                    ],
                },
                "artifacts": {
                    "rendered_video": str(render_res.output_path),
                    "thumbnail": str(thumbnail_path),
                    "short_video": str(short_res.video_path),
                    "now_playing_srt": str(render_res.srt_path),
                },
            }
            manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

            gate = ComplianceReviewGate(validator=validator)
            compliance_report = gate.review_package_manifest(
                manifest_path,
                active_source_expiries=[datetime.now(timezone.utc) + timedelta(days=29)],
            )
            self.assertTrue(
                compliance_report.passed,
                f"Expected compliance gate to pass, failed: {compliance_report.blocking_reasons}",
            )

            # 9. Snapshot & Restore Studio Database via BackupService
            db_path = workspace / "studio.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE releases (id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute(
                "INSERT INTO releases (title) VALUES (?)",
                (metadata_pkg.title,),
            )
            conn.commit()
            conn.close()

            backup_svc = BackupService(database_path=db_path, backup_dir=workspace / "backups")
            backup_zip, _ = backup_svc.create_backup(extra_files=[manifest_path])
            restored = backup_svc.restore_backup(backup_zip)
            self.assertEqual(len(restored.database_sha256), 64)


if __name__ == "__main__":
    unittest.main()
