"""SQLAlchemy ORM table definitions (mirrors domain models)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from youtube_studio.storage.database import Base


class ChannelORM(Base):
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    brand_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    default_output_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    projects: Mapped[list["ProjectORM"]] = relationship(back_populates="channel")


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("channels.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    manifest_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    channel: Mapped["ChannelORM"] = relationship(back_populates="projects")

    __table_args__ = (Index("idx_projects_channel", "channel_id"),)


class MediaFileORM(Base):
    __tablename__ = "media_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_media_files_hash", "file_hash"),)


class ProjectTrackORM(Base):
    __tablename__ = "project_tracks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    media_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("media_files.id"), nullable=False
    )
    track_order: Mapped[int] = mapped_column(Integer, nullable=False)
    trim_start_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trim_end_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gain_db: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fade_in_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fade_out_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transition_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class AssetORM(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MetadataDraftORM(Base):
    __tablename__ = "metadata_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    chapters_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobORM(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("idx_jobs_status_created", "status", "created_at"),)


class ResearchProjectORM(Base):
    __tablename__ = "research_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brief: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResearchSourceORM(Base):
    __tablename__ = "research_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retention_class: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    __table_args__ = (Index("idx_research_sources_expiry", "expires_at"),)


class SavedIdeaORM(Base):
    __tablename__ = "saved_ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("channels.id"), nullable=True
    )
    research_project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idea")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublishingTaskORM(Base):
    __tablename__ = "publishing_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(36), ForeignKey("channels.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    destination_video_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requested_publish_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    privacy_status: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    user_approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_publishing_tasks_status", "status"),)


class SettingORM(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="null")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelRegistryORM(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    compatibility_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
