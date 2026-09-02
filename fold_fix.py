# -*- coding: utf-8 -*-
"""正文标题嵌套折叠与“折叠块后继续写”支持。

折叠标题后按 Enter 时，会在折叠内容末尾插入一个不可见边界。
边界本身保存在富文本里，因此重新打开笔记后仍能知道：
后面的正文已经不属于前面那个折叠块。
"""
from widgets import NoteEditor


# 全部由零宽/不可见 Unicode 字符组成，不会显示在正文中。
# 末尾 U+200C 的数量表示要结束的标题层级：1 / 2 / 3。
_FOLD_BREAK_PREFIX = "\u2063\u200b\u2063"
_FOLD_BREAK_UNIT = "\u200c"


def make_fold_break_text(level):
    level = max(1, min(3, int(level)))
    return _FOLD_BREAK_PREFIX + (_FOLD_BREAK_UNIT * level)


def fold_break_level(block):
    if not block or not block.isValid():
        return 0
    text = block.text()
    if not text.startswith(_FOLD_BREAK_PREFIX):
        return 0
    suffix = text[len(_FOLD_BREAK_PREFIX):]
    if len(suffix) not in (1, 2, 3):
        return 0
    if suffix != (_FOLD_BREAK_UNIT * len(suffix)):
        return 0
    return len(suffix)


def _set_block_visible(block, visible):
    block.setVisible(bool(visible))
    block.setLineCount(1 if visible else 0)


def _apply_fold_visibility(self):
    if getattr(self, "_applying_fold_visibility", False):
        return

    self._applying_fold_visibility = True
    try:
        active_levels = []
        block = self.document().begin()

        while block.isValid():
            break_level = fold_break_level(block)
            if break_level:
                # 结束指定层级及其更深层级的折叠，但不影响更高一级的父标题。
                # 例如 H2 后的边界会结束 H2/H3，却仍允许外层折叠 H1 生效。
                while active_levels and active_levels[-1] >= break_level:
                    active_levels.pop()
                # 边界只用于结构判断，本身完全不占一行。
                _set_block_visible(block, False)
                block = block.next()
                continue

            level = self.heading_level(block)

            if level > 0:
                while active_levels and level <= active_levels[-1]:
                    active_levels.pop()

                hidden_by_parent = bool(active_levels)
                _set_block_visible(block, not hidden_by_parent)

                key = self.heading_key(block)
                if key in self.folded_heading_keys:
                    active_levels.append(level)
            else:
                _set_block_visible(block, not bool(active_levels))

            block = block.next()

        doc = self.document()
        doc.markContentsDirty(0, doc.characterCount())
        self.viewport().update()
        if hasattr(self, "fold_gutter"):
            self.fold_gutter.update()
    finally:
        self._applying_fold_visibility = False


def _current_heading_block(self):
    block = self.textCursor().block()
    if self.heading_level(block) > 0:
        return block

    level_stack = []
    b = self.document().begin()
    while b.isValid() and b.position() <= block.position():
        break_level = fold_break_level(b)
        if break_level:
            while level_stack and level_stack[-1][0] >= break_level:
                level_stack.pop()
            b = b.next()
            continue

        level = self.heading_level(b)
        if level > 0:
            while level_stack and level_stack[-1][0] >= level:
                level_stack.pop()
            level_stack.append((level, b))
        b = b.next()

    return level_stack[-1][1] if level_stack else None


def _expand_for_position(self, position):
    """搜索跳转时只展开真正遮住目标位置的上级折叠标题。"""
    changed = False
    stack = []
    block = self.document().begin()

    while block.isValid() and block.position() <= position:
        break_level = fold_break_level(block)
        if break_level:
            while stack and stack[-1][0] >= break_level:
                stack.pop()
            block = block.next()
            continue

        level = self.heading_level(block)
        if level > 0:
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, block))
        block = block.next()

    for _, heading_block in stack:
        key = self.heading_key(heading_block)
        if key in self.folded_heading_keys:
            self.folded_heading_keys.remove(key)
            changed = True

    if changed:
        self.apply_fold_visibility()
        self.fold_state_changed.emit()
    return changed


NoteEditor.apply_fold_visibility = _apply_fold_visibility
NoteEditor.current_heading_block = _current_heading_block
NoteEditor.expand_for_position = _expand_for_position
