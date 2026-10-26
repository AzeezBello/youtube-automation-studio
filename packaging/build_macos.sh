#!/usr/bin/env bash
# Build macOS .app bundle and .dmg installer for YouTube Automation Studio
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python3}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "==> Creating virtual environment in .venv..."
  python3 -m venv --upgrade-deps .venv
  PYTHON_BIN=".venv/bin/python3"
fi

echo "==> Ensuring youtube-automation-studio and pyinstaller are installed..."
"${PYTHON_BIN}" -m pip install -e ".[dev]" pyinstaller

echo "==> Cleaning previous build artifacts..."
rm -rf build/ dist/

echo "==> Running PyInstaller with packaging/youtube_studio.spec..."
"${PYTHON_BIN}" -m PyInstaller --noconfirm packaging/youtube_studio.spec

APP_BUNDLE="dist/YouTube Automation Studio.app"
DMG_PATH="dist/YouTube-Automation-Studio-macOS.dmg"

if [[ -d "${APP_BUNDLE}" ]]; then
  echo "==> Applying ad-hoc code signature to ${APP_BUNDLE}..."
  codesign --force --deep --sign - "${APP_BUNDLE}" || true

  if command -v hdiutil >/dev/null 2>&1; then
    echo "==> Packaging macOS disk image (${DMG_PATH})..."
    hdiutil create \
      -volname "YouTube Automation Studio" \
      -srcfolder "${APP_BUNDLE}" \
      -ov \
      -format UDZO \
      "${DMG_PATH}"
    echo "==> Created macOS installer: ${DMG_PATH}"
  fi
else
  echo "ERROR: Expected app bundle not found at ${APP_BUNDLE}" >&2
  exit 1
fi
