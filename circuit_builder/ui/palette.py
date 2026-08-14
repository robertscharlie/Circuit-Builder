from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from circuit_builder.core.components import COMPONENT_TYPES
from circuit_builder.ui.component_item import render_symbol_pixmap

MIME_TYPE = "application/x-circuit-component-type"
ICON_ROW_HEIGHT = 26
ICON_SWATCH_PADDING = 10


class ComponentPalette(QListWidget):
    """Sidebar list of component types the user can drag onto the canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        for key, meta in COMPONENT_TYPES.items():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.addItem(item)

            text = meta.display_name if not meta.unit else f"{meta.display_name} ({meta.unit})"

            # The symbol itself is drawn in dark ink (meant for the light
            # canvas background) - undrawn against this panel's dark theme
            # it's all but invisible, so give it its own light swatch card.
            # Sized to the scaled pixmap's own dimensions (plus padding)
            # rather than a fixed square - components are wider than tall,
            # so a square box either clips them or leaves it half-empty.
            pixmap = render_symbol_pixmap(key).scaledToHeight(
                ICON_ROW_HEIGHT, Qt.TransformationMode.SmoothTransformation
            )
            icon_label = QLabel()
            icon_label.setObjectName("paletteIconSwatch")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setFixedSize(
                pixmap.width() + ICON_SWATCH_PADDING, ICON_ROW_HEIGHT + ICON_SWATCH_PADDING
            )
            icon_label.setPixmap(pixmap)

            key_badge = QLabel(meta.shortcut)
            key_badge.setObjectName("shortcutBadge")
            key_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_badge.setFixedSize(18, 18)
            key_badge.setToolTip(f"Press {meta.shortcut} to place a {meta.display_name.lower()}")

            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 4, 8, 4)
            layout.setSpacing(8)
            layout.addWidget(QLabel(text))
            layout.addStretch()
            layout.addWidget(key_badge)
            layout.addWidget(icon_label)

            item.setSizeHint(row.sizeHint())
            self.setItemWidget(item, row)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        comp_type = item.data(Qt.ItemDataRole.UserRole)

        mime = QMimeData()
        mime.setData(MIME_TYPE, QByteArray(comp_type.encode("utf-8")))

        pixmap = render_symbol_pixmap(comp_type)
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)
