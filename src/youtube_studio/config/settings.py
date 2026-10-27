"""Application configuration and paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
from typing import Optional


class ResourceProfile(str, Enum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    HIGH_PERFORMANCE = "high_performance"


def _resolve_output_dir_for_settings(
    resolved_data_dir: Path,
    default_output_root: Optional[Path],
) -> Path:
    prefs_path = resolved_data_dir / "studio_preferences.json"
    if prefs_path.exists():
        try:
            data = json.loads(prefs_path.read_text(encoding="utf-8"))
            custom_out = data.get("output_dir")
            if isinstance(custom_out, str) and custom_out.strip():
                out_path = Path(custom_out.strip()).expanduser().resolve()
                out_path.mkdir(parents=True, exist_ok=True)
                return out_path
        except Exception:
            pass
    if default_output_root is not None:
        out_path = default_output_root.expanduser().resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        return out_path
    fallback_out = (resolved_data_dir / "jobs").resolve()
    fallback_out.mkdir(parents=True, exist_ok=True)
    return fallback_out


def _persist_output_dir_for_settings(resolved_data_dir: Path, new_dir: Path | str) -> Path:
    raw_path = Path(str(new_dir).strip()).expanduser()
    if not raw_path.is_absolute() and raw_path.parts:
        first_part = raw_path.parts[0]
        if first_part.lower() in {"downloads", "desktop", "documents", "movies", "music"}:
            home_candidate = Path.home() / first_part.capitalize()
            if len(raw_path.parts) > 1:
                home_candidate = home_candidate.joinpath(*raw_path.parts[1:])
            raw_path = home_candidate
    target = raw_path.resolve()
    target.mkdir(parents=True, exist_ok=True)
    prefs_path = resolved_data_dir / "studio_preferences.json"
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, object] = {}
    if prefs_path.exists():
        try:
            existing = json.loads(prefs_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing["output_dir"] = str(target)
    prefs_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return target


try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):  # type: ignore[no-redef]
        model_config = SettingsConfigDict(
            env_prefix="YAS_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # Application identity
        app_name: str = "YouTube Automation Studio"
        app_version: str = "0.1.0"

        # Paths (overridable)
        data_dir: Optional[Path] = None
        database_name: str = "youtube_studio.db"
        ffmpeg_path: Optional[Path] = None
        ffprobe_path: Optional[Path] = None
        models_dir: Optional[Path] = None
        default_output_root: Optional[Path] = None

        # Runtime
        resource_profile: ResourceProfile = ResourceProfile.BALANCED
        max_concurrent_jobs: int = 2
        log_level: str = "INFO"

        # Feature flags
        enable_cloud_ai: bool = False
        enable_local_image_gen: bool = False

        def resolved_data_dir(self) -> Path:
            if self.data_dir is not None:
                return self.data_dir.expanduser().resolve()
            return (Path.home() / ".youtube_automation_studio").resolve()

        def resolved_output_dir(self) -> Path:
            return _resolve_output_dir_for_settings(
                self.resolved_data_dir(),
                self.default_output_root,
            )

        def set_output_dir(self, new_dir: Path | str) -> Path:
            return _persist_output_dir_for_settings(self.resolved_data_dir(), new_dir)

        def database_path(self) -> Path:
            return self.resolved_data_dir() / self.database_name

        def ensure_directories(self) -> None:
            base = self.resolved_data_dir()
            (base / "logs").mkdir(parents=True, exist_ok=True)
            (base / "assets").mkdir(parents=True, exist_ok=True)
            (base / "jobs").mkdir(parents=True, exist_ok=True)
            (base / "backups").mkdir(parents=True, exist_ok=True)
            self.resolved_output_dir()
            if self.models_dir:
                self.models_dir.mkdir(parents=True, exist_ok=True)
            if self.default_output_root:
                self.default_output_root.mkdir(parents=True, exist_ok=True)

except ImportError:

    @dataclass
    class Settings:  # type: ignore[no-redef]
        app_name: str = "YouTube Automation Studio"
        app_version: str = "0.1.0"
        data_dir: Optional[Path] = None
        database_name: str = "youtube_studio.db"
        ffmpeg_path: Optional[Path] = None
        ffprobe_path: Optional[Path] = None
        models_dir: Optional[Path] = None
        default_output_root: Optional[Path] = None
        resource_profile: ResourceProfile = ResourceProfile.BALANCED
        max_concurrent_jobs: int = 2
        log_level: str = "INFO"
        enable_cloud_ai: bool = False
        enable_local_image_gen: bool = False

        def __post_init__(self) -> None:
            env_data_dir = os.environ.get("YAS_DATA_DIR")
            if env_data_dir and self.data_dir is None:
                self.data_dir = Path(env_data_dir)

        def resolved_data_dir(self) -> Path:
            if self.data_dir is not None:
                return self.data_dir.expanduser().resolve()
            return (Path.home() / ".youtube_automation_studio").resolve()

        def resolved_output_dir(self) -> Path:
            return _resolve_output_dir_for_settings(
                self.resolved_data_dir(),
                self.default_output_root,
            )

        def set_output_dir(self, new_dir: Path | str) -> Path:
            return _persist_output_dir_for_settings(self.resolved_data_dir(), new_dir)

        def database_path(self) -> Path:
            return self.resolved_data_dir() / self.database_name

        def ensure_directories(self) -> None:
            base = self.resolved_data_dir()
            (base / "logs").mkdir(parents=True, exist_ok=True)
            (base / "assets").mkdir(parents=True, exist_ok=True)
            (base / "jobs").mkdir(parents=True, exist_ok=True)
            (base / "backups").mkdir(parents=True, exist_ok=True)
            self.resolved_output_dir()
            if self.models_dir:
                self.models_dir.mkdir(parents=True, exist_ok=True)
            if self.default_output_root:
                self.default_output_root.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
