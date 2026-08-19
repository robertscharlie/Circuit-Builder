import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circuit_builder.core.circuit_model import Circuit, ComponentData, WireData, TerminalRef
from circuit_builder.core.ac_simulation import frequency_response


def close(a, b, tol):
    return abs(a - b) <= tol


def series2(a, b, va, vb):
    # V1 -> X1 -> X2 -> V1(ground). X2's far terminal (1) IS the ground
    # reference, so the mid node - X1 terminal 1, equivalently X2 terminal 0
    # - reads the voltage ACROSS X2 relative to ground directly.
    return Circuit(
        components=[
            ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
            ComponentData(id="x1", type=a, x=100, y=0, rotation=0, value=va, label="X1"),
            ComponentData(id="x2", type=b, x=200, y=0, rotation=0, value=vb, label="X2"),
        ],
        wires=[
            WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("x1", 0)),
            WireData(id="w2", start=TerminalRef("x1", 1), end=TerminalRef("x2", 0)),
            WireData(id="w3", start=TerminalRef("x2", 1), end=TerminalRef("v1", 1)),
        ],
    )


R, L = 1000.0, 0.1
freqs = [10, 100, 1000, 10000, 100000]

# --- 1. RL low-pass (L then R, probe across R): H = R/(R+jwL) --------------

circ = series2("inductor", "resistor", L, R)
result = frequency_response(circ, "x1", 1, freqs)
for f, h in zip(freqs, result.response):
    w = 2 * math.pi * f
    h_analytic = R / (R + 1j * w * L)
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 1e-6 + 1e-9), (f, h, h_analytic)
print("1. RL low-pass (L then R, probe across R) matches R/(R+jwL): OK")

# --- 2. RL high-pass (R then L, probe across L): H = jwL/(R+jwL) - the
# complement of #1 by KVL, so together they must sum to unity. -------------

circ2 = series2("resistor", "inductor", R, L)
result2 = frequency_response(circ2, "x1", 1, freqs)
for f, h in zip(freqs, result2.response):
    w = 2 * math.pi * f
    h_analytic = (1j * w * L) / (R + 1j * w * L)
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 1e-6 + 1e-9), (f, h, h_analytic)
for h_lp, h_hp in zip(result.response, result2.response):
    assert close(abs(h_lp + h_hp), 1.0, 1e-9), "RL low-pass and high-pass should reconstruct the input exactly"
print("2. RL high-pass (R then L, probe across L) matches jwL/(R+jwL), complementary to the low-pass: OK")

# --- 3. Parallel LC tank loaded by a series source resistor: a band-pass
# that peaks at EXACTLY unity gain right at resonance (a lossless tank has
# infinite impedance there, so all the source voltage appears across it),
# falling off on both sides as either L (low f) or C (high f) shorts it. ----

Rt, Lt, Ct = 600.0, 1e-3, 1e-6
tank = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="rs", type="resistor", x=100, y=0, rotation=0, value=Rt, label="Rs"),
        ComponentData(id="l1", type="inductor", x=250, y=-40, rotation=0, value=Lt, label="L1"),
        ComponentData(id="c1", type="capacitor", x=250, y=40, rotation=0, value=Ct, label="C1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("rs", 0)),
        WireData(id="w2", start=TerminalRef("rs", 1), end=TerminalRef("l1", 0)),
        WireData(id="w3", start=TerminalRef("rs", 1), end=TerminalRef("c1", 0)),
        WireData(id="w4", start=TerminalRef("l1", 1), end=TerminalRef("v1", 1)),
        WireData(id="w5", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
    ],
)
f0t = 1.0 / (2 * math.pi * math.sqrt(Lt * Ct))
result3 = frequency_response(tank, "l1", 0, [f0t / 50, f0t, f0t * 50])
mags3 = [abs(h) for h in result3.response]
assert close(mags3[1], 1.0, 1e-6), f"parallel LC tank should peak at unity gain at resonance, got {mags3[1]}"
assert mags3[0] < 0.05 and mags3[2] < 0.05, "should be heavily attenuated a decade+ off resonance on either side"
print("3. a parallel LC tank (loaded by a series source resistor) peaks at exactly unity gain at resonance: OK")

