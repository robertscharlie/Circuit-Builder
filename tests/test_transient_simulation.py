import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuit_builder.core.circuit_model import Circuit, ComponentData, TerminalRef, WireData
from circuit_builder.core.simulation import TransientState, simulate
from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.wire_item import WireItem

# --- core solver: backward-Euler capacitor companion model ------------------

R, C, V = 1000.0, 1e-3, 9.0  # tau = R*C = 1s


def series_rc_circuit(switch_closed: bool = True) -> Circuit:
    return Circuit(
        components=[
            ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=V, label="V1"),
            ComponentData(id="sw1", type="switch", x=100, y=0, rotation=0, value=0.0, label="SW1", closed=switch_closed),
            ComponentData(id="r1", type="resistor", x=200, y=0, rotation=0, value=R, label="R1"),
            ComponentData(id="c1", type="capacitor", x=300, y=0, rotation=0, value=C, label="C1"),
        ],
        wires=[
            WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("sw1", 0)),
            WireData(id="w2", start=TerminalRef("sw1", 1), end=TerminalRef("r1", 0)),
            WireData(id="w3", start=TerminalRef("r1", 1), end=TerminalRef("c1", 0)),
            WireData(id="w4", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
        ],
    )


circuit = series_rc_circuit()
state = TransientState()
dt = 0.05
tau = R * C
t = 0.0
for _ in range(20):
    result = simulate(circuit, dt=dt, state=state)
    t += dt

v_sim = state.capacitor_voltage["c1"]
v_analytic = V * (1 - math.exp(-t / tau))
assert abs(v_sim - v_analytic) < 0.15, f"charging curve should track the analytic RC formula: sim={v_sim}, analytic={v_analytic}"
assert v_sim > 3.0, "after 1s (~1 tau) the capacitor should be well on its way to charging"
print("1. repeated ticks trace out the analytic RC charging curve: OK")

# capacitor voltage rises monotonically while charging (backward Euler is
# unconditionally stable - it should never overshoot or oscillate)
circuit2 = series_rc_circuit()
state2 = TransientState()
prev = 0.0
for _ in range(30):
    simulate(circuit2, dt=dt, state=state2)
    v = state2.capacitor_voltage["c1"]
    assert v >= prev - 1e-9, "capacitor voltage should rise monotonically while charging, never overshoot"
    prev = v
assert prev < V, "should still be approaching, not exceeding, the supply voltage"
print("2. charging is monotonic and never overshoots the supply voltage: OK")

# --- discharge: charge through one resistor, then open the switch and
# watch it drain through a SECOND resistor that's permanently in parallel
# with it (unlike the series-only circuit above, this one still has
# somewhere for the charge to go once the switch disconnects the battery -
# exactly the "capacitor keeps a bulb glowing after the switch opens" demo).


def charge_and_bleed_circuit(switch_closed: bool) -> Circuit:
    return Circuit(
        components=[
            ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=V, label="V1"),
            ComponentData(id="sw1", type="switch", x=100, y=0, rotation=0, value=0.0, label="SW1", closed=switch_closed),
            # small relative to r_bleed, so the R_bleed/(r_charge+R_bleed)
            # voltage-divider asymptote it charges toward is still close to
            # the full supply voltage.
            ComponentData(id="r_charge", type="resistor", x=200, y=0, rotation=0, value=R / 10, label="Rc"),
            ComponentData(id="r_bleed", type="resistor", x=300, y=100, rotation=0, value=R, label="Rb"),
            ComponentData(id="c1", type="capacitor", x=300, y=-100, rotation=0, value=C, label="C1"),
        ],
        wires=[
            WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("sw1", 0)),
            WireData(id="w2", start=TerminalRef("sw1", 1), end=TerminalRef("r_charge", 0)),
            WireData(id="w3", start=TerminalRef("r_charge", 1), end=TerminalRef("c1", 0)),
            WireData(id="w4", start=TerminalRef("r_charge", 1), end=TerminalRef("r_bleed", 0)),
            WireData(id="w5", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
            WireData(id="w6", start=TerminalRef("r_bleed", 1), end=TerminalRef("v1", 1)),
        ],
    )


circuit3 = charge_and_bleed_circuit(switch_closed=True)
state3 = TransientState()
for _ in range(60):  # let it charge up first
    simulate(circuit3, dt=dt, state=state3)
