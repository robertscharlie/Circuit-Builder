# Circuit Builder

A desktop app for sketching electrical circuit schematics: drag components onto a canvas, wire them up, and simulate them. Built with Python and [PySide6](https://doc.qt.io/qtforpython-6/).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # on Windows
pip install -r requirements.txt
python main.py
```

## Features

- **Components** - resistor, battery, capacitor, inductor, bulb, switch, and a bare Node for junctions. Place one with its shortcut key (`R` `B` `C` `I` `L` `S` `N`) or by clicking it in the sidebar - both drop you into a placement mode where a ghost follows the cursor, `R` rotates it, click to drop, `Esc` cancels. Dragging from the sidebar instead works too, it just can't be rotated mid-drag. Switches start open and toggle with a click; bulbs glow live under Simulate.
- **Wiring** - drag between two terminals to connect them, drop onto an existing wire to tap into it, or land both terminals of a component on the same wire to splice it in. Right-click a wire to split it, or to split-and-move in one step.
- **Moving and merging** - drag a component, or right-click it for a "follow the cursor" move. Drop a Node onto a terminal (or the reverse) and it merges away, rewiring directly.
- **Undo/redo** covers everything. Double-click a component to rename or revalue it - renaming a Node carries its name into the Frequency Response node list instead of an auto-generated one.
- **Simulate** (`F5`) - live DC solve, voltage shown at every terminal, refreshing as you edit. Capacitors and inductors charge/discharge over real time rather than snapping to steady state.
- **Frequency Response** - a Bode plot panel, docked into the main window or popped out into its own, opened from a terminal's right-click menu, the toolbar, or the Simulate menu. Choose which battery drives the sweep and which node to probe, flip between magnitude and phase, hover for exact readings. The sweep range is guessed from the circuit's own R/L/C values to begin with.
- **Save/open** as plain JSON. A few example circuits live in `example_files/`.
- Zoom, pan, and a full shortcut reference under Help > Controls (`F1`).

## Running tests

Standalone assertion scripts, not pytest:

```bash
python tests/run_all.py
```

or run one directly, e.g. `python tests/smoke_test.py`.

## Project layout

```
main.py                           entry point, applies the app theme
circuit_builder/
  core/
    components.py                 component type metadata (name, unit, default value, shortcut)
    circuit_model.py              Circuit/ComponentData/WireData + JSON save/load
    simulation.py                 DC nodal analysis behind Simulate, plus transient charge/discharge
    ac_simulation.py              complex-valued nodal analysis behind Frequency Response
  ui/
    component_item.py             draggable/rotatable QGraphicsItem, draws each symbol
    terminal_item.py              connection-point dot on a component
    wire_item.py                  line connecting two terminals, follows them when moved
    canvas.py                     the scene/view: drag-drop, wiring, zoom/pan, placement mode
    palette.py                    sidebar list of components
    edit_dialog.py                rename/revalue popup
    help_dialog.py                Help > Controls reference
    simulation_overlay.py         voltage labels drawn during Simulate
    bode_dialog.py                the Bode plot panel behind Frequency Response
    commands.py                   undo/redo command classes
    icons.py                      hand-drawn toolbar icons
    theme.py                      app-wide stylesheet
    main_window.py                menus, toolbar, shortcuts, file I/O, wires everything together
tests/                            standalone assertion scripts (see above)
```

`core/` has no Qt imports on purpose - it's the plain-data model, kept separate from the UI.

## Roadmap

- A proper ground symbol (0V currently defaults to the first battery's negative terminal).
- Current readouts, and highlighting a shorted/unconnected branch on the canvas.
- Multi-select editing, copy/paste, right-angle wire routing.
- A packaged standalone `.exe` once things settle.

## Acknowledgements

Designed and built by me - the model, the features, the UX calls were mine. Used an AI coding assistant along the way to speed up the implementation and chase down bugs.
