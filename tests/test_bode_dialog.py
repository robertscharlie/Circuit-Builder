import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QEvent, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QDockWidget

from circuit_builder.core.circuit_model import Circuit, ComponentData, WireData, TerminalRef
from circuit_builder.ui.bode_dialog import BodePanel, _format_hz, _suggest_range
from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.terminal_item import TerminalItem
from circuit_builder.ui.wire_item import WireItem

app = QApplication(sys.argv)


class _FakeHoverEvent:
    """Stands in for matplotlib's MouseEvent, which _on_plot_hover only
    reads .inaxes/.xdata from - lets hover be tested directly without
    driving a real (and unreliable, in a headless test) mouse-move."""

    def __init__(self, inaxes, xdata):
        self.inaxes = inaxes
        self.xdata = xdata
        self.ydata = 0.0


R, C = 1000.0, 1e-6


def make_lowpass():
    """A fresh Circuit each time (some tests mutate the components list in
    place to simulate circuit edits made while the panel stays open)."""
    return Circuit(
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


lowpass = make_lowpass()

# --- 1. Constructing the panel sweeps and plots real data immediately, on
# a single big Magnitude/Phase-toggle plot rather than two small stacked
# subplots. -------------------------------------------------------------
panel = BodePanel(lambda: lowpass, "c1", 0)
assert panel._magnitude_button.isChecked() and not panel._phase_button.isChecked(), "should default to the Magnitude tab"
mag_lines = panel._ax.get_lines()
# the axis has 3 lines while on the Magnitude tab: the response curve, the
# -3dB reference axhline, and the (initially invisible) hover crosshair.
assert len(mag_lines) == 3, "should have plotted the response curve + -3dB reference + hover crosshair"
mag_ydata = mag_lines[0].get_ydata()
assert len(mag_ydata) > 50, "should have swept many points across the default range"
assert mag_ydata[0] > mag_ydata[-1], "a low-pass filter's magnitude should fall off from low to high frequency"
assert panel._ax.get_ylabel() == "Magnitude (dB)"
assert panel._status_label.text() == "", "a clean sweep shouldn't leave a warning message"
assert not panel._crosshair.get_visible(), "crosshair should start hidden until the first hover"
print("1. constructing the panel immediately sweeps and plots a real low-pass curve on the Magnitude tab: OK")

# --- 1b. The Phase tab shows the same sweep's phase, with no re-solve
# needed - switching is a pure re-draw from the already-solved arrays. -----
phase_values_before = list(panel._plotted_phase)
panel._phase_button.setChecked(True)
panel._set_view_mode("phase")
assert not panel._magnitude_button.isChecked() and panel._phase_button.isChecked()
phase_lines = panel._ax.get_lines()
assert len(phase_lines) == 2, "phase tab has just the response curve + hover crosshair - no -3dB reference line"
assert panel._ax.get_ylabel() == "Phase (degrees)"
assert panel._plotted_phase == phase_values_before, "switching tabs shouldn't re-sweep - same solved data"
panel._magnitude_button.setChecked(True)
panel._set_view_mode("magnitude")
print("1b. the Phase tab redraws the same solved data (no re-sweep) with its own axis label and line count: OK")

# --- 2. Replotting with a narrower range updates the data ------------------
panel.start_edit.setText("100")
panel.end_edit.setText("10000")
panel._on_replot_clicked()
mag_lines2 = panel._ax.get_lines()
xdata = mag_lines2[0].get_xdata()
assert min(xdata) >= 99 and max(xdata) <= 10001, f"expected the sweep clipped to [100,10000], got [{min(xdata)},{max(xdata)}]"
print("2. changing the sweep range and hitting Replot re-sweeps within the new bounds: OK")

# --- 3. Invalid range input is rejected with a message, not a crash --------
panel.start_edit.setText("1000")
panel.end_edit.setText("10")  # end < start
panel._on_replot_clicked()
assert "must be" in panel._status_label.text().lower() or "start" in panel._status_label.text().lower()
print("3. an invalid (end <= start) range shows a message instead of crashing: OK")

# --- 4. A circuit with no battery shows a clear message, not a crash -------
no_battery = Circuit(
    components=[ComponentData(id="r1", type="resistor", x=0, y=0, rotation=0, value=1000.0, label="R1")],
    wires=[],
)
panel2 = BodePanel(lambda: no_battery, "r1", 0)
assert "battery" in panel2._status_label.text().lower()
assert panel2.input_combo.count() == 0, "no batteries in the circuit -> nothing to offer as Input"
print("4. a circuit with no battery shows a clear message instead of crashing: OK")

# --- 5. The default sweep range is suggested from the circuit's own R/L/C
# values (bracketing the analytic corner/resonant frequency). --------------

lo, hi = _suggest_range(lowpass)
f_corner = 1.0 / (2 * math.pi * R * C)
assert lo < f_corner < hi, f"suggested range [{lo},{hi}] should bracket the corner frequency {f_corner}"
panel3 = BodePanel(lambda: lowpass, "c1", 0)
assert abs(float(panel3.start_edit.text()) - lo) / lo < 1e-6
assert abs(float(panel3.end_edit.text()) - hi) / hi < 1e-6
print("5. the panel's default sweep range is suggested from the circuit's own R/C values, bracketing the corner: OK")

purely_resistive = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r1", type="resistor", x=100, y=0, rotation=0, value=1000.0, label="R1"),
    ],
    wires=[],
)
assert _suggest_range(purely_resistive) == (1.0, 1_000_000.0), "no reactive components -> fixed fallback range"
print("6. a purely resistive circuit (nothing frequency-dependent) falls back to the fixed default range: OK")

