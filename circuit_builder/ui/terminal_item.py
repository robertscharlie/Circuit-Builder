from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem

TERMINAL_RADIUS = 5.0
_IDLE_COLOR = QColor("#3a3a3a")
_HOVER_COLOR = QColor("#e07a1f")
# Matches the canvas background - gives each terminal a subtle halo that
# separates it from a wire passing right through it, rather than the dot
# and the line just melting into one blob.
_RING_COLOR = QColor("#fafafa")
# Distinct from the orange hover/selection accent used everywhere else, so a
# probed terminal (Frequency Response dialog open) still reads clearly even
# while the cursor happens to be sitting over it too.
_PROBE_COLOR = QColor("#3fb950")
_PROBE_RING_MARGIN = 4.0


class TerminalItem(QGraphicsEllipseItem):
    """A connection point on a component. Click-drag from one to another to wire them."""

    def __init__(self, index: int, parent=None):
        super().__init__(
            -TERMINAL_RADIUS, -TERMINAL_RADIUS, TERMINAL_RADIUS * 2, TERMINAL_RADIUS * 2, parent
        )
        self.index = index
        self.wires: list = []
        self._probed = False
        self.setBrush(QBrush(_IDLE_COLOR))
        self.setPen(QPen(_RING_COLOR, 1.4))
        self.setAcceptHoverEvents(True)
        self.setZValue(2)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(_IDLE_COLOR))
        super().hoverLeaveEvent(event)

    def set_probed(self, probed: bool) -> None:
        """Marks/unmarks this terminal as the current Frequency Response
        probe point - drawn as an extra ring around it, independent of the
        idle/hover fill color, so it stays visible whichever state those
        are in."""
        if probed == self._probed:
            return
        self.prepareGeometryChange()
        self._probed = probed
        self.update()

    def boundingRect(self) -> QRectF:
        r = TERMINAL_RADIUS + (_PROBE_RING_MARGIN if self._probed else 0.0)
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._probed:
            painter.setRenderHint(painter.RenderHint.Antialiasing)
            painter.setPen(QPen(_PROBE_COLOR, 2.2))
            painter.setBrush(QBrush())
            r = TERMINAL_RADIUS + _PROBE_RING_MARGIN * 0.7
            painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

    def add_wire(self, wire) -> None:
        if wire not in self.wires:
            self.wires.append(wire)

    def remove_wire(self, wire) -> None:
        if wire in self.wires:
            self.wires.remove(wire)

    def component(self):
        return self.parentItem()


def terminals_already_wired(a: "TerminalItem", b: "TerminalItem") -> bool:
    return any({wire.start_terminal, wire.end_terminal} == {a, b} for wire in a.wires)
