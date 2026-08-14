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

print("ALL SPLIT-WIRE TESTS PASSED")
