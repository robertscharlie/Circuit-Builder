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
window.raise_()
window.activateWindow()
app.processEvents()
view = window.view

# QMenu.exec() opens a real, blocking native popup with no way for a headless
# test to click it - CircuitView exposes _menu_exec_override as a testing
# seam specifically for this (see canvas.py); production code never sets it.
view._menu_exec_override = lambda menu: menu.actions()[0] if menu.actions() else None


def rmb(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos), QPointF(pos), Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier)


def lmb(pos):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos), QPointF(pos), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def move(pos):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(pos), QPointF(pos), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)


r1 = window.add_component("resistor", QPointF(-200, 0))
v1 = window.add_component("battery", QPointF(200, 0))
wire = WireItem(r1.terminals[1], v1.terminals[0])
wire.attach()
window.scene.addItem(wire)
app.processEvents()

# --- 1. Right-click a wired terminal -> "Move Node" -> detaches the wire ---
terminal_scene_pos = r1.terminals[1].scenePos()
view.mousePressEvent(rmb(view.mapFromScene(terminal_scene_pos)))
app.processEvents()

assert view._pending_move_target is not None, "Move Node should enter move-mode for the new node"
node = view._pending_move_target
assert node.component_type == "junction"
assert node not in (r1, v1)
# start_move_component() immediately re-snaps the node to the real cursor
# position for visual feedback (same as the existing Move Component/Node
# flow), so node.pos() itself is transient here - but the *undo baseline* it
# captured just before doing that snap is the terminal's original position,
# which is what matters: Escape (or undoing the move) puts it right back.
assert view._pending_move_start_pos == QPointF(terminal_scene_pos.x(), terminal_scene_pos.y()), (
    f"node's pre-move position should be exactly where the terminal was, got {view._pending_move_start_pos}"
)

wires = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert wire not in window.scene.items(), "the original wire should be gone"
assert len(wires) == 1, f"expected exactly 1 wire (now node<->v1), got {len(wires)}"
new_wire = wires[0]
assert {new_wire.start_terminal, new_wire.end_terminal} == {node.terminals[0], v1.terminals[0]}
assert wire not in r1.terminals[1].wires, "r1's terminal should no longer reference the old wire"
assert new_wire not in r1.terminals[1].wires, "r1 should have no wire on that terminal anymore - it's disconnected"
print('1. right-click a wired terminal -> "Move Node" detaches the wire onto a free Node: OK')

# --- 2. That new node can then be dragged to its actual destination --------
target_vp = view.mapFromScene(QPointF(-300, -140))
view.mouseMoveEvent(move(target_vp))
app.processEvents()
view.mousePressEvent(lmb(target_vp))
app.processEvents()
assert view._pending_move_target is None
assert node.pos() == QPointF(-300, -140), f"node should have moved to the drop point, got {node.pos()}"
print("2. the detached node can then be dragged to wherever it's needed: OK")

# --- 3. Undo restores the original direct wire; redo re-detaches -----------
window.undo_stack.undo()  # undo the move
window.undo_stack.undo()  # undo the detach
app.processEvents()
wires_after_undo = [i for i in window.scene.items() if isinstance(i, WireItem)]
nodes_after_undo = [i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction"]
assert wires_after_undo == [wire], wires_after_undo
assert nodes_after_undo == [], nodes_after_undo
assert wire in r1.terminals[1].wires, "r1 should be reconnected after undo"
print("3. undo removes the node and restores the direct wire: OK")

window.undo_stack.redo()
window.undo_stack.redo()
app.processEvents()
wires_after_redo = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert wire not in window.scene.items()
assert len(wires_after_redo) == 1
print("4. redo re-detaches and re-applies the move: OK")

# --- 5. An unconnected terminal falls back to the normal "Move Component"
# menu instead (nothing to detach) -------------------------------------------
r2 = window.add_component("capacitor", QPointF(0, 200))
before_types = sorted(i.component_type for i in window.scene.items() if isinstance(i, ComponentItem))
view.mousePressEvent(rmb(view.mapFromScene(r2.terminals[0].scenePos())))
app.processEvents()
assert view._pending_move_target is r2, "an unconnected terminal should just move the whole component"
view.cancel_move_component()
after_types = sorted(i.component_type for i in window.scene.items() if isinstance(i, ComponentItem))
assert before_types == after_types, "no node should have been created for an unconnected terminal"
print("5. right-clicking an unconnected terminal falls back to moving the whole component: OK")

print("ALL DETACH-TERMINAL TESTS PASSED")
