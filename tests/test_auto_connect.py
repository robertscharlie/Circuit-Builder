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


def move(pos):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(pos), QPointF(pos), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)


def lmb(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos), QPointF(pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


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


def junctions_in_scene():
    return [i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"]


def wires_in_scene():
    return [i for i in window.scene.items() if isinstance(i, WireItem)]


# --- 1. A Node carrying a wire, dropped onto another component's terminal,
# merges away: the wire is rehomed directly to that terminal and the Node
# is deleted -------------------------------------------------------------
r1 = window.add_component("resistor", QPointF(-300, 0))
v1 = window.add_component("battery", QPointF(0, 0))
wire = WireItem(r1.terminals[1], v1.terminals[0])
wire.attach()
window.scene.addItem(wire)
c1 = window.add_component("capacitor", QPointF(300, 0))
app.processEvents()

# detach r1's wire onto a free node (as in the previous round's feature)
view._menu_exec_override = lambda menu: menu.actions()[0] if menu.actions() else None
view.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(view.mapFromScene(r1.terminals[1].scenePos())), QPointF(view.mapFromScene(r1.terminals[1].scenePos())), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier))
app.processEvents()
node = view._pending_move_target
assert node is not None and node.component_type == "junction"
# drop it off to the side first so it isn't already coincident with anything
away_vp = view.mapFromScene(QPointF(-300, -200))
view.mouseMoveEvent(move(away_vp))
app.processEvents()
view.mousePressEvent(lmb(away_vp))
app.processEvents()
assert len(junctions_in_scene()) == 1
assert len(wires_in_scene()) == 1  # node <-> v1

target_terminal = c1.terminals[0]
target_pos = target_terminal.scenePos()
shift_drag(node.terminals[0].scenePos(), target_pos)

assert node not in window.scene.items(), "the Node should have been deleted after merging"
assert junctions_in_scene() == [], "no junction should remain"
wires = wires_in_scene()
assert len(wires) == 1, f"expected exactly 1 wire (c1 <-> v1 directly), got {len(wires)}"
merged_wire = wires[0]
assert {merged_wire.start_terminal, merged_wire.end_terminal} == {target_terminal, v1.terminals[0]}, (
    "the wire the Node was carrying should now connect directly to c1's terminal"
)
print("1. a Node carrying a wire, dropped on a terminal, merges away and rewires directly: OK")

# --- 2. That's a single undo step ------------------------------------------
window.undo_stack.undo()
app.processEvents()
assert len(junctions_in_scene()) == 1, "undo should bring the Node back"
assert merged_wire not in window.scene.items(), "undo should remove the merged wire"
restored_node = junctions_in_scene()[0]
assert restored_node.pos() != target_pos, "undo should restore the node's pre-merge position"
print("2. the move + merge undo together as a single step: OK")

window.undo_stack.redo()
app.processEvents()
assert junctions_in_scene() == []
assert len(wires_in_scene()) == 1
print("3. redo re-applies the move and the merge: OK")

# --- 4. A Node with NO wires, dropped onto a terminal, is simply deleted ---
window._on_component_dropped("junction", QPointF(300, -200))
app.processEvents()
empty_node = next(j for j in junctions_in_scene())
assert len(empty_node.terminals[0].wires) == 0
before_wire_count = len(wires_in_scene())
shift_drag(empty_node.terminals[0].scenePos(), target_pos)
assert empty_node not in window.scene.items(), "an empty Node dropped on a terminal should still be deleted"
assert len(wires_in_scene()) == before_wire_count, "an empty Node has nothing to rehome, so no wire is added"
print("4. a Node with no wires, dropped on a terminal, is deleted with no new wire: OK")

# --- 5. A regular (non-Node) component landing on a terminal still just
# auto-wires - it is not deleted --------------------------------------------
r2 = window.add_component("inductor", QPointF(300, 200))
app.processEvents()

# r2.terminals[0] sits at local (-40, 0); to land it exactly on target_pos,
# r2's own position must be offset by (+40, 0) from target_pos.
desired_r2_pos = QPointF(target_pos.x() + 40, target_pos.y())
# Ordinary body-drag relies on Qt's native ItemIsMovable dragging, which
# needs real QTest-synthesized events (not hand-built QMouseEvents) to set
# up mouse-grab state correctly - unlike the app's own custom interactions
# (shift+drag, panning, etc.) used elsewhere in this file.
vp = view.viewport()
a = view.mapFromScene(r2.scenePos())
b = view.mapFromScene(desired_r2_pos)
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
QTest.mouseMove(vp, b)
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
app.processEvents()

assert r2 in window.scene.items(), "a regular component should never be auto-deleted"
assert r2.terminals[0].scenePos() == target_pos, f"expected {target_pos}, got {r2.terminals[0].scenePos()}"
wires_final = wires_in_scene()
assert any({w.start_terminal, w.end_terminal} == {target_terminal, r2.terminals[0]} for w in wires_final), (
    "r2's terminal should have auto-wired to c1's terminal without deleting r2"
)
print("5. a regular component landing on a terminal auto-wires without being deleted: OK")

