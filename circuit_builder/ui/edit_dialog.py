from __future__ import annotations

from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QWidget


class EditComponentDialog(QDialog):
    """Small popup for editing a component's label and value, opened on double-click."""

    def __init__(self, label: str, value: float, unit: str, show_value: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Component")
        layout = QFormLayout(self)

        self.label_edit = QLineEdit(label)
        layout.addRow("Label:", self.label_edit)

        # A plain validated line edit (rather than QDoubleSpinBox) so values
        # display cleanly at any magnitude - electrical values here range
        # from femtofarads to gigaohms, and a spin box's fixed decimal count
        # either pads small round numbers with zeros or truncates tiny ones.
        # Scientific notation is accepted too (e.g. "4.7e-9").
        self._show_value = show_value
        self._unchanged_value = value
        self.value_edit: QLineEdit | None = None
        if show_value:
            self.value_edit = QLineEdit(f"{value:g}")
            validator = QDoubleValidator(-1e12, 1e12, 12, self)
            validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
            self.value_edit.setValidator(validator)

            value_row = QWidget()
            value_layout = QHBoxLayout(value_row)
            value_layout.setContentsMargins(0, 0, 0, 0)
            value_layout.addWidget(self.value_edit)
            if unit:
                value_layout.addWidget(QLabel(unit))
            layout.addRow("Value:", value_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.label_edit.setFocus()
        self.label_edit.selectAll()

    def values(self) -> tuple[str, float]:
        if not self._show_value:
            return self.label_edit.text(), self._unchanged_value
        try:
            value = float(self.value_edit.text())
        except ValueError:
            value = 0.0
        return self.label_edit.text(), value
