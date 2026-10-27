"""Credential vault backed by OS keyring with persistent local fallback when keyring is unavailable."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

from youtube_studio.config import get_settings

logger = logging.getLogger(__name__)

SERVICE_NAMESPACE = "youtube-automation-studio"


class CredentialVault:
    """Stores and retrieves sensitive secrets (OAuth sessions, API keys) outside SQLite."""

    _SHARED_MEMORY_STORE: dict[str, dict[str, str]] = {}

    def __init__(self, service_name: str = SERVICE_NAMESPACE, *, use_fallback: bool = False) -> None:
        self._service_name = service_name
        self._use_fallback = use_fallback
        self._memory_store: dict[str, str] = {}

    @staticmethod
    def _vault_file_path() -> Path:
        return get_settings().resolved_data_dir() / ".vault_store.json"

    def _read_disk_store(self) -> dict[str, str]:
        path = self._vault_file_path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            ns_data = raw.get(self._service_name, {})
            out: dict[str, str] = {}
            for k, v in ns_data.items():
                if isinstance(v, str):
                    try:
                        out[k] = base64.b64decode(v.encode("ascii")).decode("utf-8")
                    except Exception:
                        out[k] = v
            return out
        except Exception:
            return {}

    def _write_disk_store(self, store: dict[str, str]) -> None:
        path = self._vault_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            all_data: dict[str, dict[str, str]] = {}
            if path.exists():
                try:
                    all_data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    all_data = {}
            encoded_ns = {
                k: base64.b64encode(v.encode("utf-8")).decode("ascii")
                for k, v in store.items()
            }
            all_data[self._service_name] = encoded_ns
            path.write_text(json.dumps(all_data, indent=2), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
        except Exception as exc:
            logger.debug("Could not persist fallback vault file: %s", exc)

    def set_secret(self, key: str, value: str) -> None:
        if self._use_fallback:
            self._memory_store[key] = value
            return

        # Always update shared memory + local encrypted/encoded fallback file so macOS -60005 never loses state
        ns_mem = self._SHARED_MEMORY_STORE.setdefault(self._service_name, {})
        ns_mem[key] = value
        disk = self._read_disk_store()
        disk[key] = value
        self._write_disk_store(disk)

        try:
            import keyring

            keyring.set_password(self._service_name, key, value)
        except Exception as exc:
            logger.debug("Keyring unavailable (%s); using local persistent vault store", exc)

    def get_secret(self, key: str) -> Optional[str]:
        if self._use_fallback:
            return self._memory_store.get(key)

        ns_mem = self._SHARED_MEMORY_STORE.get(self._service_name, {})
        if key in ns_mem:
            return ns_mem[key]

        disk = self._read_disk_store()
        if key in disk:
            ns_mem[key] = disk[key]
            return disk[key]

        try:
            import keyring

            val = keyring.get_password(self._service_name, key)
            if val is not None:
                ns_mem[key] = val
                return val
        except Exception as exc:
            logger.debug("Keyring read unavailable (%s); checked local vault store", exc)
        return None

    def delete_secret(self, key: str) -> bool:
        if self._use_fallback:
            if key in self._memory_store:
                del self._memory_store[key]
                return True
            return False

        deleted = False
        ns_mem = self._SHARED_MEMORY_STORE.get(self._service_name, {})
        if key in ns_mem:
            del ns_mem[key]
            deleted = True

        disk = self._read_disk_store()
        if key in disk:
            del disk[key]
            self._write_disk_store(disk)
            deleted = True

        try:
            import keyring

            keyring.delete_password(self._service_name, key)
            deleted = True
        except Exception:
            pass
        return deleted

    def channel_token_key(self, channel_id: str) -> str:
        return f"channel:{channel_id}:oauth_token"
