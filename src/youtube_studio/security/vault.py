"""Credential vault backed by OS keyring with safe in-memory fallback for tests/headless runs."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_NAMESPACE = "youtube-automation-studio"


class CredentialVault:
    """Stores and retrieves sensitive secrets (OAuth tokens, API keys) outside SQLite."""

    def __init__(self, service_name: str = SERVICE_NAMESPACE, *, use_fallback: bool = False) -> None:
        self._service_name = service_name
        self._use_fallback = use_fallback
        self._memory_store: dict[str, str] = {}

    def set_secret(self, key: str, value: str) -> None:
        if not self._use_fallback:
            try:
                import keyring

                keyring.set_password(self._service_name, key, value)
                return
            except Exception as exc:
                logger.warning("Keyring unavailable (%s); falling back to in-memory store", exc)
        self._memory_store[key] = value

    def get_secret(self, key: str) -> Optional[str]:
        if not self._use_fallback:
            try:
                import keyring

                val = keyring.get_password(self._service_name, key)
                if val is not None:
                    return val
            except Exception as exc:
                logger.warning("Keyring read unavailable (%s); checking in-memory store", exc)
        return self._memory_store.get(key)

    def delete_secret(self, key: str) -> bool:
        deleted = False
        if not self._use_fallback:
            try:
                import keyring

                keyring.delete_password(self._service_name, key)
                deleted = True
            except Exception:
                pass
        if key in self._memory_store:
            del self._memory_store[key]
            deleted = True
        return deleted

    def channel_token_key(self, channel_id: str) -> str:
        return f"channel:{channel_id}:oauth_token"
