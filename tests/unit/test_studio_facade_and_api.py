"""Unit tests for the StudioFacade service boundary and HTTP/FastAPI skeleton."""

from __future__ import annotations

from pathlib import Path

from youtube_studio.api.app import create_api_app
from youtube_studio.domain.services.studio_facade import StudioFacade


def test_studio_facade_and_api_endpoints(tmp_path: Path, monkeypatch) -> None:
    """Verify StudioFacade and StudioAPIApp expose health, channels, projects, script/voice, and daily autopilot."""
    monkeypatch.setenv("YAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("YAS_DEFAULT_OUTPUT_ROOT", str(tmp_path / "output"))

    from youtube_studio.storage import reset_engine

    reset_engine()

    api = create_api_app(run_mode="desktop_local")

    # 1. Health endpoint
    status, health = api.dispatch("GET", "/api/v1/health")
    assert status == 200
    assert health["status"] == "ok"
    assert health["run_mode"] == "desktop_local"
    assert "counts" in health

    # 2. Presets endpoint
    status, presets = api.dispatch("GET", "/api/v1/presets")
    assert status == 200
    assert len(presets["niche_style_presets"]) >= 5
    assert len(presets["voice_library_presets"]) >= 4

    # 3. Create / ensure channel via API
    status, ch_resp = api.dispatch(
        "POST",
        "/api/v1/channels",
        body={
            "name": "Echoes of Livity",
            "niche_preset": "roots_reggae_mix",
            "preferred_voice_preset": "warm_male_narrator",
        },
    )
    assert status == 200
    assert ch_resp["channel"]["name"] == "Echoes of Livity"

    status, ch_list = api.dispatch("GET", "/api/v1/channels")
    assert status == 200
    assert any(c["name"] == "Echoes of Livity" for c in ch_list["channels"])

    # 4. Score titles endpoint
    status, scored = api.dispatch(
        "POST",
        "/api/v1/titles/score",
        body={
            "project_name": "Roots Reggae & Dub Session",
            "channel_name": "Echoes of Livity",
            "niche_preset": "roots_reggae_mix",
        },
    )
    assert status == 200
    assert len(scored["ranked_candidates"]) == 5
    assert scored["highest_scoring_title"]["total_score"] > 0

    # 5. Structured script endpoint
    status, script_data = api.dispatch(
        "POST",
        "/api/v1/script/generate",
        body={
            "topic": "Roots Reggae Vinyl Session",
            "channel_name": "Echoes of Livity",
            "target_duration_minutes": 15,
        },
    )
    assert status == 200
    assert script_data["hook"]
    assert script_data["full_script"]
    assert len(script_data["extracted_chapters"]) >= 2

    # 6. Voiceover synthesis endpoint
    status, vo_data = api.dispatch(
        "POST",
        "/api/v1/voiceover/synthesize",
        body={
            "text": "Welcome to Echoes of Livity roots reggae vinyl session.",
            "preset_key": "warm_male_narrator",
            "speed": 1.0,
        },
    )
    assert status == 200
    assert Path(vo_data["output_path"]).exists()
    assert vo_data["duration_ms"] > 0

    # 7. Locked Daily Channel Autopilot endpoint (personal workflow for Echoes of Livity)
    status, ap_res = api.dispatch(
        "POST",
        "/api/v1/autopilot/daily",
        body={
            "channel_name": "Echoes of Livity",
            "niche_preset": "roots_reggae_mix",
            "voice_preset": "warm_male_narrator",
            "synthesize_voiceover": True,
            "target_duration_minutes": 30,
            "render_video": False,
            "export_short": False,
        },
    )
    assert status == 200
    assert ap_res["channel_name"] == "Echoes of Livity"
    assert ap_res["track_count"] >= 1
    assert Path(ap_res["thumbnail_path"]).exists()
    assert Path(ap_res["nle_fcpxml_path"]).exists()

    # 8. List & inspect project via API
    status, projs = api.dispatch("GET", "/api/v1/projects")
    assert status == 200
    assert len(projs["projects"]) >= 1

    project_id = ap_res["project_id"]
    status, proj_detail = api.dispatch("GET", f"/api/v1/projects/{project_id}")
    assert status == 200
    assert proj_detail["project"]["id"] == project_id
    assert proj_detail["project"]["chapters"][0]["timestamp"] == "00:00"
    assert proj_detail["project"]["metadata_draft"] is not None
