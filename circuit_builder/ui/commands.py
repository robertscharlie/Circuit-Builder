from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QUndoCommand

from circuit_builder.core.components import COMPONENT_TYPES
from circuit_builder.ui.component_item import ComponentItem
from circuit_builder.ui.terminal_item import terminals_already_wired
from circuit_builder.ui.wire_item import WireItem


class AddComponentCommand(QUndoCommand):
    """Adds a single newly-created component (e.g. dropped from the palette)."""

    def __init__(self, main_window, component_type: str, scene_pos: QPointF, rotation: float = 0.0):
        super().__init__(f"Add {COMPONENT_TYPES[component_type].display_name}")
        self.main_window = main_window
        # Built once up front: label auto-numbering must only happen the
        # first time, not be re-run on every redo().
        self.item = main_window._create_component(component_type, scene_pos)
        if rotation:
            self.item.setRotation(rotation)

    def redo(self) -> None:
        self.main_window.scene.addItem(self.item)

    def undo(self) -> None:
        self.main_window.scene.removeItem(self.item)


class AddWireCommand(QUndoCommand):
    """Adds a wire that has already been constructed (but not yet attached
    to its terminals or added to the scene)."""

    def __init__(self, main_window, wire: WireItem):
        super().__init__("Add wire")
        self.main_window = main_window
        self.wire = wire

    def redo(self) -> None:
        self.wire.attach()
        self.main_window.scene.addItem(self.wire)

    def undo(self) -> None:
        self.wire.detach()
        self.main_window.scene.removeItem(self.wire)


class MoveComponentsCommand(QUndoCommand):
    """One or more components dragged to a new position in a single drag."""

    def __init__(self, moves: list[tuple[ComponentItem, QPointF, QPointF]]):
        super().__init__("Move" if len(moves) == 1 else "Move components")
        self.moves = moves

    def redo(self) -> None:
        for component, _old_pos, new_pos in self.moves:
            component.setPos(new_pos)

    def undo(self) -> None:
        for component, old_pos, _new_pos in self.moves:
            component.setPos(old_pos)


class RotateComponentsCommand(QUndoCommand):
    """One or more selected components rotated 90 degrees together."""

    def __init__(self, rotations: list[tuple[ComponentItem, float, float]]):
        super().__init__("Rotate" if len(rotations) == 1 else "Rotate components")
        self.rotations = rotations

    def redo(self) -> None:
        for component, _old_rot, new_rot in self.rotations:
            component.setRotation(new_rot)
            component.update_wires()

    def undo(self) -> None:
        for component, old_rot, _new_rot in self.rotations:
            component.setRotation(old_rot)
            component.update_wires()


class EditComponentCommand(QUndoCommand):
    """A label/value change made through the double-click edit dialog."""

    def __init__(self, component: ComponentItem, old_label: str, old_value: float, new_label: str, new_value: float):
        super().__init__("Edit component")
        self.component = component
        self.old_label = old_label
        self.old_value = old_value
        self.new_label = new_label
        self.new_value = new_value

    def redo(self) -> None:
        self.component.apply_edit(self.new_label, self.new_value)

    def undo(self) -> None:
        self.component.apply_edit(self.old_label, self.old_value)


class ToggleSwitchCommand(QUndoCommand):
    """Flips a switch's open/closed state - both redo() and undo() just flip
    it again, since the operation is its own inverse."""

    def __init__(self, component: ComponentItem):
        super().__init__("Toggle switch")
        self.component = component

    def redo(self) -> None:
        self.component.closed = not self.component.closed
        self.component.update()

    def undo(self) -> None:
        self.component.closed = not self.component.closed
        self.component.update()


def _wire_unless_duplicate(a, b) -> WireItem | None:
    """A new WireItem between `a` and `b`, or None if they're already wired
    directly to each other. Used when splitting an existing wire into two
    new segments through a tapping-in terminal: that terminal might already
    happen to have its own separate wire straight to one of the original
    wire's endpoints (e.g. it was wired elsewhere in the diagram before
    being dragged on top of this wire) - reusing that existing connection
    instead of adding a redundant parallel wire on top of it."""
    return None if terminals_already_wired(a, b) else WireItem(a, b)


