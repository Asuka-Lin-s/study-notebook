# -*- coding: utf-8 -*-
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSizeGrip, QTreeWidget, QSplitter, QTabWidget, QComboBox,
    QAbstractItemView
)
from config import DISPLAY_NAME
from widgets import TitleBar, SearchLineEdit
from mixin_search import SearchMixin
from mixin_notes import NotesMixin
from mixin_save import SaveCaptureMixin
from mixin_window import WindowMixin
from mixin_format import FormatMixin


class MainWindow(SearchMixin, NotesMixin, SaveCaptureMixin, WindowMixin, FormatMixin, QMainWindow):
    SNAP_DISTANCE = 22
    HIDDEN_STRIP = 7

    def __init__(self):
        super().__init__()
        self.edge = None
        self.is_edge_hidden = False
        self.last_inside_time = time.time()
        self.snip = None
        self.notes_index = {}
        self.open_editors = {}
        self.search_positions = {}
        self.search_indices = {}
        self.tree_items = {}

        self.setWindowTitle(DISPLAY_NAME)
        self.setMinimumSize(430, 300)
        self.resize(980, 700)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet("""
            QWidget#root {
                background: #fbfbfb;
                border: 1px solid #cfcfcf;
            }
        """)
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.titlebar = TitleBar(self)
        outer.addWidget(self.titlebar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.splitter, 1)

        self.sidebar = QWidget()
        self.sidebar.setMinimumWidth(210)
        self.sidebar.setMaximumWidth(380)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        sidebar_layout.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self.search_box = SearchLineEdit()
        self.search_box.setPlaceholderText("搜索标题或正文…")
        self.search_box.setClearButtonEnabled(True)
        self.search_prev_btn = QPushButton("↑")
        self.search_prev_btn.setFixedWidth(34)
        self.search_prev_btn.setToolTip("上一个匹配  Shift+Enter / Shift+F3")
        self.search_next_btn = QPushButton("↓")
        self.search_next_btn.setFixedWidth(34)
        self.search_next_btn.setToolTip("下一个匹配  Enter / F3")
        search_row.addWidget(self.search_box, 1)
        search_row.addWidget(self.search_prev_btn)
        search_row.addWidget(self.search_next_btn)
        sidebar_layout.addLayout(search_row)

        create_row = QHBoxLayout()
        self.sidebar_new_btn = QPushButton("+ 笔记")
        self.folder_btn = QPushButton("+ 文件夹")
        create_row.addWidget(self.sidebar_new_btn)
        create_row.addWidget(self.folder_btn)
        sidebar_layout.addLayout(create_row)

        manage_row = QHBoxLayout()
        self.rename_btn = QPushButton("重命名")
        self.delete_btn = QPushButton("删除")
        manage_row.addWidget(self.rename_btn)
        manage_row.addWidget(self.delete_btn)
        sidebar_layout.addLayout(manage_row)

        self.note_list = QTreeWidget()
        self.note_list.setHeaderHidden(True)
        self.note_list.setIndentation(18)
        self.note_list.setAnimated(True)
        self.note_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.note_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.note_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.note_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.note_list.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #d8d8d8;
                background: #f7f7f7;
                outline: none;
            }
            QTreeWidget::item {
                min-height: 28px;
                padding: 3px 5px;
            }
            QTreeWidget::item:selected {
                background: #dbeafe;
                color: #111;
            }
        """)
        sidebar_layout.addWidget(self.note_list, 1)
        self.splitter.addWidget(self.sidebar)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)

        format_bar = QWidget()
        format_bar.setFixedHeight(38)
        format_bar.setStyleSheet("""
            QWidget { background: #f3f3f3; border-bottom: 1px solid #dddddd; }
            QComboBox { min-width: 125px; padding: 4px 8px; }
            QPushButton { padding: 4px 8px; }
            QLabel { color: #555; }
        """)
        format_layout = QHBoxLayout(format_bar)
        format_layout.setContentsMargins(10, 4, 10, 4)
        format_layout.setSpacing(6)
        format_layout.addWidget(QLabel("段落"))
        self.heading_combo = QComboBox()
        self.heading_combo.addItems(["正文", "H1 一级标题", "H2 二级标题", "H3 三级标题"])
        self.heading_combo.setToolTip("Ctrl+0 正文 / Ctrl+1~3 标题")
        format_layout.addWidget(self.heading_combo)

        self.fold_btn = QPushButton("折叠/展开")
        self.fold_btn.setToolTip("折叠或展开当前标题  Ctrl+Alt+[")
        self.expand_all_btn = QPushButton("全部展开")
        self.expand_all_btn.setToolTip("展开当前笔记全部标题  Ctrl+Alt+]")
        format_layout.addWidget(self.fold_btn)
        format_layout.addWidget(self.expand_all_btn)
        format_layout.addStretch()
        format_layout.addWidget(QLabel("Ctrl+0~3"))
        editor_layout.addWidget(format_bar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        editor_layout.addWidget(self.tabs)

        self.splitter.addWidget(editor_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([255, 725])

        bottom = QWidget()
        bottom.setFixedHeight(26)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(10, 0, 2, 1)
        self.status = QLabel("自动保存已开启")
        self.status.setStyleSheet("color: #777; font-size: 12px;")
        bottom_layout.addWidget(self.status)
        bottom_layout.addStretch()
        self.grip = QSizeGrip(bottom)
        self.grip.setFixedSize(20, 20)
        bottom_layout.addWidget(self.grip)
        outer.addWidget(bottom)

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(800)
        self.autosave_timer.timeout.connect(self.save_all_open_notes)

        self.edge_timer = QTimer(self)
        self.edge_timer.setInterval(120)
        self.edge_timer.timeout.connect(self.check_edge_behavior)
        self.edge_timer.start()

        self.sidebar_new_btn.clicked.connect(self.create_new_note)
        self.folder_btn.clicked.connect(self.create_new_folder)
        self.rename_btn.clicked.connect(self.rename_selected_note)
        self.delete_btn.clicked.connect(self.delete_selected_note)
        self.search_box.textChanged.connect(self.on_search_text_changed)
        self.search_box.search_next.connect(self.search_next_match)
        self.search_box.search_previous.connect(self.search_previous_match)
        self.search_prev_btn.clicked.connect(self.search_previous_match)
        self.search_next_btn.clicked.connect(self.search_next_match)
        self.note_list.itemClicked.connect(self.open_note_from_item)
        self.note_list.customContextMenuRequested.connect(self.show_note_context_menu)
        self.note_list.itemExpanded.connect(self.on_tree_item_expanded)
        self.note_list.itemCollapsed.connect(self.on_tree_item_collapsed)
        self.note_list.model().rowsMoved.connect(self.sync_tree_hierarchy)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.sync_list_selection_to_tab)
        self.tabs.currentChanged.connect(self.sync_heading_combo)
        self.heading_combo.activated.connect(self.apply_heading_level)
        self.fold_btn.clicked.connect(self.toggle_current_heading_fold)
        self.expand_all_btn.clicked.connect(self.expand_all_headings)

        self._last_sidebar_width = 255
        self.create_resize_handles()

        self.install_shortcuts()
        self.load_settings()
        self.load_index()
        self.migrate_legacy_note()
        self.refresh_note_list()
        self.open_initial_note()

    def install_shortcuts(self):
        save_action = QAction(self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_current_note)
        self.addAction(save_action)

        export_action = QAction(self)
        export_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_action.triggered.connect(self.export_current_note)
        self.addAction(export_action)

        capture_action = QAction(self)
        capture_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        capture_action.triggered.connect(self.start_capture)
        self.addAction(capture_action)

        new_action = QAction(self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.create_new_note)
        self.addAction(new_action)

        search_action = QAction(self)
        search_action.setShortcut(QKeySequence.StandardKey.Find)
        search_action.triggered.connect(lambda: self.search_box.setFocus())
        self.addAction(search_action)

        sidebar_action = QAction(self)
        sidebar_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        sidebar_action.triggered.connect(
            lambda: self.titlebar.sidebar_btn.setChecked(
                not self.titlebar.sidebar_btn.isChecked()
            )
        )
        self.addAction(sidebar_action)

        next_search_action = QAction(self)
        next_search_action.setShortcut(QKeySequence("F3"))
        next_search_action.triggered.connect(self.search_next_match)
        self.addAction(next_search_action)

        prev_search_action = QAction(self)
        prev_search_action.setShortcut(QKeySequence("Shift+F3"))
        prev_search_action.triggered.connect(self.search_previous_match)
        self.addAction(prev_search_action)

        fold_action = QAction(self)
        fold_action.setShortcut(QKeySequence("Ctrl+Alt+["))
        fold_action.triggered.connect(self.toggle_current_heading_fold)
        self.addAction(fold_action)

        expand_action = QAction(self)
        expand_action.setShortcut(QKeySequence("Ctrl+Alt+]"))
        expand_action.triggered.connect(self.expand_all_headings)
        self.addAction(expand_action)

        for level in range(4):
            action = QAction(self)
            action.setShortcut(QKeySequence("Ctrl+%d" % level))
            action.triggered.connect(lambda checked=False, lv=level: self.apply_heading_level(lv))
            self.addAction(action)