# --- 7. set_probed() actually changes the terminal's drawn extent (an
# extra ring around it), not just an inert flag - a real visual highlight. -

scratch_terminal = TerminalItem(0)
idle_rect = scratch_terminal.boundingRect()
scratch_terminal.set_probed(True)
assert scratch_terminal.boundingRect().width() > idle_rect.width(), "probed terminal should draw a visibly larger ring"
scratch_terminal.set_probed(False)
assert scratch_terminal.boundingRect() == idle_rect, "un-probing should restore the original extent"
print("7. TerminalItem.set_probed() draws a real, visibly larger ring - not just an inert flag: OK")

# --- 8. The Output dropdown lists real electrical NODES (terminals grouped
# by wiring), not one raw entry per terminal. ------------------------------

panel4 = BodePanel(lambda: lowpass, "c1", 0)
assert panel4.input_combo.count() == 1 and panel4.input_combo.itemText(0).startswith("V1")
assert panel4.output_combo.count() == 3, "3 electrical nodes (not 6 raw terminals) - r1.1/c1.0 share a node, as do v1.1/c1.1 and v1.0/r1.0"
initial_group = panel4.output_combo.currentData()
assert set(initial_group) == {("c1", 0), ("r1", 1)}, "should preselect the NODE containing what the panel was opened on"
explanation = panel4._explanation_label.text()
assert "V1" in explanation and "R1 terminal 1" in explanation and "C1 terminal 0" in explanation
assert "frequency" in explanation.lower() and "reference" in explanation.lower()
assert panel4.output_combo.currentText().startswith("Node")
assert panel4.title() == f"Frequency Response - {panel4.output_combo.currentText()}"
print("8. Output dropdown groups terminals into real, labeled electrical nodes (not raw per-terminal entries): OK")

titles_seen = []
panel4.title_changed.connect(titles_seen.append)
other_node_index = next(i for i in range(panel4.output_combo.count()) if ("r1", 0) in panel4.output_combo.itemData(i))
panel4.output_combo.setCurrentIndex(other_node_index)
assert set(panel4.output_combo.currentData()) == {("v1", 0), ("r1", 0)}
assert "R1 terminal 0" in panel4._explanation_label.text()
assert titles_seen and "R1 terminal 0" in titles_seen[-1], "title_changed should fire (for the hosting dock's title bar) when Output changes"
print("9. changing Output from its dropdown re-probes a different node, firing title_changed for the dock: OK")

