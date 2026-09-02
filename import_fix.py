# -*- coding: utf-8 -*-
"""HTML/TXT 导入；支持恢复本软件分类导出的目录层级。"""
import re
import json
import html as html_lib
import base64
import shutil
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QKeySequence, QTextDocument
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QMenu

from main_window import MainWindow
from mixin_save import SaveCaptureMixin
from config import ASSETS_DIR


EXPORT_FORMAT = "study-notebook-category"
EXPORT_DATA_ID = "study-notebook-category-data"


def _read_text_file(path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _copy_local_html_images(self, html, source_file, note_id):
    asset_dir = ASSETS_DIR / note_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_dir = source_file.parent
    pattern = re.compile(r'src=["\']([^"\']+)["\']', re.IGNORECASE)
    used_names = set()

    def repl(match):
        src = match.group(1).strip()
        lower = src.lower()
        if lower.startswith(("data:", "http://", "https://")):
            return match.group(0)

        try:
            if lower.startswith("file:"):
                local = Path(QUrl(src).toLocalFile())
            else:
                local = Path(src)
                if not local.is_absolute():
                    local = source_dir / local
                local = local.resolve()
        except Exception:
            return match.group(0)

        if not local.exists() or not local.is_file():
            return match.group(0)

        stem = local.stem or "image"
        suffix = local.suffix or ".png"
        name = stem + suffix
        index = 2
        while name.lower() in used_names or (asset_dir / name).exists():
            name = "%s_%d%s" % (stem, index, suffix)
            index += 1
        used_names.add(name.lower())

        dest = asset_dir / name
        try:
            shutil.copy2(local, dest)
            return 'src="%s"' % QUrl.fromLocalFile(str(dest)).toString()
        except Exception:
            return match.group(0)

    return pattern.sub(repl, html)


def _extract_structured_payload(content):
    pattern = re.compile(
        r"<script\b[^>]*\bid=[\"']%s[\"'][^>]*>(.*?)</script>" % re.escape(EXPORT_DATA_ID),
        re.I | re.S,
    )
    match = pattern.search(content or "")
    if not match:
        return None

    try:
        raw = base64.b64decode(match.group(1).strip())
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict) or payload.get("format") != EXPORT_FORMAT:
        return None
    root = payload.get("root")
    if not isinstance(root, dict):
        return None
    return payload


