"""Official Brand Logo & Multi-Resolution App Icon Generator for YouTube Automation Studio."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)

APP_ICON_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="1024" height="1024" viewBox="0 0 1024 1024" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="bgGrad" cx="35%" cy="25%" r="78%">
      <stop offset="0%" stop-color="#312E81"/>
      <stop offset="55%" stop-color="#0F172A"/>
      <stop offset="100%" stop-color="#050811"/>
    </radialGradient>
    <linearGradient id="rimGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#818CF8"/>
      <stop offset="50%" stop-color="#38BDF8"/>
      <stop offset="100%" stop-color="#F59E0B"/>
    </linearGradient>
    <linearGradient id="playGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FDE047"/>
      <stop offset="50%" stop-color="#F59E0B"/>
      <stop offset="100%" stop-color="#EA580C"/>
    </linearGradient>
    <linearGradient id="barGrad" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#6366F1"/>
      <stop offset="60%" stop-color="#38BDF8"/>
      <stop offset="100%" stop-color="#FACC15"/>
    </linearGradient>
  </defs>

  <!-- macOS Squircle Background -->
  <rect x="64" y="64" width="896" height="896" rx="210" fill="url(#bgGrad)" stroke="url(#rimGrad)" stroke-width="16"/>

  <!-- Outer Vinyl / Harmonic Wheel Grooves -->
  <circle cx="512" cy="480" r="320" stroke="#334155" stroke-width="6" stroke-dasharray="18 12" opacity="0.75"/>
  <circle cx="512" cy="480" r="272" stroke="#475569" stroke-width="4" opacity="0.65"/>
  <circle cx="512" cy="480" r="224" stroke="#6366F1" stroke-width="6" opacity="0.55"/>

  <!-- Glowing Inner Studio Ring -->
  <circle cx="512" cy="480" r="168" fill="#0B0F19" stroke="url(#rimGrad)" stroke-width="12"/>

  <!-- Center Play Triangle Emblem -->
  <polygon points="462,388 462,572 618,480" fill="url(#playGrad)"/>

  <!-- Audio Spectrum Equalizer Bars at Bottom -->
  <g fill="url(#barGrad)" opacity="0.95">
    <rect x="236" y="790" width="24" height="58" rx="12"/>
    <rect x="280" y="756" width="24" height="92" rx="12"/>
    <rect x="324" y="720" width="24" height="128" rx="12"/>
    <rect x="368" y="764" width="24" height="84" rx="12"/>
    <rect x="412" y="704" width="24" height="144" rx="12"/>
    <rect x="456" y="674" width="24" height="174" rx="12"/>
    <rect x="500" y="652" width="24" height="196" rx="12"/>
    <rect x="544" y="680" width="24" height="168" rx="12"/>
    <rect x="588" y="714" width="24" height="134" rx="12"/>
    <rect x="632" y="758" width="24" height="90" rx="12"/>
    <rect x="676" y="730" width="24" height="118" rx="12"/>
    <rect x="720" y="768" width="24" height="80" rx="12"/>
    <rect x="764" y="794" width="24" height="54" rx="12"/>
  </g>
</svg>
"""