class ConnectTerminalToWireCommand(QUndoCommand):
    """A component's terminal has landed exactly on an existing wire's line
    (not on either of its endpoints, which would instead go through
    AddWireCommand/MergeNodeIntoTerminalCommand) - taps into it by replacing
    that one wire with two new ones routed through the terminal. No new
    component is created, unlike SplitWireCommand."""

    def __init__(self, main_window, wire: WireItem, terminal):
        super().__init__("Connect to wire")
        self.main_window = main_window
        self.old_wire = wire
        self.wire_a = _wire_unless_duplicate(wire.start_terminal, terminal)
        self.wire_b = _wire_unless_duplicate(terminal, wire.end_terminal)

    def redo(self) -> None:
        scene = self.main_window.scene
        self.old_wire.detach()
        scene.removeItem(self.old_wire)
        for wire in (self.wire_a, self.wire_b):
            if wire is not None:
                wire.attach()
                scene.addItem(wire)

    def undo(self) -> None:
        scene = self.main_window.scene
        for wire in (self.wire_a, self.wire_b):
            if wire is not None:
                wire.detach()
                scene.removeItem(wire)
        self.old_wire.attach()
        scene.addItem(self.old_wire)


class SpliceComponentIntoWireCommand(QUndoCommand):
    """A two-terminal component was dropped with BOTH of its terminals
    landing on the same existing wire - unlike ConnectTerminalToWireCommand
    (one terminal tapping in, leaving the wire's original path still
    directly connected end to end), tapping in independently at each end
    here would leave that original path intact and just short the new
    component out in parallel with it, instead of actually inserting it
    into the circuit. Deletes that one wire and rewires its two original
    endpoints straight to the component's near/far terminal instead, so
    current has to pass through the component where the wire used to run
    straight through."""

    def __init__(self, main_window, wire: WireItem, near_terminal, far_terminal):
        super().__init__("Insert component into wire")
        self.main_window = main_window
        self.old_wire = wire
        self.wire_a = _wire_unless_duplicate(wire.start_terminal, near_terminal)
        self.wire_b = _wire_unless_duplicate(far_terminal, wire.end_terminal)

    def redo(self) -> None:
        scene = self.main_window.scene
        self.old_wire.detach()
        scene.removeItem(self.old_wire)
        for wire in (self.wire_a, self.wire_b):
            if wire is not None:
                wire.attach()
                scene.addItem(wire)

    def undo(self) -> None:
        scene = self.main_window.scene
        for wire in (self.wire_a, self.wire_b):
            if wire is not None:
                wire.detach()
                scene.removeItem(wire)
        self.old_wire.attach()
        scene.addItem(self.old_wire)


class SplitWireCommand(QUndoCommand):
    """Splits an existing wire in two by inserting a Node at scene_pos,
    rewiring the original endpoints to the node instead of to each other.
    Electrically a no-op (a Node is just a pass-through junction) - this is
    purely a way to add a bend/tap point to an existing wire run."""

    def __init__(self, main_window, wire: WireItem, scene_pos: QPointF):
        super().__init__("Split wire")
        self.main_window = main_window
        self.old_wire = wire
        # Built once up front, same reasoning as AddComponentCommand: label
        # auto-numbering must only happen the first time, not on every redo().
        self.node = main_window._create_component("junction", scene_pos)
        self.wire_a = WireItem(wire.start_terminal, self.node.terminals[0])
        self.wire_b = WireItem(self.node.terminals[0], wire.end_terminal)

    def redo(self) -> None:
        scene = self.main_window.scene
        self.old_wire.detach()
        scene.removeItem(self.old_wire)
        scene.addItem(self.node)
        self.wire_a.attach()
        scene.addItem(self.wire_a)
        self.wire_b.attach()
        scene.addItem(self.wire_b)

    def undo(self) -> None:
        scene = self.main_window.scene
        self.wire_a.detach()
        scene.removeItem(self.wire_a)
        self.wire_b.detach()
        scene.removeItem(self.wire_b)
        scene.removeItem(self.node)
        self.old_wire.attach()
        scene.addItem(self.old_wire)


