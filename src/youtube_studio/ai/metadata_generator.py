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
class TitleCandidateScore:
    """Transparent, explainable rule-based evaluation of a title candidate (never a fake CTR score)."""

    title: str
    total_score: int
    length_score: int
    keyword_score: int
    brand_fit_score: int
    length_ok: bool
    matched_keywords: list[str] = field(default_factory=list)
    matches_channel_tone: bool = True
    explanation: str = ""


@dataclass
class ScriptDraftResult:
    """Structured Hook -> Outline -> Full Script output timed to a target video duration."""

    hook: str
    outline: str
    full_script: str
    target_duration_minutes: int
    estimated_word_count: int
    extracted_chapters: list[ChapterEntry] = field(default_factory=list)


@dataclass
class MetadataGenerationRequest:
    project_name: str
    project_type: ProjectType = ProjectType.MIX
    channel_name: str = "YouTube Automation Studio"
    brand_config: ChannelBrandConfig = field(default_factory=ChannelBrandConfig)
    chapters: list[ChapterEntry] = field(default_factory=list)
    research_brief: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    target_duration_minutes: int = 60
    script_text: Optional[str] = None
    candidate_count: int = 3


@dataclass
class GeneratedMetadataResult:
    title: str
    title_candidates: list[str]
    description: str
    tags: list[str]
    chapters: list[ChapterEntry]
    adapter_used: str
    provenance: dict[str, Any] = field(default_factory=dict)
    scored_candidates: list[TitleCandidateScore] = field(default_factory=list)
    highest_scoring_title: Optional[TitleCandidateScore] = None


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
        scored = self.rank_title_candidates(req, extra_candidates=candidates)
        best_scored = scored[0] if scored else None
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
                "scoring_method": "transparent_rule_rubric_v1",
            },
            scored_candidates=scored,
            highest_scoring_title=best_scored,
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
            cls._clamp_title(
                f"{base} — {type_label} ({req.target_duration_minutes} Min Session) | {req.channel_name}"
            ),
            cls._clamp_title(
                f"{req.channel_name}: {base} [{', '.join(t.title() for t in (req.keywords or req.brand_config.default_tags)[:2]) or type_label}]"
            ),
        ]
        for t in template_titles:
            if t not in raw_candidates:
                raw_candidates.append(t)
        limit = max(3, int(req.candidate_count or 3))
        return raw_candidates[:limit]

    @classmethod
    def score_title_candidate(
        cls,
        title: str,
        req: MetadataGenerationRequest,
    ) -> TitleCandidateScore:
        """Score a title using transparent, explainable rules (length, seed keywords, brand/format fit)."""
        clean = title.strip()
        char_len = len(clean)
        length_ok = 25 <= char_len <= MAX_YOUTUBE_TITLE_LENGTH

        if 42 <= char_len <= 78:
            length_score = 35
        elif 28 <= char_len <= 92:
            length_score = 28
        elif 15 <= char_len <= MAX_YOUTUBE_TITLE_LENGTH:
            length_score = 18
        else:
            length_score = 5

        lower_title = clean.lower()
        seed_pool: list[str] = []
        for kw in list(req.keywords) + list(req.brand_config.default_tags):
            k_clean = kw.strip().lower()
            if k_clean and k_clean not in seed_pool:
                seed_pool.append(k_clean)
        for token in re.findall(r"[a-zA-Z0-9]{4,}", req.project_name.lower()):
            if token not in seed_pool:
                seed_pool.append(token)

        matched_kw = [kw for kw in seed_pool if kw in lower_title]
        if len(matched_kw) >= 3:
            keyword_score = 35
        elif len(matched_kw) == 2:
            keyword_score = 28
        elif len(matched_kw) == 1:
            keyword_score = 20
        else:
            keyword_score = 10

        brand_fit_score = 10
        matches_tone = False
        if req.channel_name and req.channel_name.lower() in lower_title:
            brand_fit_score += 10
            matches_tone = True
        format_markers = ("mix", "session", "album", "audio", "dub", "reggae", "documentary", "|", "—", "–", "(")
        if any(m in lower_title for m in format_markers):
            brand_fit_score += 10
            matches_tone = True
        brand_fit_score = min(30, brand_fit_score)

        total = min(100, length_score + keyword_score + brand_fit_score)
        reasons = [
            f"Length OK ({char_len} chars)" if length_ok else f"Length ({char_len} chars)",
            f"Keywords ({len(matched_kw)} matched)" if matched_kw else "Keywords (base title)",
            "Matches channel tone" if matches_tone else "Standard format",
        ]
        return TitleCandidateScore(
            title=clean,
            total_score=total,
            length_score=length_score,
            keyword_score=keyword_score,
            brand_fit_score=brand_fit_score,
            length_ok=length_ok,
            matched_keywords=matched_kw[:5],
            matches_channel_tone=matches_tone,
            explanation=" · ".join(reasons),
        )

    @classmethod
    def rank_title_candidates(
        cls,
        req: MetadataGenerationRequest,
        *,
        extra_candidates: Optional[list[str]] = None,
    ) -> list[TitleCandidateScore]:
        """Generate 5 title options and rank them highest-first by transparent rule criteria."""
        req_five = MetadataGenerationRequest(
            project_name=req.project_name,
            project_type=req.project_type,
            channel_name=req.channel_name,
            brand_config=req.brand_config,
            chapters=req.chapters,
            research_brief=req.research_brief,
            keywords=req.keywords,
            target_duration_minutes=req.target_duration_minutes,
            script_text=req.script_text,
            candidate_count=5,
        )
        pool = list(extra_candidates or [])
        for cand in cls._build_title_candidates(req_five, None):
            if cand not in pool:
                pool.append(cand)
        scored = [cls.score_title_candidate(c, req_five) for c in pool]
        scored.sort(key=lambda s: s.total_score, reverse=True)
        return scored

    # ------------------------------------------------------------------
    # Structured Hook -> Outline -> Full Script & Script Paste/Upload
    # ------------------------------------------------------------------

    def generate_hook(
        self,
        topic: str,
        *,
        channel_name: str = "Studio Channel",
        tone: str = "warm, authentic studio session",
        target_duration_minutes: int = 15,
    ) -> str:
        """Step 1: Generate an engaging opening hook (first 15 seconds) tailored to the channel tone."""
        clean_topic = topic.strip() or "Featured Session"
        return (
            f"[00:00 — OPENING HOOK ({tone})]\n"
            f"Welcome back to {channel_name}. In the next {target_duration_minutes} minutes, "
            f"we are diving deep into {clean_topic} — exploring the sonic architecture, "
            f"harmonic transitions, and essential selections that define this sound."
        )

    def generate_outline(
        self,
        topic: str,
        *,
        hook: str = "",
        chapters: Optional[list[ChapterEntry]] = None,
        target_duration_minutes: int = 15,
    ) -> str:
        """Step 2: Build a timestamped section outline from the hook, chapters, and target video length."""
        clean_topic = topic.strip() or "Featured Session"
        lines = [
            f"=== Structured Outline: {clean_topic} (Target: {target_duration_minutes} min) ===",
            "1. 00:00 — Opening Hook & Sonic Premise",
        ]
        if chapters:
            for idx, ch in enumerate(chapters, start=2):
                lines.append(f"{idx}. {ch.format_timestamp()} — {ch.title}")
        else:
            mid_min = max(1, target_duration_minutes // 3)
            peak_min = max(2, (target_duration_minutes * 2) // 3)
            end_min = max(3, target_duration_minutes - 1)
            lines.extend(
                [
                    f"2. {mid_min:02d}:00 — Core Groove & Harmonic Progression",
                    f"3. {peak_min:02d}:00 — Peak Energy Selection & Bass-Swap Transition",
                    f"4. {end_min:02d}:00 — Closing Resolution & Listener Call-to-Action",
                ]
            )
        return "\n".join(lines)

    def generate_structured_script(
        self,
        topic: str,
        *,
        channel_name: str = "Studio Channel",
        tone: str = "warm, authentic studio session",
        chapters: Optional[list[ChapterEntry]] = None,
        target_duration_minutes: int = 15,
        custom_hook: Optional[str] = None,
        custom_outline: Optional[str] = None,
    ) -> ScriptDraftResult:
        """Step 3: Generate Hook -> Outline -> Full Narration/Host Script timed to target_duration_minutes."""
        hook = (custom_hook or "").strip() or self.generate_hook(
            topic,
            channel_name=channel_name,
            tone=tone,
            target_duration_minutes=target_duration_minutes,
        )
        outline = (custom_outline or "").strip() or self.generate_outline(
            topic,
            hook=hook,
            chapters=chapters,
            target_duration_minutes=target_duration_minutes,
        )

        body_sections = [
            hook,
            "",
            outline,
            "",
            "=== FULL NARRATION / HOST SCRIPT ===",
            f"[INTRO — 00:00]\n{hook.splitlines()[-1]}",
        ]
        if chapters:
            for ch in chapters:
                body_sections.append(
                    f"\n[{ch.format_timestamp()} — {ch.title}]\n"
                    f"Up next at {ch.format_timestamp()}, we lock into '{ch.title}'. "
                    f"Notice how the bassline and rhythm section carry the {tone} atmosphere forward."
                )
        else:
            body_sections.append(
                f"\n[MAIN SEGMENT — 02:00]\n"
                f"Throughout '{topic}', each transition is shaped to preserve low-end clarity and harmonic flow."
            )

        body_sections.append(
            f"\n[OUTRO — {max(1, target_duration_minutes - 1):02d}:00]\n"
            f"Thank you for tuning in to {channel_name}. If you felt this session, "
            f"drop your favorite timestamp in the comments and subscribe for the next release."
        )
        full_script = "\n".join(body_sections)
        extracted_ch, _ = self.parse_script_text(full_script)
        word_count = len(re.findall(r"\S+", full_script))
        return ScriptDraftResult(
            hook=hook,
            outline=outline,
            full_script=full_script,
            target_duration_minutes=target_duration_minutes,
            estimated_word_count=word_count,
            extracted_chapters=extracted_ch,
        )

    @staticmethod
    def parse_script_text(raw_script: str) -> tuple[list[ChapterEntry], list[str]]:
        """Extract ChapterEntry items (from 00:00 timestamps) and clean narration paragraphs from a pasted/uploaded script."""
        chapters: list[ChapterEntry] = []
        paragraphs: list[str] = []
        if not raw_script:
            return chapters, paragraphs

        ts_pattern = re.compile(r"(?:\[)?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\])?\s*[-–—:|]?\s*(.+)")
        for line in raw_script.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            m = ts_pattern.search(stripped)
            if m:
                hh = int(m.group(1) or 0)
                mm = int(m.group(2) or 0)
                ss = int(m.group(3) or 0)
                label = m.group(4).strip(" ]—-:")
                start_ms = ((hh * 3600) + (mm * 60) + ss) * 1000
                if label and not any(c.start_ms == start_ms for c in chapters):
                    chapters.append(ChapterEntry(start_ms=start_ms, title=label[:80]))
            if not stripped.startswith("==="):
                paragraphs.append(stripped)

        if chapters and chapters[0].start_ms != 0:
            chapters.insert(0, ChapterEntry(start_ms=0, title="Intro"))
        return chapters, paragraphs

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
