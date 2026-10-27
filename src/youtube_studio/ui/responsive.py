"""Responsive layout utilities for adaptive Mobile (<840px), Tablet, and Desktop Qt viewports."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QScrollArea,
    QTableWidget,
    QWidget,
)

MOBILE_BREAKPOINT_PX = 840


def wrap_in_responsive_scroll(page: QWidget, parent: Optional[QWidget] = None) -> QScrollArea:
    """Wrap a workspace page in a frameless, vertically scrollable QScrollArea that always fits the viewport width."""
    page.setObjectName("WorkspacePage")
    scroll = QScrollArea(parent)
    scroll.setObjectName("WorkspaceScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(page)
    scroll.viewport().setObjectName("ScrollViewport")
    return scroll


def apply_responsive_mode_to_page(page: QWidget, is_mobile: bool) -> None:
    """Recursively adapt QBoxLayout directions and QTableWidget column visibility for mobile vs desktop."""
    direction = (
        QBoxLayout.Direction.TopToBottom
        if is_mobile
        else QBoxLayout.Direction.LeftToRight
    )

    # 1. Switch all QBoxLayouts that have multi-widget horizontal splits
    for box in page.findChildren(QBoxLayout):
        if bool(box.property("responsive_split")):
            box.setDirection(direction)

    # Also check top-level layout children if findChildren misses direct sub-layouts
    top_layout = page.layout()
    if isinstance(top_layout, QBoxLayout):
        _walk_and_adapt_layouts(top_layout, direction)

    # 2. Adapt QTableWidgets so narrow screens keep primary columns readable
    for table in page.findChildren(QTableWidget):
        col_count = table.columnCount()
        table.setMinimumHeight(210 if is_mobile else 160)
        if col_count >= 6:
            # Hide the last 2 detail/path columns on compact mobile widths
            table.setColumnHidden(col_count - 1, is_mobile)
            table.setColumnHidden(col_count - 2, is_mobile)
        elif col_count >= 4:
            table.setColumnHidden(col_count - 1, is_mobile)


def _walk_and_adapt_layouts(layout: QBoxLayout, direction: QBoxLayout.Direction) -> None:
    """Walk nested QBoxLayouts and flip any layout marked responsive_split or wide multi-panel rows."""
    if bool(layout.property("responsive_split")):
        layout.setDirection(direction)

    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        sub_layout = item.layout()
        if isinstance(sub_layout, QBoxLayout):
            # Automatically treat any originally LeftToRight layout with >= 2 items as responsive
            if sub_layout.property("responsive_split") is None:
                if (
                    sub_layout.direction() == QBoxLayout.Direction.LeftToRight
                    and sub_layout.count() >= 2
                ):
                    sub_layout.setProperty("responsive_split", True)
            if bool(sub_layout.property("responsive_split")):
                sub_layout.setDirection(direction)
            _walk_and_adapt_layouts(sub_layout, direction)
        w = item.widget()
        if w is not None and w.layout() is not None and isinstance(w.layout(), QBoxLayout):
            _walk_and_adapt_layouts(w.layout(), direction)  # type: ignore[arg-type]
