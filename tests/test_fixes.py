import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import GRID_SIZE, TERMINAL_OFFSET
from circuit_builder.ui.wire_item import WireItem
from circuit_builder.ui.palette import ComponentPalette

app = QApplication(sys.argv)
window = MainWindow()

# --- 1. Terminal grid alignment -----------------------------------------
r1 = window.add_component("resistor", QPointF(-140, -60))
for t in r1.terminals:
    sp = t.scenePos()
    assert sp.x() % GRID_SIZE == 0, f"terminal x {sp.x()} not on grid"
    assert sp.y() % GRID_SIZE == 0, f"terminal y {sp.y()} not on grid"
r1.setRotation(90)
for t in r1.terminals:
    sp = t.scenePos()
    assert sp.x() % GRID_SIZE == 0, f"rotated terminal x {sp.x()} not on grid"
    assert sp.y() % GRID_SIZE == 0, f"rotated terminal y {sp.y()} not on grid"
print("1. terminal grid alignment: OK")

# --- 2. Duplicate wire prevention ----------------------------------------
r1.setRotation(0)
v1 = window.add_component("battery", QPointF(120, -60))
view = window.view

def connect(t1, t2):
    start_vp = view.mapFromScene(t1.scenePos())
    end_vp = view.mapFromScene(t2.scenePos())
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt as Qt_

    def ev(t, pos, button, buttons):
        return QMouseEvent(t, QPointF(pos), QPointF(pos), button, buttons, Qt_.KeyboardModifier.NoModifier)

    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, start_vp, Qt_.MouseButton.LeftButton, Qt_.MouseButton.LeftButton))
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, end_vp, Qt_.MouseButton.NoButton, Qt_.MouseButton.LeftButton))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, end_vp, Qt_.MouseButton.LeftButton, Qt_.MouseButton.NoButton))

connect(r1.terminals[1], v1.terminals[0])
connect(r1.terminals[1], v1.terminals[0])  # attempt duplicate
connect(v1.terminals[0], r1.terminals[1])  # attempt duplicate, reversed direction
wires = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert len(wires) == 1, f"expected exactly 1 wire, got {len(wires)}"
print("2. duplicate wire prevention: OK")

# --- 3. Junction / node component -----------------------------------------
assert "junction" in window._counters
j1 = window.add_component("junction", QPointF(-40, 60))
assert len(j1.terminals) == 1, f"junction should have exactly 1 terminal, got {len(j1.terminals)}"
c1 = window.add_component("capacitor", QPointF(-260, 60))
connect(j1.terminals[0], c1.terminals[1])
connect(j1.terminals[0], r1.terminals[0])  # second, distinct wire off the same junction terminal
wires = [i for i in window.scene.items() if isinstance(i, WireItem)]
assert len(wires) == 3, f"expected 3 wires total after junction fan-out, got {len(wires)}"
print("3. junction fan-out wiring: OK")

# junction should not open the edit dialog on double-click (would block headless test if it did)
from PySide6.QtCore import QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Qt as Qt_
dbl = QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(0, 0), QPointF(0, 0), Qt_.MouseButton.LeftButton, Qt_.MouseButton.LeftButton, Qt_.KeyboardModifier.NoModifier)
j1.mouseDoubleClickEvent(dbl)  # should return immediately, no dialog
print("4. junction double-click no-op: OK")

# --- 5. Save/load round trip including a junction --------------------------
from circuit_builder.core.circuit_model import Circuit

save_path = os.path.join(os.path.dirname(__file__), "test_circuit_junction.json")
circuit = window._build_circuit_model()
circuit.save(save_path)
window2 = MainWindow()
window2._load_circuit(Circuit.load(save_path))
from circuit_builder.ui.component_item import ComponentItem
loaded_types = sorted(i.component_type for i in window2.scene.items() if isinstance(i, ComponentItem))
assert loaded_types.count("junction") == 1, loaded_types
loaded_wires = [i for i in window2.scene.items() if isinstance(i, WireItem)]
assert len(loaded_wires) == 3, len(loaded_wires)
os.remove(save_path)
print("5. save/load round trip with junction: OK")

# --- 6. Palette icons render actual (non-blank) pixmaps ---------------------
palette = ComponentPalette()
assert palette.count() == 5, palette.count()
from circuit_builder.ui.component_item import render_symbol_pixmap
for key in ("resistor", "battery", "capacitor", "inductor", "junction"):
    pix = render_symbol_pixmap(key)
    img = pix.toImage()
    has_ink = any(
        img.pixelColor(x, y).alpha() > 0
        for x in range(0, img.width(), 3)
        for y in range(0, img.height(), 3)
    )
    assert has_ink, f"{key} icon appears blank"
print("6. palette icons non-blank: OK")

print("ALL FIX TESTS PASSED")
