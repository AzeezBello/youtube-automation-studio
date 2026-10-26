"""Unit tests for P3 local AI adapters, metadata generator, artwork generator, and model hardware checks."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

from youtube_studio.ai.image_adapter import (
    ArtworkGenerator,
    DiffusersImageAdapter,
    ProceduralArtworkFallbackAdapter,
)
from youtube_studio.ai.metadata_generator import (
    MetadataGenerationRequest,
    MetadataGenerator,
)
from youtube_studio.ai.text_adapter import (
    LlamaCppTextAdapter,
    TemplateFallbackTextAdapter,
)
from youtube_studio.config.hardware import HardwareReport
from youtube_studio.config.settings import ResourceProfile
from youtube_studio.domain.models.ai import RegisteredModel
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.project import ChapterEntry, ProjectType
from youtube_studio.media.validator import MediaValidator


def test_model_hardware_compatibility_check():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        weight_file = root / "qwen-3b-instruct.gguf"
        weight_file.write_bytes(b"0" * 1024)

        hw = HardwareReport(
            os_name="Darwin",
            os_version="24.6.0",
            architecture="x86_64",
            cpu_count=8,
            total_ram_gb=16.0,
            free_disk_gb=50.0,
            has_ffmpeg_hwaccel=False,
            cpu_hash_mb_per_sec=400.0,
            recommended_profile=ResourceProfile.HIGH_PERFORMANCE,
        )

        # 1. Small/medium 4 GB model on 16 GB system -> compatible
        m_ok = RegisteredModel(
            name="qwen-3b",
            path=str(weight_file),
            size_bytes=4 * (1024**3),
        )
        ok, note = m_ok.check_hardware_compatibility(total_ram_gb=hw.total_ram_gb)
        assert ok is True
        assert "Compatible" in note

        # 2. Huge 32 GB model on 16 GB system -> rejected
        m_big = RegisteredModel(
            name="llama-70b",
            path=str(weight_file),
            size_bytes=32 * (1024**3),
        )
        ok_big, note_big = m_big.check_hardware_compatibility(total_ram_gb=hw.total_ram_gb)
        assert ok_big is False
        assert "exceeding safe budget" in note_big


def test_metadata_generator_with_local_lm_and_template_fallback():
    chapters = [
        ChapterEntry(start_ms=0, title="King Tubby - Dub Opening"),
        ChapterEntry(start_ms=185_000, title="Scientist - Heavyweight Steppers"),
    ]
    req = MetadataGenerationRequest(
        project_name="Echoes of Livity – Heavyweight Dub Session Vol. 4",
        project_type=ProjectType.MIX,
        channel_name="Echoes of Livity",
        brand_config=ChannelBrandConfig(
            default_tags=["roots reggae", "dub", "sound system"],
            visual_style="vintage_roots",
        ),
        chapters=chapters,
        research_brief="Late-70s analogue dub mix recorded on 4-track tape.",
        keywords=["king tubby", "steppers"],
    )

    # 1. Template fallback when no local LM is configured
    gen_fallback = MetadataGenerator()
    res_fb = gen_fallback.generate(req)
    assert res_fb.adapter_used == "template_fallback"
    assert len(res_fb.title) <= 100
    assert len(res_fb.title_candidates) == 3
    assert "00:00 King Tubby - Dub Opening" in res_fb.description
    assert "03:05 Scientist - Heavyweight Steppers" in res_fb.description
    assert "roots reggae" in res_fb.tags
    assert "steppers" in res_fb.tags

    # 2. Local instruction-following LM adapter via completion_fn
    def fake_llm_completion(
        _prompt: str,
        _sys: Optional[str],
        _max_tok: int,
        _temp: float,
    ) -> str:
        return json.dumps(
            {
                "title_candidates": [
                    "Heavyweight 1970s Dubplate Mix | Echoes of Livity Vol. 4",
                    "Echoes of Livity: Analogue Roots & Steppers Session",
                    "King Tubby & Scientist Era Dub Mix (Vinyl Selection)",
                ],
                "intro_paragraph": "Deep 1970s analogue dubplates mixed live with spring reverb and tape delay.",
                "extra_tags": ["vinyl dub mix", "analogue dub"],
            }
        )

    lm_adapter = LlamaCppTextAdapter(completion_fn=fake_llm_completion)
    gen_lm = MetadataGenerator(primary_adapter=lm_adapter)
    res_lm = gen_lm.generate(req)
    assert res_lm.adapter_used == "llama_cpp"
    assert res_lm.title == "Heavyweight 1970s Dubplate Mix | Echoes of Livity Vol. 4"
    assert "spring reverb and tape delay" in res_lm.description
    assert "vinyl dub mix" in res_lm.tags


def test_artwork_generator_diffusion_and_procedural_fallback():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1. Default procedural fallback when local image diffusion is disabled
        art_gen = ArtworkGenerator()
        out_fb = root / "fallback_thumb.png"
        res_fb = art_gen.generate(
            "Roots & Culture Session",
            out_fb,
            width=1280,
            height=720,
            style_palette="vintage_roots",
            subtitle="Echoes of Livity",
            badge_text="MIX",
        )
        assert res_fb.adapter_used == "procedural_template_fallback"
        assert res_fb.output_path.exists()
        assert MediaValidator().validate_image(out_fb, expected_width=1280, expected_height=720).is_valid

        # 2. Enabled local diffusion adapter via pipeline_fn
        def fake_diffusion_pipeline(
            prompt: str,
            output_path: Path,
            width: int,
            height: int,
            seed: Optional[int],
        ) -> None:
            # Render via procedural engine to produce a valid PNG for the test
            ProceduralArtworkFallbackAdapter().generate_image(
                prompt, output_path, width=width, height=height, seed=seed
            )

        diff_adapter = DiffusersImageAdapter(
            enable_override=True,
            pipeline_fn=fake_diffusion_pipeline,
        )
        art_gen_diff = ArtworkGenerator(primary_adapter=diff_adapter)
        out_diff = root / "diff_thumb.png"
        res_diff = art_gen_diff.generate(
            "Roots & Culture Session",
            out_diff,
            width=1280,
            height=720,
            seed=42,
        )
        assert res_diff.adapter_used == "local_diffusers"
        assert res_diff.provenance["seed"] == 42
        assert len(res_diff.checksum) == 64