charged_voltage = state3.capacitor_voltage["c1"]
assert charged_voltage > 6.0, "should be well charged by now"

next(c for c in circuit3.components if c.label == "SW1").closed = False  # cut the battery
readings = []
for _ in range(20):
    result = simulate(circuit3, dt=dt, state=state3)
    readings.append(state3.capacitor_voltage["c1"])

assert readings[0] < charged_voltage, "voltage should start dropping the very next tick after opening the switch"
for i in range(1, len(readings)):
    assert readings[i] <= readings[i - 1] + 1e-9, "capacitor voltage should decrease monotonically while discharging"
assert readings[-1] < charged_voltage * 0.5, "should have visibly decayed after this many ticks"
print("3. opening the switch makes the capacitor discharge monotonically through the parallel resistor: OK")

# --- a tiny dt ("instant" refresh after some other edit, e.g. a switch
# flip) barely nudges an already-charged capacitor's voltage - close to its
# last known value, not reset to 0 and not jumping elsewhere. Deliberately
# NOT modeled as a hard voltage-source pin (see the module docstring) -
# using a tiny dt instead sidesteps a real degenerate case: an ideal battery
# wired with no resistance straight to an uncharged capacitor is a genuine
# mathematical singularity (an instant short-circuit-like contradiction),
# which a plain finite conductance never hits.
circuit4 = series_rc_circuit()
state4 = TransientState()
state4.capacitor_voltage["c1"] = 4.5  # pretend it's already partway charged
instant = simulate(circuit4, dt=1e-6, state=state4)
v0 = instant.voltage_at("c1", 0)
v1 = instant.voltage_at("c1", 1)
assert abs((v0 - v1) - 4.5) < 1e-3, "an effectively-instant refresh should show the capacitor very close to its last known voltage"
assert abs(state4.capacitor_voltage["c1"] - 4.5) < 1e-3, "and barely nudge the stored charge, not reset or jump it"
print("4. an effectively-instant refresh leaves an already-charged capacitor close to where it was: OK")

# and directly on the degenerate case itself: a battery wired with zero
# resistance straight to an initially uncharged capacitor must still solve
# cleanly (no crash, no NaN) - unlike a hard voltage-source pin would.
degenerate = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="c1", type="capacitor", x=100, y=0, rotation=0, value=1e-3, label="C1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("c1", 0)),
        WireData(id="w2", start=TerminalRef("v1", 1), end=TerminalRef("c1", 1)),
    ],
)
degenerate_state = TransientState()
degenerate_result = simulate(degenerate, dt=1e-6, state=degenerate_state)
assert not degenerate_result.warnings, "a direct battery-to-capacitor connection should solve cleanly via the companion model, not be flagged as a contradiction"
print("5. a capacitor wired with no series resistance straight across a battery still solves cleanly: OK")

# --- UI integration: a full switch+capacitor+bulb demo circuit, driven tick
# by tick like the live QTimer would, dims the bulb as the capacitor
# discharges through it - the exact scenario asked for. ---------------------

app = QApplication(sys.argv)
window = MainWindow()
window.resize(900, 500)
window.show()

v1 = window.add_component("battery", QPointF(-200, 0))
sw1 = window.add_component("switch", QPointF(0, 0))
cap1 = window.add_component("capacitor", QPointF(200, 100))
bulb1 = window.add_component("lamp", QPointF(200, -100))
for a, b in (
    (v1.terminals[0], sw1.terminals[0]),
    (sw1.terminals[1], cap1.terminals[0]),
    (sw1.terminals[1], bulb1.terminals[0]),
    (cap1.terminals[1], v1.terminals[1]),
    (bulb1.terminals[1], v1.terminals[1]),
):
    w = WireItem(a, b)
    w.attach()
    window.scene.addItem(w)
app.processEvents()

window._simulate_action.setChecked(True)  # switch starts open - nothing charged, bulb off
app.processEvents()
assert bulb1.brightness == 0.0

window._on_switch_toggle_requested(sw1)  # close it - battery charges cap + lights bulb together
app.processEvents()
assert bulb1.brightness > 0.5, "closing the switch should immediately light the bulb"

for _ in range(80):  # let the capacitor fully charge (tick the same way the QTimer does)
    window._on_sim_tick()
charged_brightness = bulb1.brightness
assert charged_brightness > 0.5

window._on_switch_toggle_requested(sw1)  # open it - battery disconnected, cap discharges through bulb
app.processEvents()

