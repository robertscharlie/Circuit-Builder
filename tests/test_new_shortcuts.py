import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, Qt
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


def place_via_shortcut(key, expected_type):
    QTest.keyClick(view, key)
    app.processEvents()
    assert view._pending_place_type == expected_type, f"{key} should start placing {expected_type}, got {view._pending_place_type}"
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, vp.rect().center())
    app.processEvents()


# --- 1. R/B/C/I/N each place the right component type ----------------------
place_via_shortcut(Qt.Key.Key_R, "resistor")
place_via_shortcut(Qt.Key.Key_B, "battery")
place_via_shortcut(Qt.Key.Key_C, "capacitor")
place_via_shortcut(Qt.Key.Key_I, "inductor")
place_via_shortcut(Qt.Key.Key_N, "junction")

placed = [i for i in window.scene.items() if isinstance(i, ComponentItem)]
types = sorted(i.component_type for i in placed)
assert types == ["battery", "capacitor", "inductor", "junction", "resistor"], types
print("1. R/B/C/I/N shortcuts place the right component types: OK")

# --- 2. Ctrl+R rotates a selection (R alone is now the resistor shortcut) --
r1 = next(i for i in placed if i.component_type == "resistor")
r1.setSelected(True)
QTest.keyClick(view, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
app.processEvents()
assert r1.rotation() == 90, r1.rotation()
r1.setSelected(False)
print("2. Ctrl+R rotates the selected component: OK")

print("ALL NEW SHORTCUT TESTS PASSED")
