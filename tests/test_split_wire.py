import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import ComponentItem
from circuit_builder.ui.wire_item import WireItem

app = QApplication(sys.argv)
window = MainWindow()
window.resize(900, 500)
window.show()
app.processEvents()
view = window.view

# QMenu.exec() opens a real, blocking native popup with no way for a headless
# test to click it - CircuitView exposes _menu_exec_override as a testing
# seam specifically for this (see canvas.py); production code never sets it.
view._menu_exec_override = lambda menu: menu.actions()[0] if menu.actions() else None


def rmb(t, pos):
    return QMouseEvent(t, QPointF(pos), QPointF(pos), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)


def right_click(viewport_pos):
    view.mousePressEvent(rmb(QEvent.Type.MouseButtonPress, viewport_pos))


r1 = window.add_component("resistor", QPointF(-200, 0))
v1 = window.add_component("battery", QPointF(200, 0))
wire = WireItem(r1.terminals[1], v1.terminals[0])
wire.attach()
window.scene.addItem(wire)
app.processEvents()

# --- 1. Right-click a wire -> "Split Wire Here" -> splits at the click point
click_scene_pos = QPointF(3, 0)  # on the wire (y=0), nearest grid point should be (0, 0)
right_click(view.mapFromScene(click_scene_pos))
app.processEvents()

wires = [i for i in window.scene.items() if isinstance(i, WireItem)]
junctions = [i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"]
assert wire not in window.scene.items(), "original wire should be gone after split"
assert len(wires) == 2, f"expected 2 wires after split, got {len(wires)}"
assert len(junctions) == 1, f"expected 1 new junction, got {len(junctions)}"
node = junctions[0]
assert node.pos() == QPointF(0, 0), f"node should snap to nearest grid point, got {node.pos()}"

endpoints = {frozenset({w.start_terminal, w.end_terminal}) for w in wires}
assert frozenset({r1.terminals[1], node.terminals[0]}) in endpoints
assert frozenset({node.terminals[0], v1.terminals[0]}) in endpoints
print("1. right-click a wire -> Split Wire Here -> splits at a grid-snapped Node: OK")

# --- 2. Undo restores the single original wire; redo re-splits -------------
window.undo_stack.undo()
app.processEvents()
wires_after_undo = [i for i in window.scene.items() if isinstance(i, WireItem)]
junctions_after_undo = [i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"]
assert wires_after_undo == [wire], wires_after_undo
assert junctions_after_undo == [], junctions_after_undo
print("2. undo restores the original single wire: OK")

window.undo_stack.redo()
app.processEvents()
wires_after_redo = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert len(wires_after_redo) == 2
print("3. redo re-splits it: OK")

# --- 4. Right-clicking empty canvas is a no-op ------------------------------
before = len(window.scene.items())
empty_vp = view.mapFromScene(QPointF(-500, -500))
view.mousePressEvent(rmb(QEvent.Type.MouseButtonPress, empty_vp))
app.processEvents()
assert len(window.scene.items()) == before, "right-click on empty canvas should not create a node"
print("4. right-click away from a wire/component is a no-op: OK")

# --- 5. Edit > Split Wire splits the selected wire at its midpoint ---------
remaining_wire = [i for i in window.scene.items() if isinstance(i, WireItem)][0]
window.scene.clearSelection()
remaining_wire.setSelected(True)
window.split_selected_wire()
app.processEvents()
wires_after_menu_split = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert remaining_wire not in window.scene.items(), "Edit > Split Wire should have removed the selected wire"
assert len(wires_after_menu_split) == 3, f"expected 3 wires total, got {len(wires_after_menu_split)}"
print("5. Edit > Split Wire splits the selected wire at its midpoint: OK")

# with nothing selected, it's a no-op
window.scene.clearSelection()
before_count = len(window.scene.items())
window.split_selected_wire()
assert len(window.scene.items()) == before_count, "Split Wire with no selection should do nothing"
print("6. Edit > Split Wire with no wire selected is a no-op: OK")

# --- 7. Right-click a wire -> "Split and Move" -> splits it AND immediately
# hands the new Node to move-mode (follows the cursor, same as picking
# "Move Node" afterward separately) instead of leaving it sitting still. ----

wire_for_move_split = [i for i in window.scene.items() if isinstance(i, WireItem)][0]
view._menu_exec_override = lambda menu: next(a for a in menu.actions() if a.text() == "Split and Move")

before_junctions = {i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"}
start = wire_for_move_split.start_terminal.scenePos()
end = wire_for_move_split.end_terminal.scenePos()
click_scene_pos2 = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)  # wire's midpoint - clear of both terminals
right_click(view.mapFromScene(click_scene_pos2))
app.processEvents()

after_junctions = {i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"}
new_nodes = after_junctions - before_junctions
assert len(new_nodes) == 1, f"expected exactly one new Node from the split, got {len(new_nodes)}"
new_node = next(iter(new_nodes))
assert view._pending_move_target is new_node, "the new Node should immediately be in move-mode, following the cursor"
print("7. right-click a wire -> Split and Move -> splits it AND puts the new Node into move-mode right away: OK")

# Moving the mouse actually moves it, and clicking drops it at the new spot
# (a SEPARATE undo step from the split, same as the existing detach+move
# pattern - splitting alone shouldn't force a specific final position).
drop_scene_pos = QPointF(new_node.pos().x() + 60, new_node.pos().y() + 40)
move_event = QMouseEvent(
    QEvent.Type.MouseMove,
    view.mapFromScene(drop_scene_pos),
    view.mapFromScene(drop_scene_pos),
    Qt.MouseButton.NoButton,
    Qt.MouseButton.NoButton,
    Qt.KeyboardModifier.NoModifier,
)
view.mouseMoveEvent(move_event)
app.processEvents()
assert new_node.pos() == QPointF(round(drop_scene_pos.x() / 20) * 20, round(drop_scene_pos.y() / 20) * 20), (
    "the Node should follow the cursor (grid-snapped) while the move is pending"
)

left_click_pos = view.mapFromScene(drop_scene_pos)
left_click = QMouseEvent(QEvent.Type.MouseButtonPress, left_click_pos, left_click_pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
view.mousePressEvent(left_click)
app.processEvents()
assert view._pending_move_target is None, "clicking should drop the Node and end the pending move"
print("8. moving the mouse follows the cursor (grid-snapped), and clicking drops it at the new spot: OK")

# Split and the drop-move are two separate undo steps: undoing once only
# undoes the move (Node stays, back at its split-time position); undoing
# again removes the split itself.
node_pos_after_drop = new_node.pos()
window.undo_stack.undo()
app.processEvents()
assert new_node in [i for i in window.scene.items() if isinstance(i, ComponentItem)], "undoing the move shouldn't remove the Node itself"
assert new_node.pos() != node_pos_after_drop, "undoing the move should restore its split-time position"
window.undo_stack.undo()
app.processEvents()
assert new_node not in window.scene.items(), "undoing the split itself should remove the Node"
print("9. the split and the subsequent move are separate undo steps: OK")

window.undo_stack.redo()
window.undo_stack.redo()
app.processEvents()
assert new_node.pos() == node_pos_after_drop, "redoing both steps should restore the split then the moved position"
print("10. redo re-applies both the split and the move: OK")

print("ALL SPLIT-WIRE TESTS PASSED")
