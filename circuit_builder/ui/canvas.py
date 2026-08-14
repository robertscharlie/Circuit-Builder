from __future__ import annotations

from PySide6.QtCore import QEvent, QLineF, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsScene, QGraphicsView, QMenu

from circuit_builder.ui.component_item import ComponentItem, GRID_SIZE, JUNCTION_TYPE
from circuit_builder.ui.palette import MIME_TYPE
from circuit_builder.ui.terminal_item import TerminalItem, terminals_already_wired
from circuit_builder.ui.wire_item import WireItem


class CircuitScene(QGraphicsScene):
    """Scene that draws a light grid to help with component alignment."""

    def drawBackground(self, painter: QPainter, rect):
        painter.fillRect(rect, QColor("#fafafa"))
        painter.setPen(QPen(QColor("#e6e6e6")))

        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)

        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += GRID_SIZE

        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += GRID_SIZE


class CircuitView(QGraphicsView):
    """Canvas view: accepts palette drops and handles click-drag wiring
    between terminals, middle-drag panning, and wheel/button zoom."""

    component_dropped = Signal(str, QPointF, float)  # type, scene_pos, rotation
    wire_created = Signal(object)  # WireItem - not a QObject, so plain 'object'
    components_moved = Signal(list)  # [(ComponentItem, QPointF old_pos, QPointF new_pos), ...]
    wire_split_requested = Signal(object, QPointF)  # WireItem, grid-snapped scene_pos
    terminal_detach_requested = Signal(object, QPointF)  # TerminalItem, its current scene_pos

    MIN_ZOOM = 0.2
    MAX_ZOOM = 5.0
    ZOOM_STEP = 1.15
    BUTTON_ZOOM_STEP = 1.25

    def __init__(self, scene: CircuitScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        # MinimalViewportUpdate (the default) is known to leave stale pixels
        # behind when combined with a custom drawBackground() and items that
        # move - it was the cause of streaky redraw artifacts here. A full
        # repaint per update is cheap for a schematic-sized scene.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self._wire_start: TerminalItem | None = None
        self._temp_line: QGraphicsLineItem | None = None
        self._drag_start_positions: dict[ComponentItem, QPointF] = {}
        self._panning = False
        self._pan_start = QPointF()
        self._pan_tool_active = False
        self._drag_preview: ComponentItem | None = None
        self._zoom = 1.0
        self._pending_place_type: str | None = None
        self._pending_place_rotation = 0.0
        # A component dragged by its own terminal (Shift+drag - see
        # mousePressEvent) rather than through Qt's normal item-drag, since
        # Qt would otherwise deliver the press to the terminal, not its
        # movable parent.
        self._manual_drag_component: ComponentItem | None = None
        self._manual_drag_start_scene_pos = QPointF()
        self._manual_drag_start_item_pos = QPointF()
        # A component being relocated via its right-click context menu's
        # "Move" action - it follows the cursor (like the placement ghost)
        # until the next click, rather than requiring a drag.
        self._pending_move_target: ComponentItem | None = None
        self._pending_move_start_pos = QPointF()
        # Testing seam: QMenu.exec() opens a real, blocking native popup that
        # automated tests can't reliably drive (no real desktop/input to
        # click it with). When set, this replaces that call with
        # menu_exec_override(menu) -> chosen QAction | None. Production code
        # never sets it, so real usage is unaffected.
        self._menu_exec_override = None

    def _exec_context_menu(self, menu: QMenu, global_pos):
        if self._menu_exec_override is not None:
            return self._menu_exec_override(menu)
        return menu.exec(global_pos)

    # --- keyboard placement: press a shortcut, move the ghost, click to place

    def start_placement(self, component_type: str) -> None:
        if self._wire_start is not None or self._panning or self._pending_move_target is not None:
            return  # don't interrupt an in-progress wire drag, pan, or component move
        self._pending_place_type = component_type
        self._pending_place_rotation = 0.0
        self._show_drag_preview(component_type, self.mapFromGlobal(QCursor.pos()))
        self.setCursor(Qt.CursorShape.CrossCursor)

    def cancel_placement(self) -> None:
        if self._pending_place_type is not None:
            self._pending_place_type = None
            self._pending_place_rotation = 0.0
            self._clear_drag_preview()
            self.unsetCursor()

    def set_pan_tool_active(self, active: bool) -> None:
        self._pan_tool_active = active
        if not self._panning:
            self.setCursor(Qt.CursorShape.OpenHandCursor if active else Qt.CursorShape.ArrowCursor)

    # --- move-via-context-menu: pick "Move" on a component, it follows the
    # cursor, click elsewhere to drop it (any wires attached follow along
    # automatically, same as a normal drag).

    def start_move_component(self, component: ComponentItem) -> None:
        if self._wire_start is not None or self._panning or self._pending_place_type is not None:
            return
        self._pending_move_target = component
        self._pending_move_start_pos = component.pos()
        self.scene().clearSelection()
        component.setSelected(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._move_pending_target(self.mapFromGlobal(QCursor.pos()))

    def cancel_move_component(self) -> None:
        if self._pending_move_target is not None:
            self._pending_move_target.setPos(self._pending_move_start_pos)
            self._pending_move_target = None
            self.unsetCursor()

    def _move_pending_target(self, viewport_pos) -> None:
        if self._pending_move_target is None:
            return
        scene_pos = self.mapToScene(viewport_pos)
        snapped = QPointF(
            round(scene_pos.x() / GRID_SIZE) * GRID_SIZE,
            round(scene_pos.y() / GRID_SIZE) * GRID_SIZE,
        )
        self._pending_move_target.setPos(snapped)

    # --- right-click context menus ----------------------------------------

    def _show_wire_context_menu(self, wire: WireItem, viewport_pos) -> None:
        menu = QMenu(self)
        split_action = menu.addAction("Split Wire Here")
        chosen = self._exec_context_menu(menu, self.viewport().mapToGlobal(viewport_pos))
        if chosen == split_action:
            scene_pos = self.mapToScene(viewport_pos)
            snapped = QPointF(
                round(scene_pos.x() / GRID_SIZE) * GRID_SIZE,
                round(scene_pos.y() / GRID_SIZE) * GRID_SIZE,
            )
            self.wire_split_requested.emit(wire, snapped)

    def _show_component_context_menu(self, component: ComponentItem, viewport_pos) -> None:
        menu = QMenu(self)
        label = "Move Node" if component.component_type == JUNCTION_TYPE else "Move Component"
        move_action = menu.addAction(label)
        chosen = self._exec_context_menu(menu, self.viewport().mapToGlobal(viewport_pos))
        if chosen == move_action:
            self.start_move_component(component)

    def _show_terminal_context_menu(self, terminal: TerminalItem, viewport_pos) -> None:
        menu = QMenu(self)
        move_action = menu.addAction("Move Node")
        chosen = self._exec_context_menu(menu, self.viewport().mapToGlobal(viewport_pos))
        if chosen == move_action:
            self.terminal_detach_requested.emit(terminal, terminal.scenePos())

    def event(self, event):
        # MainWindow binds "R" and "Esc" as global QAction shortcuts (rotate
        # selection, etc). Qt resolves those via a ShortcutOverride event
        # sent to the focused widget *before* a normal key press would reach
        # keyPressEvent() below - without claiming it here first, the global
        # action would steal the key and this widget would never see it.
        if event.type() == QEvent.Type.ShortcutOverride and self._pending_place_type is not None:
            if event.key() in (Qt.Key.Key_R, Qt.Key.Key_Escape):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        if self._pending_place_type is not None:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_placement()
                event.accept()
                return
            if event.key() == Qt.Key.Key_R:
                self._pending_place_rotation = (self._pending_place_rotation + 90) % 360
                if self._drag_preview is not None:
                    self._drag_preview.setRotation(self._pending_place_rotation)
                event.accept()
                return

        if self._pending_move_target is not None and event.key() == Qt.Key.Key_Escape:
            self.cancel_move_component()
            event.accept()
            return
        super().keyPressEvent(event)

    def reset_interaction_state(self) -> None:
        """Cancels any in-progress interaction that holds a direct reference
        to a scene item (placement ghost, wire-drag preview line). Callers
        MUST call this before scene.clear() - those items would otherwise be
        destroyed out from under these references, crashing on next use."""
        self.cancel_placement()
        if self._temp_line is not None:
            self.scene().removeItem(self._temp_line)
            self._temp_line = None
        self._wire_start = None
        self._drag_start_positions = {}
        self._manual_drag_component = None
        self._pending_move_target = None
        if self._panning:
            self._panning = False
            self.set_pan_tool_active(self._pan_tool_active)

    # --- wiring: click a terminal, drag to another terminal -------------
    # --- also tracks component drag-start/end for undo, and middle-drag pan

    def mousePressEvent(self, event):
        if self._pending_place_type is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                comp_type = self._pending_place_type
                rotation = self._pending_place_rotation
                scene_pos = self.mapToScene(event.pos())
                self.cancel_placement()
                self.component_dropped.emit(comp_type, scene_pos, rotation)
            else:
                self.cancel_placement()
            event.accept()
            return

        if self._pending_move_target is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                component = self._pending_move_target
                old_pos = self._pending_move_start_pos
                new_pos = component.pos()
                self._pending_move_target = None
                self.unsetCursor()
                if new_pos != old_pos:
                    self.components_moved.emit([(component, old_pos, new_pos)])
            else:
                self.cancel_move_component()
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            item = self.itemAt(event.pos())
            if isinstance(item, TerminalItem):
                # A regular component's terminal with a wire on it gets its
                # own menu (detach that wire onto a free Node) - a Node's own
                # terminal, or an unconnected terminal, falls back to moving
                # the whole component, same as clicking its body.
                if item.component().component_type != JUNCTION_TYPE and item.wires:
                    self._show_terminal_context_menu(item, event.pos())
                    event.accept()
                    return
                item = item.component()
            if isinstance(item, WireItem):
                self._show_wire_context_menu(item, event.pos())
                event.accept()
                return
            if isinstance(item, ComponentItem):
                self._show_component_context_menu(item, event.pos())
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton or (
            self._pan_tool_active and event.button() == Qt.MouseButton.LeftButton
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        item = self.itemAt(event.pos())
        shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if isinstance(item, TerminalItem) and event.button() == Qt.MouseButton.LeftButton:
            if shift_held:
                # Shift+drag a terminal moves its owning component instead of
                # starting a wire - a terminal (esp. a Node's, which has no
                # other body to grab) would otherwise be very hard to
                # reposition, since clicking it always starts a wire.
                component = item.component()
                self.scene().clearSelection()
                component.setSelected(True)
                self._manual_drag_component = component
                self._manual_drag_start_scene_pos = self.mapToScene(event.pos())
                self._manual_drag_start_item_pos = component.pos()
                event.accept()
                return

            self._wire_start = item
            start_pos = item.scenePos()
            self._temp_line = QGraphicsLineItem(QLineF(start_pos, start_pos))
            self._temp_line.setPen(QPen(QColor("#e07a1f"), 1.5, Qt.PenStyle.DashLine))
            self._temp_line.setZValue(10)
            self.scene().addItem(self._temp_line)
            event.accept()
            return

        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_positions = {
                comp: comp.pos() for comp in self.scene().selectedItems() if isinstance(comp, ComponentItem)
            }

    def mouseMoveEvent(self, event):
        if self._pending_place_type is not None:
            self._move_drag_preview(event.pos())
            event.accept()
            return

        if self._pending_move_target is not None:
            self._move_pending_target(event.pos())
            event.accept()
            return

        if self._panning:
            pos = event.position()
            delta = pos - self._pan_start
            self._pan_start = pos
            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() - int(delta.x()))
            v.setValue(v.value() - int(delta.y()))
            event.accept()
            return

        if self._manual_drag_component is not None:
            scene_pos = self.mapToScene(event.pos())
            delta = scene_pos - self._manual_drag_start_scene_pos
            self._manual_drag_component.setPos(self._manual_drag_start_item_pos + delta)
            event.accept()
            return

        if self._wire_start is not None and self._temp_line is not None:
            start_pos = self._wire_start.scenePos()
            end_pos = self.mapToScene(event.pos())
            self._temp_line.setLine(QLineF(start_pos, end_pos))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and (
            event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.LeftButton
        ):
            self._panning = False
            self.set_pan_tool_active(self._pan_tool_active)
            event.accept()
            return

        if self._manual_drag_component is not None:
            component = self._manual_drag_component
            old_pos = self._manual_drag_start_item_pos
            new_pos = component.pos()
            self._manual_drag_component = None
            if new_pos != old_pos:
                self.components_moved.emit([(component, old_pos, new_pos)])
            event.accept()
            return

        if self._wire_start is not None:
            if self._temp_line is not None:
                self.scene().removeItem(self._temp_line)
                self._temp_line = None

            end_item = self.itemAt(event.pos())
            if (
                isinstance(end_item, TerminalItem)
                and end_item is not self._wire_start
                and end_item.component() is not self._wire_start.component()
                and not terminals_already_wired(self._wire_start, end_item)
            ):
                wire = WireItem(self._wire_start, end_item)
                self.wire_created.emit(wire)

            self._wire_start = None
            event.accept()
            return

        super().mouseReleaseEvent(event)
        if self._drag_start_positions:
            moves = [
                (comp, old_pos, comp.pos())
                for comp, old_pos in self._drag_start_positions.items()
                if comp.pos() != old_pos
            ]
            self._drag_start_positions = {}
            if moves:
                self.components_moved.emit(moves)

    # --- zoom -------------------------------------------------------------

    def wheelEvent(self, event):
        factor = self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
        self._apply_zoom(factor)
        event.accept()

    def zoom_in(self) -> None:
        self._apply_zoom(self.BUTTON_ZOOM_STEP, anchor_view_center=True)

    def zoom_out(self) -> None:
        self._apply_zoom(1 / self.BUTTON_ZOOM_STEP, anchor_view_center=True)

    def _apply_zoom(self, factor: float, anchor_view_center: bool = False) -> None:
        new_zoom = self._zoom * factor
        if not (self.MIN_ZOOM <= new_zoom <= self.MAX_ZOOM):
            return
        self._zoom = new_zoom
        if anchor_view_center:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.scale(factor, factor)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        else:
            self.scale(factor, factor)

    def zoom_to_fit(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            self.reset_zoom()
            return
        margin = 60
        rect = rect.adjusted(-margin, -margin, margin, margin)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def reset_zoom(self) -> None:
        self.resetTransform()
        self._zoom = 1.0

    # --- drag-and-drop of components from the palette --------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            comp_type = bytes(event.mimeData().data(MIME_TYPE)).decode("utf-8")
            self._show_drag_preview(comp_type, event.position().toPoint())
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            self._move_drag_preview(event.position().toPoint())
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._clear_drag_preview()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._clear_drag_preview()
        if event.mimeData().hasFormat(MIME_TYPE):
            comp_type = bytes(event.mimeData().data(MIME_TYPE)).decode("utf-8")
            scene_pos = self.mapToScene(event.position().toPoint())
            self.component_dropped.emit(comp_type, scene_pos, 0.0)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _show_drag_preview(self, component_type: str, viewport_pos) -> None:
        # Drawn as a real (vector) ComponentItem rather than a rasterized
        # pixmap, so it stays crisp at any zoom level instead of pixelating -
        # it's non-interactive and never added to the undo stack or circuit
        # model, purely a visual stand-in until the user clicks to place it.
        self._clear_drag_preview()
        preview = ComponentItem(component_type)
        preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        preview.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        preview.setOpacity(0.45)
        preview.setZValue(20)
        for terminal in preview.terminals:
            terminal.setAcceptHoverEvents(False)
            terminal.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene().addItem(preview)
        self._drag_preview = preview
        self._move_drag_preview(viewport_pos)

    def _move_drag_preview(self, viewport_pos) -> None:
        if self._drag_preview is None:
            return
        scene_pos = self.mapToScene(viewport_pos)
        snapped = QPointF(
            round(scene_pos.x() / GRID_SIZE) * GRID_SIZE,
            round(scene_pos.y() / GRID_SIZE) * GRID_SIZE,
        )
        self._drag_preview.setPos(snapped)

    def _clear_drag_preview(self) -> None:
        if self._drag_preview is not None:
            self.scene().removeItem(self._drag_preview)
            self._drag_preview = None
