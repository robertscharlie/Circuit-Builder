from __future__ import annotations

from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem

TERMINAL_RADIUS = 5.0
_IDLE_COLOR = QColor("#3a3a3a")
_HOVER_COLOR = QColor("#e07a1f")
# Matches the canvas background - gives each terminal a subtle halo that
# separates it from a wire passing right through it, rather than the dot
# and the line just melting into one blob.
_RING_COLOR = QColor("#fafafa")


class TerminalItem(QGraphicsEllipseItem):
    """A connection point on a component. Click-drag from one to another to wire them."""

    def __init__(self, index: int, parent=None):
        super().__init__(
            -TERMINAL_RADIUS, -TERMINAL_RADIUS, TERMINAL_RADIUS * 2, TERMINAL_RADIUS * 2, parent
        )
        self.index = index
        self.wires: list = []
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
