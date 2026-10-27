# YouTube Automation Studio — User Guide

YouTube Automation Studio is a **local-first, privacy-respecting desktop studio** for multi-channel YouTube music/video creators. It runs entirely on your machine without mandatory vidIQ subscriptions, cloud rendering fees, or automated background uploads—keeping you in **100% manual control of publishing**.

---

## 1. Quick Start & Installation

### Requirements
- **Python**: 3.9+ (3.11+ recommended)
- **FFmpeg**: Installed on `PATH` (for full MP4/AAC/filtergraph rendering; a pure-Python WAV/PNG fallback pipeline is built in for offline testing)
- **OS**: macOS 12+ or Windows 10/11

### Setup from Source
```bash
python3 -m venv --upgrade-deps .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
youtube-studio
```

### Hardware Benchmark & Resource Profiles
Run the hardware probe to benchmark your CPU, RAM, GPU, and FFmpeg encoders:
```bash
python scripts/benchmark_hardware.py
```
Profiles (`YTS_RESOURCE_PROFILE`):
- `light`: CPU-only / 8 GB RAM — uses deterministic template text and procedural gradient/vinyl artwork.
- `standard`: 16 GB RAM — enables quantized local LLM (`.gguf`) and local diffusion thumbnail generation.
- `creator_pro`: 32 GB+ RAM & discrete/Apple Silicon GPU — enables high-bitrate hardware-accelerated rendering and batch studio pipelines.

---

## 2. Music Library & Harmonic Audio Intelligence

Navigate to **Music Library** to index your local audio (`WAV`, `MP3`, `FLAC`, `OGG`, `M4A`, `AAC`, `AIFF`, `OPUS`) tracks:
1. Click **Scan Folder** to recursively index audio files, durations, sample rates, bitrates, and waveforms.
   - **Audio-Only Filtering**: Video containers (`.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.flv`, `.m4v`) are strictly excluded so only pure music files are loaded into the Music Library.
   - **Unicode & Curly-Quote Path Resolution**: Automatically resolves folders with curly quotes (`“ ” ‘ ’`) and NFD/NFC macOS filenames.
2. **Audio Intelligence (`DJIntelligenceService`)**:
   - **Auto-BPM & Camelot Key Detection**: Estimates tempo (BPM) and musical key (`1A`–`12B` Camelot wheel).
   - **Harmonic Tracklist Ordering**: Automatically sequences your mix so adjacent tracks share identical or neighbor Camelot keys (`±1` step or relative A/B) and minimal BPM jumps.
   - **Smart Silence Trim & Energy Drop Marker**: Finds leading/trailing dead air (`<-48 dBFS`) for tight cue points and locates the peak energy window for Shorts clipping.

---

## 3. Production Studio & Visual FX

Navigate to **Production** to assemble single-track videos or multi-track DJ mixes:
1. **Audio Transitions**:
   - `NONE`: Hard cut or gap.
   - `CROSSFADE`: Smooth overlapping volume crossfade.
   - `BASS_SWAP_EQ`: 250 Hz low-shelf cut on the outgoing track during the overlap to eliminate muddy double-bass clashes, paired with `-14 LUFS` EBU R128 loudness normalization.
2. **Audio-Reactive Visualizers (`VisualizerStyle`)**:
   - `LINE_WAVE`: Classic sinusoidal waveform overlay.
   - `BAR_SPECTRUM`: Multi-band frequency bars (`showspectrum`).
   - `MIRRORED_STEREO`: Symmetric dual-channel waveform (`split` + `vflip`).
   - `DUB_OSCILLOSCOPE`: Vectorscope / circular stereo phase meter (`avectorscope`).
3. **Motion & Overlay FX (`VisualFXConfig`)**:
   - **Spinning Vinyl Centerpiece**: Rotating vinyl record overlay (`33.3 RPM`).
   - **Now-Playing Track HUD**: Time-windowed `drawtext` lower-third displaying the active track title and artist.
   - **Bottom Progress Bar**: Animated progress bar sweeping from `0%` to `100%`.
   - **Ken Burns Slow Zoom, Film Grain & Vignette**: Prevents static background visual fatigue.
4. ** Export Artifacts**:
   - Every render produces the `.mp4` video, `.png` thumbnail, YouTube chapters (`00:00 Track Title`), `.srt` timed captions, and a `package_manifest.json` ready for manual upload.

