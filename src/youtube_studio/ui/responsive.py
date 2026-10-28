"""Responsive & Collapsible layout utilities — zero horizontal scrolling, collapsible sections, rows & columns."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QBoxLayout,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayoutItem,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QWidget,
)

MOBILE_BREAKPOINT_PX = 960
_HEADER_CLICK_HEIGHT_PX = 30

# Keywords identifying secondary/advanced sections that should start collapsed (▶) by default
_DEFAULT_COLLAPSED_SECTION_KEYWORDS: tuple[str, ...] = (
    "selected track & harmonic transition",
    "selected clip inspector",
    "video background asset",
    "system environment",
    "studio diagnostics",
    "watchlist",
    "external mcp servers",
    "tool playground",
    "sqlite backup",
)


class _GroupBoxCollapseFilter(QObject):
    """Event filter that toggles a QGroupBox between expanded (▼) and collapsed (▶) when its header is clicked."""

    def __init__(self, group_box: QGroupBox) -> None:
        super().__init__(group_box)
        self._box = group_box

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._box and event.type() == QEvent.Type.MouseButtonPress:
            mouse_ev = event  # type: ignore[assignment]
            if isinstance(mouse_ev, QMouseEvent) and mouse_ev.button() == Qt.MouseButton.LeftButton:
                if mouse_ev.position().y() <= _HEADER_CLICK_HEIGHT_PX:
                    toggle_groupbox_collapsed(self._box)
                    return True
        return super().eventFilter(watched, event)


def make_groupbox_collapsible(group_box: QGroupBox, *, start_collapsed: bool = False) -> None:
    """Enable click-to-collapse on a QGroupBox header and attach helper methods."""
    if not bool(group_box.property("_collapsible_installed")):
        raw_title = group_box.title().strip()
        for prefix in ("▼  ", "▶  ", "▼ ", "▶ "):
            if raw_title.startswith(prefix):
                raw_title = raw_title[len(prefix) :].strip()
        group_box.setProperty("_base_title", raw_title)
        group_box.setProperty("_is_collapsed", False)
        group_box.setProperty("_collapsible_installed", True)
        if raw_title:
            group_box.setTitle(f"▼  {raw_title}")
        tip = group_box.toolTip().strip()
        collapse_hint = "Click section header (▼/▶) to collapse or expand."
        group_box.setToolTip(f"{tip}\n{collapse_hint}".strip() if tip else collapse_hint)

        flt = _GroupBoxCollapseFilter(group_box)
        group_box.installEventFilter(flt)
        group_box.setProperty("_collapse_filter_ref", flt)

        setattr(group_box, "set_collapsed", lambda c, gb=group_box: set_groupbox_collapsed(gb, c))
        setattr(group_box, "toggle_collapsed", lambda gb=group_box: toggle_groupbox_collapsed(gb))
        setattr(group_box, "is_collapsed", lambda gb=group_box: is_groupbox_collapsed(gb))

    if start_collapsed:
        set_groupbox_collapsed(group_box, True)


def is_groupbox_collapsed(group_box: QGroupBox) -> bool:
    """Return True if the QGroupBox is currently collapsed."""
    return bool(group_box.property("_is_collapsed"))


def toggle_groupbox_collapsed(group_box: QGroupBox) -> bool:
    """Toggle a QGroupBox between collapsed and expanded states and return the new collapsed state."""
    new_state = not is_groupbox_collapsed(group_box)
    set_groupbox_collapsed(group_box, new_state)
    return new_state


def set_groupbox_collapsed(group_box: QGroupBox, collapsed: bool) -> None:
    """Collapse or expand a QGroupBox by hiding/showing its child widgets and shrinking its height."""
    if not bool(group_box.property("_collapsible_installed")):
        make_groupbox_collapsible(group_box)

    base_title = str(group_box.property("_base_title") or group_box.title()).strip()
    group_box.setProperty("_is_collapsed", bool(collapsed))

    if collapsed:
        if base_title:
            group_box.setTitle(f"▶  {base_title}")
        for child in group_box.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setVisible(False)
        group_box.setMinimumHeight(30)
        group_box.setMaximumHeight(32)
    else:
        if base_title:
            group_box.setTitle(f"▼  {base_title}")
        for child in group_box.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            child.setVisible(True)
        group_box.setMinimumHeight(0)
        group_box.setMaximumHeight(16777215)


def _set_layout_tree_widgets_visible(item: QLayoutItem, visible: bool) -> None:
    """Recursively show or hide all widgets inside a QLayoutItem (widget or nested layout)."""
    w = item.widget()
    if w is not None:
        w.setVisible(visible)
        return
    sub = item.layout()
    if sub is not None:
        for i in range(sub.count()):
            child_item = sub.itemAt(i)
            if child_item is not None:
                _set_layout_tree_widgets_visible(child_item, visible)


def set_layout_item_collapsed(layout: QBoxLayout, index: int, collapsed: bool) -> None:
    """Collapse or expand a specific column or row index inside a QBoxLayout."""
    if index < 0 or index >= layout.count():
        return
    item = layout.itemAt(index)
    if item is None:
        return
    orig_key = f"_orig_stretch_{index}"
    if collapsed:
        if layout.property(orig_key) is None:
            layout.setProperty(orig_key, max(1, layout.stretch(index)))
        _set_layout_tree_widgets_visible(item, False)
        layout.setStretch(index, 0)
    else:
        _set_layout_tree_widgets_visible(item, True)
        saved_stretch = layout.property(orig_key)
        if saved_stretch is not None:
            layout.setStretch(index, int(saved_stretch))


def _find_primary_columns_layout(page: QWidget) -> Optional[QBoxLayout]:
    """Locate the main multi-column LeftToRight QBoxLayout on a workspace page, if any."""
    top = page.layout()
    if not isinstance(top, QBoxLayout):
        return None
    best: Optional[QBoxLayout] = None
    best_score = 0
    for i in range(top.count()):
        item = top.itemAt(i)
        if item is None:
            continue
        sub = item.layout()
        if isinstance(sub, QBoxLayout) and sub.direction() == QBoxLayout.Direction.LeftToRight:
            if sub.count() >= 2:
                score = sub.count() * 10 + max(1, top.stretch(i))
                if score > best_score:
                    best = sub
                    best_score = score
    return best


def enforce_no_horizontal_scroll(page: QWidget) -> None:
    """Eliminate horizontal scrollbars and prevent wide widgets from overflowing any page."""
    page.setMinimumWidth(0)
    page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    # 1. Prevent QComboBoxes from forcing wide minimum widths based on long item strings
    for combo in page.findChildren(QComboBox):
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(6)
        combo.setMinimumWidth(50)

    # 2. Prevent QLineEdits from demanding wide minimum widths
    for edit in page.findChildren(QLineEdit):
        edit.setMinimumWidth(40)

    # 3. Disable horizontal scrollbars on all scroll areas, tables, lists, and text editors
    for area in page.findChildren(QAbstractScrollArea):
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # 4. Make every QTableWidget fit 100% of its available width without sideways scrolling
    for table in page.findChildren(QTableWidget):
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(True)
        col_count = table.columnCount()
        for c in range(col_count):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        # Keep index '#' column compact if present
        if col_count >= 2 and table.horizontalHeaderItem(0) is not None:
            first_lbl = table.horizontalHeaderItem(0).text().strip()
            if first_lbl in {"#", "ID"}:
                hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
                table.setColumnWidth(0, 32)


class CollapsibleLayoutBar(QFrame):
    """Minimalist inline pill strip for collapsing/expanding columns, stacking vertically, and collapsing sections."""

    def __init__(self, page: QWidget, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent or page)
        self._page = page
        self._cols_layout: Optional[QBoxLayout] = _find_primary_columns_layout(page)
        self.setObjectName("CollapsibleLayoutBar")
        self.setStyleSheet(
            "QFrame#CollapsibleLayoutBar { background: transparent; border: none; } "
            "QPushButton { "
            "background-color: #141824; color: #94a3b8; border: 1px solid #1e293b; "
            "border-radius: 5px; padding: 2px 7px; font-size: 11px; "
            "} "
            "QPushButton:checked { background-color: #162436; color: #22d3ee; border-color: #0891b2; } "
            "QPushButton:hover { border-color: #38bdf8; color: #f8fafc; }"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self.col_buttons: list[QPushButton] = []
        if self._cols_layout is not None:
            self.btn_stack_vertical = QPushButton("⇅ Stack")
            self.btn_stack_vertical.setCheckable(True)
            self.btn_stack_vertical.setChecked(False)
            self.btn_stack_vertical.setToolTip(
                "Stack columns vertically (top-to-bottom) so every panel gets 100% full width with zero side-by-side squeezing."
            )
            self.btn_stack_vertical.toggled.connect(self._on_toggle_stack_vertical)
            row.addWidget(self.btn_stack_vertical)

            col_count = self._cols_layout.count()
            col_labels = (
                [("◧ Left", "Toggle Left Column"), ("◨ Right", "Toggle Right Column")]
                if col_count == 2
                else [
                    ("◧ Media", "Toggle Left Media Column"),
                    ("▣ Player", "Toggle Center Player Column"),
                    ("◨ Details", "Toggle Right Details Column"),
                ]
                if col_count == 3
                else [(f"Col {i + 1}", f"Toggle Column {i + 1}") for i in range(col_count)]
            )
            for idx, (text, tip) in enumerate(col_labels):
                btn = QPushButton(text)
                btn.setCheckable(True)
                btn.setChecked(True)
                btn.setToolTip(tip)
                btn.toggled.connect(
                    lambda checked, c_idx=idx: self._on_toggle_column(c_idx, checked)
                )
                row.addWidget(btn)
                self.col_buttons.append(btn)

        self.btn_collapse_all_sections = QPushButton("▲ Compact")
        self.btn_collapse_all_sections.setToolTip("Collapse all section cards on this page for a clean compact view.")
        self.btn_collapse_all_sections.clicked.connect(lambda: self.set_all_sections_collapsed(True))
        row.addWidget(self.btn_collapse_all_sections)

        self.btn_expand_all_sections = QPushButton("▼ Expand")
        self.btn_expand_all_sections.setToolTip("Expand all sections and columns on this page.")
        self.btn_expand_all_sections.clicked.connect(self.expand_everything)
        row.addWidget(self.btn_expand_all_sections)

    def _on_toggle_stack_vertical(self, stacked: bool) -> None:
        if self._cols_layout is None:
            return
        self._cols_layout.setProperty("_user_forced_stack", stacked)
        self._cols_layout.setDirection(
            QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight
        )

    def _on_toggle_column(self, col_idx: int, visible: bool) -> None:
        if self._cols_layout is None:
            return
        if not visible and all(
            not b.isChecked() for i, b in enumerate(self.col_buttons) if i != col_idx
        ):
            self.col_buttons[col_idx].blockSignals(True)
            self.col_buttons[col_idx].setChecked(True)
            self.col_buttons[col_idx].blockSignals(False)
            return
        set_layout_item_collapsed(self._cols_layout, col_idx, collapsed=not visible)

    def set_all_sections_collapsed(self, collapsed: bool) -> None:
        for gb in self._page.findChildren(QGroupBox):
            set_groupbox_collapsed(gb, collapsed)

    def expand_everything(self) -> None:
        self.set_all_sections_collapsed(False)
        for idx, btn in enumerate(self.col_buttons):
            if not btn.isChecked():
                btn.setChecked(True)
            elif self._cols_layout is not None:
                set_layout_item_collapsed(self._cols_layout, idx, collapsed=False)


def enable_collapsible_sections_and_panes(page: QWidget) -> Optional[CollapsibleLayoutBar]:
    """Install click-to-collapse on all QGroupBoxes, eliminate horizontal scrolling, and attach inline toggle pills."""
    enforce_no_horizontal_scroll(page)

    for gb in page.findChildren(QGroupBox):
        title_lower = gb.title().lower()
        should_collapse = any(kw in title_lower for kw in _DEFAULT_COLLAPSED_SECTION_KEYWORDS)
        make_groupbox_collapsible(gb, start_collapsed=should_collapse)

    if getattr(page, "collapsible_bar", None) is not None:
        return getattr(page, "collapsible_bar")

    top_layout = page.layout()
    if isinstance(top_layout, QBoxLayout) and top_layout.count() > 0:
        bar = CollapsibleLayoutBar(page, parent=page)
        first_item = top_layout.itemAt(0)
        first_widget = first_item.widget() if first_item is not None else None
        if isinstance(first_widget, QLabel):
            top_layout.removeWidget(first_widget)
            hdr_row = QHBoxLayout()
            hdr_row.setContentsMargins(0, 0, 0, 0)
            hdr_row.addWidget(first_widget, stretch=1)
            hdr_row.addWidget(bar)
            top_layout.insertLayout(0, hdr_row)
        else:
            top_layout.insertWidget(0, bar)
        setattr(page, "collapsible_bar", bar)
        return bar
    return None


def wrap_in_responsive_scroll(page: QWidget, parent: Optional[QWidget] = None) -> QScrollArea:
    """Wrap a workspace page in a frameless, vertically scrollable QScrollArea with zero horizontal scroll."""
    page.setObjectName("WorkspacePage")
    enable_collapsible_sections_and_panes(page)
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
    """Recursively adapt QBoxLayout directions and QTableWidget column visibility so nothing ever overflows horizontally."""
    enforce_no_horizontal_scroll(page)

    direction = (
        QBoxLayout.Direction.TopToBottom
        if is_mobile
        else QBoxLayout.Direction.LeftToRight
    )

    # 1. Switch all QBoxLayouts that have multi-widget horizontal splits
    for box in page.findChildren(QBoxLayout):
        if bool(box.property("_user_forced_stack")):
            box.setDirection(QBoxLayout.Direction.TopToBottom)
        elif bool(box.property("responsive_split")):
            box.setDirection(direction)

    top_layout = page.layout()
    if isinstance(top_layout, QBoxLayout):
        _walk_and_adapt_layouts(top_layout, direction)

    # 2. Keep QTableWidgets clean and never horizontally scrolling
    for table in page.findChildren(QTableWidget):
        col_count = table.columnCount()
        table.setMinimumHeight(180 if is_mobile else 145)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if col_count >= 7:
            # Always hide secondary numeric detail columns (Trim, Gain, Fade) that belong in the right-side Inspector
            table.setColumnHidden(3, True)
            table.setColumnHidden(4, True)
            table.setColumnHidden(5, True)
        elif col_count == 6:
            table.setColumnHidden(4, True)
            table.setColumnHidden(5, True)
        elif col_count >= 4 and is_mobile:
            table.setColumnHidden(col_count - 1, True)


def _walk_and_adapt_layouts(layout: QBoxLayout, direction: QBoxLayout.Direction) -> None:
    """Walk nested QBoxLayouts and flip any layout marked responsive_split or wide multi-panel rows."""
    if bool(layout.property("_user_forced_stack")):
        layout.setDirection(QBoxLayout.Direction.TopToBottom)
    elif bool(layout.property("responsive_split")):
        layout.setDirection(direction)

    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        sub_layout = item.layout()
        if isinstance(sub_layout, QBoxLayout):
            if sub_layout.property("responsive_split") is None:
                if (
                    sub_layout.direction() == QBoxLayout.Direction.LeftToRight
                    and sub_layout.count() >= 2
                ):
                    # Only mark major multi-column body splits (those containing sub-layouts or GroupBoxes/Frames)
                    has_panel_child = any(
                        sub_layout.itemAt(j) is not None
                        and (
                            sub_layout.itemAt(j).layout() is not None
                            or isinstance(sub_layout.itemAt(j).widget(), (QGroupBox, QFrame))
                        )
                        for j in range(sub_layout.count())
                    )
                    if has_panel_child:
                        sub_layout.setProperty("responsive_split", True)
            if bool(sub_layout.property("_user_forced_stack")):
                sub_layout.setDirection(QBoxLayout.Direction.TopToBottom)
            elif bool(sub_layout.property("responsive_split")):
                sub_layout.setDirection(direction)
            _walk_and_adapt_layouts(sub_layout, direction)
        w = item.widget()
        if w is not None and w.layout() is not None and isinstance(w.layout(), QBoxLayout):
            _walk_and_adapt_layouts(w.layout(), direction)  # type: ignore[arg-type]
