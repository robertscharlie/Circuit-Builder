from __future__ import annotations

import uuid

from PySide6.QtCore import QLineF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem


class WireItem(QGraphicsLineItem):
    """A straight-line connection between two component terminals.

    Tracks its endpoints' scene positions so it stays attached as either
    component is moved or rotated. Construction does not attach the wire to
    its terminals or add it to a scene - callers (normally an undo command)
    do that via attach()/detach(), so presence on the canvas can be toggled
    for undo/redo without reconstructing the object.
    """

    def __init__(self, start_terminal, end_terminal):
        super().__init__()
        self.id = uuid.uuid4().hex
        self.start_terminal = start_terminal
        self.end_terminal = end_terminal

        pen = QPen(QColor("#2b6cb0"), 2)
        pen.setCapStyle(Qt.RoundCap)
        self.setPen(pen)
        self.setZValue(0)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        self.update_path()

    def update_path(self) -> None:
        self.setLine(QLineF(self.start_terminal.scenePos(), self.end_terminal.scenePos()))

    def attach(self) -> None:
        self.start_terminal.add_wire(self)
        self.end_terminal.add_wire(self)

    def detach(self) -> None:
        self.start_terminal.remove_wire(self)
        self.end_terminal.remove_wire(self)

    def paint(self, painter, option, widget=None):
        # Overridden (rather than using the default paint + selection
        # decoration) because Qt's default selected-item highlight is a
        # dashed axis-aligned box, which looks odd around a diagonal line -
        # recoloring the line itself reads more clearly as "this wire".
        pen = QPen(self.pen())
        if self.isSelected():
            pen.setColor(QColor("#e07a1f"))
            pen.setWidth(3)
        painter.setPen(pen)
        painter.drawLine(self.line())
