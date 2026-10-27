"""Nonlinear Multi-Track Visual Timeline & Video Stage Canvas Editor for YouTube Automation Studio."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from youtube_studio.domain.models.project import TransitionConfig, TransitionType
from youtube_studio.domain.services.media_service import MediaLibraryService
from youtube_studio.domain.services.project_service import ProjectService
from youtube_studio.storage import session_scope


@dataclass
class TimelineClipItem:
    """In-memory representation of a timeline audio clip for interactive editing."""

    track_id: str
    media_file_id: str
    title: str
    artist: str
    file_path: str
    source_duration_ms: int
    trim_start_ms: int = 0
    trim_end_ms: Optional[int] = None
    gain_db: float = 0.0
    fade_in_ms: int = 0
    fade_out_ms: int = 0
    overlap_ms: int = 3000
    transition_type: str = TransitionType.BASS_SWAP_EQ.value
    bpm: Optional[float] = None
    camelot_code: Optional[str] = None
    peaks: list[float] = field(default_factory=list)
    timeline_start_ms: int = 0
    timeline_end_ms: int = 0

    @property
    def effective_duration_ms(self) -> int:
        end_ms = (
            min(self.trim_end_ms, self.source_duration_ms)
            if self.trim_end_ms and self.trim_end_ms > self.trim_start_ms
            else self.source_duration_ms
        )
        return max(500, end_ms - max(0, self.trim_start_ms))


class VideoStageCanvas(QWidget):
    """Live 16:9 / 9:16 Video Monitor Canvas rendering background image, spectrum visualizer, Now-Playing text & progress bar."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 240)
        self._bg_pixmap: Optional[QPixmap] = None
        self._bg_label: str = "Studio Visual Stage"
        self._now_playing_text: str = "00:00 — Select or Play a Clip"
        self._visualizer_style: str = "bar_spectrum"
        self._show_now_playing: bool = True
        self._show_progress_bar: bool = True
        self._aspect_mode: str = "16:9"
        self._playhead_ms: int = 0
        self._total_duration_ms: int = 1
        self._is_playing: bool = False
        self._anim_phase: float = 0.0

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(45)
        self._anim_timer.timeout.connect(self._on_anim_tick)

    def set_playing(self, playing: bool) -> None:
        self._is_playing = playing
        if playing and not self._anim_timer.isActive():
            self._anim_timer.start()
        elif not playing and self._anim_timer.isActive():
            self._anim_timer.stop()
        self.update()

    def _on_anim_tick(self) -> None:
        self._anim_phase += 0.28
        self.update()

    def set_background_asset(self, path: Optional[Path]) -> None:
        self._bg_pixmap = None
        if path and path.exists():
            self._bg_label = path.name
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                pix = QPixmap(str(path))
                if not pix.isNull():
                    self._bg_pixmap = pix
        else:
            self._bg_label = "Auto-Generated 16:9 Studio Artwork"
        self.update()

    def set_stage_state(
        self,
        *,
        playhead_ms: int,
        total_duration_ms: int,
        now_playing_text: str,
        visualizer_style: str = "bar_spectrum",
        show_now_playing: bool = True,
        show_progress_bar: bool = True,
        aspect_mode: str = "16:9",
    ) -> None:
        self._playhead_ms = max(0, playhead_ms)
        self._total_duration_ms = max(1, total_duration_ms)
        self._now_playing_text = now_playing_text
        self._visualizer_style = visualizer_style
        self._show_now_playing = show_now_playing
        self._show_progress_bar = show_progress_bar
        self._aspect_mode = aspect_mode
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        painter.fillRect(QRectF(0, 0, w, h), QColor("#090b10"))

        # Compute aspect-fitted stage rectangle
        target_ratio = (9.0 / 16.0) if self._aspect_mode == "9:16" else (16.0 / 9.0)
        avail_w = w - 24.0
        avail_h = h - 24.0
        if avail_w / max(1.0, avail_h) > target_ratio:
            stage_h = avail_h
            stage_w = stage_h * target_ratio
        else:
            stage_w = avail_w
            stage_h = stage_w / target_ratio
        sx = (w - stage_w) / 2.0
        sy = (h - stage_h) / 2.0
        stage_rect = QRectF(sx, sy, stage_w, stage_h)

        # Clip to rounded stage rect
        clip_path = QPainterPath()
        clip_path.addRoundedRect(stage_rect, 10.0, 10.0)
        painter.save()
        painter.setClipPath(clip_path)

        if self._bg_pixmap is not None and not self._bg_pixmap.isNull():
            scaled = self._bg_pixmap.scaled(
                int(stage_w),
                int(stage_h),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(int(sx), int(sy), scaled)
            # Subtle dark overlay for text legibility
            painter.fillRect(stage_rect, QColor(10, 14, 24, 95))
        else:
            grad = QLinearGradient(sx, sy, sx + stage_w, sy + stage_h)
            grad.setColorAt(0.0, QColor("#1e1b4b"))
            grad.setColorAt(0.5, QColor("#0f172a"))
            grad.setColorAt(1.0, QColor("#31102f"))
            painter.fillRect(stage_rect, grad)

        # Center watermark / visual asset badge
        painter.setPen(QColor(255, 255, 255, 130))
        painter.setFont(QFont("", 10, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(sx + 14, sy + stage_h - 68, stage_w - 28, 20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"🎬 {self._bg_label} ({self._aspect_mode})",
        )

        # Draw audio-reactive visualizer preview
        if self._visualizer_style != "none":
            vis_top = sy + stage_h * 0.62
            vis_h = stage_h * 0.28
            num_bars = 36
            bar_w = (stage_w - 32.0) / num_bars
            phase = self._anim_phase if self._is_playing else (self._playhead_ms / 350.0)
            for i in range(num_bars):
                energy = (
                    0.35
                    + 0.45 * abs(math.sin(phase + i * 0.42))
                    + 0.20 * abs(math.cos(phase * 1.7 - i * 0.25))
                )
                bh = max(4.0, vis_h * energy)
                bx = sx + 16.0 + i * bar_w
                if self._visualizer_style == "mirrored_stereo":
                    by = vis_top + (vis_h - bh) / 2.0
                    painter.fillRect(
                        QRectF(bx, by, max(2.0, bar_w - 2.0), bh),
                        QColor(56, 189, 248, 200),
                    )
                elif self._visualizer_style == "dub_oscilloscope":
                    by = vis_top + vis_h * 0.5 + math.sin(phase + i * 0.35) * (vis_h * 0.38)
                    painter.fillRect(
                        QRectF(bx, by, max(3.0, bar_w), 4.0),
                        QColor(250, 204, 21, 220),
                    )
                else:
                    by = vis_top + vis_h - bh
                    painter.fillRect(
                        QRectF(bx, by, max(2.0, bar_w - 2.0), bh),
                        QColor(230, 161, 69, 210),
                    )

        # Draw Now-Playing overlay box
        if self._show_now_playing and self._now_playing_text:
            box_rect = QRectF(sx + 16.0, sy + 16.0, min(stage_w - 32.0, 420.0), 34.0)
            painter.fillRect(box_rect, QColor(9, 13, 22, 185))
            painter.setPen(QPen(QColor("#6366f1"), 1.0))
            painter.drawRoundedRect(box_rect, 6.0, 6.0)
            painter.setPen(QColor("#f8fafc"))
            painter.setFont(QFont("", 11, QFont.Weight.Bold))
            painter.drawText(
                box_rect.adjusted(10, 0, -10, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"♪ Now Playing: {self._now_playing_text}",
            )

        # Draw bottom progress bar
        if self._show_progress_bar:
            prog_ratio = max(0.0, min(1.0, self._playhead_ms / max(1, self._total_duration_ms)))
            bar_h = 6.0
            painter.fillRect(
                QRectF(sx, sy + stage_h - bar_h, stage_w, bar_h),
                QColor(255, 255, 255, 45),
            )
            painter.fillRect(
                QRectF(sx, sy + stage_h - bar_h, stage_w * prog_ratio, bar_h),
                QColor("#e6a145"),
            )

        painter.restore()

        # Border around stage
        painter.setPen(QPen(QColor("#334155"), 1.5))
        painter.drawRoundedRect(stage_rect, 10.0, 10.0)


class MultiTrackTimelineWidget(QWidget):
    """Interactive multi-lane timeline widget with draggable playhead, waveforms, and clip trim handles."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        on_clip_selected: Optional[Callable[[int], None]] = None,
        on_playhead_scrubbed: Optional[Callable[[int], None]] = None,
        on_clip_trimmed: Optional[Callable[[int, int, Optional[int]], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumHeight(195)
        self.setMouseTracking(True)
        self._clips: list[TimelineClipItem] = []
        self._selected_idx: int = 0
        self._playhead_ms: int = 0
        self._total_duration_ms: int = 1000
        self._visual_label: str = "Studio Artwork / Video Loop"
        self._on_clip_selected = on_clip_selected
        self._on_playhead_scrubbed = on_playhead_scrubbed
        self._on_clip_trimmed = on_clip_trimmed

        self._dragging_playhead: bool = False
        self._dragging_trim_mode: Optional[str] = None  # "left" or "right"
        self._drag_start_x: float = 0.0
        self._drag_orig_trim_start: int = 0
        self._drag_orig_trim_end: int = 0

    @property
    def left_header_width(self) -> float:
        return 135.0

    def set_timeline_data(
        self,
        clips: list[TimelineClipItem],
        *,
        selected_idx: Optional[int] = None,
        visual_label: str = "Studio Artwork / Video Loop",
    ) -> None:
        self._clips = clips
        self._visual_label = visual_label
        # Compute timeline start/end positions accounting for crossfade overlaps
        cursor_ms = 0
        for idx, c in enumerate(self._clips):
            c.timeline_start_ms = cursor_ms
            eff = c.effective_duration_ms
            c.timeline_end_ms = cursor_ms + eff
            overlap = (
                min(max(0, c.overlap_ms), eff // 2)
                if idx < len(self._clips) - 1 and c.transition_type != TransitionType.NONE.value
                else 0
            )
            cursor_ms += max(200, eff - overlap)
        self._total_duration_ms = max(1000, cursor_ms if self._clips else 60_000)
        if selected_idx is not None and 0 <= selected_idx < len(self._clips):
            self._selected_idx = selected_idx
        elif self._selected_idx >= len(self._clips):
            self._selected_idx = max(0, len(self._clips) - 1)
        self.update()

    def set_playhead_ms(self, pos_ms: int) -> None:
        self._playhead_ms = max(0, min(self._total_duration_ms, pos_ms))
        self.update()

    def playhead_ms(self) -> int:
        return self._playhead_ms

    def total_duration_ms(self) -> int:
        return self._total_duration_ms

    def selected_clip_index(self) -> int:
        return self._selected_idx

    def _ms_to_x(self, ms: int) -> float:
        track_w = max(10.0, float(self.width()) - self.left_header_width - 16.0)
        return self.left_header_width + (ms / max(1, self._total_duration_ms)) * track_w

    def _x_to_ms(self, x: float) -> int:
        track_w = max(10.0, float(self.width()) - self.left_header_width - 16.0)
        rel = max(0.0, min(1.0, (x - self.left_header_width) / track_w))
        return int(rel * self._total_duration_ms)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w = float(self.width())
        h = float(self.height())
        hdr_w = self.left_header_width

        painter.fillRect(QRectF(0, 0, w, h), QColor("#0d1017"))

        ruler_h = 26.0
        lane_h = (h - ruler_h - 12.0) / 3.0
        lane_y = [ruler_h + 4.0 + i * lane_h for i in range(3)]
        lane_labels = [
            ("T1 · Chapters", "#a855f7"),
            ("V1 · Visual Loop", "#0ea5e9"),
            ("A1 · Audio Mix", "#4f46e5"),
        ]

        # Draw Left Track Headers
        painter.fillRect(QRectF(0, 0, hdr_w, h), QColor("#141824"))
        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("", 10, QFont.Weight.Bold))
        painter.drawText(
            QRectF(10, 0, hdr_w - 14, ruler_h),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._format_mm_ss(self._playhead_ms),
        )

        for i, (lbl, accent) in enumerate(lane_labels):
            ly = lane_y[i]
            painter.setPen(QPen(QColor("#22283a"), 1.0))
            painter.drawLine(0, int(ly), int(w), int(ly))
            painter.fillRect(QRectF(0, ly + 2, 4, lane_h - 4), QColor(accent))
            painter.setPen(QColor("#e2e8f0"))
            painter.setFont(QFont("", 10, QFont.Weight.DemiBold))
            painter.drawText(
                QRectF(12, ly, hdr_w - 16, lane_h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                lbl,
            )

        # Draw Time Ruler ticks
        painter.fillRect(QRectF(hdr_w, 0, w - hdr_w, ruler_h), QColor("#111520"))
        num_ticks = 10
        painter.setFont(QFont("", 9))
        for t_idx in range(num_ticks + 1):
            t_ms = int((t_idx / num_ticks) * self._total_duration_ms)
            tx = self._ms_to_x(t_ms)
            painter.setPen(QPen(QColor("#334155"), 1.0))
            painter.drawLine(int(tx), int(ruler_h - 8), int(tx), int(ruler_h))
            if t_idx < num_ticks:
                painter.setPen(QColor("#94a3b8"))
                painter.drawText(
                    QRectF(tx + 3, 2, 65, ruler_h - 4),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    self._format_mm_ss(t_ms),
                )

        # Lane 0 (T1 · Chapter Title Blocks)
        for idx, clip in enumerate(self._clips):
            cx1 = self._ms_to_x(clip.timeline_start_ms)
            cx2 = self._ms_to_x(clip.timeline_end_ms)
            cw = max(14.0, cx2 - cx1 - 2.0)
            crect = QRectF(cx1, lane_y[0] + 5.0, cw, lane_h - 10.0)
            painter.fillRect(crect, QColor(168, 85, 247, 70))
            painter.setPen(QPen(QColor("#a855f7"), 1.0))
            painter.drawRoundedRect(crect, 4.0, 4.0)
            painter.setPen(QColor("#f3e8ff"))
            painter.setFont(QFont("", 9, QFont.Weight.Medium))
            painter.drawText(
                crect.adjusted(6, 0, -6, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"T{idx + 1}: {clip.title}",
            )

        # Lane 1 (V1 · Visual Background Asset Span)
        if self._clips:
            vx1 = self._ms_to_x(0)
            vx2 = self._ms_to_x(self._total_duration_ms)
            vrect = QRectF(vx1, lane_y[1] + 5.0, max(20.0, vx2 - vx1), lane_h - 10.0)
            painter.fillRect(vrect, QColor(14, 165, 233, 65))
            painter.setPen(QPen(QColor("#0ea5e9"), 1.0))
            painter.drawRoundedRect(vrect, 4.0, 4.0)
            painter.setPen(QColor("#e0f2fe"))
            painter.setFont(QFont("", 9, QFont.Weight.DemiBold))
            painter.drawText(
                vrect.adjusted(8, 0, -8, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"🎬 Visual Track: {self._visual_label} (Looped across full timeline)",
            )

        # Lane 2 (A1 · Audio Clips + Waveform + Trim Handles + Crossfade Overlaps)
        palette_colors = [
            QColor(79, 70, 229, 190),
            QColor(13, 148, 136, 190),
            QColor(37, 99, 235, 190),
            QColor(124, 58, 237, 190),
        ]
        for idx, clip in enumerate(self._clips):
            ax1 = self._ms_to_x(clip.timeline_start_ms)
            ax2 = self._ms_to_x(clip.timeline_end_ms)
            aw = max(18.0, ax2 - ax1)
            arect = QRectF(ax1, lane_y[2] + 4.0, aw, lane_h - 8.0)

            base_col = palette_colors[idx % len(palette_colors)]
            painter.fillRect(arect, base_col)

            # Draw synthetic/extracted waveform peaks inside clip
            peaks = clip.peaks or [
                0.3 + 0.55 * abs(math.sin(i * 0.55 + idx)) for i in range(28)
            ]
            if aw > 24.0 and peaks:
                step_w = (aw - 8.0) / len(peaks)
                mid_y = arect.center().y()
                max_ph = (arect.height() - 10.0) * 0.45
                painter.setPen(QPen(QColor(255, 255, 255, 115), 1.2))
                for p_idx, pk in enumerate(peaks):
                    px = arect.left() + 4.0 + p_idx * step_w
                    ph = max(2.0, float(pk) * max_ph)
                    painter.drawLine(QPointF(px, mid_y - ph), QPointF(px, mid_y + ph))

            # Highlight selected clip with bright border & left/right trim handles
            is_sel = idx == self._selected_idx
            border_col = QColor("#facc15") if is_sel else QColor("#818cf8")
            painter.setPen(QPen(border_col, 2.0 if is_sel else 1.0))
            painter.drawRoundedRect(arect, 5.0, 5.0)

            if is_sel:
                # Left and right yellow trim grab handles
                handle_w = 5.0
                painter.fillRect(
                    QRectF(arect.left(), arect.top(), handle_w, arect.height()),
                    QColor("#facc15"),
                )
                painter.fillRect(
                    QRectF(arect.right() - handle_w, arect.top(), handle_w, arect.height()),
                    QColor("#facc15"),
                )

            # Clip label + BPM/Key badge
            harmonic = (
                f" · {clip.bpm:.0f} BPM · {clip.camelot_code}"
                if clip.bpm and clip.camelot_code
                else ""
            )
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("", 9, QFont.Weight.Bold))
            painter.drawText(
                arect.adjusted(8, 2, -8, -2),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                f"{idx + 1}. {clip.title}{harmonic}",
            )

        # Draw Red Playhead Line + Handle across all lanes
        px = self._ms_to_x(self._playhead_ms)
        painter.setPen(QPen(QColor("#ef4444"), 2.0))
        painter.drawLine(int(px), 0, int(px), int(h))
        head_poly = QPainterPath()
        head_poly.moveTo(px - 6, 0)
        head_poly.lineTo(px + 6, 0)
        head_poly.lineTo(px, 11)
        head_poly.closeSubpath()
        painter.fillPath(head_poly, QColor("#ef4444"))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        x = pos.x()
        y = pos.y()
        if x < self.left_header_width:
            return

        ruler_h = 26.0
        lane_h = (float(self.height()) - ruler_h - 12.0) / 3.0
        audio_lane_top = ruler_h + 4.0 + 2.0 * lane_h

        # Check if clicking inside Audio Lane (Lane 2)
        if y >= audio_lane_top:
            for idx, clip in enumerate(self._clips):
                ax1 = self._ms_to_x(clip.timeline_start_ms)
                ax2 = self._ms_to_x(clip.timeline_end_ms)
                if ax1 - 4 <= x <= ax2 + 4:
                    self._selected_idx = idx
                    if self._on_clip_selected:
                        self._on_clip_selected(idx)
                    # Check if grabbing left or right trim handle
                    if abs(x - ax1) <= 8.0:
                        self._dragging_trim_mode = "left"
                        self._drag_start_x = x
                        self._drag_orig_trim_start = clip.trim_start_ms
                    elif abs(x - ax2) <= 8.0:
                        self._dragging_trim_mode = "right"
                        self._drag_start_x = x
                        self._drag_orig_trim_end = (
                            clip.trim_end_ms
                            if clip.trim_end_ms and clip.trim_end_ms > clip.trim_start_ms
                            else clip.source_duration_ms
                        )
                    break

        # Scrub playhead to clicked position
        self._dragging_playhead = self._dragging_trim_mode is None
        new_ms = self._x_to_ms(x)
        self.set_playhead_ms(new_ms)
        if self._on_playhead_scrubbed:
            self._on_playhead_scrubbed(new_ms)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        x = pos.x()

        if self._dragging_trim_mode and 0 <= self._selected_idx < len(self._clips):
            clip = self._clips[self._selected_idx]
            delta_ms = self._x_to_ms(x) - self._x_to_ms(self._drag_start_x)
            if self._dragging_trim_mode == "left":
                max_start = (
                    (clip.trim_end_ms or clip.source_duration_ms) - 1000
                )
                clip.trim_start_ms = max(0, min(max_start, self._drag_orig_trim_start + delta_ms))
            elif self._dragging_trim_mode == "right":
                min_end = clip.trim_start_ms + 1000
                clip.trim_end_ms = max(
                    min_end,
                    min(clip.source_duration_ms, self._drag_orig_trim_end + delta_ms),
                )
            self.set_timeline_data(self._clips, selected_idx=self._selected_idx, visual_label=self._visual_label)
            if self._on_clip_trimmed:
                self._on_clip_trimmed(self._selected_idx, clip.trim_start_ms, clip.trim_end_ms)
            return

        if self._dragging_playhead:
            new_ms = self._x_to_ms(x)
            self.set_playhead_ms(new_ms)
            if self._on_playhead_scrubbed:
                self._on_playhead_scrubbed(new_ms)

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:  # noqa: N802
        self._dragging_playhead = False
        self._dragging_trim_mode = None

    @staticmethod
    def _format_mm_ss(ms: int) -> str:
        total_s = max(0, int(ms) // 1000)
        mins = total_s // 60
        secs = total_s % 60
        return f"{mins:02d}:{secs:02d}"


class TimelineCanvasEditorDialog(QDialog):
    """Full-screen Nonlinear Video & Audio Timeline Editor Dialog with Live Stage Monitor and Playhead Trim Tools."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        project_id: str,
        visual_asset_path: Optional[Path] = None,
        visualizer_style: str = "bar_spectrum",
        on_saved: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._project_id = project_id
        self._visual_asset_path = visual_asset_path
        self._visualizer_style = visualizer_style
        self._on_saved = on_saved
        self._clips: list[TimelineClipItem] = []
        self._active_playing_clip_idx: Optional[int] = None

        self.setWindowTitle("🎬 Studio Nonlinear Timeline & Canvas Video Editor")
        self.resize(1060, 680)

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.85)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_media_position_changed)

        self._build_ui()
        self._load_from_project()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header Row
        hdr = QHBoxLayout()
        title = QLabel("🎬 Nonlinear Multi-Track Timeline & Canvas Editor")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        hdr.addWidget(title)
        hdr.addStretch(1)

        hdr.addWidget(QLabel("Canvas Aspect:"))
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["16:9 Widescreen", "9:16 Vertical Short"])
        self.aspect_combo.currentIndexChanged.connect(self._sync_stage_canvas)
        hdr.addWidget(self.aspect_combo)

        self.btn_change_visual = QPushButton("🖼/🎬 Swap Visual Asset…")
        self.btn_change_visual.setToolTip("Choose a custom background image or looping video clip for the stage.")
        self.btn_change_visual.clicked.connect(self._on_swap_visual_asset)
        hdr.addWidget(self.btn_change_visual)

        root.addLayout(hdr)

        # Upper Split: Left = Video Stage Monitor, Right = Selected Clip Inspector
        upper = QHBoxLayout()
        self.stage_canvas = VideoStageCanvas(self)
        self.stage_canvas.set_background_asset(self._visual_asset_path)
        upper.addWidget(self.stage_canvas, stretch=3)

        inspector_box = QGroupBox("Selected Clip Inspector & Precision Trim")
        insp_form = QFormLayout(inspector_box)

        self.lbl_selected_clip = QLabel("No clip selected")
        self.lbl_selected_clip.setStyleSheet("color: #38bdf8; font-weight: 600;")
        insp_form.addRow("Active Clip:", self.lbl_selected_clip)

        self.spin_trim_start = QSpinBox()
        self.spin_trim_start.setRange(0, 36_000_000)
        self.spin_trim_start.setSingleStep(250)
        self.spin_trim_start.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("In Point / Trim Start (ms):", self.spin_trim_start)

        self.spin_trim_end = QSpinBox()
        self.spin_trim_end.setRange(0, 36_000_000)
        self.spin_trim_end.setSingleStep(250)
        self.spin_trim_end.setSpecialValueText("Full Track End (0)")
        self.spin_trim_end.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Out Point / Trim End (ms):", self.spin_trim_end)

        self.spin_gain = QDoubleSpinBox()
        self.spin_gain.setRange(-24.0, 24.0)
        self.spin_gain.setSingleStep(0.5)
        self.spin_gain.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Clip Gain (dB):", self.spin_gain)

        self.spin_fade_in = QSpinBox()
        self.spin_fade_in.setRange(0, 60_000)
        self.spin_fade_in.setSingleStep(250)
        self.spin_fade_in.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Fade In (ms):", self.spin_fade_in)

        self.spin_fade_out = QSpinBox()
        self.spin_fade_out.setRange(0, 60_000)
        self.spin_fade_out.setSingleStep(250)
        self.spin_fade_out.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Fade Out (ms):", self.spin_fade_out)

        self.combo_transition = QComboBox()
        self.combo_transition.addItems([t.value for t in TransitionType])
        self.combo_transition.currentTextChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Transition Mode:", self.combo_transition)

        self.spin_overlap = QSpinBox()
        self.spin_overlap.setRange(0, 30_000)
        self.spin_overlap.setSingleStep(500)
        self.spin_overlap.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Crossfade Overlap (ms):", self.spin_overlap)

        upper.addWidget(inspector_box, stretch=2)
        root.addLayout(upper, stretch=3)

        # Timeline Editing Toolbar (Play/Pause, Set In/Out at Playhead, Move, Delete)
        tbar = QHBoxLayout()
        self.btn_play = QPushButton("▶ Play / Preview Timeline")
        self.btn_play.setObjectName("PrimaryButton")
        self.btn_play.clicked.connect(self.toggle_playback)
        tbar.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self.stop_playback)
        tbar.addWidget(self.btn_stop)

        self.btn_trim_in_here = QPushButton("⇤ Set Clip Start at Playhead")
        self.btn_trim_in_here.setToolTip("Trim the start of the active clip to the current red playhead position.")
        self.btn_trim_in_here.clicked.connect(self._on_set_in_at_playhead)
        tbar.addWidget(self.btn_trim_in_here)

        self.btn_trim_out_here = QPushButton("⇥ Set Clip End at Playhead")
        self.btn_trim_out_here.setToolTip("Trim the end of the active clip to the current red playhead position.")
        self.btn_trim_out_here.clicked.connect(self._on_set_out_at_playhead)
        tbar.addWidget(self.btn_trim_out_here)

        self.btn_reset_trim = QPushButton("↺ Reset Clip Trim")
        self.btn_reset_trim.clicked.connect(self._on_reset_clip_trim)
        tbar.addWidget(self.btn_reset_trim)

        self.btn_move_left = QPushButton("← Move Earlier")
        self.btn_move_left.clicked.connect(lambda: self._on_move_selected_clip(-1))
        tbar.addWidget(self.btn_move_left)

        self.btn_move_right = QPushButton("→ Move Later")
        self.btn_move_right.clicked.connect(lambda: self._on_move_selected_clip(1))
        tbar.addWidget(self.btn_move_right)

        self.btn_delete_clip = QPushButton("🗑 Delete Clip")
        self.btn_delete_clip.clicked.connect(self._on_delete_selected_clip)
        tbar.addWidget(self.btn_delete_clip)

        tbar.addStretch(1)
        self.lbl_timecode = QLabel("00:00 / 00:00")
        self.lbl_timecode.setStyleSheet("color: #facc15; font-family: monospace; font-weight: bold;")
        tbar.addWidget(self.lbl_timecode)
        root.addLayout(tbar)

        # Multi-Track Timeline Canvas
        self.timeline_widget = MultiTrackTimelineWidget(
            self,
            on_clip_selected=self._on_timeline_clip_selected,
            on_playhead_scrubbed=self._on_playhead_scrubbed,
            on_clip_trimmed=self._on_timeline_clip_trimmed_by_drag,
        )
        root.addWidget(self.timeline_widget, stretch=2)

        # Footer Save / Close Buttons
        footer = QHBoxLayout()
        hint = QLabel(
            "Tip: Drag the red playhead to scrub across your mix, or drag the yellow left/right edges of any audio clip to trim."
        )
        hint.setStyleSheet("color: #94a3b8;")
        footer.addWidget(hint, stretch=1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        footer.addWidget(btn_cancel)

        self.btn_save = QPushButton("💾 Save Timeline Edits to Project")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self._on_save_and_close)
        footer.addWidget(self.btn_save)
        root.addLayout(footer)

    def _load_from_project(self) -> None:
        self._clips = []
        with session_scope() as session:
            proj_svc = ProjectService(session)
            media_svc = MediaLibraryService(session)
            tracks = proj_svc.list_tracks(self._project_id)
            for pt in tracks:
                mf = media_svc.get(pt.media_file_id)
                if not mf:
                    continue
                title = str(mf.metadata.get("title") or Path(mf.path).stem)
                artist = str(mf.metadata.get("artist") or "—")
                peaks = list(mf.metadata.get("waveform_peaks") or [])[:36]
                self._clips.append(
                    TimelineClipItem(
                        track_id=pt.id,
                        media_file_id=mf.id,
                        title=title,
                        artist=artist,
                        file_path=mf.path,
                        source_duration_ms=mf.duration_ms or 60_000,
                        trim_start_ms=pt.trim_start_ms,
                        trim_end_ms=pt.trim_end_ms,
                        gain_db=pt.gain_db,
                        fade_in_ms=pt.fade_in_ms,
                        fade_out_ms=pt.fade_out_ms,
                        overlap_ms=pt.transition_config.overlap_ms,
                        transition_type=pt.transition_config.transition_type.value,
                        bpm=mf.metadata.get("bpm"),
                        camelot_code=mf.metadata.get("camelot_code"),
                        peaks=peaks,
                    )
                )
        vis_lbl = self._visual_asset_path.name if self._visual_asset_path else "Auto-Generated 16:9 Artwork"
        self.timeline_widget.set_timeline_data(self._clips, selected_idx=0, visual_label=vis_lbl)
        self._populate_inspector(0)
        self._sync_stage_canvas()

    def _populate_inspector(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._clips):
            self.lbl_selected_clip.setText("No clip selected")
            return
        c = self._clips[idx]
        self.lbl_selected_clip.setText(f"{idx + 1}. {c.title}")
        for w in (
            self.spin_trim_start,
            self.spin_trim_end,
            self.spin_gain,
            self.spin_fade_in,
            self.spin_fade_out,
            self.combo_transition,
            self.spin_overlap,
        ):
            w.blockSignals(True)
        self.spin_trim_start.setValue(c.trim_start_ms)
        self.spin_trim_end.setValue(c.trim_end_ms or 0)
        self.spin_gain.setValue(c.gain_db)
        self.spin_fade_in.setValue(c.fade_in_ms)
        self.spin_fade_out.setValue(c.fade_out_ms)
        self.combo_transition.setCurrentText(c.transition_type)
        self.spin_overlap.setValue(c.overlap_ms)
        for w in (
            self.spin_trim_start,
            self.spin_trim_end,
            self.spin_gain,
            self.spin_fade_in,
            self.spin_fade_out,
            self.combo_transition,
            self.spin_overlap,
        ):
            w.blockSignals(False)

    def _on_inspector_changed(self, *_args) -> None:
        idx = self.timeline_widget.selected_clip_index()
        if idx < 0 or idx >= len(self._clips):
            return
        c = self._clips[idx]
        c.trim_start_ms = self.spin_trim_start.value()
        end_val = self.spin_trim_end.value()
        c.trim_end_ms = end_val if end_val > c.trim_start_ms else None
        c.gain_db = float(self.spin_gain.value())
        c.fade_in_ms = self.spin_fade_in.value()
        c.fade_out_ms = self.spin_fade_out.value()
        c.transition_type = self.combo_transition.currentText()
        c.overlap_ms = self.spin_overlap.value()
        vis_lbl = self._visual_asset_path.name if self._visual_asset_path else "Auto-Generated 16:9 Artwork"
        self.timeline_widget.set_timeline_data(self._clips, selected_idx=idx, visual_label=vis_lbl)
        self._sync_stage_canvas()

    def _on_timeline_clip_selected(self, idx: int) -> None:
        self._populate_inspector(idx)
        self._sync_stage_canvas()

    def _on_timeline_clip_trimmed_by_drag(self, idx: int, _start_ms: int, _end_ms: Optional[int]) -> None:
        self._populate_inspector(idx)
        self._sync_stage_canvas()

    def _clip_at_playhead(self, playhead_ms: int) -> tuple[int, Optional[TimelineClipItem]]:
        for idx, c in enumerate(self._clips):
            if c.timeline_start_ms <= playhead_ms <= c.timeline_end_ms:
                return idx, c
        if self._clips:
            sel = self.timeline_widget.selected_clip_index()
            if 0 <= sel < len(self._clips):
                return sel, self._clips[sel]
        return -1, None

    def _sync_stage_canvas(self) -> None:
        pos_ms = self.timeline_widget.playhead_ms()
        tot_ms = self.timeline_widget.total_duration_ms()
        _, active_clip = self._clip_at_playhead(pos_ms)
        now_title = active_clip.title if active_clip else "No active track"
        aspect = "9:16" if self.aspect_combo.currentIndex() == 1 else "16:9"
        self.stage_canvas.set_stage_state(
            playhead_ms=pos_ms,
            total_duration_ms=tot_ms,
            now_playing_text=now_title,
            visualizer_style=self._visualizer_style,
            aspect_mode=aspect,
        )
        self.lbl_timecode.setText(
            f"{MultiTrackTimelineWidget._format_mm_ss(pos_ms)} / {MultiTrackTimelineWidget._format_mm_ss(tot_ms)}"
        )

    def _on_playhead_scrubbed(self, pos_ms: int) -> None:
        self._sync_stage_canvas()
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._seek_player_to_timeline_ms(pos_ms)

    def toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.stage_canvas.set_playing(False)
            self.btn_play.setText("▶ Resume Timeline")
            return
        self._seek_player_to_timeline_ms(self.timeline_widget.playhead_ms(), start_play=True)

    def stop_playback(self) -> None:
        self._player.stop()
        self.stage_canvas.set_playing(False)
        self.btn_play.setText("▶ Play / Preview Timeline")

    def _seek_player_to_timeline_ms(self, pos_ms: int, *, start_play: bool = False) -> None:
        idx, clip = self._clip_at_playhead(pos_ms)
        if clip is None or not Path(clip.file_path).exists():
            return
        offset_in_clip = max(0, pos_ms - clip.timeline_start_ms) + clip.trim_start_ms
        if self._active_playing_clip_idx != idx:
            self._active_playing_clip_idx = idx
            self._player.setSource(QUrl.fromLocalFile(clip.file_path))
        self._player.setPosition(int(offset_in_clip))
        if start_play:
            self._player.play()
            self.stage_canvas.set_playing(True)
            self.btn_play.setText("⏸ Pause Timeline")

    def _on_media_position_changed(self, media_pos_ms: int) -> None:
        if (
            self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
            or self._active_playing_clip_idx is None
            or not (0 <= self._active_playing_clip_idx < len(self._clips))
        ):
            return
        clip = self._clips[self._active_playing_clip_idx]
        timeline_pos = clip.timeline_start_ms + max(0, int(media_pos_ms) - clip.trim_start_ms)
        self.timeline_widget.set_playhead_ms(timeline_pos)
        self._sync_stage_canvas()

    def _on_set_in_at_playhead(self) -> None:
        idx = self.timeline_widget.selected_clip_index()
        if idx < 0 or idx >= len(self._clips):
            return
        clip = self._clips[idx]
        pos_ms = self.timeline_widget.playhead_ms()
        if clip.timeline_start_ms < pos_ms < clip.timeline_end_ms:
            delta = pos_ms - clip.timeline_start_ms
            clip.trim_start_ms = min(clip.source_duration_ms - 1000, clip.trim_start_ms + delta)
            self.timeline_widget.set_timeline_data(self._clips, selected_idx=idx)
            self._populate_inspector(idx)
            self._sync_stage_canvas()

    def _on_set_out_at_playhead(self) -> None:
        idx = self.timeline_widget.selected_clip_index()
        if idx < 0 or idx >= len(self._clips):
            return
        clip = self._clips[idx]
        pos_ms = self.timeline_widget.playhead_ms()
        if clip.timeline_start_ms < pos_ms < clip.timeline_end_ms:
            new_eff = max(1000, pos_ms - clip.timeline_start_ms)
            clip.trim_end_ms = min(clip.source_duration_ms, clip.trim_start_ms + new_eff)
            self.timeline_widget.set_timeline_data(self._clips, selected_idx=idx)
            self._populate_inspector(idx)
            self._sync_stage_canvas()

    def _on_reset_clip_trim(self) -> None:
        idx = self.timeline_widget.selected_clip_index()
        if idx < 0 or idx >= len(self._clips):
            return
        clip = self._clips[idx]
        clip.trim_start_ms = 0
        clip.trim_end_ms = None
        self.timeline_widget.set_timeline_data(self._clips, selected_idx=idx)
        self._populate_inspector(idx)
        self._sync_stage_canvas()

    def _on_move_selected_clip(self, delta: int) -> None:
        idx = self.timeline_widget.selected_clip_index()
        target = idx + delta
        if 0 <= idx < len(self._clips) and 0 <= target < len(self._clips):
            self._clips[idx], self._clips[target] = self._clips[target], self._clips[idx]
            self.timeline_widget.set_timeline_data(self._clips, selected_idx=target)
            self._populate_inspector(target)
            self._sync_stage_canvas()

    def _on_delete_selected_clip(self) -> None:
        idx = self.timeline_widget.selected_clip_index()
        if 0 <= idx < len(self._clips):
            self._clips.pop(idx)
            new_sel = max(0, min(idx, len(self._clips) - 1))
            self.timeline_widget.set_timeline_data(self._clips, selected_idx=new_sel)
            self._populate_inspector(new_sel)
            self._sync_stage_canvas()

    def _on_swap_visual_asset(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Image or Video Loop",
            str(Path.home()),
            "Visual Assets (*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.webm *.mkv)",
        )
        if not chosen:
            return
        self._visual_asset_path = Path(chosen)
        self.stage_canvas.set_background_asset(self._visual_asset_path)
        self.timeline_widget.set_timeline_data(
            self._clips,
            selected_idx=self.timeline_widget.selected_clip_index(),
            visual_label=self._visual_asset_path.name,
        )

    def _on_save_and_close(self) -> None:
        self.stop_playback()
        with session_scope() as session:
            proj_svc = ProjectService(session)
            existing_tracks = {t.id: t for t in proj_svc.list_tracks(self._project_id)}
            kept_ids = {c.track_id for c in self._clips}
            # Remove deleted tracks
            for tid in list(existing_tracks.keys()):
                if tid not in kept_ids:
                    proj_svc.remove_track(tid)

            # Reorder and update trim/gain/fade/transition parameters
            ordered_ids = [c.track_id for c in self._clips if c.track_id in existing_tracks]
            if ordered_ids:
                proj_svc.reorder_tracks(self._project_id, ordered_ids)
            refreshed = {t.id: t for t in proj_svc.list_tracks(self._project_id)}
            for c in self._clips:
                pt = refreshed.get(c.track_id)
                if pt is None:
                    continue
                pt.trim_start_ms = c.trim_start_ms
                pt.trim_end_ms = c.trim_end_ms
                pt.gain_db = c.gain_db
                pt.fade_in_ms = c.fade_in_ms
                pt.fade_out_ms = c.fade_out_ms
                pt.transition_config = TransitionConfig(
                    transition_type=TransitionType(c.transition_type)
                    if c.overlap_ms > 0
                    else TransitionType.NONE,
                    overlap_ms=c.overlap_ms,
                )
                proj_svc.update_track(pt)

        if self._on_saved:
            self._on_saved()
        self.accept()
