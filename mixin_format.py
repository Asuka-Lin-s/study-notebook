# -*- coding: utf-8 -*-
from PySide6.QtGui import QTextCursor, QTextCharFormat, QFont


class FormatMixin:
    """正文段落级格式：正文 / H1 / H2 / H3，以及标题折叠状态。"""

    HEADING_SIZES = {
        0: 11.0,
        1: 20.0,
        2: 16.0,
        3: 13.5,
    }

    def attach_format_tracking(self, editor):
        editor.cursorPositionChanged.connect(self.sync_heading_combo)

        # 折叠状态单独保存在索引中；正文 HTML 始终保持完整。
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

        # 修改标题结构前先展开，避免正在编辑隐藏块产生不可预期的位置关系。
        editor.expand_all_headings()

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
