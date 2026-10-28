"""Channel profile models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from youtube_studio.domain.models._compat import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class NicheStylePreset(BaseModel):
    """Named niche & production style preset that configures aspect ratio, palette, visualizer, tone, and target duration."""

    key: str
    label: str
    description: str
    default_aspect_ratio: str = "16:9"
    default_resolution: str = "1920x1080"
    visual_style: str = "vintage_roots"
    visualizer_style: str = "bar_spectrum"
    metadata_tone: str = "warm, authentic studio session"
    target_duration_minutes: int = 60
    default_project_type: str = "mix"
    default_tags: list[str] = Field(default_factory=list)


NICHE_STYLE_PRESETS: dict[str, NicheStylePreset] = {
    "roots_reggae_mix": NicheStylePreset(
        key="roots_reggae_mix",
        label="Roots Reggae & Dub Sound System Mix (16:9)",
        description="Warm analog roots & dub aesthetic with bass-swap EQ transitions and bar spectrum visualizer.",
        default_aspect_ratio="16:9",
        default_resolution="1920x1080",
        visual_style="vintage_roots",
        visualizer_style="bar_spectrum",
        metadata_tone="warm, conscious roots reggae & dub sound system session",
        target_duration_minutes=60,
        default_project_type="mix",
        default_tags=["roots reggae", "dub mix", "sound system", "vinyl session", "conscious reggae"],
    ),
    "midnight_bass_visualizer": NicheStylePreset(
        key="midnight_bass_visualizer",
        label="Midnight Bass & Electronic Club Mix (16:9)",
        description="High-contrast neon midnight palette with mirrored stereo spectrum and club mix pacing.",
        default_aspect_ratio="16:9",
        default_resolution="1920x1080",
        visual_style="midnight_dub",
        visualizer_style="mirrored_stereo",
        metadata_tone="deep, hypnotic late-night electronic & bass club session",
        target_duration_minutes=45,
        default_project_type="mix",
        default_tags=["bass mix", "electronic mix", "deep dub", "club session", "harmonic mix"],
    ),
    "album_vinyl_visualizer": NicheStylePreset(
        key="album_vinyl_visualizer",
        label="Full Album / EP Vinyl Visualizer (16:9)",
        description="Warm earth audiophile presentation with oscilloscope waveform and full tracklist chapters.",
        default_aspect_ratio="16:9",
        default_resolution="1920x1080",
        visual_style="warm_earth",
        visualizer_style="dub_oscilloscope",
        metadata_tone="curated audiophile full-album listening session",
        target_duration_minutes=40,
        default_project_type="album",
        default_tags=["full album", "vinyl session", "official audio", "album stream"],
    ),
    "documentary_storytelling": NicheStylePreset(
        key="documentary_storytelling",
        label="Documentary & Music History Essay (16:9)",
        description="Clean modern editorial style with narrative hook, structured chapter outline, and script.",
        default_aspect_ratio="16:9",
        default_resolution="1920x1080",
        visual_style="modern_clean",
        visualizer_style="line_wave",
        metadata_tone="engaging, researched music history documentary & cultural essay",
        target_duration_minutes=15,
        default_project_type="compilation",
        default_tags=["music documentary", "video essay", "music history", "deep dive"],
    ),
    "vertical_shorts_reel": NicheStylePreset(
        key="vertical_shorts_reel",
        label="Vertical 9:16 Shorts / Highlight Reel",
        description="Punchy 1080x1920 vertical format optimized for 30–60s peak-energy highlights.",
        default_aspect_ratio="9:16",
        default_resolution="1080x1920",
        visual_style="warm_earth",
        visualizer_style="bar_spectrum",
        metadata_tone="high-retention vertical highlight clip",
        target_duration_minutes=1,
        default_project_type="promo_clip",
        default_tags=["shorts", "music highlight", "sound system", "vertical mix"],
    ),
}


class VoicePreset(BaseModel):
    """Local-first voice preset (gender, speed, style, and native OS voice identifier)."""

    key: str
    label: str
    gender: str  # "male" | "female"
    default_speed: float = 1.0  # 0.5 to 2.0 multiplier
    base_wpm: int = 165
    macos_voice: str = "Daniel"
    pitch_hz: float = 135.0
    description: str = ""


VOICE_LIBRARY_PRESETS: dict[str, VoicePreset] = {
    "warm_male_narrator": VoicePreset(
        key="warm_male_narrator",
        label="Warm Male Narrator (Studio Documentary)",
        gender="male",
        default_speed=1.0,
        base_wpm=160,
        macos_voice="Daniel",
        pitch_hz=125.0,
        description="Rich, steady male narration suited for documentaries, intros, and tracklist commentary.",
    ),
    "clear_female_storyteller": VoicePreset(
        key="clear_female_storyteller",
        label="Clear Female Storyteller (Editorial & Essay)",
        gender="female",
        default_speed=1.0,
        base_wpm=165,
        macos_voice="Samantha",
        pitch_hz=210.0,
        description="Crisp, engaging female voice ideal for cultural essays, hooks, and chapter introductions.",
    ),
    "deep_radio_host": VoicePreset(
        key="deep_radio_host",
        label="Deep Sound System / Radio Host (Male)",
        gender="male",
        default_speed=0.95,
        base_wpm=150,
        macos_voice="Alex",
        pitch_hz=110.0,
        description="Deep late-night radio host delivery for roots reggae, dub, and electronic mix sessions.",
    ),
    "calm_documentary_female": VoicePreset(
        key="calm_documentary_female",
        label="Calm Documentary Guide (Female)",
        gender="female",
        default_speed=0.95,
        base_wpm=152,
        macos_voice="Karen",
        pitch_hz=195.0,
        description="Measured, atmospheric female narration for album visualizers and deep-dive storytelling.",
    ),
    "energetic_mc_male": VoicePreset(
        key="energetic_mc_male",
        label="Upbeat Promo / Shorts Announcer (Male)",
        gender="male",
        default_speed=1.10,
        base_wpm=180,
        macos_voice="Fred",
        pitch_hz=145.0,
        description="Fast-paced, punchy delivery for 9:16 vertical Shorts hooks and release promos.",
    ),
}


class ChannelBrandConfig(BaseModel):
    """Brand and production defaults for a channel."""

    preferred_language: str = "en"
    default_aspect_ratio: str = "16:9"  # or "9:16"
    default_resolution: str = "1920x1080"
    visual_style: str = "vintage_roots"
    niche_preset: str = "roots_reggae_mix"
    target_duration_minutes: int = 60
    reference_image_path: Optional[str] = None
    style_lock: bool = False
    preferred_voice_preset: str = "warm_male_narrator"
    voice_speed: float = 1.0
    metadata_template: dict[str, Any] = Field(default_factory=dict)
    thumbnail_style: dict[str, Any] = Field(default_factory=dict)
    intro_outro_enabled: bool = False
    default_tags: list[str] = Field(default_factory=list)


def apply_niche_preset_to_brand_config(
    preset_key: str,
    existing: Optional[ChannelBrandConfig] = None,
) -> ChannelBrandConfig:
    """Apply a named NicheStylePreset to a ChannelBrandConfig while preserving custom reference image locks."""
    preset = NICHE_STYLE_PRESETS.get(preset_key) or NICHE_STYLE_PRESETS["roots_reggae_mix"]
    cfg = existing.model_copy(deep=True) if existing is not None else ChannelBrandConfig()
    cfg.niche_preset = preset.key
    cfg.default_aspect_ratio = preset.default_aspect_ratio
    cfg.default_resolution = preset.default_resolution
    cfg.visual_style = preset.visual_style
    cfg.target_duration_minutes = preset.target_duration_minutes
    cfg.default_tags = list(dict.fromkeys(list(preset.default_tags) + list(cfg.default_tags)))
    tmpl = dict(cfg.metadata_template or {})
    tmpl["tone"] = preset.metadata_tone
    tmpl["visualizer_style"] = preset.visualizer_style
    tmpl["default_project_type"] = preset.default_project_type
    cfg.metadata_template = tmpl
    return cfg


class Channel(BaseModel):
    """Local channel profile – independent branding, libraries, and settings."""

    id: str = Field(default_factory=_new_id)
    name: str
    platform_channel_id: Optional[str] = None  # YouTube channel ID once connected
    brand_config: ChannelBrandConfig = Field(default_factory=ChannelBrandConfig)
    default_output_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    archived_at: Optional[datetime] = None

    def touch(self) -> None:
        self.updated_at = _utcnow()

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None
