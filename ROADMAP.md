# Implementation Roadmap

Aligned with PRD §8.

## P0 – Foundation (current)

- [x] Repository skeleton & `pyproject.toml`
- [x] SQLite schema + Alembic migration `001`
- [x] Domain models (Channel, Project, Job, Media, Research)
- [x] ChannelService & JobService
- [x] FFmpeg detection service
- [x] Research provider contracts + Stub provider
- [x] PySide6 main window + navigation shell
- [x] Unit test scaffolding
- [ ] Local hardware benchmark script
- [ ] Secure credential vault stub

## P1 – Music-to-video production

- [ ] Recursive media library scanner (MP3/WAV/FLAC)
- [ ] Waveform / fingerprint generation
- [ ] Track ordering, trim, gain, crossfade editor
- [ ] Audio mix pipeline (FFmpeg)
- [ ] Single-track + multi-track video renderer
- [ ] Thumbnail layout engine (Pillow)
- [ ] Output validation (duration, codec, streams)
- [ ] Job stage recovery & intermediate reuse

## P2 – Research workspace

- [ ] YouTube Data API search adapter (quota-aware)
- [ ] Research project UI + notes
- [ ] Retention enforcement job (public_api_30d)
- [ ] Topic clustering (local embeddings)
- [ ] Competitor watchlist (public metadata only)
- [ ] Saved ideas → production brief hand-off

## P3 – Local AI

- [ ] Hardware detection & model registry
- [ ] Local instruction-following LM adapter
- [ ] Title / description / tag generation
- [ ] Optional local image generation
- [ ] Template fallbacks when models unavailable

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
