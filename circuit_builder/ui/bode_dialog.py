"""Bode plot panel - shows the AC frequency response between a chosen
Input (which battery is swept as the AC excitation) and Output (which
electrical node is probed, relative to the Input's own negative terminal)
using the complex-MNA sweep in core/ac_simulation.py. Docked into the main
window (see main_window.py's _open_bode_panel) rather than a separate
modal dialog - Qt's own dock-widget chrome already gives it a "float into
its own window" button and lets it be dragged out, so no custom pop-out
code is needed for that. Opened via a terminal's right-click menu
("Frequency Response..."), the Simulate menu, or the toolbar button -
whichever just picks a starting Input/Output selection; both can be
changed from the dropdowns inside the panel itself at any time, and stay
changeable indefinitely since the panel isn't modal.
"""

from __future__ import annotations

import math
import re
from typing import Callable

import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from circuit_builder.core.ac_simulation import frequency_response
from circuit_builder.core.circuit_model import Circuit
from circuit_builder.core.simulation import _RESISTIVE_TYPES, _terminal_count, _UnionFind

_ACCENT = "#e07a1f"
_PHASE_COLOR = "#58a6ff"
_CROSSHAIR_COLOR = "#e6e6e6"
_POINTS_PER_DECADE = 60

# Matches the app's dark dialog chrome (theme.py) so the plot reads as part
# of the UI instead of a plain white matplotlib default dropped on top of it.
_DIALOG_BG = "#202020"
_AXES_BG = "#181818"
_GRID_COLOR = "#3a3a3a"
_TEXT_COLOR = "#c9c9c9"
_REFERENCE_LINE_COLOR = "#6a6a6a"

_MIN_SWEEP_HZ = 1e-3
_MAX_SWEEP_HZ = 1e12
_DEFAULT_RANGE = (1.0, 1_000_000.0)

# One plot shown full-size at a time (Magnitude/Phase tabs) reads much
# better than two small stacked subplots, especially once the dock gets
# resized wide - these look like tabs sitting on top of the plot they
# control, active one matched to the plot's own background so it reads as
# attached to it rather than floating above.
_TAB_BUTTON_STYLE = f"""
QPushButton {{
    background: #2c2c2c;
    color: #9a9a9a;
    border: 1px solid #3a3a3a;
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 6px 18px;
    font-weight: 600;
}}
QPushButton:checked {{
    background: {_AXES_BG};
    color: #e6e6e6;
    border-color: {_ACCENT};
}}
QPushButton:hover:!checked {{
    background: #333333;
    color: #cfcfcf;
}}
"""

TerminalKey = tuple[str, int]


def _style_axis(ax) -> None:
    ax.set_facecolor(_AXES_BG)
    for spine in ax.spines.values():
        spine.set_color(_GRID_COLOR)
    ax.tick_params(colors=_TEXT_COLOR, labelsize=8)
    ax.xaxis.label.set_color(_TEXT_COLOR)
    ax.yaxis.label.set_color(_TEXT_COLOR)


def _suggest_range(circuit: Circuit) -> tuple[float, float]:
    """Picks a sweep range likely to actually show the circuit's
    frequency-dependent behavior, instead of a fixed window that (depending
    on component values) can easily miss it entirely - e.g. the shipped
    capacitor default is sized for a visible Simulate transient, which
    pushes a plain RC low-pass's corner below 1Hz, off the start of a fixed
    1Hz-1MHz sweep. Estimates a characteristic frequency for every R-C,
    R-L, and L-C pairing present (1/2piRC, R/2piL, 1/2pi*sqrt(LC)) and
    spans two decades past the extremes on either side. Falls back to a
    fixed default when there's nothing reactive to estimate from (a purely
    resistive circuit, or too few component types to pair up)."""
    resistances = [c.value for c in circuit.components if c.type in _RESISTIVE_TYPES and c.value > 0]
    capacitances = [c.value for c in circuit.components if c.type == "capacitor" and c.value > 0]
    inductances = [c.value for c in circuit.components if c.type == "inductor" and c.value > 0]

    candidates: list[float] = []
    for r in resistances:
        for c in capacitances:
            candidates.append(1.0 / (2 * math.pi * r * c))
        for l in inductances:
            candidates.append(r / (2 * math.pi * l))
    for l in inductances:
        for c in capacitances:
            candidates.append(1.0 / (2 * math.pi * math.sqrt(l * c)))

    if not candidates:
        return _DEFAULT_RANGE

    lo = max(_MIN_SWEEP_HZ, min(candidates) / 100.0)
    hi = min(_MAX_SWEEP_HZ, max(candidates) * 100.0)
    if hi <= lo:
        hi = lo * 100.0
    return lo, hi


