"""Built-in Studio MCP Server (stdio JSON-RPC 2.0 + direct in-process invocation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional, TextIO

from youtube_studio import __version__
from youtube_studio.ai import ArtworkGenerator, MetadataGenerationRequest, MetadataGenerator
from youtube_studio.config import get_settings
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.media import MediaType
from youtube_studio.domain.models.project import (
    AssetType,
    ProjectType,
    TransitionConfig,
    TransitionType,
)
from youtube_studio.domain.policies.compliance_gate import ComplianceReviewGate
from youtube_studio.domain.services import (
    ChannelService,
    MediaLibraryService,
    ProjectService,
    ResearchService,
)
from youtube_studio.jobs.runner import ProductionJobRunner
from youtube_studio.mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    MCPCallResult,
    MCPPromptDefinition,
    MCPResourceDefinition,
    MCPToolDefinition,
)
from youtube_studio.media.scanner import MediaScanner
from youtube_studio.media.shorts_clipper import ShortsClipperService
from youtube_studio.research import QuotaTracker, StubResearchProvider, TopicClusterer
from youtube_studio.storage import get_engine, session_scope
from youtube_studio.storage.backup import BackupService
from youtube_studio.storage.orm import Base


class StudioMCPServer:
    """Exposes YouTube Automation Studio tools, resources, and prompts over MCP."""

    SERVER_NAME = "youtube-automation-studio-mcp"

    def __init__(self) -> None:
        settings = get_settings()
        settings.ensure_directories()
        engine = get_engine()
        Base.metadata.create_all(engine)
        self._scanner = MediaScanner()
        self._quota = QuotaTracker()
        self._stub_research = StubResearchProvider()
        self._clusterer = TopicClusterer()
        self._compliance_gate = ComplianceReviewGate()

    @classmethod
    def get_host_config_json(cls, python_executable: Optional[str] = None) -> str:
        """Return a ready-to-paste mcpServers JSON configuration for Claude Desktop / Cursor / Antigravity."""
        py_bin = python_executable or sys.executable
        config = {
            "mcpServers": {
                "youtube-automation-studio": {
                    "command": py_bin,
                    "args": ["-m", "youtube_studio.mcp.cli"],
                    "env": {
                        "YAS_DATA_DIR": str(get_settings().resolved_data_dir()),
                    },
                }
            }
        }
        return json.dumps(config, indent=2)

    # ------------------------------------------------------------------
    # Tool, Resource & Prompt Catalog
    # ------------------------------------------------------------------

    def list_tools(self) -> list[MCPToolDefinition]:
        return [
            MCPToolDefinition(
                name="list_channels",
                description="List all active YouTube channel brand profiles in the local studio database.",
                input_schema={"type": "object", "properties": {}},
                sample_arguments={},
            ),
            MCPToolDefinition(
                name="create_channel",
                description="Create a new YouTube channel profile with a visual palette and default genre tags.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Channel display name"},
                        "palette": {
                            "type": "string",
                            "description": "Brand palette (warm_earth, dub_obsidian, neon_cyber, minimal_slate)",
                            "default": "dub_obsidian",
                        },
                        "default_tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Default genre/topic tags for this channel",
                        },
                    },
                    "required": ["name"],
                },
                sample_arguments={
                    "name": "Deep 140 Bass Collective",
                    "palette": "dub_obsidian",
                    "default_tags": ["deep dubstep", "140 bpm", "harmonic mix"],
                },
            ),
            MCPToolDefinition(
                name="scan_music_library",
                description="Recursively scan a local folder for audio files (WAV/MP3/FLAC/M4A/AAC/OGG), extracting BPM, Camelot key, waveform fingerprint, and duplicates.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "folder_path": {
                            "type": "string",
                            "description": "Absolute or relative path to the local music directory",
                        }
                    },
                    "required": ["folder_path"],
                },
                sample_arguments={"folder_path": "./output/studio_data/assets"},
            ),
            MCPToolDefinition(
                name="list_music_library",
                description="List indexed audio tracks in the Music Library with BPM, Camelot key (1A-12B), duration, and file path.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional search filter by title, artist, or path",
                        }
                    },
                },
                sample_arguments={"query": ""},
            ),
            MCPToolDefinition(
                name="build_harmonic_mix_project",
                description=(
                    "Create a production project, add tracks from the library, run Auto-Cue Silence Trim "
                    "and Smart Harmonic Sort (Camelot Wheel + BPM), and configure transitions."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "string", "description": "Target channel ID"},
                        "project_name": {"type": "string", "description": "Name of the mix/video project"},
                        "media_file_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of media_file_id values to add (if empty, uses all indexed audio tracks)",
                        },
                        "transition_type": {
                            "type": "string",
                            "description": "Transition mode: bass_swap_eq, crossfade, or none",
                            "default": "bass_swap_eq",
                        },
                        "overlap_ms": {
                            "type": "integer",
                            "description": "Crossfade overlap in milliseconds",
                            "default": 3000,
                        },
                    },
                    "required": ["channel_id", "project_name"],
                },
                sample_arguments={
                    "channel_id": "<channel_id>",
                    "project_name": "Harmonic Dub Session Vol. 1",
                    "media_file_ids": [],
                    "transition_type": "bass_swap_eq",
                    "overlap_ms": 3000,
                },
            ),
            MCPToolDefinition(
                name="render_release_package",
                description=(
                    "Execute the full 6-stage ProductionJobRunner pipeline (validate_inputs -> mix_audio -> "
                    "generate_thumbnail -> render_video -> validate_output -> package) with visualizers and overlays."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Production project ID"},
                        "visualizer_style": {
                            "type": "string",
                            "description": "bar_spectrum, mirrored_stereo, dub_oscilloscope, line_wave, or none",
                            "default": "bar_spectrum",
                        },
                        "now_playing_overlay": {"type": "boolean", "default": True},
                        "progress_bar": {"type": "boolean", "default": True},
                        "slow_zoom": {"type": "boolean", "default": True},
                    },
                    "required": ["project_id"],
                },
                sample_arguments={
                    "project_id": "<project_id>",
                    "visualizer_style": "bar_spectrum",
                    "now_playing_overlay": True,
                    "progress_bar": True,
                    "slow_zoom": True,
                },
            ),
            MCPToolDefinition(
                name="export_highlight_short_9x16",
                description="Detect the highest-energy 30-second window of a project's audio and render a 1080x1920 (9:16) vertical Short video & thumbnail.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Production project ID"},
                        "clip_duration_ms": {"type": "integer", "default": 30000},
                    },
                    "required": ["project_id"],
                },
                sample_arguments={"project_id": "<project_id>", "clip_duration_ms": 15000},
            ),
            MCPToolDefinition(
                name="generate_metadata_and_artwork",
                description="Generate 3 YouTube SEO title candidates, 00:00 chapter descriptions, tags, and a 16:9 or 9:16 thumbnail asset for a project.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Production project ID"},
                        "palette": {"type": "string", "default": "dub_obsidian"},
                        "aspect_ratio": {
                            "type": "string",
                            "description": "16:9 or 9:16",
                            "default": "16:9",
                        },
                    },
                    "required": ["project_id"],
                },
                sample_arguments={
                    "project_id": "<project_id>",
                    "palette": "dub_obsidian",
                    "aspect_ratio": "16:9",
                },
            ),
            MCPToolDefinition(
                name="search_and_cluster_topics",
                description="Search keyword topics, group results into TF-IDF cosine similarity clusters, and optionally save top ideas.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search topic or genre query"},
                        "save_top_idea": {"type": "boolean", "default": True},
                        "channel_id": {"type": "string", "description": "Optional channel ID to attach saved idea"},
                    },
                    "required": ["query"],
                },
                sample_arguments={
                    "query": "deep 140 dubstep harmonic bass mix",
                    "save_top_idea": True,
                },
            ),
            MCPToolDefinition(
                name="audit_compliance_and_backup",
                description="Run the Compliance Review Gate on an export package_manifest.json and optionally create an atomic SHA-256 verified SQLite database backup.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "manifest_path": {
                            "type": "string",
                            "description": "Optional path to package_manifest.json to audit",
                        },
                        "create_db_backup": {
                            "type": "boolean",
                            "description": "Whether to create an atomic SQLite snapshot backup ZIP",
                            "default": True,
                        },
                    },
                },
                sample_arguments={"create_db_backup": True},
            ),
        ]

    def list_resources(self) -> list[MCPResourceDefinition]:
        return [
            MCPResourceDefinition(
                uri="studio://channels",
                name="Active YouTube Channels",
                description="All active channel profiles and their brand configurations.",
            ),
            MCPResourceDefinition(
                uri="studio://library/audio",
                name="Indexed Audio Library",
                description="All scanned audio tracks with BPM, Camelot key, duration, and file hash.",
            ),
            MCPResourceDefinition(
                uri="studio://projects",
                name="Production Projects & Chapters",
                description="All production projects with track counts, status, and computed chapter timestamps.",
            ),
            MCPResourceDefinition(
                uri="studio://compliance/status",
                name="Compliance & Backup Status",
                description="YouTube API quota usage, 30-day retention policy rules, and available database snapshots.",
            ),
        ]

    def list_prompts(self) -> list[MCPPromptDefinition]:
        return [
            MCPPromptDefinition(
                name="curate_harmonic_mix_session",
                description="Analyzes indexed library tracks (BPM + Camelot keys) and proposes an optimal harmonic DJ mix tracklist and SEO package.",
                arguments=[
                    {
                        "name": "genre_focus",
                        "description": "Target genre or mood (e.g. Deep Dubstep, Ambient Lo-Fi)",
                        "required": False,
                    }
                ],
            ),
            MCPPromptDefinition(
                name="pre_publish_compliance_review",
                description="Reviews a production project's metadata and generates a manual YouTube Studio publishing checklist.",
                arguments=[
                    {
                        "name": "project_id",
                        "description": "Target project ID to review",
                        "required": False,
                    }
                ],
            ),
        ]

    # ------------------------------------------------------------------
    # Tool Execution
    # ------------------------------------------------------------------

    def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> MCPCallResult:
        args = arguments or {}
        try:
            if name == "list_channels":
                with session_scope() as session:
                    channels = ChannelService(session).list_active()
                payload = {
                    "count": len(channels),
                    "channels": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "visual_style": c.brand_config.visual_style,
                            "default_resolution": c.brand_config.default_resolution,
                            "default_tags": c.brand_config.default_tags,
                        }
                        for c in channels
                    ],
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "create_channel":
                ch_name = str(args.get("name", "")).strip()
                if not ch_name:
                    raise ValueError("'name' is required to create a channel")
                palette = str(args.get("palette", "dub_obsidian"))
                tags = [str(t) for t in args.get("default_tags", ["music mix", "full session"])]
                brand = ChannelBrandConfig(
                    visual_style=palette,
                    default_tags=tags,
                    thumbnail_style={"palette": palette, "motif": "vinyl_and_sound_system"},
                )
                with session_scope() as session:
                    ch = ChannelService(session).create(ch_name, brand=brand)
                payload = {
                    "id": ch.id,
                    "name": ch.name,
                    "palette": palette,
                    "default_tags": tags,
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "scan_music_library":
                raw_folder = str(args.get("folder_path") or args.get("directory_path") or "")
                folder = self._scanner.resolve_directory(raw_folder)
                folder.mkdir(parents=True, exist_ok=True)
                with session_scope() as session:
                    media_svc = MediaLibraryService(session)
                    summary = self._scanner.scan_directory(
                        folder,
                        media_service=media_svc,
                        audio_only=True,
                    )
                payload = {
                    "folder": str(folder),
                    "scanned_count": len(summary.scanned_files),
                    "duplicate_groups": len(summary.duplicates_by_hash),
                    "skipped_extensions": summary.skipped_extensions,
                    "errors": summary.errors,
                    "tracks": [
                        {
                            "id": m.id,
                            "title": m.metadata.get("title") or Path(m.path).stem,
                            "duration_ms": m.duration_ms,
                            "bpm": m.metadata.get("bpm"),
                            "camelot_code": m.metadata.get("camelot_code"),
                            "path": m.path,
                        }
                        for m in summary.scanned_files
                    ],
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "list_music_library":
                query = str(args.get("query", "")).strip() or None
                with session_scope() as session:
                    svc = MediaLibraryService(session)
                    items = svc.list_media(media_type=MediaType.AUDIO, query=query)
                    dups = svc.find_duplicates()
                dup_hashes = set(dups.keys())
                payload = {
                    "count": len(items),
                    "duplicate_groups": len(dup_hashes),
                    "tracks": [
                        {
                            "id": m.id,
                            "title": m.metadata.get("title") or Path(m.path).stem,
                            "duration_ms": m.duration_ms,
                            "bpm": m.metadata.get("bpm"),
                            "camelot_code": m.metadata.get("camelot_code"),
                            "musical_key": m.metadata.get("musical_key"),
                            "is_duplicate": bool(m.file_hash and m.file_hash in dup_hashes),
                            "path": m.path,
                        }
                        for m in items
                    ],
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "build_harmonic_mix_project":
                channel_id = str(args.get("channel_id", "")).strip()
                project_name = str(args.get("project_name", "Harmonic Mix Session")).strip()
                media_ids = [str(x) for x in args.get("media_file_ids", []) if str(x).strip()]
                trans_str = str(args.get("transition_type", "bass_swap_eq"))
                overlap_ms = int(args.get("overlap_ms", 3000))
                t_type = (
                    TransitionType(trans_str)
                    if trans_str in {t.value for t in TransitionType}
                    else TransitionType.BASS_SWAP_EQ
                )

                with session_scope() as session:
                    ch_svc = ChannelService(session)
                    proj_svc = ProjectService(session)
                    media_svc = MediaLibraryService(session)

                    if not channel_id or ch_svc.get(channel_id) is None:
                        existing = ch_svc.list_active()
                        channel_id = existing[0].id if existing else ch_svc.create("Default Studio Channel").id

                    proj = proj_svc.create_project(channel_id, project_name, project_type=ProjectType.MIX)
                    if not media_ids:
                        media_ids = [m.id for m in media_svc.list_media(media_type=MediaType.AUDIO)]

                    for mid in media_ids:
                        pt = proj_svc.add_track(proj.id, mid)
                        pt.transition_config = TransitionConfig(
                            transition_type=t_type,
                            overlap_ms=overlap_ms,
                        )
                        proj_svc.update_track(pt)

                    proj_svc.auto_cue_trim_tracks(proj.id)
                    ordered_tracks = proj_svc.auto_harmonic_sort(proj.id)
                    chapters = proj_svc.compute_chapters(proj.id)
                    total_ms = proj_svc.compute_total_duration_ms(proj.id)

                payload = {
                    "project_id": proj.id,
                    "channel_id": channel_id,
                    "project_name": proj.name,
                    "track_count": len(ordered_tracks),
                    "total_duration_ms": total_ms,
                    "chapters": [
                        {"start_ms": c.start_ms, "timestamp": c.format_timestamp(), "title": c.title}
                        for c in chapters
                    ],
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "render_release_package":
                project_id = str(args.get("project_id", "")).strip()
                vis_style = str(args.get("visualizer_style", "bar_spectrum"))
                fx_payload = {
                    "now_playing_overlay": bool(args.get("now_playing_overlay", True)),
                    "progress_bar": bool(args.get("progress_bar", True)),
                    "slow_zoom": bool(args.get("slow_zoom", True)),
                }
                with session_scope() as session:
                    runner = ProductionJobRunner(session)
                    job = runner.enqueue_production_job(
                        project_id,
                        visualizer_style=vis_style,
                        visual_fx=fx_payload,
                    )
                    summary = runner.run_job(job.id)
                payload = {
                    "job_id": summary.job.id,
                    "project_id": summary.project_id,
                    "status": summary.job.status.value,
                    "output_dir": str(summary.output_dir),
                    "manifest_path": str(summary.manifest_path) if summary.manifest_path else None,
                    "executed_stages": summary.executed_stages,
                    "reused_stages": summary.reused_stages,
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "export_highlight_short_9x16":
                project_id = str(args.get("project_id", "")).strip()
                clip_dur = int(args.get("clip_duration_ms", 30000))
                with session_scope() as session:
                    proj_svc = ProjectService(session)
                    media_svc = MediaLibraryService(session)
                    proj = proj_svc.get_project(project_id)
                    if not proj:
                        raise ValueError(f"Project not found: {project_id}")
                    tracks = proj_svc.list_tracks(project_id)
                    if not tracks:
                        raise ValueError(f"Project '{proj.name}' has no tracks")
                    first_media = media_svc.get(tracks[0].media_file_id)
                    if not first_media:
                        raise ValueError("Track media file not found")
                    out_dir = get_settings().resolved_output_dir() / project_id / "shorts"
                    clipper = ShortsClipperService()
                    short_res = clipper.create_highlight_short(
                        Path(first_media.path),
                        out_dir,
                        title=proj.name,
                        source_duration_ms=first_media.duration_ms,
                        clip_duration_ms=clip_dur,
                    )
                payload = {
                    "project_id": project_id,
                    "video_path": str(short_res.video_path),
                    "thumbnail_path": str(short_res.thumbnail_path),
                    "audio_path": str(short_res.audio_path),
                    "start_ms": short_res.start_ms,
                    "end_ms": short_res.end_ms,
                    "duration_ms": short_res.duration_ms,
                    "resolution": "1080x1920",
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "generate_metadata_and_artwork":
                project_id = str(args.get("project_id", "")).strip()
                palette = str(args.get("palette", "dub_obsidian"))
                aspect = str(args.get("aspect_ratio", "16:9"))
                width, height = (1080, 1920) if aspect == "9:16" else (1280, 720)

                with session_scope() as session:
                    proj_svc = ProjectService(session)
                    ch_svc = ChannelService(session)
                    proj = proj_svc.get_project(project_id)
                    if not proj:
                        raise ValueError(f"Project not found: {project_id}")
                    ch = ch_svc.get(proj.channel_id)
                    chapters = proj_svc.compute_chapters(project_id)

                    meta_gen = MetadataGenerator()
                    meta_res = meta_gen.generate(
                        MetadataGenerationRequest(
                            project_name=proj.name,
                            project_type=proj.project_type,
                            channel_name=ch.name if ch else "YouTube Automation Studio",
                            brand_config=ch.brand_config if ch else ChannelBrandConfig(),
                            chapters=chapters,
                        )
                    )
                    draft = proj_svc.save_metadata_draft(
                        project_id,
                        title=meta_res.title,
                        description=meta_res.description,
                        tags=meta_res.tags,
                        chapters=chapters,
                        approval_status="approved",
                    )

                    out_dir = get_settings().resolved_output_dir() / project_id
                    out_path = out_dir / f"thumbnail_{palette}_{width}x{height}.png"
                    art_res = ArtworkGenerator().generate(
                        proj.name,
                        out_path,
                        width=width,
                        height=height,
                        style_palette=palette,
                        subtitle=ch.name if ch else None,
                        badge_text=proj.project_type.value.upper(),
                    )
                    proj_svc.register_asset(
                        project_id,
                        AssetType.THUMBNAIL,
                        str(art_res.output_path),
                        source_type=art_res.adapter_used,
                        provenance=art_res.provenance,
                        checksum=art_res.checksum,
                        approved=True,
                    )

                payload = {
                    "project_id": project_id,
                    "draft_version": draft.version,
                    "title": meta_res.title,
                    "title_candidates": meta_res.title_candidates,
                    "tags": meta_res.tags,
                    "description": meta_res.description,
                    "thumbnail_path": str(art_res.output_path),
                    "thumbnail_resolution": f"{width}x{height}",
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "search_and_cluster_topics":
                query = str(args.get("query", "")).strip()
                if not query:
                    raise ValueError("'query' is required")
                save_top = bool(args.get("save_top_idea", True))
                channel_id = args.get("channel_id")

                results = self._stub_research.search(query, max_results=12)
                clusters = self._clusterer.cluster(results)
                saved_idea_id: Optional[str] = None

                with session_scope() as session:
                    r_svc = ResearchService(session)
                    for r in results:
                        r_svc.record_source(r)
                    if save_top and clusters and clusters[0].results:
                        top = clusters[0].results[0]
                        idea = r_svc.save_idea(
                            str(top.payload.get("title", query)),
                            channel_id=channel_id,
                            rationale=f"MCP Cluster: {clusters[0].label}",
                        )
                        saved_idea_id = idea.id

                payload = {
                    "query": query,
                    "total_results": len(results),
                    "cluster_count": len(clusters),
                    "saved_idea_id": saved_idea_id,
                    "clusters": [
                        {
                            "label": c.label,
                            "keywords": c.keywords,
                            "items": [str(item.payload.get("title", "")) for item in c.results],
                        }
                        for c in clusters
                    ],
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if name == "audit_compliance_and_backup":
                manifest_str = str(args.get("manifest_path", "")).strip()
                do_backup = bool(args.get("create_db_backup", True))
                payload: dict[str, Any] = {}

                if manifest_str:
                    rep = self._compliance_gate.review_package_manifest(Path(manifest_str))
                    payload["compliance_report"] = {
                        "passed": rep.passed,
                        "blocking_reasons": rep.blocking_reasons,
                        "checks": [
                            {"name": c.name, "passed": c.passed, "details": c.details}
                            for c in rep.checks
                        ],
                    }

                if do_backup:
                    backup_svc = BackupService()
                    db_path = get_settings().database_path()
                    if db_path.exists():
                        zip_path, b_manifest = backup_svc.create_backup()
                        payload["backup"] = {
                            "archive_path": str(zip_path),
                            "backup_id": b_manifest.backup_id,
                            "database_sha256": b_manifest.database_sha256,
                            "created_at": b_manifest.created_at,
                        }
                    else:
                        payload["backup"] = {"status": "skipped (database file not yet created)"}

                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            raise ValueError(f"Unknown MCP tool: {name}")
        except Exception as exc:
            err_payload = {"error": str(exc), "tool": name}
            return MCPCallResult(True, json.dumps(err_payload, indent=2), err_payload)

    # ------------------------------------------------------------------
    # Resource & Prompt Readers
    # ------------------------------------------------------------------

    def read_resource(self, uri: str) -> MCPCallResult:
        try:
            if uri == "studio://channels":
                return self.call_tool("list_channels", {})
            if uri == "studio://library/audio":
                return self.call_tool("list_music_library", {})
            if uri == "studio://projects":
                with session_scope() as session:
                    proj_svc = ProjectService(session)
                    projects = proj_svc.list_projects()
                    items = []
                    for p in projects:
                        chapters = proj_svc.compute_chapters(p.id)
                        items.append(
                            {
                                "id": p.id,
                                "channel_id": p.channel_id,
                                "name": p.name,
                                "type": p.project_type.value,
                                "status": p.status.value,
                                "chapters": [
                                    {"timestamp": c.format_timestamp(), "title": c.title}
                                    for c in chapters
                                ],
                            }
                        )
                payload = {"count": len(items), "projects": items}
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            if uri == "studio://compliance/status":
                backups = BackupService().list_backups()
                payload = {
                    "manual_publishing_enforced": True,
                    "api_retention_window_days": 30,
                    "quota_used_units": self._quota.used_units,
                    "quota_remaining_units": self._quota.remaining_units,
                    "available_backups_count": len(backups),
                    "latest_backup": str(backups[0]) if backups else None,
                }
                return MCPCallResult(False, json.dumps(payload, indent=2), payload)

            raise ValueError(f"Unknown MCP resource URI: {uri}")
        except Exception as exc:
            err = {"error": str(exc), "uri": uri}
            return MCPCallResult(True, json.dumps(err, indent=2), err)

    def get_prompt(self, name: str, arguments: Optional[dict[str, Any]] = None) -> MCPCallResult:
        args = arguments or {}
        if name == "curate_harmonic_mix_session":
            genre = str(args.get("genre_focus", "Deep Harmonic Session"))
            lib_res = self.call_tool("list_music_library", {})
            tracks = lib_res.structured_data.get("tracks", [])
            prompt_text = (
                f"You are curating a '{genre}' release in YouTube Automation Studio.\n"
                f"Currently indexed audio tracks ({len(tracks)}):\n"
                f"{json.dumps(tracks[:20], indent=2)}\n\n"
                "Tasks:\n"
                "1. Select tracks that form a smooth Camelot Wheel progression (0 or 1 step distance).\n"
                "2. Call `build_harmonic_mix_project` with `transition_type='bass_swap_eq'`.\n"
                "3. Call `generate_metadata_and_artwork` and `render_release_package`.\n"
                "4. Present the final package path and chapters for manual upload review."
            )
            return MCPCallResult(
                False,
                prompt_text,
                {"description": f"Curate {genre} mix", "messages": [{"role": "user", "content": prompt_text}]},
            )

        if name == "pre_publish_compliance_review":
            pid = str(args.get("project_id", "<project_id>"))
            prompt_text = (
                f"Run a pre-publish compliance review for project '{pid}':\n"
                "1. Call `audit_compliance_and_backup` on the project's `package_manifest.json`.\n"
                "2. Verify that title length <= 100 chars, tags <= 500 chars, chapters start at 00:00, "
                "and all rendered video/thumbnail files pass validation.\n"
                "3. Provide a concise manual upload checklist for YouTube Studio."
            )
            return MCPCallResult(
                False,
                prompt_text,
                {"description": "Pre-publish compliance review", "messages": [{"role": "user", "content": prompt_text}]},
            )

        return MCPCallResult(True, f"Unknown prompt: {name}", {"error": f"Unknown prompt: {name}"})

    # ------------------------------------------------------------------
    # JSON-RPC 2.0 Message Handler & stdio Server Loop
    # ------------------------------------------------------------------

    def handle_jsonrpc_request(self, request: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Process a single JSON-RPC 2.0 request dict and return a JSON-RPC response dict (or None for notifications)."""
        method = str(request.get("method", ""))
        req_id = request.get("id")
        params = request.get("params") or {}

        # Notifications have no 'id'
        if req_id is None and method.startswith("notifications/"):
            return None

        try:
            if method == "initialize":
                result: dict[str, Any] = {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": self.SERVER_NAME,
                        "version": __version__,
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [t.to_mcp_dict() for t in self.list_tools()]}
            elif method == "tools/call":
                t_name = str(params.get("name", ""))
                t_args = params.get("arguments") or {}
                call_res = self.call_tool(t_name, t_args)
                result = call_res.to_mcp_tool_result()
            elif method == "resources/list":
                result = {"resources": [r.to_mcp_dict() for r in self.list_resources()]}
            elif method == "resources/read":
                uri = str(params.get("uri", ""))
                read_res = self.read_resource(uri)
                result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": read_res.text,
                        }
                    ]
                }
            elif method == "prompts/list":
                result = {"prompts": [p.to_mcp_dict() for p in self.list_prompts()]}
            elif method == "prompts/get":
                p_name = str(params.get("name", ""))
                p_args = params.get("arguments") or {}
                p_res = self.get_prompt(p_name, p_args)
                result = {
                    "description": p_res.structured_data.get("description", p_name),
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": p_res.text},
                        }
                    ],
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }

    def serve_stdio(
        self,
        stdin: Optional[TextIO] = None,
        stdout: Optional[TextIO] = None,
    ) -> None:
        """Run the newline-delimited JSON-RPC 2.0 MCP server loop over stdio."""
        in_stream = stdin or sys.stdin
        out_stream = stdout or sys.stdout
        for raw_line in in_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except Exception as exc:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                out_stream.write(json.dumps(err_resp) + "\n")
                out_stream.flush()
                continue

            resp = self.handle_jsonrpc_request(req)
            if resp is not None:
                out_stream.write(json.dumps(resp) + "\n")
                out_stream.flush()
