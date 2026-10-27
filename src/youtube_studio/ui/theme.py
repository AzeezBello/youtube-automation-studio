"""Modern dark-studio QSS theme for YouTube Automation Studio."""

from __future__ import annotations

DARK_STUDIO_STYLESHEET = """
QMainWindow, QDialog {
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

QFrame#EmptyStateCard {
    background-color: #151822;
    border: 1px dashed #3b425c;
    border-radius: 10px;
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
    color: #e6e9f0;
    border: 1px solid #2b3147;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #4f46e5;
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