# --- 10. Changing Input actually selects which battery excites the sweep;
# explanation wording only mentions "every other battery" when there
# genuinely is one; an exact-0V branch plots as real data, not a gap. ------

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
        WireData(id="w7", start=TerminalRef("v1", 1), end=TerminalRef("v2", 1)),
    ],
)
panel5 = BodePanel(lambda: two_source, "cx", 0)
assert panel5.input_combo.count() == 2
mag_v1_excited = panel5._ax.get_lines()[0].get_ydata()
assert mag_v1_excited[0] > mag_v1_excited[-1], "V1 (default Input) drives Cx's branch - a real RC roll-off"

v2_index = next(i for i in range(panel5.input_combo.count()) if panel5.input_combo.itemData(i) == ("v2",))
panel5.input_combo.setCurrentIndex(v2_index)
mag_v2_excited = panel5._ax.get_lines()[0].get_ydata()
assert len(mag_v2_excited) > 0, "an exact 0V reading is determined data, not a gap - it should still be plotted"
assert all(v < -250 for v in mag_v2_excited), (
    "with V2 chosen as Input, Cx's branch should read essentially -inf dB (V1 is now AC-shorted)"
)
assert panel5._status_label.text() == "", "an exact-zero reading is fully determined - no 'gaps' warning"
print("10. changing Input actually re-excites via a different battery; exact-0V branches plot as real data: OK")

assert "other battery" not in panel4._explanation_label.text().lower(), (
    "a single-battery circuit shouldn't talk about 'every other battery' - there isn't one"
)
assert "other battery" in panel5._explanation_label.text().lower(), (
    "a genuinely multi-battery circuit SHOULD explain that other batteries are AC-shorted"
)
print("11. explanation text only mentions 'every other battery' when there's actually more than one: OK")

# --- 12. A renamed Node (junction) placed on an electrical node lends it a
# real name in the Output list ("Vout (...)") instead of "Node N: ...". ----

named = Circuit(
    components=[
        ComponentData(id="v1", type="battery", x=0, y=0, rotation=0, value=9.0, label="V1"),
        ComponentData(id="r1", type="resistor", x=100, y=0, rotation=0, value=R, label="R1"),
        ComponentData(id="c1", type="capacitor", x=200, y=0, rotation=0, value=C, label="C1"),
        ComponentData(id="j1", type="junction", x=150, y=0, rotation=0, value=0.0, label="Vout"),
    ],
    wires=[
        WireData(id="w1", start=TerminalRef("v1", 0), end=TerminalRef("r1", 0)),
        WireData(id="w2", start=TerminalRef("r1", 1), end=TerminalRef("c1", 0)),
        WireData(id="w3", start=TerminalRef("c1", 1), end=TerminalRef("v1", 1)),
        WireData(id="w4", start=TerminalRef("j1", 0), end=TerminalRef("c1", 0)),  # same node as r1.1/c1.0
    ],
)
panel6 = BodePanel(lambda: named, "c1", 0)
named_index = next(i for i in range(panel6.output_combo.count()) if ("j1", 0) in panel6.output_combo.itemData(i))
named_text = panel6.output_combo.itemText(named_index)
assert named_text.startswith("Vout"), f"a renamed Node should lend its name to the whole node's label, got {named_text!r}"
assert "Node" not in named_text.split("(")[0], "shouldn't fall back to generic 'Node N:' numbering once it's been named"
# an UN-renamed Node (still "J2" style) should NOT be treated as a real name
unnamed_index = next(i for i in range(panel6.output_combo.count()) if ("v1", 0) in panel6.output_combo.itemData(i))
assert panel6.output_combo.itemText(unnamed_index).startswith("Node"), "a still-default 'J#' Node shouldn't be treated as a custom name"
print("12. a renamed Node lends its name to the Output entry for its whole electrical node: OK")

# --- 13. set_probe() reuses the SAME panel for a fresh request - it
# refreshes Input/Output from the circuit's current state, re-suggests the
# sweep range for the new target, but preserves the Input selection if
# that battery still exists. -----------------------------------------------

panel7 = BodePanel(lambda: two_source, "cx", 0)
v2_idx = next(i for i in range(panel7.input_combo.count()) if panel7.input_combo.itemData(i) == ("v2",))
panel7.input_combo.setCurrentIndex(v2_idx)
assert panel7.input_combo.currentData() == ("v2",)

