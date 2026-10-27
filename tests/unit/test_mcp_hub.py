"""Unit tests for the Bidirectional MCP Hub (StudioMCPServer + MCPClientHub) and MediaScanner fixes."""

from __future__ import annotations

from contextlib import contextmanager
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Iterator
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from youtube_studio.domain.services import MediaLibraryService
from youtube_studio.mcp.client import MCPClientHub
from youtube_studio.mcp.server import StudioMCPServer
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.storage.orm import Base
from youtube_studio.updater import UpdateService, is_newer_version


def _write_test_wav(path: Path, freq_hz: float = 440.0, duration_sec: float = 1.2) -> None:
    sr = 22050
    num_samples = int(sr * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(num_samples):
            val = int(14000 * math.sin(2.0 * math.pi * freq_hz * (i / sr)))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))


class MCPHubAndScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.db_path = self.root / "test_studio.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

        @contextmanager
        def _fake_session_scope() -> Iterator[Session]:
            session = self.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self._session_scope = _fake_session_scope

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tmp_dir.cleanup()

    def test_studio_mcp_server_jsonrpc_and_tools(self) -> None:
        with patch("youtube_studio.mcp.server.session_scope", side_effect=self._session_scope):
            server = StudioMCPServer()

            # 1. Initialize handshake
            init_resp = server.handle_jsonrpc_request(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            )
            self.assertIsNotNone(init_resp)
            assert init_resp is not None
            self.assertEqual(init_resp["result"]["serverInfo"]["name"], "youtube-automation-studio-mcp")

            # 2. List tools, resources, prompts
            tools_resp = server.handle_jsonrpc_request(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            assert tools_resp is not None
            tools = tools_resp["result"]["tools"]
            self.assertEqual(len(tools), 10)

            res_resp = server.handle_jsonrpc_request(
                {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}
            )
            assert res_resp is not None
            self.assertEqual(len(res_resp["result"]["resources"]), 4)

            prompts_resp = server.handle_jsonrpc_request(
                {"jsonrpc": "2.0", "id": 4, "method": "prompts/list", "params": {}}
            )
            assert prompts_resp is not None
            self.assertEqual(len(prompts_resp["result"]["prompts"]), 2)

            # 3. Call create_channel & list_channels
            ch_res = server.call_tool(
                "create_channel",
                {"name": "Goldtooth Beats", "palette": "dub_obsidian", "default_tags": ["lofi", "beats"]},
            )
            self.assertFalse(ch_res.is_error)
            self.assertEqual(ch_res.structured_data["name"], "Goldtooth Beats")

            list_ch = server.call_tool("list_channels", {})
            self.assertEqual(list_ch.structured_data["count"], 1)

            # 4. Scan music library with curly-quote path & build harmonic mix project
            music_dir = self.root / "Jahron “Goldtooth” Perry"
            music_dir.mkdir(parents=True, exist_ok=True)
            _write_test_wav(music_dir / "track_a.wav", freq_hz=440.0)
            _write_test_wav(music_dir / "track_b.wav", freq_hz=523.25)

            # Pass straight quotes to verify resolve_directory matches curly-quote folder on disk
            straight_quote_query = str(self.root / 'Jahron "Goldtooth" Perry')
            scan_res = server.call_tool(
                "scan_music_library",
                {"folder_path": straight_quote_query},
            )
            self.assertFalse(scan_res.is_error)
            self.assertEqual(scan_res.structured_data["scanned_count"], 2)

            mix_res = server.call_tool(
                "build_harmonic_mix_project",
                {
                    "project_name": "Goldtooth Session Vol 1",
                    "transition_type": "bass_swap_eq",
                    "overlap_ms": 3000,
                },
            )
            self.assertFalse(mix_res.is_error)
            self.assertEqual(mix_res.structured_data["track_count"], 2)

            # 5. Read resources and prompts
            channels_res = server.read_resource("studio://channels")
            self.assertEqual(channels_res.structured_data["count"], 1)
            audio_res = server.read_resource("studio://library/audio")
            self.assertEqual(audio_res.structured_data["count"], 2)

            prompt_res = server.get_prompt(
                "curate_harmonic_mix_session",
                {"genre_focus": "late night jazzhop"},
            )
            self.assertFalse(prompt_res.is_error)
            self.assertIn("late night jazzhop", prompt_res.text)

    def test_mcp_client_hub_manages_builtin_and_external_servers(self) -> None:
        from youtube_studio.security.vault import CredentialVault

        with (
            patch("youtube_studio.mcp.server.session_scope", side_effect=self._session_scope),
            patch("youtube_studio.mcp.channel_sync.session_scope", side_effect=self._session_scope),
            patch.object(
                 __import__("youtube_studio.mcp.channel_sync", fromlist=["ChannelSyncService"]).ChannelSyncService,
                "_profile_cache_path",
                return_value=self.root / "synced_channel_profile.json",
            ),
        ):
            hub = MCPClientHub(
                registry_path=self.root / "mcp_servers.json",
                builtin_server=StudioMCPServer(),
                vault=CredentialVault(use_fallback=True),
            )
            servers = hub.list_servers()
            self.assertEqual(len(servers), 1)
            self.assertEqual(servers[0].id, "studio-builtin")

            # Add external server config
            ext = hub.register_server(
                "Local Filesystem MCP",
                transport="stdio",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                description="External stdio server",
                server_id="filesystem-local",
            )
            self.assertEqual(ext.id, "filesystem-local")
            self.assertEqual(len(hub.list_servers()), 2)

            # Call tool on builtin server through hub
            res = hub.call_tool("studio-builtin", "search_and_cluster_topics", {"query": "lofi chill beats"})
            self.assertFalse(res.is_error)
            self.assertGreater(res.structured_data["total_results"], 0)

            # Remove external server
            self.assertTrue(hub.remove_server("filesystem-local"))
            self.assertEqual(len(hub.list_servers()), 1)

            # Seed preconfigured connectors (vidIQ, TubeBuddy, Suno, ElevenLabs, etc.) and test Browser OAuth Redirect flow
            seeded = hub.seed_preconfigured_servers()
            self.assertGreaterEqual(len(seeded), 10)
            vidiq_cfg = hub.get_server("vidiq-seo")
            self.assertIsNotNone(vidiq_cfg)
            assert vidiq_cfg is not None
            self.assertEqual(vidiq_cfg.url, "https://mcp.vidiq.com/sse")

            # Test Browser OAuth Redirect login (no API key required!)
            completed_sessions = []
            authorize_url = hub.start_browser_oauth_login(
                "vidiq-seo",
                connection_url="https://mcp.vidiq.com/sse",
                on_connected=lambda s: completed_sessions.append(s),
                open_browser=False,
            )
            self.assertTrue(authorize_url.startswith("http://127.0.0.1:"))
            self.assertIn("/mcp/authorize?state=", authorize_url)

            # Simulate user clicking "Authorize & Connect to Studio" in the browser redirect page
            hub._oauth_flow.complete_pending_login(
                account_label="goldtooth@studio.local",
                code="oauth_pkce_code_789",
            )

            self.assertTrue(hub.is_account_connected("vidiq-seo"))
            self.assertEqual(len(completed_sessions), 1)
            self.assertEqual(completed_sessions[0].account_label, "goldtooth@studio.local")
            oauth_sess = hub.get_oauth_session("vidiq-seo")
            self.assertIsNotNone(oauth_sess)
            assert oauth_sess is not None
            self.assertEqual(oauth_sess.connection_url, "https://mcp.vidiq.com/sse")

            vidiq_res = hub.call_tool(
                "vidiq-seo",
                "vidiq_keyword_inspector",
                {"keyword": "roots reggae dub mix"},
            )
            self.assertFalse(vidiq_res.is_error)
            self.assertIn("Account Connected", vidiq_res.structured_data["account_status"])

            # Verify vidIQ Channel Audit tool returns synced channel data & research ideas
            audit_res = hub.call_tool(
                "vidiq-seo",
                "vidiq_channel_audit",
                {"channel_handle": "@GoldtoothPerry"},
            )
            self.assertFalse(audit_res.is_error)
            ch_data = audit_res.structured_data["connected_channel"]
            self.assertEqual(ch_data["handle"], "@GoldtoothPerry")
            self.assertGreaterEqual(len(ch_data["recent_videos"]), 1)
            self.assertGreaterEqual(len(ch_data["recommended_ideas"]), 3)

            hub.disconnect_account("vidiq-seo")
            self.assertFalse(hub.is_account_connected("vidiq-seo"))

    def test_update_service_and_release_manifest(self) -> None:
        self.assertTrue(is_newer_version("0.2.0", "0.1.0"))
        self.assertFalse(is_newer_version("0.1.0", "0.1.0"))
        self.assertTrue(is_newer_version("0.2.0", "0.2.0-beta.1"))

        updater = UpdateService()
        chk = updater.check_for_updates(current_version="0.1.0", allow_remote=False)
        self.assertEqual(chk.latest_version, "0.1.0")
        self.assertFalse(chk.update_available)
        self.assertIsNotNone(chk.recommended_asset)

        chk_older = updater.check_for_updates(current_version="0.0.9", allow_remote=False)
        self.assertTrue(chk_older.update_available)

    def test_scanner_curly_quote_resolution_and_excludes_video_formats(self) -> None:
        folder = self.root / "Jahron “Goldtooth” Perry"
        folder.mkdir(parents=True, exist_ok=True)
        wav_file = folder / "beat1.wav"
        mp4_file = folder / "video_track.mp4"
        mov_file = folder / "clip.mov"
        _write_test_wav(wav_file, freq_hz=440.0)
        _write_test_wav(mp4_file, freq_hz=330.0)
        _write_test_wav(mov_file, freq_hz=220.0)

        # Resolve using ASCII straight quotes
        resolved = MediaScanner.resolve_directory(str(self.root / 'Jahron "Goldtooth" Perry'))
        self.assertEqual(resolved, folder.resolve())

        with self._session_scope() as session:
            media_svc = MediaLibraryService(session)
            scanner = MediaScanner()
            # Video formats (.mp4, .mov) must NOT be loaded as music files
            summary = scanner.scan_directory(
                resolved,
                media_service=media_svc,
                audio_only=True,
            )
            self.assertEqual(len(summary.scanned_files), 1)
            self.assertEqual(Path(summary.scanned_files[0].path).name, "beat1.wav")
            self.assertIn(".mp4", summary.skipped_extensions)
            self.assertIn(".mov", summary.skipped_extensions)

    def test_light_and_dark_theme_manager(self) -> None:
        from youtube_studio.config import Settings
        from youtube_studio.ui.theme import (
            DARK_STUDIO_STYLESHEET,
            LIGHT_STUDIO_STYLESHEET,
            ThemeManager,
        )

        ThemeManager.set_preference("light")
        self.assertEqual(ThemeManager.resolve_effective_theme(), "light")
        self.assertEqual(ThemeManager.get_stylesheet(), LIGHT_STUDIO_STYLESHEET)

        ThemeManager.set_preference("dark")
        self.assertEqual(ThemeManager.resolve_effective_theme(), "dark")
        self.assertEqual(ThemeManager.get_stylesheet(), DARK_STUDIO_STYLESHEET)

        # Verify custom output location persistence
        custom_out = self.root / "my_custom_exports"
        cfg = Settings(data_dir=self.root)
        saved_out = cfg.set_output_dir(custom_out)
        self.assertEqual(saved_out, custom_out.resolve())
        self.assertEqual(cfg.resolved_output_dir(), custom_out.resolve())
        self.assertTrue(custom_out.exists())


if __name__ == "__main__":
    unittest.main()
