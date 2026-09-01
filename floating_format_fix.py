# -*- coding: utf-8 -*-
"""把正文格式栏改成可停靠、可悬浮、可隐藏的 QToolBar。"""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolBar, QLabel, QPushButton
from config import SETTINGS_FILE
from main_window import MainWindow


_original_init = MainWindow.__init__
_original_save_settings = MainWindow.save_settings


def _read_toolbar_state():
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return (
                bool(data.get("format_toolbar_visible", True)),
                bool(data.get("format_toolbar_floating", False)),
            )
    except Exception:
        pass
    return True, False


def _save_settings_with_toolbar(self):
    _original_save_settings(self)
    if not hasattr(self, "format_toolbar"):
        return
    try:
        data = {}
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        data["format_toolbar_visible"] = self.format_toolbar.isVisible()
        data["format_toolbar_floating"] = self.format_toolbar.isFloating()
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _floating_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)

    # 原来的固定格式栏只是控件容器；把控件迁移到 QToolBar 后移除它。
    old_bar = self.heading_combo.parentWidget()
    if old_bar is None:
        return
    old_layout_parent = old_bar.parentWidget()
    old_layout = old_layout_parent.layout() if old_layout_parent else None

    toolbar = QToolBar("正文格式", self)
    toolbar.setObjectName("formatToolbar")
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(
        Qt.ToolBarArea.TopToolBarArea |
        Qt.ToolBarArea.BottomToolBarArea |
        Qt.ToolBarArea.LeftToolBarArea |
        Qt.ToolBarArea.RightToolBarArea
    )
    toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    toolbar.setStyleSheet("""
        QToolBar {
            spacing: 5px;
            padding: 3px 5px;
            background: #f3f3f3;
            border: none;
            border-bottom: 1px solid #dddddd;
        }
        QToolBar QLabel { color: #555; padding-left: 3px; }
        QToolBar QComboBox, QToolBar QFontComboBox, QToolBar QSpinBox {
            padding: 3px 5px;
        }
        QToolBar QPushButton { padding: 4px 7px; }
    """)

    # QToolBar 在空间不足时会自动出现 » 扩展按钮，不会增加高度。
    toolbar.addWidget(QLabel("段落", toolbar))
    self.heading_combo.setParent(toolbar)
    self.heading_combo.setMinimumWidth(105)
    toolbar.addWidget(self.heading_combo)

    toolbar.addSeparator()
    toolbar.addWidget(QLabel("字体", toolbar))
    self.font_combo.setParent(toolbar)
    self.font_combo.setMinimumWidth(120)
    self.font_combo.setMaximumWidth(175)
    toolbar.addWidget(self.font_combo)

    self.font_size_box.setParent(toolbar)
    toolbar.addWidget(self.font_size_box)

    self.text_color_btn.setParent(toolbar)
    toolbar.addWidget(self.text_color_btn)

    toolbar.addSeparator()
    self.fold_btn.setParent(toolbar)
    toolbar.addWidget(self.fold_btn)

    self.expand_all_btn.setParent(toolbar)
    toolbar.addWidget(self.expand_all_btn)

    if old_layout is not None:
        old_layout.removeWidget(old_bar)
    old_bar.hide()
    old_bar.deleteLater()

    self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
    self.format_toolbar = toolbar

    # 标题栏始终留一个“格式”开关；工具栏隐藏后也能随时叫回来。
    format_btn = QPushButton("格式", self.titlebar)
    format_btn.setCheckable(True)
    format_btn.setToolTip("显示/隐藏正文格式栏；格式栏也可以拖出窗口悬浮")
    self.titlebar.layout().insertWidget(
        max(0, self.titlebar.layout().indexOf(self.titlebar.sidebar_btn)),
        format_btn,
    )
    self.titlebar.format_btn = format_btn

    format_btn.toggled.connect(toolbar.setVisible)
    toolbar.visibilityChanged.connect(format_btn.setChecked)
    toolbar.visibilityChanged.connect(lambda _=False: self.save_settings())
    toolbar.topLevelChanged.connect(lambda _=False: self.save_settings())

    visible, floating = _read_toolbar_state()
    format_btn.blockSignals(True)
    format_btn.setChecked(visible)
    format_btn.blockSignals(False)
    toolbar.setVisible(visible)

    # 恢复悬浮状态。位置由 Qt 自己选择，避免保存无效的屏幕坐标。
    if floating:
        toolbar.setFloating(True)

    self.format_toolbar_toggle_action = toolbar.toggleViewAction()


MainWindow.save_settings = _save_settings_with_toolbar
MainWindow.__init__ = _floating_init