panel7.set_probe("cy", 0)
assert set(panel7.output_combo.currentData()) & {("cy", 0)}, "should jump Output to the newly requested probe"
assert panel7.input_combo.currentData() == ("v2",), "Input selection (V2) should survive a set_probe() to an unrelated node"
print("13. set_probe() redirects Output to the new target while preserving the current Input selection: OK")

# --- 14. Replot also refreshes Input/Output from the circuit's current
# state - components added since the panel was constructed show up without
# needing to reopen it. -----------------------------------------------------

live_circuit = make_lowpass()
panel8 = BodePanel(lambda: live_circuit, "c1", 0)
assert panel8.output_combo.count() == 3
live_circuit.components.append(ComponentData(id="r2", type="resistor", x=400, y=400, rotation=0, value=500.0, label="R2"))
panel8._on_replot_clicked()
assert panel8.output_combo.count() == 5, "a freshly-added (unwired) resistor should add 2 new node entries after Replot"
print("14. clicking Replot picks up components added to the circuit since the panel was opened: OK")

# --- 15. Hovering over the plot reads out the exact frequency, magnitude,
# AND phase at that point (both, regardless of which tab is active),
# drawing a crosshair - moving off the plot (or a gap with no determined
# value) clears it. Switching tabs after a hover still shows the readout
# from before (it isn't cleared just by switching, only by moving off). ---

panel_hover = BodePanel(lambda: lowpass, "c1", 0)
freqs = panel_hover._plotted_frequencies
mid = len(freqs) // 2
f, mag, phase = freqs[mid], panel_hover._plotted_mag[mid], panel_hover._plotted_phase[mid]

panel_hover._on_plot_hover(_FakeHoverEvent(panel_hover._ax, f))
assert panel_hover._hover_label.text() == f"At {_format_hz(f)}: {mag:.2f} dB, {phase:.1f}°"
assert panel_hover._crosshair.get_visible()
print("15. hovering the plot shows the exact frequency/magnitude/phase and drops a crosshair: OK")

panel_hover._phase_button.setChecked(True)
panel_hover._set_view_mode("phase")
panel_hover._on_plot_hover(_FakeHoverEvent(panel_hover._ax, f))
assert panel_hover._hover_label.text() == f"At {_format_hz(f)}: {mag:.2f} dB, {phase:.1f}°"
print("16. hovering after switching to the Phase tab gives the same shared readout: OK")

panel_hover._on_plot_hover(_FakeHoverEvent(None, None))
assert panel_hover._hover_label.text().strip() == ""
assert not panel_hover._crosshair.get_visible()
print("17. moving the cursor off the plot clears the readout and hides the crosshair: OK")

# =====================================================================
# MainWindow integration: the panel lives in a QDockWidget docked into
# the same window, reused (not recreated) across requests, with the
# canvas highlight following whether it's actually visible.
# =====================================================================

window = MainWindow()
window.resize(1000, 600)
window.show()
window.raise_()
window.activateWindow()
app.processEvents()
view = window.view

probe_calls: list[tuple[object, bool]] = []
original_set_probed = TerminalItem.set_probed


def _tracking_set_probed(self, probed):
    probe_calls.append((self, probed))
    original_set_probed(self, probed)


TerminalItem.set_probed = _tracking_set_probed

# --- 18. Toolbar/menu with an empty canvas shows a status message, not a
# crash - and doesn't create a dock for nothing. -----------------------

window.statusBar().clearMessage()
window._show_frequency_response_panel()
assert "nothing to analyze" in window.statusBar().currentMessage().lower()
assert window._bode_dock is None, "an empty canvas shouldn't create the dock at all"
print("18. Simulate menu / toolbar button on an empty canvas shows a message instead of crashing: OK")

v1 = window.add_component("battery", QPointF(-200, 0))
r1 = window.add_component("resistor", QPointF(0, 0))
c1 = window.add_component("capacitor", QPointF(200, 0))
for a, b in ((v1.terminals[0], r1.terminals[0]), (r1.terminals[1], c1.terminals[0]), (c1.terminals[1], v1.terminals[1])):
    w = WireItem(a, b)
    w.attach()
    window.scene.addItem(w)
app.processEvents()

