import math
import os
import sys
import cmath

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from circuit_builder.core.circuit_model import Circuit, ComponentData, WireData, TerminalRef
from circuit_builder.core.ac_simulation import frequency_response


def close(a, b, tol):
    return abs(a - b) <= tol


# --- 1. RC low-pass filter: H(jw) = 1/(1+jwRC), -3dB corner at 1/(2*pi*RC) -

R, C = 1000.0, 1e-6
lowpass = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r1", type="resistor", x=100, y=0, rotation=0, value=R, label="R1"),
        ComponentData(id="c1", type="capacitor", x=200, y=0, rotation=0, value=C, label="C1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("r1", 0)),
        WireData(id="w2", start=TerminalRef("r1", 1), end=TerminalRef("c1", 0)),
        WireData(id="w3", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
    ],
)
f_corner = 1.0 / (2 * math.pi * R * C)
freqs = [f_corner / 100, f_corner / 10, f_corner, f_corner * 10, f_corner * 100]
result = frequency_response(lowpass, "c1", 0, freqs)
assert result is not None and not result.warnings
for f, h in zip(freqs, result.response):
    w = 2 * math.pi * f
    h_analytic = 1 / (1 + 1j * w * R * C)
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 0.01 + 1e-9), (f, h, h_analytic)
    assert close(cmath.phase(h), cmath.phase(h_analytic), 0.01), (f, h, h_analytic)
mags_db = result.magnitude_db()
assert close(mags_db[2], -3.0, 0.05), "should be within 0.05dB of the textbook -3dB corner"
print("1. RC low-pass filter matches the analytic transfer function, -3dB at the expected corner: OK")

# --- 2. RC high-pass filter (capacitor first, output across R): H = jwRC/(1+jwRC) -
# same R and C values as the low-pass above, just swapped order, output
# read across the OTHER element - the two are complementary by KVL, so
# their transfer functions must sum to exactly 1 at every frequency.

highpass = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="c1", type="capacitor", x=100, y=0, rotation=0, value=C, label="C1"),
        ComponentData(id="r1", type="resistor", x=200, y=0, rotation=0, value=R, label="R1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("c1", 0)),
        WireData(id="w2", start=TerminalRef("c1", 1), end=TerminalRef("r1", 0)),
        WireData(id="w3", start=TerminalRef("r1", 1), end=TerminalRef("v1", 1)),
    ],
)
result2 = frequency_response(highpass, "r1", 0, freqs)
for f, h in zip(freqs, result2.response):
    w = 2 * math.pi * f
    h_analytic = (1j * w * R * C) / (1 + 1j * w * R * C)
    assert close(abs(h), abs(h_analytic), abs(h_analytic) * 0.01 + 1e-9), (f, h, h_analytic)
# low-pass and high-pass magnitudes should sum to 1 in linear terms at every frequency (complementary filters, by KVL)
for h_lp, h_hp in zip(result.response, result2.response):
    assert close(abs(h_lp + h_hp), 1.0, 1e-9), "low-pass and high-pass outputs should reconstruct the input exactly"
print("2. an R-C order swap (same values) gives the complementary high-pass response, summing to unity with the low-pass: OK")

# --- 3. Series RLC band-pass: peaks at unity gain exactly at w0=1/sqrt(LC) -

L, Cr, Rr = 1e-3, 1e-6, 10.0
w0 = 1 / math.sqrt(L * Cr)
f0 = w0 / (2 * math.pi)
rlc = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="l1", type="inductor", x=100, y=0, rotation=0, value=L, label="L1"),
        ComponentData(id="c1", type="capacitor", x=200, y=0, rotation=0, value=Cr, label="C1"),
        ComponentData(id="r1", type="resistor", x=300, y=0, rotation=0, value=Rr, label="R1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("l1", 0)),
        WireData(id="w2", start=TerminalRef("l1", 1), end=TerminalRef("c1", 0)),
        WireData(id="w3", start=TerminalRef("c1", 1), end=TerminalRef("r1", 0)),
        WireData(id="w4", start=TerminalRef("r1", 1), end=TerminalRef("v1", 1)),
    ],
)
result3 = frequency_response(rlc, "r1", 0, [f0 / 10, f0, f0 * 10])
mags = [abs(h) for h in result3.response]
assert close(mags[1], 1.0, 1e-6), f"should peak at exactly unity gain at resonance, got {mags[1]}"
assert mags[0] < 0.1 and mags[2] < 0.1, "should be heavily attenuated a decade off resonance on either side"
assert close(mags[0], mags[2], 0.01), "a series RLC band-pass should be symmetric in log-frequency around resonance"
print("3. series RLC band-pass peaks at exactly unity gain at the resonant frequency, symmetric off-peak: OK")

# --- 4. DC behavior (f->0) matches the DC solver: capacitor open, inductor short

from circuit_builder.core.simulation import simulate

dc_result = simulate(lowpass)
v_c1_dc = dc_result.voltage_at("c1", 0) - dc_result.voltage_at("c1", 1)
v_v1_dc = dc_result.voltage_at("v1", 0) - dc_result.voltage_at("v1", 1)
h_dc_expected = v_c1_dc / v_v1_dc  # should be 1.0 - capacitor fully blocks current, no drop across R
low_f_result = frequency_response(lowpass, "c1", 0, [1e-6])
assert close(abs(low_f_result.response[0]), h_dc_expected, 1e-4), "very low frequency should match the DC gain"
print("4. the low-frequency limit of the AC sweep matches the DC solver's steady-state gain: OK")

