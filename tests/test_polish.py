import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QMimeData, QByteArray, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import ComponentItem
from circuit_builder.ui.wire_item import WireItem
from circuit_builder.ui.palette import MIME_TYPE

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1000, 600)
window.show()
window.raise_()
window.activateWindow()
app.processEvents()
view = window.view
vp = view.viewport()
stack = window.undo_stack


def qpoint(p: QPointF) -> QPoint:
    return QPoint(round(p.x()), round(p.y()))


def drag(from_scene_pos: QPointF, to_scene_pos: QPointF, button=Qt.MouseButton.LeftButton, steps=5):
    a = view.mapFromScene(from_scene_pos)
    b = view.mapFromScene(to_scene_pos)
    QTest.mousePress(vp, button, Qt.KeyboardModifier.NoModifier, a)
    for i in range(1, steps + 1):
        p = a + (b - a) * (i / steps)
        QTest.mouseMove(vp, qpoint(p))
        app.processEvents()
    QTest.mouseRelease(vp, button, Qt.KeyboardModifier.NoModifier, b)
    app.processEvents()


def drag_connect(t1, t2):
    drag(t1.scenePos(), t2.scenePos())


# --- 1. Undo/redo: add component ------------------------------------------
window._on_component_dropped("resistor", QPointF(-100, 0))
r1 = next(i for i in window.scene.items() if isinstance(i, ComponentItem))
assert r1 in window.scene.items()
stack.undo()
assert r1 not in window.scene.items(), "undo should remove the added component"
stack.redo()
assert r1 in window.scene.items(), "redo should re-add the component"
print("1. undo/redo add component: OK")

# --- 2. Undo/redo: move component ------------------------------------------
start_pos = r1.pos()
target = QPointF(start_pos.x() + 120, start_pos.y() + 80)
drag(r1.scenePos(), target)
moved_pos = r1.pos()
assert moved_pos != start_pos, f"component should have moved, still at {moved_pos}"
stack.undo()
assert r1.pos() == start_pos, f"undo should restore original position, got {r1.pos()}"
stack.redo()
assert r1.pos() == moved_pos, "redo should reapply the move"
print("2. undo/redo move component: OK")

# --- 3. Undo/redo: rotate ---------------------------------------------------
r1.setSelected(True)
window.rotate_selected()
assert r1.rotation() == 90
stack.undo()
assert r1.rotation() == 0
stack.redo()
assert r1.rotation() == 90
r1.setSelected(False)
print("3. undo/redo rotate: OK")

# --- 4. Undo/redo: edit label/value ----------------------------------------
old_label, old_value = r1.label, r1.value
window._on_component_edit_requested(r1, "Rx", 2200.0)
assert r1.label == "Rx" and r1.value == 2200.0
stack.undo()
assert r1.label == old_label and r1.value == old_value
stack.redo()
assert r1.label == "Rx" and r1.value == 2200.0
print("4. undo/redo edit component: OK")

# --- 5. Undo/redo: add wire + cascade delete --------------------------------
window._on_component_dropped("battery", QPointF(150, 0))
v1 = next(i for i in window.scene.items() if isinstance(i, ComponentItem) and i.component_type == "battery")
drag_connect(r1.terminals[1], v1.terminals[0])
wires = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert len(wires) == 1, f"expected 1 wire, got {len(wires)}"
wire = wires[0]
stack.undo()  # undo wire add
assert wire not in window.scene.items()
stack.redo()
assert wire in window.scene.items()
print("5. undo/redo add wire: OK")

# delete r1 (cascades to the wire) then undo
r1.setSelected(True)
window.delete_selected()
assert r1 not in window.scene.items()
assert wire not in window.scene.items(), "cascade-deleted wire should be gone"
stack.undo()
assert r1 in window.scene.items(), "undo delete should restore the component"
assert wire in window.scene.items(), "undo delete should restore the cascaded wire"
assert wire in r1.terminals[1].wires, "wire should be reattached to its terminal on undo"
print("6. undo/redo cascade delete: OK")

# --- 7. Selection outline tighter than the safety bounding box -------------
outline = r1._outline_rect()
bounds = r1.boundingRect()
assert outline.width() < bounds.width() and outline.height() < bounds.height(), (
    f"outline {outline} should be smaller than bounds {bounds}"
)
print("7. selection outline tighter than bounding box: OK")

# --- 8. Zoom in/out/fit/reset -----------------------------------------------
view.reset_zoom()
assert abs(view.transform().m11() - 1.0) < 1e-6
view.zoom_in()
zoomed_in = view.transform().m11()
assert zoomed_in > 1.0, zoomed_in
view.zoom_out()
view.zoom_out()
zoomed_out = view.transform().m11()
assert zoomed_out < 1.0, zoomed_out
for _ in range(60):
    view.zoom_out()
assert view._zoom >= view.MIN_ZOOM - 1e-6, view._zoom
for _ in range(60):
    view.zoom_in()
assert view._zoom <= view.MAX_ZOOM + 1e-6, view._zoom
view.reset_zoom()
view.zoom_to_fit()
assert view.transform().m11() > 0
print("8. zoom in/out/clamp/fit/reset: OK")

# --- 9. Middle-drag panning --------------------------------------------------
view.reset_zoom()
h_before = view.horizontalScrollBar().value()
v_before = view.verticalScrollBar().value()
p1_scene = view.mapToScene(QPoint(400, 300))
p2_scene = view.mapToScene(QPoint(250, 200))
drag(p1_scene, p2_scene, button=Qt.MouseButton.MiddleButton)
h_after = view.horizontalScrollBar().value()
v_after = view.verticalScrollBar().value()
assert (h_after, v_after) != (h_before, v_before), "middle-drag should have panned the view"
print("9. middle-drag panning: OK")

# --- 10. Drag preview ghost appears/disappears ------------------------------
mime = QMimeData()
mime.setData(MIME_TYPE, QByteArray(b"capacitor"))

enter_pos = QPointF(300, 300)
enter_event = QDragEnterEvent(enter_pos.toPoint(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
view.dragEnterEvent(enter_event)
assert view._drag_preview is not None, "expected a drag preview item"
assert isinstance(view._drag_preview, ComponentItem)
assert view._drag_preview in window.scene.items()

move_pos = QPointF(340, 340)
move_event = QDragMoveEvent(move_pos.toPoint(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
view.dragMoveEvent(move_event)

drop_event = QDropEvent(move_pos, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
# exclude the ghost preview itself - it's a ComponentItem too, but gets
# removed (not counted) once the drop places the real component
before_count = len([i for i in window.scene.items() if isinstance(i, ComponentItem) and i is not view._drag_preview])
view.dropEvent(drop_event)
app.processEvents()
after_count = len([i for i in window.scene.items() if isinstance(i, ComponentItem)])
assert view._drag_preview is None, "preview should be cleared after drop"
assert after_count == before_count + 1, "drop should have added exactly one new component"
print("10. drag preview ghost lifecycle: OK")

print("ALL POLISH TESTS PASSED")
