from __future__ import annotations

import uuid

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from circuit_builder.core.components import COMPONENT_TYPES
from circuit_builder.ui.terminal_item import TERMINAL_RADIUS, TerminalItem

JUNCTION_TYPE = "junction"

BODY_WIDTH = 70
BODY_HEIGHT = 30
GRID_SIZE = 20
# Distance from the component's center to each terminal. Kept as a multiple
# of GRID_SIZE so a terminal always lands exactly on the grid whenever the
# component's (grid-snapped) center does too - otherwise wires never quite
# line up with the grid the body appears to snap to.
TERMINAL_OFFSET = 40
LEAD = TERMINAL_OFFSET - BODY_WIDTH / 2  # stub between body edge and terminal

_ENGINEERING_PREFIXES = [
    (1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""),
    (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"),
]


def _draw_resistor(painter: QPainter) -> None:
    # Classic ANSI zigzag. Crisp miter joins at each peak (round joins made
    # the peaks look soft/blobby rather than precise), rounded caps only at
    # the two ends where the path meets the leads, and a slightly thinner
    # stroke than the leads themselves so the zigzag doesn't look heavy-
    # handed against its own modest amplitude. A short flat run at each end,
    # parallel to the leads, keeps the zigzag from appearing to plunge
    # straight into the terminal - the existing lead stub alone is too short
    # (5px) to read as a deliberate straight approach.
    #
    # segments must be (even number of peaks/valleys) + 1 trailing flat point
    # - that's what gives every point on the path a 180-degree-rotated
    # counterpart also on the path (point/rotational symmetry about the
    # center). An odd count of alternating peaks/valleys instead leaves one
    # unpaired peak sitting exactly at the center, which only gives mirror
    # symmetry, not rotational.
    w = BODY_WIDTH
    amplitude = BODY_HEIGHT * 0.26
    flat = 6
    segments = 7
    seg_w = (w - 2 * flat) / segments

    pen = painter.pen()
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    painter.setPen(pen)

    path = QPainterPath(QPointF(-w / 2, 0))
    path.lineTo(-w / 2 + flat, 0)
    for i in range(segments):
        x = -w / 2 + flat + seg_w * (i + 1)
        y = 0 if i == segments - 1 else (amplitude if i % 2 == 0 else -amplitude)
        path.lineTo(x, y)
    path.lineTo(w / 2, 0)
    painter.drawPath(path)


def _draw_battery(painter: QPainter) -> None:
    # The (+) plate is taller than the (-) plate - same stroke width for
    # both, so the only difference is the classic long/short plate length.
    gap = 6
    pos_half_height = 14
    neg_half_height = 8

    pen = painter.pen()
    pen.setWidthF(3.0)
    painter.setPen(pen)
    painter.drawLine(QPointF(-gap, -pos_half_height), QPointF(-gap, pos_half_height))
    painter.drawLine(QPointF(gap, -neg_half_height), QPointF(gap, neg_half_height))
    pen.setWidthF(2.0)
    painter.setPen(pen)

    painter.drawLine(QPointF(-BODY_WIDTH / 2, 0), QPointF(-gap, 0))
    painter.drawLine(QPointF(gap, 0), QPointF(BODY_WIDTH / 2, 0))

    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(QRectF(-gap - 16, -28, 12, 14), Qt.AlignmentFlag.AlignCenter, "+")
    painter.drawText(QRectF(gap + 4, -28, 12, 14), Qt.AlignmentFlag.AlignCenter, "-")


def _draw_capacitor(painter: QPainter) -> None:
    gap = 5
    painter.drawLine(QPointF(-gap, -14), QPointF(-gap, 14))
    painter.drawLine(QPointF(gap, -14), QPointF(gap, 14))
    painter.drawLine(QPointF(-BODY_WIDTH / 2, 0), QPointF(-gap, 0))
    painter.drawLine(QPointF(gap, 0), QPointF(BODY_WIDTH / 2, 0))


def _draw_inductor(painter: QPainter) -> None:
    coil_w = BODY_WIDTH * 0.6
    bumps = 4
    bump_w = coil_w / bumps
    bump_h = bump_w * 1.05

    pen = painter.pen()
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)

    painter.drawLine(QPointF(-BODY_WIDTH / 2, 0), QPointF(-coil_w / 2, 0))
    painter.drawLine(QPointF(coil_w / 2, 0), QPointF(BODY_WIDTH / 2, 0))

    path = QPainterPath(QPointF(-coil_w / 2, 0))
    for i in range(bumps):
        cx = -coil_w / 2 + bump_w * (i + 0.5)
        rect = QRectF(cx - bump_w / 2, -bump_h / 2, bump_w, bump_h)
        path.arcTo(rect, 180, -180)
    painter.drawPath(path)


