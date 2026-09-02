# -*- coding: utf-8 -*-
"""按左侧目录的最高级分类合并导出，并写入可还原目录树的隐藏数据。"""
import re
import json
import html as html_lib
import base64
import mimetypes
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QFileDialog, QMessageBox

from mixin_save import SaveCaptureMixin


ENTRY_ID_ROLE = Qt.ItemDataRole.UserRole
EXPORT_FORMAT = "study-notebook-category"
EXPORT_VERSION = 1
EXPORT_DATA_ID = "study-notebook-category-data"


def _safe_filename(text):
    return re.sub(r'[\\/:*?"<>|]+', "_", text).strip() or "学习笔记"


def _top_level_entry(self, entry_id):
    if entry_id not in self.notes_index:
        return None
    current = entry_id
    seen = set()
    while current in self.notes_index and current not in seen:
        seen.add(current)
        parent = self.notes_index[current].get("parent")
        if not parent or parent not in self.notes_index:
            return current
        current = parent
    return entry_id


def _export_anchor_entry(self):
    try:
        item = self.note_list.currentItem()
        if item:
            entry_id = item.data(0, ENTRY_ID_ROLE)
            if entry_id in self.notes_index:
                return entry_id
    except Exception:
        pass
    return self.current_note_id()


def _children_for_export(self, parent_id):
    ids = [
        entry_id for entry_id, info in self.notes_index.items()
        if info.get("parent") == parent_id
    ]

    def key(entry_id):
        info = self.notes_index[entry_id]
        return (
            0 if info.get("type", "note") == "folder" else 1,
            int(info.get("order", 0)),
            info.get("title", "").lower(),
        )

    ids.sort(key=key)
    return ids


def _note_html(self, note_id):
    editor = self.open_editors.get(note_id)
    if editor is not None:
        return editor.toHtml()
    try:
        return self.note_path(note_id).read_text(encoding="utf-8")
    except Exception:
        return ""


def _body_fragment(raw_html):
    if not raw_html:
        return ""
    match = re.search(r"<body\b[^>]*>(.*?)</body>", raw_html, re.I | re.S)
    return match.group(1) if match else raw_html


def _embed_images(raw_html):
    pattern = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)

    def repl(match):
        src = match.group(1)
        if src.startswith("data:"):
            return match.group(0)

        local_path = None
        if src.startswith("file:"):
            local_path = QUrl(src).toLocalFile()
        else:
            candidate = Path(src)
            if candidate.exists():
                local_path = str(candidate)

        if not local_path:
            return match.group(0)

        path = Path(local_path)
        if not path.exists() or not path.is_file():
            return match.group(0)

        try:
            mime, _ = mimetypes.guess_type(str(path))
            mime = mime or "image/png"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return 'src="data:%s;base64,%s"' % (mime, encoded)
        except Exception:
            return match.group(0)

    return pattern.sub(repl, raw_html)


def _plain_text_from_html(raw_html):
    doc = QTextDocument()
    doc.setHtml(raw_html or "")
    return doc.toPlainText().strip()


def _export_tree_node(self, entry_id):
    info = self.notes_index[entry_id]
    kind = info.get("type", "note")
    node = {
        "type": kind,
        "title": info.get("title", "未命名"),
    }

    if kind == "folder":
        node["children"] = [
            _export_tree_node(self, child_id)
            for child_id in _children_for_export(self, entry_id)
        ]
        return node

    # 元数据中的每篇笔记保留完整 HTML，并把本地图片内嵌，保证单文件可迁移。
    node["html"] = _embed_images(_note_html(self, entry_id))
    folded = info.get("folded_headings", [])
    if isinstance(folded, list):
        node["folded_headings"] = folded
    return node


