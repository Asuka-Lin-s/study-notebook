# -*- coding: utf-8 -*-
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor
from PySide6.QtWidgets import QTextEdit
from widgets import ResizeHandle

class SearchMixin:
    def set_sidebar_visible(self, visible):
        if visible:
            self.sidebar.show()
            sizes = self.splitter.sizes()
            right = max(1, sizes[1] if len(sizes) > 1 else self.width() - self._last_sidebar_width)
            self.splitter.setSizes([max(210, self._last_sidebar_width), right])
            self.titlebar.sidebar_btn.setToolTip("隐藏笔记目录  Ctrl+Shift+L")
        else:
            sizes = self.splitter.sizes()
            if sizes and sizes[0] > 0:
                self._last_sidebar_width = sizes[0]
            self.sidebar.hide()
            self.titlebar.sidebar_btn.setToolTip("显示笔记目录  Ctrl+Shift+L")
        self.save_settings()

    def on_search_text_changed(self, text):
        self.refresh_note_list()
        self.rebuild_search_matches(text)
        self.highlight_search_keyword(text)

    def rebuild_search_matches(self, keyword=None):
        if keyword is None:
            keyword = self.search_box.text()
        keyword = keyword.strip()
        self.search_positions = {}
        self.search_indices = {}
        for note_id, editor in self.open_editors.items():
            positions = []
            if keyword:
                doc = editor.document()
                cursor = QTextCursor(doc)
                while True:
                    cursor = doc.find(keyword, cursor)
                    if cursor.isNull():
                        break
                    positions.append((cursor.selectionStart(), cursor.selectionEnd()))
            self.search_positions[note_id] = positions
            self.search_indices[note_id] = -1

    def highlight_search_keyword(self, keyword=None):
        if keyword is None:
            keyword = self.search_box.text()
        keyword = keyword.strip()
        for note_id, editor in self.open_editors.items():
            selections = []
            positions = self.search_positions.get(note_id, [])
            normal_fmt = QTextCharFormat()
            normal_fmt.setBackground(QColor(255, 235, 120))
            normal_fmt.setForeground(QColor(20, 20, 20))
            current_fmt = QTextCharFormat()
            current_fmt.setBackground(QColor(255, 170, 70))
            current_fmt.setForeground(QColor(10, 10, 10))
            current_index = self.search_indices.get(note_id, -1)
            for i, (start, end) in enumerate(positions):
                cursor = QTextCursor(editor.document())
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format = current_fmt if i == current_index else normal_fmt
                selections.append(selection)
            editor.setExtraSelections(selections)

    def _current_search_context(self):
        editor = self.current_editor()
        keyword = self.search_box.text().strip()
        if not editor or not keyword:
            return None, None, []
        note_id = editor.note_id
        if note_id not in self.search_positions:
            self.rebuild_search_matches(keyword)
        positions = self.search_positions.get(note_id, [])
        return editor, note_id, positions

    def search_next_match(self):
        editor, note_id, positions = self._current_search_context()
        if not editor:
            return
        if not positions:
            self.status.setText("当前笔记没有匹配内容")
            return
        idx = self.search_indices.get(note_id, -1)
        idx = (idx + 1) % len(positions)
        self.search_indices[note_id] = idx
        self._focus_search_match(editor, note_id, idx, positions)

    def search_previous_match(self):
        editor, note_id, positions = self._current_search_context()
        if not editor:
            return
        if not positions:
            self.status.setText("当前笔记没有匹配内容")
            return
        idx = self.search_indices.get(note_id, -1)
        if idx < 0:
            idx = 0
        idx = (idx - 1) % len(positions)
        self.search_indices[note_id] = idx
        self._focus_search_match(editor, note_id, idx, positions)

    def _focus_search_match(self, editor, note_id, idx, positions):
        start, end = positions[idx]
        cursor = QTextCursor(editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        editor.setFocus()
        self.highlight_search_keyword()
        self.status.setText("搜索匹配：%d / %d" % (idx + 1, len(positions)))

    def create_resize_handles(self):
        self.resize_handles = {
            "left": ResizeHandle(self, ("left",), self),
            "right": ResizeHandle(self, ("right",), self),
            "top": ResizeHandle(self, ("top",), self),
            "bottom": ResizeHandle(self, ("bottom",), self),
            "lt": ResizeHandle(self, ("left", "top"), self),
            "rt": ResizeHandle(self, ("right", "top"), self),
            "lb": ResizeHandle(self, ("left", "bottom"), self),
            "rb": ResizeHandle(self, ("right", "bottom"), self),
        }
        for handle in self.resize_handles.values():
            handle.raise_()

    def position_resize_handles(self):
        if not hasattr(self, "resize_handles"):
            return
        w, h = self.width(), self.height()
        edge = 5
        corner = 10
        self.resize_handles["left"].setGeometry(0, corner, edge, max(0, h - corner * 2))
        self.resize_handles["right"].setGeometry(w - edge, corner, edge, max(0, h - corner * 2))
        self.resize_handles["top"].setGeometry(corner, 0, max(0, w - corner * 2), edge)
        self.resize_handles["bottom"].setGeometry(corner, h - edge, max(0, w - corner * 2), edge)
        self.resize_handles["lt"].setGeometry(0, 0, corner, corner)
        self.resize_handles["rt"].setGeometry(w - corner, 0, corner, corner)
        self.resize_handles["lb"].setGeometry(0, h - corner, corner, corner)
        self.resize_handles["rb"].setGeometry(w - corner, h - corner, corner, corner)
        for handle in self.resize_handles.values():
            handle.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_resize_handles()