def _draw_switch(painter: QPainter, closed: bool) -> None:
    # Two contact dots with a pole/lever between them: lying flat and
    # touching the right dot when closed, angled up and away when open.
    gap = 8
    left = QPointF(-gap, 0)
    right = QPointF(gap, 0)

    pen = painter.pen()
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    painter.drawLine(QPointF(-BODY_WIDTH / 2, 0), left)
    painter.drawLine(right, QPointF(BODY_WIDTH / 2, 0))

    lever_end = right if closed else QPointF(right.x() - 4, right.y() - 13)
    painter.drawLine(left, lever_end)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#1a1a1a"))
    painter.drawEllipse(left, 2.4, 2.4)
    painter.drawEllipse(right, 2.4, 2.4)


def _draw_lamp(painter: QPainter, brightness: float) -> None:
    # Classic circle-with-an-X indicator/lamp symbol - filled with a warm
    # glow whose strength tracks `brightness` (0 = off, 1 = full - driven by
    # the voltage across it during a live simulation, so a capacitor-fed
    # bulb visibly fades as it discharges rather than snapping on/off).
    r = 12
    pen = painter.pen()
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    painter.drawLine(QPointF(-BODY_WIDTH / 2, 0), QPointF(-r, 0))
    painter.drawLine(QPointF(r, 0), QPointF(BODY_WIDTH / 2, 0))

    brightness = max(0.0, min(1.0, brightness))
    if brightness > 0.0:
        painter.setBrush(QColor(255, 196, 64, round(235 * brightness)))
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(0, 0), r, r)

    d = r * 0.707
    painter.drawLine(QPointF(-d, -d), QPointF(d, d))
    painter.drawLine(QPointF(-d, d), QPointF(d, -d))


_SYMBOL_DRAWERS = {
    "resistor": _draw_resistor,
    "battery": _draw_battery,
    "capacitor": _draw_capacitor,
    "inductor": _draw_inductor,
}


def draw_component_symbol(
    painter: QPainter, component_type: str, closed: bool = True, brightness: float = 0.0
) -> None:
    """Draws a component's leads + symbol centered on the origin, with no
    label or selection decoration. Shared by ComponentItem.paint() and the
    palette's icon renderer so the two never drift out of sync. `closed`
    and `brightness` only matter for a switch / bulb respectively - ignored
    by every other type."""
    if component_type == JUNCTION_TYPE:
        return  # a junction is represented solely by its terminal dot

    lead_pen = QPen(QColor("#1a1a1a"), 2)
    lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(lead_pen)
    painter.drawLine(QPointF(-TERMINAL_OFFSET, 0), QPointF(-BODY_WIDTH / 2, 0))
    painter.drawLine(QPointF(BODY_WIDTH / 2, 0), QPointF(TERMINAL_OFFSET, 0))

    if component_type == "switch":
        _draw_switch(painter, closed)
    elif component_type == "lamp":
        _draw_lamp(painter, brightness)
    else:
        draw_fn = _SYMBOL_DRAWERS.get(component_type)
        if draw_fn:
            draw_fn(painter)


def render_symbol_pixmap(component_type: str) -> QPixmap:
    """Renders a component's schematic symbol to a small transparent pixmap,
    for use as an icon (e.g. in the component palette)."""
    if component_type == JUNCTION_TYPE:
        size = 40
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#3a3a3a"))
        painter.drawEllipse(QPointF(size / 2, size / 2), 8, 8)
        painter.end()
        return pixmap

    width, height = 100, 60
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(width / 2, height / 2)

    # Palette icons always show a switch in its classic "open" resting
    # position - the generic recognizable glyph, independent of whatever
    # state a placed switch instance happens to be in.
    draw_component_symbol(painter, component_type, closed=False)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#3a3a3a"))
    painter.drawEllipse(QPointF(-TERMINAL_OFFSET, 0), TERMINAL_RADIUS, TERMINAL_RADIUS)
    painter.drawEllipse(QPointF(TERMINAL_OFFSET, 0), TERMINAL_RADIUS, TERMINAL_RADIUS)
    painter.end()
    return pixmap


