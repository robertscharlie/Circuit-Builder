import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuit_builder.core.circuit_model import Circuit, ComponentData, TerminalRef, WireData
from circuit_builder.core.simulation import simulate
from circuit_builder.ui.component_item import ComponentItem
from circuit_builder.ui.main_window import MainWindow

# --- core solver: no Qt involved, works straight off the example files -----

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "example files")


def volt(result, comp_id, terminal):
    v = result.voltage_at(comp_id, terminal)
    assert v is not None, f"expected a determined voltage at ({comp_id}, {terminal})"
    return v


def by_label(circuit, label):
    return next(c for c in circuit.components if c.label == label)


circuit = Circuit.load(os.path.join(EXAMPLES, "simple_loop.json"))
result = simulate(circuit)
v1, r1 = by_label(circuit, "V1"), by_label(circuit, "R1")
assert abs(volt(result, v1.id, 0) - 9.0) < 1e-6, "battery + terminal should be at 9V"
assert abs(volt(result, v1.id, 1) - 0.0) < 1e-6, "battery - terminal is the 0V reference"
assert abs(volt(result, r1.id, 0) - 9.0) < 1e-6
assert abs(volt(result, r1.id, 1) - 0.0) < 1e-6
print("1. simple loop (battery + resistor): OK")

circuit = Circuit.load(os.path.join(EXAMPLES, "voltage_divider.json"))
result = simulate(circuit)
r1, r2 = by_label(circuit, "R1"), by_label(circuit, "R2")
# equal resistors -> the tap between them sits at exactly half the supply
assert abs(volt(result, r1.id, 1) - 4.5) < 1e-6, "equal-resistor divider should tap at half the supply voltage"
assert abs(volt(result, r2.id, 1) - 0.0) < 1e-6
print("2. voltage divider (equal resistors tap at half the supply): OK")

circuit = Circuit.load(os.path.join(EXAMPLES, "series_rc_circuit.json"))
result = simulate(circuit)
r1, c1 = by_label(circuit, "R1"), by_label(circuit, "C1")
# DC steady state: a capacitor is an open circuit, so no current flows at
# all - a series resistor carrying no current has zero voltage drop.
assert abs(volt(result, r1.id, 0) - volt(result, r1.id, 1)) < 1e-6, "resistor in series with an open capacitor carries no current, so no voltage drop"
assert abs(volt(result, c1.id, 0) - 9.0) < 1e-6
assert abs(volt(result, c1.id, 1) - 0.0) < 1e-6
print("3. series RC at DC steady state (capacitor blocks current): OK")

circuit = Circuit.load(os.path.join(EXAMPLES, "series_rlc_circuit.json"))
result = simulate(circuit)
l1 = by_label(circuit, "L1")
# an inductor is a dead short at DC steady state - both its terminals must
# land on the exact same electrical node.
assert result.terminal_node[(l1.id, 0)] == result.terminal_node[(l1.id, 1)], "inductor terminals should merge into one electrical node at DC"
print("4. series RLC at DC steady state (inductor is a short): OK")

circuit = Circuit.load(os.path.join(EXAMPLES, "parallel_resistors.json"))
result = simulate(circuit)
r1, r2 = by_label(circuit, "R1"), by_label(circuit, "R2")
v_r1 = abs(volt(result, r1.id, 0) - volt(result, r1.id, 1))
v_r2 = abs(volt(result, r2.id, 0) - volt(result, r2.id, 1))
assert abs(v_r1 - v_r2) < 1e-6, "resistors in parallel must have the same voltage across them"
print("5. parallel resistors share the same voltage: OK")

# --- switch + bulb: V1(9V) -- SW1 -- R1(1k) -- back to V1 -------------------


def series_switch_circuit(closed: bool) -> Circuit:
    return Circuit(
        components=[
            ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
            ComponentData(id="sw1", type="switch", x=100, y=0, rotation=0, value=0.0, label="SW1", closed=closed),
            ComponentData(id="r1", type="resistor", x=200, y=0, rotation=0, value=1000.0, label="R1"),
        ],
        wires=[
            WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("sw1", 0)),
            WireData(id="w2", start=TerminalRef("sw1", 1), end=TerminalRef("r1", 0)),
            WireData(id="w3", start=TerminalRef("r1", 1), end=TerminalRef("v1", 1)),
        ],
    )


