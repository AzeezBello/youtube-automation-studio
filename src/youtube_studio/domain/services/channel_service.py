"""Channel profile CRUD service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from youtube_studio.domain.models.channel import Channel, ChannelBrandConfig
from youtube_studio.storage.orm import ChannelORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChannelService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        name: str,
        brand: Optional[ChannelBrandConfig] = None,
        *,
        brand_config: Optional[ChannelBrandConfig] = None,
    ) -> Channel:
        resolved_brand = brand or brand_config or ChannelBrandConfig()
        now = _utcnow()
        domain = Channel(name=name, brand_config=resolved_brand, created_at=now, updated_at=now)
        orm = ChannelORM(
            id=domain.id,
            name=domain.name,
            platform_channel_id=domain.platform_channel_id,
            brand_config_json=domain.brand_config.model_dump_json(),
            default_output_path=domain.default_output_path,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
            archived_at=None,
        )
        self._session.add(orm)
        self._session.flush()
        return domain

    def get(self, channel_id: str) -> Optional[Channel]:
        orm = self._session.get(ChannelORM, channel_id)
        if orm is None:
            return None
        return self._to_domain(orm)

    def list_active(self) -> list[Channel]:
        stmt = (
            select(ChannelORM)
            .where(ChannelORM.archived_at.is_(None))
            .order_by(ChannelORM.name)
        )
        return [self._to_domain(o) for o in self._session.scalars(stmt)]

    def update(self, channel: Channel) -> Channel:
        orm = self._session.get(ChannelORM, channel.id)
        if orm is None:
            raise ValueError(f"Channel {channel.id} not found")
        channel.touch()
        orm.name = channel.name
        orm.platform_channel_id = channel.platform_channel_id
        orm.brand_config_json = channel.brand_config.model_dump_json()
        orm.default_output_path = channel.default_output_path
        orm.updated_at = channel.updated_at
        orm.archived_at = channel.archived_at
        self._session.flush()
        return channel

    def update_brand_config(
        self,
        channel_id: str,
        brand_config: ChannelBrandConfig,
    ) -> Channel:
        ch = self.get(channel_id)
        if ch is None:
            raise ValueError(f"Channel {channel_id} not found")
        ch.brand_config = brand_config
        return self.update(ch)

    def archive(self, channel_id: str) -> None:
        orm = self._session.get(ChannelORM, channel_id)
        if orm is None:
            raise ValueError(f"Channel {channel_id} not found")
        orm.archived_at = _utcnow()
        orm.updated_at = _utcnow()
        self._session.flush()

    @staticmethod
    def _to_domain(orm: ChannelORM) -> Channel:
        brand_data = json.loads(orm.brand_config_json or "{}")
        return Channel(
            id=orm.id,
            name=orm.name,
            platform_channel_id=orm.platform_channel_id,
            brand_config=ChannelBrandConfig.model_validate(brand_data),
            default_output_path=orm.default_output_path,
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            archived_at=orm.archived_at,
        )