def _encoded_export_payload(self, root_id):
    payload = {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "root": _export_tree_node(self, root_id),
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _build_category_html(self, root_id):
    root = self.notes_index[root_id]
    root_title = root.get("title", "未命名")
    parts = []
    note_count = 0

    parts.append("<!DOCTYPE html>")
    parts.append("<html><head><meta charset='utf-8'>")
    parts.append("<title>%s</title>" % html_lib.escape(root_title))
    parts.append("""
<style>
body { font-family: sans-serif; max-width: 1000px; margin: 32px auto; padding: 0 28px; line-height: 1.65; color: #222; }
h1 { border-bottom: 2px solid #ddd; padding-bottom: 10px; }
h2, h3, h4, h5, h6 { margin-top: 1.4em; }
.folder-heading { color: #333; }
.note-section { margin: 18px 0 34px 0; }
.note-title { border-bottom: 1px solid #e6e6e6; padding-bottom: 5px; }
p, li { white-space: pre-wrap; }
img { max-width: 100%; height: auto; }
</style></head><body>
""")
    parts.append("<h1>%s</h1>" % html_lib.escape(root_title))

    def walk(parent_id, depth):
        nonlocal note_count
        for entry_id in _children_for_export(self, parent_id):
            info = self.notes_index[entry_id]
            title = info.get("title", "未命名")
            kind = info.get("type", "note")
            heading_level = min(6, max(2, depth + 1))

            if kind == "folder":
                parts.append(
                    "<h%d class='folder-heading'>%s</h%d>" % (
                        heading_level, html_lib.escape(title), heading_level
                    )
                )
                walk(entry_id, depth + 1)
            else:
                note_count += 1
                raw = _note_html(self, entry_id)
                fragment = _embed_images(_body_fragment(raw))
                parts.append("<section class='note-section'>")
                parts.append(
                    "<h%d class='note-title'>%s</h%d>" % (
                        heading_level, html_lib.escape(title), heading_level
                    )
                )
                parts.append(fragment)
                parts.append("</section>")

    walk(root_id, 1)

    # 浏览器不会显示这一段；本软件导入时用它完整重建目录和每篇笔记。
    parts.append(
        "<script id='%s' type='application/x-study-notebook'>%s</script>" % (
            EXPORT_DATA_ID, _encoded_export_payload(self, root_id)
        )
    )
    parts.append("</body></html>")
    return "\n".join(parts), note_count


def _build_category_text(self, root_id):
    root = self.notes_index[root_id]
    lines = [root.get("title", "未命名"), "=" * 40, ""]
    note_count = 0

    def walk(parent_id, depth):
        nonlocal note_count
        for entry_id in _children_for_export(self, parent_id):
            info = self.notes_index[entry_id]
            title = info.get("title", "未命名")
            kind = info.get("type", "note")
            indent = "  " * max(0, depth - 1)

            if kind == "folder":
                lines.append("%s[%s]" % (indent, title))
                lines.append("")
                walk(entry_id, depth + 1)
            else:
                note_count += 1
                lines.append("%s%s" % (indent, title))
                lines.append("%s%s" % (indent, "-" * max(8, len(title))))
                text = _plain_text_from_html(_note_html(self, entry_id))
                if text:
                    lines.append(text)
                lines.append("")

    walk(root_id, 1)
    return "\n".join(lines).rstrip() + "\n", note_count


def _export_current_note_by_category(self):
    anchor_id = _export_anchor_entry(self)
    if not anchor_id or anchor_id not in self.notes_index:
        return

    self.save_all_open_notes()

    root_id = _top_level_entry(self, anchor_id)
    root_info = self.notes_index.get(root_id, {})

    if root_info.get("type", "note") != "folder":
        editor = self.open_editors.get(root_id)
        if editor is None:
            self.open_note_exclusive(root_id)
            editor = self.open_editors.get(root_id)
        if editor is None:
            return _original_export_current_note(self)
        return _original_export_current_note(self)

    root_title = root_info.get("title", "学习笔记")
    safe_title = _safe_filename(root_title)
    documents = Path.home() / "Documents"
    if not documents.exists():
        documents = Path.home()

    default_name = documents / ("%s.html" % safe_title)
    filename, selected_filter = QFileDialog.getSaveFileName(
        self,
        "导出最高级分类：%s" % root_title,
        str(default_name),
        "HTML 合并笔记 (*.html);;纯文本合并笔记 (*.txt)",
    )
    if not filename:
        self.status.setText("已取消导出")
        return

    path = Path(filename)
    try:
        if path.suffix.lower() == ".txt" or "纯文本" in selected_filter:
            if path.suffix.lower() != ".txt":
                path = path.with_suffix(".txt")
            content, count = _build_category_text(self, root_id)
            path.write_text(content, encoding="utf-8")
        else:
            if path.suffix.lower() not in (".html", ".htm"):
                path = path.with_suffix(".html")
            content, count = _build_category_html(self, root_id)
            path.write_text(content, encoding="utf-8")

        self.status.setText("已导出分类：%s" % root_title)
        QMessageBox.information(
            self,
            "导出成功",
            "已按最高级目录“%s”合并导出 %d 篇笔记：\n%s\n\nHTML 再导入时可恢复完整目录层级。" % (
                root_title, count, str(path)
            ),
        )
    except Exception as exc:
        self.status.setText("导出失败")
        QMessageBox.warning(self, "导出失败", str(exc))


_original_export_current_note = SaveCaptureMixin.export_current_note
SaveCaptureMixin.export_current_note = _export_current_note_by_category
