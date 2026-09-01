# -*- coding: utf-8 -*-
"""折叠状态使用结构位置标识，不再依赖标题文字。

旧版 key:  1|GPIO基础|1
新版 key:  path|2|1.2   （第1个 H1 下的第2个 H2）

这样修改标题文字不会导致 key 改变，也就不会把折叠区域自动展开。
"""
from widgets import NoteEditor
from mixin_format import FormatMixin


def _structural_heading_key(self, target_block):
    if not target_block or not target_block.isValid():
        return None

    target_level = self.heading_level(target_block)
    if target_level <= 0:
        return None

    # 记录 H1/H2/H3 在各自父层级中的序号。
    counters = [0, 0, 0, 0]
    block = self.document().begin()

    while block.isValid():
        level = self.heading_level(block)
        if 1 <= level <= 3:
            counters[level] += 1
            for deeper in range(level + 1, 4):
                counters[deeper] = 0

            if block == target_block:
                path = ".".join(str(counters[i]) for i in range(1, level + 1))
                return "path|%d|%s" % (level, path)

        if block == target_block:
            break
        block = block.next()

    return None


def _legacy_heading_key(self, target_block):
    """复现旧版标题文字 key，仅用于第一次自动迁移。"""
    if not target_block or not target_block.isValid():
        return None
    level = self.heading_level(target_block)
    if level <= 0:
        return None

    text = target_block.text().strip()
    occurrence = 0
    block = self.document().begin()
    while block.isValid():
        if self.heading_level(block) == level and block.text().strip() == text:
            occurrence += 1
        if block == target_block:
            break
        block = block.next()
    return "%d|%s|%d" % (level, text, occurrence)


def _set_folded_heading_keys(self, keys):
    incoming = set(str(k) for k in (keys or []))
    converted = {k for k in incoming if k.startswith("path|")}

    # 将已有的“层级|标题文字|序号”状态匹配到当前标题，再换成结构 key。
    if any(not k.startswith("path|") for k in incoming):
        block = self.document().begin()
        while block.isValid():
            if self.heading_level(block) > 0:
                old_key = _legacy_heading_key(self, block)
                if old_key in incoming:
                    new_key = _structural_heading_key(self, block)
                    if new_key:
                        converted.add(new_key)
            block = block.next()

    self.folded_heading_keys = converted
    self._fold_keys_migrated = converted != incoming
    self.apply_fold_visibility()


def _attach_format_tracking(self, editor):
    editor.cursorPositionChanged.connect(self.sync_heading_combo)
    editor.cursorPositionChanged.connect(self.sync_text_format_controls)

    # 先连接折叠状态保存，再做旧 key 迁移，这样迁移结果可以立即写回索引。
    editor.fold_state_changed.connect(
        lambda note_id=editor.note_id, e=editor: self.save_heading_fold_state(note_id, e)
    )

    info = self.notes_index.get(editor.note_id, {})
    editor.set_folded_heading_keys(info.get("folded_headings", []))

    if getattr(editor, "_fold_keys_migrated", False):
        self.save_heading_fold_state(editor.note_id, editor)
        editor._fold_keys_migrated = False


NoteEditor.heading_key = _structural_heading_key
NoteEditor.set_folded_heading_keys = _set_folded_heading_keys
FormatMixin.attach_format_tracking = _attach_format_tracking
