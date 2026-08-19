from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
from PySide6.QtWidgets import QDockWidget, QFileDialog, QMainWindow, QMessageBox, QStatusBar, QToolBar

from circuit_builder.core.circuit_model import Circuit, ComponentData, TerminalRef, WireData
from circuit_builder.core.components import COMPONENT_TYPES
from circuit_builder.core.simulation import TransientState, simulate
from circuit_builder.ui.canvas import CircuitScene, CircuitView
from circuit_builder.ui.commands import (
    AddComponentCommand,
    AddWireCommand,
    ConnectTerminalToWireCommand,
    DeleteSelectionCommand,
    DetachTerminalCommand,
    EditComponentCommand,
    MergeNodeIntoTerminalCommand,
    MoveComponentsCommand,
    RotateComponentsCommand,
    SpliceComponentIntoWireCommand,
    SplitWireCommand,
    ToggleSwitchCommand,
)
from circuit_builder.ui.bode_dialog import BodePanel
from circuit_builder.ui.component_item import ComponentItem, GRID_SIZE, JUNCTION_TYPE
from circuit_builder.ui.help_dialog import ControlsHelpDialog
from circuit_builder.ui import icons
from circuit_builder.ui.palette import ComponentPalette
from circuit_builder.ui.simulation_overlay import VoltageLabelItem
from circuit_builder.ui.terminal_item import TerminalItem, terminals_already_wired
from circuit_builder.ui.wire_item import WireItem

