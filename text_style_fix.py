# -*- coding: utf-8 -*-
"""标题回车后的正文样式修复。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextCharFormat, QFont
from widgets import NoteEditor


_original_key_press = NoteEditor.keyPressEvent


def _key_press_event(self, event):
    is_plain_enter = (
        event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        and not (event.modifiers() & (Qt.KeyboardModifier.ShiftModifier |
                                     Qt.KeyboardModifier.ControlModifier |
                                     Qt.KeyboardModifier.AltModifier))
    )

    old_block = self.textCursor().block()
    old_level = self.heading_level(old_block) if is_plain_enter else 0
    old_char_fmt = self.currentCharFormat() if is_plain_enter else None

    _original_key_press(self, event)

    if not is_plain_enter or old_level <= 0:
        return

    # 标题后新起一段时，自动回到正文层级。
    cursor = self.textCursor()
    block_fmt = cursor.blockFormat()
    block_fmt.setHeadingLevel(0)
    block_fmt.setTopMargin(0)
    block_fmt.setBottomMargin(0)
    cursor.setBlockFormat(block_fmt)

    # 保留用户选择的字体家族和颜色，但恢复正文常规字号与字重。
    fmt = QTextCharFormat()
    if old_char_fmt is not None:
        try:
            families = old_char_fmt.fontFamilies()
            if families:
                fmt.setFontFamilies(families)
        except Exception:
            family = old_char_fmt.fontFamily()
            if family:
                fmt.setFontFamily(family)
        color = old_char_fmt.foreground().color()
        if color.isValid():
            fmt.setForeground(color)

    fmt.setFontPointSize(11.0)
    fmt.setFontWeight(int(QFont.Weight.Normal))
    cursor.mergeCharFormat(fmt)
    self.setCurrentCharFormat(fmt)
    self.setTextCursor(cursor)


NoteEditor.keyPressEvent = _key_press_event
