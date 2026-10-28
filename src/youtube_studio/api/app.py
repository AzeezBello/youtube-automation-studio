"""FastAPI + zero-dependency HTTP router exposing StudioFacade for local desktop IPC and future SaaS."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from youtube_studio import __version__
from youtube_studio.config import get_settings
from youtube_studio.domain.services.studio_facade import StudioFacade
from youtube_studio.storage import get_engine
from youtube_studio.storage.orm import Base


class StudioAPIApp:
    """Unified HTTP API router backed by StudioFacade.

    Supports both:
    - FastAPI / Uvicorn when installed (`pip install -e ".[saas]"`)
    - Built-in stdlib HTTP server & direct `.dispatch()` for zero-dependency local mode and unit testing
    """

    def __init__(self, *, facade: Optional[StudioFacade] = None, run_mode: str = "desktop_local") -> None:
        self.facade = facade or StudioFacade(run_mode=run_mode)

    def dispatch(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict[str, Any]] = None,
        query: Optional[dict[str, Any]] = None,
    ) -> tuple[int, dict[str, Any]]:
        """Route an HTTP request to the appropriate StudioFacade method and return (status_code, payload)."""
        verb = method.upper().strip()
        clean_path = path.split("?", 1)[0].rstrip("/") or "/"
        payload = body or {}
        params = query or {}

        try:
            if verb == "GET" and clean_path in ("/", "/health", "/api/v1/health"):
                return 200, self.facade.get_health()

            if verb == "GET" and clean_path == "/api/v1/presets":
                return 200, self.facade.list_presets()

            if verb == "GET" and clean_path == "/api/v1/channels":
                return 200, {"channels": self.facade.list_channels()}

            if verb == "POST" and clean_path == "/api/v1/channels":
                name = str(payload.get("name") or "Echoes of Livity")
                niche_preset = str(payload.get("niche_preset") or "roots_reggae_mix")
                preferred_voice_preset = str(
                    payload.get("preferred_voice_preset") or "warm_male_narrator"
                )
                voice_speed = float(payload.get("voice_speed") or 1.0)
                channel = self.facade.create_or_get_channel(
                    name,
                    niche_preset=niche_preset,
                    preferred_voice_preset=preferred_voice_preset,
                    voice_speed=voice_speed,
                )
                return 200, {"channel": channel}

            if verb == "GET" and clean_path == "/api/v1/projects":
                channel_id = params.get("channel_id")
                if isinstance(channel_id, list):
                    channel_id = channel_id[0] if channel_id else None
                return 200, {"projects": self.facade.list_projects(channel_id=channel_id)}

            if verb == "GET" and clean_path.startswith("/api/v1/projects/"):
                project_id = clean_path.removeprefix("/api/v1/projects/").strip("/")
                return 200, {"project": self.facade.get_project_details(project_id)}

            if verb == "POST" and clean_path == "/api/v1/research/import-url":
                video_url = str(payload.get("video_url") or "").strip()
                if not video_url:
                    return 400, {"error": "video_url is required"}
                channel_id = payload.get("channel_id")
                res = self.facade.import_youtube_url_brief(video_url, channel_id=channel_id)
                return 200, res

            if verb == "POST" and clean_path == "/api/v1/titles/score":
                project_name = str(payload.get("project_name") or "").strip()
                if not project_name:
                    return 400, {"error": "project_name is required"}
                res = self.facade.score_titles(
                    project_name,
                    channel_name=str(payload.get("channel_name") or "Echoes of Livity"),
                    niche_preset=str(payload.get("niche_preset") or "roots_reggae_mix"),
                    seed_keywords=payload.get("seed_keywords"),
                )
                return 200, res

            if verb == "POST" and clean_path == "/api/v1/script/generate":
                topic = str(payload.get("topic") or "").strip()
                if not topic:
                    return 400, {"error": "topic is required"}
                res = self.facade.generate_structured_script(
                    topic,
                    channel_name=str(payload.get("channel_name") or "Echoes of Livity"),
                    tone=str(
                        payload.get("tone")
                        or "warm, conscious roots reggae & dub sound system session"
                    ),
                    target_duration_minutes=int(payload.get("target_duration_minutes") or 15),
                )
                return 200, res

            if verb == "POST" and clean_path == "/api/v1/voiceover/synthesize":
                text = str(payload.get("text") or "").strip()
                if not text:
                    return 400, {"error": "text is required"}
                res = self.facade.synthesize_voiceover(
                    text,
                    preset_key=str(payload.get("preset_key") or "warm_male_narrator"),
                    speed=float(payload.get("speed") or 1.0),
                    output_filename=payload.get("output_filename"),
                )
                return 200, res

            if verb == "POST" and clean_path == "/api/v1/autopilot/run":
                res = self.facade.run_autopilot(
                    channel_id=payload.get("channel_id"),
                    project_name=payload.get("project_name"),
                    source_folder=payload.get("source_folder"),
                    library_folder_name=payload.get("library_folder_name"),
                    youtube_url=payload.get("youtube_url"),
                    script_text=payload.get("script_text"),
                    synthesize_voiceover=bool(payload.get("synthesize_voiceover", False)),
                    voice_preset=payload.get("voice_preset"),
                    voice_speed=float(payload.get("voice_speed") or 1.0),
                    niche_preset=payload.get("niche_preset", "roots_reggae_mix"),
                    target_duration_minutes=int(payload.get("target_duration_minutes") or 60),
                    output_name=payload.get("output_name"),
                    render_video=bool(payload.get("render_video", True)),
                    export_short=bool(payload.get("export_short", True)),
                )
                return 200, res

            if verb == "POST" and clean_path == "/api/v1/autopilot/daily":
                res = self.facade.run_daily_channel_autopilot(
                    channel_name=str(payload.get("channel_name") or "Echoes of Livity"),
                    niche_preset=str(payload.get("niche_preset") or "roots_reggae_mix"),
                    voice_preset=str(payload.get("voice_preset") or "warm_male_narrator"),
                    source_folder=payload.get("source_folder"),
                    library_folder_name=payload.get("library_folder_name"),
                    youtube_url=payload.get("youtube_url"),
                    script_text=payload.get("script_text"),
                    synthesize_voiceover=bool(payload.get("synthesize_voiceover", False)),
                    target_duration_minutes=int(payload.get("target_duration_minutes") or 60),
                    render_video=bool(payload.get("render_video", True)),
                    export_short=bool(payload.get("export_short", True)),
                )
                return 200, res

            return 404, {"error": f"Route not found: {verb} {clean_path}"}
        except ValueError as exc:
            return 404, {"error": str(exc)}
        except Exception as exc:
            return 500, {"error": str(exc)}


def create_api_app(*, run_mode: str = "desktop_local") -> StudioAPIApp:
    """Create a configured StudioAPIApp instance and ensure DB schema exists."""
    settings = get_settings()
    settings.ensure_directories()
    Base.metadata.create_all(get_engine())
    return StudioAPIApp(run_mode=run_mode)


def create_fastapi_app(*, run_mode: str = "desktop_local") -> Any:
    """Create a FastAPI app wrapping StudioAPIApp if FastAPI is installed, else return StudioAPIApp."""
    api_app = create_api_app(run_mode=run_mode)
    try:
        from fastapi import Body, FastAPI, HTTPException, Query
    except ImportError:
        return api_app

    fapp = FastAPI(
        title="YouTube Automation Studio API",
        version=__version__,
        description="Shared domain API for Desktop Local IPC and Web SaaS mode.",
    )

    @fapp.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return api_app.facade.get_health()

    @fapp.get("/api/v1/presets")
    def list_presets() -> dict[str, Any]:
        return api_app.facade.list_presets()

    @fapp.get("/api/v1/channels")
    def list_channels() -> dict[str, Any]:
        return {"channels": api_app.facade.list_channels()}

    @fapp.post("/api/v1/channels")
    def create_channel(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/channels", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Error"))
        return data

    @fapp.get("/api/v1/projects")
    def list_projects(channel_id: Optional[str] = Query(default=None)) -> dict[str, Any]:
        return {"projects": api_app.facade.list_projects(channel_id=channel_id)}

    @fapp.get("/api/v1/projects/{project_id}")
    def get_project(project_id: str) -> dict[str, Any]:
        status, data = api_app.dispatch("GET", f"/api/v1/projects/{project_id}")
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Not found"))
        return data

    @fapp.post("/api/v1/research/import-url")
    def import_url(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/research/import-url", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Bad request"))
        return data

    @fapp.post("/api/v1/titles/score")
    def score_titles(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/titles/score", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Bad request"))
        return data

    @fapp.post("/api/v1/script/generate")
    def generate_script(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/script/generate", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Bad request"))
        return data

    @fapp.post("/api/v1/voiceover/synthesize")
    def synthesize_voiceover(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/voiceover/synthesize", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Bad request"))
        return data

    @fapp.post("/api/v1/autopilot/run")
    def run_autopilot(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/autopilot/run", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Autopilot error"))
        return data

    @fapp.post("/api/v1/autopilot/daily")
    def run_daily(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        status, data = api_app.dispatch("POST", "/api/v1/autopilot/daily", body=payload)
        if status >= 400:
            raise HTTPException(status_code=status, detail=data.get("error", "Autopilot error"))
        return data

    return fapp


def make_stdlib_http_server(
    api_app: StudioAPIApp,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> ThreadingHTTPServer:
    """Create a zero-dependency ThreadingHTTPServer serving StudioAPIApp JSON endpoints."""

    class _Handler(BaseHTTPRequestHandler):
        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            length = int(self.headers.get("Content-Length", "0") or "0")
            body: dict[str, Any] = {}
            if length > 0:
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    body = {}
            status, response_data = api_app.dispatch(
                method,
                parsed.path,
                body=body,
                query=query,
            )
            encoded = json.dumps(response_data, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return ThreadingHTTPServer((host, port), _Handler)
