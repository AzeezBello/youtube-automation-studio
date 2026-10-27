"""Production project, timeline track, chapter, asset, and metadata service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from youtube_studio.domain.models.project import (
    Asset,
    AssetType,
    ChapterEntry,
    MetadataDraft,
    Project,
    ProjectStatus,
    ProjectTrack,
    ProjectType,
    TransitionConfig,
    TransitionType,
)
from youtube_studio.storage.orm import (
    AssetORM,
    MediaFileORM,
    MetadataDraftORM,
    ProjectORM,
    ProjectTrackORM,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectService:
    """Manages production projects, track arrangements, assets, and metadata drafts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def create_project(
        self,
        channel_id: str,
        name: str,
        project_type: ProjectType = ProjectType.SINGLE_TRACK,
    ) -> Project:
        now = _utcnow()
        domain = Project(
            channel_id=channel_id,
            name=name,
            project_type=project_type,
            status=ProjectStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )
        orm = ProjectORM(
            id=domain.id,
            channel_id=domain.channel_id,
            name=domain.name,
            project_type=domain.project_type.value,
            status=domain.status.value,
            manifest_path=domain.manifest_path,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def get_project(self, project_id: str) -> Optional[Project]:
        orm = self._session.get(ProjectORM, project_id)
        return self._project_to_domain(orm) if orm else None

    def list_projects(self, channel_id: Optional[str] = None) -> list[Project]:
        stmt = select(ProjectORM).order_by(ProjectORM.created_at.desc())
        if channel_id is not None:
            stmt = stmt.where(ProjectORM.channel_id == channel_id)
        return [self._project_to_domain(o) for o in self._session.scalars(stmt)]

    def update_project_status(
        self,
        project_id: str,
        status: ProjectStatus,
        manifest_path: Optional[str] = None,
    ) -> Project:
        orm = self._session.get(ProjectORM, project_id)
        if orm is None:
            raise ValueError(f"Project {project_id} not found")
        orm.status = status.value
        if manifest_path is not None:
            orm.manifest_path = manifest_path
        orm.updated_at = _utcnow()
        self._session.flush()
        return self._project_to_domain(orm)

    # ------------------------------------------------------------------
    # Tracks & Timeline Editing
    # ------------------------------------------------------------------

    def add_track(
        self,
        project_id: str,
        media_file_id: str,
        *,
        trim_start_ms: int = 0,
        trim_end_ms: Optional[int] = None,
        gain_db: float = 0.0,
        fade_in_ms: int = 0,
        fade_out_ms: int = 0,
        transition_config: Optional[TransitionConfig] = None,
    ) -> ProjectTrack:
        existing = self.list_tracks(project_id)
        next_order = len(existing)
        domain = ProjectTrack(
            project_id=project_id,
            media_file_id=media_file_id,
            track_order=next_order,
            trim_start_ms=trim_start_ms,
            trim_end_ms=trim_end_ms,
            gain_db=gain_db,
            fade_in_ms=fade_in_ms,
            fade_out_ms=fade_out_ms,
            transition_config=transition_config or TransitionConfig(),
        )
        orm = ProjectTrackORM(
            id=domain.id,
            project_id=domain.project_id,
            media_file_id=domain.media_file_id,
            track_order=domain.track_order,
            trim_start_ms=domain.trim_start_ms,
            trim_end_ms=domain.trim_end_ms,
            gain_db=domain.gain_db,
            fade_in_ms=domain.fade_in_ms,
            fade_out_ms=domain.fade_out_ms,
            transition_config_json=domain.transition_config.model_dump_json(),
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def list_tracks(self, project_id: str) -> list[ProjectTrack]:
        stmt = (
            select(ProjectTrackORM)
            .where(ProjectTrackORM.project_id == project_id)
            .order_by(ProjectTrackORM.track_order)
        )
        return [self._track_to_domain(o) for o in self._session.scalars(stmt)]

    def update_track(self, track: ProjectTrack) -> ProjectTrack:
        orm = self._session.get(ProjectTrackORM, track.id)
        if orm is None:
            raise ValueError(f"ProjectTrack {track.id} not found")
        orm.track_order = track.track_order
        orm.trim_start_ms = track.trim_start_ms
        orm.trim_end_ms = track.trim_end_ms
        orm.gain_db = track.gain_db
        orm.fade_in_ms = track.fade_in_ms
        orm.fade_out_ms = track.fade_out_ms
        orm.transition_config_json = track.transition_config.model_dump_json()
        self._session.flush()
        return self._track_to_domain(orm)

    def reorder_tracks(self, project_id: str, ordered_track_ids: list[str]) -> list[ProjectTrack]:
        tracks = self.list_tracks(project_id)
        by_id = {t.id: t for t in tracks}
        if set(ordered_track_ids) != set(by_id.keys()):
            raise ValueError("ordered_track_ids must match the project's existing track IDs")
        updated: list[ProjectTrack] = []
        for idx, tid in enumerate(ordered_track_ids):
            t = by_id[tid]
            t.track_order = idx
            updated.append(self.update_track(t))
        return updated

    def remove_track(self, track_id: str) -> None:
        orm = self._session.get(ProjectTrackORM, track_id)
        if orm is None:
            return
        project_id = orm.project_id
        self._session.delete(orm)
        self._session.flush()
        # Re-normalize track_order
        remaining = self.list_tracks(project_id)
        for idx, track in enumerate(remaining):
            if track.track_order != idx:
                track.track_order = idx
                self.update_track(track)

    def compute_chapters(self, project_id: str) -> list[ChapterEntry]:
        """Compute YouTube chapter timestamps accounting for track trims and crossfades."""
        tracks = self.list_tracks(project_id)
        chapters: list[ChapterEntry] = []
        cursor_ms = 0
        for idx, pt in enumerate(tracks):
            media_orm = self._session.get(MediaFileORM, pt.media_file_id)
            source_dur = media_orm.duration_ms if media_orm else None
            meta = json.loads(media_orm.metadata_json or "{}") if media_orm else {}
            title = (
                meta.get("title")
                or (Path(media_orm.path).stem if media_orm else None)
                or f"Track {idx + 1}"
            )
            artist = meta.get("artist")
            label = f"{artist} - {title}" if artist else str(title)

            chapters.append(ChapterEntry(start_ms=max(0, cursor_ms), title=label))

            eff_dur = pt.effective_duration_ms(source_dur)
            overlap = 0
            if idx < len(tracks) - 1 and pt.transition_config.transition_type in (
                TransitionType.CROSSFADE,
                TransitionType.BASS_SWAP_EQ,
            ):
                overlap = min(max(0, pt.transition_config.overlap_ms), eff_dur // 2)
            cursor_ms += max(0, eff_dur - overlap)
        return chapters

    def compute_total_duration_ms(self, project_id: str) -> int:
        tracks = self.list_tracks(project_id)
        total_ms = 0
        for idx, pt in enumerate(tracks):
            media_orm = self._session.get(MediaFileORM, pt.media_file_id)
            source_dur = media_orm.duration_ms if media_orm else None
            eff_dur = pt.effective_duration_ms(source_dur)
            overlap = 0
            if idx < len(tracks) - 1 and pt.transition_config.transition_type in (
                TransitionType.CROSSFADE,
                TransitionType.BASS_SWAP_EQ,
            ):
                overlap = min(max(0, pt.transition_config.overlap_ms), eff_dur // 2)
            total_ms += max(0, eff_dur - overlap)
        return total_ms

    def auto_cue_trim_tracks(self, project_id: str) -> list[ProjectTrack]:
        """Automatically set trim_start_ms and trim_end_ms using detected cue_in_ms/cue_out_ms."""
        tracks = self.list_tracks(project_id)
        updated: list[ProjectTrack] = []
        for pt in tracks:
            media_orm = self._session.get(MediaFileORM, pt.media_file_id)
            meta = json.loads(media_orm.metadata_json or "{}") if media_orm else {}
            cue_in = meta.get("cue_in_ms")
            cue_out = meta.get("cue_out_ms")
            if isinstance(cue_in, int) and cue_in >= 0:
                pt.trim_start_ms = cue_in
            if isinstance(cue_out, int) and cue_out > pt.trim_start_ms:
                pt.trim_end_ms = cue_out
            updated.append(self.update_track(pt))
        return updated

    def auto_harmonic_sort(self, project_id: str) -> list[ProjectTrack]:
        """Reorder project tracks using Camelot wheel harmonic key + BPM progression."""
        from youtube_studio.media.dj_intelligence import DJIntelligenceService

        tracks = self.list_tracks(project_id)
        if len(tracks) <= 1:
            return tracks
        items: list[tuple[str, float, str]] = []
        for pt in tracks:
            media_orm = self._session.get(MediaFileORM, pt.media_file_id)
            meta = json.loads(media_orm.metadata_json or "{}") if media_orm else {}
            bpm = float(meta.get("bpm") or 120.0)
            camelot = str(meta.get("camelot_code") or "8A")
            items.append((pt.id, bpm, camelot))
        ordered_ids = DJIntelligenceService.harmonic_sort_order(items)
        return self.reorder_tracks(project_id, ordered_ids)

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------

    def register_asset(
        self,
        project_id: str,
        asset_type: AssetType,
        file_path: str,
        *,
        source_type: str = "generated",
        provenance: Optional[dict[str, Any]] = None,
        checksum: Optional[str] = None,
        approved: bool = False,
    ) -> Asset:
        domain = Asset(
            project_id=project_id,
            asset_type=asset_type,
            file_path=file_path,
            source_type=source_type,
            provenance=provenance or {},
            checksum=checksum,
            approved=approved,
        )
        orm = AssetORM(
            id=domain.id,
            project_id=domain.project_id,
            asset_type=domain.asset_type.value,
            file_path=domain.file_path,
            source_type=domain.source_type,
            provenance_json=json.dumps(domain.provenance),
            checksum=domain.checksum,
            approved=1 if domain.approved else 0,
            created_at=domain.created_at,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def approve_asset(self, asset_id: str, approved: bool = True) -> Asset:
        orm = self._session.get(AssetORM, asset_id)
        if orm is None:
            raise ValueError(f"Asset {asset_id} not found")
        orm.approved = 1 if approved else 0
        self._session.flush()
        return self._asset_to_domain(orm)

    def list_assets(
        self,
        project_id: str,
        asset_type: Optional[AssetType] = None,
    ) -> list[Asset]:
        stmt = (
            select(AssetORM)
            .where(AssetORM.project_id == project_id)
            .order_by(AssetORM.created_at.desc())
        )
        if asset_type is not None:
            stmt = stmt.where(AssetORM.asset_type == asset_type.value)
        return [self._asset_to_domain(o) for o in self._session.scalars(stmt)]

    # ------------------------------------------------------------------
    # Metadata Drafts
    # ------------------------------------------------------------------

    def save_metadata_draft(
        self,
        project_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        chapters: Optional[list[ChapterEntry]] = None,
        approval_status: str = "draft",
    ) -> MetadataDraft:
        latest = self.get_latest_metadata_draft(project_id)
        next_version = (latest.version + 1) if latest else 1
        resolved_chapters = chapters if chapters is not None else self.compute_chapters(project_id)

        domain = MetadataDraft(
            project_id=project_id,
            version=next_version,
            title=title,
            description=description,
            tags=tags or [],
            chapters=resolved_chapters,
            approval_status=approval_status,
        )
        orm = MetadataDraftORM(
            id=domain.id,
            project_id=domain.project_id,
            version=domain.version,
            title=domain.title,
            description=domain.description,
            tags_json=json.dumps(domain.tags),
            chapters_json=json.dumps([c.model_dump() for c in domain.chapters]),
            approval_status=domain.approval_status,
            created_at=domain.created_at,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def get_latest_metadata_draft(self, project_id: str) -> Optional[MetadataDraft]:
        stmt = (
            select(MetadataDraftORM)
            .where(MetadataDraftORM.project_id == project_id)
            .order_by(MetadataDraftORM.version.desc())
        )
        orm = self._session.scalars(stmt).first()
        return self._draft_to_domain(orm) if orm else None

    # ------------------------------------------------------------------
    # Mappers
    # ------------------------------------------------------------------

    @staticmethod
    def _project_to_domain(orm: ProjectORM) -> Project:
        return Project(
            id=orm.id,
            channel_id=orm.channel_id,
            name=orm.name,
            project_type=ProjectType(orm.project_type),
            status=ProjectStatus(orm.status),
            manifest_path=orm.manifest_path,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
        )

    @staticmethod
    def _track_to_domain(orm: ProjectTrackORM) -> ProjectTrack:
        tc_data = json.loads(orm.transition_config_json or "{}")
        return ProjectTrack(
            id=orm.id,
            project_id=orm.project_id,
            media_file_id=orm.media_file_id,
            track_order=orm.track_order,
            trim_start_ms=orm.trim_start_ms,
            trim_end_ms=orm.trim_end_ms,
            gain_db=orm.gain_db,
            fade_in_ms=orm.fade_in_ms,
            fade_out_ms=orm.fade_out_ms,
            transition_config=TransitionConfig.model_validate(tc_data),
        )

    @staticmethod
    def _asset_to_domain(orm: AssetORM) -> Asset:
        return Asset(
            id=orm.id,
            project_id=orm.project_id,
            asset_type=AssetType(orm.asset_type),
            file_path=orm.file_path,
            source_type=orm.source_type,
            provenance=json.loads(orm.provenance_json or "{}"),
            checksum=orm.checksum,
            approved=bool(orm.approved),
            created_at=orm.created_at,
        )

    @staticmethod
    def _draft_to_domain(orm: MetadataDraftORM) -> MetadataDraft:
        raw_chapters = json.loads(orm.chapters_json or "[]")
        return MetadataDraft(
            id=orm.id,
            project_id=orm.project_id,
            version=orm.version,
            title=orm.title,
            description=orm.description,
            tags=json.loads(orm.tags_json or "[]"),
            chapters=[ChapterEntry.model_validate(c) for c in raw_chapters],
            approval_status=orm.approval_status,
            created_at=orm.created_at,
        )
