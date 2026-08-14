import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import ComponentItem
from circuit_builder.ui.wire_item import WireItem

app = QApplication(sys.argv)
window = MainWindow()
window.resize(900, 500)
window.show()
window.raise_()
window.activateWindow()
app.processEvents()
view = window.view
vp = view.viewport()


def move(pos):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(pos), QPointF(pos), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)


def lmb(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos), QPointF(pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def release(pos):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(pos), QPointF(pos), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)


def draw_wire(from_scene_pos, to_scene_pos):
    """Plain (no Shift) press-drag-release starting on a terminal - this is
    the app's normal wire-drawing gesture, and the only way to drag FROM a
    Node at all (Shift+drag is reserved for MOVING one instead)."""
    view.mousePressEvent(lmb(view.mapFromScene(from_scene_pos)))
    app.processEvents()
    view.mouseMoveEvent(move(view.mapFromScene(to_scene_pos)))
    app.processEvents()
    view.mouseReleaseEvent(release(view.mapFromScene(to_scene_pos)))
    app.processEvents()


def shift_lmb(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos), QPointF(pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)


def shift_release(pos):
    return QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(pos), QPointF(pos), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.ShiftModifier)


def shift_drag(terminal_scene_pos, target_scene_pos):
    view.mousePressEvent(shift_lmb(view.mapFromScene(terminal_scene_pos)))
    app.processEvents()
    view.mouseMoveEvent(move(view.mapFromScene(target_scene_pos)))
    app.processEvents()
    view.mouseReleaseEvent(shift_release(view.mapFromScene(target_scene_pos)))
    app.processEvents()


def native_drag(from_scene_pos, to_scene_pos):
    a = view.mapFromScene(from_scene_pos)
    b = view.mapFromScene(to_scene_pos)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    QTest.mouseMove(vp, b)
    app.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    app.processEvents()


def wires_in_scene():
    return [i for i in window.scene.items() if isinstance(i, WireItem)]


