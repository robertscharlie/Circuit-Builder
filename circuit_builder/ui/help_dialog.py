from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

_CONTROLS_HTML = """
<style>
  h3 { color: #e07a1f; margin-bottom: 4px; }
  ul { margin-top: 2px; }
  li { margin-bottom: 4px; }
  code {
    background: rgba(255,255,255,20);
    border-radius: 3px;
    padding: 1px 5px;
  }
</style>

<h3>Placing components</h3>
<ul>
  <li>Drag a component from the panel on the left onto the canvas, or press
    its shortcut key: <code>R</code> Resistor, <code>B</code> Battery,
    <code>C</code> Capacitor, <code>I</code> Inductor, <code>L</code> Bulb,
    <code>S</code> Switch, <code>N</code> Node.</li>
  <li>Pressing a shortcut key drops the canvas into placement mode - a ghost
    symbol follows the cursor until you click to place it.</li>
  <li>While placing, press <code>R</code> again to rotate the ghost, or
    <code>Esc</code> to cancel.</li>
  <li>A <b>Switch</b> starts open. Click a placed switch (a plain click, not
    a drag) to flip it open/closed - double-click it instead to rename it.</li>
</ul>

<h3>Wiring</h3>
<ul>
  <li>Click and drag from one terminal (the small dot at the end of a
    component's leads) to another terminal.</li>
  <li>Drop it on an existing wire's line instead (not at either of that
    wire's own ends) to tap into it - handy for a Node, which has no body
    to drag and so can only ever be moved with Shift+drag (below) or
    connected this way.</li>
  <li>A <b>Node</b> is a bare terminal you can drop anywhere to fan a wire
    out to several others.</li>
</ul>

<h3>Moving things</h3>
<ul>
  <li>Click and drag a component's body. It snaps to a 20px grid; connected
    wires follow automatically.</li>
  <li>A Node has no body to grab - hold <code>Shift</code> while dragging its
    terminal to move it instead of starting a wire.</li>
  <li>Right-click a component or Node and choose <b>Move</b> as an
    alternative to dragging - it then follows the cursor until your next
    click.</li>
  <li>Renaming a Node (double-click it) gives its whole electrical point a
    real name, e.g. "Vout" - Frequency Response's Output list (below) picks
    that name up automatically instead of an auto-numbered "Node 3: ...",
    so naming a point you care about ahead of time makes it much easier to
    find in the dropdown later.</li>
</ul>

<h3>Right-click menus</h3>
<ul>
  <li><b>On a wire</b> - <i>Split Wire Here</i> inserts a Node at the
    nearest grid point, splitting the wire in two. <i>Split and Move</i>
    does the same split, then immediately hands the new Node to the cursor
    (follows it until your next click, same as picking Move afterward)
    instead of leaving it sitting still - handy when you already know it
    needs repositioning.</li>
  <li><b>On a component or Node</b> - <i>Move</i> lets you relocate it by
    clicking its new spot instead of dragging.</li>
  <li><b>On a wired terminal</b> - <i>Move Node</i> detaches that wire onto
    a new free Node, disconnecting it from the component so it can be
    dragged elsewhere.</li>
  <li><b>On any terminal</b> - <i>Frequency Response...</i> opens a Bode
    plot for that point's electrical node (see "Frequency Response" below),
    highlighting every terminal belonging to that node on the canvas with a
    green ring for as long as the panel stays visible. Available on every
    terminal, wired or not, alongside whichever of the above also applies
    to it.</li>
</ul>

<h3>Auto-connect</h3>
<ul>
  <li>Ending a move with a terminal sitting on top of (or, for a diagonal
    wire, very close to) another terminal wires them together automatically.</li>
  <li>If either side is a Node, it merges away instead: the Node is deleted
    and its wire(s) are rewired straight to the other terminal. This works
    whichever side you dragged, and for every component type.</li>
  <li>Ending a move with a terminal sitting on an existing wire's line (not
    at either end) taps into it instead - that one wire becomes two, routed
    through the terminal that landed on it. No new component is created.</li>
  <li>Dropping a two-terminal component with BOTH terminals on the same
    wire splices it into that wire instead: the wire is deleted and its two
    original ends are rewired straight to the component's near/far
    terminal, so current now has to pass through it (e.g. a resistor or
    switch actually does something) rather than the wire's original direct
    connection just shorting it out in parallel.</li>
</ul>

<h3>Simulating</h3>
<ul>
  <li>Press <b>Simulate</b> (<code>F5</code>) to start a <i>live</i>
    simulation: it solves the circuit and shows a small voltage label at
    every terminal - wires carry that same voltage all the way along, since
    both ends of a wire are electrically one node. A Bulb's glow tracks the
    voltage across it, brightest at the supply voltage and dimming smoothly
    below that.</li>
  <li>It keeps running on its own - no need to touch anything - and any
    edit (move, wire, toggle a switch, undo/redo, ...) also refreshes it
    immediately. A <b>Capacitor</b> charges and discharges over real time
    while it runs: build a switch + capacitor + bulb circuit (bulb in
    parallel with the capacitor), close the switch to charge the capacitor
    and light the bulb, then open it - the bulb visibly fades out as the
    capacitor drains through it, tracing out a real RC decay curve.</li>
  <li>An <b>Inductor</b> does the opposite - it resists a sudden change in
    current instead of voltage. Build a switch + inductor + bulb circuit
    (all three in series this time), and closing the switch leaves the bulb
    dark at first - then it brightens smoothly over a couple of seconds as
    current builds up through the inductor, tracing out a real L/R curve.</li>
  <li>Resistors and bulbs behave normally, and a switch is a wire while
    closed or a break while open. A fresh simulation starts every capacitor
    uncharged (0V) and every inductor carrying no current (0A), same as a
    real one before anything has happened.</li>
  <li>0V (the reference/"ground") is the negative terminal of the first
    battery in the circuit - there's no separate ground symbol yet.</li>
  <li>A label reading <code>N/A</code> means that point has no path back to
    the reference at all (e.g. a disconnected sub-circuit) so its voltage
    isn't determined by the circuit.</li>
  <li>Click <b>Stop</b> (the same button, now showing a stop icon - or
    <code>F5</code> again) to end the live simulation and clear the labels.</li>
</ul>

<h3>Frequency Response</h3>
<ul>
  <li>Right-click any terminal and choose <i>Frequency Response...</i>, or
    use the toolbar button (a small chart icon, next to Simulate) or
    <b>Simulate &gt; Frequency Response...</b> to open it without picking a
    terminal first, for a Bode plot - magnitude (dB) and phase (degrees) of
    a chosen point, swept across a range of frequencies. Unlike Simulate
    (a single instant), this shows how the circuit responds across a whole
    frequency range at once.</li>
  <li>It opens as a panel docked into this same window, right beside the
    canvas rather than a popup blocking it. Its title bar has a small
    float button to pop it into its own separate window whenever you want
    it out of the way - drag it back onto the main window to re-dock it,
    or just leave it floating. Closing it (the X button) hides it without
    losing your settings; asking for Frequency Response again reuses the
    same panel and just re-targets it, rather than opening a second one.</li>
  <li>Every terminal belonging to the probed node is marked with a green
    ring on the canvas the whole time the panel is visible (docked or
    floating), so it's always clear which point the plot is showing.</li>
  <li>The panel has explicit <b>Input</b> and <b>Output</b> dropdowns
    instead of quietly assuming them: <b>Input</b> picks which battery is
    the swept AC excitation (held at unit amplitude - its own rated
    voltage doesn't matter, only its position in the circuit; every other
    battery is treated as an AC short, the standard convention for
    isolating one source's contribution). <b>Output</b> picks which
    <i>electrical node</i> is probed - terminals that are wired together
    are grouped into one clearly labeled entry (e.g.
    <code>Node 3: R1 terminal 1, C1 terminal 0</code>, or just
    <code>Vout (...)</code> if you've renamed a Node placed there - see
    "Moving things" above) instead of listing every terminal separately,
    since two entries that are actually wired together give identical
    results and would otherwise look like different choices. Both Input
    and Output start out set by however the panel was opened, but can be
    changed from their dropdowns at any time - an italic line underneath
    spells out, in plain terms, what's being varied (frequency) and what
    the current Input/Output actually are.</li>
  <li>The plotted voltage is always relative to the <i>chosen</i> Input
    battery's own negative terminal - that's the 0V reference for the
    sweep, and it moves with whichever battery is picked as Input. This is
    different from Simulate, which always references the first battery in
    the circuit regardless.</li>
  <li>Resistors stay purely real; capacitors and inductors become complex
    impedances (<code>1/(jwC)</code>, <code>jwL</code>) that change with
    frequency.</li>
  <li>The plot is one big chart with <b>Magnitude</b> and <b>Phase</b> tab
    buttons above it, rather than two small stacked ones - click either to
    switch, instantly (it's just re-drawing the same already-solved sweep,
    not re-sweeping). Hover the mouse over the plot to read out the exact
    frequency, magnitude, AND phase together at that point (regardless of
    which tab is currently showing), with a thin crosshair marking it.</li>
  <li>The panel isn't modal, so you can keep editing the circuit while it
    stays open - click <b>Replot</b> to both re-sweep and pick up any
    structural changes since it was opened (new, renamed, or removed
    components), keeping your current Input/Output selections if they
    still exist.</li>
  <li>The initial sweep range is auto-suggested from the circuit's own
    R/L/C values - it estimates every R-C/R-L corner and L-C resonant
    frequency actually present and spans a couple of decades past the
    extremes, so the interesting part of the curve is visible immediately
    rather than needing a manual widen first. Enter a different start/end
    frequency (Hz) and click <b>Replot</b> to zoom further into a corner or
    resonant peak.</li>
</ul>

<h3>Editing</h3>
<ul>
  <li>Double-click a component to edit its label and value.</li>
  <li>Select a component or wire and press <code>Delete</code> to remove it.</li>
  <li>Select a component and press <code>Ctrl+R</code> to rotate it.</li>
</ul>

<h3>Undo, zoom, and pan</h3>
<ul>
  <li><code>Ctrl+Z</code> / <code>Ctrl+Y</code> to undo/redo - covers adds,
    deletes, moves, rotates, wiring, and value edits.</li>
  <li>Scroll to zoom, or use the toolbar's Zoom In/Out, Fit to View, and
    Reset Zoom buttons (<code>Ctrl+=</code> / <code>Ctrl+-</code> /
    <code>Ctrl+0</code> / <code>Ctrl+1</code>).</li>
  <li>Hold the middle mouse button and drag to pan, or toggle the Pan Tool
    (<code>H</code>) to make plain left-drag pan the canvas instead.</li>
</ul>

<h3>Files</h3>
<ul>
  <li><code>Ctrl+S</code> / <code>Ctrl+O</code> to save/open a circuit as
    plain JSON. Closing the window, or starting New/Open, prompts to save
    first if there are unsaved changes.</li>
</ul>
"""


class ControlsHelpDialog(QDialog):
    """Reference dialog listing every mouse/keyboard interaction the app
    supports - opened from Help > Controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Controls")
        self.resize(520, 620)

        layout = QVBoxLayout(self)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(False)
        browser.setHtml(_CONTROLS_HTML)
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)
