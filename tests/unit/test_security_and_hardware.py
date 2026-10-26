"""Unit tests for CredentialVault and HardwareProbe."""

from __future__ import annotations

from youtube_studio.config.hardware import HardwareProbe
from youtube_studio.config.settings import ResourceProfile
from youtube_studio.security.vault import CredentialVault


def test_credential_vault_fallback_lifecycle():
    vault = CredentialVault(use_fallback=True)
    key = vault.channel_token_key("ch-123")
    assert vault.get_secret(key) is None

    vault.set_secret(key, "secret-token-xyz")
    assert vault.get_secret(key) == "secret-token-xyz"

    assert vault.delete_secret(key) is True
    assert vault.get_secret(key) is None
    assert vault.delete_secret(key) is False


def test_hardware_probe_runs_and_recommends_profile():
    probe = HardwareProbe()
    report = probe.run()
    assert report.cpu_count >= 1
    assert report.total_ram_gb > 0
    assert report.cpu_hash_mb_per_sec > 0
    assert isinstance(report.recommended_profile, ResourceProfile)
