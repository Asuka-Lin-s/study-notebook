# -*- coding: utf-8 -*-
import sys
from PySide6.QtCore import QTimer, QObject, QEvent
from PySide6.QtWidgets import QApplication
from config import DISPLAY_NAME
from main_window import MainWindow
import fold_fix  # noqa: F401  启动时安装正文嵌套折叠补丁
import text_style_fix  # noqa: F401  标题回车后恢复正文样式


class TreeDropWatcher(QObject):
    """拖放结束后再保存目录树，避免 Qt rowsMoved 偶发漏掉跨层级移动。"""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Drop:
            QTimer.singleShot(0, self.persist_tree)
        return False

    def persist_tree(self):
        if self.window.search_box.text().strip():
            return
        self.window.sync_tree_hierarchy()
        self.window.status.setText("目录层级已保存")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(DISPLAY_NAME)
    app.setStyle("Fusion")

    window = MainWindow()
    window.tree_drop_watcher = TreeDropWatcher(window)
    window.note_list.viewport().installEventFilter(window.tree_drop_watcher)

    window.show()
    window.restore_splitter()

    if window.edge:
        QTimer.singleShot(1200, window.hide_to_edge)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
