"""Dark and Light Studio QSS themes and ThemeManager for YouTube Automation Studio."""

from __future__ import annotations

import json
from typing import Optional

from youtube_studio.config import get_settings

DARK_STUDIO_STYLESHEET = """
QMainWindow, QDialog, QScrollArea, QWidget#ScrollViewport, QWidget#WorkspacePage {
    background-color: #0f1117;
    color: #e6e9f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #e6e9f0;
}

/* Top Header Bar & Tour Banner */
QFrame#TopHeaderBar {
    background-color: #161923;
    border-bottom: 1px solid #262b3d;
}

QFrame#ProductTourBanner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e1b4b, stop:1 #172554);
    border: 1px solid #4f46e5;
    border-radius: 8px;
}

/* Metric Cards & Empty State Guide Cards */
QFrame#MetricCard {
    background-color: #171a24;
    border: 1px solid #262b3d;
    border-radius: 8px;
}

QLabel#MetricTitle {
    color: #94a3b8;
    font-size: 12px;
    font-weight: 600;
}

QLabel#MetricValue {
    color: #f8fafc;
}

QLabel#MetricSubtitle {
    color: #64748b;
    font-size: 11px;
}

QFrame#EmptyStateCard {
    background-color: #151822;
    border: 1px dashed #3b425c;
    border-radius: 10px;
}

QLabel#EmptyStateTitle {
    color: #a5b4fc;
}

QLabel#EmptyStateDesc {
    color: #cbd5e1;
}

QLabel#EmptyStateTips {
    color: #94a3b8;
}

QLabel#TourTitle {
    color: #f8fafc;
}

QLabel#TourSummary {
    color: #e2e8f0;
}

QLabel#TourTip {
    color: #93c5fd;
    font-size: 12px;
}

QLabel#VersionBadge {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
}

/* Sidebar Navigation */
QListWidget#SideNav {
    background-color: #141720;
    border-right: 1px solid #232838;
    outline: none;
    padding: 8px 6px;
    font-size: 13px;
    font-weight: 500;
}

QListWidget#SideNav::item {
    padding: 10px 14px;
    margin-bottom: 4px;
    border-radius: 6px;
    color: #a5adcb;
}

QListWidget#SideNav::item:hover {
    background-color: #1e2230;
    color: #ffffff;
}

QListWidget#SideNav::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
    font-weight: 600;
}

/* GroupBoxes */
QGroupBox {
    background-color: #161923;
    border: 1px solid #262b3d;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    color: #cad3f5;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #8aadf4;
}

/* Buttons */
QPushButton {
    background-color: #232838;
    color: #e6e9f0;
    border: 1px solid #343b52;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #2e3448;
    border-color: #4f46e5;
}

QPushButton:pressed {
    background-color: #1d212f;
}

QPushButton#PrimaryButton {
    background-color: #4f46e5;
    border: 1px solid #6366f1;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #4338ca;
}

QPushButton#AccentButton {
    background-color: #0d9488;
    border: 1px solid #14b8a6;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#AccentButton:hover {
    background-color: #0f766e;
}

/* Inputs, Combos, SpinBoxes, TextAreas */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QListWidget {
    background-color: #11131c;
    color: #f1f5f9;
    border: 1px solid #2b3147;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
}

QComboBox {
    combobox-popup: 0;
}

QComboBox QAbstractItemView, QComboBox QListView, QAbstractItemView {
    background-color: #161926;
    color: #f1f5f9;
    border: 1px solid #4f46e5;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
    outline: none;
}

QComboBox QAbstractItemView::item, QComboBox QListView::item, QListWidget::item {
    min-height: 26px;
    padding: 4px 8px;
    background-color: #161926;
    color: #f1f5f9;
}

QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover,
QComboBox QListView::item:selected, QComboBox QListView::item:hover,
QListWidget::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #6366f1;
}

/* Tables */
QTableWidget {
    background-color: #11131c;
    alternate-background-color: #151824;
    color: #e6e9f0;
    border: 1px solid #262b3d;
    border-radius: 6px;
    gridline-color: #202434;
    selection-background-color: #3730a3;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #191d2b;
    color: #939ab7;
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #2b3147;
    border-right: 1px solid #202434;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #d0d6e8;
}

/* Tooltips */
QToolTip {
    background-color: #1e2235;
    color: #f8fafc;
    border: 1px solid #6366f1;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}

/* StatusBar & MenuBar */
QStatusBar {
    background-color: #141720;
    color: #939ab7;
    border-top: 1px solid #232838;
}

QMenuBar {
    background-color: #141720;
    color: #e6e9f0;
    border-bottom: 1px solid #232838;
}

QMenuBar::item:selected {
    background-color: #2b3147;
}

QMenu {
    background-color: #181b28;
    color: #e6e9f0;
    border: 1px solid #2b3147;
}

QMenu::item:selected {
    background-color: #4f46e5;
}
"""


