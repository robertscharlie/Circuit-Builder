"""Frequency-domain (AC / phasor) analysis: small-signal frequency response
of a circuit, swept across a range of frequencies, for Bode magnitude/phase
plots.

Qt-free, like the rest of `core/` - reuses the DC/transient solver's
union-find node-grouping and terminal bookkeeping (`_UnionFind`,
`_terminal_count`) from ``simulation.py``, generalized from real-valued
Modified Nodal Analysis to complex-valued MNA:

- resistor / bulb: admittance ``1/R`` (real, frequency-independent).
- capacitor: admittance ``jwC`` - grows with frequency (a capacitor looks
  like an open circuit at DC, w=0, and like a short at very high frequency).
- inductor: admittance ``1/(jwL)`` - the mirror image, a short at DC and an
  open circuit at very high frequency. A (practically) zero-valued inductor
  is instead collapsed into a plain wire via union-find, same as the DC
  solver, since ``1/(jw*0)`` is undefined rather than merely large.
- switch: closed is a union-find short, same as DC; open drops it entirely.
- batteries: exactly ONE battery is the swept AC excitation (input) - the
  one named by `excitation_component_id`, or the first battery in the
  circuit if that's omitted, matching the DC solver's reference-node
  convention. It's held at a unit phasor (1∠0°) at every frequency - a Bode
  plot is a *ratio* of output to input, so the source's actual rated DC
  voltage is irrelevant to the shape of the response, only its position in
  the circuit matters. Every OTHER battery is collapsed into a wire via
  union-find (0V AC, i.e. a short) - the standard small-signal convention
  of zeroing every source except the one being characterized. The 0V
  reference for the whole sweep is that excitation battery's own negative
  terminal, so it moves with whichever battery is chosen as the input.

Because the excitation is pinned to exactly 1∠0°, the transfer function
H(jw) = V_probe(jw) / V_source(jw) is just V_probe(jw) directly - no
separate division needed.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field

from circuit_builder.core.circuit_model import Circuit
from circuit_builder.core.simulation import _RESISTIVE_TYPES, _UnionFind, _terminal_count

_EPSILON = 1e-12
_PIVOT_EPSILON = 1e-9
# 20*log10(0) is -inf, which isn't a real number matplotlib can plot or
# autoscale an axis around - but an exact 0V reading is a perfectly
# determined result (e.g. probing straight onto the reference node, or a
# genuine notch/null in the response), not the same thing as "undetermined,
# no path to the reference" (a None response). Clipping to a very deep but
# finite floor keeps that distinction: None still means "gap, no data";
# this floor means "real data, it just happens to be silent here."
_MAGNITUDE_FLOOR_DB = -300.0

TerminalKey = tuple[str, int]


@dataclass
class FrequencyResponseResult:
    frequencies_hz: list[float]
    # Complex phasor H(jw) = V_probe/V_source at each swept frequency, or
    # None at any frequency where the probe point has no determined AC path
    # back to the reference (e.g. isolated behind an open switch).
    response: list[complex | None]
    warnings: list[str] = field(default_factory=list)

    def magnitude_db(self) -> list[float | None]:
        result: list[float | None] = []
        for h in self.response:
            if h is None:
                result.append(None)
            elif abs(h) <= 0:
                result.append(_MAGNITUDE_FLOOR_DB)
            else:
                result.append(20.0 * math.log10(abs(h)))
        return result

    def phase_degrees(self) -> list[float | None]:
        return [None if h is None else math.degrees(cmath.phase(h)) for h in self.response]


def frequency_response(
    circuit: Circuit,
    probe_component_id: str,
    probe_terminal_index: int,
    frequencies_hz: list[float],
    excitation_component_id: str | None = None,
) -> FrequencyResponseResult | None:
    """Sweeps `frequencies_hz`, solving the complex MNA system fresh at each
    one, and returns the phasor voltage at the probe terminal (relative to
    the excitation battery's negative terminal - the 0V reference for this
    sweep). Returns None if there's nothing to simulate (an empty circuit)
    or no battery to excite it.

    `excitation_component_id` picks which battery is the swept AC input -
    defaults to the first battery in the circuit (matching the DC solver's
    reference-node convention) if omitted or if it doesn't match any
    battery actually present."""
    if not circuit.components:
        return None
    batteries = [c for c in circuit.components if c.type == "battery"]
    if not batteries:
        return None
    excitation = next((b for b in batteries if b.id == excitation_component_id), batteries[0])

    warnings: list[str] = []
    response: list[complex | None] = []
    for f in frequencies_hz:
        omega = 2 * math.pi * f
        voltage, warning = _solve_at_frequency(circuit, batteries, excitation, omega, probe_component_id, probe_terminal_index)
        response.append(voltage)
        if warning and warning not in warnings:
            warnings.append(warning)

    return FrequencyResponseResult(frequencies_hz=list(frequencies_hz), response=response, warnings=warnings)


def _solve_at_frequency(
    circuit: Circuit,
    batteries: list,
    excitation,
    omega: float,
    probe_component_id: str,
    probe_terminal_index: int,
) -> tuple[complex | None, str | None]:
    uf = _UnionFind()
    for c in circuit.components:
        for i in range(_terminal_count(c.type)):
            uf.find((c.id, i))

    for w in circuit.wires:
        uf.union((w.start.component_id, w.start.terminal_index), (w.end.component_id, w.end.terminal_index))

    other_batteries = [b for b in batteries if b is not excitation]

    for c in circuit.components:
        if (
            (c.type == "inductor" and c.value <= _EPSILON)
            or (c.type in _RESISTIVE_TYPES and c.value <= _EPSILON)
            or (c.type == "switch" and c.closed)
            or c in other_batteries  # every non-excitation source is an AC short
        ):
            uf.union((c.id, 0), (c.id, 1))

    node_of: dict[TerminalKey, int] = {}
    node_ids: dict[TerminalKey, int] = {}
    for c in circuit.components:
        for i in range(_terminal_count(c.type)):
            key = (c.id, i)
            root = uf.find(key)
            if root not in node_ids:
                node_ids[root] = len(node_ids)
            node_of[key] = node_ids[root]

    n_nodes = len(node_ids)
    reference_node = node_of[(excitation.id, 1)]

    p_source, m_source = node_of[(excitation.id, 0)], node_of[(excitation.id, 1)]
    if p_source == m_source:
        return None, f"{excitation.label}: short-circuited (both terminals share a node) - excluded from the sweep"
    source_usable = True

    adjacency: dict[int, set[int]] = {i: set() for i in range(n_nodes)}

    def _connect(a: int, b: int) -> None:
        adjacency[a].add(b)
        adjacency[b].add(a)

    admittances: list[tuple[int, int, complex]] = []  # (node_p, node_m, Y)
    for c in circuit.components:
        if c.type in _RESISTIVE_TYPES and c.value > _EPSILON:
            admittances.append((node_of[(c.id, 0)], node_of[(c.id, 1)], complex(1.0 / c.value, 0.0)))
        elif c.type == "capacitor" and c.value > _EPSILON:
            admittances.append((node_of[(c.id, 0)], node_of[(c.id, 1)], complex(0.0, omega * c.value)))
        elif c.type == "inductor" and c.value > _EPSILON:
            admittances.append((node_of[(c.id, 0)], node_of[(c.id, 1)], 1.0 / complex(0.0, omega * c.value)))

    for p, m, _y in admittances:
        _connect(p, m)
    if source_usable:
        _connect(p_source, m_source)

    reachable = {reference_node}
    frontier = [reference_node]
    while frontier:
        cur = frontier.pop()
        for nxt in adjacency[cur]:
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)

    probe_node = node_of.get((probe_component_id, probe_terminal_index))
    if probe_node is None:
        return None, None
    if probe_node == reference_node:
        return complex(0.0, 0.0), None
    if probe_node not in reachable:
        return None, None

    unknown_nodes = sorted(n for n in reachable if n != reference_node)
    node_unknown_index = {n: i for i, n in enumerate(unknown_nodes)}
    source_in_reach = source_usable and p_source in reachable and m_source in reachable
    size = len(unknown_nodes) + (1 if source_in_reach else 0)
    source_unknown_index = len(unknown_nodes) if source_in_reach else None

    if size == 0:
        return None, None

    A = [[complex(0.0, 0.0)] * size for _ in range(size)]
    z = [complex(0.0, 0.0)] * size

    def stamp(a: int, b_: int, y: complex) -> None:
        ia, ib = node_unknown_index.get(a), node_unknown_index.get(b_)
        if ia is not None:
            A[ia][ia] += y
        if ib is not None:
            A[ib][ib] += y
        if ia is not None and ib is not None:
            A[ia][ib] -= y
            A[ib][ia] -= y

    for p, m, y in admittances:
        stamp(p, m, y)

    if source_in_reach:
        k = source_unknown_index
        ip, im = node_unknown_index.get(p_source), node_unknown_index.get(m_source)
        if ip is not None:
            A[ip][k] += 1
            A[k][ip] += 1
        if im is not None:
            A[im][k] -= 1
            A[k][im] -= 1
        z[k] += complex(1.0, 0.0)  # unit-amplitude excitation, 1∠0°

    solution = _solve_linear_complex(A, z)
    if solution is None:
        return None, "Circuit has no unique solution at this frequency (contradictory constraints)."

    if probe_node == reference_node:
        return complex(0.0, 0.0), None
    idx = node_unknown_index.get(probe_node)
    if idx is None:
        return None, None
    return solution[idx], None


def _solve_linear_complex(matrix: list[list[complex]], rhs: list[complex]) -> list[complex] | None:
    """Gaussian elimination with partial pivoting, generalized to complex
    coefficients (pivot selection uses magnitude via abs(), which is well
    defined for complex numbers same as for real ones)."""
    n = len(rhs)
    augmented = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(augmented[r][col]))
        if abs(augmented[pivot_row][col]) < _PIVOT_EPSILON:
            return None
        augmented[col], augmented[pivot_row] = augmented[pivot_row], augmented[col]
        pivot = augmented[col][col]
        for row in range(col + 1, n):
            factor = augmented[row][col] / pivot
            if factor == 0:
                continue
            for c in range(col, n + 1):
                augmented[row][c] -= factor * augmented[col][c]

    solution = [complex(0.0, 0.0)] * n
    for row in range(n - 1, -1, -1):
        s = augmented[row][n] - sum(augmented[row][c] * solution[c] for c in range(row + 1, n))
        solution[row] = s / augmented[row][row]
    return solution
