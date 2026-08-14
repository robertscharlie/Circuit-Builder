"""Voltage-label overlay drawn on the canvas after Simulate runs - a small
pill-shaped label sits next to every terminal showing that electrical
node's DC voltage. Purely visual: each label's shape() is empty, so clicks
pass straight through to whatever's underneath (wires, terminals,
components) and the overlay never gets in the way of normal editing.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainterPath
from PySide6.QtWidgets import QGraphicsItem

_POSITIVE_COLOR = QColor("#1f6feb")
_NEGATIVE_COLOR = QColor("#cf222e")
_ZERO_COLOR = QColor("#57606a")
_UNKNOWN_COLOR = QColor("#8b949e")
_BACKGROUND = QColor(255, 255, 255, 235)
_PADDING_X = 5
_HEIGHT = 15
_OFFSET = QPointF(8, -20)

_PREFIXES = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ")]


def format_voltage(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) < 5e-4:
        return "0 V"
    for scale, prefix in _PREFIXES:
        if abs(value) >= scale:
            return f"{value / scale:g} {prefix}V"
    return f"{value:g} V"


def _color_for(value: float | None) -> QColor:
    if value is None:
        return _UNKNOWN_COLOR
    if abs(value) < 5e-4:
        return _ZERO_COLOR
    return _POSITIVE_COLOR if value > 0 else _NEGATIVE_COLOR


class VoltageLabelItem(QGraphicsItem):
    """A small floating pill showing one terminal's simulated DC voltage."""

    def __init__(self, voltage: float | None, scene_pos: QPointF):
        super().__init__()
        self._text = format_voltage(voltage)
        self._color = _color_for(voltage)
        font = QFont("Segoe UI", 7)
        font.setBold(True)
        self._font = font
        width = QFontMetricsF(font).horizontalAdvance(self._text) + _PADDING_X * 2
        self._rect = QRectF(0, 0, width, _HEIGHT)
        self.setZValue(50)
        self.setPos(scene_pos + _OFFSET)

    def boundingRect(self) -> QRectF:
        return self._rect

    def shape(self) -> QPainterPath:
        return QPainterPath()  # purely visual - never intercepts clicks

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_BACKGROUND)
        painter.drawRoundedRect(self._rect, 4, 4)
        painter.setPen(self._color)
        painter.setFont(self._font)
        painter.drawText(self._rect, Qt.AlignmentFlag.AlignCenter, self._text)
