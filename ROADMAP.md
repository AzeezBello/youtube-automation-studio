# Implementation Roadmap

Aligned with PRD §8.

## P0 – Foundation (completed)

- [x] Repository skeleton & `pyproject.toml`
- [x] SQLite schema + Alembic migration `001`
- [x] Domain models (Channel, Project, Job, Media, Research)
- [x] ChannelService & JobService
- [x] FFmpeg detection service
- [x] Research provider contracts + Stub provider
- [x] PySide6 main window + navigation shell
- [x] Unit test scaffolding
- [x] Local hardware benchmark script
- [x] Secure credential vault stub

## P1 – Music-to-video production (completed)

- [x] Recursive media library scanner (MP3/WAV/FLAC)
- [x] Waveform / fingerprint generation
- [x] Track ordering, trim, gain, crossfade editor
- [x] Audio mix pipeline (FFmpeg + PCM WAV fallback)
- [x] Single-track + multi-track video renderer
- [x] Thumbnail layout engine (Pillow + PNG fallback)
- [x] Output validation (duration, codec, streams)
- [x] Job stage recovery & intermediate reuse

## P2 – Research workspace (completed)

- [x] YouTube Data API search adapter (quota-aware)
- [x] Research project UI + notes
- [x] Retention enforcement job (public_api_30d)
- [x] Topic clustering (local embeddings / TF-IDF cosine)
- [x] Competitor watchlist (public metadata only)
- [x] Saved ideas → production brief hand-off

## P3 – Local AI (completed)

- [x] Hardware detection & model registry
- [x] Local instruction-following LM adapter
- [x] Title / description / tag generation
- [x] Optional local image generation
- [x] Template fallbacks when models unavailable

## P4 – Analytics & publishing

- [ ] OAuth 2.0 flow + OS keyring storage
- [ ] YouTube Analytics import
- [ ] Upload preparation + resumable uploads
- [ ] Explicit approval gate & privacy controls
- [ ] Token revocation & data deletion workflow

## P5 – Hardening

- [ ] Windows / macOS installers
- [ ] Backup / restore
- [ ] Full workflow integration tests with real media
- [ ] Compliance review gate
- [ ] User documentation
