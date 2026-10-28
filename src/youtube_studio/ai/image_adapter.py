"""Optional local image generation adapter with deterministic procedural/template artwork fallback."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from youtube_studio.config import get_settings
from youtube_studio.media.thumbnail import ThumbnailEngine, ThumbnailSpec


@dataclass(frozen=True)
class ImageGenerationResult:
    output_path: Path
    width: int
    height: int
    checksum: str
    adapter_used: str
    provenance: dict[str, Any] = field(default_factory=dict)


PipelineCallable = Callable[[str, Path, int, int, Optional[int]], None]


class ImageGenerationAdapter(ABC):
    """Abstract interface for local artwork / thumbnail generation."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        width: int = 1280,
        height: int = 720,
        style_palette: str = "warm_earth",
        subtitle: Optional[str] = None,
        badge_text: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> ImageGenerationResult:
        ...


class DiffusersImageAdapter(ImageGenerationAdapter):
    """Local diffusion image adapter (enabled when Settings.enable_local_image_gen is True or pipeline_fn provided)."""

    def __init__(
        self,
        model_path: Optional[Path] = None,
        *,
        enable_override: Optional[bool] = None,
        pipeline_fn: Optional[PipelineCallable] = None,
    ) -> None:
        self._model_path = model_path.expanduser().resolve() if model_path else None
        self._enable_override = enable_override
        self._pipeline_fn = pipeline_fn

    @property
    def name(self) -> str:
        return "local_diffusers"

    def is_available(self) -> bool:
        enabled = (
            self._enable_override
            if self._enable_override is not None
            else get_settings().enable_local_image_gen
        )
        if not enabled:
            return False
        if self._pipeline_fn is not None:
            return True
        if self._model_path is None or not self._model_path.exists():
            return False
        try:
            import diffusers  # noqa: F401
            import torch  # noqa: F401

            return True
        except ImportError:
            return False

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        width: int = 1280,
        height: int = 720,
        style_palette: str = "warm_earth",
        subtitle: Optional[str] = None,
        badge_text: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> ImageGenerationResult:
        if not self.is_available():
            raise RuntimeError("DiffusersImageAdapter is not enabled or available on this hardware")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._pipeline_fn is not None:
            self._pipeline_fn(prompt, output_path, width, height, seed)
        else:
            raise RuntimeError("Local diffusion pipeline execution requires a configured pipeline")

        checksum = hashlib.sha256(output_path.read_bytes()).hexdigest()
        return ImageGenerationResult(
            output_path=output_path,
            width=width,
            height=height,
            checksum=checksum,
            adapter_used=self.name,
            provenance={
                "adapter": self.name,
                "prompt": prompt,
                "seed": seed,
                "model_path": str(self._model_path) if self._model_path else None,
            },
        )


class ProceduralArtworkFallbackAdapter(ImageGenerationAdapter):
    """Deterministic template/procedural artwork generator using ThumbnailEngine when local diffusion is disabled."""

    def __init__(self, thumbnail_engine: Optional[ThumbnailEngine] = None) -> None:
        self._engine = thumbnail_engine or ThumbnailEngine()

    @property
    def name(self) -> str:
        return "procedural_template_fallback"

    def is_available(self) -> bool:
        return True

    def generate_image(
        self,
        prompt: str,
        output_path: Path,
        *,
        width: int = 1280,
        height: int = 720,
        style_palette: str = "warm_earth",
        subtitle: Optional[str] = None,
        badge_text: Optional[str] = None,
        seed: Optional[int] = None,
        reference_image_path: Optional[Path] = None,
        style_lock: bool = False,
    ) -> ImageGenerationResult:
        aspect = "9:16" if height > width else "16:9"
        spec = ThumbnailSpec(
            title=prompt.strip() or "Untitled Artwork",
            subtitle=subtitle,
            badge_text=badge_text,
            palette=style_palette,
            aspect_ratio=aspect,
            width=width,
            height=height,
            motif="vinyl_and_sound_system",
            reference_image_path=reference_image_path,
            style_lock=style_lock,
        )
        res = self._engine.render(spec, output_path)
        return ImageGenerationResult(
            output_path=res.output_path,
            width=res.width,
            height=res.height,
            checksum=res.checksum,
            adapter_used=self.name,
            provenance={
                "adapter": self.name,
                "prompt": prompt,
                "palette": res.palette,
                "seed": seed,
                "reference_image_path": str(reference_image_path) if reference_image_path else None,
                "style_lock": style_lock,
            },
        )


class ArtworkGenerator:
    """Orchestrates optional local diffusion artwork generation with guaranteed procedural template fallback."""

    def __init__(
        self,
        *,
        primary_adapter: Optional[ImageGenerationAdapter] = None,
        fallback_adapter: Optional[ImageGenerationAdapter] = None,
    ) -> None:
        self._primary = primary_adapter or DiffusersImageAdapter()
        self._fallback = fallback_adapter or ProceduralArtworkFallbackAdapter()

    def generate(
        self,
        prompt: str,
        output_path: Path,
        *,
        width: int = 1280,
        height: int = 720,
        style_palette: str = "warm_earth",
        subtitle: Optional[str] = None,
        badge_text: Optional[str] = None,
        seed: Optional[int] = None,
        reference_image_path: Optional[Path] = None,
        style_lock: bool = False,
    ) -> ImageGenerationResult:
        if self._primary.is_available():
            try:
                return self._primary.generate_image(
                    prompt,
                    output_path,
                    width=width,
                    height=height,
                    style_palette=style_palette,
                    subtitle=subtitle,
                    badge_text=badge_text,
                    seed=seed,
                )
            except Exception:
                pass
        if isinstance(self._fallback, ProceduralArtworkFallbackAdapter):
            return self._fallback.generate_image(
                prompt,
                output_path,
                width=width,
                height=height,
                style_palette=style_palette,
                subtitle=subtitle,
                badge_text=badge_text,
                seed=seed,
                reference_image_path=reference_image_path,
                style_lock=style_lock,
            )
        return self._fallback.generate_image(
            prompt,
            output_path,
            width=width,
            height=height,
            style_palette=style_palette,
            subtitle=subtitle,
            badge_text=badge_text,
            seed=seed,
        )
