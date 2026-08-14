import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import ComponentItem
from circuit_builder.ui.wire_item import WireItem

app = QApplication(sys.argv)
window = MainWindow()
window.show()

# Simulate dropping a resistor and a battery, then wiring them.
r1 = window.add_component("resistor", QPointF(0, 0))
v1 = window.add_component("battery", QPointF(200, 0))
assert r1.label == "R1", r1.label
assert v1.label == "V1", v1.label

wire = WireItem(r1.terminals[1], v1.terminals[0])
wire.attach()
window.scene.addItem(wire)

# Move a component and confirm the wire follows.
r1.setPos(QPointF(-40, -40))
r1.update_wires()
expected_start = r1.terminals[1].scenePos()
actual_line = wire.line()
assert abs(actual_line.p1().x() - expected_start.x()) < 0.01, "wire did not follow component"
assert abs(actual_line.p1().y() - expected_start.y()) < 0.01, "wire did not follow component"

# Rotate and confirm wire still attached correctly.
r1.setRotation(90)
r1.update_wires()
expected_start2 = r1.terminals[1].scenePos()
assert abs(wire.line().p1().x() - expected_start2.x()) < 0.01, "wire did not follow rotation"

# Save then load into a fresh window, check round-trip fidelity.
save_path = os.path.join(os.path.dirname(__file__), "test_circuit.json")
window._current_path = None
circuit = window._build_circuit_model()
circuit.save(save_path)

window2 = MainWindow()
from circuit_builder.core.circuit_model import Circuit
loaded = Circuit.load(save_path)
window2._load_circuit(loaded)

items = [i for i in window2.scene.items() if isinstance(i, ComponentItem)]
wires = [i for i in window2.scene.items() if isinstance(i, WireItem)]
assert len(items) == 2, f"expected 2 components after load, got {len(items)}"
assert len(wires) == 1, f"expected 1 wire after load, got {len(wires)}"

labels = sorted(i.label for i in items)
assert labels == ["R1", "V1"], labels

r1_loaded = next(i for i in items if i.label == "R1")
assert abs(r1_loaded.rotation() - 90) < 0.01, r1_loaded.rotation()

# Delete component and confirm attached wire is also removed.
r1_loaded.setSelected(True)
window2.delete_selected()
remaining_wires = [i for i in window2.scene.items() if isinstance(i, WireItem)]
assert len(remaining_wires) == 0, "wire should be removed when connected component is deleted"

os.remove(save_path)

print("SMOKE TEST PASSED")
