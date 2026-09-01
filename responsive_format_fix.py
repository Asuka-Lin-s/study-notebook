# -*- coding: utf-8 -*-
"""让正文格式工具栏随窗口宽度自动换行，而不是被裁掉。"""
from PySide6.QtCore import Qt, QRect, QSize, QPoint
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLayout, QSizePolicy
)
from main_window import MainWindow


class FlowLayout(QLayout):
    """简单稳定的流式布局：一行放不下时自动换到下一行。"""

    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=4):
        super().__init__(parent)
        self._items = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = area.x()
        y = area.y()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._hspacing

            if line_height > 0 and next_x - self._hspacing > area.right() + 1:
                x = area.x()
                y += line_height + self._vspacing
                next_x = x + hint.width() + self._hspacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


def _make_group(parent, label_text, control):
    group = QWidget(parent)
    layout = QHBoxLayout(group)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    if label_text:
        label = QLabel(label_text, group)
        label.setStyleSheet("color: #555; border: none;")
        layout.addWidget(label)
    layout.addWidget(control)
    group.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return group


_original_init = MainWindow.__init__


def _responsive_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)

    old_bar = self.heading_combo.parentWidget()
    if old_bar is None:
        return
    editor_panel = old_bar.parentWidget()
    if editor_panel is None or editor_panel.layout() is None:
        return

    editor_layout = editor_panel.layout()
    insert_at = editor_layout.indexOf(old_bar)

    flow_bar = QWidget(editor_panel)
    flow_bar.setObjectName("responsiveFormatBar")
    flow_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    flow_bar.setStyleSheet("""
        QWidget#responsiveFormatBar {
            background: #f3f3f3;
            border-bottom: 1px solid #dddddd;
        }
        QComboBox, QFontComboBox, QSpinBox {
            padding: 4px 6px;
        }
        QPushButton {
            padding: 4px 8px;
        }
    """)

    flow = FlowLayout(flow_bar, margin=6, hspacing=6, vspacing=4)

    # 每个标签和它对应的控件绑成一个组，换行时不会拆散。
    paragraph_group = _make_group(flow_bar, "段落", self.heading_combo)
    font_group = _make_group(flow_bar, "字体", self.font_combo)

    # 缩小一点控件的刚性宽度，使中等窗口下尽量保持一行。
    self.heading_combo.setMinimumWidth(100)
    self.font_combo.setMinimumWidth(115)
    self.font_combo.setMaximumWidth(175)

    flow.addWidget(paragraph_group)
    flow.addWidget(font_group)
    flow.addWidget(self.font_size_box)
    flow.addWidget(self.text_color_btn)
    flow.addWidget(self.fold_btn)
    flow.addWidget(self.expand_all_btn)

    editor_layout.removeWidget(old_bar)
    old_bar.hide()
    old_bar.setParent(None)
    editor_layout.insertWidget(max(0, insert_at), flow_bar)

    self.responsive_format_bar = flow_bar
    self.responsive_format_layout = flow


MainWindow.__init__ = _responsive_init