LOGO_HORIZONTAL_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="960" height="240" viewBox="0 0 960 240" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="iconBg" cx="35%" cy="25%" r="78%">
      <stop offset="0%" stop-color="#312E81"/>
      <stop offset="60%" stop-color="#0F172A"/>
      <stop offset="100%" stop-color="#050811"/>
    </radialGradient>
    <linearGradient id="accentRim" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#818CF8"/>
      <stop offset="50%" stop-color="#38BDF8"/>
      <stop offset="100%" stop-color="#F59E0B"/>
    </linearGradient>
    <linearGradient id="goldPlay" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FDE047"/>
      <stop offset="60%" stop-color="#F59E0B"/>
      <stop offset="100%" stop-color="#EA580C"/>
    </linearGradient>
  </defs>

  <rect x="8" y="8" width="944" height="224" rx="32" fill="#0B0F19" stroke="#1E293B" stroke-width="3"/>

  <!-- Left Icon Emblem -->
  <rect x="28" y="24" width="192" height="192" rx="44" fill="url(#iconBg)" stroke="url(#accentRim)" stroke-width="5"/>
  <circle cx="124" cy="112" r="66" stroke="#475569" stroke-width="2" stroke-dasharray="6 4"/>
  <circle cx="124" cy="112" r="42" fill="#0B0F19" stroke="url(#accentRim)" stroke-width="4"/>
  <polygon points="112,90 112,134 148,112" fill="url(#goldPlay)"/>

  <!-- Mini Spectrum Bars -->
  <g fill="url(#accentRim)">
    <rect x="68" y="182" width="6" height="16" rx="3"/>
    <rect x="82" y="174" width="6" height="24" rx="3"/>
    <rect x="96" y="166" width="6" height="32" rx="3"/>
    <rect x="110" y="158" width="6" height="40" rx="3"/>
    <rect x="124" y="154" width="6" height="44" rx="3"/>
    <rect x="138" y="162" width="6" height="36" rx="3"/>
    <rect x="152" y="170" width="6" height="28" rx="3"/>
    <rect x="166" y="178" width="6" height="20" rx="3"/>
    <rect x="180" y="184" width="6" height="14" rx="3"/>
  </g>

  <!-- Brand Typography -->
  <text x="252" y="106" fill="#F8FAFC" font-family="-apple-system, BlinkMacSystemFont, Inter, Segoe UI, sans-serif" font-size="44" font-weight="800" letter-spacing="-0.5">YouTube Automation Studio</text>
  <text x="254" y="148" fill="#38BDF8" font-family="-apple-system, BlinkMacSystemFont, Inter, Segoe UI, sans-serif" font-size="22" font-weight="600" letter-spacing="1.5">HARMONIC MIXING · LOCAL AI · VIDEO &amp; SHORTS ENGINE</text>
  <rect x="254" y="168" width="260" height="28" rx="14" fill="#1E1B4B" stroke="#6366F1" stroke-width="1.5"/>
  <text x="272" y="187" fill="#FCD34D" font-family="monospace" font-size="14" font-weight="700">LOCAL-FIRST PRO STUDIO</text>