# --- 4. A cascaded, LOADED two-stage RC low-pass - the second stage isn't
# buffered from the first, so this must NOT match the naive (1/(1+jwRC))^2
# an unloaded/buffered cascade would give; it must match the actual 2nd-
# order network equations for the loaded circuit. ---------------------------

Rc, Cc = 1000.0, 1e-6
cascade = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r1", type="resistor", x=100, y=0, rotation=0, value=Rc, label="R1"),
        ComponentData(id="c1", type="capacitor", x=150, y=0, rotation=0, value=Cc, label="C1"),
        ComponentData(id="r2", type="resistor", x=200, y=0, rotation=0, value=Rc, label="R2"),
        ComponentData(id="c2", type="capacitor", x=250, y=0, rotation=0, value=Cc, label="C2"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("r1", 0)),
        WireData(id="w2", start=TerminalRef("r1", 1), end=TerminalRef("c1", 0)),
        WireData(id="w3", start=TerminalRef("r1", 1), end=TerminalRef("r2", 0)),
        WireData(id="w4", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
        WireData(id="w5", start=TerminalRef("r2", 1), end=TerminalRef("c2", 0)),
        WireData(id="w6", start=TerminalRef("c2", 1), end=TerminalRef("v1", 1)),
    ],
)
result4 = frequency_response(cascade, "c2", 0, freqs)
for f, h in zip(freqs, result4.response):
    w = 2 * math.pi * f
    s = 1j * w
    RC = Rc * Cc
    denom = 1 + s * RC + 1 - 1.0 / (1 + s * RC)  # node equation for the loaded 1st stage
    va = 1.0 / denom
    h_analytic = va / (1 + s * RC)  # 2nd stage divides Va down further
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 1e-6 + 1e-9), (f, h, h_analytic)
naive_unbuffered = [abs(1 / (1 + 1j * 2 * math.pi * f * Rc * Cc)) ** 2 for f in freqs]
actual = [abs(h) for h in result4.response]
assert any(abs(a - n) > 0.01 for a, n in zip(actual, naive_unbuffered)), (
    "the loaded cascade should differ measurably from a naive squared single-stage response - "
    "if it doesn't, the 2nd stage isn't actually loading the 1st"
)
print("4. a loaded (unbuffered) 2-stage RC cascade matches the true loaded network equations, not a naive square: OK")

# --- 5. A balanced RC bridge: two independent R-C dividers off the same
# source with equal time constants (R1*C1 == R2*C2) must read IDENTICALLY
# at every frequency, even though R and C differ between the two branches. -

bridge = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="ra", type="resistor", x=100, y=-50, rotation=0, value=1000.0, label="Ra"),
        ComponentData(id="ca", type="capacitor", x=200, y=-50, rotation=0, value=1e-6, label="Ca"),
        ComponentData(id="rb", type="resistor", x=100, y=50, rotation=0, value=2000.0, label="Rb"),
        ComponentData(id="cb", type="capacitor", x=200, y=50, rotation=0, value=0.5e-6, label="Cb"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("ra", 0)),
        WireData(id="w2", start=TerminalRef("ra", 1), end=TerminalRef("ca", 0)),
        WireData(id="w3", start=TerminalRef("ca", 1), end=TerminalRef("v1", 1)),
        WireData(id="w4", start=TerminalRef("v1", 0), end=TerminalRef("rb", 0)),
        WireData(id="w5", start=TerminalRef("rb", 1), end=TerminalRef("cb", 0)),
        WireData(id="w6", start=TerminalRef("cb", 1), end=TerminalRef("v1", 1)),
    ],
)
result_a = frequency_response(bridge, "ra", 1, freqs)
result_b = frequency_response(bridge, "rb", 1, freqs)
for f, ha, hb in zip(freqs, result_a.response, result_b.response):
    assert close(abs(ha - hb), 0.0, 1e-9), f"balanced bridge midpoints should match exactly at f={f}: {ha} vs {hb}"
print("5. two independent RC dividers off the same source with equal time constants (different R, C) read identically: OK")