# --- 6. Moving a regular component ONTO a Node (the reverse direction)
# merges that Node away too - not just Node-onto-component ------------------
node2 = window.add_component("junction", QPointF(-500, -400))
wire2 = WireItem(node2.terminals[0], r1.terminals[1])  # r1.terminals[1] is free since test 1's detach
wire2.attach()
window.scene.addItem(wire2)
app.processEvents()
assert len(node2.terminals[0].wires) == 1

b2 = window.add_component("battery", QPointF(-800, -400))
app.processEvents()
node2_pos = node2.terminals[0].scenePos()
# b2.terminals[0] sits at local (-40, 0); offset b2 so that terminal lands
# exactly on node2's terminal.
desired_b2_pos = QPointF(node2_pos.x() + 40, node2_pos.y())
a2 = view.mapFromScene(b2.scenePos())
b2_target_vp = view.mapFromScene(desired_b2_pos)
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a2)
QTest.mouseMove(vp, b2_target_vp)
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b2_target_vp)
app.processEvents()

assert node2 not in window.scene.items(), "moving a component onto a Node should delete that Node"
assert b2 in window.scene.items(), "the component that moved should never be deleted"
assert wire2 not in window.scene.items(), "the Node's old wire should be gone, replaced by a direct one"
wires_after_reverse = wires_in_scene()
assert any({w.start_terminal, w.end_terminal} == {b2.terminals[0], r1.terminals[1]} for w in wires_after_reverse), (
    "r1 should now be wired directly to b2, with the Node cut out of the middle"
)
print("6. moving a component onto a Node also merges the Node away (reverse direction): OK")

# --- 7. Dropping a regular component so BOTH of its terminals land on the
# same existing wire splices it in (deletes that wire, rewires through the
# component) instead of tapping each terminal in independently, which would
# leave the wire's original ends still directly connected - shorting the
# component out in parallel with it rather than actually inserting it -------
nodeA = window.add_component("junction", QPointF(600, 400))
nodeB = window.add_component("junction", QPointF(800, 400))
wire_ab = WireItem(nodeA.terminals[0], nodeB.terminals[0])
wire_ab.attach()
window.scene.addItem(wire_ab)
r3 = window.add_component("resistor", QPointF(600, 600))
app.processEvents()
assert wire_ab in wires_in_scene()

# r3's terminals sit at local (-40, 0) / (+40, 0); centering r3 at (700,400)
# lands terminal0 at (660,400) and terminal1 at (740,400) - both squarely
# along wire_ab's (600,400)-(800,400) span, not at either of its own ends.
desired_r3_pos = QPointF(700, 400)
a3 = view.mapFromScene(r3.scenePos())
b3 = view.mapFromScene(desired_r3_pos)
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a3)
QTest.mouseMove(vp, b3)
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b3)
app.processEvents()

assert wire_ab not in window.scene.items(), "the original wire should be deleted, not left shorting the resistor out"
assert r3.terminals[0].scenePos() == QPointF(660, 400)
assert r3.terminals[1].scenePos() == QPointF(740, 400)
spliced_wires = [
    w for w in wires_in_scene()
    if r3.terminals[0] in (w.start_terminal, w.end_terminal) or r3.terminals[1] in (w.start_terminal, w.end_terminal)
]
assert len(spliced_wires) == 2, f"expected exactly 2 new wires (nodeA<->r3, r3<->nodeB), got {len(spliced_wires)}"
assert any({w.start_terminal, w.end_terminal} == {nodeA.terminals[0], r3.terminals[0]} for w in spliced_wires), (
    "nodeA should now connect to the resistor's near terminal"
)
assert any({w.start_terminal, w.end_terminal} == {r3.terminals[1], nodeB.terminals[0]} for w in spliced_wires), (
    "the resistor's far terminal should connect to nodeB"
)
assert not any({w.start_terminal, w.end_terminal} == {nodeA.terminals[0], nodeB.terminals[0]} for w in wires_in_scene()), (
    "nodeA and nodeB should no longer be directly wired - only via the resistor now"
)
print("7. dropping a component with both terminals on the same wire splices it in instead of shorting it out: OK")

# --- 8. That splice (delete old wire + move + 2 new wires) undoes as a
# single step, same as the merge cases above ---------------------------------
window.undo_stack.undo()
app.processEvents()
assert wire_ab in window.scene.items(), "undo should restore the original wire"
assert not any(
    r3.terminals[0] in (w.start_terminal, w.end_terminal) or r3.terminals[1] in (w.start_terminal, w.end_terminal)
    for w in wires_in_scene()
), "undo should remove the splice wires"
print("8. undo restores the original wire and un-splices the resistor as one step: OK")

window.undo_stack.redo()
app.processEvents()
assert wire_ab not in window.scene.items()
spliced_wires_after_redo = [
    w for w in wires_in_scene()
    if r3.terminals[0] in (w.start_terminal, w.end_terminal) or r3.terminals[1] in (w.start_terminal, w.end_terminal)
]
assert len(spliced_wires_after_redo) == 2, "redo should re-apply both splice wires"
print("9. redo re-applies the splice: OK")

