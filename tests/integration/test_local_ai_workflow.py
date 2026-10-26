"""End-to-end integration test for P3 model registry, AI metadata draft, and artwork approval."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from youtube_studio.ai import (
    ArtworkGenerator,
    MetadataGenerationRequest,
    MetadataGenerator,
)
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.project import AssetType, ProjectType
from youtube_studio.domain.services import (
    ChannelService,
    ModelRegistryService,
    ProjectService,
)
from youtube_studio.storage import orm  # noqa: F401
from youtube_studio.storage.database import Base


@pytest.fixture()
def session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    sess = factory()
    yield sess
    sess.close()
    engine.dispose()
    Path(path).unlink(missing_ok=True)


def test_model_registry_and_ai_asset_workflow(session):
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        models_dir = workspace / "models"
        models_dir.mkdir()
        (models_dir / "mistral-7b-instruct.gguf").write_bytes(b"gguf-weights" * 100)
        (models_dir / "sdxl-turbo.safetensors").write_bytes(b"safetensors" * 100)

        # 1. Scan and register local models
        reg_svc = ModelRegistryService(session)
        discovered = reg_svc.scan_models_directory(models_dir)
        session.commit()
        assert len(discovered) == 2
        names = {m.name for m in reg_svc.list_models()}
        assert "mistral-7b-instruct" in names
        assert "sdxl-turbo" in names

        # 2. Create channel and project
        ch_svc = ChannelService(session)
        channel = ch_svc.create(
            "Echoes of Livity",
            brand=ChannelBrandConfig(
                default_tags=["roots reggae", "dub"],
                thumbnail_style={"palette": "warm_earth"},
            ),
        )
        proj_svc = ProjectService(session)
        project = proj_svc.create_project(
            channel.id,
            "Midnight Dubplate Transmission",
            project_type=ProjectType.MIX,
        )

        # 3. Generate metadata via MetadataGenerator & save draft
        meta_gen = MetadataGenerator()
        meta_res = meta_gen.generate(
            MetadataGenerationRequest(
                project_name=project.name,
                project_type=project.project_type,
                channel_name=channel.name,
                brand_config=channel.brand_config,
                research_brief="Deep midnight dub session with vintage spring reverb.",
            )
        )
        draft = proj_svc.save_metadata_draft(
            project.id,
            title=meta_res.title,
            description=meta_res.description,
            tags=meta_res.tags,
            approval_status="approved",
        )
        assert draft.version == 1
        assert "roots reggae" in draft.tags

        # 4. Generate artwork via ArtworkGenerator, register asset, and approve
        art_gen = ArtworkGenerator()
        thumb_path = workspace / "thumbnail.png"
        art_res = art_gen.generate(
            project.name,
            thumb_path,
            style_palette="warm_earth",
            subtitle=channel.name,
            badge_text="MIX",
        )
        asset = proj_svc.register_asset(
            project.id,
            AssetType.THUMBNAIL,
            str(art_res.output_path),
            source_type=art_res.adapter_used,
            provenance=art_res.provenance,
            checksum=art_res.checksum,
            approved=False,
        )
        assert asset.approved is False

        approved_asset = proj_svc.approve_asset(asset.id, approved=True)
        session.commit()
        assert approved_asset.approved is True