def _terminal_label(component, terminal_index: int) -> str:
    return f"{component.label} terminal {terminal_index}"


# Matches a Node's auto-generated default label ("J1", "J2", ...) - see
# components.py's JUNCTION prefix "J" and main_window._create_component's
# f"{prefix}{counter}" numbering. Used to tell a still-default Node apart
# from one the user has deliberately renamed (e.g. "Vout"), so a renamed
# Node's label can stand in for its whole electrical node's name.
_DEFAULT_JUNCTION_LABEL = re.compile(r"^J\d+$")


def _node_groups(circuit: Circuit) -> list[list[TerminalKey]]:
    """Groups every terminal in the circuit by which electrical node it's
    actually part of (directly wired together), matching the solver's own
    node-merging - so the Output list shows real, distinguishable circuit
    nodes instead of raw per-terminal entries that can silently duplicate
    each other (two differently-labeled entries that are actually the same
    node because a wire ties them together). Order is stable: each node
    appears where its first member terminal is first encountered, walking
    the circuit's components top to bottom."""
    uf = _UnionFind()
    ordered_terminals: list[TerminalKey] = []
    for c in circuit.components:
        for i in range(_terminal_count(c.type)):
            key = (c.id, i)
            uf.find(key)
            ordered_terminals.append(key)
    for w in circuit.wires:
        uf.union((w.start.component_id, w.start.terminal_index), (w.end.component_id, w.end.terminal_index))

    groups: dict[TerminalKey, list[TerminalKey]] = {}
    for key in ordered_terminals:
        groups.setdefault(uf.find(key), []).append(key)
    return list(groups.values())


def _node_label(group: list[TerminalKey], components_by_id: dict, node_number: int) -> str:
    """Display label for one electrical node in the Output list. A renamed
    Node (junction) placed on that node (e.g. double-clicked and retitled
    "Vout") gives the whole node an actual name - shown up front, since
    that's the whole point of naming it: picking "Vout" out of a dropdown
    is a lot easier than picking "Node 3: R1 terminal 1, C1 terminal 0".
    Falls back to plain auto-numbering when nothing's been named."""
    member_text = ", ".join(_terminal_label(components_by_id[cid], idx) for cid, idx in group)
    custom_names = [
        components_by_id[cid].label
        for cid, idx in group
        if components_by_id[cid].type == "junction"
        and components_by_id[cid].label
        and not _DEFAULT_JUNCTION_LABEL.match(components_by_id[cid].label)
    ]
    if custom_names:
        return f"{custom_names[0]} ({member_text})"
    return f"Node {node_number}: {member_text}"


def _format_hz(f: float) -> str:
    for scale, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m")):
        if abs(f) >= scale:
            return f"{f / scale:.4g} {prefix}Hz"
    return f"{f:.4g} Hz"


