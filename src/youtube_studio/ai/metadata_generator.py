"""YouTube title, description, chapter, and tag generation with local LM + template fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from youtube_studio.ai.text_adapter import (
    TemplateFallbackTextAdapter,
    TextGenerationAdapter,
)
from youtube_studio.domain.models.channel import ChannelBrandConfig
from youtube_studio.domain.models.project import ChapterEntry, ProjectType

MAX_YOUTUBE_TITLE_LENGTH = 100
MAX_YOUTUBE_TAGS_TOTAL_CHARS = 500


@dataclass
class MetadataGenerationRequest:
    project_name: str
    project_type: ProjectType = ProjectType.MIX
    channel_name: str = "YouTube Automation Studio"
    brand_config: ChannelBrandConfig = field(default_factory=ChannelBrandConfig)
    chapters: list[ChapterEntry] = field(default_factory=list)
    research_brief: Optional[str] = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class GeneratedMetadataResult:
    title: str
    title_candidates: list[str]
    description: str
    tags: list[str]
    chapters: list[ChapterEntry]
    adapter_used: str
    provenance: dict[str, Any] = field(default_factory=dict)


class MetadataGenerator:
    """Generates YouTube titles, descriptions, chapters, and tags using a local LM or template fallback."""

    def __init__(
        self,
        *,
        primary_adapter: Optional[TextGenerationAdapter] = None,
        fallback_adapter: Optional[TextGenerationAdapter] = None,
    ) -> None:
        self._primary = primary_adapter
        self._fallback = fallback_adapter or TemplateFallbackTextAdapter()

    def generate(self, req: MetadataGenerationRequest) -> GeneratedMetadataResult:
        adapter = (
            self._primary
            if (self._primary is not None and self._primary.is_available())
            else self._fallback
        )

        used_name = adapter.name
        llm_data: Optional[dict[str, Any]] = None

        if adapter.name != "template_fallback":
            try:
                raw_text = adapter.generate(
                    self._build_prompt(req),
                    system_prompt=(
                        "Return valid JSON with keys: 'title_candidates' (list of 3 strings <=100 chars), "
                        "'intro_paragraph' (string), and 'extra_tags' (list of strings)."
                    ),
                    max_tokens=400,
                    temperature=0.6,
                )
                llm_data = self._try_parse_json(raw_text)
            except Exception:
                used_name = self._fallback.name
                llm_data = None

        candidates = self._build_title_candidates(req, llm_data)
        primary_title = candidates[0]
        tags = self._build_tags(req, llm_data)
        description = self._build_description(req, primary_title, tags, llm_data)

        return GeneratedMetadataResult(
            title=primary_title,
            title_candidates=candidates,
            description=description,
            tags=tags,
            chapters=list(req.chapters),
            adapter_used=used_name,
            provenance={
                "adapter": used_name,
                "visual_style": req.brand_config.visual_style,
                "language": req.brand_config.preferred_language,
            },
        )

    @staticmethod
    def _build_prompt(req: MetadataGenerationRequest) -> str:
        kw_str = ", ".join(req.keywords + req.brand_config.default_tags)
        return (
            f"Project: {req.project_name}\n"
            f"Channel: {req.channel_name}\n"
            f"Type: {req.project_type.value}\n"
            f"Style: {req.brand_config.visual_style}\n"
            f"Keywords: {kw_str}\n"
            f"Brief: {req.research_brief or 'N/A'}\n"
        )

    @staticmethod
    def _try_parse_json(text: str) -> Optional[dict[str, Any]]:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    @classmethod
    def _build_title_candidates(
        cls,
        req: MetadataGenerationRequest,
        llm_data: Optional[dict[str, Any]],
    ) -> list[str]:
        raw_candidates: list[str] = []
        if llm_data and isinstance(llm_data.get("title_candidates"), list):
            for c in llm_data["title_candidates"]:
                if isinstance(c, str) and c.strip():
                    raw_candidates.append(cls._clamp_title(c.strip()))

        base = req.project_name.strip() or "Untitled Session"
        type_label = {
            ProjectType.MIX: "Full Mix",
            ProjectType.SINGLE_TRACK: "Official Audio",
            ProjectType.COMPILATION: "Compilation",
            ProjectType.ALBUM: "Full Album",
            ProjectType.PROMO_CLIP: "Short Mix",
        }.get(req.project_type, "Session")

        template_titles = [
            cls._clamp_title(base),
            cls._clamp_title(f"{base} | {req.channel_name} ({type_label})"),
            cls._clamp_title(
                f"{base} – {req.brand_config.default_tags[0].title() if req.brand_config.default_tags else type_label}"
            ),
        ]
        for t in template_titles:
            if t not in raw_candidates:
                raw_candidates.append(t)
        return raw_candidates[:3]

    @staticmethod
    def _clamp_title(title: str) -> str:
        if len(title) <= MAX_YOUTUBE_TITLE_LENGTH:
            return title
        return title[: MAX_YOUTUBE_TITLE_LENGTH - 1].rstrip() + "…"

    @staticmethod
    def _build_tags(
        req: MetadataGenerationRequest,
        llm_data: Optional[dict[str, Any]],
    ) -> list[str]:
        pool: list[str] = []
        pool.extend(req.brand_config.default_tags)
        pool.extend(req.keywords)
        if llm_data and isinstance(llm_data.get("extra_tags"), list):
            pool.extend(str(t) for t in llm_data["extra_tags"] if str(t).strip())

        # Extract salient words from project name
        for word in re.findall(r"[a-zA-Z0-9]{4,}", req.project_name.lower()):
            pool.append(word)

        deduped: list[str] = []
        seen: set[str] = set()
        total_chars = 0
        for tag in pool:
            cleaned = tag.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            cost = len(cleaned) + (1 if deduped else 0)
            if total_chars + cost > MAX_YOUTUBE_TAGS_TOTAL_CHARS:
                break
            deduped.append(cleaned)
            seen.add(cleaned)
            total_chars += cost
        return deduped

    @staticmethod
    def _build_description(
        req: MetadataGenerationRequest,
        title: str,
        tags: list[str],
        llm_data: Optional[dict[str, Any]],
    ) -> str:
        tmpl = req.brand_config.metadata_template or {}
        header = str(tmpl.get("header") or f"{title} — presented by {req.channel_name}.")
        intro = (
            str(llm_data["intro_paragraph"]).strip()
            if llm_data and isinstance(llm_data.get("intro_paragraph"), str) and llm_data["intro_paragraph"].strip()
            else (req.research_brief.strip() if req.research_brief else "")
        )

        sections: list[str] = [header]
        if intro:
            sections.append(intro)

        if req.chapters:
            chapter_lines = ["Tracklist / Chapters:"]
            for ch in req.chapters:
                chapter_lines.append(f"{ch.format_timestamp()} {ch.title}")
            sections.append("\n".join(chapter_lines))

        footer = str(
            tmpl.get("footer")
            or f"Subscribe to {req.channel_name} for more sessions."
        )
        sections.append(footer)

        if tags:
            hashtags = " ".join(
                "#" + re.sub(r"[^a-z0-9]", "", t.lower()) for t in tags[:5] if re.sub(r"[^a-z0-9]", "", t.lower())
            )
            if hashtags:
                sections.append(hashtags)

        return "\n\n".join(sections)
