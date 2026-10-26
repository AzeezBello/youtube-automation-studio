#!/usr/bin/env python3
"""Seed the database with an initial Echoes of Livity channel profile."""

from __future__ import annotations

from youtube_studio.config import get_settings
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.services import ChannelService
from youtube_studio.storage import get_engine, session_scope
from youtube_studio.storage.orm import Base


def main() -> None:
    settings = get_settings()
    settings.ensure_directories()
    engine = get_engine()
    Base.metadata.create_all(engine)

    brand = ChannelBrandConfig(
        preferred_language="en",
        default_aspect_ratio="16:9",
        default_resolution="1920x1080",
        visual_style="vintage_roots",
        default_tags=[
            "roots reggae",
            "dub",
            "sound system",
            "reggae mix",
            "vintage reggae",
        ],
        thumbnail_style={
            "palette": "warm_earth",
            "typography": "classic_serif",
            "motif": "vinyl_and_sound_system",
        },
    )

    with session_scope() as session:
        svc = ChannelService(session)
        existing = [c for c in svc.list_active() if c.name == "Echoes of Livity"]
        if existing:
            print(f"Channel already exists: {existing[0].id}")
            return
        channel = svc.create("Echoes of Livity", brand=brand)
        print(f"Created channel '{channel.name}' ({channel.id})")


if __name__ == "__main__":
    main()
