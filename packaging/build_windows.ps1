<#
.SYNOPSIS
    Builds the Windows desktop distribution and ZIP installer package for YouTube Automation Studio.
#>
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RootDir

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "==> Creating virtual environment in .venv..."
    python -m venv --upgrade-deps .venv
}

Write-Host "==> Installing dependencies and PyInstaller..."
& $VenvPython -m pip install -e ".[dev]" pyinstaller

Write-Host "==> Cleaning previous build artifacts..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")  { Remove-Item -Recurse -Force "dist" }

Write-Host "==> Running PyInstaller with packaging\youtube_studio.spec..."
& $VenvPython -m PyInstaller --noconfirm "packaging\youtube_studio.spec"

$DistAppDir = Join-Path $RootDir "dist\YouTubeAutomationStudio"
$ZipInstaller = Join-Path $RootDir "dist\YouTube-Automation-Studio-Windows-x64.zip"

if (Test-Path $DistAppDir) {
    Write-Host "==> Creating Windows portable installer archive: $ZipInstaller"
    Compress-Archive -Path "$DistAppDir\*" -DestinationPath $ZipInstaller -Force
    Write-Host "==> Build complete: $ZipInstaller"
} else {
    Write-Error "Expected build output directory not found: $DistAppDir"
    exit 1
}
