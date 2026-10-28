"""Unit tests for P5 BackupService and ComplianceReviewGate."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from youtube_studio.domain.models.project import ChapterEntry
from youtube_studio.domain.policies.compliance_gate import ComplianceReviewGate
from youtube_studio.media.renderer import RenderSpec, VideoRendererService
from youtube_studio.media.thumbnail import ThumbnailEngine, ThumbnailSpec
from youtube_studio.storage.backup import BackupService


class TestBackupAndCompliance(unittest.TestCase):
    """Tests atomic SQLite backups, SHA-256 verification, and ComplianceReviewGate rules."""

    def test_backup_create_list_and_restore_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "studio.db"
            backups_dir = tmp_path / "backups"
            extra_manifest = tmp_path / "package_manifest.json"
            extra_manifest.write_text('{"project_name": "Dub Session"}', encoding="utf-8")

            # Create a real SQLite database with sample studio state
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE channels (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO channels (name) VALUES ('Deep Dub Collective')")
            conn.commit()
            conn.close()

            service = BackupService(database_path=db_path, backup_dir=backups_dir)
            archive_path, manifest = service.create_backup(extra_files=[extra_manifest])
            self.assertTrue(archive_path.exists())
            self.assertIn("manifests/package_manifest.json", manifest.included_files)

            backups = service.list_backups()
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0], archive_path)

            # Mutate the live DB, then restore from backup
            conn = sqlite3.connect(str(db_path))
            conn.execute("DELETE FROM channels")
            conn.commit()
            conn.close()

            restored_manifest = service.restore_backup(archive_path)
            self.assertEqual(len(restored_manifest.database_sha256), 64)

            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("SELECT name FROM channels").fetchall()
            conn.close()
            self.assertEqual(rows, [("Deep Dub Collective",)])

    def test_backup_restore_rejects_tampered_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "studio.db"
            backups_dir = tmp_path / "backups"

            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE t (x INT)")
            conn.execute("INSERT INTO t VALUES (42)")
            conn.commit()
            conn.close()

            service = BackupService(database_path=db_path, backup_dir=backups_dir)
            archive_path, _ = service.create_backup()

            # Tamper with studio.db inside the zip archive
            tampered_zip = tmp_path / "tampered.zip"
            with zipfile.ZipFile(archive_path, "r") as zin, zipfile.ZipFile(
                tampered_zip, "w"
            ) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == "studio.db":
                        data = data + b"corrupted-tail"
                    zout.writestr(item, data)

            with self.assertRaises(ValueError):
                service.restore_backup(tampered_zip)

    def test_compliance_gate_passes_valid_package_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            thumb_file = tmp_path / "thumb.png"
            video_file = tmp_path / "mix.mp4"
            audio_file = tmp_path / "audio.wav"
            audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")

            # Generate real PNG and fallback MP4 so MediaValidator passes
            ThumbnailEngine().render(
                ThumbnailSpec(title="Deep Dub Mix", width=1280, height=720),
                thumb_file,
            )
            VideoRendererService(ffmpeg_path=Path("/nonexistent/ffmpeg")).render(
                RenderSpec(
                    audio_path=audio_file,
                    image_path=thumb_file,
                    output_path=video_file,
                    resolution="1920x1080",
                    duration_ms=5000,
                )
            )

            future_expiry = datetime.now(timezone.utc) + timedelta(days=25)
            manifest_path = tmp_path / "package_manifest.json"
            manifest_data = {
                "project_name": "Deep Dubstep & Harmonic Bass Mix 2026",
                "resolution": "1920x1080",
                "metadata_draft": {
                    "title": "Deep Dubstep & Harmonic Bass Mix 2026 [140 BPM]",
                    "description": "00:00 Intro Dub\n03:15 Sub Pressure\nFull local studio mix.",
                    "tags": ["dubstep", "bass music", "140 bpm", "dj mix"],
                    "chapters": [
                        {"start_ms": 0, "title": "Intro Dub"},
                        {"start_ms": 195000, "title": "Sub Pressure"},
                    ],
                },
                "artifacts": {
                    "rendered_video": str(video_file),
                    "thumbnail": str(thumb_file),
                },
            }
            manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

            gate = ComplianceReviewGate()
            report = gate.review_package_manifest(
                manifest_path,
                active_source_expiries=[future_expiry],
            )
            self.assertTrue(report.passed, f"Unexpected blocking reasons: {report.blocking_reasons}")
            self.assertEqual(len(report.blocking_reasons), 0)

    def test_compliance_gate_catches_violations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "bad_manifest.json"
            expired_expiry = datetime.now(timezone.utc) - timedelta(days=5)

            bad_manifest = {
                "project_name": "Invalid Mix",
                "vidiq_score": 99.5,  # violates no_prohibited_derived_metrics
                "metadata_draft": {
                    "title": "",  # invalid empty title
                    "description": "Test",
                    "tags": ["ok"],
                    "chapters": [
                        {"start_ms": 30000, "title": "Starts late instead of 00:00"},
                    ],
                },
                "artifacts": {
                    "rendered_video": str(tmp_path / "missing.mp4"),
                },
            }
            manifest_path.write_text(json.dumps(bad_manifest), encoding="utf-8")

            gate = ComplianceReviewGate()
            report = gate.review_package_manifest(
                manifest_path,
                active_source_expiries=[expired_expiry],
            )
            self.assertFalse(report.passed)
            failed_names = {c.name for c in report.checks if not c.passed}
            self.assertIn("no_prohibited_derived_metrics", failed_names)
            self.assertIn("api_retention_30d_clean", failed_names)
            self.assertIn("youtube_title_bounds", failed_names)
            self.assertIn("youtube_chapters_format", failed_names)
            self.assertIn("rendered_video_valid", failed_names)
            self.assertIn("thumbnail_valid", failed_names)

            # Direct chapter order check
            ok, _ = gate.validate_youtube_chapters(
                [
                    ChapterEntry(start_ms=0, title="First"),
                    ChapterEntry(start_ms=10000, title="Second"),
                    ChapterEntry(start_ms=5000, title="Out of order"),
                ]
            )
            self.assertFalse(ok)

    def test_main_window_all_six_pages_instantiate(self) -> None:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from youtube_studio.ui import MainWindow

        _app = QApplication.instance() or QApplication([])
        win = MainWindow()
        self.assertEqual(win.nav.count(), 9)

        # Verify tooltips on header buttons and navigation items
        self.assertTrue(len(win.btn_onboarding.toolTip()) > 10)
        self.assertTrue(len(win.btn_tour.toolTip()) > 10)
        for idx in range(win.nav.count()):
            self.assertTrue(len(win.nav.item(idx).toolTip()) > 10)
            win.nav.setCurrentRow(idx)
            self.assertEqual(win.stack.currentIndex(), idx)

        # Verify EmptyStateWidget exists on pages
        for key in (
            "dashboard",
            "research",
            "music_library",
            "script_voice",
            "production",
            "timeline_editor",
            "artwork",
            "mcp_hub",
        ):
            page = win.pages[key]
            self.assertTrue(hasattr(page, "empty_state"), f"Missing empty_state on {key}")
        self.assertTrue(hasattr(win.pages["settings"], "backup_empty_state"))

        # Verify Product Tour steps through all 9 workspaces
        win.start_product_tour()
        self.assertEqual(win.tour_banner.current_step, 0)
        self.assertEqual(win.stack.currentIndex(), 0)
        for expected_step in range(1, 9):
            win.tour_banner.next_step()
            self.assertEqual(win.tour_banner.current_step, expected_step)
            self.assertEqual(win.stack.currentIndex(), expected_step)
        win.tour_banner.stop_tour()

        # Verify Light & Dark theme switching and OnboardingDialog 4-step wizard
        win.apply_theme("light")
        self.assertEqual(win.btn_theme.text(), "🌙 Dark")
        win.apply_theme("dark")
        self.assertEqual(win.btn_theme.text(), "☀️ Light")

        dlg = win.open_onboarding_dialog()
        self.assertEqual(dlg.stack.count(), 4)
        self.assertEqual(dlg.stack.currentIndex(), 0)
        dlg._on_next()
        self.assertEqual(dlg.stack.currentIndex(), 1)
        dlg._on_prev()
        self.assertEqual(dlg.stack.currentIndex(), 0)


if __name__ == "__main__":
    unittest.main()
