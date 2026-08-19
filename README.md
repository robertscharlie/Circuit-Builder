# Circuit Builder

A desktop app for sketching electrical circuit schematics: drag components
onto a canvas, wire them together, and save the result. Built with Python
and [PySide6](https://doc.qt.io/qtforpython-6/) (Qt).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # on Windows
pip install -r requirements.txt
python main.py
```

## Features

- **Resistor, battery, capacitor, inductor, bulb, and switch** components
  with proper schematic symbols, plus a plain **Node** for junctions/taps.
  Place any of them with a shortcut key (`R` `B` `C` `I` `L` `S` `N`) - a
  ghost preview follows the cursor, `R` rotates it before you click, `Esc`
  cancels. A **Switch** starts open - click a placed one (no drag) to flip
  it, and watch a **Bulb** light up live if Simulate is running.
- **Wiring**: drag between two terminals to connect them. Drop one terminal
  onto another (or, for a diagonal wire, close enough to it) and they
  auto-connect, or onto an existing wire's line to tap into it - no
  separate wiring step either way, and it works for every component
  including a Node dragging a fresh wire out of its only terminal. Drop a
  component with both its terminals landing on that same wire and it's
  spliced directly into it instead - the wire is deleted and rewired
  through the component, so it actually sits in the circuit rather than
  just shorting it out in parallel.
- **Splitting and merging**: right-click a wire to insert a Node partway
  along it; drag a Node onto a terminal (or a terminal onto a Node) and it
  merges away, reconnecting its wires directly. Right-click a wire and
  choose **Split and Move** instead to do both in one step - it splits the
  wire and immediately hands the new Node to the cursor (same as picking
  Move afterward separately), so you can drop it wherever it actually needs
  to go without a second right-click.
- **Moving things**: drag a component's body, or right-click it and choose
  Move to have it follow the cursor instead. Wires stay attached and follow
  along. A terminal's wire can be detached onto a free Node the same way.
- **Editing**: double-click a component to rename it or change its value.
  Undo/redo covers every action, including moves, wiring, and switch flips.
  Renaming a Node gives its whole electrical point a real name (e.g.
  "Vout") - picked up automatically by Frequency Response's Output list
  below instead of an auto-numbered "Node 3: ...".
- **Simulate** (`F5`): starts a *live* simulation and shows the voltage at
  every terminal - wires carry that voltage along their whole length, since
  both ends are electrically the same node. It keeps running on its own
  (no need to touch anything), and any edit also refreshes it immediately.
  A **Capacitor** and an **Inductor** both genuinely evolve over real time
  while it runs (backward-Euler integration, not just a DC snapshot) - and
  behave as opposites of each other. Build a switch + capacitor + bulb
  circuit (bulb in parallel with the capacitor) and watch the bulb fade out
  over a few seconds as the capacitor drains through it after the switch
  opens, tracing a real RC decay curve. Build a switch + inductor + bulb
  circuit (all in series) instead and the bulb stays dark right as the
  switch closes - the inductor blocks the sudden current - then brightens
  smoothly as current builds up, tracing a real L/R curve. Switches are a
  wire-or-break depending on their state. Click Stop (or press `F5` again)
  to end it.
- **Frequency Response**: right-click any terminal and choose "Frequency
  Response...", or open it with no terminal preselected from the toolbar
  button or Simulate menu, for a Bode plot - magnitude in dB and phase in
  degrees, both vs a log-scaled frequency axis. It opens as a panel docked
  into the same window (right next to the canvas, not a popup blocking it)
  with a float button in its title bar to pop it out into its own window
  whenever you want it separate - drag it back to re-dock, or just close it,
  either way it's remembered and reused the next time you ask for it rather
  than piling up new copies. Has explicit **Input** and **Output** dropdowns
  rather than baking in assumptions: Input picks which battery is the swept
  AC excitation (any others are AC-shorted, the standard small-signal
  convention), Output picks which *electrical node* is probed - terminals
  wired together are grouped into one clearly labeled entry (e.g.
  `Node 3: R1 terminal 1, C1 terminal 0`, or just `Vout (...)` if you've
  renamed a Node placed there) instead of listing every terminal separately
  and letting two identical-valued entries look like different choices -
  and an explanation line spells out what's actually being varied, what the
  input/output are, and that the 0V reference for the sweep is the *chosen*
  Input battery's negative terminal (it moves with whichever one you pick,
  unlike Simulate which always references the first battery) - both are
  changeable at any time, and since the panel isn't modal you can keep
  editing the circuit while it's open; click Replot to also pick up any
  structural changes (new/renamed/removed components), not just re-sweep.
  Resistors stay purely real, capacitors/inductors become complex impedances
  (`1/(jwC)`, `jwL`). Every terminal belonging to the probed node is
  highlighted with a green ring on the canvas for as long as the panel
  stays visible. The plot itself is one big chart with **Magnitude** and
  **Phase** tabs above it rather than two small stacked ones - switching
  is instant (no re-sweep, just a re-draw of the already-solved data), and
  hovering over it reads out both the magnitude and phase at that
  frequency together, with a crosshair, no matter which tab is showing.
  The initial sweep
  range is auto-suggested from the circuit's own R/L/C values (bracketing
  every R-C/R-L corner and L-C resonance actually present) instead of a
  fixed window that could easily miss a filter's interesting behavior -
  adjust it and hit Replot to zoom in/out further. Try it on a resistor +
  capacitor in series (probe across the capacitor) for a classic low-pass
  roll-off.
- **Save/open** circuits as plain JSON, with a few example circuits included
  in `example files/` to explore or build on.
- **Zoom, pan, and a full keyboard/mouse reference** (`Help > Controls`, or
  `F1`) for everything above.

## Running tests

`tests/` has standalone assertion scripts (not pytest) covering wiring,
undo/redo, save/load, placement mode, and the interactions above. Run them
all with:

```bash
python tests/run_all.py
```

or run any single script directly, e.g. `python tests/smoke_test.py`.

## Project layout

```
main.py                          entry point, applies the app theme
circuit_builder/
  core/
    components.py                component type metadata (name, unit, default value, shortcut)
    circuit_model.py             Qt-free Circuit/ComponentData/WireData + JSON save/load
    simulation.py                 Qt-free nodal analysis (MNA) solver behind Simulate - DC steady state, and a backward-Euler transient mode for capacitor charge/discharge and inductor current ramp-up/freewheel
    ac_simulation.py               Qt-free complex-valued MNA solver behind Frequency Response - sweeps a frequency range for a Bode plot
  ui/
    component_item.py            draggable/rotatable QGraphicsItem, draws each symbol + icons
    terminal_item.py             connection-point dot on a component
    wire_item.py                 line connecting two terminals, follows them when moved
    canvas.py                    CircuitScene (grid) + CircuitView (drag-drop, wiring, zoom/pan, placement mode)
    palette.py                   sidebar list of draggable component types
    edit_dialog.py                popup for editing a component's label/value
    help_dialog.py                Help > Controls reference dialog
    simulation_overlay.py         voltage-label pills drawn on the canvas by Simulate
    bode_dialog.py                 matplotlib-backed Bode plot panel (docked/floatable) behind Frequency Response
    commands.py                   QUndoCommand classes backing undo/redo
    icons.py                      hand-drawn toolbar icons (no external assets)
    theme.py                      app-wide QSS stylesheet
    main_window.py               menus, toolbar, shortcuts, file I/O, save-prompt, wires everything together
tests/                           standalone assertion scripts (see "Running tests" above)
```

`core/` has no Qt imports on purpose - it's the plain-data model (components,
their values, and which terminals are wired to which). That's the layer a
future analysis engine should build on.

## Roadmap

Not yet implemented, but planned:

- A proper **ground/reference symbol** - Simulate currently defaults 0V to
  the first battery's negative terminal since there's no dedicated component
  for it yet.
- **Current** readouts (not just voltage), and highlighting a shorted or
  unconnected branch directly on the canvas rather than just a status-bar
  warning.
- Multi-select value editing, copy/paste, and right-angle wire routing.
- Packaging into a standalone `.exe` once the feature set settles.

## Acknowledgements

Designed and built by me - the component/wiring model, every feature, and
the UX decisions were mine. I used an AI coding assistant along the way to
help with implementation and save time (writing PySide6 code from those
decisions, tracking down bugs, expanding the test suite).
