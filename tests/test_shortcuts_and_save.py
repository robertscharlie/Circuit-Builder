import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.component_item import ComponentItem

app = QApplication(sys.argv)


def mev(t, pos, button, buttons):
    return QMouseEvent(t, QPointF(pos), QPointF(pos), button, buttons, Qt.KeyboardModifier.NoModifier)


# --- 1. Placement mode: shortcut -> ghost follows cursor -> click places ---
window = MainWindow()
window.resize(1000, 600)
window.show()
app.processEvents()
view = window.view

view.start_placement("capacitor")
assert view._pending_place_type == "capacitor"
assert view._drag_preview is not None
app.processEvents()

click_vp = view.mapFromScene(QPointF(200, 100))
view.mousePressEvent(mev(QEvent.Type.MouseButtonPress, click_vp, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton))
app.processEvents()

comps = [i for i in window.scene.items() if isinstance(i, ComponentItem)]
assert len(comps) == 1, f"expected 1 component placed, got {len(comps)}"
assert comps[0].component_type == "capacitor"
assert view._pending_place_type is None, "placement mode should exit after placing"
assert view._drag_preview is None, "ghost preview should be cleared after placing"
print("1. keyboard placement mode places a component and exits: OK")

# --- 2. Escape cancels placement without placing ----------------------------
view.start_placement("inductor")
assert view._pending_place_type == "inductor"
from PySide6.QtGui import QKeyEvent
esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
view.keyPressEvent(esc)
assert view._pending_place_type is None, "Escape should cancel placement mode"
assert view._drag_preview is None
comps_after = [i for i in window.scene.items() if isinstance(i, ComponentItem)]
assert len(comps_after) == 1, "Escape should not have placed anything"
print("2. Escape cancels placement mode: OK")

# --- 3. Component-type shortcut QActions exist with correct keys -----------
from circuit_builder.core.components import COMPONENT_TYPES
shortcut_map = {a.shortcut().toString(): a for a in window._placement_actions}
for comp_type, meta in COMPONENT_TYPES.items():
    assert meta.shortcut in shortcut_map, f"no action bound to shortcut {meta.shortcut}"
print("3. placement shortcut actions registered for all component types: OK")

# window has a placed capacitor (dirty stack) - patch the prompt so closing
# it doesn't block on a real modal dialog.
_question_orig_for_window1 = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
try:
    window.close()
finally:
    QMessageBox.question = _question_orig_for_window1

# --- 4. Save-prompt: clean stack closes without any dialog -------------------
window2 = MainWindow()
assert window2.undo_stack.isClean()
event = QCloseEvent()
window2.closeEvent(event)
assert event.isAccepted(), "closing a clean (unmodified) window should not prompt and should accept"
print("4. clean window closes without prompting: OK")

# --- 5. Save-prompt: dirty stack + Discard -> proceeds without saving --------
window3 = MainWindow()
window3._on_component_dropped("resistor", QPointF(0, 0))
assert not window3.undo_stack.isClean()

original_question = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
try:
    event3 = QCloseEvent()
    window3.closeEvent(event3)
    assert event3.isAccepted(), "Discard should allow the window to close"
finally:
    QMessageBox.question = original_question
print("5. dirty window + Discard closes without saving: OK")

# --- 6. Save-prompt: dirty stack + Cancel -> blocks the close -----------------
window4 = MainWindow()
window4._on_component_dropped("resistor", QPointF(0, 0))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel)
try:
    event4 = QCloseEvent()
    window4.closeEvent(event4)
    assert not event4.isAccepted(), "Cancel should block the window from closing"
finally:
    QMessageBox.question = original_question
print("6. dirty window + Cancel blocks close: OK")

# --- 7. Save-prompt: dirty stack + Save -> writes file and proceeds ----------
import os
save_path = os.path.join(os.path.dirname(__file__), "test_save_prompt.json")
window5 = MainWindow()
window5._on_component_dropped("battery", QPointF(0, 0))
window5._current_path = None


def fake_get_save_file_name(*args, **kwargs):
    return save_path, "Circuit Files (*.json)"


from PySide6.QtWidgets import QFileDialog
original_save_dialog = QFileDialog.getSaveFileName
QFileDialog.getSaveFileName = staticmethod(fake_get_save_file_name)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save)
try:
    event5 = QCloseEvent()
    window5.closeEvent(event5)
    assert event5.isAccepted(), "Save should allow the window to close"
    assert os.path.exists(save_path), "Save should have written the file"
    assert window5.undo_stack.isClean(), "stack should be clean after a successful save"
finally:
    QMessageBox.question = original_question
    QFileDialog.getSaveFileName = original_save_dialog
    if os.path.exists(save_path):
        os.remove(save_path)
print("7. dirty window + Save writes file and closes: OK")

# --- 8. Window title shows unsaved-changes indicator -------------------------
window6 = MainWindow()
title_clean = window6.windowTitle()
assert "*" not in title_clean, f"clean window title should have no asterisk: {title_clean!r}"
window6._on_component_dropped("resistor", QPointF(0, 0))
app.processEvents()
title_dirty = window6.windowTitle()
assert title_dirty.startswith("*"), f"dirty window title should start with *: {title_dirty!r}"
window6.undo_stack.undo()
app.processEvents()
title_after_undo = window6.windowTitle()
assert "*" not in title_after_undo, f"undoing back to the clean state should drop the *: {title_after_undo!r}"
print("8. window title reflects unsaved-changes state: OK")

print("ALL SHORTCUT/SAVE-PROMPT TESTS PASSED")
