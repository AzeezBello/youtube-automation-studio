# Architecture Overview

Modular monolith – single installable desktop product with clear module boundaries.

## Layers

```
┌─────────────────────────────────────────────────────────┐
│  PySide6 UI  (dashboard · research · library · …)       │
├─────────────────────────────────────────────────────────┤
│  Application services  (projects · channels · jobs)     │
├──────────────┬──────────────┬──────────────┬────────────┤
│  Research    │  Local AI    │  Media       │  YouTube   │
│  providers   │  adapters    │  (FFmpeg)    │  APIs      │
├──────────────┴──────────────┴──────────────┴────────────┤
│  Persistence  (SQLite · file manifests · keyring)       │
└─────────────────────────────────────────────────────────┘
```

## Key design rules

1. **Local-first** – inference, rendering, and storage stay on the user’s machine by default.
2. **Provider interfaces** – research sources, AI models, and media backends are behind abstract contracts so they can be swapped.
3. **Provenance everywhere** – every research result carries `provider`, `retrieved_at`, and `retention_class`.
4. **Explicit approval** – publishing and destructive actions require a user-confirmed step.
5. **Job stages** – long-running work is persisted with stage-level progress so interrupted renders can resume.
6. **Policy layer** – retention and derived-metric rules are enforced in domain services, not only in the UI.

## Database

SQLite + SQLAlchemy 2.0 + Alembic.  
Media files live on disk; the DB stores paths, hashes, and metadata only.

## Background work

`JobService` + SQLite-backed queue.  
Workers run outside the UI thread (QThread / process pool to be added in P1).

## Compliance

See PRD §6. Public YouTube API data is classified `public_api_30d` and must be refreshed or deleted within 30 days. Derived competitor scores from API statistics are out of scope for v1.
