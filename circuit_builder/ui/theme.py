"""App-wide look and feel: a dark UI chrome around the light schematic canvas,
built around a single accent color (the same orange already used on the
canvas for selection highlights and terminal hover)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

ACCENT = "#e07a1f"

STYLESHEET = """
* {
    font-family: "Segoe UI", sans-serif;
}

QMainWindow, QDialog, QMessageBox {
    background: #202020;
    color: #e6e6e6;
}

QMenuBar {
    background: #1b1b1b;
    color: #e6e6e6;
    padding: 2px 4px;
    border-bottom: 1px solid #2a2a2a;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: rgba(224, 122, 31, 46);
    color: #ffffff;
}

QMenu {
    background: #232323;
    color: #e6e6e6;
    border: 1px solid #333333;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #e07a1f;
    color: #1b1b1b;
}
QMenu::item:disabled {
    color: #6a6a6a;
}
QMenu::separator {
    height: 1px;
    background: #333333;
    margin: 4px 8px;
}

QToolBar {
    background: #1b1b1b;
    border: none;
    border-bottom: 1px solid #2a2a2a;
    padding: 5px 6px;
    spacing: 2px;
}
QToolButton {
    background: transparent;
    color: #e6e6e6;
    border: none;
    border-radius: 6px;
    padding: 5px 8px;
}
QToolButton:hover {
    background: rgba(224, 122, 31, 46);
}
QToolButton:pressed {
    background: rgba(224, 122, 31, 82);
}
QToolButton:disabled {
    color: #5a5a5a;
}

QDockWidget {
    color: #e6e6e6;
}
QDockWidget::title {
    background: #202020;
    padding: 8px 10px;
    border-bottom: 1px solid #2a2a2a;
    font-weight: 600;
}

QListWidget {
    background: #1b1b1b;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget::item {
    border-radius: 6px;
    margin: 2px 4px;
}
QListWidget::item:hover {
    background: #272727;
}
QListWidget::item:selected {
    background: rgba(224, 122, 31, 56);
}

QLabel#shortcutBadge {
    qproperty-alignment: AlignCenter;
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 41);
    border-radius: 4px;
    color: #b7b7b7;
    font-size: 10px;
    padding: 0px;
}

QLabel#paletteIconSwatch {
    qproperty-alignment: AlignCenter;
    background: #fafafa;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
}

QStatusBar {
    background: #1b1b1b;
    color: #9a9a9a;
    border-top: 1px solid #2a2a2a;
}

QPushButton {
    background: #2c2c2c;
    color: #e6e6e6;
    border: 1px solid #3a3a3a;
    border-radius: 5px;
    padding: 5px 16px;
}
QPushButton:hover {
    border-color: #e07a1f;
}
QPushButton:pressed {
    background: #e07a1f;
    color: #1b1b1b;
}

QTextBrowser, QTextEdit {
    background: #1b1b1b;
    color: #e6e6e6;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    padding: 8px;
}

QLineEdit, QDoubleSpinBox {
    background: #1b1b1b;
    color: #e6e6e6;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: #e07a1f;
}
QLineEdit:focus, QDoubleSpinBox:focus {
    border-color: #e07a1f;
}

QScrollBar:vertical, QScrollBar:horizontal {
    background: #1b1b1b;
    border: none;
    margin: 0;
}
QScrollBar:vertical { width: 12px; }
QScrollBar:horizontal { height: 12px; }
QScrollBar::handle {
    background: #3a3a3a;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: #4a4a4a;
}
QScrollBar::add-line, QScrollBar::sub-line {
    height: 0;
    width: 0;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(STYLESHEET)
