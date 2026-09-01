# -*- coding: utf-8 -*-
"""V8.1: 修复正文标题嵌套折叠。

QTextBlock 仅 setVisible(False) 在 QTextEdit 中并不足以可靠压缩版面。
隐藏时同时把 lineCount 设为 0；恢复时设回 1，并让文档重新布局。
"""
from widgets import NoteEditor


def _set_block_visible(block, visible):
    block.setVisible(bool(visible))
    # Qt 官方代码折叠范式：隐藏块 lineCount=0，展开恢复为 1。
    block.setLineCount(1 if visible else 0)


def _apply_fold_visibility(self):
    if getattr(self, "_applying_fold_visibility", False):
        return

    self._applying_fold_visibility = True
    try:
        # 保存当前所有正在生效的折叠标题层级。
        # 例如 H1 折叠后 active_levels=[1]，其后的 H2/H3/正文全部隐藏，
        # 直到遇到下一个 H1（level <= 1）才退出这个折叠范围。
        active_levels = []
        block = self.document().begin()

        while block.isValid():
            level = self.heading_level(block)

            if level > 0:
                # 当前标题若与某个已折叠标题同级或更高，说明已走出其范围。
                while active_levels and level <= active_levels[-1]:
                    active_levels.pop()

                hidden_by_parent = bool(active_levels)
                _set_block_visible(block, not hidden_by_parent)

                key = self.heading_key(block)
                if key in self.folded_heading_keys:
                    # 即便这个子标题本身已被父标题隐藏，也保留它自己的折叠状态；
                    # 父标题展开后，子标题仍会维持原来的折叠状态。
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


# NoteEditor 的其它折叠入口都会动态调用 self.apply_fold_visibility，
# 因此只替换这一处即可覆盖点击三角、恢复状态、全部展开、搜索展开等路径。
NoteEditor.apply_fold_visibility = _apply_fold_visibility
