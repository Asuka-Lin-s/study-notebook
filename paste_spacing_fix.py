# -*- coding: utf-8 -*-
"""粘贴富文本时统一段落行距和段前/段后，避免网页/Word样式把行距带乱。"""
from PySide6.QtGui import QTextCursor, QTextBlockFormat
from widgets import NoteEditor


_original_insert_from_mime_data = NoteEditor.insertFromMimeData


def _normalize_block_spacing(editor, start_pos, end_pos):
    document = editor.document()
    if document is None:
        return

    start = max(0, min(int(start_pos), document.characterCount() - 1))
    end = max(start, min(int(end_pos), document.characterCount() - 1))
    end_probe = max(start, end - 1)

    start_cursor = QTextCursor(document)
    start_cursor.setPosition(start)
    block = start_cursor.block()

    end_cursor = QTextCursor(document)
    end_cursor.setPosition(end_probe)
    end_block = end_cursor.block()

    while block.isValid():
        cursor = QTextCursor(block)
        fmt = cursor.blockFormat()

        # 清除外部网页/Word带进来的自定义 line-height。
        # 100% = 使用当前字体自身的正常单行高度。
        fmt.setLineHeight(
            100.0,
            QTextBlockFormat.LineHeightTypes.ProportionalHeight,
        )

        # 段前段后只使用本软件自己的规则。
        try:
            level = int(fmt.headingLevel())
        except Exception:
            level = 0

        if level == 1:
            fmt.setTopMargin(8)
            fmt.setBottomMargin(4)
        elif level in (2, 3):
            fmt.setTopMargin(5)
            fmt.setBottomMargin(4)
        else:
            fmt.setTopMargin(0)
            fmt.setBottomMargin(0)

        cursor.setBlockFormat(fmt)

        if block == end_block:
            break
        block = block.next()


def _insert_from_mime_data(self, source):
    # 图片沿用原来的截图/图片保存逻辑。
    if source.hasImage():
        return _original_insert_from_mime_data(self, source)

    cursor_before = self.textCursor()
    insert_start = cursor_before.selectionStart()

    _original_insert_from_mime_data(self, source)

    insert_end = self.textCursor().position()
    if insert_end < insert_start:
        insert_start, insert_end = insert_end, insert_start

    # 无论来源是网页、Word、其他富文本编辑器还是普通文本，
    # 只规范新粘贴区域的段落间距，不碰字符级字体/颜色/粗体等格式。
    _normalize_block_spacing(self, insert_start, insert_end)
    self.apply_fold_visibility()
    self.viewport().update()


NoteEditor.insertFromMimeData = _insert_from_mime_data