# --- 6. Pure capacitive divider (no resistors at all): frequency-
# INDEPENDENT, H = C1/(C1+C2) - impedance ratios invert the capacitance
# ratio, and the jw factors cancel top and bottom. --------------------------

c1v, c2v = 2e-6, 6e-6
circ6 = series2("capacitor", "capacitor", c1v, c2v)
result6 = frequency_response(circ6, "x1", 1, [1, 1000, 1_000_000])
want6 = c1v / (c1v + c2v)
for h in result6.response:
    assert close(abs(h), want6, 1e-9) and close(h.imag, 0.0, 1e-9), (h, want6)
print("6. a pure capacitive divider (no resistors) is frequency-independent, C1/(C1+C2): OK")

# --- 7. excitation_component_id lets the caller choose WHICH battery is
# the swept AC input, instead of always defaulting to the first one. Two
# batteries, each driving its own independent R-C branch, sharing only a
# common ground rail: exciting via V1 should light up the V1 branch (a
# textbook RC low-pass) while leaving the V2 branch dead at exactly 0V
# (nothing else drives it once V2 itself is AC-shorted), and vice versa. --

Rx, Cx = 1000.0, 1e-6
Ry, Cy = 2000.0, 2e-6
two_source = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=-50, rotation=0, value=9.0, label="V1"),
        ComponentData(id="rx", type="resistor", x=100, y=-50, rotation=0, value=Rx, label="Rx"),
        ComponentData(id="cx", type="capacitor", x=200, y=-50, rotation=0, value=Cx, label="Cx"),
        ComponentData(id="v2", type="battery", x=0, y=50, rotation=0, value=9.0, label="V2"),
        ComponentData(id="ry", type="resistor", x=100, y=50, rotation=0, value=Ry, label="Ry"),
        ComponentData(id="cy", type="capacitor", x=200, y=50, rotation=0, value=Cy, label="Cy"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("rx", 0)),
        WireData(id="w2", start=TerminalRef("rx", 1), end=TerminalRef("cx", 0)),
        WireData(id="w3", start=TerminalRef("cx", 1), end=TerminalRef("v1", 1)),
        WireData(id="w4", start=TerminalRef("v2", 0), end=TerminalRef("ry", 0)),
        WireData(id="w5", start=TerminalRef("ry", 1), end=TerminalRef("cy", 0)),
        WireData(id="w6", start=TerminalRef("cy", 1), end=TerminalRef("v2", 1)),
        WireData(id="w7", start=TerminalRef("v1", 1), end=TerminalRef("v2", 1)),  # shared ground rail
    ],
)

result_v1_on_x = frequency_response(two_source, "cx", 0, freqs, excitation_component_id="v1")
result_v1_on_y = frequency_response(two_source, "cy", 0, freqs, excitation_component_id="v1")
for f, h in zip(freqs, result_v1_on_x.response):
    w = 2 * math.pi * f
    h_analytic = 1.0 / (1 + 1j * w * Rx * Cx)
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 1e-6 + 1e-9), (f, h, h_analytic)
assert all(close(abs(h), 0.0, 1e-9) for h in result_v1_on_y.response), (
    "with V1 as excitation, V2's own branch should be entirely dead (V2 is AC-shorted, and it's not "
    "otherwise connected to the V1 branch except through the shared ground rail)"
)

result_v2_on_y = frequency_response(two_source, "cy", 0, freqs, excitation_component_id="v2")
result_v2_on_x = frequency_response(two_source, "cx", 0, freqs, excitation_component_id="v2")
for f, h in zip(freqs, result_v2_on_y.response):
    w = 2 * math.pi * f
    h_analytic = 1.0 / (1 + 1j * w * Ry * Cy)
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 1e-6 + 1e-9), (f, h, h_analytic)
assert all(close(abs(h), 0.0, 1e-9) for h in result_v2_on_x.response), "and symmetrically for V2 as excitation"
print("7. excitation_component_id actually selects which battery is the swept input, not always the first: OK")

print("ALL EXTRA AC CIRCUIT VERIFICATION TESTS PASSED")