result = simulate(series_switch_circuit(closed=True))
assert abs(volt(result, "r1", 0) - 9.0) < 1e-6, "closed switch should act as a wire - full 9V reaches R1"
assert abs(volt(result, "r1", 1) - 0.0) < 1e-6
assert abs(volt(result, "sw1", 0) - volt(result, "sw1", 1)) < 1e-6, "no voltage drop across a closed switch"
print("6. closed switch acts as a wire (current flows to R1): OK")

result = simulate(series_switch_circuit(closed=False))
# open switch blocks current, so R1 carries none and both its ends settle
# at the reference potential (0V) - and the switch itself, sitting between
# the 9V source and that 0V dead end, shows the full source voltage across
# its open contacts.
assert abs(volt(result, "r1", 0) - 0.0) < 1e-6, "no current through R1 -> no drop, both ends at 0V"
assert abs(volt(result, "r1", 1) - 0.0) < 1e-6
assert abs(volt(result, "sw1", 0) - 9.0) < 1e-6, "the full source voltage should appear across an open switch"
assert abs(volt(result, "sw1", 1) - 0.0) < 1e-6
print("7. open switch blocks current (full source voltage across the open contacts): OK")

# a bulb is electrically just a resistor - the divider example works
# identically whether R2 is a resistor or a bulb.
circuit = Circuit.load(os.path.join(EXAMPLES, "voltage_divider.json"))
for c in circuit.components:
    if c.label == "R2":
        c.type = "lamp"
result = simulate(circuit)
r1 = by_label(circuit, "R1")
assert abs(volt(result, r1.id, 1) - 4.5) < 1e-6, "a bulb should divide voltage exactly like a resistor of the same value"
print("8. a bulb behaves electrically like a resistor: OK")

# a wire dropped straight across a battery's own terminals short-circuits
# it - the solver should flag that rather than silently returning nonsense.
shorted = Circuit(
    components=[ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1")],
    wires=[WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("v1", 1))],
)
result = simulate(shorted)
assert result.warnings, "a battery shorted by its own wire should produce a warning"
print("9. short-circuited battery is flagged with a warning: OK")

empty = Circuit()
assert simulate(empty) is None, "an empty circuit has nothing to simulate"
print("10. empty circuit returns None: OK")

# --- UI integration: the Simulate button is a live session, not a snapshot -

app = QApplication(sys.argv)
window = MainWindow()
window.resize(900, 500)
window.show()

circuit = Circuit.load(os.path.join(EXAMPLES, "simple_loop.json"))
window._load_circuit(circuit)
app.processEvents()

assert not window._simulation_active
window._simulate_action.setChecked(True)
app.processEvents()
assert window._simulation_active
assert window._simulate_action.text() == "Stop Simulation"
assert len(window._simulation_labels) == 4, "one label per terminal - 2 components x 2 terminals each"
for label in window._simulation_labels:
    assert label.scene() is window.scene
print("11. Simulate button adds one voltage label per terminal, and becomes Stop: OK")

component = next(item for item in window.scene.items() if isinstance(item, ComponentItem))
component.setSelected(True)
window.rotate_selected()  # pushes an undo command
app.processEvents()
assert window._simulation_active, "a live simulation should keep running through an edit, not clear itself"
assert len(window._simulation_labels) == 4, "it should have refreshed (removed + redrawn), not just left stale labels"
print("12. an edit while simulating live refreshes the voltages instead of stopping: OK")

window._simulate_action.setChecked(False)
app.processEvents()
assert not window._simulation_active
assert window._simulation_labels == []
assert window._simulate_action.text() == "Simulate"
print("13. clicking Stop ends the live simulation and removes the labels: OK")

window._simulate_action.setChecked(True)
app.processEvents()
window.undo_stack.setClean()  # skip the "unsaved changes?" prompt - not what this test is checking
window.new_circuit()
app.processEvents()
assert not window._simulation_active
assert window._simulation_labels == []
print("14. New Circuit stops an active simulation cleanly: OK")