# --- 10. The same splice also happens for a component dropped fresh from
# the palette (or placed via a keyboard shortcut) - not just one that was
# already on the canvas and got moved. _on_component_dropped is the signal
# handler for both of those gestures (see canvas.py's dropEvent and
# mousePressEvent's placement-click branch), so driving it directly here
# exercises the same path a real palette drag takes. -----------------------
nodeC = window.add_component("junction", QPointF(600, -400))
nodeD = window.add_component("junction", QPointF(800, -400))
wire_cd = WireItem(nodeC.terminals[0], nodeD.terminals[0])
wire_cd.attach()
window.scene.addItem(wire_cd)
app.processEvents()

# A resistor placed centered at (700,-400) lands its terminals at
# (660,-400) and (740,-400) - squarely along wire_cd's span, same geometry
# as test 7 above, but via a fresh placement instead of a move.
resistors_before = {i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "resistor"}
window._on_component_dropped("resistor", QPointF(700, -400))
app.processEvents()
r4 = next(
    i for i in window.scene.items()
    if isinstance(i, ComponentItem) and i.component_type == "resistor" and i not in resistors_before
)

assert wire_cd not in window.scene.items(), "a component dropped fresh onto a wire should splice into it, same as a moved one"
assert r4.terminals[0].scenePos() == QPointF(660, -400)
assert r4.terminals[1].scenePos() == QPointF(740, -400)
fresh_spliced = [
    w for w in wires_in_scene()
    if r4.terminals[0] in (w.start_terminal, w.end_terminal) or r4.terminals[1] in (w.start_terminal, w.end_terminal)
]
assert len(fresh_spliced) == 2, f"expected exactly 2 new wires (nodeC<->r4, r4<->nodeD), got {len(fresh_spliced)}"
assert any({w.start_terminal, w.end_terminal} == {nodeC.terminals[0], r4.terminals[0]} for w in fresh_spliced)
assert any({w.start_terminal, w.end_terminal} == {r4.terminals[1], nodeD.terminals[0]} for w in fresh_spliced)
print("10. a component dropped fresh from the palette onto a wire splices in too, not just a moved one: OK")

# --- 11. That's a single undo step (the add + the splice together) ---------
window.undo_stack.undo()
app.processEvents()
assert r4 not in window.scene.items(), "undo should remove the just-placed component"
assert wire_cd in window.scene.items(), "undo should restore the original wire in the same step"
print("11. the fresh placement + splice undo together as a single step: OK")

# --- 12. Splicing must not create a duplicate wire either, when the
# component being spliced in is already directly wired to one of the
# target wire's endpoints (e.g. it was wired elsewhere in the diagram
# before being dragged on top of this wire). --------------------------------
nodeE = window.add_component("junction", QPointF(600, -800))
nodeF = window.add_component("junction", QPointF(800, -800))
wire_ef = WireItem(nodeE.terminals[0], nodeF.terminals[0])
wire_ef.attach()
window.scene.addItem(wire_ef)

r5 = window.add_component("resistor", QPointF(600, -600))
pre_existing = WireItem(r5.terminals[1], nodeF.terminals[0])  # r5 already wired to nodeF elsewhere
pre_existing.attach()
window.scene.addItem(pre_existing)
app.processEvents()

# center r5 at (700,-800): terminal0 lands at (660,-800, nearer to nodeE),
# terminal1 at (740,-800, nearer to nodeF) - both on wire_ef's span,
# splicing r5 in. terminal1 ends up as the "far" (nodeF-side) terminal,
# which already has a direct wire to nodeF.
desired_r5_pos = QPointF(700, -800)
a5 = view.mapFromScene(r5.scenePos())
b5 = view.mapFromScene(desired_r5_pos)
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a5)
QTest.mouseMove(vp, b5)
app.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b5)
app.processEvents()

assert wire_ef not in window.scene.items(), "the target wire should still have been spliced through"
assert pre_existing in window.scene.items(), "r5's pre-existing wire to nodeF should be left alone, not duplicated"
all_pairs = [frozenset({w.start_terminal, w.end_terminal}) for w in wires_in_scene()]
assert len(all_pairs) == len(set(all_pairs)), "no two wires should connect the exact same pair of terminals"
r5_wires = [w for w in wires_in_scene() if r5.terminals[0] in (w.start_terminal, w.end_terminal) or r5.terminals[1] in (w.start_terminal, w.end_terminal)]
assert len(r5_wires) == 2, f"expected exactly 2 wires on r5 (the untouched pre-existing one, plus one new near-side splice wire), got {len(r5_wires)}"
assert any(frozenset({r5.terminals[0], nodeE.terminals[0]}) == p for p in all_pairs), "r5's near terminal should be newly wired to nodeE"
print("12. splicing a component that's already wired to one of the target wire's endpoints doesn't duplicate that wire: OK")

print("ALL AUTO-CONNECT TESTS PASSED")
