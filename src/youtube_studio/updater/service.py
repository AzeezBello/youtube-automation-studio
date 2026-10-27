"""Application Update & Release Manifest Service for YouTube Automation Studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import platform
import re
from pathlib import Path
from typing import Any, Optional
from urllib import request as urllib_request

from youtube_studio import __version__
from youtube_studio.config import get_settings

DEFAULT_UPDATE_FEED_URL = "https://releases.youtubeautomationstudio.local/releases.json"


@dataclass(frozen=True)
class PlatformInstallerAsset:
    """Metadata for a downloadable desktop installer package on a specific OS/architecture."""

    platform_key: str  # e.g. "macos_arm64", "macos_x64", "windows_x64", "linux_x64"
    os_name: str
    arch: str
    filename: str
    download_url: str
    sha256: str
    size_bytes: int
    install_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_key": self.platform_key,
            "os_name": self.os_name,
            "arch": self.arch,
            "filename": self.filename,
            "download_url": self.download_url,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "install_hint": self.install_hint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformInstallerAsset":
        return cls(
            platform_key=str(data.get("platform_key", "")),
            os_name=str(data.get("os_name", "")),
            arch=str(data.get("arch", "")),
            filename=str(data.get("filename", "")),
            download_url=str(data.get("download_url", "")),
            sha256=str(data.get("sha256", "")),
            size_bytes=int(data.get("size_bytes", 0)),
            install_hint=str(data.get("install_hint", "")),
        )


@dataclass(frozen=True)
class ReleaseManifest:
    """Canonical release manifest shared by the download website and the in-app updater."""

    version: str
    channel: str = "stable"
    published_at: str = ""
    min_supported_version: str = "0.1.0"
    headline: str = ""
    release_notes: list[str] = field(default_factory=list)
    platforms: dict[str, PlatformInstallerAsset] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "channel": self.channel,
            "published_at": self.published_at,
            "min_supported_version": self.min_supported_version,
            "headline": self.headline,
            "release_notes": list(self.release_notes),
            "platforms": {k: v.to_dict() for k, v in self.platforms.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReleaseManifest":
        raw_platforms = data.get("platforms") or {}
        platforms = {
            str(k): PlatformInstallerAsset.from_dict(v)
            for k, v in raw_platforms.items()
            if isinstance(v, dict)
        }
        return cls(
            version=str(data.get("version", __version__)),
            channel=str(data.get("channel", "stable")),
            published_at=str(data.get("published_at", "")),
            min_supported_version=str(data.get("min_supported_version", "0.1.0")),
            headline=str(data.get("headline", "")),
            release_notes=[str(x) for x in (data.get("release_notes") or [])],
            platforms=platforms,
        )


@dataclass(frozen=True)
class UpdateCheckResult:
    """Result of comparing the running studio version against the release manifest."""

    current_version: str
    latest_version: str
    update_available: bool
    channel: str
    published_at: str
    headline: str
    release_notes: list[str]
    recommended_asset: Optional[PlatformInstallerAsset]
    source: str  # "remote", "local_manifest", or "builtin_fallback"


def parse_semver(version_str: str) -> tuple[int, int, int, int]:
    """Parse a semantic version string like '0.2.1' or '0.2.1-beta.1' into a comparable tuple."""
    cleaned = version_str.strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$", cleaned)
    if not match:
        return (0, 0, 0, 0)
    major, minor, patch, pre = match.groups()
    # Stable release has higher precedence (999) than pre-release tags
    pre_Num = 999 if not pre else int(re.sub(r"\D", "", pre) or "1")
    return (int(major), int(minor), int(patch), pre_Num)


def is_newer_version(candidate_version: str, current_version: str) -> bool:
    """Return True if candidate_version is strictly newer than current_version."""
    return parse_semver(candidate_version) > parse_semver(current_version)


def detect_current_platform_key() -> str:
    """Detect the current host OS and CPU architecture key for installer matching."""
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if sys_name == "darwin":
        return "macos_arm64" if ("arm" in machine or "aarch64" in machine) else "macos_x64"
    if sys_name == "windows":
        return "windows_x64"
    return "linux_x64"


class UpdateService:
    """Manages release manifests, update checks, and SHA-256 installer verification."""

    def __init__(
        self,
        *,
        local_manifest_path: Optional[Path] = None,
        feed_url: Optional[str] = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._local_manifest_path = local_manifest_path or (repo_root / "website" / "releases.json")
        self._prefs_path = get_settings().resolved_data_dir() / "updater_prefs.json"
        self._feed_url = feed_url or self.get_preferences().get("feed_url", DEFAULT_UPDATE_FEED_URL)

    def get_preferences(self) -> dict[str, Any]:
        if self._prefs_path.exists():
            try:
                return json.loads(self._prefs_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "channel": "stable",
            "auto_check_on_startup": True,
            "feed_url": DEFAULT_UPDATE_FEED_URL,
        }

    def save_preferences(
        self,
        *,
        channel: str = "stable",
        auto_check_on_startup: bool = True,
        feed_url: Optional[str] = None,
    ) -> dict[str, Any]:
        prefs = {
            "channel": channel if channel in ("stable", "beta") else "stable",
            "auto_check_on_startup": bool(auto_check_on_startup),
            "feed_url": (feed_url or self._feed_url or DEFAULT_UPDATE_FEED_URL).strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
        self._prefs_path.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
        self._feed_url = prefs["feed_url"]
        return prefs

    @staticmethod
    def build_default_manifest(version: str = __version__) -> ReleaseManifest:
        """Build the default canonical release manifest for the current version."""
        return ReleaseManifest(
            version=version,
            channel="stable",
            published_at="2026-10-27T12:00:00Z",
            min_supported_version="0.1.0",
            headline="Mobile-Responsive Dark Studio, Bidirectional MCP Hub & Harmonic Mixing Engine",
            release_notes=[
                "Full Bidirectional MCP Hub: Built-in Studio MCP Server (10 tools, 4 resources, 2 prompts) + external stdio/HTTP MCP client manager.",
                "Mobile-Responsive Adaptive UI: Collapsible navigation drawer, responsive split containers, touch-friendly scroll views, and one-click Mobile/Desktop viewport toggle.",
                "Harmonic Mixing & Pro Video Engine: Camelot Wheel (1A–12B) key detection, BPM estimation, Auto-Cue Silence Trim, Bass-Swap EQ transitions, and 4 audio-reactive visualizers.",
                "9:16 Vertical Shorts Auto-Clipper & Dynamic 'Now Playing' Subtitle Overlays (.srt).",
                "Enhanced Music Library Scanner: macOS smart-quote path resolution, explicit OS permission diagnostics, and MP4/MOV/WEBM music track indexing.",
            ],
            platforms={
                "macos_arm64": PlatformInstallerAsset(
                    platform_key="macos_arm64",
                    os_name="macOS (Apple Silicon M1/M2/M3/M4)",
                    arch="arm64",
                    filename=f"YouTubeAutomationStudio-{version}-macos-arm64.dmg",
                    download_url=f"./downloads/YouTubeAutomationStudio-{version}-macos-arm64.dmg",
                    sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    size_bytes=68_400_000,
                    install_hint="Open the .dmg image and drag 'YouTube Automation Studio.app' to Applications.",
                ),
                "macos_x64": PlatformInstallerAsset(
                    platform_key="macos_x64",
                    os_name="macOS (Intel x86_64)",
                    arch="x86_64",
                    filename=f"YouTubeAutomationStudio-{version}-macos-x64.dmg",
                    download_url=f"./downloads/YouTubeAutomationStudio-{version}-macos-x64.dmg",
                    sha256="8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4",
                    size_bytes=71_200_000,
                    install_hint="Open the .dmg image and drag 'YouTube Automation Studio.app' to Applications.",
                ),
                "windows_x64": PlatformInstallerAsset(
                    platform_key="windows_x64",
                    os_name="Windows 10 / 11 (64-bit)",
                    arch="x86_64",
                    filename=f"YouTubeAutomationStudio-{version}-windows-x64-setup.exe",
                    download_url=f"./downloads/YouTubeAutomationStudio-{version}-windows-x64-setup.exe",
                    sha256="2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
                    size_bytes=64_800_000,
                    install_hint="Run the Setup .exe installer or extract the portable .zip archive.",
                ),
                "linux_x64": PlatformInstallerAsset(
                    platform_key="linux_x64",
                    os_name="Linux (Ubuntu / Fedora / Arch)",
                    arch="x86_64",
                    filename=f"YouTubeAutomationStudio-{version}-linux-x86_64.AppImage",
                    download_url=f"./downloads/YouTubeAutomationStudio-{version}-linux-x86_64.AppImage",
                    sha256="4938d873b6755092912b54f97033052206192a4e13269738a2011a39c581242b",
                    size_bytes=66_100_000,
                    install_hint="chmod +x YouTubeAutomationStudio-*.AppImage && ./YouTubeAutomationStudio-*.AppImage",
                ),
            },
        )

    def load_manifest(self, allow_remote: bool = False) -> tuple[ReleaseManifest, str]:
        """Load the release manifest from remote feed (if enabled), local website/releases.json, or fallback."""
        if allow_remote and self._feed_url.startswith(("http://", "https://")) and ".local" not in self._feed_url:
            try:
                req = urllib_request.Request(
                    self._feed_url,
                    headers={"Accept": "application/json", "User-Agent": f"YouTubeAutomationStudio/{__version__}"},
                )
                with urllib_request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return ReleaseManifest.from_dict(data), "remote"
            except Exception:
                pass

        if self._local_manifest_path.exists():
            try:
                data = json.loads(self._local_manifest_path.read_text(encoding="utf-8"))
                return ReleaseManifest.from_dict(data), "local_manifest"
            except Exception:
                pass

        return self.build_default_manifest(), "builtin_fallback"

    def check_for_updates(
        self,
        *,
        current_version: str = __version__,
        allow_remote: bool = False,
    ) -> UpdateCheckResult:
        """Compare current_version against the latest release manifest and return an UpdateCheckResult."""
        manifest, source = self.load_manifest(allow_remote=allow_remote)
        plat_key = detect_current_platform_key()
        asset = manifest.platforms.get(plat_key) or next(iter(manifest.platforms.values()), None)
        newer = is_newer_version(manifest.version, current_version)
        return UpdateCheckResult(
            current_version=current_version,
            latest_version=manifest.version,
            update_available=newer,
            channel=manifest.channel,
            published_at=manifest.published_at,
            headline=manifest.headline,
            release_notes=manifest.release_notes,
            recommended_asset=asset,
            source=source,
        )

    @staticmethod
    def verify_installer_checksum(file_path: Path, expected_sha256: str) -> bool:
        """Verify that a downloaded installer binary matches its expected SHA-256 digest."""
        h = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest().lower() == expected_sha256.strip().lower()