LIGHT_STUDIO_STYLESHEET = """
QMainWindow, QDialog, QScrollArea, QWidget#ScrollViewport, QWidget#WorkspacePage {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

QWidget {
    color: #0f172a;
}

/* Top Header Bar & Tour Banner */
QFrame#TopHeaderBar {
    background-color: #ffffff;
    border-bottom: 1px solid #cbd5e1;
}

QFrame#ProductTourBanner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #eef2ff, stop:1 #e0e7ff);
    border: 1px solid #4f46e5;
    border-radius: 8px;
}

/* Metric Cards & Empty State Guide Cards */
QFrame#MetricCard {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

QLabel#MetricTitle {
    color: #475569;
    font-size: 12px;
    font-weight: 600;
}

QLabel#MetricValue {
    color: #0f172a;
}

QLabel#MetricSubtitle {
    color: #64748b;
    font-size: 11px;
}

QFrame#EmptyStateCard {
    background-color: #f1f5f9;
    border: 1px dashed #94a3b8;
    border-radius: 10px;
}

QLabel#EmptyStateTitle {
    color: #4338ca;
}

QLabel#EmptyStateDesc {
    color: #1e293b;
}

QLabel#EmptyStateTips {
    color: #475569;
}

QLabel#TourTitle {
    color: #1e1b4b;
}

QLabel#TourSummary {
    color: #1e293b;
}

QLabel#TourTip {
    color: #3730a3;
    font-size: 12px;
}

QLabel#VersionBadge {
    background-color: #e2e8f0;
    color: #334155;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
}

/* Sidebar Navigation */
QListWidget#SideNav {
    background-color: #f1f5f9;
    border-right: 1px solid #cbd5e1;
    outline: none;
    padding: 8px 6px;
    font-size: 13px;
    font-weight: 500;
}

QListWidget#SideNav::item {
    padding: 10px 14px;
    margin-bottom: 4px;
    border-radius: 6px;
    color: #334155;
}

QListWidget#SideNav::item:hover {
    background-color: #e2e8f0;
    color: #0f172a;
}

QListWidget#SideNav::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
    font-weight: 600;
}

/* GroupBoxes */
QGroupBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    color: #1e293b;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: #4338ca;
}

/* Buttons */
QPushButton {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #94a3b8;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #4f46e5;
}

QPushButton:pressed {
    background-color: #e2e8f0;
}

QPushButton#PrimaryButton {
    background-color: #4f46e5;
    border: 1px solid #4338ca;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #4338ca;
}

QPushButton#AccentButton {
    background-color: #0d9488;
    border: 1px solid #0f766e;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#AccentButton:hover {
    background-color: #0f766e;
}

/* Inputs, Combos, SpinBoxes, TextAreas */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit, QListWidget {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #94a3b8;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
}

QComboBox {
    combobox-popup: 0;
}

QComboBox QAbstractItemView, QComboBox QListView, QAbstractItemView {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #4f46e5;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
    outline: none;
}

QComboBox QAbstractItemView::item, QComboBox QListView::item, QListWidget::item {
    min-height: 26px;
    padding: 4px 8px;
    background-color: #ffffff;
    color: #0f172a;
}

QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover,
QComboBox QListView::item:selected, QComboBox QListView::item:hover,
QListWidget::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #4f46e5;
}

/* Tables */
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    gridline-color: #e2e8f0;
    selection-background-color: #4f46e5;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #f1f5f9;
    color: #334155;
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #cbd5e1;
    border-right: 1px solid #e2e8f0;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #1e293b;
}

/* Tooltips */
QToolTip {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #4f46e5;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}

/* StatusBar & MenuBar */
QStatusBar {
    background-color: #f1f5f9;
    color: #475569;
    border-top: 1px solid #cbd5e1;
}

QMenuBar {
    background-color: #f1f5f9;
    color: #0f172a;
    border-bottom: 1px solid #cbd5e1;
}

QMenuBar::item:selected {
    background-color: #e2e8f0;
}

QMenu {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
}

QMenu::item:selected {
    background-color: #4f46e5;
    color: #ffffff;
}
"""