brightness_readings = [bulb1.brightness]
for _ in range(15):
    window._on_sim_tick()
    brightness_readings.append(bulb1.brightness)

assert brightness_readings[-1] < brightness_readings[0], "the bulb should visibly dim as the capacitor discharges through it"
for i in range(1, len(brightness_readings)):
    assert brightness_readings[i] <= brightness_readings[i - 1] + 1e-9, "brightness should fade monotonically, not flicker"
print("6. switch+capacitor+bulb demo: closing charges and lights it, opening dims it out over time: OK")

window._simulate_action.setChecked(False)  # stop before the script exits, see test_simulation.py's note

# --- core solver: backward-Euler INDUCTOR companion model - the mirror
# image of the capacitor above (current can't jump instantly, instead of
# voltage), verified the same three ways. ----------------------------------

L, R_L, V2 = 20.0, 50.0, 9.0  # tau = L/R = 0.4s - matches the new component default
dt2 = 0.05


def series_rl_circuit(switch_closed: bool = True) -> Circuit:
    return Circuit(
        components=[
            ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=V2, label="V1"),
            ComponentData(id="sw1", type="switch", x=100, y=0, rotation=0, value=0.0, label="SW1", closed=switch_closed),
            ComponentData(id="r1", type="resistor", x=200, y=0, rotation=0, value=R_L, label="R1"),
            ComponentData(id="l1", type="inductor", x=300, y=0, rotation=0, value=L, label="L1"),
        ],
        wires=[
            WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("sw1", 0)),
            WireData(id="w2", start=TerminalRef("sw1", 1), end=TerminalRef("r1", 0)),
            WireData(id="w3", start=TerminalRef("r1", 1), end=TerminalRef("l1", 0)),
            WireData(id="w4", start=TerminalRef("l1", 1), end=TerminalRef("v1", 1)),
        ],
    )


circuit5 = series_rl_circuit()
state5 = TransientState()
tau2 = L / R_L
t2 = 0.0
for _ in range(20):
    simulate(circuit5, dt=dt2, state=state5)
    t2 += dt2

i_sim = state5.inductor_current["l1"]
i_ss = V2 / R_L
i_analytic = i_ss * (1 - math.exp(-t2 / tau2))
assert abs(i_sim - i_analytic) < 0.02, f"L/R charging curve should track the analytic formula: sim={i_sim}, analytic={i_analytic}"
assert i_sim > i_ss * 0.5, "after 1s (2.5 tau) the inductor's current should be well built up"
print("7. repeated ticks trace out the analytic L/R current ramp-up: OK")

# current rises monotonically while building up (unconditionally stable,
# same as the capacitor case - never overshoots the steady-state current)
circuit6 = series_rl_circuit()
state6 = TransientState()
prev_i = 0.0
for _ in range(30):
    simulate(circuit6, dt=dt2, state=state6)
    i = state6.inductor_current["l1"]
    assert i >= prev_i - 1e-9, "inductor current should rise monotonically, never overshoot"
    prev_i = i
assert prev_i < i_ss, "should still be approaching, not exceeding, the steady-state current"
print("8. current build-up is monotonic and never overshoots the steady-state current: OK")

# --- freewheel discharge: charge the inductor through a series resistor,
# then open the switch - current keeps flowing (an inductor resists sudden
# current changes) through a second resistor permanently in parallel with
# it, decaying with its own L/R time constant.


def charge_and_freewheel_circuit(switch_closed: bool) -> Circuit:
    return Circuit(
        components=[
            ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=V2, label="V1"),
            ComponentData(id="sw1", type="switch", x=100, y=0, rotation=0, value=0.0, label="SW1", closed=switch_closed),
            ComponentData(id="r_series", type="resistor", x=200, y=0, rotation=0, value=R_L, label="Rs"),
            ComponentData(id="r_freewheel", type="resistor", x=300, y=100, rotation=0, value=R_L, label="Rf"),
            ComponentData(id="l1", type="inductor", x=300, y=-100, rotation=0, value=L, label="L1"),
        ],
        wires=[
            WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("sw1", 0)),
            WireData(id="w2", start=TerminalRef("sw1", 1), end=TerminalRef("r_series", 0)),
            WireData(id="w3", start=TerminalRef("r_series", 1), end=TerminalRef("l1", 0)),
            WireData(id="w4", start=TerminalRef("r_series", 1), end=TerminalRef("r_freewheel", 0)),
            WireData(id="w5", start=TerminalRef("l1", 1), end=TerminalRef("v1", 1)),
            WireData(id="w6", start=TerminalRef("r_freewheel", 1), end=TerminalRef("v1", 1)),
        ],
    )