SCENE_EXTENT = 3000
# How often a live simulation re-solves the circuit on its own, with no user
# interaction - what makes a capacitor's charge/discharge visibly animate
# instead of only updating on the next edit.
SIM_TICK_MS = 150
# Used for an "instant" refresh (e.g. right after an edit) instead of a real
# tick - small enough that a capacitor's charge doesn't perceptibly move,
# but a genuine (if tiny) time step rather than a hard voltage-source pin,
# which would risk a singular/contradictory system - see simulation.py.
INSTANT_DT = 1e-6


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Circuit Builder")
        self.resize(1150, 720)

        self.scene = CircuitScene(-SCENE_EXTENT, -SCENE_EXTENT, SCENE_EXTENT * 2, SCENE_EXTENT * 2, self)
        self.view = CircuitView(self.scene, self)
        self.setCentralWidget(self.view)

        self.undo_stack = QUndoStack(self)

        self.view.component_dropped.connect(self._on_component_dropped)
        self.view.wire_created.connect(self._on_wire_created)
        self.view.components_moved.connect(self._on_components_moved)
        self.view.wire_split_requested.connect(self._on_wire_split_requested)
        self.view.wire_split_and_move_requested.connect(self._on_wire_split_and_move_requested)
        self.view.terminal_detach_requested.connect(self._on_terminal_detach_requested)
        self.view.wire_tap_requested.connect(self._on_wire_tap_requested)
        self.view.frequency_response_requested.connect(self._on_frequency_response_requested)

        palette = ComponentPalette(self)
        palette.component_picked.connect(self.view.start_placement)
        palette_dock = QDockWidget("Components", self)
        palette_dock.setWidget(palette)
        palette_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, palette_dock)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage(
            "Drag components or press R/B/C/I/L/S/N to place one (Resistor/Battery/Capacitor/Inductor/"
            "Bulb/Switch/Node) - while placing, press R to rotate it, click to drop. Click a placed "
            "switch to flip it open/closed. "
            "Drag between terminal dots to wire them - drop on an existing wire's line to tap into it, or "
            "Shift+drag a terminal to move its component instead. "
            "Right-click a wire, component, or a wired terminal for more options (split a wire, move a "
            "component by clicking its new spot instead of dragging, or detach a wired terminal onto its "
            "own Node). Ending a move with a terminal on another terminal auto-wires them, or on a wire's "
            "line taps into it - if either side is a Node, it merges away instead, rewiring its connections "
            "straight to the other terminal. "
            "Double-click to edit, Delete to remove, Ctrl+R to rotate a selection. "
            "Scroll to zoom, middle-drag or the Pan Tool (H) to move around. "
            "Press Simulate (F5) to solve the circuit live and show the DC voltage at every terminal - "
            "press it again (or Stop) to end the live simulation."
        )

        self._counters = {key: 0 for key in COMPONENT_TYPES}
        self._current_path: Path | None = None
        self._simulation_labels: list[VoltageLabelItem] = []
        self._simulation_active = False
        self._transient_state: TransientState | None = None
        self._probe_highlight_terminals: list[TerminalItem] = []
        self._bode_panel: BodePanel | None = None
        self._bode_dock: QDockWidget | None = None
        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(SIM_TICK_MS)
        self._sim_timer.timeout.connect(self._on_sim_tick)

        self._build_toolbar()
        self._build_component_shortcuts()
        self._build_menu()

        self.undo_stack.cleanChanged.connect(lambda _clean: self._update_title())
        # Every mutation in this app goes through the undo stack, so this one
        # hook is enough to catch moves, wiring, value edits, switch toggles,
        # etc. - and re-run a live simulation to reflect them.
        self.undo_stack.indexChanged.connect(lambda _index: self._on_circuit_changed())
        self._update_title()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setIconSize(QSize(icons.SIZE, icons.SIZE))
        self.addToolBar(toolbar)

        self._undo_action = self.undo_stack.createUndoAction(self, "Undo")
        self._undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo_action.setIcon(icons.undo_icon())
        self._redo_action = self.undo_stack.createRedoAction(self, "Redo")
        self._redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo_action.setIcon(icons.redo_icon())
        toolbar.addAction(self._undo_action)
        toolbar.addAction(self._redo_action)
        toolbar.addSeparator()

        pan_tool_action = QAction(icons.pan_icon(), "Pan Tool", self)
        pan_tool_action.setCheckable(True)
        pan_tool_action.setShortcut("H")
        pan_tool_action.setToolTip("Pan Tool (H) - left-drag to move the camera")
        pan_tool_action.toggled.connect(self.view.set_pan_tool_active)
        toolbar.addAction(pan_tool_action)
        toolbar.addSeparator()
        self._pan_tool_action = pan_tool_action

        zoom_in_action = QAction(icons.zoom_in_icon(), "Zoom In", self)
        zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_action.triggered.connect(self.view.zoom_in)
        toolbar.addAction(zoom_in_action)

        zoom_out_action = QAction(icons.zoom_out_icon(), "Zoom Out", self)
        zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_action.triggered.connect(self.view.zoom_out)
        toolbar.addAction(zoom_out_action)

        fit_action = QAction(icons.fit_to_view_icon(), "Fit to View", self)
        fit_action.setShortcut("Ctrl+0")
        fit_action.triggered.connect(self.view.zoom_to_fit)
        toolbar.addAction(fit_action)

        reset_zoom_action = QAction(icons.reset_zoom_icon(), "Reset Zoom", self)
        reset_zoom_action.setShortcut("Ctrl+1")
        reset_zoom_action.triggered.connect(self.view.reset_zoom)
        toolbar.addAction(reset_zoom_action)

        self._zoom_in_action = zoom_in_action
        self._zoom_out_action = zoom_out_action
        self._fit_action = fit_action
        self._reset_zoom_action = reset_zoom_action

        toolbar.addSeparator()
        simulate_action = QAction(icons.simulate_icon(), "Simulate", self)
        simulate_action.setCheckable(True)
        simulate_action.setShortcut("F5")
        simulate_action.setToolTip(
            "Simulate (F5) - solve the circuit and show the DC voltage at every terminal"
        )
        simulate_action.toggled.connect(self._on_simulate_toggled)
        toolbar.addAction(simulate_action)
        self._simulate_action = simulate_action

        frequency_response_action = QAction(icons.frequency_response_icon(), "Frequency Response...", self)
        frequency_response_action.setToolTip(
            "Frequency Response - open a Bode plot; pick which source to sweep (Input) and which node to "
            "probe (Output) from dropdowns in the panel"
        )
        frequency_response_action.triggered.connect(self._show_frequency_response_panel)
        toolbar.addAction(frequency_response_action)
        self._frequency_response_action = frequency_response_action

    def _build_component_shortcuts(self) -> None:
        """One QAction per component type: pressing its shortcut key drops the
        canvas into placement mode (a ghost symbol follows the cursor until
        the next click), so a component can be placed without touching the
        palette at all."""
        self._placement_actions: list[QAction] = []
        for comp_type, meta in COMPONENT_TYPES.items():
            action = QAction(f"Place {meta.display_name}", self)
            action.setShortcut(meta.shortcut)
            action.triggered.connect(lambda checked=False, t=comp_type: self.view.start_placement(t))
            self.addAction(action)  # window-wide shortcut even with no menu/toolbar home
            self._placement_actions.append(action)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_circuit)
        file_menu.addAction(new_action)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_circuit)
        file_menu.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_circuit)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_circuit_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self._undo_action)
        edit_menu.addAction(self._redo_action)
        edit_menu.addSeparator()

        delete_action = QAction("Delete Selected", self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.triggered.connect(self.delete_selected)
        edit_menu.addAction(delete_action)

        rotate_action = QAction("Rotate Selected", self)
        rotate_action.setShortcut("Ctrl+R")
        rotate_action.triggered.connect(self.rotate_selected)
        edit_menu.addAction(rotate_action)

        split_wire_action = QAction("Split Wire", self)
        split_wire_action.setToolTip("Select a single wire, then split it in two with a Node at its midpoint")
        split_wire_action.triggered.connect(self.split_selected_wire)
        edit_menu.addAction(split_wire_action)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self._pan_tool_action)
        view_menu.addSeparator()
        view_menu.addAction(self._zoom_in_action)
        view_menu.addAction(self._zoom_out_action)
        view_menu.addAction(self._fit_action)
        view_menu.addAction(self._reset_zoom_action)

        components_menu = self.menuBar().addMenu("&Components")
        for action in self._placement_actions:
            components_menu.addAction(action)

        simulate_menu = self.menuBar().addMenu("&Simulate")
        simulate_menu.addAction(self._simulate_action)
        simulate_menu.addSeparator()
        simulate_menu.addAction(self._frequency_response_action)

        help_menu = self.menuBar().addMenu("&Help")
        controls_action = QAction("Controls...", self)
        controls_action.setShortcut("F1")
        controls_action.triggered.connect(self.show_controls_help)
        help_menu.addAction(controls_action)

    def show_controls_help(self) -> None:
        ControlsHelpDialog(self).exec()

    # --- simulation ---------------------------------------------------
    #
    # "Simulate" starts a live session, not a one-shot snapshot: a QTimer
    # (_sim_timer) keeps re-solving on its own every SIM_TICK_MS, advancing
    # a TransientState's capacitor charge one step (backward-Euler) each
    # time - this is what makes an RC charge/discharge curve visibly
    # animate with no user interaction at all. Any edit (move, wire, toggle
    # a switch, undo/redo, ...) - all of which go through the undo stack -
    # ALSO refreshes immediately via _on_circuit_changed(), but as an
    # instantaneous snapshot at the capacitor's current charge rather than
    # advancing the clock, so e.g. flipping a switch updates at once without
    # skipping ahead in time. It only stops when the user explicitly clicks
    # Stop, or the circuit itself goes away (New/Open).

    def _on_simulate_toggled(self, checked: bool) -> None:
        if checked:
            self._simulate_action.setIcon(icons.stop_icon())
            self._simulate_action.setText("Stop Simulation")
            self._simulate_action.setToolTip("Stop Simulation (F5) - stop the live simulation")
            self._transient_state = TransientState()  # every capacitor starts uncharged, t=0
            if self._refresh_simulation(dt=INSTANT_DT):
                self._sim_timer.start()
            else:
                self._simulate_action.setChecked(False)  # nothing to simulate - bail back out
        else:
            self._simulate_action.setIcon(icons.simulate_icon())
            self._simulate_action.setText("Simulate")
            self._simulate_action.setToolTip(
                "Simulate (F5) - solve the circuit live and show the DC voltage at every terminal"
            )
            self._sim_timer.stop()
            self._clear_simulation_visuals()
            self._simulation_active = False
            self._transient_state = None

    def _on_sim_tick(self) -> None:
        """Fires every SIM_TICK_MS while a simulation is running - advances
        simulated time so a capacitor's charge keeps animating even with no
        user interaction."""
        try:
            if not self._refresh_simulation(dt=SIM_TICK_MS / 1000.0):
                # The circuit went empty out from under a running simulation
                # (e.g. everything got deleted) - bail out the same way
                # starting Simulate on an empty canvas does, instead of
                # leaving the toolbar stuck on "Stop Simulation" while the
                # timer quietly keeps polling an empty circuit.
                self._simulate_action.setChecked(False)
        except RuntimeError:
            self._sim_timer.stop()  # window torn down mid-tick

    def _on_circuit_changed(self) -> None:
        """Hooked to undo_stack.indexChanged - every undoable edit runs
        through here. Only acts while a simulation is actively running."""
        if not self._simulation_active:
            return
        try:
            if not self._refresh_simulation(dt=INSTANT_DT):
                self._simulate_action.setChecked(False)
        except RuntimeError:
            return  # indexChanged fired while the window was being torn down

    def _refresh_simulation(self, dt: float) -> bool:
        """Re-solves the circuit - advancing any capacitor's charge by `dt`
        of simulated time (pass INSTANT_DT for an effectively-instant
        refresh after an edit, rather than a real tick) - and redraws the
        voltage labels + bulb glow from scratch. Returns False (and leaves
        nothing on screen) if there's nothing to simulate."""
        circuit = self._build_circuit_model()
        result = simulate(circuit, dt=dt, state=self._transient_state)
        self._clear_simulation_visuals()

        if result is None:
            self.statusBar().showMessage("Nothing to simulate - add some components first.", 4000)
            self._simulation_active = False
            return False

        # A bulb's glow is scaled against the largest battery voltage in the
        # circuit, so it reads as "full brightness" at the supply voltage
        # and dims smoothly below that (e.g. as a capacitor discharges
        # through it) rather than snapping on/off.
        battery_values = [abs(c.value) for c in circuit.components if c.type == "battery" and c.value]
        brightness_reference = max(battery_values) if battery_values else 5.0

        for item in self.scene.items():
            if isinstance(item, ComponentItem):
                if item.component_type == "lamp":
                    v0 = result.voltage_at(item.id, 0)
                    v1 = result.voltage_at(item.id, 1)
                    drop = abs(v0 - v1) if v0 is not None and v1 is not None else 0.0
                    item.brightness = max(0.0, min(1.0, drop / brightness_reference))
                    item.update()
                for terminal in item.terminals:
                    voltage = result.voltage_at(item.id, terminal.index)
                    label = VoltageLabelItem(voltage, terminal.scenePos())
                    self.scene.addItem(label)
                    self._simulation_labels.append(label)

        self._simulation_active = True
        if result.warnings:
            self.statusBar().showMessage(" | ".join(result.warnings), 8000)
        else:
            self.statusBar().showMessage(
                "Simulating live - voltage shown at every terminal, and any capacitor's charge evolves "
                "in real time. Reference (0V) is the first battery's negative terminal. Click Stop (F5) "
                "to end it.",
                6000,
            )
        return True

    def _clear_simulation_visuals(self) -> None:
        """Removes the voltage labels and un-lights any bulbs, without
        touching _simulation_active or the toolbar button - used both when
        stopping outright and as the first step of every live refresh."""
        for label in self._simulation_labels:
            self.scene.removeItem(label)
        self._simulation_labels.clear()
        for item in self.scene.items():
            if isinstance(item, ComponentItem) and item.component_type == "lamp" and item.brightness:
                item.brightness = 0.0
                item.update()

    def _stop_simulation(self) -> None:
        """Used by New/Open, which replace the circuit out from under any
        running simulation - stops it via the same path a manual Stop click
        would take, so the icon/tooltip/labels/timer all reset together."""
        if self._simulate_action.isChecked():
            self._simulate_action.setChecked(False)
        else:
            self._sim_timer.stop()
            self._clear_simulation_visuals()
            self._simulation_active = False
            self._transient_state = None

    def _on_switch_toggle_requested(self, component: ComponentItem) -> None:
        self.undo_stack.push(ToggleSwitchCommand(component))

    # --- component / wire management ------------------------------------

    def _create_component(
        self,
        comp_type: str,
        scene_pos: QPointF,
        label: str | None = None,
        value: float | None = None,
        component_id: str | None = None,
        closed: bool | None = None,
    ) -> ComponentItem:
        """Builds and configures a component but does not add it to the
        scene - used by AddComponentCommand so redo()/undo() can toggle its
        presence without re-running label auto-numbering each time."""
        if label is None:
            self._counters[comp_type] += 1
            label = f"{COMPONENT_TYPES[comp_type].prefix}{self._counters[comp_type]}"
        item = ComponentItem(comp_type, value=value, label=label, component_id=component_id, closed=closed)
        item.setPos(scene_pos)
        item.edit_requested.connect(self._on_component_edit_requested)
        item.toggle_requested.connect(self._on_switch_toggle_requested)
        return item

    def add_component(
        self,
        comp_type: str,
        scene_pos: QPointF,
        label: str | None = None,
        value: float | None = None,
        component_id: str | None = None,
        closed: bool | None = None,
    ) -> ComponentItem:
        """Creates a component and adds it straight to the scene, bypassing
        the undo stack. Used for loading a file, not for user-driven adds
        (those go through AddComponentCommand so they're undoable)."""
        item = self._create_component(
            comp_type, scene_pos, label=label, value=value, component_id=component_id, closed=closed
        )
        self.scene.addItem(item)
        return item

    def _on_component_dropped(self, comp_type: str, scene_pos: QPointF, rotation: float = 0.0) -> None:
        # A freshly placed component (dragged from the palette, or dropped
        # via a keyboard-shortcut placement) gets the same auto-connect/
        # splice treatment as one that just finished being moved (see
        # _auto_connect_or_merge) - landing it on a terminal or a wire
        # should wire it in immediately, not only on a later drag.
        self.undo_stack.beginMacro(f"Add {COMPONENT_TYPES[comp_type].display_name}")
        command = AddComponentCommand(self, comp_type, scene_pos, rotation)
        self.undo_stack.push(command)
        self._auto_connect_or_merge(command.item)
        self.undo_stack.endMacro()

    def _on_wire_created(self, wire: WireItem) -> None:
        self.undo_stack.push(AddWireCommand(self, wire))

    def _on_wire_split_requested(self, wire: WireItem, scene_pos: QPointF) -> None:
        self.undo_stack.push(SplitWireCommand(self, wire, scene_pos))

    def _on_wire_split_and_move_requested(self, wire: WireItem, scene_pos: QPointF) -> None:
        """"Split and Move": same split as above, but the new Node is
        immediately handed to move-mode (follows the cursor until the next
        click) instead of staying put - for when you already know it needs
        repositioning, skipping the separate drag/Move step."""
        command = SplitWireCommand(self, wire, scene_pos)
        self.undo_stack.push(command)
        self.view.start_move_component(command.node)

    def _on_wire_tap_requested(self, start_terminal: TerminalItem, wire: WireItem, scene_pos: QPointF) -> None:
        """A wire dragged out from `start_terminal` (the natural gesture for
        a Node, which has no body to drag - see Shift+drag) was dropped onto
        an existing wire instead of a terminal - split that wire with a
        Node at scene_pos, same as a manual "Split Wire Here", then wire
        start_terminal to the new Node, as one undo step."""
        self.undo_stack.beginMacro("Connect to wire")
        split_command = SplitWireCommand(self, wire, scene_pos)
        self.undo_stack.push(split_command)
        self.undo_stack.push(AddWireCommand(self, WireItem(start_terminal, split_command.node.terminals[0])))
        self.undo_stack.endMacro()

    def _on_frequency_response_requested(self, terminal: TerminalItem) -> None:
        """Right-click "Frequency Response..." on a terminal - opens the
        Bode panel with that terminal preselected as the Output (probe)."""
        component = terminal.component()
        self._open_bode_panel(component.id, terminal.index)

    def _show_frequency_response_panel(self) -> None:
        """Simulate menu / toolbar button - opens the Bode panel without a
        right-clicked terminal to start from. Defaults Output to the first
        non-battery component's terminal 0 (probing a battery's own
        terminal is a poor starting point - it always reads a flat unity
        gain, since it IS the excitation); falls back to whatever's there
        if the circuit is nothing but batteries. The panel's own dropdowns
        let the user redirect either Input or Output from here."""
        circuit = self._build_circuit_model()
        if not circuit.components:
            self.statusBar().showMessage("Nothing to analyze - add some components first.", 4000)
            return
        default = next((c for c in circuit.components if c.type != "battery"), circuit.components[0])
        self._open_bode_panel(default.id, 0)

    def _open_bode_panel(self, probe_component_id: str, probe_terminal_index: int) -> None:
        """Shared by every entry point above. The panel lives in a dock
        widget docked into this same window - Qt's own dock chrome already
        gives it a "float into its own window" button and lets it be
        dragged out, so repeated requests reuse the same instance (via
        set_probe()) rather than creating a new one each time, and just
        show/raise it if it's already open somewhere."""
        if self._bode_panel is None:
            self._bode_panel = BodePanel(
                self._build_circuit_model,
                probe_component_id,
                probe_terminal_index,
                on_probe_changed=self._set_probe_highlight,
            )
            self._bode_panel.title_changed.connect(self._on_bode_title_changed)
            self._bode_dock = QDockWidget(self._bode_panel.title(), self)
            self._bode_dock.setObjectName("bodeDock")
            self._bode_dock.setWidget(self._bode_panel)
            self._bode_dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
            self._bode_dock.visibilityChanged.connect(self._on_bode_visibility_changed)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._bode_dock)
            self.resizeDocks([self._bode_dock], [620], Qt.Orientation.Horizontal)
        else:
            self._bode_panel.set_probe(probe_component_id, probe_terminal_index)
        self._bode_dock.setVisible(True)
        self._bode_dock.raise_()

    def _on_bode_title_changed(self, title: str) -> None:
        if self._bode_dock is not None:
            self._bode_dock.setWindowTitle(title)

    def _on_bode_visibility_changed(self, visible: bool) -> None:
        """Keeps the canvas highlight in sync with whether the panel is
        actually on screen - lit while it's visible (docked or floating),
        cleared the moment it's hidden (closed), whichever probed node it
        was last showing."""
        if visible and self._bode_panel is not None:
            group = self._bode_panel.output_combo.currentData()
            if group:
                self._set_probe_highlight(group)
        else:
            self._clear_probe_highlight()

    def _find_terminal_item(self, component_id: str, terminal_index: int) -> TerminalItem | None:
        for item in self.scene.items():
            if isinstance(item, ComponentItem) and item.id == component_id:
                return item.terminals[terminal_index]
        return None

    def _set_probe_highlight(self, terminals: list[tuple[str, int]]) -> None:
        """Highlights every terminal in `terminals` - a whole electrical
        node's worth (see BodeDialog's Output list, which groups terminals
        by node), not just one dot, since they're all the same electrical
        point and should read that way on the canvas too."""
        self._clear_probe_highlight()
        found = [t for t in (self._find_terminal_item(cid, idx) for cid, idx in terminals) if t is not None]
        for terminal in found:
            terminal.set_probed(True)
        self._probe_highlight_terminals = found

    def _clear_probe_highlight(self) -> None:
        for terminal in self._probe_highlight_terminals:
            terminal.set_probed(False)
        self._probe_highlight_terminals = []

    def _on_terminal_detach_requested(self, terminal, scene_pos: QPointF) -> None:
        command = DetachTerminalCommand(self, terminal, scene_pos)
        self.undo_stack.push(command)
        # The new Node starts out exactly where the terminal was, still
        # holding the detached wire(s) - immediately hand it to move-mode so
        # the user can drag it to wherever it's actually needed.
        self.view.start_move_component(command.node)

    def _on_components_moved(self, moves: list) -> None:
        # Grouped into one undo step even when it also auto-wires/merges - a
        # macro with a single child command behaves just like a plain push,
        # so this is safe to do unconditionally.
        self.undo_stack.beginMacro("Move" if len(moves) == 1 else "Move components")
        self.undo_stack.push(MoveComponentsCommand(moves))
        for component, _old_pos, _new_pos in moves:
            self._auto_connect_or_merge(component)
        self.undo_stack.endMacro()

    def _auto_connect_or_merge(self, component: ComponentItem) -> None:
        """After `component` finishes moving, resolve each of its terminals
        against whatever it now sits on top of. A two-terminal component
        that landed with BOTH terminals on the same existing wire is spliced
        into it as a single step (see _splice_into_wire) rather than each
        terminal being resolved independently, which would just short it out
        in parallel with the wire's still-intact original path. Otherwise -
        a Node's single terminal, or a regular component that only has one
        terminal (or neither) on something - each terminal is resolved on
        its own via _auto_connect_terminal()."""
        if self._splice_into_wire(component):
            return
        for terminal in component.terminals:
            self._auto_connect_terminal(terminal)

    def _splice_into_wire(self, component: ComponentItem) -> bool:
        """If `component` has exactly two terminals and both just landed on
        the same existing wire's line (not at either of its own endpoints -
        _coincident_terminal already covers landing exactly on a terminal,
        so this only fires for a genuine "dropped across the middle of a
        wire" case), tapping each one in independently would leave that
        wire's original two ends still directly wired to each other -
        shorting the new component out in parallel instead of actually
        inserting it into the circuit. Delete that one wire instead and
        rewire its two original endpoints straight to whichever of the
        component's terminals is nearer each one, so current has to pass
        through the component. Returns True if this happened."""
        if component.component_type == JUNCTION_TYPE or len(component.terminals) != 2:
            return False
        t0, t1 = component.terminals
        if self._coincident_terminal(t0) is not None or self._coincident_terminal(t1) is not None:
            return False  # an exact terminal landing takes the usual merge/wire path instead

        wire = self._wire_at(t0)
        if wire is None or self._wire_at(t1) is not wire:
            return False  # not the same wire (or not on a wire at all) - handle each terminal on its own

        def dist(a: TerminalItem, b: TerminalItem) -> float:
            delta = a.scenePos() - b.scenePos()
            return (delta.x() ** 2 + delta.y() ** 2) ** 0.5

        if dist(wire.start_terminal, t0) <= dist(wire.start_terminal, t1):
            near, far = t0, t1
        else:
            near, far = t1, t0
        self.undo_stack.push(SpliceComponentIntoWireCommand(self, wire, near, far))
        return True

    def _auto_connect_terminal(self, terminal: TerminalItem) -> None:
        """Resolves one terminal that just finished moving:
        - landed exactly on another terminal, and either side is a Node ->
          that Node is redundant now - merge it away into the other side
          (whichever one is the Node, regardless of which side moved).
        - landed exactly on another terminal, neither side a Node -> wire
          them together (unless already wired).
        - landed on an existing wire's line (not at either of its ends) ->
          tap into it, splitting that wire through this terminal instead of
          through a new Node.
        """
        other = self._coincident_terminal(terminal)
        if other is not None:
            terminal_is_node = terminal.component().component_type == JUNCTION_TYPE
            other_is_node = other.component().component_type == JUNCTION_TYPE
            if terminal_is_node:
                self.undo_stack.push(MergeNodeIntoTerminalCommand(self, terminal.component(), other))
            elif other_is_node:
                self.undo_stack.push(MergeNodeIntoTerminalCommand(self, other.component(), terminal))
            elif not terminals_already_wired(terminal, other):
                self.undo_stack.push(AddWireCommand(self, WireItem(terminal, other)))
            return

        wire = self._wire_at(terminal)
        if wire is not None:
            self.undo_stack.push(ConnectTerminalToWireCommand(self, wire, terminal))

    def _coincident_terminal(self, terminal: TerminalItem) -> TerminalItem | None:
        """The first other terminal (belonging to a different component)
        sitting exactly on top of `terminal`, if any."""
        component = terminal.component()
        for other in self.scene.items(terminal.scenePos()):
            if isinstance(other, TerminalItem) and other is not terminal and other.component() is not component:
                return other
        return None

    # A terminal landing within this many scene units of a wire's line still
    # counts as "on" it. A plain pixel hit test (scene.items(exact_point))
    # only ever catches perfectly horizontal/vertical wires, since for any
    # diagonal wire almost no other grid point sits mathematically exactly
    # on its line - a small tolerance is what makes tapping work reliably
    # for the (very common) case of two components that aren't lined up on
    # the same row/column. Every terminal is grid-snapped (GRID_SIZE=20), so
    # this is nowhere near large enough to ever confuse two distinct wires.
    WIRE_TAP_TOLERANCE = 6.0

    def _wire_at(self, terminal: TerminalItem) -> WireItem | None:
        """The closest wire (belonging to some other component) passing
        within tolerance of `terminal`'s position, if any - only meaningful
        to call once _coincident_terminal() has already ruled out landing on
        an actual terminal, since a wire's own endpoints would otherwise
        match here too."""
        component = terminal.component()
        point = terminal.scenePos()
        best: WireItem | None = None
        best_dist = self.WIRE_TAP_TOLERANCE
        for item in self.scene.items():
            if (
                isinstance(item, WireItem)
                and item.start_terminal.component() is not component
                and item.end_terminal.component() is not component
            ):
                dist = item.distance_to(point)
                if dist <= best_dist:
                    best = item
                    best_dist = dist
        return best

    def _on_component_edit_requested(self, component: ComponentItem, new_label: str, new_value: float) -> None:
        self.undo_stack.push(
            EditComponentCommand(component, component.label, component.value, new_label, new_value)
        )

    def delete_selected(self) -> None:
        selected = list(self.scene.selectedItems())
        if selected:
            self.undo_stack.push(DeleteSelectionCommand(self, selected))

    def rotate_selected(self) -> None:
        rotations = [
            (item, item.rotation(), (item.rotation() + 90) % 360)
            for item in self.scene.selectedItems()
            if isinstance(item, ComponentItem)
        ]
        if rotations:
            self.undo_stack.push(RotateComponentsCommand(rotations))

    def split_selected_wire(self) -> None:
        wires = [item for item in self.scene.selectedItems() if isinstance(item, WireItem)]
        if len(wires) != 1:
            return
        wire = wires[0]
        line = wire.line()
        midpoint = QPointF((line.x1() + line.x2()) / 2, (line.y1() + line.y2()) / 2)
        snapped = QPointF(
            round(midpoint.x() / GRID_SIZE) * GRID_SIZE,
            round(midpoint.y() / GRID_SIZE) * GRID_SIZE,
        )
        self._on_wire_split_requested(wire, snapped)

    # --- window title / unsaved-changes tracking --------------------------

    def _update_title(self) -> None:
        try:
            clean = self.undo_stack.isClean()
        except RuntimeError:
            return  # cleanChanged fired while the window was being torn down
        name = self._current_path.name if self._current_path is not None else "Untitled"
        dirty_mark = "" if clean else "*"
        self.setWindowTitle(f"{dirty_mark}{name} - Circuit Builder")

    def _maybe_save(self) -> bool:
        """Offers to save unsaved changes. Returns True if it's OK to proceed
        with whatever discards the current circuit (new/open/quit) - i.e. the
        user saved successfully or explicitly chose to discard. Returns False
        if the operation should be aborted (save failed/cancelled, or the
        user cancelled outright)."""
        if self.undo_stack.isClean():
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "This circuit has unsaved changes. Do you want to save before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self.save_circuit()
        return reply == QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:
        if self._maybe_save():
            # Stop a live simulation before the window (and its scene) start
            # tearing down - otherwise a stray indexChanged during teardown
            # can fire _on_circuit_changed() against an already-destroyed
            # scene.
            self._stop_simulation()
            event.accept()
        else:
            event.ignore()

    # --- file operations --------------------------------------------------

    def new_circuit(self) -> None:
        if not self._maybe_save():
            return
        self._stop_simulation()
        self.view.reset_interaction_state()
        self.scene.clear()
        self.undo_stack.clear()
        self._counters = {key: 0 for key in COMPONENT_TYPES}
        self._current_path = None
        self._update_title()

    def open_circuit(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Circuit", "", "Circuit Files (*.json)")
        if not path:
            return
        try:
            circuit = Circuit.load(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open Circuit", f"Could not open file:\n{exc}")
            return
        self._load_circuit(circuit)
        self._current_path = Path(path)
        self._update_title()

    def save_circuit(self) -> bool:
        if self._current_path is None:
            return self.save_circuit_as()
        return self._write_to(self._current_path)

    def save_circuit_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save Circuit", "circuit.json", "Circuit Files (*.json)")
        if not path:
            return False
        self._current_path = Path(path)
        ok = self._write_to(self._current_path)
        self._update_title()
        return ok

    def _write_to(self, path: Path) -> bool:
        circuit = self._build_circuit_model()
        try:
            circuit.save(str(path))
        except Exception as exc:
            QMessageBox.critical(self, "Save Circuit", f"Could not save file:\n{exc}")
            return False
        self.undo_stack.setClean()
        return True

    def _build_circuit_model(self) -> Circuit:
        components: list[ComponentData] = []
        wires: list[WireData] = []
        seen_wire_ids: set[str] = set()

        for item in self.scene.items():
            if isinstance(item, ComponentItem):
                components.append(
                    ComponentData(
                        id=item.id,
                        type=item.component_type,
                        x=item.pos().x(),
                        y=item.pos().y(),
                        rotation=item.rotation(),
                        value=item.value,
                        label=item.label,
                        closed=item.closed,
                    )
                )
            elif isinstance(item, WireItem) and item.id not in seen_wire_ids:
                seen_wire_ids.add(item.id)
                wires.append(
                    WireData(
                        id=item.id,
                        start=TerminalRef(item.start_terminal.component().id, item.start_terminal.index),
                        end=TerminalRef(item.end_terminal.component().id, item.end_terminal.index),
                    )
                )

        return Circuit(components=components, wires=wires)

    def _load_circuit(self, circuit: Circuit) -> None:
        self._stop_simulation()
        self.view.reset_interaction_state()
        self.scene.clear()
        self._counters = {key: 0 for key in COMPONENT_TYPES}
        id_to_item: dict[str, ComponentItem] = {}

        for c in circuit.components:
            item = self.add_component(
                c.type, QPointF(c.x, c.y), label=c.label, value=c.value, component_id=c.id, closed=c.closed
            )
            item.setRotation(c.rotation)
            id_to_item[c.id] = item

            digits = "".join(ch for ch in c.label if ch.isdigit())
            if digits:
                self._counters[c.type] = max(self._counters[c.type], int(digits))

        for w in circuit.wires:
            start_item = id_to_item.get(w.start.component_id)
            end_item = id_to_item.get(w.end.component_id)
            if start_item is None or end_item is None:
                continue
            start_terminal = start_item.terminals[w.start.terminal_index]
            end_terminal = end_item.terminals[w.end.terminal_index]
            wire = WireItem(start_terminal, end_terminal)
            wire.id = w.id
            wire.attach()
            self.scene.addItem(wire)

        self.undo_stack.clear()
