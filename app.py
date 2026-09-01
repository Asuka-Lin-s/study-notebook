# -*- coding: utf-8 -*-
import sys
from PySide6.QtCore import QTimer, QObject, QEvent
from PySide6.QtWidgets import QApplication
from config import DISPLAY_NAME
from main_window import MainWindow


class TreeDropWatcher(QObject):
    """拖放结束后再保存目录树，避免 Qt rowsMoved 偶发漏掉跨层级移动。"""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Drop:
            # Drop 事件处理完成以后，QTreeWidget 的父子关系才是最终状态。
            # 延迟到下一个事件循环再读取整棵树并持久化 parent/order。
            QTimer.singleShot(0, self.persist_tree)
        return False

    def persist_tree(self):
        # 搜索状态下树是过滤后的临时视图，不能拿它覆盖真实层级。
        if self.window.search_box.text().strip():
            return
        self.window.sync_tree_hierarchy()
        self.window.status.setText("目录层级已保存")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(DISPLAY_NAME)
    app.setStyle("Fusion")

    window = MainWindow()

    # QAbstractItemView 的拖放事件发生在 viewport 上。
    # 保留 watcher 引用，防止被 Python 垃圾回收。
    window.tree_drop_watcher = TreeDropWatcher(window)
    window.note_list.viewport().installEventFilter(window.tree_drop_watcher)

    window.show()
    window.restore_splitter()

    if window.edge:
        QTimer.singleShot(1200, window.hide_to_edge)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