circuit7 = charge_and_freewheel_circuit(switch_closed=True)
state7 = TransientState()
for _ in range(60):  # let the current build up first
    simulate(circuit7, dt=dt2, state=state7)
charged_current = state7.inductor_current["l1"]
assert charged_current > i_ss * 0.5, "should have built up a substantial current by now"

next(c for c in circuit7.components if c.label == "SW1").closed = False  # cut the battery
i_readings = []
for _ in range(20):
    simulate(circuit7, dt=dt2, state=state7)
    i_readings.append(state7.inductor_current["l1"])

assert i_readings[0] < charged_current, "current should start dropping the very next tick after opening the switch"
for i in range(1, len(i_readings)):
    assert i_readings[i] <= i_readings[i - 1] + 1e-9, "inductor current should decrease monotonically while freewheeling"
assert i_readings[-1] < charged_current * 0.5, "should have visibly decayed after this many ticks"
print("9. opening the switch makes the inductor's current freewheel and decay through the parallel resistor: OK")

# a battery wired directly across an inductor (no series resistance) with
# zero initial current must still solve cleanly - at t->0 an inductor looks
# like an open circuit (current can't jump instantly), which is itself the
# well-behaved opposite of the capacitor's zero-series-resistance case, not
# a singularity, but worth a regression check all the same.
degenerate2 = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="l1", type="inductor", x=100, y=0, rotation=0, value=20.0, label="L1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("l1", 0)),
        WireData(id="w2", start=TerminalRef("v1", 1), end=TerminalRef("l1", 1)),
    ],
)
degenerate2_state = TransientState()
degenerate2_result = simulate(degenerate2, dt=1e-6, state=degenerate2_state)
assert not degenerate2_result.warnings, "a direct battery-to-inductor connection should solve cleanly"
assert abs(degenerate2_state.inductor_current["l1"]) < 1e-3, "an uncharged inductor should still look almost open an instant after power is applied"
print("10. an inductor wired with no series resistance straight across a battery starts near-open, not singular: OK")

# --- UI integration: a switch+resistor+inductor+bulb demo, driven tick by
# tick like the live QTimer would - the mirror image of the capacitor demo:
# the bulb stays dark right after closing the switch (the inductor blocks
# the sudden current) and brightens smoothly as current builds up. ---------

window2 = MainWindow()
window2.resize(900, 500)
window2.show()

v1b = window2.add_component("battery", QPointF(-200, 0))
sw1b = window2.add_component("switch", QPointF(0, 0))
ind1 = window2.add_component("inductor", QPointF(150, 0))
bulb2 = window2.add_component("lamp", QPointF(300, 0))
for a, b in (
    (v1b.terminals[0], sw1b.terminals[0]),
    (sw1b.terminals[1], ind1.terminals[0]),
    (ind1.terminals[1], bulb2.terminals[0]),
    (bulb2.terminals[1], v1b.terminals[1]),
):
    w = WireItem(a, b)
    w.attach()
    window2.scene.addItem(w)
app.processEvents()

window2._simulate_action.setChecked(True)  # switch starts open - bulb off
app.processEvents()
assert bulb2.brightness == 0.0

window2._on_switch_toggle_requested(sw1b)  # close it - inductor blocks the sudden current, bulb stays dark
app.processEvents()
assert bulb2.brightness < 0.2, "the bulb should stay (near) dark right as the switch closes - current can't jump instantly"

brightness_ramp = [bulb2.brightness]
for _ in range(40):
    window2._on_sim_tick()
    brightness_ramp.append(bulb2.brightness)

assert brightness_ramp[-1] > brightness_ramp[0], "the bulb should visibly brighten as the inductor's current builds up"
for i in range(1, len(brightness_ramp)):
    assert brightness_ramp[i] >= brightness_ramp[i - 1] - 1e-9, "brightness should ramp up monotonically, not flicker"
print("11. switch+inductor+bulb demo: closing it leaves the bulb dark, then it brightens as current builds up: OK")

window2._simulate_action.setChecked(False)  # stop before the script exits
print("ALL TRANSIENT SIMULATION TESTS PASSED")