class ComponentItem(QGraphicsObject):
    """A draggable, rotatable schematic symbol. Two terminals for ordinary
    components; a single terminal at the origin for a junction/node."""

    # Emitted instead of applying a double-click edit directly, so the
    # MainWindow can wrap the change in an undoable command. Args: (self,
    # new_label, new_value).
    edit_requested = Signal(object, str, float)
    # A switch was clicked (pressed and released without being dragged) -
    # the MainWindow wraps the actual flip in an undoable command. Arg: self.
    toggle_requested = Signal(object)

    def __init__(
        self,
        component_type: str,
        value: float | None = None,
        label: str = "",
        component_id: str | None = None,
        closed: bool | None = None,
    ):
        super().__init__()
        self.id = component_id or uuid.uuid4().hex
        self.component_type = component_type
        meta = COMPONENT_TYPES[component_type]
        self.value = meta.default_value if value is None else value
        self.label = label
        # Only meaningful for "switch" (open/closed) - everything else just
        # carries the default and ignores it. A freshly placed switch starts
        # open, matching its palette icon; loading a saved circuit passes
        # the saved state through explicitly instead.
        self.closed = (component_type != "switch") if closed is None else closed
        # Only meaningful for "lamp" - how strongly a live simulation's
        # voltage across it should make it glow, 0 (off) to 1 (full). Set
        # by MainWindow, not by the user.
        self.brightness = 0.0
        self._press_pos: QPointF | None = None

        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)

        if component_type == JUNCTION_TYPE:
            self.terminals = [TerminalItem(0, self)]
            self.terminals[0].setPos(0, 0)
        else:
            self.terminals = [TerminalItem(0, self), TerminalItem(1, self)]
            self.terminals[0].setPos(-TERMINAL_OFFSET, 0)
            self.terminals[1].setPos(TERMINAL_OFFSET, 0)

    def boundingRect(self) -> QRectF:
        if self.component_type == JUNCTION_TYPE:
            half = 14
            return QRectF(-half, -half, half * 2, half * 2)
        # Square and centered on the origin so it's identical at every 90-degree
        # rotation step - required because the label is drawn at a fixed
        # screen-relative offset (see paint()), not one that rotates with the
        # body, so the declared bounds must already cover it at every angle.
        half = TERMINAL_OFFSET + 6
        return QRectF(-half, -half, half * 2, half * 2)

    def _outline_rect(self) -> QRectF:
        """A tight box around the visible symbol - unlike boundingRect(),
        this does NOT need to stay rotation-invariant or cover the
        (fixed-offset) label. Used both for the selection highlight and, via
        shape(), for hit-testing - boundingRect() alone is far bigger than
        the visible symbol (it has to be, to stay rotation-invariant), and
        using it for hit-testing let clicks register well outside the
        component's actual drawn area."""
        if self.component_type == JUNCTION_TYPE:
            half = 9
            return QRectF(-half, -half, half * 2, half * 2)
        half_w = TERMINAL_OFFSET
        half_h = BODY_HEIGHT / 2 + 6
        return QRectF(-half_w, -half_h, half_w * 2, half_h * 2)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._outline_rect())
        return path

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            point = value
            return QPointF(
                round(point.x() / GRID_SIZE) * GRID_SIZE,
                round(point.y() / GRID_SIZE) * GRID_SIZE,
            )
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.update_wires()
        return super().itemChange(change, value)

    def update_wires(self) -> None:
        for terminal in self.terminals:
            for wire in list(terminal.wires):
                wire.update_path()

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # A plain click (no drag in between) on a switch flips it - the
        # position round-trips through the grid-snap in itemChange(), so
        # comparing pos() before/after is a reliable "did it actually move"
        # check rather than comparing raw event coordinates.
        if (
            self.component_type == "switch"
            and event.button() == Qt.MouseButton.LeftButton
            and self.pos() == self._press_pos
        ):
            self.toggle_requested.emit(self)

    def mouseDoubleClickEvent(self, event):
        if self.component_type == JUNCTION_TYPE:
            return  # nothing to configure on a bare wiring node

        from circuit_builder.ui.edit_dialog import EditComponentDialog

        meta = COMPONENT_TYPES[self.component_type]
        # A switch has no numeric value - its state is the open/closed
        # toggle (click it), not something to type in here.
        show_value = self.component_type != "switch"
        dialog = EditComponentDialog(self.label, self.value, meta.unit, show_value=show_value)
        if dialog.exec() == EditComponentDialog.DialogCode.Accepted:
            label, value = dialog.values()
            self.edit_requested.emit(self, label, value)
        super().mouseDoubleClickEvent(event)

    def apply_edit(self, label: str, value: float) -> None:
        self.label = label
        self.value = value
        self.update()

    def _paint_selection(self, painter: QPainter) -> None:
        painter.setPen(QPen(QColor("#e07a1f"), 1.5))
        painter.setBrush(QColor(224, 122, 31, 28))
        painter.drawRoundedRect(self._outline_rect(), 6, 6)

    def paint(self, painter: QPainter, option, widget=None):
        if self.component_type == JUNCTION_TYPE:
            if self.isSelected():
                self._paint_selection(painter)
            return

        draw_component_symbol(painter, self.component_type, self.closed, self.brightness)

        if self.isSelected():
            self._paint_selection(painter)

        # Draw the label upright and at a fixed screen-relative offset, even
        # when the component is rotated: cancel the item's rotation first, so
        # the translate below moves along screen axes rather than the body's.
        painter.save()
        painter.rotate(-self.rotation())
        painter.translate(0, BODY_HEIGHT / 2 + 9)
        painter.setPen(QPen(QColor("#1a1a1a")))
        painter.setFont(QFont("Segoe UI", 8))
        if self.component_type == "switch":
            text = f"{self.label}  {'Closed' if self.closed else 'Open'}"
        else:
            text = f"{self.label}  {self._format_value()}"
        painter.drawText(
            QRectF(-TERMINAL_OFFSET, -7, TERMINAL_OFFSET * 2, 14), Qt.AlignmentFlag.AlignCenter, text
        )
        painter.restore()

    def _format_value(self) -> str:
        v = self.value
        for scale, prefix in _ENGINEERING_PREFIXES:
            if abs(v) >= scale:
                return f"{v / scale:g}{prefix}"
        return f"{v:g}"