empty_window = MainWindow()
empty_window._simulate_action.setChecked(True)
app.processEvents()
assert not empty_window._simulation_active, "nothing to simulate on an empty canvas"
print("15. Simulate on an empty canvas is a no-op (and un-checks itself): OK")

# --- switch click-to-toggle, and a lamp lighting up live -------------------

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

sw_window = MainWindow()
sw_window.resize(700, 400)
sw_window.show()
sw = sw_window.add_component("switch", QPointF(0, 0))
app.processEvents()
assert not sw.closed, "a freshly placed switch should start open, matching its palette icon"

sw_view = sw_window.view
click_pos = sw_view.mapFromScene(sw.scenePos())
QTest.mouseClick(sw_view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, click_pos)
app.processEvents()
assert sw.closed, "a plain click on a switch (no drag) should flip it closed"
assert sw_window.undo_stack.count() == 1, "the toggle should be a single undoable command"

sw_window._on_switch_toggle_requested(sw)
assert not sw.closed, "toggling again should re-open it"
sw_window._on_switch_toggle_requested(sw)
assert sw.closed
sw_window.undo_stack.undo()
assert not sw.closed, "toggling is undoable"
sw_window.undo_stack.redo()
assert sw.closed
print("16. a switch toggles open/closed via a real click, and it's undoable: OK")

lamp_window = MainWindow()
v1 = lamp_window.add_component("battery", QPointF(-100, 0))
lamp = lamp_window.add_component("lamp", QPointF(100, 0))
sw2 = lamp_window.add_component("switch", QPointF(0, 0))
from circuit_builder.ui.wire_item import WireItem

for a, b in ((v1.terminals[0], sw2.terminals[0]), (sw2.terminals[1], lamp.terminals[0]), (lamp.terminals[1], v1.terminals[1])):
    w = WireItem(a, b)
    w.attach()
    lamp_window.scene.addItem(w)

lamp_window._simulate_action.setChecked(True)
app.processEvents()
assert lamp.brightness == 0.0, "the switch starts open - no current, so the bulb should not be lit"

lamp_window._on_switch_toggle_requested(sw2)  # close the switch while simulating live
app.processEvents()
assert lamp.brightness > 0.5, "closing the switch should complete the circuit and light the bulb, live"

lamp_window._on_switch_toggle_requested(sw2)  # open it again
app.processEvents()
assert lamp.brightness == 0.0, "opening the switch again should turn the bulb back off"
print("17. a live simulation lights a bulb the moment its switch closes: OK")

# Deleting every component out from under a running simulation (e.g.
# select-all + Delete) makes the circuit go empty mid-session - this should
# auto-stop the same way starting Simulate on an already-empty canvas does
# (test 15), not leave the toolbar stuck showing "Stop Simulation" while
# _simulation_active has quietly gone False underneath it.
delete_window = MainWindow()
delete_window.resize(700, 400)
delete_window.show()
delete_circuit = Circuit.load(os.path.join(EXAMPLES, "simple_loop.json"))
delete_window._load_circuit(delete_circuit)
app.processEvents()

delete_window._simulate_action.setChecked(True)
app.processEvents()
assert delete_window._simulation_active

for item in list(delete_window.scene.items()):
    item.setSelected(True)
delete_window.delete_selected()
app.processEvents()
assert not delete_window._simulation_active, "should have auto-stopped once the circuit went empty"
assert delete_window._simulation_labels == []
assert not delete_window._simulate_action.isChecked(), "the Simulate toggle should reflect that it stopped"
assert delete_window._simulate_action.text() == "Simulate"
print("18. deleting every component while simulating auto-stops instead of going stale: OK")
delete_window._simulate_action.setChecked(False)  # no-op (already stopped) - defensive, matches other teardowns

# Leaving a simulation running on a window this script is about to drop its
# only reference to risks a stray indexChanged firing during interpreter
# shutdown against an already-torn-down scene - stop it the same way a user
# clicking Stop would, same as the app's own New/Open teardown path does.
lamp_window._simulate_action.setChecked(False)

print("ALL SIMULATION TESTS PASSED")
