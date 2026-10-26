"""Local AI model registry and hardware compatibility service."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from youtube_studio.config.hardware import HardwareProbe, HardwareReport
from youtube_studio.domain.models.ai import RegisteredModel
from youtube_studio.storage.orm import ModelRegistryORM

MODEL_EXTENSIONS = {".gguf", ".safetensors", ".onnx", ".bin", ".pt", ".pth"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModelRegistryService:
    """Manages local AI model registration, discovery, and hardware compatibility checks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def register_model(
        self,
        name: str,
        path: str | Path,
        *,
        version: str = "1.0",
        license_name: Optional[str] = None,
        size_bytes: Optional[int] = None,
        compatibility_notes: Optional[str] = None,
    ) -> RegisteredModel:
        resolved_path = Path(path).expanduser().resolve()
        if size_bytes is None and resolved_path.exists() and resolved_path.is_file():
            size_bytes = resolved_path.stat().st_size

        stmt = select(ModelRegistryORM).where(ModelRegistryORM.path == str(resolved_path))
        existing = self._session.scalars(stmt).first()
        if existing is not None:
            existing.name = name
            existing.version = version
            existing.license = license_name
            existing.size_bytes = size_bytes
            existing.compatibility_notes = compatibility_notes
            self._session.flush()
            return self._to_domain(existing)

        domain = RegisteredModel(
            name=name,
            version=version,
            path=str(resolved_path),
            license=license_name,
            size_bytes=size_bytes,
            compatibility_notes=compatibility_notes,
            created_at=_utcnow(),
        )
        orm = ModelRegistryORM(
            id=domain.id,
            name=domain.name,
            version=domain.version,
            path=domain.path,
            license=domain.license,
            size_bytes=domain.size_bytes,
            compatibility_notes=domain.compatibility_notes,
            created_at=domain.created_at,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def get(self, model_id: str) -> Optional[RegisteredModel]:
        orm = self._session.get(ModelRegistryORM, model_id)
        return self._to_domain(orm) if orm else None

    def get_by_name(self, name: str) -> Optional[RegisteredModel]:
        stmt = (
            select(ModelRegistryORM)
            .where(ModelRegistryORM.name == name)
            .order_by(ModelRegistryORM.created_at.desc())
        )
        orm = self._session.scalars(stmt).first()
        return self._to_domain(orm) if orm else None

    def list_models(self) -> list[RegisteredModel]:
        stmt = select(ModelRegistryORM).order_by(ModelRegistryORM.name)
        return [self._to_domain(o) for o in self._session.scalars(stmt)]

    def delete_model(self, model_id: str) -> bool:
        orm = self._session.get(ModelRegistryORM, model_id)
        if orm is None:
            return False
        self._session.delete(orm)
        self._session.flush()
        return True

    def scan_models_directory(self, models_dir: Path) -> list[RegisteredModel]:
        root = models_dir.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return []

        discovered: list[RegisteredModel] = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            if file_path.suffix.lower() not in MODEL_EXTENSIONS:
                continue
            model = self.register_model(
                name=file_path.stem,
                path=file_path,
                compatibility_notes=f"Auto-discovered ({file_path.suffix.lower()})",
            )
            discovered.append(model)
        return discovered

    @staticmethod
    def check_hardware_compatibility(
        model: RegisteredModel,
        *,
        hardware: Optional[HardwareReport] = None,
    ) -> tuple[bool, str]:
        hw = hardware or HardwareProbe().run()
        return model.check_hardware_compatibility(total_ram_gb=hw.total_ram_gb)

    @staticmethod
    def _to_domain(orm: ModelRegistryORM) -> RegisteredModel:
        return RegisteredModel(
            id=orm.id,
            name=orm.name,
            version=orm.version,
            path=orm.path,
            license=orm.license,
            size_bytes=orm.size_bytes,
            compatibility_notes=orm.compatibility_notes,
            created_at=orm.created_at,
        )
