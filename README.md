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

- **Resistor, battery, capacitor, and inductor** components with proper
  schematic symbols, plus a plain **Node** for junctions/taps. Place any of
  them with a shortcut key (`R` `B` `C` `I` `N`) - a ghost preview follows
  the cursor, `R` rotates it before you click, `Esc` cancels.
- **Wiring**: drag between two terminals to connect them. Drop one terminal
  exactly onto another and they auto-connect - no separate wiring step.
- **Splitting and merging**: right-click a wire to insert a Node partway
  along it; drag a Node onto a terminal (or a terminal onto a Node) and it
  merges away, reconnecting its wires directly.
- **Moving things**: drag a component's body, or right-click it and choose
  Move to have it follow the cursor instead. Wires stay attached and follow
  along. A terminal's wire can be detached onto a free Node the same way.
- **Editing**: double-click a component to rename it or change its value.
  Undo/redo covers every action, including moves and wiring.
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
  ui/
    component_item.py            draggable/rotatable QGraphicsItem, draws each symbol + icons
    terminal_item.py             connection-point dot on a component
    wire_item.py                 line connecting two terminals, follows them when moved
    canvas.py                    CircuitScene (grid) + CircuitView (drag-drop, wiring, zoom/pan, placement mode)
    palette.py                   sidebar list of draggable component types
    edit_dialog.py                popup for editing a component's label/value
    help_dialog.py                Help > Controls reference dialog
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

- **Nodal analysis (DC solve)**: walk `Circuit.wires` to group terminals into
  electrical nodes and solve for node voltages (modified nodal analysis, to
  handle ideal voltage sources). The Node component is exactly the kind of
  junction this will need to resolve.
- **Frequency-domain analysis**: extend that to complex impedances and sweep
  frequency for Bode plots, via `matplotlib`.
- A ground/reference symbol, short-circuit/unconnected-terminal warnings,
  multi-select value editing, copy/paste, and right-angle wire routing.
- Packaging into a standalone `.exe` once the feature set settles.

## Acknowledgements

I designed the app end to end - the component/wiring model, every feature,
and the UX decisions above - and used Claude as an AI pair-programmer along
the way: turning those decisions into working PySide6 code, tracking down
Qt-specific bugs, and helping expand the test suite.
