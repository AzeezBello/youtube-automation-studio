"""Media library persistence and duplicate detection service."""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from youtube_studio.domain.models.media import MediaFile, MediaType
from youtube_studio.storage.orm import MediaFileORM


class MediaLibraryService:
    """Manages indexed local audio/video/image files and duplicate detection."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, media: MediaFile) -> MediaFile:
        stmt = select(MediaFileORM).where(MediaFileORM.path == media.path)
        existing = self._session.scalars(stmt).first()
        if existing is not None:
            existing.channel_id = media.channel_id or existing.channel_id
            existing.file_hash = media.file_hash
            existing.media_type = media.media_type.value
            existing.duration_ms = media.duration_ms
            existing.metadata_json = json.dumps(media.metadata)
            existing.last_scanned_at = media.last_scanned_at
            self._session.flush()
            return self._to_domain(existing)

        orm = MediaFileORM(
            id=media.id,
            channel_id=media.channel_id,
            path=media.path,
            file_hash=media.file_hash,
            media_type=media.media_type.value,
            duration_ms=media.duration_ms,
            metadata_json=json.dumps(media.metadata),
            last_scanned_at=media.last_scanned_at,
            created_at=media.created_at,
        )
        self._session.add(orm)
        self._session.flush()
        return media

    def get(self, media_id: str) -> Optional[MediaFile]:
        orm = self._session.get(MediaFileORM, media_id)
        return self._to_domain(orm) if orm else None

    def get_by_path(self, path: str) -> Optional[MediaFile]:
        stmt = select(MediaFileORM).where(MediaFileORM.path == path)
        orm = self._session.scalars(stmt).first()
        return self._to_domain(orm) if orm else None

    def find_by_hash(self, file_hash: str) -> list[MediaFile]:
        stmt = (
            select(MediaFileORM)
            .where(MediaFileORM.file_hash == file_hash)
            .order_by(MediaFileORM.path)
        )
        return [self._to_domain(o) for o in self._session.scalars(stmt)]

    def list_media(
        self,
        *,
        channel_id: Optional[str] = None,
        media_type: Optional[MediaType] = None,
        query: Optional[str] = None,
    ) -> list[MediaFile]:
        stmt = select(MediaFileORM).order_by(MediaFileORM.path)
        if channel_id is not None:
            stmt = stmt.where(MediaFileORM.channel_id == channel_id)
        if media_type is not None:
            stmt = stmt.where(MediaFileORM.media_type == media_type.value)

        items = [self._to_domain(o) for o in self._session.scalars(stmt)]
        if query:
            needle = query.strip().lower()
            filtered: list[MediaFile] = []
            for item in items:
                title = str(item.metadata.get("title", "")).lower()
                artist = str(item.metadata.get("artist", "")).lower()
                if needle in item.path.lower() or needle in title or needle in artist:
                    filtered.append(item)
            return filtered
        return items

    def find_duplicates(self, *, channel_id: Optional[str] = None) -> dict[str, list[MediaFile]]:
        """Return mapping of file_hash -> list of duplicate MediaFiles (where count > 1)."""
        all_files = self.list_media(channel_id=channel_id)
        by_hash: dict[str, list[MediaFile]] = {}
        for mf in all_files:
            if mf.file_hash:
                by_hash.setdefault(mf.file_hash, []).append(mf)
        return {h: group for h, group in by_hash.items() if len(group) > 1}

    def delete(self, media_id: str) -> bool:
        orm = self._session.get(MediaFileORM, media_id)
        if orm is None:
            return False
        self._session.delete(orm)
        self._session.flush()
        return True

    @staticmethod
    def _to_domain(orm: MediaFileORM) -> MediaFile:
        return MediaFile(
            id=orm.id,
            channel_id=orm.channel_id,
            path=orm.path,
            file_hash=orm.file_hash,
            media_type=MediaType(orm.media_type),
            duration_ms=orm.duration_ms,
            metadata=json.loads(orm.metadata_json or "{}"),
            last_scanned_at=orm.last_scanned_at,
            created_at=orm.created_at,
        )
