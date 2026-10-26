"""Local hardware detection and resource profile recommendation."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from youtube_studio.config.settings import ResourceProfile


@dataclass(frozen=True)
class HardwareReport:
    os_name: str
    os_version: str
    architecture: str
    cpu_count: int
    total_ram_gb: float
    free_disk_gb: float
    has_ffmpeg_hwaccel: bool
    cpu_hash_mb_per_sec: float
    recommended_profile: ResourceProfile


class HardwareProbe:
    """Probes local system capabilities and runs a lightweight CPU/disk benchmark."""

    def __init__(self, target_dir: Optional[Path] = None) -> None:
        self._target_dir = target_dir or Path.home()

    def run(self) -> HardwareReport:
        cpu_count = os.cpu_count() or 1
        ram_gb = self._detect_ram_gb()
        free_disk_gb = self._detect_free_disk_gb(self._target_dir)
        has_hwaccel = self._detect_ffmpeg_hwaccel()
        hash_speed = self._benchmark_cpu_sha256()
        profile = self._recommend_profile(cpu_count, ram_gb, has_hwaccel, hash_speed)
        return HardwareReport(
            os_name=platform.system(),
            os_version=platform.release(),
            architecture=platform.machine(),
            cpu_count=cpu_count,
            total_ram_gb=round(ram_gb, 2),
            free_disk_gb=round(free_disk_gb, 2),
            has_ffmpeg_hwaccel=has_hwaccel,
            cpu_hash_mb_per_sec=round(hash_speed, 1),
            recommended_profile=profile,
        )

    @staticmethod
    def _detect_ram_gb() -> float:
        system = platform.system()
        try:
            if system == "Darwin":
                out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5)
                return int(out.strip()) / (1024**3)
            if system == "Linux" and Path("/proc/meminfo").exists():
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024**2)
            if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                if pages > 0 and page_size > 0:
                    return (pages * page_size) / (1024**3)
        except Exception:
            pass
        return 8.0

    @staticmethod
    def _detect_free_disk_gb(path: Path) -> float:
        try:
            usage = shutil.disk_usage(path if path.exists() else Path.home())
            return usage.free / (1024**3)
        except Exception:
            return 0.0

    @staticmethod
    def _detect_ffmpeg_hwaccel() -> bool:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return False
        try:
            res = subprocess.run(
                [ffmpeg, "-hwaccels"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            lines = [ln.strip() for ln in (res.stdout or "").splitlines()[1:] if ln.strip()]
            return len(lines) > 0
        except Exception:
            return False

    @staticmethod
    def _benchmark_cpu_sha256(megabytes: int = 16) -> float:
        block = b"youtube-automation-studio-benchmark-" * (1024 * 1024 // 36)
        start = time.perf_counter()
        hasher = hashlib.sha256()
        for _ in range(megabytes):
            hasher.update(block)
        _ = hasher.hexdigest()
        elapsed = max(time.perf_counter() - start, 1e-6)
        return megabytes / elapsed

    @staticmethod
    def _recommend_profile(
        cpu_count: int,
        ram_gb: float,
        has_hwaccel: bool,
        hash_speed: float,
    ) -> ResourceProfile:
        if cpu_count >= 8 and ram_gb >= 15.0 and (has_hwaccel or hash_speed >= 300.0):
            return ResourceProfile.HIGH_PERFORMANCE
        if cpu_count >= 4 and ram_gb >= 7.5:
            return ResourceProfile.BALANCED
        return ResourceProfile.ECONOMY