</svg>
"""


class BrandAssetsService:
    """Generates and caches official app icons (.svg, .png, .icns, .ico) and horizontal brand logos."""

    _cached_icon: Optional[QIcon] = None

    @staticmethod
    def repo_assets_dir() -> Path:
        root = Path(__file__).resolve().parents[3]
        d = root / "assets" / "icons"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def render_icon_image(cls, size: int = 512) -> QImage:
        """Render the Studio App Icon (Vinyl + Harmonic Ring + Gold Play Emblem + Spectrum Bars) at any resolution."""
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        s = float(size)
        pad = s * 0.0625
        box = QRectF(pad, pad, s - 2 * pad, s - 2 * pad)
        radius = s * 0.205

        # 1. Squircle background with radial gradient
        bg_grad = QRadialGradient(QPointF(s * 0.35, s * 0.25), s * 0.78)
        bg_grad.setColorAt(0.0, QColor("#312E81"))
        bg_grad.setColorAt(0.55, QColor("#0F172A"))
        bg_grad.setColorAt(1.0, QColor("#050811"))

        rim_grad = QLinearGradient(QPointF(0, 0), QPointF(s, s))
        rim_grad.setColorAt(0.0, QColor("#818CF8"))
        rim_grad.setColorAt(0.5, QColor("#38BDF8"))
        rim_grad.setColorAt(1.0, QColor("#F59E0B"))

        path = QPainterPath()
        path.addRoundedRect(box, radius, radius)
        painter.fillPath(path, bg_grad)
        painter.setPen(QPen(rim_grad, max(1.5, s * 0.016)))
        painter.drawPath(path)

        # 2. Concentric Vinyl / Camelot Harmonic Rings
        cx = s * 0.50
        cy = s * 0.465
        for mult, col, width_mult, dashed in [
            (0.31, QColor(71, 85, 105, 190), 0.006, True),
            (0.26, QColor(99, 102, 241, 155), 0.005, False),
            (0.215, QColor(56, 189, 248, 145), 0.006, False),
        ]:
            pen = QPen(col, max(1.0, s * width_mult))
            if dashed:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = s * mult
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # 3. Inner Dark Disc with Glowing Rim
        inner_r = s * 0.162
        painter.setPen(QPen(rim_grad, max(1.5, s * 0.012)))
        painter.setBrush(QColor("#0B0F19"))
        painter.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # 4. Gold Play Triangle Emblem
        play_grad = QLinearGradient(
            QPointF(cx - inner_r * 0.5, cy - inner_r * 0.5),
            QPointF(cx + inner_r * 0.6, cy + inner_r * 0.6),
        )
        play_grad.setColorAt(0.0, QColor("#FDE047"))
        play_grad.setColorAt(0.55, QColor("#F59E0B"))
        play_grad.setColorAt(1.0, QColor("#EA580C"))

        tri = QPolygonF(
            [
                QPointF(cx - inner_r * 0.30, cy - inner_r * 0.54),
                QPointF(cx - inner_r * 0.30, cy + inner_r * 0.54),
                QPointF(cx + inner_r * 0.62, cy),
            ]
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(play_grad)
        painter.drawPolygon(tri)

        # 5. Audio Spectrum Equalizer Bars along bottom
        bar_grad = QLinearGradient(QPointF(0, s * 0.84), QPointF(0, s * 0.63))
        bar_grad.setColorAt(0.0, QColor("#6366F1"))
        bar_grad.setColorAt(0.6, QColor("#38BDF8"))
        bar_grad.setColorAt(1.0, QColor("#FACC15"))
        painter.setBrush(bar_grad)

        heights = [0.28, 0.46, 0.64, 0.42, 0.72, 0.88, 1.0, 0.85, 0.68, 0.45, 0.58, 0.40, 0.26]
        n_bars = len(heights)
        total_w = s * 0.54
        start_x = (s - total_w) / 2.0
        step_x = total_w / n_bars
        bar_w = max(1.5, step_x * 0.56)
        max_bar_h = s * 0.185
        base_y = s * 0.835

        for i, h_ratio in enumerate(heights):
            bh = max(2.0, max_bar_h * h_ratio)
            bx = start_x + i * step_x + (step_x - bar_w) / 2.0
            by = base_y - bh
            painter.drawRoundedRect(QRectF(bx, by, bar_w, bh), bar_w * 0.45, bar_w * 0.45)

        painter.end()
        return img

    @classmethod
    def render_horizontal_logo_image(cls, width: int = 960, height: int = 240) -> QImage:
        """Render the full horizontal Studio Brand Logo banner."""
        img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(width)
        h = float(height)

        # Card background
        card_rect = QRectF(4.0, 4.0, w - 8.0, h - 8.0)
        painter.setBrush(QColor("#0B0F19"))
        painter.setPen(QPen(QColor("#334155"), 2.5))
        painter.drawRoundedRect(card_rect, 28.0, 28.0)

        # Draw icon on left
        icon_size = int(h * 0.82)
        icon_img = cls.render_icon_image(icon_size)
        icon_x = int(h * 0.09)
        icon_y = (height - icon_size) // 2
        painter.drawImage(icon_x, icon_y, icon_img)

        # Brand title
        text_x = float(icon_x + icon_size + 24)
        painter.setPen(QColor("#F8FAFC"))
        title_font = QFont("", int(h * 0.165), QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(
            QRectF(text_x, h * 0.16, w - text_x - 24, h * 0.30),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "YouTube Automation Studio",
        )

        # Subtitle
        painter.setPen(QColor("#38BDF8"))
        sub_font = QFont("", int(h * 0.078), QFont.Weight.DemiBold)
        painter.setFont(sub_font)
        painter.drawText(
            QRectF(text_x, h * 0.47, w - text_x - 24, h * 0.20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "HARMONIC MIXING  ·  LOCAL AI  ·  VIDEO & SHORTS ENGINE",
        )

        # Pill badge
        pill_rect = QRectF(text_x, h * 0.69, 275.0, h * 0.16)
        painter.setBrush(QColor("#1E1B4B"))
        painter.setPen(QPen(QColor("#6366F1"), 1.5))
        painter.drawRoundedRect(pill_rect, pill_rect.height() / 2.0, pill_rect.height() / 2.0)

        painter.setPen(QColor("#FCD34D"))
        badge_font = QFont("", int(h * 0.058), QFont.Weight.Bold)
        painter.setFont(badge_font)
        painter.drawText(
            pill_rect,
            Qt.AlignmentFlag.AlignCenter,
            "✦ LOCAL-FIRST PRO STUDIO",
        )

        painter.end()
        return img

    @classmethod
    def generate_all_brand_files(cls, output_dir: Optional[Path] = None) -> dict[str, Path]:
        """Write SVG, multi-size PNGs, macOS .icns, Windows .ico, and horizontal logo banner to disk."""
        target_dir = output_dir or cls.repo_assets_dir()
        target_dir.mkdir(parents=True, exist_ok=True)

        svg_icon_path = target_dir / "app_icon.svg"
        svg_icon_path.write_text(APP_ICON_SVG, encoding="utf-8")

        svg_logo_path = target_dir / "logo_horizontal.svg"
        svg_logo_path.write_text(LOGO_HORIZONTAL_SVG, encoding="utf-8")

        sizes = [1024, 512, 256, 128, 64, 32, 16]
        png_paths: dict[int, Path] = {}
        for sz in sizes:
            qimg = cls.render_icon_image(sz)
            p = target_dir / f"app_icon_{sz}.png"
            qimg.save(str(p), "PNG")
            png_paths[sz] = p

        # Also save canonical app_icon.png (512x512) and logo_horizontal.png (960x240)
        canonical_icon = target_dir / "app_icon.png"
        cls.render_icon_image(512).save(str(canonical_icon), "PNG")

        horiz_logo_png = target_dir / "logo_horizontal.png"
        cls.render_horizontal_logo_image(960, 240).save(str(horiz_logo_png), "PNG")

        icns_path = target_dir / "youtube_studio.icns"
        ico_path = target_dir / "youtube_studio.ico"
        try:
            from PIL import Image

            with Image.open(png_paths[1024]) as base_im:
                base_im.save(
                    icns_path,
                    format="ICNS",
                )
                base_im.save(
                    ico_path,
                    format="ICO",
                    sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)],
                )
        except Exception:
            pass

        return {
            "app_icon_svg": svg_icon_path,
            "logo_horizontal_svg": svg_logo_path,
            "app_icon_png": canonical_icon,
            "app_icon_1024_png": png_paths[1024],
            "logo_horizontal_png": horiz_logo_png,
            "icns": icns_path,
            "ico": ico_path,
        }

    @classmethod
    def get_app_icon(cls) -> QIcon:
        """Return a multi-resolution QIcon for QApplication and QMainWindow."""
        if cls._cached_icon is not None and not cls._cached_icon.isNull():
            return cls._cached_icon
        icon = QIcon()
        for sz in (16, 32, 64, 128, 256, 512):
            pix = QPixmap.fromImage(cls.render_icon_image(sz))
            icon.addPixmap(pix)
        cls._cached_icon = icon
        return icon

    @classmethod
    def get_header_icon_pixmap(cls, size: int = 28) -> QPixmap:
        return QPixmap.fromImage(cls.render_icon_image(size))
