"""Application Updater & Release Manifest package."""

from youtube_studio.updater.service import (
    DEFAULT_UPDATE_FEED_URL,
    PlatformInstallerAsset,
    ReleaseManifest,
    UpdateCheckResult,
    UpdateService,
    detect_current_platform_key,
    is_newer_version,
    parse_semver,
)

__all__ = [
    "DEFAULT_UPDATE_FEED_URL",
    "PlatformInstallerAsset",
    "ReleaseManifest",
    "UpdateCheckResult",
    "UpdateService",
    "detect_current_platform_key",
    "is_newer_version",
    "parse_semver",
]
