"""Thumbnail and video background layout engine (Pillow + pure-Python PNG fallback)."""

from __future__ import annotations

import hashlib
import struct
import textwrap
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "warm_earth": {
        "bg_top": (42, 27, 18),
        "bg_bottom": (18, 12, 9),
        "accent": (230, 161, 69),
        "secondary": (184, 75, 41),
        "text": (247, 239, 226),
        "muted": (196, 178, 153),
    },
    "vintage_roots": {
        "bg_top": (25, 48, 32),
        "bg_bottom": (12, 22, 15),
        "accent": (235, 190, 62),
        "secondary": (196, 61, 45),
        "text": (245, 242, 232),
        "muted": (175, 191, 172),
    },
    "midnight_dub": {
        "bg_top": (20, 26, 46),
        "bg_bottom": (9, 11, 20),
        "accent": (92, 184, 230),
        "secondary": (150, 98, 224),
        "text": (240, 244, 255),
        "muted": (160, 172, 198),
    },
    "modern_clean": {
        "bg_top": (32, 34, 38),
        "bg_bottom": (16, 17, 20),
        "accent": (255, 90, 95),
        "secondary": (72, 149, 239),
        "text": (250, 250, 252),
        "muted": (175, 180, 190),
    },
}


@dataclass(frozen=True)
class ThumbnailSpec:
    title: str
    subtitle: Optional[str] = None
    badge_text: Optional[str] = None
    palette: str = "warm_earth"
    aspect_ratio: str = "16:9"  # "16:9" or "9:16"
    width: Optional[int] = None
    height: Optional[int] = None
    motif: str = "vinyl_and_sound_system"

    def resolved_dimensions(self) -> tuple[int, int]:
        if self.width and self.height:
            return self.width, self.height
        if self.aspect_ratio == "9:16":
            return 1080, 1920
        return 1280, 720


@dataclass(frozen=True)
class ThumbnailResult:
    output_path: Path
    width: int
    height: int
    checksum: str
    palette: str


class ThumbnailEngine:
    """Renders channel-branded thumbnails and video background canvases."""

    def render(self, spec: ThumbnailSpec, output_path: Path) -> ThumbnailResult:
        if not spec.title or not spec.title.strip():
            raise ValueError("Thumbnail title cannot be empty")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = spec.resolved_dimensions()
        colors = PALETTES.get(spec.palette, PALETTES["warm_earth"])

        try:
            self._render_with_pillow(spec, output_path, width=width, height=height, colors=colors)
        except ImportError:
            self._render_minimal_png(output_path, width=width, height=height, colors=colors)

        checksum = hashlib.sha256(output_path.read_bytes()).hexdigest()
        return ThumbnailResult(
            output_path=output_path,
            width=width,
            height=height,
            checksum=checksum,
            palette=spec.palette if spec.palette in PALETTES else "warm_earth",
        )

    @staticmethod
    def _render_with_pillow(
        spec: ThumbnailSpec,
        output_path: Path,
        *,
        width: int,
        height: int,
        colors: dict[str, tuple[int, int, int]],
    ) -> None:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (width, height), color=colors["bg_bottom"])
        draw = ImageDraw.Draw(img)

        # Vertical gradient background
        top_r, top_g, top_b = colors["bg_top"]
        bot_r, bot_g, bot_b = colors["bg_bottom"]
        for y in range(height):
            t = y / max(1, height - 1)
            r = int(top_r + (bot_r - top_r) * t)
            g = int(top_g + (bot_g - top_g) * t)
            b = int(top_b + (bot_b - top_b) * t)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # Outer border frame
        margin = max(24, min(width, height) // 24)
        draw.rectangle(
            [margin, margin, width - margin, height - margin],
            outline=colors["accent"],
            width=4,
        )

        # Decorative vinyl / sound-system motif on the right (16:9) or bottom (9:16)
        if spec.motif == "vinyl_and_sound_system":
            cx = int(width * 0.78) if width >= height else width // 2
            cy = height // 2 if width >= height else int(height * 0.72)
            max_radius = int(min(width, height) * 0.30)
            for ring in range(max_radius, max_radius // 4, -max(12, max_radius // 10)):
                draw.ellipse(
                    [cx - ring, cy - ring, cx + ring, cy + ring],
                    outline=colors["secondary"] if ring == max_radius else colors["muted"],
                    width=2,
                )
            label_r = max(16, max_radius // 4)
            draw.ellipse(
                [cx - label_r, cy - label_r, cx + label_r, cy + label_r],
                fill=colors["accent"],
            )
            hole_r = max(4, label_r // 5)
            draw.ellipse(
                [cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r],
                fill=colors["bg_bottom"],
            )

        font = ImageFont.load_default()
        text_x = margin * 2
        cursor_y = margin * 2

        if spec.badge_text:
            badge = spec.badge_text.strip().upper()
            pad_x, pad_y = 14, 8
            badge_w = max(80, len(badge) * 9 + pad_x * 2)
            badge_h = 28
            draw.rectangle(
                [text_x, cursor_y, text_x + badge_w, cursor_y + badge_h],
                fill=colors["secondary"],
            )
            draw.text((text_x + pad_x, cursor_y + pad_y), badge, fill=colors["text"], font=font)
            cursor_y += badge_h + 28

        wrapped_title = textwrap.wrap(spec.title.strip(), width=26)
        for line in wrapped_title[:4]:
            draw.text((text_x, cursor_y), line, fill=colors["text"], font=font)
            cursor_y += 28

        if spec.subtitle:
            cursor_y += 12
            for line in textwrap.wrap(spec.subtitle.strip(), width=36)[:3]:
                draw.text((text_x, cursor_y), line, fill=colors["accent"], font=font)
                cursor_y += 22

        img.save(output_path, format="PNG")

    @staticmethod
    def _render_minimal_png(
        output_path: Path,
        *,
        width: int,
        height: int,
        colors: dict[str, tuple[int, int, int]],
    ) -> None:
        """Pure-Python valid RGB PNG fallback with border and gradient."""
        top_r, top_g, top_b = colors["bg_top"]
        bot_r, bot_g, bot_b = colors["bg_bottom"]
        acc_r, acc_g, acc_b = colors["accent"]
        margin = max(8, min(width, height) // 24)

        rows = bytearray()
        for y in range(height):
            rows.append(0)
            t = y / max(1, height - 1)
            r = int(top_r + (bot_r - top_r) * t)
            g = int(top_g + (bot_g - top_g) * t)
            b = int(top_b + (bot_b - top_b) * t)
            is_top_or_bot_border = y in (margin, margin + 1, height - margin - 1, height - margin)
            if is_top_or_bot_border:
                row_bytes = bytes((acc_r, acc_g, acc_b)) * width
            else:
                bg_pixel = bytes((r, g, b))
                acc_pixel = bytes((acc_r, acc_g, acc_b))
                row_bytes = (
                    bg_pixel * margin
                    + acc_pixel * 2
                    + bg_pixel * max(0, width - 2 * margin - 4)
                    + acc_pixel * 2
                    + bg_pixel * margin
                )
                if len(row_bytes) != width * 3:
                    row_bytes = bg_pixel * width
            rows.extend(row_bytes)

        def _chunk(chunk_type: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        compressed = zlib.compress(bytes(rows), level=4)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", compressed)
            + _chunk(b"IEND", b"")
        )
        output_path.write_bytes(png_bytes)
