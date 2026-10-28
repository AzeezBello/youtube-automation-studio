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
    """Compact, collapsible empty-state guide banner that stays out of the way of primary tools."""

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
        self._details_expanded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.toggle_btn = QPushButton("▶")
        self.toggle_btn.setFixedSize(24, 24)
        self.toggle_btn.setToolTip("Show or hide quick-start tips for this workspace.")
        self.toggle_btn.clicked.connect(self.toggle_details)
        header_row.addWidget(self.toggle_btn)

        title_lbl = QLabel(f"✦  {title}")
        title_lbl.setObjectName("EmptyStateTitle")
        title_lbl.setFont(QFont("", 12, QFont.Weight.Bold))
        header_row.addWidget(title_lbl, stretch=1)

        if action_label and on_action:
            safe_action = action_label.replace("&", "&&") if "&&" not in action_label else action_label
            self.action_btn = QPushButton(safe_action)
            self.action_btn.setObjectName("PrimaryButton")
            if action_tooltip:
                self.action_btn.setToolTip(action_tooltip)
            self.action_btn.clicked.connect(on_action)
            header_row.addWidget(self.action_btn)
        else:
            self.action_btn = None

        if secondary_label and on_secondary:
            safe_secondary = (
                secondary_label.replace("&", "&&") if "&&" not in secondary_label else secondary_label
            )
            self.secondary_btn = QPushButton(safe_secondary)
            self.secondary_btn.setObjectName("AccentButton")
            if secondary_tooltip:
                self.secondary_btn.setToolTip(secondary_tooltip)
            self.secondary_btn.clicked.connect(on_secondary)
            header_row.addWidget(self.secondary_btn)
        else:
            self.secondary_btn = None

        layout.addLayout(header_row)

        # Collapsible details body (collapsed by default to keep screens clean and uncluttered)
        self.details_container = QWidget(self)
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setContentsMargins(28, 2, 4, 2)
        details_layout.setSpacing(4)

        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("EmptyStateDesc")
        desc_lbl.setWordWrap(True)
        details_layout.addWidget(desc_lbl)

        if tips:
            tips_html = "<ul style='margin-top:2px; margin-bottom:2px;'>" + "".join(
                f"<li>{tip}</li>" for tip in tips
            ) + "</ul>"
            tips_lbl = QLabel(tips_html)
            tips_lbl.setObjectName("EmptyStateTips")
            tips_lbl.setWordWrap(True)
            tips_lbl.setTextFormat(Qt.TextFormat.RichText)
            details_layout.addWidget(tips_lbl)

        self.details_container.setVisible(False)
        layout.addWidget(self.details_container)

    def toggle_details(self) -> None:
        self._details_expanded = not self._details_expanded
        self.details_container.setVisible(self._details_expanded)
        self.toggle_btn.setText("▼" if self._details_expanded else "▶")


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
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.value_label.setFont(QFont("", 18, QFont.Weight.Bold))
        layout.addWidget(self.value_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("MetricSubtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

    def set_metric(self, value: str, subtitle: str = "") -> None:
        self.value_label.setText(value)
        self.subtitle_label.setText(subtitle)
