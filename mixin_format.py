# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QFont, QColor
from PySide6.QtWidgets import QColorDialog


class FormatMixin:
    """正文格式：标题层级、折叠状态、字体、字号和文字颜色。"""

    HEADING_SIZES = {
        0: 11.0,
        1: 20.0,
        2: 16.0,
        3: 13.5,
    }

    def attach_format_tracking(self, editor):
        editor.cursorPositionChanged.connect(self.sync_heading_combo)
        editor.cursorPositionChanged.connect(self.sync_text_format_controls)

        info = self.notes_index.get(editor.note_id, {})
        editor.set_folded_heading_keys(info.get("folded_headings", []))
        editor.fold_state_changed.connect(
            lambda note_id=editor.note_id, e=editor: self.save_heading_fold_state(note_id, e)
        )

    def save_heading_fold_state(self, note_id, editor=None):
        if editor is None:
            editor = self.open_editors.get(note_id)
        if not editor or note_id not in self.notes_index:
            return
        self.notes_index[note_id]["folded_headings"] = editor.folded_heading_keys_list()
        self.save_index()

    def toggle_current_heading_fold(self):
        editor = self.current_editor()
        if not editor:
            return
        if editor.toggle_current_heading_fold():
            self.status.setText("已切换当前标题折叠状态")
        else:
            self.status.setText("当前位置没有可折叠标题")

    def expand_all_headings(self):
        editor = self.current_editor()
        if not editor:
            return
        editor.expand_all_headings()
        self.status.setText("已展开当前笔记全部标题")

    def _selected_blocks(self, editor):
        cursor = editor.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        if not cursor.hasSelection():
            return [cursor.block()]

        # 选区结束点如果刚好在下一段开头，不把下一段一起格式化。
        end_probe = max(start, end - 1)

        start_cursor = QTextCursor(editor.document())
        start_cursor.setPosition(start)
        block = start_cursor.block()

        end_cursor = QTextCursor(editor.document())
        end_cursor.setPosition(end_probe)
        end_block = end_cursor.block()

        blocks = []
        while block.isValid():
            blocks.append(block)
            if block == end_block:
                break
            block = block.next()
        return blocks

    def apply_heading_level(self, level):
        editor = self.current_editor()
        if not editor:
            return

        try:
            level = int(level)
        except Exception:
            level = 0
        level = max(0, min(3, level))

        # 修改可见段落的标题等级时，现有其它折叠区域保持原样。
        original = editor.textCursor()
        blocks = self._selected_blocks(editor)

        for block in blocks:
            block_cursor = QTextCursor(block)
            block_fmt = block_cursor.blockFormat()
            block_fmt.setHeadingLevel(level)
            if level == 0:
                block_fmt.setTopMargin(0)
                block_fmt.setBottomMargin(0)
            else:
                block_fmt.setTopMargin(8 if level == 1 else 5)
                block_fmt.setBottomMargin(4)
            block_cursor.setBlockFormat(block_fmt)

            # 只修改当前段落的字号和粗细，不覆盖用户自己设置的字体和颜色。
            text_cursor = QTextCursor(block)
            text_cursor.setPosition(block.position())
            text_end = block.position() + max(0, block.length() - 1)
            text_cursor.setPosition(text_end, QTextCursor.MoveMode.KeepAnchor)

            char_fmt = QTextCharFormat()
            char_fmt.setFontPointSize(self.HEADING_SIZES[level])
            char_fmt.setFontWeight(
                int(QFont.Weight.Bold if level else QFont.Weight.Normal)
            )
            if text_end > block.position():
                text_cursor.mergeCharFormat(char_fmt)

        editor.setTextCursor(original)
        editor.setFocus()
        editor.apply_fold_visibility()
        self.schedule_save()
        self.sync_heading_combo()
        self.sync_text_format_controls()
        labels = ["正文", "H1 一级标题", "H2 二级标题", "H3 三级标题"]
        self.status.setText("段落格式：" + labels[level])

    # ---------- 字体 / 字号 / 颜色 ----------
    def _merge_character_format(self, fmt):
        editor = self.current_editor()
        if not editor:
            return

        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            editor.setTextCursor(cursor)
        editor.mergeCurrentCharFormat(fmt)
        editor.setFocus()
        self.schedule_save()
        self.sync_text_format_controls()

    def apply_font_family(self, font):
        family = font.family() if hasattr(font, "family") else str(font)
        if not family:
            return
        fmt = QTextCharFormat()
        # Qt 6 下只设置字体家族，不覆盖当前字号、颜色、粗细。
        fmt.setFontFamilies([family])
        self._merge_character_format(fmt)
        self.status.setText("字体：" + family)

    def apply_font_size(self, size):
        try:
            size = float(size)
        except Exception:
            return
        if size <= 0:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._merge_character_format(fmt)
        self.status.setText("字号：%g" % size)

    def choose_text_color(self):
        editor = self.current_editor()
        if not editor:
            return
        current = editor.textColor()
        if not current.isValid():
            current = QColor(Qt.GlobalColor.black)
        color = QColorDialog.getColor(current, self, "选择文字颜色")
        if not color.isValid():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        self._merge_character_format(fmt)
        self._set_color_button_preview(color)
        self.status.setText("文字颜色已修改")

    def _set_color_button_preview(self, color):
        if not hasattr(self, "text_color_btn") or not color.isValid():
            return
        self.text_color_btn.setStyleSheet(
            "QPushButton { padding: 4px 8px; border-bottom: 4px solid %s; }" % color.name()
        )

    def sync_text_format_controls(self, *args):
        """把光标处格式同步到工具栏。

        使用 QTextEdit 的高层接口读取字体，避免 PySide6 6.6.3.1 在
        QTextCharFormat.fontFamily()/fontFamilies() 上出现原生 access violation。
        """
        editor = self.current_editor()
        if not editor:
            return

        if hasattr(self, "font_combo"):
            current_font = editor.currentFont()
            family = current_font.family()
            if family:
                self.font_combo.blockSignals(True)
                self.font_combo.setCurrentFont(QFont(family))
                self.font_combo.blockSignals(False)

        if hasattr(self, "font_size_box"):
            size = editor.fontPointSize()
            if size <= 0:
                size = editor.currentFont().pointSizeF()
            if size <= 0:
                try:
                    heading_level = int(editor.textCursor().blockFormat().headingLevel())
                except Exception:
                    heading_level = 0
                size = self.HEADING_SIZES.get(max(0, min(3, heading_level)), 11.0)
            self.font_size_box.blockSignals(True)
            self.font_size_box.setValue(int(round(size)))
            self.font_size_box.blockSignals(False)

        color = editor.textColor()
        if color.isValid():
            self._set_color_button_preview(color)

    def sync_heading_combo(self, *args):
        if not hasattr(self, "heading_combo"):
            return
        editor = self.current_editor()
        level = 0
        if editor:
            try:
                level = int(editor.textCursor().blockFormat().headingLevel())
            except Exception:
                level = 0
        level = max(0, min(3, level))
        self.heading_combo.blockSignals(True)
        self.heading_combo.setCurrentIndex(level)
        self.heading_combo.blockSignals(False)
