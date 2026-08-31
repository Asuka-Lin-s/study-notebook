# -*- coding: utf-8 -*-
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from config import DISPLAY_NAME
from main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(DISPLAY_NAME)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    window.restore_splitter()

    if window.edge:
        QTimer.singleShot(1200, window.hide_to_edge)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
