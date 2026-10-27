"""Reusable UI components: EmptyStateWidget, MetricCard, and helper builders."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class EmptyStateWidget(QFrame):
    """Friendly empty-state guide card displayed on blank screens before data is added."""

    def __init__(
        self,
        title: str,
        description: str,
        tips: list[str],
        *,
        action_label: Optional[str] = None,
        action_tooltip: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
        secondary_label: Optional[str] = None,
        secondary_tooltip: Optional[str] = None,
        on_secondary: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyStateCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        title_lbl = QLabel(f"✦  {title}")
        title_lbl.setFont(QFont("", 14, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #a5b4fc;")
        header_row.addWidget(title_lbl, stretch=1)

        if action_label and on_action:
            self.action_btn = QPushButton(action_label)
            self.action_btn.setObjectName("PrimaryButton")
            if action_tooltip:
                self.action_btn.setToolTip(action_tooltip)
            self.action_btn.clicked.connect(on_action)
            header_row.addWidget(self.action_btn)
        else:
            self.action_btn = None

        if secondary_label and on_secondary:
            self.secondary_btn = QPushButton(secondary_label)
            self.secondary_btn.setObjectName("AccentButton")
            if secondary_tooltip:
                self.secondary_btn.setToolTip(secondary_tooltip)
            self.secondary_btn.clicked.connect(on_secondary)
            header_row.addWidget(self.secondary_btn)
        else:
            self.secondary_btn = None

        layout.addLayout(header_row)

        desc_lbl = QLabel(description)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #cbd5e1;")
        layout.addWidget(desc_lbl)

        if tips:
            tips_html = "<ul style='margin-top:4px; margin-bottom:2px; color:#94a3b8;'>" + "".join(
                f"<li>{tip}</li>" for tip in tips
            ) + "</ul>"
            tips_lbl = QLabel(tips_html)
            tips_lbl.setWordWrap(True)
            tips_lbl.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(tips_lbl)


class MetricCard(QFrame):
    """Compact KPI metric card for the Dashboard."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        subtitle: str = "",
        tooltip: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MetricCard")
        if tooltip:
            self.setToolTip(tooltip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: 600;")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setFont(QFont("", 20, QFont.Weight.Bold))
        self.value_label.setStyleSheet("color: #f8fafc;")
        layout.addWidget(self.value_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(self.subtitle_label)

    def set_metric(self, value: str, subtitle: str = "") -> None:
        self.value_label.setText(value)
        self.subtitle_label.setText(subtitle)
