"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform_channel_id", sa.String(64), nullable=True),
        sa.Column("brand_config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("default_output_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("project_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_projects_channel", "projects", ["channel_id"])

    op.create_table(
        "media_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_media_files_hash", "media_files", ["file_hash"])

    op.create_table(
        "project_tracks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("media_file_id", sa.String(36), sa.ForeignKey("media_files.id"), nullable=False),
        sa.Column("track_order", sa.Integer(), nullable=False),
        sa.Column("trim_start_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trim_end_ms", sa.Integer(), nullable=True),
        sa.Column("gain_db", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fade_in_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fade_out_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transition_config_json", sa.Text(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("approved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "metadata_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("chapters_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("job_type", sa.String(32), nullable=False),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("input_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("output_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_json", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_jobs_status_created", "jobs", ["status", "created_at"])

    op.create_table(
        "research_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brief", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "research_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "research_project_id",
            sa.String(36),
            sa.ForeignKey("research_projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("external_reference", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_class", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("idx_research_sources_expiry", "research_sources", ["expires_at"])

    op.create_table(
        "saved_ideas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=True),
        sa.Column(
            "research_project_id",
            sa.String(36),
            sa.ForeignKey("research_projects.id"),
            nullable=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="idea"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "publishing_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(36), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("destination_video_id", sa.String(64), nullable=True),
        sa.Column("requested_publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("privacy_status", sa.String(16), nullable=False, server_default="private"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("user_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_publishing_tasks_status", "publishing_tasks", ["status"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value_json", sa.Text(), nullable=False, server_default="null"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("license", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("compatibility_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("model_registry")
    op.drop_table("settings")
    op.drop_index("idx_publishing_tasks_status", table_name="publishing_tasks")
    op.drop_table("publishing_tasks")
    op.drop_table("saved_ideas")
    op.drop_index("idx_research_sources_expiry", table_name="research_sources")
    op.drop_table("research_sources")
    op.drop_table("research_projects")
    op.drop_index("idx_jobs_status_created", table_name="jobs")
    op.drop_table("jobs")
    op.drop_table("metadata_drafts")
    op.drop_table("assets")
    op.drop_table("project_tracks")
    op.drop_index("idx_media_files_hash", table_name="media_files")
    op.drop_table("media_files")
    op.drop_index("idx_projects_channel", table_name="projects")
    op.drop_table("projects")
    op.drop_table("channels")
