# -*- coding: utf-8 -*-
from PySide6.QtGui import QTextCursor, QTextCharFormat, QFont


class FormatMixin:
    """正文段落级格式：正文 / H1 / H2 / H3。"""

    HEADING_SIZES = {
        0: 11.0,
        1: 20.0,
        2: 16.0,
        3: 13.5,
    }

    def attach_format_tracking(self, editor):
        editor.cursorPositionChanged.connect(self.sync_heading_combo)

    def _selected_blocks(self, editor):
        cursor = editor.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        start_cursor = QTextCursor(editor.document())
        start_cursor.setPosition(start)
        block = start_cursor.block()

        blocks = []
        while block.isValid():
            blocks.append(block)
            if block.position() + block.length() - 1 >= end:
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

        original = editor.textCursor()
        blocks = self._selected_blocks(editor)

        for block in blocks:
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)

            block_fmt = cursor.blockFormat()
            block_fmt.setHeadingLevel(level)
            if level == 0:
                block_fmt.setTopMargin(0)
                block_fmt.setBottomMargin(0)
            else:
                block_fmt.setTopMargin(8 if level == 1 else 5)
                block_fmt.setBottomMargin(4)
            cursor.mergeBlockFormat(block_fmt)

            char_fmt = QTextCharFormat()
            char_fmt.setFontPointSize(self.HEADING_SIZES[level])
            char_fmt.setFontWeight(
                int(QFont.Weight.Bold if level else QFont.Weight.Normal)
            )
            cursor.mergeCharFormat(char_fmt)

        editor.setTextCursor(original)
        editor.setFocus()
        self.schedule_save()
        self.sync_heading_combo()
        labels = ["正文", "H1 一级标题", "H2 二级标题", "H3 三级标题"]
        self.status.setText("段落格式：" + labels[level])

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
