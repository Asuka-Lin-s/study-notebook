# -*- coding: utf-8 -*-
"""标题回车后的正文样式与折叠行为修复。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QTextBlockFormat, QFont
from widgets import NoteEditor
from fold_fix import make_fold_break_text


_original_key_press = NoteEditor.keyPressEvent


def _fold_scope_end_block(editor, heading_block):
    """返回该标题折叠范围结束后的第一个块；若到文档末尾则返回无效块。"""
    level = editor.heading_level(heading_block)
    block = heading_block.next()
    while block.isValid():
        block_level = editor.heading_level(block)
        if block_level > 0 and block_level <= level:
            return block
        block = block.next()
    return block


def _apply_body_format(editor, cursor, family, old_char_fmt):
    block_fmt = cursor.blockFormat()
    block_fmt.setHeadingLevel(0)
    block_fmt.setTopMargin(0)
    block_fmt.setBottomMargin(0)
    cursor.setBlockFormat(block_fmt)

    fmt = QTextCharFormat()
    if family:
        fmt.setFontFamilies([family])
    if old_char_fmt is not None:
        color = old_char_fmt.foreground().color()
        if color.isValid():
            fmt.setForeground(color)
    fmt.setFontPointSize(11.0)
    fmt.setFontWeight(int(QFont.Weight.Normal))
    cursor.mergeCharFormat(fmt)
    editor.setCurrentCharFormat(fmt)
    editor.setTextCursor(cursor)


def _insert_after_collapsed_scope(editor, heading_block, family, old_char_fmt):
    level = editor.heading_level(heading_block)
    end_block = _fold_scope_end_block(editor, heading_block)
    doc = editor.document()

    cursor = QTextCursor(doc)
    cursor.beginEditBlock()

    if end_block.isValid():
        # 在下一个同级/更高级标题之前插入：
        # 边界块 + 新正文块，然后原标题继续保持原位。
        cursor.setPosition(end_block.position())
        cursor.insertText(make_fold_break_text(level))
        cursor.insertBlock()
        body_cursor = QTextCursor(cursor)
    else:
        # 折叠范围一直到文档末尾：在末尾追加边界块和正文块。
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if cursor.position() > 0:
            cursor.insertBlock()
        cursor.insertText(make_fold_break_text(level))
        cursor.insertBlock()
        body_cursor = QTextCursor(cursor)

    cursor.endEditBlock()
    _apply_body_format(editor, body_cursor, family, old_char_fmt)
    editor.apply_fold_visibility()
    editor.ensureCursorVisible()


def _key_press_event(self, event):
    is_plain_enter = (
        event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        and not (event.modifiers() & (
            Qt.KeyboardModifier.ShiftModifier |
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.AltModifier
        ))
    )

    cursor_before = self.textCursor()
    old_block = cursor_before.block()
    old_level = self.heading_level(old_block) if is_plain_enter else 0
    old_char_fmt = self.currentCharFormat() if is_plain_enter else None
    old_family = self.currentFont().family() if is_plain_enter else ""

    # 只有“光标在已折叠标题末尾按 Enter”才把折叠块当作一个整体跳过。
    at_heading_end = (
        is_plain_enter
        and old_level > 0
        and not cursor_before.hasSelection()
        and cursor_before.positionInBlock() == len(old_block.text())
    )

    if at_heading_end and self.is_heading_folded(old_block):
        _insert_after_collapsed_scope(self, old_block, old_family, old_char_fmt)
        event.accept()
        return

    _original_key_press(self, event)

    if not is_plain_enter or old_level <= 0:
        return

    # 普通展开标题后回车：新段落仍按正文格式处理。
    cursor = self.textCursor()
    _apply_body_format(self, cursor, old_family, old_char_fmt)
    self.apply_fold_visibility()


NoteEditor.keyPressEvent = _key_press_event
