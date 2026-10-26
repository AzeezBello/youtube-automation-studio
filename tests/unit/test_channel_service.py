"""Unit tests for ChannelService."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.services.channel_service import ChannelService
from youtube_studio.storage.database import Base
from youtube_studio.storage import orm  # noqa: F401


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


def test_create_and_list_channels(session):
    svc = ChannelService(session)
    c1 = svc.create("Echoes of Livity")
    c2 = svc.create(
        "Promo Clips",
        brand=ChannelBrandConfig(preferred_language="en", default_aspect_ratio="9:16"),
    )
    session.commit()

    active = svc.list_active()
    assert len(active) == 2
    names = {c.name for c in active}
    assert "Echoes of Livity" in names
    assert "Promo Clips" in names

    fetched = svc.get(c1.id)
    assert fetched is not None
    assert fetched.name == "Echoes of Livity"
    assert fetched.brand_config.default_aspect_ratio == "16:9"


def test_archive_channel(session):
    svc = ChannelService(session)
    ch = svc.create("Temporary")
    session.commit()
    svc.archive(ch.id)
    session.commit()
    assert svc.list_active() == []
    archived = svc.get(ch.id)
    assert archived is not None
    assert archived.is_archived
