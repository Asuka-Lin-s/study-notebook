# -*- coding: utf-8 -*-
"""标题回车后的正文样式与折叠行为修复。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QFont
from widgets import NoteEditor


_original_key_press = NoteEditor.keyPressEvent


def _key_press_event(self, event):
    is_plain_enter = (
        event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        and not (event.modifiers() & (
            Qt.KeyboardModifier.ShiftModifier |
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.AltModifier
        ))
    )

    old_block = self.textCursor().block()
    old_level = self.heading_level(old_block) if is_plain_enter else 0

    # 记录标题处当前的字符外观。使用 QFont 高层接口读取字体家族，
    # 避免直接调用 QTextCharFormat.fontFamily()/fontFamilies() 的兼容问题。
    old_char_fmt = self.currentCharFormat() if is_plain_enter else None
    old_family = self.currentFont().family() if is_plain_enter else ""

    # 如果当前标题已经折叠，直接在它后面回车会创建一个“属于该标题”的正文段，
    # 随后又会被折叠逻辑隐藏。先展开当前标题，让新增正文立即可见。
    if is_plain_enter and old_level > 0 and self.is_heading_folded(old_block):
        self.toggle_heading_fold(old_block)

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
    if old_family:
        fmt.setFontFamilies([old_family])
    if old_char_fmt is not None:
        color = old_char_fmt.foreground().color()
        if color.isValid():
            fmt.setForeground(color)

    fmt.setFontPointSize(11.0)
    fmt.setFontWeight(int(QFont.Weight.Normal))
    cursor.mergeCharFormat(fmt)
    self.setCurrentCharFormat(fmt)
    self.setTextCursor(cursor)

    # 文档结构刚发生变化，重新应用一次折叠可见性。
    self.apply_fold_visibility()


NoteEditor.keyPressEvent = _key_press_event
