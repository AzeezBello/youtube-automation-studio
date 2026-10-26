# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for YouTube Automation Studio desktop bundles (macOS & Windows)."""

import sys
from pathlib import Path

ROOT_DIR = Path(SPECPATH).resolve().parent
SRC_DIR = ROOT_DIR / "src"

datas = []
if (ROOT_DIR / "alembic.ini").exists():
    datas.append((str(ROOT_DIR / "alembic.ini"), "."))
if (ROOT_DIR / "migrations").exists():
    datas.append((str(ROOT_DIR / "migrations"), "migrations"))

hiddenimports = [
    "youtube_studio",
    "youtube_studio.config",
    "youtube_studio.domain",
    "youtube_studio.domain.models",
    "youtube_studio.domain.policies",
    "youtube_studio.domain.services",
    "youtube_studio.media",
    "youtube_studio.research",
    "youtube_studio.ai",
    "youtube_studio.security",
    "youtube_studio.storage",
    "youtube_studio.ui",
    "sqlite3",
]

a = Analysis(
    [str(SRC_DIR / "youtube_studio" / "main.py")],
    pathex=[str(SRC_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YouTubeAutomationStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="YouTubeAutomationStudio",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="YouTube Automation Studio.app",
        icon=None,
        bundle_identifier="com.youtubeautomationstudio.desktop",
        info_plist={
            "CFBundleName": "YouTube Automation Studio",
            "CFBundleDisplayName": "YouTube Automation Studio",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
        },
    )
