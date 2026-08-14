import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QLineF, QPoint, QPointF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QApplication, QGraphicsLineItem

from circuit_builder.core.circuit_model import Circuit
from circuit_builder.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.resize(1000, 600)
window.show()
app.processEvents()
view = window.view

# --- 1. Placement ghost active when New Circuit clears the scene -----------
view.start_placement("resistor")
window.new_circuit()
view._move_drag_preview(QPoint(100, 100))  # would raise RuntimeError if dangling
assert view._pending_place_type is None
print("1. placement ghost survives New Circuit cleanly: OK")

# --- 2. In-progress wire-drag temp line when New Circuit clears the scene --
r1 = window.add_component("resistor", QPointF(-100, 0))
window.add_component("battery", QPointF(100, 0))
view._wire_start = r1.terminals[1]
temp = QGraphicsLineItem(QLineF(r1.terminals[1].scenePos(), r1.terminals[1].scenePos()))
temp.setPen(QPen(QColor("#e07a1f"), 1.5))
window.scene.addItem(temp)
view._temp_line = temp
window.new_circuit()  # would raise RuntimeError on the dangling temp_line if unfixed
assert view._wire_start is None
assert view._temp_line is None
print("2. in-progress wire-drag survives New Circuit cleanly: OK")

# --- 3. Placement ghost active when opening a file (_load_circuit) ---------
view.start_placement("capacitor")
window._load_circuit(Circuit())
view._move_drag_preview(QPoint(50, 50))
assert view._pending_place_type is None
print("3. placement ghost survives file load cleanly: OK")

print("ALL BUGFIX REGRESSION TESTS PASSED")
