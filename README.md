# YouTube Automation Studio

Local-first, multi-channel desktop application for YouTube research, content planning, music-video production, and publishing.

**Version:** 0.1.0 (Foundation / P0)  
**Status:** Starter repository – working software, not a mockup  
**Primary stack:** Python 3.11+, PySide6, SQLite, FFmpeg, SQLAlchemy, Alembic

## Product Vision

A self-contained desktop platform that combines:

- YouTube research & competitor monitoring (public metadata)
- Keyword / topic discovery with transparent provenance
- Multi-channel brand profiles and production templates
- Local music library → DJ mixes / single-track videos
- Artwork & thumbnail generation (local models preferred)
- Metadata & export packaging (user retains full manual control of posting)

**Principles:** Local-first · No mandatory vidIQ or paid AI subscription · Full manual user control over posting · Policy-compliant YouTube data handling · Working software from day one.

## Current Milestone (P3 – Local AI)

- [x] Project skeleton & dependency configuration
- [x] SQLite schema + Alembic migrations
- [x] Multi-channel profile support
- [x] Persistent job queue interfaces + stage recovery
- [x] FFmpeg detection & hardware benchmark service
- [x] Secure credential vault (`keyring` + fallback)
- [x] Research provider contracts + Quota-aware YouTube Data API v3 adapter (P2)
- [x] Basic PySide6 desktop shell + Music Library, Production, Research & Artwork/AI workspaces (P1–P3)
- [x] Full music library scanner + duplicate & waveform/fingerprint detection (P1)
- [x] Audio mixing + thumbnail layout + video rendering + output validation pipeline (P1)
- [x] Research workspace UI, topic clustering, competitor watchlist, 30-day retention purge, and Saved Ideas → Production hand-off (P2)
- [x] Local AI model registry, hardware compatibility check, LM/template metadata generation, and optional diffusion/procedural artwork generation (P3)
- [x] VirtualDJ smart mixing (BPM/Camelot key detection, harmonic sort, auto-silence cue trim, bass-swap EQ crossfades) & CapCut video styling ("Now Playing" chapter overlays, multi-style visualizers, Ken Burns/vintage FX, and 9:16 Auto-Shorts clipper) (P4)
- [x] Unit / integration test suite
- [ ] Packaging, hardening, backup/restore & docs (P5)

## Quick Start

### Prerequisites

- Python 3.11 or newer
- FFmpeg and FFprobe available on `PATH` (or configure path in Settings)
- Git

### Setup

```bash
cd youtube-automation-studio
python3 -m venv --upgrade-deps .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --no-build-isolation -e ".[dev]"
```

### Database

```bash
# Create / upgrade schema
alembic upgrade head
```

### Run

```bash
youtube-studio
# or
python -m youtube_studio.main
```

### Tests

```bash
pytest -q
```

## Project Layout

```
youtube-automation-studio/
├── src/youtube_studio/
│   ├── main.py                 # Entry point
│   ├── app.py                  # Application factory
│   ├── config/                 # Settings & paths
│   ├── ui/                     # PySide6 views (dashboard, research, …)
│   ├── domain/                 # Models, services, policies
│   ├── research/               # Providers, keywords, competitors
│   ├── ai/                     # Local text / image / embedding adapters
│   ├── media/                  # Library, audio, mixing, video, validation
│   ├── jobs/                   # Persistent job queue
│   ├── storage/                # SQLite + file manifests
│   ├── security/               # Credential vault
│   └── logging/
├── migrations/                 # Alembic
├── tests/
├── scripts/
└── packaging/
```

## Configuration

Application data lives under the user data directory (platform-specific).  
Key settings (model paths, FFmpeg binary, output roots, resource profile) are editable in **Settings**.

## YouTube API Compliance

Public Data API results are subject to retention rules (typically ≤ 30 days).  
Derived metrics from API data are restricted.  
See `docs/COMPLIANCE.md` (to be expanded) and the policy layer in `domain/policies`.

## Development Phases

| Phase | Focus                                      | Exit criteria                                      |
|-------|--------------------------------------------|----------------------------------------------------|
| P0    | Foundation, shell, DB, jobs, FFmpeg        | App launches, multi-channel, jobs persist          |
| P1    | Music library → video pipeline             | Validated MP3 → video package                      |
| P2    | Research workspace + retention             | Save / reopen research projects                    |
| P3    | Local AI (text + optional image)           | Metadata + artwork without paid API                |
| P4    | VirtualDJ & CapCut pro studio features     | Harmonic mixing, visualizers, FX & 9:16 Shorts     |
| P5    | Packaging, hardening, docs                 | Installable release + recovery procedures          |

## License

Proprietary – all rights reserved.  
Source media, generated assets, and user research remain the property of the user.