class ThemeManager:
    """Persists and resolves Light / Dark / System theme mode for the desktop studio."""

    VALID_MODES = ("dark", "light", "system")

    @staticmethod
    def _prefs_file():
        return get_settings().resolved_data_dir() / "ui_theme.json"

    @classmethod
    def get_preference(cls) -> str:
        path = cls._prefs_file()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                mode = str(data.get("theme_mode", "dark")).lower()
                if mode in cls.VALID_MODES:
                    return mode
            except Exception:
                pass
        return "dark"

    @classmethod
    def set_preference(cls, mode: str) -> str:
        normalized = mode.lower().strip()
        if normalized not in cls.VALID_MODES:
            normalized = "dark"
        path = cls._prefs_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"theme_mode": normalized}, indent=2), encoding="utf-8")
        return normalized

    @classmethod
    def detect_system_scheme(cls) -> str:
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None and hasattr(app, "styleHints"):
                scheme = app.styleHints().colorScheme()  # type: ignore[attr-defined]
                if scheme == Qt.ColorScheme.Light:
                    return "light"
                if scheme == Qt.ColorScheme.Dark:
                    return "dark"
        except Exception:
            pass
        return "dark"

    @classmethod
    def resolve_effective_theme(cls, mode: Optional[str] = None) -> str:
        pref = (mode or cls.get_preference()).lower()
        if pref == "system":
            return cls.detect_system_scheme()
        return "light" if pref == "light" else "dark"

    @classmethod
    def get_stylesheet(cls, mode: Optional[str] = None) -> str:
        effective = cls.resolve_effective_theme(mode)
        return LIGHT_STUDIO_STYLESHEET if effective == "light" else DARK_STUDIO_STYLESHEET

    @classmethod
    def apply_palette(cls, mode: Optional[str] = None) -> None:
        """Synchronize QApplication palette and global stylesheet so popup menus and dialogs never render low-contrast text."""
        try:
            from PySide6.QtGui import QColor, QPalette
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                return
            effective = cls.resolve_effective_theme(mode)
            pal = QPalette()
            if effective == "light":
                pal.setColor(QPalette.ColorRole.Window, QColor("#f8fafc"))
                pal.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
                pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
                pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f1f5f9"))
                pal.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
                pal.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
                pal.setColor(QPalette.ColorRole.ButtonText, QColor("#0f172a"))
                pal.setColor(QPalette.ColorRole.Highlight, QColor("#4f46e5"))
                pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            else:
                pal.setColor(QPalette.ColorRole.Window, QColor("#0f1117"))
                pal.setColor(QPalette.ColorRole.WindowText, QColor("#f1f5f9"))
                pal.setColor(QPalette.ColorRole.Base, QColor("#161926"))
                pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#11131c"))
                pal.setColor(QPalette.ColorRole.Text, QColor("#f1f5f9"))
                pal.setColor(QPalette.ColorRole.Button, QColor("#232838"))
                pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f1f5f9"))
                pal.setColor(QPalette.ColorRole.Highlight, QColor("#4f46e5"))
                pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            app.setPalette(pal)  # type: ignore[attr-defined]
        except Exception:
            pass