# --- 5. A circuit with no battery has nothing to analyze ---------------------

no_battery = Circuit(
    components=[ComponentData(id="r1", type="resistor", x=0, y=0, rotation=0, value=1000.0, label="R1")],
    wires=[],
)
assert frequency_response(no_battery, "r1", 0, [1000.0]) is None
print("5. a circuit with no battery returns None (nothing to sweep): OK")

# --- 6. Past an open switch with a resistor still tying it back to
# reference, the node is well-determined (0V - a dead end with nowhere for
# current to flow still obeys Ohm's law), not undetermined. A component
# with NEITHER terminal wired to anything, on the other hand, forms its own
# isolated island with no path back to reference at all - genuinely
# undetermined (None). Both are worth pinning down, since they look similar
# but aren't. ------------------------------------------------------------

R2 = 500.0
switched = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="sw1", type="switch", x=100, y=0, rotation=0, value=0.0, label="SW1", closed=False),
        ComponentData(id="r1", type="resistor", x=200, y=0, rotation=0, value=R2, label="R1"),
        ComponentData(id="r2", type="resistor", x=400, y=400, rotation=0, value=R2, label="R2"),  # wired to nothing at all
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("sw1", 0)),
        WireData(id="w2", start=TerminalRef("sw1", 1), end=TerminalRef("r1", 0)),
        WireData(id="w3", start=TerminalRef("r1", 1), end=TerminalRef("v1", 1)),
    ],
)
result6 = frequency_response(switched, "r1", 0, [100.0, 1000.0])
assert all(h is not None and close(abs(h), 0.0, 1e-9) for h in result6.response), (
    "a dead end past the open switch still has a path to reference through R1 itself - well-determined at 0V, not None"
)
result6b = frequency_response(switched, "r2", 0, [100.0, 1000.0])
assert all(h is None for h in result6b.response), "a component wired to nothing at all is a genuinely isolated island - undetermined"
print("6. a resistive dead-end past an open switch settles at 0V (determined); a fully unwired component is undetermined: OK")

# --- 7. A second, non-excitation battery is treated as an AC short (0V AC) -
# so it shouldn't change the shape of the response relative to a plain wire.

with_second_battery = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r1", type="resistor", x=100, y=0, rotation=0, value=R, label="R1"),
        ComponentData(id="v2", type="battery", x=150, y=0, rotation=0, value=5.0, label="V2"),
        ComponentData(id="c1", type="capacitor", x=200, y=0, rotation=0, value=C, label="C1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("r1", 0)),
        WireData(id="w2", start=TerminalRef("r1", 1), end=TerminalRef("v2", 0)),
        WireData(id="w3", start=TerminalRef("v2", 1), end=TerminalRef("c1", 0)),
        WireData(id="w4", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
    ],
)
result7 = frequency_response(with_second_battery, "c1", 0, freqs)
for h_plain, h_with_v2 in zip(result.response, result7.response):
    assert close(abs(h_plain), abs(h_with_v2), 1e-9), "a second battery, AC-shorted, shouldn't change the response shape"
print("7. a second (non-excitation) battery is correctly treated as an AC short: OK")

# --- 8. A node that reads EXACTLY 0V (e.g. probing the reference node
# itself) is a well-DETERMINED result, not the same thing as "undetermined,
# no path to the reference" - magnitude_db() must not conflate the two by
# returning None for both (20*log10(0) is -inf, not a real number, but the
# underlying reading is still perfectly valid data, just a deep null/
# reference point - it should report a very-negative-but-real dB floor,
# not None, so plotting code doesn't silently treat it as a gap). ---------

reference_probe = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r1", type="resistor", x=100, y=0, rotation=0, value=R, label="R1"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("r1", 0)),
        WireData(id="w2", start=TerminalRef("r1", 1), end=TerminalRef("v1", 1)),
    ],
)
result8 = frequency_response(reference_probe, "v1", 1, [10.0, 100.0, 1000.0])
assert all(h == complex(0, 0) for h in result8.response), "probing the reference node itself should read exactly 0V"
mags8 = result8.magnitude_db()
assert all(m is not None for m in mags8), "an exact 0V reading is DETERMINED - magnitude_db() must not report None for it"
assert all(m < -200 for m in mags8), "should report a very deep (but finite, real) dB floor for an exact null, not a small number"
phases8 = result8.phase_degrees()
assert all(p == 0.0 for p in phases8), "phase of an exact 0V reading is well-defined too (0 degrees)"

# Contrast with a GENUINELY undetermined probe (isolated island) - that one
# really should stay None, so the two cases don't collapse into each other.
undetermined = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r2", type="resistor", x=400, y=400, rotation=0, value=R, label="R2"),
    ],
    wires=[],
)
result8b = frequency_response(undetermined, "r2", 0, [10.0, 100.0])
assert all(h is None for h in result8b.response)
assert all(m is None for m in result8b.magnitude_db()), "a genuinely isolated/undetermined probe should still report None"
print("8. an exact 0V (fully determined) reading reports a real dB floor, not None - distinct from truly undetermined: OK")

print("ALL AC/FREQUENCY-RESPONSE TESTS PASSED")
