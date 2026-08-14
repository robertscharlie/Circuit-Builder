import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from circuit_builder.ui.main_window import MainWindow
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


r1 = window.add_component("resistor", QPointF(-200, 0))
v1 = window.add_component("battery", QPointF(200, 0))
wire = WireItem(r1.terminals[1], v1.terminals[0])
wire.attach()
window.scene.addItem(wire)
window._on_component_dropped("junction", QPointF(0, 120))
app.processEvents()
j1 = next(i for i in window.scene.items() if hasattr(i, "component_type") and i.component_type == "junction")

# --- 1. Right-click a component -> "Move Component" -> follows the cursor,
# click elsewhere to drop it -------------------------------------------------
start_pos = r1.pos()
view.mousePressEvent(rmb(view.mapFromScene(r1.scenePos())))
app.processEvents()
assert view._pending_move_target is r1, "context menu's Move action should enter move-mode for r1"

target_vp = view.mapFromScene(QPointF(-100, -100))
view.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(target_vp), QPointF(target_vp), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
app.processEvents()
assert r1.pos() == QPointF(-100, -100), f"component should follow the cursor (grid-snapped), got {r1.pos()}"

view.mousePressEvent(lmb(target_vp))
app.processEvents()
assert view._pending_move_target is None, "move-mode should end after the confirming click"
assert r1.pos() == QPointF(-100, -100)
assert r1.pos() != start_pos
print("1. right-click a component -> Move Component -> click to drop it at the new spot: OK")

# wire should have followed automatically (WireItem tracks terminal scenePos live)
line = wire.line()
assert abs(line.p1().x() - r1.terminals[1].scenePos().x()) < 0.01
assert abs(line.p1().y() - r1.terminals[1].scenePos().y()) < 0.01
print("2. the wire attached to the moved component followed it: OK")

# --- 3. The move is undo/redo tracked --------------------------------------
moved_pos = r1.pos()
window.undo_stack.undo()
assert r1.pos() == start_pos, f"undo should restore the original position, got {r1.pos()}"
window.undo_stack.redo()
assert r1.pos() == moved_pos
print("3. Move Component is undo/redo tracked: OK")

# --- 4. Escape cancels a move in progress, restoring the original position -
before_escape_pos = r1.pos()
view.mousePressEvent(rmb(view.mapFromScene(r1.scenePos())))
app.processEvents()
assert view._pending_move_target is r1
view._move_pending_target(view.mapFromScene(QPointF(300, 300)))
app.processEvents()
assert r1.pos() == QPointF(300, 300)
esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
view.keyPressEvent(esc)
app.processEvents()
assert view._pending_move_target is None
assert r1.pos() == before_escape_pos, "Escape should restore the pre-move position"
print("4. Escape cancels an in-progress move, restoring the original position: OK")

# --- 5. Right-click a Node -> "Move Node" -----------------------------------
node_start = j1.pos()
view.mousePressEvent(rmb(view.mapFromScene(j1.scenePos())))
app.processEvents()
assert view._pending_move_target is j1, "context menu's Move action should enter move-mode for the Node"
new_node_vp = view.mapFromScene(QPointF(60, 60))
view.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(new_node_vp), QPointF(new_node_vp), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
app.processEvents()
view.mousePressEvent(lmb(new_node_vp))
app.processEvents()
assert j1.pos() == QPointF(60, 60), f"node should have moved, got {j1.pos()}"
assert j1.pos() != node_start
print("5. right-click a Node -> Move Node -> click to relocate it: OK")

print("ALL MOVE-VIA-MENU TESTS PASSED")
