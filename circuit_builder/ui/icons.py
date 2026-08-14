"""Small hand-drawn toolbar icons, rendered with QPainter so the app needs no
external icon assets. Kept visually consistent with each other: same stroke
width, same size, same round caps/joins.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

SIZE = 22
_STROKE = QColor("#d7d7d7")


def _pixmap() -> QPixmap:
    pm = QPixmap(SIZE, SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def _painter(pm: QPixmap, width: float = 1.6) -> QPainter:
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(_STROKE, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    return p


def _arrowhead(path: QPainterPath, tip: QPointF, pointing_deg: float, length: float = 5.5, spread: float = 28) -> None:
    a1 = math.radians(pointing_deg + 180 - spread)
    a2 = math.radians(pointing_deg + 180 + spread)
    path.moveTo(tip.x() + length * math.cos(a1), tip.y() - length * math.sin(a1))
    path.lineTo(tip.x(), tip.y())
    path.lineTo(tip.x() + length * math.cos(a2), tip.y() - length * math.sin(a2))


def _undo_redo_icon(mirrored: bool) -> QIcon:
    pm = _pixmap()
    p = _painter(pm)
    cx, cy, r = SIZE / 2, SIZE / 2 + 1, SIZE / 2 - 6.5

    start_deg, span_deg = (200, 250) if not mirrored else (-20, -250)
    rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))

    end_deg = start_deg + span_deg
    tip = QPointF(cx + r * math.cos(math.radians(end_deg)), cy - r * math.sin(math.radians(end_deg)))
    tangent_deg = end_deg + (90 if span_deg > 0 else -90)
    head = QPainterPath()
    _arrowhead(head, tip, tangent_deg)
    p.drawPath(head)

    p.end()
    return QIcon(pm)


def undo_icon() -> QIcon:
    return _undo_redo_icon(mirrored=False)


def redo_icon() -> QIcon:
    return _undo_redo_icon(mirrored=True)


def _magnifier(p: QPainter, plus: bool, minus: bool) -> None:
    cx, cy, r = SIZE / 2 - 2, SIZE / 2 - 2, 6.5
    p.drawEllipse(QPointF(cx, cy), r, r)
    handle_dir = QPointF(math.cos(math.radians(45)), -math.sin(math.radians(45)))
    start = QPointF(cx + r * handle_dir.x(), cy - r * handle_dir.y() * -1)
    p.drawLine(
        QPointF(cx + r * 0.75, cy + r * 0.75),
        QPointF(cx + r * 1.9, cy + r * 1.9),
    )
    if minus or plus:
        p.drawLine(QPointF(cx - 3, cy), QPointF(cx + 3, cy))
    if plus:
        p.drawLine(QPointF(cx, cy - 3), QPointF(cx, cy + 3))


def zoom_in_icon() -> QIcon:
    pm = _pixmap()
    p = _painter(pm)
    _magnifier(p, plus=True, minus=False)
    p.end()
    return QIcon(pm)


def zoom_out_icon() -> QIcon:
    pm = _pixmap()
    p = _painter(pm)
    _magnifier(p, plus=False, minus=True)
    p.end()
    return QIcon(pm)


def fit_to_view_icon() -> QIcon:
    pm = _pixmap()
    p = _painter(pm)
    m, arm = 3.5, 5.5
    corners = [
        (m, m, 1, 1),
        (SIZE - m, m, -1, 1),
        (m, SIZE - m, 1, -1),
        (SIZE - m, SIZE - m, -1, -1),
    ]
    for x, y, dx, dy in corners:
        p.drawLine(QPointF(x, y), QPointF(x + arm * dx, y))
        p.drawLine(QPointF(x, y), QPointF(x, y + arm * dy))
    p.end()
    return QIcon(pm)


def pan_icon() -> QIcon:
    pm = _pixmap()
    p = _painter(pm)
    cx, cy = SIZE / 2, SIZE / 2
    arm = 7.5
    path = QPainterPath()
    for angle in (0, 90, 180, 270):
        rad = math.radians(angle)
        tip = QPointF(cx + arm * math.cos(rad), cy - arm * math.sin(rad))
        path.moveTo(cx, cy)
        path.lineTo(tip)
        _arrowhead(path, tip, angle, length=4.5, spread=25)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def reset_zoom_icon() -> QIcon:
    pm = _pixmap()
    p = _painter(pm)
    cx, cy, r = SIZE / 2, SIZE / 2, SIZE / 2 - 6
    rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    start_deg, span_deg = -50, 300
    p.drawArc(rect, int(start_deg * 16), int(span_deg * 16))
    end_deg = start_deg + span_deg
    tip = QPointF(cx + r * math.cos(math.radians(end_deg)), cy - r * math.sin(math.radians(end_deg)))
    head = QPainterPath()
    _arrowhead(head, tip, end_deg + 90)
    p.drawPath(head)
    p.end()
    return QIcon(pm)
