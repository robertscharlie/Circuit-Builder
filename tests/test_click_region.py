import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from circuit_builder.ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.resize(900, 500)
window.show()
view = window.view

r1 = window.add_component("resistor", QPointF(0, 0))
j1 = window.add_component("junction", QPointF(200, 0))
app.processEvents()

# boundingRect() is a big square (half=46 for regular components, half=14
# for a Node) so it stays rotation-invariant for the fixed-offset label -
# but hit-testing must use the tighter _outline_rect() via shape(), or
# clicks well outside the visible symbol would still select the component.

far_above = view.itemAt(view.mapFromScene(QPointF(0, -30)))
assert far_above is not r1, "should not select the resistor from 30px above its center (outside its outline)"

on_body = view.itemAt(view.mapFromScene(QPointF(0, 0)))
assert on_body is r1, "clicking the actual body should still select it"

on_lead = view.itemAt(view.mapFromScene(QPointF(-25, 0)))
assert on_lead is r1, "clicking the lead stub (still within the outline) should still select it"
print("1. clicks outside a component's visible outline no longer select it: OK")

far_from_node = view.itemAt(view.mapFromScene(QPointF(200, 12)))
assert far_from_node is not j1, "should not select the node from 12px away (outside its tight outline)"

near_node = view.itemAt(view.mapFromScene(QPointF(200, 7)))
assert near_node is j1, "clicking within the node's tight outline should still select it"
print("2. same for a Node's smaller outline: OK")

print("ALL CLICK-REGION TESTS PASSED")
