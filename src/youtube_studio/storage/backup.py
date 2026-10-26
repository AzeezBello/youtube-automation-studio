"""Atomic SQLite database and manifest backup / restore service."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from youtube_studio import __version__
from youtube_studio.config import get_settings


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass(frozen=True)
class BackupManifest:
    backup_id: str
    created_at: str
    app_version: str
    database_filename: str
    database_sha256: str
    included_files: list[str] = field(default_factory=list)


class BackupService:
    """Creates and restores atomic, checksum-verified ZIP backups of the studio database and manifests."""

    def __init__(
        self,
        *,
        database_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ) -> None:
        settings = get_settings()
        self._db_path = (
            database_path.expanduser().resolve()
            if database_path is not None
            else settings.database_path()
        )
        self._backup_dir = (
            backup_dir.expanduser().resolve()
            if backup_dir is not None
            else (settings.resolved_data_dir() / "backups")
        )

    def create_backup(
        self,
        *,
        output_zip_path: Optional[Path] = None,
        extra_files: Optional[list[Path]] = None,
    ) -> tuple[Path, BackupManifest]:
        if not self._db_path.exists():
            raise FileNotFoundError(f"Database file does not exist: {self._db_path}")

        self._backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _utcnow_iso()
        backup_id = str(uuid4())[:8]
        zip_path = (
            output_zip_path.expanduser().resolve()
            if output_zip_path is not None
            else (self._backup_dir / f"yas_backup_{timestamp}_{backup_id}.zip")
        )
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            snapshot_db = tmp_dir / self._db_path.name

            # Use SQLite online backup API for an atomic, lock-safe snapshot
            src_conn = sqlite3.connect(str(self._db_path))
            dst_conn = sqlite3.connect(str(snapshot_db))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()

            db_sha256 = self._sha256(snapshot_db)
            included: list[str] = [snapshot_db.name]

            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(snapshot_db, arcname=snapshot_db.name)

                for extra in extra_files or []:
                    if extra.exists() and extra.is_file():
                        arc = f"manifests/{extra.name}"
                        zf.write(extra, arcname=arc)
                        included.append(arc)

                manifest = BackupManifest(
                    backup_id=backup_id,
                    created_at=timestamp,
                    app_version=__version__,
                    database_filename=snapshot_db.name,
                    database_sha256=db_sha256,
                    included_files=included,
                )
                zf.writestr(
                    "backup_manifest.json",
                    json.dumps(asdict(manifest), indent=2),
                )

        return zip_path, manifest

    def restore_backup(
        self,
        archive_path: Path,
        *,
        target_db_path: Optional[Path] = None,
    ) -> BackupManifest:
        resolved_zip = archive_path.expanduser().resolve()
        if not resolved_zip.exists():
            raise FileNotFoundError(f"Backup archive not found: {resolved_zip}")

        dest_db = (
            target_db_path.expanduser().resolve()
            if target_db_path is not None
            else self._db_path
        )
        dest_db.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            with zipfile.ZipFile(resolved_zip, "r") as zf:
                if "backup_manifest.json" not in zf.namelist():
                    raise ValueError("Invalid backup archive: missing backup_manifest.json")
                raw_manifest = json.loads(zf.read("backup_manifest.json").decode("utf-8"))
                manifest = BackupManifest(**raw_manifest)

                if manifest.database_filename not in zf.namelist():
                    raise ValueError(
                        f"Backup archive missing database file '{manifest.database_filename}'"
                    )
                extracted_db = tmp_dir / manifest.database_filename
                zf.extract(manifest.database_filename, path=tmp_dir)

            actual_sha = self._sha256(extracted_db)
            if actual_sha != manifest.database_sha256:
                raise ValueError(
                    f"Backup checksum mismatch: expected {manifest.database_sha256}, got {actual_sha}"
                )

            # Atomically replace target SQLite database
            shutil.copy2(extracted_db, dest_db)

        return manifest

    def list_backups(self) -> list[Path]:
        if not self._backup_dir.exists():
            return []
        return sorted(self._backup_dir.glob("yas_backup_*.zip"), reverse=True)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