# --- 19. The toolbar button and the Simulate menu item are the SAME
# QAction (so both stay in sync automatically) - triggering it opens the
# dock, defaulting Output to a non-battery component's node. ---------------

assert window._frequency_response_action is not None
window._frequency_response_action.trigger()
app.processEvents()
assert isinstance(window._bode_dock, QDockWidget)
assert window._bode_dock.isVisible()
expected_default = next(c for c in window._build_circuit_model().components if c.type != "battery")
assert (expected_default.id, 0) in window._bode_panel.output_combo.currentData()
print("19. the toolbar button (== the Simulate menu item) opens the dock, defaulting Output to a non-battery node: OK")

# --- 20. Right-clicking a DIFFERENT terminal reuses the SAME dock/panel
# instance rather than creating a second one - and highlights every
# terminal belonging to that node (they're the same electrical point). -----

first_dock = window._bode_dock
first_panel = window._bode_panel

view._menu_exec_override = lambda menu: next((a for a in menu.actions() if a.text() == "Frequency Response..."), None)

def right_click(scene_pos):
    vp_pos = view.mapFromScene(scene_pos)
    view.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, vp_pos, vp_pos, Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier))

probe_calls.clear()
right_click(c1.terminals[0].scenePos())
app.processEvents()
assert window._bode_dock is first_dock and window._bode_panel is first_panel, "should reuse the existing dock/panel, not create a new one"
assert set(window._bode_panel.output_combo.currentData()) == {(c1.id, 0), (r1.id, 1)}
true_terminals = {t for t, probed in probe_calls if probed}
assert true_terminals == {c1.terminals[0], r1.terminals[1]}, "every terminal in the probed node should be highlighted, not just the one clicked"
print("20. right-clicking a different terminal reuses the same dock/panel and re-targets Output to it: OK")
print("    ...highlighting every terminal belonging to that node, not just the one clicked: OK")

# --- 21. Hiding the dock (closing it) clears the canvas highlight;
# reshowing it re-applies the highlight for whatever's currently selected. -

probe_calls.clear()
window._bode_dock.setVisible(False)
app.processEvents()
assert window._probe_highlight_terminals == [], "hiding the panel should clear the canvas highlight"
assert c1.terminals[0]._probed is False and r1.terminals[1]._probed is False

window._bode_dock.setVisible(True)
app.processEvents()
assert {t for t in window._probe_highlight_terminals} == {c1.terminals[0], r1.terminals[1]}, (
    "reshowing the panel should re-apply the highlight for whatever Output is currently selected"
)
print("21. hiding the dock clears the canvas highlight; reshowing it re-applies for the current selection: OK")

# --- 22. An unwired terminal's own node is just itself. --------------------

probe_calls.clear()
r2 = window.add_component("resistor", QPointF(400, 300))
app.processEvents()
right_click(r2.terminals[1].scenePos())
app.processEvents()
assert set(window._bode_panel.output_combo.currentData()) == {(r2.id, 1)}
true_terminals = {t for t, probed in probe_calls if probed}
assert true_terminals == {r2.terminals[1]}
print("22. an unwired terminal (previously without any Frequency Response option) now offers it too: OK")

# --- 23. A Node's own terminal also offers Frequency Response. -------------

probe_calls.clear()
node = window.add_component("junction", QPointF(400, 500))
app.processEvents()
right_click(node.terminals[0].scenePos())
app.processEvents()
assert set(window._bode_panel.output_combo.currentData()) == {(node.id, 0)}
print("23. a Node's own terminal also offers Frequency Response, and gets highlighted the same way: OK")

# --- 24. Floating the dock (popping it into its own window) keeps it
# visible - and thus keeps the canvas highlight - with no crash. -----------

window._bode_dock.setFloating(True)
app.processEvents()
assert window._bode_dock.isVisible()
assert window._probe_highlight_terminals, "floating the dock into its own window shouldn't drop the highlight"
window._bode_dock.setFloating(False)
app.processEvents()
print("24. floating the dock into its own window keeps it visible (and the highlight) with no crash: OK")

TerminalItem.set_probed = original_set_probed
window.undo_stack.setClean()
window.close()
print("ALL BODE DIALOG TESTS PASSED")