class DetachTerminalCommand(QUndoCommand):
    """Right-click a component's terminal (that has wire(s) attached) and
    choose "Move Node": pulls every wire on that terminal off onto a new
    free Node placed at the terminal's current position, disconnecting them
    from the component entirely. The node is left for the caller to enter
    move-mode on (see CircuitView.start_move_component) so it can be dragged
    to wherever it's actually needed."""

    def __init__(self, main_window, terminal, scene_pos: QPointF):
        super().__init__("Detach wire to a new Node")
        self.main_window = main_window
        self.terminal = terminal
        # Built once up front, same reasoning as AddComponentCommand: label
        # auto-numbering must only happen the first time, not on every redo().
        self.node = main_window._create_component("junction", scene_pos)
        self.old_wires = list(terminal.wires)
        self.new_wires = [
            WireItem(self.node.terminals[0], wire.end_terminal if wire.start_terminal is terminal else wire.start_terminal)
            for wire in self.old_wires
        ]

    def redo(self) -> None:
        scene = self.main_window.scene
        for wire in self.old_wires:
            wire.detach()
            scene.removeItem(wire)
        scene.addItem(self.node)
        for wire in self.new_wires:
            wire.attach()
            scene.addItem(wire)

    def undo(self) -> None:
        scene = self.main_window.scene
        for wire in self.new_wires:
            wire.detach()
            scene.removeItem(wire)
        scene.removeItem(self.node)
        for wire in self.old_wires:
            wire.attach()
            scene.addItem(wire)


class MergeNodeIntoTerminalCommand(QUndoCommand):
    """The inverse of DetachTerminalCommand: a Node dropped exactly onto
    another terminal is redundant now that it's coincident with it, so it's
    deleted, and every wire that was on the Node is rewired straight to that
    terminal instead. If the Node had no wires, this just removes it."""

    def __init__(self, main_window, node: ComponentItem, target_terminal):
        super().__init__("Merge Node into terminal")
        self.main_window = main_window
        self.node = node
        self.node_pos = node.pos()
        node_terminal = node.terminals[0]
        self.old_wires = list(node_terminal.wires)
        self.new_wires = [
            WireItem(target_terminal, wire.end_terminal if wire.start_terminal is node_terminal else wire.start_terminal)
            for wire in self.old_wires
        ]

    def redo(self) -> None:
        scene = self.main_window.scene
        for wire in self.old_wires:
            wire.detach()
            scene.removeItem(wire)
        scene.removeItem(self.node)
        for wire in self.new_wires:
            wire.attach()
            scene.addItem(wire)

    def undo(self) -> None:
        scene = self.main_window.scene
        for wire in self.new_wires:
            wire.detach()
            scene.removeItem(wire)
        self.node.setPos(self.node_pos)
        scene.addItem(self.node)
        for wire in self.old_wires:
            wire.attach()
            scene.addItem(wire)


class DeleteSelectionCommand(QUndoCommand):
    """Deletes a set of selected components and/or wires as one step.

    Deleting a component cascades to any wires attached to it, even if
    those wires weren't themselves selected.
    """

    def __init__(self, main_window, selected_items: list):
        super().__init__("Delete")
        self.main_window = main_window

        components = [i for i in selected_items if isinstance(i, ComponentItem)]
        wires = {i for i in selected_items if isinstance(i, WireItem)}
        for component in components:
            for terminal in component.terminals:
                wires.update(terminal.wires)

        self.components = components
        self.wires = list(wires)

    def redo(self) -> None:
        scene = self.main_window.scene
        for wire in self.wires:
            wire.detach()
            scene.removeItem(wire)
        for component in self.components:
            scene.removeItem(component)

    def undo(self) -> None:
        scene = self.main_window.scene
        for component in self.components:
            scene.addItem(component)
        for wire in self.wires:
            wire.attach()
            scene.addItem(wire)