class BodePanel(QWidget):
    """Sweeps frequency response between a chosen Input (which battery is
    the swept AC excitation) and Output (which electrical node is probed,
    relative to the Input's negative terminal - the 0V reference for this
    sweep, which moves with whichever battery is picked as Input). Both
    start out set by however the panel was opened, but either can be
    changed at any time from the dropdowns. Shows one big plot at a time -
    Magnitude or Phase, picked with the tab buttons above it - rather than
    two small stacked ones, and hovering over it reads out both values at
    that frequency regardless of which is currently showing.

    Meant to be hosted inside a QDockWidget (see main_window.py) and
    reused across requests via set_probe() rather than recreated each
    time, so it keeps its sweep range/selections when the user asks for a
    different point. Not modal - the circuit can change while it's open,
    so clicking Replot also refreshes Input/Output from the circuit's
    current state (new/removed/renamed components) before re-sweeping,
    preserving the current selections where they still make sense."""

    title_changed = Signal(str)

    def __init__(
        self,
        circuit_provider: Callable[[], Circuit],
        probe_component_id: str,
        probe_terminal_index: int,
        parent=None,
        on_probe_changed: Callable[[list[TerminalKey]], None] | None = None,
    ):
        super().__init__(parent)

        # A callable rather than a static Circuit snapshot, so Replot
        # always sweeps the circuit's current state.
        self._circuit_provider = circuit_provider
        self._on_probe_changed = on_probe_changed
        # Fallback only - used the very first time selectors are populated
        # (nothing to preserve yet). set_probe() re-targets this directly.
        self._initial_probe = (probe_component_id, probe_terminal_index)

        # Filled in by a successful _replot(), read by the hover handler and
        # by _redraw_active_view() (switching Magnitude/Phase just re-draws
        # from these already-solved arrays - no need to re-sweep). None
        # entries (gaps in the sweep) are kept so hover can skip them.
        self._plotted_frequencies: list[float] = []
        self._plotted_mag: list[float | None] = []
        self._plotted_phase: list[float | None] = []
        self._view_mode = "magnitude"  # or "phase" - which one is currently the big plot
        self._crosshair = None

        layout = QVBoxLayout(self)

        io_form = QFormLayout()
        io_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.input_combo = QComboBox()
        self.input_combo.currentIndexChanged.connect(self._on_selection_changed)
        io_form.addRow("Input (swept source):", self.input_combo)

        self.output_combo = QComboBox()
        self.output_combo.currentIndexChanged.connect(self._on_selection_changed)
        io_form.addRow("Output (probed node):", self.output_combo)
        layout.addLayout(io_form)

        self._explanation_label = QLabel("")
        self._explanation_label.setWordWrap(True)
        self._explanation_label.setStyleSheet("color: #9a9a9a; font-style: italic; padding: 2px 0 6px 0;")
        layout.addWidget(self._explanation_label)

        controls = QFormLayout()
        controls.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        range_row = QWidget()
        range_layout = QHBoxLayout(range_row)
        range_layout.setContentsMargins(0, 0, 0, 0)

        validator = QDoubleValidator(1e-3, 1e12, 6, self)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)

        self.start_edit = QLineEdit()
        self.start_edit.setValidator(validator)
        self.end_edit = QLineEdit()
        self.end_edit.setValidator(validator)
        replot_button = QPushButton("Replot")
        replot_button.setToolTip("Re-sweep, and refresh Input/Output from the circuit's current state")
        replot_button.clicked.connect(self._on_replot_clicked)

        range_layout.addWidget(self.start_edit)
        range_layout.addWidget(QLabel("Hz to"))
        range_layout.addWidget(self.end_edit)
        range_layout.addWidget(QLabel("Hz"))
        range_layout.addStretch()
        range_layout.addWidget(replot_button)
        controls.addRow("Frequency swept:", range_row)
        layout.addLayout(controls)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(2)
        self._magnitude_button = QPushButton("Magnitude")
        self._phase_button = QPushButton("Phase")
        for button in (self._magnitude_button, self._phase_button):
            button.setCheckable(True)
            button.setStyleSheet(_TAB_BUTTON_STYLE)
            tab_row.addWidget(button)
        tab_row.addStretch()
        self._magnitude_button.setChecked(True)
        self._magnitude_button.clicked.connect(lambda: self._set_view_mode("magnitude"))
        self._phase_button.clicked.connect(lambda: self._set_view_mode("phase"))
        # Exclusive as a pair (QPushButton's own setCheckable doesn't imply
        # that on its own) - clicking one always un-checks the other.
        self._view_button_group = QButtonGroup(self)
        self._view_button_group.setExclusive(True)
        self._view_button_group.addButton(self._magnitude_button)
        self._view_button_group.addButton(self._phase_button)
        layout.addLayout(tab_row)

        # A single big plot showing whichever of Magnitude/Phase is active,
        # rather than two small stacked subplots - reads far better once
        # the dock gets resized wide, and toggling is instant (no re-sweep,
        # just a re-draw from the already-solved arrays - see
        # _redraw_active_view()).
        self._figure = Figure(figsize=(7, 6), facecolor=_DIALOG_BG)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setMinimumHeight(320)
        self._ax = self._figure.add_subplot(111)
        _style_axis(self._ax)
        self._figure.tight_layout(pad=2.5)
        layout.addWidget(self._canvas, stretch=1)
        self._canvas.mpl_connect("motion_notify_event", self._on_plot_hover)
        self._canvas.mpl_connect("figure_leave_event", lambda _event: self._clear_hover())

        self._hover_label = QLabel(" ")
        self._hover_label.setStyleSheet(f"color: {_TEXT_COLOR}; font-family: Consolas, monospace;")
        layout.addWidget(self._hover_label)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #9a9a9a;")
        layout.addWidget(self._status_label)

        self._populate_selectors()
        lo, hi = _suggest_range(self._circuit_provider())
        self.start_edit.setText(f"{lo:g}")
        self.end_edit.setText(f"{hi:g}")
        self._replot()

    def set_probe(self, probe_component_id: str, probe_terminal_index: int) -> None:
        """Redirects the panel to a newly-requested probe point (a fresh
        right-click, or the menu/toolbar default), refreshing Input/Output
        from the circuit's current state and re-suggesting the sweep range
        for it - unlike a plain Replot, which keeps whatever range the
        user already has."""
        self._populate_selectors(preferred_probe=(probe_component_id, probe_terminal_index))
        lo, hi = _suggest_range(self._circuit_provider())
        self.start_edit.setText(f"{lo:g}")
        self.end_edit.setText(f"{hi:g}")
        self._replot()

    def _on_replot_clicked(self) -> None:
        self._populate_selectors()
        self._replot()

    def _populate_selectors(self, preferred_probe: TerminalKey | None = None) -> None:
        """Fills Input with every battery in the circuit and Output with
        every electrical NODE in the circuit (terminals grouped by wiring,
        not listed one-by-one - see _node_groups). Re-selects the current
        Input battery and Output node if `preferred_probe` isn't given and
        they still exist (so a plain refresh doesn't lose your place),
        otherwise jumps to `preferred_probe` (a genuinely new request) or,
        on the very first call, whatever the panel was opened on."""
        circuit = self._circuit_provider()
        components_by_id = {c.id: c for c in circuit.components}

        previous_input = self.input_combo.currentData()
        previous_output = self.output_combo.currentData()
        target_probe = preferred_probe
        if target_probe is None:
            target_probe = previous_output[0] if previous_output else self._initial_probe

        self.input_combo.blockSignals(True)
        self.input_combo.clear()
        restore_input_index = 0
        for b in circuit.components:
            if b.type == "battery":
                self.input_combo.addItem(f"{b.label} ({b.value:g} V)", (b.id,))
                if previous_input is not None and (b.id,) == previous_input:
                    restore_input_index = self.input_combo.count() - 1
        if self.input_combo.count():
            self.input_combo.setCurrentIndex(restore_input_index)
        self.input_combo.blockSignals(False)

        self.output_combo.blockSignals(True)
        self.output_combo.clear()
        initial_index = 0
        for node_number, group in enumerate(_node_groups(circuit), start=1):
            self.output_combo.addItem(_node_label(group, components_by_id, node_number), group)
            if target_probe in group:
                initial_index = self.output_combo.count() - 1
        if self.output_combo.count():
            self.output_combo.setCurrentIndex(initial_index)
        self.output_combo.blockSignals(False)

        self._notify_probe_changed()
        self.title_changed.emit(self.title())

    def title(self) -> str:
        text = self.output_combo.currentText()
        return f"Frequency Response - {text}" if text else "Frequency Response"

    def _component_by_id(self, component_id: str):
        return next((c for c in self._circuit_provider().components if c.id == component_id), None)

    def _notify_probe_changed(self) -> None:
        if self._on_probe_changed is None:
            return
        group = self.output_combo.currentData()
        if group:
            self._on_probe_changed(group)

    def _on_selection_changed(self, _index: int) -> None:
        self._notify_probe_changed()
        self.title_changed.emit(self.title())
        self._replot()

    def _update_explanation(self) -> None:
        input_data = self.input_combo.currentData()
        output_text = self.output_combo.currentText()
        if input_data is None or not output_text:
            self._explanation_label.setText("")
            return
        excitation = self._component_by_id(input_data[0])
        excitation_label = excitation.label if excitation else "?"
        # The "every other battery"/"moves with whichever you pick" phrasing
        # only makes sense when there's actually more than one to choose
        # between - with just the one (by far the common case), it's
        # confusing filler about a choice that doesn't exist.
        if self.input_combo.count() > 1:
            input_clause = (
                f"Input: {excitation_label}, held at unit amplitude - only its position in the circuit "
                f"matters, not its rated voltage; every other battery is treated as an AC short."
            )
            reference_clause = "the 0V reference for this sweep, which moves with whichever battery is chosen as Input."
        else:
            input_clause = (
                f"Input: {excitation_label}, held at unit amplitude - only its position in the circuit "
                f"matters, not its rated voltage."
            )
            reference_clause = "the 0V reference for this sweep."
        self._explanation_label.setText(
            f"Varying: frequency, swept below. {input_clause} Output: {output_text}, plotted relative to "
            f"{excitation_label}'s negative terminal - {reference_clause}"
        )

    def _set_view_mode(self, mode: str) -> None:
        """Switches the single big plot between Magnitude and Phase -
        no re-sweep needed, just a re-draw from the arrays _replot() (or
        the very first construction) already solved and stored."""
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self._clear_hover()
        self._redraw_active_view()

    def _replot(self) -> None:
        circuit = self._circuit_provider()
        self._update_explanation()
        self._clear_hover()
        self._plotted_frequencies = []
        self._plotted_mag = []
        self._plotted_phase = []
        try:
            start = float(self.start_edit.text())
            end = float(self.end_edit.text())
        except ValueError:
            self._status_label.setText("Enter valid start/end frequencies.")
            self._redraw_active_view()
            return
        if start <= 0 or end <= start:
            self._status_label.setText("Start must be > 0 and less than end.")
            self._redraw_active_view()
            return

        output_group = self.output_combo.currentData()
        input_data = self.input_combo.currentData()

        if not output_group:
            self._status_label.setText("Nothing to analyze - the circuit needs at least one component.")
            self._redraw_active_view()
            return

        probe_component_id, probe_terminal_index = output_group[0]
        excitation_component_id = input_data[0] if input_data is not None else None

        frequencies = _log_sweep(start, end)
        result = frequency_response(
            circuit, probe_component_id, probe_terminal_index, frequencies, excitation_component_id
        )

        if result is None:
            self._status_label.setText("Nothing to analyze - the circuit needs at least one battery.")
            self._redraw_active_view()
            return

        self._plotted_frequencies = frequencies
        self._plotted_mag = result.magnitude_db()
        self._plotted_phase = result.phase_degrees()
        self._redraw_active_view()

        determined_count = sum(1 for m in self._plotted_mag if m is not None)
        if result.warnings:
            self._status_label.setText(" | ".join(result.warnings))
        elif determined_count < len(frequencies):
            self._status_label.setText(
                "Some frequencies had no determined path back to the reference - gaps left out of the plot."
            )
        else:
            self._status_label.setText("")

    def _redraw_active_view(self) -> None:
        """Draws whichever of Magnitude/Phase is currently active from the
        arrays _replot() last solved - called after a real sweep, after
        switching tabs, and on any error path (where the arrays are empty,
        so this just clears the plot)."""
        self._ax.clear()
        # ax.clear() resets facecolor/spines/tick colors to matplotlib's
        # defaults, so the dark styling has to be reapplied every time.
        _style_axis(self._ax)

        if self._view_mode == "magnitude":
            values = self._plotted_mag
            color = _ACCENT
            self._ax.set_ylabel("Magnitude (dB)")
        else:
            values = self._plotted_phase
            color = _PHASE_COLOR
            self._ax.set_ylabel("Phase (degrees)")

        valid_freqs = [f for f, v in zip(self._plotted_frequencies, values) if v is not None]
        valid_values = [v for v in values if v is not None]
        self._ax.semilogx(valid_freqs, valid_values, color=color, linewidth=2.0)
        if self._view_mode == "magnitude":
            self._ax.axhline(-3.0, color=_REFERENCE_LINE_COLOR, linewidth=0.8, linestyle="--")
        self._ax.set_xlabel("Frequency (Hz)")
        self._ax.grid(True, which="both", linewidth=0.4, alpha=0.3, color=_GRID_COLOR)

        # Invisible until the first hover - moved and shown by
        # _on_plot_hover(). Recreated here since ax.clear() above threw
        # away any crosshair from before.
        self._crosshair = self._ax.axvline(valid_freqs[0] if valid_freqs else 1.0, color=_CROSSHAIR_COLOR, linewidth=0.8, linestyle=":", visible=False)

        self._figure.tight_layout(pad=2.5)
        self._canvas.draw()

    def _on_plot_hover(self, event) -> None:
        """Live readout of the exact swept value under the cursor - shows
        the frequency plus BOTH magnitude and phase at that point (not
        just whichever one is currently the active tab, so switching tabs
        after hovering still tells you what the other one was), and drops
        a thin crosshair at that frequency on the plot."""
        if not self._plotted_frequencies or event.inaxes is not self._ax:
            self._clear_hover()
            return
        x = event.xdata
        if x is None or x <= 0:
            self._clear_hover()
            return

        freqs = self._plotted_frequencies
        target = math.log10(x)
        idx = min(range(len(freqs)), key=lambda i: abs(math.log10(freqs[i]) - target))
        f = freqs[idx]
        mag = self._plotted_mag[idx]
        phase = self._plotted_phase[idx]

        if mag is None or phase is None:
            self._hover_label.setText(f"At {_format_hz(f)}: no determined value (no path to the reference)")
            self._set_crosshair_visible(f, False)
            self._canvas.draw_idle()
            return

        self._hover_label.setText(f"At {_format_hz(f)}: {mag:.2f} dB, {phase:.1f}°")
        self._set_crosshair_visible(f, True)
        self._canvas.draw_idle()

    def _set_crosshair_visible(self, f: float, visible: bool) -> None:
        if self._crosshair is not None:
            self._crosshair.set_xdata([f, f])
            self._crosshair.set_visible(visible)

    def _clear_hover(self) -> None:
        self._hover_label.setText(" ")
        if self._crosshair is not None and self._crosshair.get_visible():
            self._crosshair.set_visible(False)
            self._canvas.draw_idle()


def _log_sweep(start_hz: float, end_hz: float) -> list[float]:
    decades = math.log10(end_hz / start_hz)
    n_points = max(2, int(round(decades * _POINTS_PER_DECADE)) + 1)
    return [start_hz * (end_hz / start_hz) ** (i / (n_points - 1)) for i in range(n_points)]