---

## 4. Auto-Shorts Highlight Clipper (9:16 Vertical)

Use `ShortsClipperService` (or the **Export 9:16 Short** option in Production) to automatically:
- Detect the highest-energy 15–60 second drop in any track or mix.
- Center-crop and scale the video to `1080x1920` (`9:16` vertical).
- Burn in a hook caption header and audio spectrum bar for YouTube Shorts / Reels / TikTok.

---

## 5. Research Workspace (No vidIQ Required)

Navigate to **Research** to explore public YouTube metadata using your own YouTube Data API v3 key:
- **Keyword & Channel Discovery**: Search public videos, inspect tags/titles, and track daily API quota usage (`10,000` units/day budget).
- **TF-IDF Topic Clustering**: Groups videos into topical clusters using local cosine similarity.
- **Competitor Watchlist**: Track public channel uploads locally without any third-party subscription.

---

## 6. Local AI Metadata & Artwork Studio

Navigate to **Artwork** to manage local AI models (`ModelRegistryService`) and generate:
- **SEO Metadata (`MetadataGenerator`)**: Generates 3 title variants, timestamped descriptions, tags, and thumbnail hook text using either a local GGUF model (`llama-cpp-python`) or the zero-dependency `TemplateFallbackTextAdapter`.
- **16:9 Thumbnails (`ArtworkGenerator`)**: Generates `1280x720` thumbnails using local `diffusers` or the deterministic `ProceduralArtworkFallbackAdapter` (multi-stop harmonic gradients + vinyl grooves + typography).

---

## 7. MCP Hub — Bidirectional Model Context Protocol & Browser OAuth Redirect

Navigate to **MCP Hub** to use both directions of the Model Context Protocol (`2024-11-05`):
1. **Studio as an MCP Server (`youtube-studio-mcp`)**:
   - Exposes **10 MCP tools** (`list_channels`, `create_channel`, `scan_music_library`, `list_audio_tracks`, `search_and_cluster_topics`, `build_harmonic_mix_project`, `generate_project_seo_and_artwork`, `run_production_pipeline`, `export_short_highlight`, `audit_compliance_manifest`), **4 `studio://` resources**, and **2 prompt templates** over JSON-RPC 2.0 stdio.
   - Click **Copy Host Config** to copy the `mcpServers` JSON snippet for Claude Desktop, Cursor, or Antigravity.
2. **Preconfigured MCP Connectors (Connection URL + Browser Login Redirect)**:
   - Includes **9 preconfigured creator MCP connectors** with their MCP Connection URLs pre-populated (`https://mcp.vidiq.com/sse`, `https://mcp.tubebuddy.com/sse`, `https://mcp.youtube.com/sse`, `https://mcp.suno.com/sse`, `https://mcp.elevenlabs.io/sse`, `https://mcp.replicate.com/sse`, `https://mcp.search.brave.com/sse`, `https://mcp.drive.google.com/sse`, `https://mcp.discord.com/sse`).
   - **No API Keys Required**: Select any connector (or paste a custom MCP Connection URL) and click **🌐 Login & Connect in Browser** to authenticate via OAuth 2.1 + PKCE loopback redirect (`http://127.0.0.1:<port>/mcp/oauth/callback`).

---

## 8. Settings, Light/Dark Themes, Auto-Update & Desktop Installers

- **Light / Dark / System Themes**: Click the **☀️ Light / 🌙 Dark** button in the top header bar or use **View → Follow System Theme** to switch themes dynamically.
- **Responsive Desktop Window**: All 7 workspaces automatically reflow between wide desktop split-panes and compact stacked layouts as you resize the window.
- **Settings & Snapshots**:
  - Create and restore atomic **SQLite + Config `.zip` Snapshots** verified by SHA-256 checksums.
  - Run the **Compliance Review Gate** on any export package manifest and purge expired 30-day API cache rows.
  - Check for software updates across `stable` and `beta` channels (`UpdateService`) or open the static **Download & Update Website** (`website/index.html`).

### Building Native Desktop Installers
- **macOS (`.app` and `.dmg`)**:
  ```bash
  ./packaging/build_macos.sh
  ```
- **Windows (`.exe` and `.zip` bundle)**:
  ```powershell
  .\packaging\build_windows.ps1
  ```
