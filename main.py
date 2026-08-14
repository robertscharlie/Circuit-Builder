from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from circuit_builder.ui.main_window import MainWindow
from circuit_builder.ui.theme import apply_theme


def main() -> None:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
