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
        self.setMinimumSize(260, 170)
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
        if hasattr(self, "insp_group") and hasattr(self.insp_group, "set_collapsed"):
            self.insp_group.set_collapsed(False)  # type: ignore[attr-defined]
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


class TimelineEditorPage(QWidget):
    """Dedicated 4-Pane Pro Video & Audio Timeline Editor workspace (Asset Browser | Player | Details | Timeline Dock)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._channel_ids: list[str] = []
        self._project_ids: list[str] = []
        self._clips: list[TimelineClipItem] = []
        self._visual_asset_path: Optional[Path] = None
        self._visualizer_style: str = "bar_spectrum"
        self._active_playing_clip_idx: Optional[int] = None

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(0.85)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_media_position_changed)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        from PySide6.QtWidgets import (
            QCheckBox,
            QFrame,
            QListWidget,
            QListWidgetItem,
            QMessageBox,
            QTabWidget,
        )
        from youtube_studio.config import get_settings
        from youtube_studio.domain.models.channel import NICHE_STYLE_PRESETS
        from youtube_studio.media.renderer import VisualizerStyle
        from youtube_studio.ui.components import EmptyStateWidget

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        # Hidden status/export widgets retained for programmatic compatibility while MainWindow hosts the unified top bar
        self.lbl_autosave = QLabel("● Auto saved: Ready")
        self.lbl_autosave.setVisible(False)
        self.btn_export_top = QPushButton("↗ Export")
        self.btn_export_top.clicked.connect(self._on_export_timeline_package)
        self.btn_export_top.setVisible(False)

        # Empty State Widget (shown when no clips exist in the current project)
        self.empty_state = EmptyStateWidget(
            title="Timeline Empty — Import Media or Launch EditPilot",
            description=(
                "Import audio tracks, images, or video loops from the left Media browser, "
                "or click '✦ EditPilot' to auto-populate and harmonic-sort your timeline."
            ),
            tips=[
                "<b>4-Pane Studio Layout:</b> Left = Media/Audio/Text/Effects/Transitions/Captions/Filters browser; Center = Player-Timeline 01; Right = Details & Clip Inspector; Bottom = Multi-Track Timeline.",
                "<b>Precision Trim Handles:</b> Drag the yellow left/right handles on any timeline clip or click 'Set In / Set Out at Playhead'.",
                "<b>AI Clipper & Export:</b> Extract peak 30s 9:16 Shorts or export .fcpxml / .edl / .csv timelines.",
            ],
            action_label="✦ EditPilot: Auto-Load Library Tracks",
            action_tooltip="Automatically load indexed audio tracks, trim silence, and harmonic-sort by BPM & Key.",
            on_action=self._on_editpilot_autoload,
            secondary_label="⊕ Import Media Files…",
            secondary_tooltip="Import audio, image, or video files into your project.",
            on_secondary=self._on_import_media_dialog,
        )
        root.addWidget(self.empty_state)

        # Upper 3-Pane Split: Left = Tabbed Asset/FX Browser | Center = Player-Timeline 01 | Right = Details & Inspector
        upper_row = QHBoxLayout()
        upper_row.setSpacing(8)

        # 1. Left Pane: Media | Audio | Text | Effects | Transitions | Captions | Filters
        left_frame = QFrame()
        self.left_frame = left_frame
        left_frame.setStyleSheet(
            "QFrame { background-color: #12151e; border: 1px solid #1e293b; border-radius: 10px; }"
        )
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        self.asset_tabs = QTabWidget()
        self.asset_tabs.setToolTip(
            "Browse Media, Audio, Text overlays, Visualizer Effects, Transitions, Captions, and Style Filters."
        )

        # Tab 1: Media (with left sub-categories + Import dropzone + Generate/Voiceover tiles + AI Clipper bar)
        media_tab = QWidget()
        media_tab_layout = QVBoxLayout(media_tab)
        media_tab_layout.setContentsMargins(4, 4, 4, 4)
        media_tab_layout.setSpacing(6)

        media_split = QHBoxLayout()
        self.media_subnav = QListWidget()
        self.media_subnav.setFixedWidth(92)
        for cat in ("Import", "Favorites", "My presets", "Brand assets", "Generate AI", "Library"):
            self.media_subnav.addItem(QListWidgetItem(cat))
        self.media_subnav.setCurrentRow(0)
        media_split.addWidget(self.media_subnav)

        media_right = QVBoxLayout()
        self.btn_import_dropzone = QPushButton("⊕ Import\nVideos, photos, and audio files")
        self.btn_import_dropzone.setMinimumHeight(64)
        self.btn_import_dropzone.setStyleSheet(
            "QPushButton { background-color: #181c28; color: #e2e8f0; border: 1px dashed #334155; "
            "border-radius: 8px; padding: 10px; font-weight: 600; } "
            "QPushButton:hover { border-color: #06b6d4; color: #22d3ee; }"
        )
        self.btn_import_dropzone.clicked.connect(self._on_import_media_dialog)
        media_right.addWidget(self.btn_import_dropzone)

        gen_tools_row = QHBoxLayout()
        btn_gen_art = QPushButton("✨ Generate Art")
        btn_gen_art.setToolTip("Open Artwork & Thumbnail Studio to generate 16:9 / 9:16 visuals.")
        btn_gen_art.clicked.connect(lambda: self._navigate_to_page("artwork"))
        gen_tools_row.addWidget(btn_gen_art)

        btn_gen_vo = QPushButton("🎙 Voiceover")
        btn_gen_vo.setToolTip("Open Script & Voiceover Studio to synthesize local TTS narration.")
        btn_gen_vo.clicked.connect(lambda: self._navigate_to_page("script_voice"))
        gen_tools_row.addWidget(btn_gen_vo)
        media_right.addLayout(gen_tools_row)

        self.visual_media_list = QListWidget()
        self.visual_media_list.setToolTip("Double-click any visual asset to set it as the active Player stage backdrop.")
        self.visual_media_list.itemDoubleClicked.connect(self._on_visual_item_activated)
        media_right.addWidget(self.visual_media_list, stretch=1)

        media_split.addLayout(media_right, stretch=1)
        media_tab_layout.addLayout(media_split, stretch=1)

        # Bottom AI Clipper bar inside Media tab (matches Screenshot 1!)
        clipper_bar = QHBoxLayout()
        lbl_clipper = QLabel("✂️ <b>AI clipper</b> · Peak 30s 9:16")
        lbl_clipper.setStyleSheet("color: #22d3ee; font-size: 11px; border: none;")
        clipper_bar.addWidget(lbl_clipper, stretch=1)

        self.btn_start_clipping = QPushButton("Start clipping")
        self.btn_start_clipping.setStyleSheet(
            "QPushButton { background-color: #06b6d4; color: #042f2e; font-weight: bold; "
            "padding: 4px 10px; border-radius: 5px; font-size: 11px; border: none; }"
        )
        self.btn_start_clipping.setToolTip("Automatically extract the highest-energy 30-second window as a 9:16 Short.")
        self.btn_start_clipping.clicked.connect(self._on_run_ai_clipper)
        clipper_bar.addWidget(self.btn_start_clipping)
        media_tab_layout.addLayout(clipper_bar)

        self.asset_tabs.addTab(media_tab, "🎬 Media")

        # Tab 2: Audio Library
        audio_tab = QWidget()
        audio_layout = QVBoxLayout(audio_tab)
        self.audio_lib_list = QListWidget()
        self.audio_lib_list.setToolTip("Indexed Music Library tracks & synthesized Voiceovers.")
        audio_layout.addWidget(self.audio_lib_list, stretch=1)

        btn_add_audio = QPushButton("+ Add Selected Audio to Timeline")
        btn_add_audio.setObjectName("PrimaryButton")
        btn_add_audio.clicked.connect(self._on_add_selected_library_audio)
        audio_layout.addWidget(btn_add_audio)
        self.asset_tabs.addTab(audio_tab, "🎵 Audio")

        # Tab 3: Text & Overlays
        text_tab = QWidget()
        text_layout = QVBoxLayout(text_tab)
        self.chk_stage_now_playing = QCheckBox("Show Dynamic 'Now Playing' Overlay")
        self.chk_stage_now_playing.setChecked(True)
        self.chk_stage_now_playing.toggled.connect(lambda _: self._sync_stage_canvas())
        text_layout.addWidget(self.chk_stage_now_playing)

        self.chk_stage_progress = QCheckBox("Show Animated Bottom Progress Bar")
        self.chk_stage_progress.setChecked(True)
        self.chk_stage_progress.toggled.connect(lambda _: self._sync_stage_canvas())
        text_layout.addWidget(self.chk_stage_progress)

        btn_open_script_studio = QPushButton("✍️ Open Script & Caption Studio →")
        btn_open_script_studio.clicked.connect(lambda: self._navigate_to_page("script_voice"))
        text_layout.addWidget(btn_open_script_studio)
        text_layout.addStretch(1)
        self.asset_tabs.addTab(text_tab, "𝐓 Text")

        # Tab 4: Effects & Visualizers
        fx_tab = QWidget()
        fx_layout = QFormLayout(fx_tab)
        self.combo_stage_visualizer = QComboBox()
        self.combo_stage_visualizer.addItems([v.value for v in VisualizerStyle])
        self.combo_stage_visualizer.currentTextChanged.connect(self._on_visualizer_style_changed)
        fx_layout.addRow("Spectrum Style:", self.combo_stage_visualizer)
        self.asset_tabs.addTab(fx_tab, "✨ Effects")

        # Tab 5: Transitions
        trans_tab = QWidget()
        trans_layout = QVBoxLayout(trans_tab)
        btn_apply_bass_swap = QPushButton("Apply Bass-Swap EQ (3000ms) to All Clips")
        btn_apply_bass_swap.clicked.connect(
            lambda: self._apply_transition_to_all(TransitionType.BASS_SWAP_EQ.value, 3000)
        )
        trans_layout.addWidget(btn_apply_bass_swap)

        btn_apply_crossfade = QPushButton("Apply Smooth Crossfade (3000ms) to All Clips")
        btn_apply_crossfade.clicked.connect(
            lambda: self._apply_transition_to_all(TransitionType.CROSSFADE.value, 3000)
        )
        trans_layout.addWidget(btn_apply_crossfade)
        trans_layout.addStretch(1)
        self.asset_tabs.addTab(trans_tab, "⋈ Transitions")

        # Tab 6: Captions & Subtitles (.srt)
        cap_tab = QWidget()
        cap_layout = QVBoxLayout(cap_tab)
        lbl_cap = QLabel(
            "<b>Auto-Synced Track & Voiceover Captions (.srt)</b><br>"
            "Generates time-coded subtitles from your timeline chapters and Script & Voice studio."
        )
        lbl_cap.setWordWrap(True)
        lbl_cap.setStyleSheet("color: #cbd5e1; font-size: 11px; border: none;")
        cap_layout.addWidget(lbl_cap)

        btn_open_captions = QPushButton("💬 Open Script & Voiceover Captions →")
        btn_open_captions.clicked.connect(lambda: self._navigate_to_page("script_voice"))
        cap_layout.addWidget(btn_open_captions)
        cap_layout.addStretch(1)
        self.asset_tabs.addTab(cap_tab, "💬 Captions")

        # Tab 7: Filters / Niche Presets
        filter_tab = QWidget()
        filter_layout = QVBoxLayout(filter_tab)
        self.filter_preset_list = QListWidget()
        for preset in NICHE_STYLE_PRESETS.values():
            it = QListWidgetItem(f"🎨 {preset.label} ({preset.default_aspect_ratio} · {preset.visual_style})")
            it.setData(Qt.ItemDataRole.UserRole, preset.key)
            self.filter_preset_list.addItem(it)
        self.filter_preset_list.itemClicked.connect(self._on_filter_preset_clicked)
        filter_layout.addWidget(self.filter_preset_list)
        self.asset_tabs.addTab(filter_tab, "🎨 Filters")

        left_layout.addWidget(self.asset_tabs)
        upper_row.addWidget(left_frame, stretch=3)

        # 2. Center Pane: Player-Timeline 01 (Live Stage Canvas + Bottom Transport Bar)
        player_frame = QFrame()
        self.player_frame = player_frame
        player_frame.setStyleSheet(
            "QFrame { background-color: #12151e; border: 1px solid #1e293b; border-radius: 10px; }"
        )
        player_layout = QVBoxLayout(player_frame)
        player_layout.setContentsMargins(10, 8, 10, 8)
        player_layout.setSpacing(6)

        player_hdr = QHBoxLayout()
        lbl_player = QLabel("Player-Timeline 01")
        lbl_player.setStyleSheet("color: #cbd5e1; font-weight: bold; font-size: 12px; border: none;")
        player_hdr.addWidget(lbl_player)
        player_hdr.addStretch(1)

        self.btn_toggle_left_pane = QPushButton("◧")
        self.btn_toggle_left_pane.setCheckable(True)
        self.btn_toggle_left_pane.setChecked(True)
        self.btn_toggle_left_pane.setFixedWidth(28)
        self.btn_toggle_left_pane.setToolTip("Collapse or expand the Left Media/Effects Browser column.")
        self.btn_toggle_left_pane.toggled.connect(lambda checked: self.left_frame.setVisible(checked))
        player_hdr.addWidget(self.btn_toggle_left_pane)

        self.btn_toggle_right_pane = QPushButton("◨")
        self.btn_toggle_right_pane.setCheckable(True)
        self.btn_toggle_right_pane.setChecked(True)
        self.btn_toggle_right_pane.setFixedWidth(28)
        self.btn_toggle_right_pane.setToolTip("Collapse or expand the Right Details & Clip Inspector column.")
        self.btn_toggle_right_pane.toggled.connect(lambda checked: self.details_frame.setVisible(checked))
        player_hdr.addWidget(self.btn_toggle_right_pane)

        self.btn_toggle_bottom_dock = QPushButton("⬓")
        self.btn_toggle_bottom_dock.setCheckable(True)
        self.btn_toggle_bottom_dock.setChecked(True)
        self.btn_toggle_bottom_dock.setFixedWidth(28)
        self.btn_toggle_bottom_dock.setToolTip("Collapse or expand the Bottom Multi-Track Timeline Dock row.")
        self.btn_toggle_bottom_dock.toggled.connect(lambda checked: self.timeline_dock.setVisible(checked))
        player_hdr.addWidget(self.btn_toggle_bottom_dock)

        self.btn_swap_backdrop = QPushButton("≡")
        self.btn_swap_backdrop.setFixedWidth(28)
        self.btn_swap_backdrop.setToolTip("Swap stage backdrop image or looping video clip.")
        self.btn_swap_backdrop.clicked.connect(self._on_swap_visual_asset)
        player_hdr.addWidget(self.btn_swap_backdrop)
        player_layout.addLayout(player_hdr)

        self.stage_canvas = VideoStageCanvas(self)
        player_layout.addWidget(self.stage_canvas, stretch=1)

        # Player Transport Bar
        player_transport = QHBoxLayout()
        self.lbl_timecode = QLabel("00:00:00 / 00:00:00")
        self.lbl_timecode.setStyleSheet(
            "color: #94a3b8; font-family: monospace; font-size: 11px; font-weight: 600; border: none;"
        )
        player_transport.addWidget(self.lbl_timecode)
        player_transport.addStretch(1)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setObjectName("PrimaryButton")
        self.btn_play.clicked.connect(self.toggle_playback)
        player_transport.addWidget(self.btn_play)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self.stop_playback)
        player_transport.addWidget(self.btn_stop)

        player_transport.addStretch(1)
        self.btn_ratio_badge = QPushButton("Ratio: 16:9")
        self.btn_ratio_badge.setToolTip("Toggle between 16:9 Widescreen and 9:16 Vertical Short.")
        self.btn_ratio_badge.clicked.connect(self._toggle_aspect_ratio)
        player_transport.addWidget(self.btn_ratio_badge)

        self.btn_popout = QPushButton("⛶ Pop-out")
        self.btn_popout.setToolTip("Open the full-screen modal Timeline & Canvas Editor dialog.")
        self.btn_popout.clicked.connect(self._on_open_modal_editor)
        player_transport.addWidget(self.btn_popout)

        player_layout.addLayout(player_transport)
        upper_row.addWidget(player_frame, stretch=4)

        # 3. Right Pane: Details & Clip Inspector
        details_frame = QFrame()
        self.details_frame = details_frame
        details_frame.setStyleSheet(
            "QFrame { background-color: #12151e; border: 1px solid #1e293b; border-radius: 10px; }"
        )
        details_layout = QVBoxLayout(details_frame)
        details_layout.setContentsMargins(12, 8, 12, 8)
        details_layout.setSpacing(6)

        lbl_details = QLabel("Details")
        lbl_details.setStyleSheet("color: #06b6d4; font-weight: bold; font-size: 13px; border: none;")
        details_layout.addWidget(lbl_details)

        proj_meta_form = QFormLayout()
        proj_meta_form.setSpacing(4)

        self.channel_combo = QComboBox()
        self.channel_combo.setToolTip("Select the active YouTube channel profile.")
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        proj_meta_form.addRow("Channel:", self.channel_combo)

        self.project_combo = QComboBox()
        self.project_combo.setToolTip("Select the production project to edit on the multi-track timeline.")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        proj_meta_form.addRow("Project:", self.project_combo)

        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["16:9 Widescreen", "9:16 Vertical Short"])
        self.aspect_combo.setToolTip("Switch the Player stage monitor between 16:9 YouTube and 9:16 Vertical Short.")
        self.aspect_combo.currentIndexChanged.connect(self._sync_stage_canvas)
        proj_meta_form.addRow("Ratio:", self.aspect_combo)

        self.lbl_detail_name = QLabel("—")
        self.lbl_detail_name.setStyleSheet("color: #f8fafc; font-weight: 600; border: none;")
        proj_meta_form.addRow("Name:", self.lbl_detail_name)

        self.lbl_detail_saved = QLabel(str(get_settings().resolved_output_dir()))
        self.lbl_detail_saved.setWordWrap(True)
        self.lbl_detail_saved.setStyleSheet("color: #94a3b8; font-size: 10px; border: none;")
        proj_meta_form.addRow("Saved:", self.lbl_detail_saved)

        self.lbl_detail_ratio = QLabel("16:9 (1920x1080 · 30.00fps)")
        self.lbl_detail_ratio.setStyleSheet("color: #cbd5e1; font-size: 11px; border: none;")
        proj_meta_form.addRow("Format:", self.lbl_detail_ratio)
        details_layout.addLayout(proj_meta_form)

        # Selected Clip Precision Inspector
        insp_group = QGroupBox("Selected Clip Inspector")
        self.insp_group = insp_group
        insp_form = QFormLayout(insp_group)
        insp_form.setSpacing(5)

        self.lbl_selected_clip = QLabel("No clip selected")
        self.lbl_selected_clip.setStyleSheet("color: #22d3ee; font-weight: 600;")
        insp_form.addRow("Active Clip:", self.lbl_selected_clip)

        self.spin_trim_start = QSpinBox()
        self.spin_trim_start.setRange(0, 36_000_000)
        self.spin_trim_start.setSingleStep(250)
        self.spin_trim_start.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Trim In (ms):", self.spin_trim_start)

        self.spin_trim_end = QSpinBox()
        self.spin_trim_end.setRange(0, 36_000_000)
        self.spin_trim_end.setSingleStep(250)
        self.spin_trim_end.setSpecialValueText("Full End (0)")
        self.spin_trim_end.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Trim Out (ms):", self.spin_trim_end)

        self.spin_gain = QDoubleSpinBox()
        self.spin_gain.setRange(-24.0, 24.0)
        self.spin_gain.setSingleStep(0.5)
        self.spin_gain.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Gain (dB):", self.spin_gain)

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
        insp_form.addRow("Transition:", self.combo_transition)

        self.spin_overlap = QSpinBox()
        self.spin_overlap.setRange(0, 30_000)
        self.spin_overlap.setSingleStep(500)
        self.spin_overlap.valueChanged.connect(self._on_inspector_changed)
        insp_form.addRow("Overlap (ms):", self.spin_overlap)

        details_layout.addWidget(insp_group, stretch=1)

        self.btn_save_modify = QPushButton("💾 Modify & Save Timeline")
        self.btn_save_modify.setObjectName("PrimaryButton")
        self.btn_save_modify.setToolTip("Persist all clip trims, gains, fades, and reorderings to the database.")
        self.btn_save_modify.clicked.connect(self._on_save_changes)
        details_layout.addWidget(self.btn_save_modify)

        upper_row.addWidget(details_frame, stretch=3)
        root.addLayout(upper_row, stretch=3)

        # Bottom Full-Width Multi-Track Timeline Dock + Floating EditPilot Action Bar
        timeline_dock = QFrame()
        self.timeline_dock = timeline_dock
        timeline_dock.setStyleSheet(
            "QFrame { background-color: #0d1017; border: 1px solid #1e293b; border-radius: 8px; }"
        )
        dock_layout = QVBoxLayout(timeline_dock)
        dock_layout.setContentsMargins(10, 6, 10, 8)
        dock_layout.setSpacing(6)

        tbar = QHBoxLayout()
        btn_set_in = QPushButton("⇤ Set In at Playhead")
        btn_set_in.clicked.connect(self._on_set_in_at_playhead)
        tbar.addWidget(btn_set_in)

        btn_set_out = QPushButton("⇥ Set Out at Playhead")
        btn_set_out.clicked.connect(self._on_set_out_at_playhead)
        tbar.addWidget(btn_set_out)

        btn_reset = QPushButton("↺ Reset Trim")
        btn_reset.clicked.connect(self._on_reset_clip_trim)
        tbar.addWidget(btn_reset)

        btn_left = QPushButton("← Earlier")
        btn_left.clicked.connect(lambda: self._on_move_selected_clip(-1))
        tbar.addWidget(btn_left)

        btn_right = QPushButton("→ Later")
        btn_right.clicked.connect(lambda: self._on_move_selected_clip(1))
        tbar.addWidget(btn_right)

        btn_del = QPushButton("🗑 Delete")
        btn_del.clicked.connect(self._on_delete_selected_clip)
        tbar.addWidget(btn_del)

        btn_harmonic = QPushButton("🎵 Harmonic Sort")
        btn_harmonic.setToolTip("Reorder tracks by BPM and Camelot Key compatibility.")
        btn_harmonic.clicked.connect(self._on_harmonic_sort)
        tbar.addWidget(btn_harmonic)

        tbar.addStretch(1)

        # Floating-style EditPilot pill button (matches bottom-right of Screenshots 1 & 2!)
        self.btn_edit_pilot = QPushButton("✦ EditPilot")
        self.btn_edit_pilot.setStyleSheet(
            "QPushButton { background-color: #1e293b; color: #22d3ee; font-weight: bold; "
            "padding: 5px 14px; border-radius: 14px; border: 1px solid #06b6d4; } "
            "QPushButton:hover { background-color: #06b6d4; color: #042f2e; }"
        )
        self.btn_edit_pilot.setToolTip(
            "EditPilot Assistant: Auto-populate tracks, trim silence, harmonic-sort by BPM/Key, and save."
        )
        self.btn_edit_pilot.clicked.connect(self._on_editpilot_autoload)
        tbar.addWidget(self.btn_edit_pilot)

        dock_layout.addLayout(tbar)

        self.timeline_widget = MultiTrackTimelineWidget(
            self,
            on_clip_selected=self._on_timeline_clip_selected,
            on_playhead_scrubbed=self._on_playhead_scrubbed,
            on_clip_trimmed=self._on_timeline_clip_trimmed_by_drag,
        )
        dock_layout.addWidget(self.timeline_widget, stretch=1)

        root.addWidget(timeline_dock, stretch=2)

    def refresh(self) -> None:
        from youtube_studio.config import get_settings
        from youtube_studio.domain.models.media import MediaType
        from youtube_studio.domain.services import ChannelService

        self.lbl_detail_saved.setText(str(get_settings().resolved_output_dir()))
        try:
            with session_scope() as session:
                channels = ChannelService(session).list_active()
                audio_items = MediaLibraryService(session).list_media(media_type=MediaType.AUDIO)
        except Exception:
            return

        self.audio_lib_list.clear()
        for m in audio_items:
            from PySide6.QtWidgets import QListWidgetItem

            title = str(m.metadata.get("title") or Path(m.path).stem)
            bpm = m.metadata.get("bpm")
            camelot = m.metadata.get("camelot_code")
            badge = f" · {bpm} BPM · {camelot}" if bpm and camelot else ""
            it = QListWidgetItem(f"🎵 {title}{badge}")
            it.setData(Qt.ItemDataRole.UserRole, m.id)
            self.audio_lib_list.addItem(it)

        self.visual_media_list.clear()
        vis_dir = get_settings().resolved_data_dir() / "visual_assets"
        if vis_dir.exists():
            for p in sorted(vis_dir.iterdir()):
                if p.is_file() and not p.name.startswith("."):
                    from PySide6.QtWidgets import QListWidgetItem

                    it = QListWidgetItem(f"🖼 {p.name}")
                    it.setData(Qt.ItemDataRole.UserRole, str(p))
                    self.visual_media_list.addItem(it)

        prev_ch = self.current_channel_id()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self._channel_ids = []
        for ch in channels:
            self.channel_combo.addItem(ch.name)
            self._channel_ids.append(ch.id)
        if prev_ch in self._channel_ids:
            self.channel_combo.setCurrentIndex(self._channel_ids.index(prev_ch))
        self.channel_combo.blockSignals(False)
        self._reload_projects()

    def current_channel_id(self) -> Optional[str]:
        idx = self.channel_combo.currentIndex()
        if 0 <= idx < len(self._channel_ids):
            return self._channel_ids[idx]
        return None

    def current_project_id(self) -> Optional[str]:
        idx = self.project_combo.currentIndex()
        if 0 <= idx < len(self._project_ids):
            return self._project_ids[idx]
        return None

    def select_project(self, project_id: str) -> None:
        self.refresh()
        if project_id in self._project_ids:
            self.project_combo.setCurrentIndex(self._project_ids.index(project_id))
            self._load_project_timeline()

    def _on_channel_changed(self, _idx: int) -> None:
        self._reload_projects()

    def _reload_projects(self) -> None:
        ch_id = self.current_channel_id()
        prev_proj = self.current_project_id()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self._project_ids = []
        if ch_id:
            with session_scope() as session:
                projects = ProjectService(session).list_projects(channel_id=ch_id)
            for p in projects:
                self.project_combo.addItem(p.name)
                self._project_ids.append(p.id)
            if prev_proj in self._project_ids:
                self.project_combo.setCurrentIndex(self._project_ids.index(prev_proj))
        self.project_combo.blockSignals(False)
        self._load_project_timeline()

    def _on_project_changed(self, _idx: int) -> None:
        self._load_project_timeline()

    def _load_project_timeline(self) -> None:
        proj_id = self.current_project_id()
        self._clips = []
        if not proj_id:
            self.lbl_detail_name.setText("No project selected")
            self.timeline_widget.set_timeline_data([])
            self.empty_state.setVisible(True)
            self._sync_stage_canvas()
            return

        with session_scope() as session:
            proj_svc = ProjectService(session)
            media_svc = MediaLibraryService(session)
            proj = proj_svc.get_project(proj_id)
            if proj:
                self.lbl_detail_name.setText(proj.name)
            tracks = proj_svc.list_tracks(proj_id)
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

        self.empty_state.setVisible(len(self._clips) == 0)
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
        if hasattr(self, "insp_group") and hasattr(self.insp_group, "set_collapsed"):
            self.insp_group.set_collapsed(False)  # type: ignore[attr-defined]
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
        self.btn_ratio_badge.setText(f"Ratio: {aspect}")
        res_txt = "1080x1920 · 30.00fps" if aspect == "9:16" else "1920x1080 · 30.00fps"
        self.lbl_detail_ratio.setText(f"{aspect} ({res_txt})")
        self.stage_canvas.set_stage_state(
            playhead_ms=pos_ms,
            total_duration_ms=tot_ms,
            now_playing_text=now_title,
            visualizer_style=self._visualizer_style,
            show_now_playing=self.chk_stage_now_playing.isChecked(),
            show_progress_bar=self.chk_stage_progress.isChecked(),
            aspect_mode=aspect,
        )
        self.lbl_timecode.setText(
            f"00:{MultiTrackTimelineWidget._format_mm_ss(pos_ms)} / 00:{MultiTrackTimelineWidget._format_mm_ss(tot_ms)}"
        )

    def _toggle_aspect_ratio(self) -> None:
        self.aspect_combo.setCurrentIndex(1 if self.aspect_combo.currentIndex() == 0 else 0)

    def _on_visualizer_style_changed(self, style: str) -> None:
        self._visualizer_style = style
        self._sync_stage_canvas()

    def _on_playhead_scrubbed(self, pos_ms: int) -> None:
        self._sync_stage_canvas()
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._seek_player_to_timeline_ms(pos_ms)

    def toggle_playback(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.stage_canvas.set_playing(False)
            self.btn_play.setText("▶ Resume")
            return
        self._seek_player_to_timeline_ms(self.timeline_widget.playhead_ms(), start_play=True)

    def stop_playback(self) -> None:
        self._player.stop()
        self.stage_canvas.set_playing(False)
        self.btn_play.setText("▶ Play")

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
            self.btn_play.setText("⏸ Pause")

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

    def _apply_transition_to_all(self, transition_type: str, overlap_ms: int) -> None:
        for c in self._clips:
            c.transition_type = transition_type
            c.overlap_ms = overlap_ms
        sel = self.timeline_widget.selected_clip_index()
        self.timeline_widget.set_timeline_data(self._clips, selected_idx=sel)
        self._populate_inspector(sel)
        self._sync_stage_canvas()

    def _on_harmonic_sort(self) -> None:
        proj_id = self.current_project_id()
        if not proj_id:
            return
        self._on_save_changes(silent=True)
        with session_scope() as session:
            ProjectService(session).auto_harmonic_sort(proj_id)
        self._load_project_timeline()

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

    def _on_visual_item_activated(self, item) -> None:
        raw = item.data(Qt.ItemDataRole.UserRole)
        if raw and Path(str(raw)).exists():
            self._visual_asset_path = Path(str(raw))
            self.stage_canvas.set_background_asset(self._visual_asset_path)
            self.timeline_widget.set_timeline_data(
                self._clips,
                selected_idx=self.timeline_widget.selected_clip_index(),
                visual_label=self._visual_asset_path.name,
            )

    def _on_filter_preset_clicked(self, item) -> None:
        from youtube_studio.domain.models.channel import NICHE_STYLE_PRESETS

        key = str(item.data(Qt.ItemDataRole.UserRole) or "")
        preset = NICHE_STYLE_PRESETS.get(key)
        if preset:
            self._visualizer_style = preset.visualizer_style
            self.combo_stage_visualizer.setCurrentText(preset.visualizer_style)
            self.aspect_combo.setCurrentIndex(1 if preset.default_aspect_ratio == "9:16" else 0)
            self._sync_stage_canvas()

    def _on_import_media_dialog(self) -> None:
        import shutil
        from youtube_studio.config import get_settings
        from youtube_studio.media.scanner import MediaScanner

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Audio, Image, or Video Assets",
            str(Path.home()),
            "Media Files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.png *.jpg *.jpeg *.webp *.mp4 *.mov *.webm)",
        )
        if not files:
            return
        audio_exts = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".aiff", ".opus"}
        vis_dir = get_settings().resolved_data_dir() / "visual_assets"
        vis_dir.mkdir(parents=True, exist_ok=True)
        scanner = MediaScanner()
        added_audio_ids: list[str] = []
        with session_scope() as session:
            media_svc = MediaLibraryService(session)
            for f in files:
                p = Path(f)
                if p.suffix.lower() in audio_exts:
                    info = scanner.inspect_file(p)
                    saved = media_svc.upsert(info)
                    added_audio_ids.append(saved.id)
                else:
                    dest = vis_dir / p.name
                    if dest.resolve() != p.resolve():
                        shutil.copy2(p, dest)
                    self._visual_asset_path = dest
                    self.stage_canvas.set_background_asset(dest)
        if added_audio_ids:
            proj_id = self._ensure_project_exists()
            with session_scope() as session:
                proj_svc = ProjectService(session)
                for mid in added_audio_ids:
                    proj_svc.add_track(
                        proj_id,
                        mid,
                        transition_config=TransitionConfig(
                            transition_type=TransitionType.BASS_SWAP_EQ, overlap_ms=3000
                        ),
                    )
        self.refresh()

    def _on_add_selected_library_audio(self) -> None:
        item = self.audio_lib_list.currentItem()
        if not item:
            return
        mid = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not mid:
            return
        proj_id = self._ensure_project_exists()
        with session_scope() as session:
            ProjectService(session).add_track(
                proj_id,
                mid,
                transition_config=TransitionConfig(
                    transition_type=TransitionType.BASS_SWAP_EQ, overlap_ms=3000
                ),
            )
        self._load_project_timeline()

    def _ensure_project_exists(self) -> str:
        from youtube_studio.domain.models.project import ProjectType
        from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService

        ch_id = self.current_channel_id()
        proj_id = self.current_project_id()
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            if not ch_id:
                ch_id, _, _ = ap.ensure_active_channel()
            if not proj_id:
                proj = ProjectService(session).create_project(
                    ch_id, "Timeline Studio Project", project_type=ProjectType.MIX
                )
                proj_id = proj.id
        self.refresh()
        return proj_id

    def _on_editpilot_autoload(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from youtube_studio.domain.services.autopilot_service import ExpressAutopilotService

        proj_id = self._ensure_project_exists()
        with session_scope() as session:
            ap = ExpressAutopilotService(session)
            tracks = ap.resolve_tracks()
            if not tracks:
                QMessageBox.information(
                    self,
                    "EditPilot",
                    "Scan or upload audio files in the Music Library first, then click EditPilot.",
                )
                return
            proj_svc = ProjectService(session)
            existing = {t.media_file_id for t in proj_svc.list_tracks(proj_id)}
            for m in tracks:
                if m.id not in existing:
                    proj_svc.add_track(
                        proj_id,
                        m.id,
                        transition_config=TransitionConfig(
                            transition_type=TransitionType.BASS_SWAP_EQ, overlap_ms=3000
                        ),
                    )
            proj_svc.auto_cue_trim_tracks(proj_id)
            if len(proj_svc.list_tracks(proj_id)) > 1:
                proj_svc.auto_harmonic_sort(proj_id)
        self._load_project_timeline()
        self.lbl_autosave.setText("● Auto saved: EditPilot synced")

    def _on_run_ai_clipper(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        from youtube_studio.config import get_settings
        from youtube_studio.jobs.runner import sanitize_output_name
        from youtube_studio.media.shorts_clipper import ShortsClipperService

        proj_id = self.current_project_id()
        if not proj_id or not self._clips:
            QMessageBox.warning(self, "AI Clipper", "Add at least one audio clip to the timeline first.")
            return
        first_clip = self._clips[0]
        out_name = sanitize_output_name(self.lbl_detail_name.text().strip() or "short_clip")
        out_dir = get_settings().resolved_output_dir() / out_name / "shorts"
        try:
            short_res = ShortsClipperService().create_highlight_short(
                Path(first_clip.file_path),
                out_dir,
                title=first_clip.title,
                output_name=out_name,
                source_duration_ms=first_clip.source_duration_ms,
            )
            QMessageBox.information(
                self,
                "✂️ AI Clipper Complete",
                f"Extracted peak 30s 9:16 Short ({short_res.start_ms}ms – {short_res.end_ms}ms):\n\n"
                f"Video: {short_res.video_path}\nThumbnail: {short_res.thumbnail_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "AI Clipper Failed", str(exc))

    def _on_save_changes(self, *, silent: bool = False) -> None:
        from PySide6.QtWidgets import QMessageBox

        proj_id = self.current_project_id()
        if not proj_id:
            return
        self.stop_playback()
        with session_scope() as session:
            proj_svc = ProjectService(session)
            existing_tracks = {t.id: t for t in proj_svc.list_tracks(proj_id)}
            kept_ids = {c.track_id for c in self._clips}
            for tid in list(existing_tracks.keys()):
                if tid not in kept_ids:
                    proj_svc.remove_track(tid)
            ordered_ids = [c.track_id for c in self._clips if c.track_id in existing_tracks]
            if ordered_ids:
                proj_svc.reorder_tracks(proj_id, ordered_ids)
            refreshed = {t.id: t for t in proj_svc.list_tracks(proj_id)}
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
        self.lbl_autosave.setText("● Auto saved: Just now")
        if not silent:
            QMessageBox.information(
                self,
                "Timeline Saved",
                f"Saved {len(self._clips)} timeline clip edits to project.",
            )

    def _on_export_timeline_package(self) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QMessageBox
        from youtube_studio.config import get_settings
        from youtube_studio.jobs.runner import sanitize_output_name
        from youtube_studio.media.nle_exporter import NLEExporterService

        proj_id = self.current_project_id()
        if not proj_id:
            QMessageBox.warning(self, "Export", "Select or create a project first.")
            return
        self._on_save_changes(silent=True)
        out_name = sanitize_output_name(self.lbl_detail_name.text().strip() or proj_id)
        out_dir = get_settings().resolved_output_dir() / out_name
        try:
            with session_scope() as session:
                bundle = NLEExporterService(session).export_project_timeline(
                    proj_id,
                    out_dir,
                    output_name=out_name,
                    visual_asset_path=self._visual_asset_path,
                )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(bundle.output_dir)))
            QMessageBox.information(
                self,
                "Timeline Exported",
                f"Exported {bundle.clip_count}-clip timeline bundle to:\n  {bundle.output_dir}\n\n"
                f"• FCPXML: {bundle.fcpxml_path.name}\n"
                f"• CMX 3600 EDL: {bundle.edl_path.name}\n"
                f"• CSV Clip List: {bundle.csv_clip_list_path.name}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _on_open_modal_editor(self) -> None:
        proj_id = self._ensure_project_exists()
        dlg = TimelineCanvasEditorDialog(
            self,
            project_id=proj_id,
            visual_asset_path=self._visual_asset_path,
            visualizer_style=self._visualizer_style,
            on_saved=self._load_project_timeline,
        )
        dlg.exec()

    def _navigate_to_page(self, page_key: str) -> None:
        win = self.window()
        nav_items = getattr(win, "NAV_ITEMS", None)
        nav_widget = getattr(win, "nav", None)
        if nav_items and nav_widget:
            for idx, (_, key, _) in enumerate(nav_items):
                if key == page_key:
                    nav_widget.setCurrentRow(idx)
                    break

