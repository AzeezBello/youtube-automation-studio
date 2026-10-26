"""Application configuration and paths."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ResourceProfile(str, Enum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    HIGH_PERFORMANCE = "high_performance"


class Settings(BaseSettings):
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
        # Platform-agnostic default under user home
        return (Path.home() / ".youtube_automation_studio").resolve()

    def database_path(self) -> Path:
        return self.resolved_data_dir() / self.database_name

    def ensure_directories(self) -> None:
        base = self.resolved_data_dir()
        (base / "logs").mkdir(parents=True, exist_ok=True)
        (base / "assets").mkdir(parents=True, exist_ok=True)
        (base / "jobs").mkdir(parents=True, exist_ok=True)
        (base / "backups").mkdir(parents=True, exist_ok=True)
        if self.models_dir:
            self.models_dir.mkdir(parents=True, exist_ok=True)
        if self.default_output_root:
            self.default_output_root.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    return Settings()
