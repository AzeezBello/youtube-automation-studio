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

## P4 – VirtualDJ & CapCut Pro Studio Features (completed)

- [x] VirtualDJ: Auto-silence trim & smart cue in/out detection + Bass-Swap EQ crossfades
- [x] VirtualDJ: BPM & Musical Key (Camelot Wheel) detection + Smart harmonic track ordering
- [x] CapCut: Dynamic "Now Playing" track title overlay (synced to chapters + `.srt` export) & progress bar
- [x] CapCut: Subtle motion & vintage FX (Ken Burns slow zoom/pan, film grain, vignette, spinning vinyl)
- [x] CapCut: Multi-style audio visualizers (Bar Spectrum, Mirrored Stereo, Dub Oscilloscope, Line Wave)
- [x] CapCut: Auto-Shorts / Reels 9:16 highlight clipper (`1080x1920` peak-energy extractor)

## P5 – Packaging & Hardening

- [ ] Windows / macOS installers
- [ ] Backup / restore
- [ ] Full workflow integration tests with real media
- [ ] Compliance review gate
- [ ] User documentation
