"""DC and transient circuit simulation (nodal analysis).

Qt-free by design, like the rest of `core/` - operates purely on a
``Circuit`` (components + wires) and hands back plain numbers; the UI layer
decides how to display them.

Wires (and any zero-resistance component) are collapsed into "electrical
nodes" via a union-find pass first, then solved with Modified Nodal
Analysis (MNA) so ideal voltage sources (batteries, and - see below - a
capacitor at a given instant) can sit alongside plain resistors.

Two ways to call ``simulate()``, both sharing the same solver:

1. ``simulate(circuit)`` - the pure DC steady-state operating point, i.e.
   "after a very long time": a capacitor is a true open circuit (fully
   charged, no current), an inductor is a plain wire (fully saturated, no
   resistance). This is what every non-transient caller (including all the
   existing tests) gets, and behaves exactly as before either component got
   a transient mode.
2. ``simulate(circuit, dt=<seconds>, state=TransientState(...))`` - advances
   the simulation by ``dt`` of simulated time using the standard
   backward-Euler companion model for BOTH reactive components, mirror
   images of each other:
     - a capacitor becomes a conductance ``C/dt`` in parallel with a
       current source based on its previous *voltage* - since a capacitor's
       voltage can't jump instantly, it starts (dt -> 0) looking like a
       short, and settles toward an open circuit as it charges.
     - an inductor becomes a conductance ``dt/L`` in parallel with a
       current source based on its previous *current* - since an
       inductor's current can't jump instantly, it starts (dt -> 0) looking
       like an open circuit, and settles toward a short as current builds
       up through it.
   `state` is updated in place with each component's new voltage/current
   for the next call, so repeated calls (e.g. from a UI timer) trace out
   the real RC/L-R charge curves. A very small ``dt`` (rather than
   ``dt=None``/no time at all) is how a caller gets an "instantaneous"
   refresh after some other edit without advancing the clock - deliberately
   NOT modeled as either component turning into an ideal source pinned at
   its last value, which sounds equivalent but isn't: a battery connected
   to an uncharged capacitor with no resistance in between would make that
   a hard, contradictory constraint (an actual short-circuit-like
   singularity) the moment a switch closes. A finite (if huge) conductance
   never has that problem.

Besides capacitors and inductors, the rest of the component model is
unchanged:
- resistors and bulbs: normal conductance, ``1/R`` (a value <= 0 is treated
  as a dead short, same as a wire, rather than dividing by zero) - a bulb is
  just a resistor that also gets a brightness readout layered on top in the UI
- switches: a short circuit while closed, an open circuit while open
- batteries: ideal voltage sources. Terminal 0 is (+) and terminal 1 is
  (-), matching the polarity drawn in ui/component_item.py's _draw_battery.

There's no dedicated ground/reference component yet (see the README
roadmap), so the reference (0V) node defaults to the first battery's
negative terminal, or the circuit's first electrical node if there's no
battery at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from circuit_builder.core.circuit_model import Circuit

_EPSILON = 1e-12
_PIVOT_EPSILON = 1e-9

# A bulb is electrically just a resistor (with a brightness readout layered
# on top in the UI) - treated identically everywhere in this solver.
_RESISTIVE_TYPES = {"resistor", "lamp"}

TerminalKey = tuple[str, int]


@dataclass
class TransientState:
    """Carries a live simulation's capacitor charge and inductor current
    from one call to the next. A freshly created TransientState means every
    capacitor starts uncharged (0V) and every inductor starts carrying no
    current (0A) - the same as either would be before anything has
    happened. Mutated in place by every ticking simulate() call."""

    capacitor_voltage: dict[str, float] = field(default_factory=dict)
    inductor_current: dict[str, float] = field(default_factory=dict)


@dataclass
class SimulationResult:
    node_voltage: dict[int, float | None]
    terminal_node: dict[TerminalKey, int]
    terminal_voltage: dict[TerminalKey, float | None]
    reference_node: int
    warnings: list[str] = field(default_factory=list)

    def voltage_at(self, component_id: str, terminal_index: int) -> float | None:
        return self.terminal_voltage.get((component_id, terminal_index))


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[TerminalKey, TerminalKey] = {}

    def find(self, x: TerminalKey) -> TerminalKey:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: TerminalKey, b: TerminalKey) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def _terminal_count(component_type: str) -> int:
    return 1 if component_type == "junction" else 2


def simulate(
    circuit: Circuit,
    dt: float | None = None,
    state: TransientState | None = None,
) -> SimulationResult | None:
    """Returns None if there's nothing to simulate (an empty circuit). See
    the module docstring for the two ways to call this."""
    if not circuit.components:
        return None

    ticking = state is not None and dt is not None and dt > 0

    uf = _UnionFind()
    for c in circuit.components:
        for i in range(_terminal_count(c.type)):
            uf.find((c.id, i))

    for w in circuit.wires:
        uf.union((w.start.component_id, w.start.terminal_index), (w.end.component_id, w.end.terminal_index))

    # Zero-resistance branches behave exactly like a wire for this pass.
    # Neither reactive component is ever one of these while ticking with a
    # real (non-zero) value - each is instead a companion conductance built
    # below. Outside of a ticking call, an inductor is fully saturated (DC
    # steady state), so it collapses to a wire same as always; a
    # (practically) zero-valued inductor collapses to a wire either way,
    # same treatment as a (practically) zero-valued resistor.
    for c in circuit.components:
        if (
            (c.type == "inductor" and (not ticking or c.value <= _EPSILON))
            or (c.type in _RESISTIVE_TYPES and c.value <= _EPSILON)
            or (c.type == "switch" and c.closed)
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
    warnings: list[str] = []
    batteries = [c for c in circuit.components if c.type == "battery"]

    if batteries:
        reference_node = node_of[(batteries[0].id, 1)]
    else:
        reference_node = 0

    # --- Ideal voltage sources for this solve: batteries only - a capacitor
    # never becomes one (see the module docstring for why).
    voltage_sources: list[tuple[str, TerminalKey, TerminalKey, float, str]] = [
        (b.id, (b.id, 0), (b.id, 1), b.value, b.label) for b in batteries
    ]

    usable_sources = []
    for comp_id, p_key, m_key, voltage, label in voltage_sources:
        p, m = node_of[p_key], node_of[m_key]
        if p == m:
            warnings.append(f"{label}: short-circuited (both terminals share a node) - excluded from the solve")
            continue
        usable_sources.append((comp_id, p, m, voltage, label))

    # --- Companion-model capacitors for a ticking step: a conductance
    # g=C/dt in parallel with a current source derived from the last-known
    # voltage (standard backward-Euler discretization of i = C*dV/dt).
    companion_capacitors: list[tuple[int, int, float, float]] = []  # (node_p, node_m, g, i_eq)
    if ticking:
        for c in circuit.components:
            if c.type == "capacitor" and c.value > _EPSILON:
                p, m = node_of[(c.id, 0)], node_of[(c.id, 1)]
                g = c.value / dt
                v_prev = state.capacitor_voltage.get(c.id, 0.0)
                companion_capacitors.append((p, m, g, g * v_prev))

    # --- Companion-model inductors for a ticking step: the mirror image of
    # the capacitor above - a conductance g=dt/L in parallel with a current
    # source derived from the last-known *current* through it (standard
    # backward-Euler discretization of v = L*di/dt). Note the injected
    # current is -i_prev rather than +i_prev like the capacitor's i_eq: the
    # capacitor's source models a voltage the branch remembers, while the
    # inductor's models a current the branch insists on keeping flowing
    # regardless of voltage - working through the same KCL bookkeeping
    # flips its sign relative to the capacitor's.
    companion_inductors: list[tuple[int, int, float, float]] = []  # (node_p, node_m, g, i_eq)
    if ticking:
        for c in circuit.components:
            if c.type == "inductor" and c.value > _EPSILON:
                p, m = node_of[(c.id, 0)], node_of[(c.id, 1)]
                g = dt / c.value
                i_prev = state.inductor_current.get(c.id, 0.0)
                companion_inductors.append((p, m, g, -i_prev))

    # Any node not reachable from the reference via a resistor, a voltage
    # source, or (while ticking) a reactive component's own conductance has
    # no DC path back to it (e.g. isolated behind a true open capacitor, or
    # a disconnected sub-circuit) - its voltage is left undetermined (None)
    # rather than guessed at.
    adjacency: dict[int, set[int]] = {i: set() for i in range(n_nodes)}

    def _connect(a: int, b: int) -> None:
        adjacency[a].add(b)
        adjacency[b].add(a)

    for c in circuit.components:
        if c.type in _RESISTIVE_TYPES and c.value > _EPSILON:
            _connect(node_of[(c.id, 0)], node_of[(c.id, 1)])
    for _comp_id, p, m, _voltage, _label in usable_sources:
        _connect(p, m)
    for p, m, _g, _i_eq in companion_capacitors:
        _connect(p, m)
    for p, m, _g, _i_eq in companion_inductors:
        _connect(p, m)

    reachable = {reference_node}
    frontier = [reference_node]
    while frontier:
        cur = frontier.pop()
        for nxt in adjacency[cur]:
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)

    unknown_nodes = sorted(n for n in reachable if n != reference_node)
    node_unknown_index = {n: i for i, n in enumerate(unknown_nodes)}
    solved_sources = [
        (comp_id, p, m, voltage, label)
        for comp_id, p, m, voltage, label in usable_sources
        if p in reachable and m in reachable
    ]
    source_unknown_index = {comp_id: len(unknown_nodes) + i for i, (comp_id, *_rest) in enumerate(solved_sources)}

    node_voltage: dict[int, float | None] = {n: (0.0 if n == reference_node else None) for n in range(n_nodes)}
    size = len(unknown_nodes) + len(solved_sources)

    if size > 0:
        A = [[0.0] * size for _ in range(size)]
        z = [0.0] * size

        def stamp_conductance(a: int, b_: int, g: float) -> None:
            ia, ib = node_unknown_index.get(a), node_unknown_index.get(b_)
            if ia is not None:
                A[ia][ia] += g
            if ib is not None:
                A[ib][ib] += g
            if ia is not None and ib is not None:
                A[ia][ib] -= g
                A[ib][ia] -= g

        def stamp_current_source(a: int, b_: int, current: float) -> None:
            # An independent current source injecting `current` into node a
            # and drawing it back out of node b.
            ia, ib = node_unknown_index.get(a), node_unknown_index.get(b_)
            if ia is not None:
                z[ia] += current
            if ib is not None:
                z[ib] -= current

        for c in circuit.components:
            if c.type in _RESISTIVE_TYPES and c.value > _EPSILON:
                stamp_conductance(node_of[(c.id, 0)], node_of[(c.id, 1)], 1.0 / c.value)

        for p, m, g, i_eq in companion_capacitors:
            stamp_conductance(p, m, g)
            stamp_current_source(p, m, i_eq)

        for p, m, g, i_eq in companion_inductors:
            stamp_conductance(p, m, g)
            stamp_current_source(p, m, i_eq)

        for comp_id, p, m, voltage, _label in solved_sources:
            k = source_unknown_index[comp_id]
            ip, im = node_unknown_index.get(p), node_unknown_index.get(m)
            if ip is not None:
                A[ip][k] += 1
                A[k][ip] += 1
            if im is not None:
                A[im][k] -= 1
                A[k][im] -= 1
            z[k] += voltage

        solution = _solve_linear(A, z)
        if solution is None:
            warnings.append("Circuit has no unique solution (contradictory constraints) - check for shorted sources.")
        else:
            for n, i in node_unknown_index.items():
                node_voltage[n] = solution[i]

    terminal_node: dict[TerminalKey, int] = {}
    terminal_voltage: dict[TerminalKey, float | None] = {}
    for c in circuit.components:
        for i in range(_terminal_count(c.type)):
            key = (c.id, i)
            n = node_of[key]
            terminal_node[key] = n
            terminal_voltage[key] = node_voltage[n]

    # Advance the transient state for the next tick - a capacitor's new
    # voltage is just whatever its terminals settled at this step; an
    # inductor's new current is recovered from that same companion formula
    # (i_new = i_prev + g*v) now that v is known.
    if ticking:
        for c in circuit.components:
            if c.type == "capacitor":
                v0 = terminal_voltage[(c.id, 0)]
                v1 = terminal_voltage[(c.id, 1)]
                if v0 is not None and v1 is not None:
                    state.capacitor_voltage[c.id] = v0 - v1
            elif c.type == "inductor" and c.value > _EPSILON:
                v0 = terminal_voltage[(c.id, 0)]
                v1 = terminal_voltage[(c.id, 1)]
                if v0 is not None and v1 is not None:
                    g = dt / c.value
                    i_prev = state.inductor_current.get(c.id, 0.0)
                    state.inductor_current[c.id] = i_prev + g * (v0 - v1)

    return SimulationResult(
        node_voltage=node_voltage,
        terminal_node=terminal_node,
        terminal_voltage=terminal_voltage,
        reference_node=reference_node,
        warnings=warnings,
    )


def _solve_linear(matrix: list[list[float]], rhs: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting. Returns None if the
    system is singular (no unique solution)."""
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

    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        s = augmented[row][n] - sum(augmented[row][c] * solution[c] for c in range(row + 1, n))
        solution[row] = s / augmented[row][row]
    return solution
