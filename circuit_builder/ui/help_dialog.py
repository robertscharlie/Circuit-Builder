from __future__ import annotations

from PySide6.QtCore import Qt
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
    <code>C</code> Capacitor, <code>I</code> Inductor, <code>N</code> Node.</li>
  <li>Pressing a shortcut key drops the canvas into placement mode - a ghost
    symbol follows the cursor until you click to place it.</li>
  <li>While placing, press <code>R</code> again to rotate the ghost, or
    <code>Esc</code> to cancel.</li>
</ul>

<h3>Wiring</h3>
<ul>
  <li>Click and drag from one terminal (the small dot at the end of a
    component's leads) to another terminal.</li>
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
</ul>

<h3>Right-click menus</h3>
<ul>
  <li><b>On a wire</b> - <i>Split Wire Here</i> inserts a Node at the
    nearest grid point, splitting the wire in two.</li>
  <li><b>On a component or Node</b> - <i>Move</i> lets you relocate it by
    clicking its new spot instead of dragging.</li>
  <li><b>On a wired terminal</b> - <i>Move Node</i> detaches that wire onto
    a new free Node, disconnecting it from the component so it can be
    dragged elsewhere.</li>
</ul>

<h3>Auto-connect</h3>
<ul>
  <li>Ending a move with a terminal sitting exactly on top of another one
    wires them together automatically.</li>
  <li>If either side is a Node, it merges away instead: the Node is deleted
    and its wire(s) are rewired straight to the other terminal. This works
    whichever side you dragged.</li>
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
