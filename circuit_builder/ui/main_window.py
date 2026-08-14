from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QUndoStack
from PySide6.QtWidgets import QDockWidget, QFileDialog, QMainWindow, QMessageBox, QStatusBar, QToolBar

from circuit_builder.core.circuit_model import Circuit, ComponentData, TerminalRef, WireData
from circuit_builder.core.components import COMPONENT_TYPES
from circuit_builder.ui.canvas import CircuitScene, CircuitView
from circuit_builder.ui.commands import (
    AddComponentCommand,
    AddWireCommand,
    DeleteSelectionCommand,
    DetachTerminalCommand,
    EditComponentCommand,
    MergeNodeIntoTerminalCommand,
    MoveComponentsCommand,
    RotateComponentsCommand,
    SplitWireCommand,
)
from circuit_builder.ui.component_item import ComponentItem, GRID_SIZE, JUNCTION_TYPE
from circuit_builder.ui.help_dialog import ControlsHelpDialog
from circuit_builder.ui import icons
from circuit_builder.ui.palette import ComponentPalette
from circuit_builder.ui.terminal_item import TerminalItem, terminals_already_wired
from circuit_builder.ui.wire_item import WireItem

SCENE_EXTENT = 3000


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
        self.view.terminal_detach_requested.connect(self._on_terminal_detach_requested)

        palette_dock = QDockWidget("Components", self)
        palette_dock.setWidget(ComponentPalette(self))
        palette_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, palette_dock)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage(
            "Drag components or press R/B/C/I/N to place one (Resistor/Battery/Capacitor/Inductor/Node) - "
            "while placing, press R to rotate it, click to drop. "
            "Drag between terminal dots to wire them - Shift+drag a terminal to move its component instead. "
            "Right-click a wire, component, or a wired terminal for more options (split a wire, move a "
            "component by clicking its new spot instead of dragging, or detach a wired terminal onto its "
            "own Node). Drop a terminal exactly onto another one to auto-wire them - if either side is a "
            "Node, it merges away instead, rewiring its connections straight to the other terminal. "
            "Double-click to edit, Delete to remove, Ctrl+R to rotate a selection. "
            "Scroll to zoom, middle-drag or the Pan Tool (H) to move around."
        )

        self._counters = {key: 0 for key in COMPONENT_TYPES}
        self._current_path: Path | None = None

        self._build_toolbar()
        self._build_component_shortcuts()
        self._build_menu()

        self.undo_stack.cleanChanged.connect(lambda _clean: self._update_title())
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

        help_menu = self.menuBar().addMenu("&Help")
        controls_action = QAction("Controls...", self)
        controls_action.setShortcut("F1")
        controls_action.triggered.connect(self.show_controls_help)
        help_menu.addAction(controls_action)

    def show_controls_help(self) -> None:
        ControlsHelpDialog(self).exec()

    # --- component / wire management ------------------------------------

    def _create_component(
        self,
        comp_type: str,
        scene_pos: QPointF,
        label: str | None = None,
        value: float | None = None,
        component_id: str | None = None,
    ) -> ComponentItem:
        """Builds and configures a component but does not add it to the
        scene - used by AddComponentCommand so redo()/undo() can toggle its
        presence without re-running label auto-numbering each time."""
        if label is None:
            self._counters[comp_type] += 1
            label = f"{COMPONENT_TYPES[comp_type].prefix}{self._counters[comp_type]}"
        item = ComponentItem(comp_type, value=value, label=label, component_id=component_id)
        item.setPos(scene_pos)
        item.edit_requested.connect(self._on_component_edit_requested)
        return item

    def add_component(
        self,
        comp_type: str,
        scene_pos: QPointF,
        label: str | None = None,
        value: float | None = None,
        component_id: str | None = None,
    ) -> ComponentItem:
        """Creates a component and adds it straight to the scene, bypassing
        the undo stack. Used for loading a file, not for user-driven adds
        (those go through AddComponentCommand so they're undoable)."""
        item = self._create_component(comp_type, scene_pos, label=label, value=value, component_id=component_id)
        self.scene.addItem(item)
        return item

    def _on_component_dropped(self, comp_type: str, scene_pos: QPointF, rotation: float = 0.0) -> None:
        self.undo_stack.push(AddComponentCommand(self, comp_type, scene_pos, rotation))

    def _on_wire_created(self, wire: WireItem) -> None:
        self.undo_stack.push(AddWireCommand(self, wire))

    def _on_wire_split_requested(self, wire: WireItem, scene_pos: QPointF) -> None:
        self.undo_stack.push(SplitWireCommand(self, wire, scene_pos))

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
        """After `component` finishes moving, resolve any of its terminals
        that now land exactly on top of another component's terminal:
        - if `component` itself is a Node, it's now redundant - merge it
          away into whatever it landed on (whichever side moved, a Node
          dropped onto something else always disappears in favor of it).
        - if it landed on a Node's terminal instead, that Node is now the
          redundant one - merge it away into `component`'s terminal.
        - otherwise (neither side is a Node), just add a wire joining them.
        """
        if component.component_type == JUNCTION_TYPE:
            target = self._coincident_terminal(component.terminals[0])
            if target is not None:
                self.undo_stack.push(MergeNodeIntoTerminalCommand(self, component, target))
            return

        for terminal in component.terminals:
            other = self._coincident_terminal(terminal)
            if other is None:
                continue
            if other.component().component_type == JUNCTION_TYPE:
                self.undo_stack.push(MergeNodeIntoTerminalCommand(self, other.component(), terminal))
            elif not terminals_already_wired(terminal, other):
                self.undo_stack.push(AddWireCommand(self, WireItem(terminal, other)))

    def _coincident_terminal(self, terminal: TerminalItem) -> TerminalItem | None:
        """The first other terminal (belonging to a different component)
        sitting exactly on top of `terminal`, if any."""
        component = terminal.component()
        for other in self.scene.items(terminal.scenePos()):
            if isinstance(other, TerminalItem) and other is not terminal and other.component() is not component:
                return other
        return None

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
            event.accept()
        else:
            event.ignore()

    # --- file operations --------------------------------------------------

    def new_circuit(self) -> None:
        if not self._maybe_save():
            return
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
        self.view.reset_interaction_state()
        self.scene.clear()
        self._counters = {key: 0 for key in COMPONENT_TYPES}
        id_to_item: dict[str, ComponentItem] = {}

        for c in circuit.components:
            item = self.add_component(
                c.type, QPointF(c.x, c.y), label=c.label, value=c.value, component_id=c.id
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