def _restore_tree_node(self, node, parent_id=None):
    kind = node.get("type", "note")
    title = str(node.get("title", "未命名")).strip() or "未命名"

    if kind == "folder":
        folder_id = self.create_folder_record(title, parent_id)
        children = node.get("children", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    _restore_tree_node(self, child, folder_id)
        return folder_id, None

    note_id = self.create_note_record(title, parent_id)
    note_html = node.get("html", "")
    if not isinstance(note_html, str):
        note_html = ""
    self.note_path(note_id).write_text(note_html, encoding="utf-8")

    folded = node.get("folded_headings", [])
    if isinstance(folded, list):
        self.notes_index[note_id]["folded_headings"] = folded
    return note_id, note_id


def _import_structured_category(self, payload):
    root = payload.get("root", {})
    title = str(root.get("title", "导入分类")).strip() or "导入分类"

    # 如果当前选中的是文件夹，就把导入的最高级分类放在它下面；否则放根目录。
    destination_parent = self.selected_parent_folder()
    created_root, last_note = _restore_tree_node(self, root, destination_parent)
    self.save_index()
    self.refresh_note_list()

    root_item = self.tree_items.get(created_root)
    if root_item:
        self.note_list.setCurrentItem(root_item)
        root_item.setExpanded(True)

    # 有笔记时打开第一篇可用笔记，方便用户立刻确认内容。
    if last_note:
        self.open_note_exclusive(last_note)

    self.status.setText("已恢复目录：" + title)
    QMessageBox.information(
        self,
        "导入成功",
        "已恢复“%s”的目录层级和笔记内容。" % title,
    )


def _legacy_category_structure(content, source_stem):
    """尽量识别旧版分类导出 HTML。

    旧版没有隐藏元数据，只能依据 folder-heading 和 note-section 重建。
    能恢复大部分目录层级，但正文中复杂嵌套 HTML 不保证完全无损。
    """
    if "class='note-section'" not in content and 'class="note-section"' not in content:
        return None

    title_match = re.search(r"<h1\b[^>]*>(.*?)</h1>", content, re.I | re.S)
    root_title = re.sub(r"<[^>]+>", "", title_match.group(1) if title_match else source_stem)
    root_title = html_lib.unescape(root_title).strip() or source_stem or "导入分类"
    root = {"type": "folder", "title": root_title, "children": []}

    token_pattern = re.compile(
        r"(<h([2-6])\b[^>]*class=[\"']folder-heading[\"'][^>]*>.*?</h\2>|"
        r"<section\b[^>]*class=[\"']note-section[\"'][^>]*>.*?</section>)",
        re.I | re.S,
    )

    stack = [(1, root)]
    for match in token_pattern.finditer(content):
        token = match.group(1)
        folder_match = re.match(
            r"<h([2-6])\b[^>]*class=[\"']folder-heading[\"'][^>]*>(.*?)</h\1>",
            token, re.I | re.S,
        )
        if folder_match:
            level = int(folder_match.group(1))
            name = re.sub(r"<[^>]+>", "", folder_match.group(2))
            name = html_lib.unescape(name).strip() or "未命名文件夹"
            node = {"type": "folder", "title": name, "children": []}
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            parent.setdefault("children", []).append(node)
            stack.append((level, node))
            continue

        note_title_match = re.search(
            r"<h[2-6]\b[^>]*class=[\"']note-title[\"'][^>]*>(.*?)</h[2-6]>",
            token, re.I | re.S,
        )
        title = re.sub(r"<[^>]+>", "", note_title_match.group(1) if note_title_match else "导入笔记")
        title = html_lib.unescape(title).strip() or "导入笔记"
        body = token
        if note_title_match:
            body = token[:note_title_match.start()] + token[note_title_match.end():]
        body = re.sub(r"^<section\b[^>]*>|</section>$", "", body, flags=re.I | re.S).strip()
        parent = stack[-1][1] if stack else root
        parent.setdefault("children", []).append({"type": "note", "title": title, "html": body})

    return {"format": EXPORT_FORMAT, "version": 0, "root": root}


def _import_note_file(self):
    filename, selected_filter = QFileDialog.getOpenFileName(
        self,
        "导入学习笔记",
        str(Path.home()),
        "支持的笔记 (*.html *.htm *.txt);;HTML 笔记 (*.html *.htm);;纯文本 (*.txt)",
    )
    if not filename:
        self.status.setText("已取消导入")
        return

    source = Path(filename)
    parent_id = self.selected_parent_folder()
    title = source.stem.strip() or "导入笔记"

    try:
        if source.suffix.lower() in (".html", ".htm"):
            content = _read_text_file(source)

            payload = _extract_structured_payload(content)
            if payload is not None:
                return _import_structured_category(self, payload)

            legacy_payload = _legacy_category_structure(content, source.stem)
            if legacy_payload is not None:
                return _import_structured_category(self, legacy_payload)

            note_id = self.create_note_record(title, parent_id)
            content = _copy_local_html_images(self, content, source, note_id)
            self.note_path(note_id).write_text(content, encoding="utf-8")
        else:
            note_id = self.create_note_record(title, parent_id)
            text = _read_text_file(source)
            document = QTextDocument()
            document.setPlainText(text)
            self.note_path(note_id).write_text(document.toHtml(), encoding="utf-8")

        self.notes_index[note_id]["preview"] = ""
        self.save_index()
        self.refresh_note_list()
        self.open_note_exclusive(note_id)

        item = self.tree_items.get(note_id)
        if item:
            self.note_list.setCurrentItem(item)

        editor = self.open_editors.get(note_id)
        if editor:
            self.save_note(note_id)
            editor.setFocus()

        self.status.setText("已导入：" + title)
        QMessageBox.information(self, "导入成功", "已导入为新笔记：\n%s" % title)
    except Exception as exc:
        self.status.setText("导入失败")
        QMessageBox.warning(self, "导入失败", str(exc))


SaveCaptureMixin.import_note_file = _import_note_file


_original_init = MainWindow.__init__


def _init_with_file_menu(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)

    layout = self.titlebar.layout()

    export_btn = getattr(self.titlebar, "export_btn", None)
    if export_btn is not None:
        layout.removeWidget(export_btn)
        export_btn.hide()
        export_btn.deleteLater()
        self.titlebar.export_btn = None

    more_btn = QPushButton("⋯", self.titlebar)
    more_btn.setFixedWidth(36)
    more_btn.setToolTip("更多")

    menu = QMenu(more_btn)
    import_menu_action = menu.addAction("导入…")
    export_menu_action = menu.addAction("导出…")
    import_menu_action.triggered.connect(self.import_note_file)
    export_menu_action.triggered.connect(self.export_current_note)
    more_btn.setMenu(menu)

    pin_btn = getattr(self.titlebar, "pin_btn", None)
    if pin_btn is not None:
        layout.insertWidget(max(0, layout.indexOf(pin_btn)), more_btn)
    else:
        layout.addWidget(more_btn)

    self.titlebar.more_btn = more_btn
    self.titlebar.more_menu = menu
    self.titlebar.import_menu_action = import_menu_action
    self.titlebar.export_menu_action = export_menu_action

    import_action = QAction(self)
    import_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
    import_action.triggered.connect(self.import_note_file)
    self.addAction(import_action)
    self.import_note_action = import_action


MainWindow.__init__ = _init_with_file_menu