def junctions_in_scene():
    return [i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"]


# --- 1. A Node, shift-dragged so its terminal lands on an existing wire's
# line (not at either endpoint), taps into it - no new component is added,
# the one wire becomes two routed through the Node ---------------------------
r1 = window.add_component("resistor", QPointF(-200, 0))
r2 = window.add_component("resistor", QPointF(0, 0))
wire = WireItem(r1.terminals[1], r2.terminals[0])  # runs from (-160,0) to (-40,0)
wire.attach()
window.scene.addItem(wire)

node = window.add_component("junction", QPointF(-100, 200))
app.processEvents()
tap_point = QPointF(-100, 0)  # grid-aligned, sits exactly on the wire's line

shift_drag(node.terminals[0].scenePos(), tap_point)

assert wire not in window.scene.items(), "the original wire should be replaced, not left in place"
assert node in window.scene.items(), "tapping a wire doesn't delete the Node, unlike merging onto a terminal"
new_wires = wires_in_scene()
assert len(new_wires) == 2, f"expected the one wire split into two through the Node, got {len(new_wires)}"
endpoints = {frozenset({w.start_terminal, w.end_terminal}) for w in new_wires}
assert frozenset({r1.terminals[1], node.terminals[0]}) in endpoints
assert frozenset({node.terminals[0], r2.terminals[0]}) in endpoints
print("1. a Node dropped onto a wire's line taps into it (no new component, wire splits through it): OK")

# --- 2. Undo restores the single original wire; redo re-taps ---------------
window.undo_stack.undo()
app.processEvents()
assert wire in window.scene.items(), "undo should bring the original wire back"
assert len(wires_in_scene()) == 1
print("2. undo restores the original single wire: OK")

window.undo_stack.redo()
app.processEvents()
assert wire not in window.scene.items()
assert len(wires_in_scene()) == 2
print("3. redo re-taps the wire: OK")

# --- 4. A regular (non-Node) component's terminal landing on a wire also
# taps into it - dragged there via a real native drag, same as any other
# component move ------------------------------------------------------------
v1 = window.add_component("battery", QPointF(-500, -300))
c1 = window.add_component("capacitor", QPointF(-300, -300))
wire2 = WireItem(v1.terminals[1], c1.terminals[0])  # runs from (-460,-300) to (-340,-300)
wire2.attach()
window.scene.addItem(wire2)

tap_point2 = QPointF(-400, -300)  # grid-aligned point on that wire's line

new_r = window.add_component("resistor", QPointF(200, 200))
app.processEvents()
# new_r.terminals[0] sits at local (-40, 0) - offset its body so that
# terminal (not its center) lands exactly on the wire.
desired_pos = QPointF(tap_point2.x() + 40, tap_point2.y())
native_drag(new_r.scenePos(), desired_pos)

assert wire2 not in window.scene.items(), "the second wire should also have been split"
assert new_r in window.scene.items(), "the component itself is never deleted by tapping"
assert new_r.terminals[0].scenePos() == tap_point2
tapped_wires = [
    w for w in wires_in_scene()
    if new_r.terminals[0] in (w.start_terminal, w.end_terminal)
]
assert len(tapped_wires) == 2, "the moved component's terminal should now have two wires through it"
endpoints2 = {frozenset({w.start_terminal, w.end_terminal}) for w in tapped_wires}
assert frozenset({v1.terminals[1], new_r.terminals[0]}) in endpoints2
assert frozenset({new_r.terminals[0], c1.terminals[0]}) in endpoints2
print("4. a regular component's terminal landing on a wire also taps into it (native drag): OK")

# --- 5. Tapping also works for a DIAGONAL wire - a component landing near
# (not mathematically exactly on) its line, within tolerance, still taps in.
# This is the common case: two components not lined up on the same row or
# column produce a diagonal wire, and almost no other grid point sits
# exactly on such a line - only a distance-based tolerance check works here.
x = window.add_component("resistor", QPointF(-40, 400))   # terminal[1] at (0, 400)
y = window.add_component("resistor", QPointF(180, 460))   # terminal[0] at (140, 460)
diag_wire = WireItem(x.terminals[1], y.terminals[0])
diag_wire.attach()
window.scene.addItem(diag_wire)
app.processEvents()

# (60, 420) sits ~5.25 units off the mathematical line from (0,400) to
# (140,460) - within WIRE_TAP_TOLERANCE (6.0) but not exactly 0.
z = window.add_component("resistor", QPointF(300, 600))
app.processEvents()
native_drag(z.scenePos(), QPointF(100, 420))  # lands z.terminals[0] at (60, 420)

assert diag_wire not in window.scene.items(), "a near-enough landing on a diagonal wire should still tap into it"
tapped = [w for w in wires_in_scene() if z.terminals[0] in (w.start_terminal, w.end_terminal)]
assert len(tapped) == 2, "expected the diagonal wire split through z's terminal"
print("5. tapping works for a diagonal wire too, within a small tolerance: OK")

# --- 6. Dragging a wire out of a Node's terminal (its only interaction,
# since it has no body to grab) and dropping it on an existing wire taps
# into it via a NEW Node at the drop point - the free Node itself doesn't
# move, unlike the Shift+drag case in test 1. ------------------------------
a = window.add_component("resistor", QPointF(-40, 800))    # terminal[1] at (0, 800)
b = window.add_component("resistor", QPointF(180, 800))    # terminal[0] at (140, 800)
straight_wire = WireItem(a.terminals[1], b.terminals[0])
straight_wire.attach()
window.scene.addItem(straight_wire)

free_node = window.add_component("junction", QPointF(60, 900))
app.processEvents()
before_pos = free_node.pos()
junctions_before = set(junctions_in_scene())  # earlier tests leave Nodes lingering in the scene

draw_wire(free_node.terminals[0].scenePos(), QPointF(60, 800))  # drop right on the wire's line

assert free_node.pos() == before_pos, "drawing a wire from the Node must not move it"
assert straight_wire not in window.scene.items(), "the target wire should have been split"
assert len(free_node.terminals[0].wires) == 1, "the Node should now have exactly one new wire"
new_junctions = [j for j in junctions_in_scene() if j not in junctions_before]
assert len(new_junctions) == 1, "a single new Node should have been inserted at the tap point"
tap_node = new_junctions[0]
assert tap_node.pos() == QPointF(60, 800)
tap_wires = [w for w in wires_in_scene() if tap_node.terminals[0] in (w.start_terminal, w.end_terminal)]
assert len(tap_wires) == 3, f"expected 3 wires through the tap Node (a<->tap, tap<->b, tap<->free_node), got {len(tap_wires)}"
print("6. dragging a wire from a Node's terminal onto a wire taps in via a new Node (Node itself doesn't move): OK")

print("ALL WIRE-TAP TESTS PASSED")
