import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import ComponentItem

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1000, 600)
window.show()
window.raise_()
window.activateWindow()
app.processEvents()
view = window.view
vp = view.viewport()


def qpoint(p):
    return QPoint(round(p.x()), round(p.y()))


def drag(from_scene_pos, to_scene_pos, button=Qt.MouseButton.LeftButton, modifier=Qt.KeyboardModifier.NoModifier, steps=5):
    a = view.mapFromScene(from_scene_pos)
    b = view.mapFromScene(to_scene_pos)
    QTest.mousePress(vp, button, modifier, a)
    for i in range(1, steps + 1):
        p = a + (b - a) * (i / steps)
        QTest.mouseMove(vp, qpoint(p))
        app.processEvents()
    QTest.mouseRelease(vp, button, modifier, b)
    app.processEvents()


# --- 1. Rotate-before-place via real shortcut dispatch, then place ---------
view.start_placement("resistor")
QTest.keyClick(view, Qt.Key.Key_R)
QTest.keyClick(view, Qt.Key.Key_R)
app.processEvents()
assert view._pending_place_rotation == 180.0

click_vp = view.mapFromScene(QPointF(200, 200))
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, click_vp)
app.processEvents()
placed = [i for i in window.scene.items() if isinstance(i, ComponentItem)]
assert len(placed) == 1
assert placed[0].rotation() == 180.0, placed[0].rotation()
print("1. rotate-before-place applies rotation to the placed component: OK")

# --- 2. Ctrl+R rotates a selection; plain R starts a new placement instead -
placed[0].setSelected(True)
QTest.keyClick(view, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
app.processEvents()
assert placed[0].rotation() == 270.0, placed[0].rotation()
print("2. Ctrl+R rotates the selected component: OK")

QTest.keyClick(view, Qt.Key.Key_R)
app.processEvents()
assert view._pending_place_type == "resistor", "plain R should start placing a new resistor"
assert placed[0].rotation() == 270.0, "plain R must not also rotate the existing selection"
view.cancel_placement()
placed[0].setSelected(False)
print("3. plain R (outside placement mode) places a new resistor instead of rotating: OK")

# --- 4. Shift+drag a Node's terminal moves the node (not a wire) -----------
window._on_component_dropped("junction", QPointF(-100, 0))
j1 = next(i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "junction")
start_pos = j1.pos()
target = QPointF(start_pos.x() + 120, start_pos.y() + 80)
drag(j1.terminals[0].scenePos(), target, modifier=Qt.KeyboardModifier.ShiftModifier)
from circuit_builder.ui.wire_item import WireItem
wires = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert len(wires) == 0, "Shift+drag on a terminal should move the component, not start a wire"
assert j1.pos() != start_pos, f"node should have moved, still at {j1.pos()}"
print("4. Shift+drag a Node's terminal moves it instead of wiring: OK")

# --- 5. That move is undoable -----------------------------------------------
moved_pos = j1.pos()
window.undo_stack.undo()
assert j1.pos() == start_pos, f"undo should restore original position, got {j1.pos()}"
window.undo_stack.redo()
assert j1.pos() == moved_pos
print("5. Shift+drag move is undo/redo tracked: OK")

# --- 6. Without Shift, dragging a terminal still starts a wire as before ---
window._on_component_dropped("resistor", QPointF(-300, 0))
r1 = next(i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "resistor")
drag(r1.terminals[1].scenePos(), j1.terminals[0].scenePos())
wires_after = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert len(wires_after) == 1, f"plain drag (no Shift) should still start a wire, got {len(wires_after)} wires"
print("6. plain drag on a terminal (no Shift) still wires as before: OK")

# --- 7. Pan tool: toggling it makes left-drag pan the canvas ---------------
view.reset_zoom()
view.scene().clearSelection()
h_before = view.horizontalScrollBar().value()
v_before = view.verticalScrollBar().value()
window._pan_tool_action.setChecked(True)
app.processEvents()
assert view._pan_tool_active is True
drag(QPointF(0, 0), QPointF(-150, -100))  # over empty canvas, would normally rubber-band select
h_after = view.horizontalScrollBar().value()
v_after = view.verticalScrollBar().value()
assert (h_after, v_after) != (h_before, v_before), "left-drag should pan while the Pan Tool is active"
assert len(window.scene.selectedItems()) == 0, "pan-tool drag should not perform a rubber-band selection"
print("7. Pan Tool: left-drag pans instead of selecting: OK")

# --- 8. Turning the pan tool back off restores normal left-drag selection --
window._pan_tool_action.setChecked(False)
app.processEvents()
assert view._pan_tool_active is False
view.scene().clearSelection()
drag(r1.scenePos(), r1.scenePos())  # simple click on the resistor body
assert r1.isSelected(), "left-click should select a component again once the Pan Tool is off"
print("8. Pan Tool: disabling it restores normal click/drag behavior: OK")

print("ALL INTERACTION TESTS PASSED")
