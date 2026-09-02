# -*- coding: utf-8 -*-
"""为学习笔记加入 HTML/TXT 导入，并把导入/导出收进标题栏“⋯”菜单。"""
import re
import shutil
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QKeySequence, QTextDocument
from PySide6.QtWidgets import QFileDialog, QMessageBox, QPushButton, QMenu

from main_window import MainWindow
from mixin_save import SaveCaptureMixin
from config import ASSETS_DIR


def _read_text_file(path):
    """优先 UTF-8，兼容常见中文文本编码。"""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _copy_local_html_images(self, html, source_file, note_id):
    """把 HTML 引用的本地图片复制到该笔记自己的 assets 目录。"""
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
        note_id = self.create_note_record(title, parent_id)

        if source.suffix.lower() in (".html", ".htm"):
            content = _read_text_file(source)
            content = _copy_local_html_images(self, content, source, note_id)
            self.note_path(note_id).write_text(content, encoding="utf-8")
        else:
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
        QMessageBox.information(
            self,
            "导入成功",
            "已导入为新笔记：\n%s" % title,
        )
    except Exception as exc:
        try:
            if "note_id" in locals():
                self.open_editors.pop(note_id, None)
                self.notes_index.pop(note_id, None)
                self.note_path(note_id).unlink(missing_ok=True)
                assets = ASSETS_DIR / note_id
                if assets.exists():
                    shutil.rmtree(assets, ignore_errors=True)
                self.save_index()
                self.refresh_note_list()
        except Exception:
            pass
        self.status.setText("导入失败")
        QMessageBox.warning(self, "导入失败", str(exc))


SaveCaptureMixin.import_note_file = _import_note_file


_original_init = MainWindow.__init__


def _init_with_file_menu(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)

    layout = self.titlebar.layout()

    # 移除原来常驻标题栏的“导出”按钮。
    export_btn = getattr(self.titlebar, "export_btn", None)
    if export_btn is not None:
        layout.removeWidget(export_btn)
        export_btn.hide()
        export_btn.deleteLater()
        self.titlebar.export_btn = None

    # 文件类低频操作统一放进“⋯”菜单，给标题和拖动区域腾空间。
    more_btn = QPushButton("⋯", self.titlebar)
    more_btn.setFixedWidth(36)
    more_btn.setToolTip("更多")

    menu = QMenu(more_btn)
    import_menu_action = menu.addAction("导入…")
    export_menu_action = menu.addAction("导出…")
    import_menu_action.triggered.connect(self.import_note_file)
    export_menu_action.triggered.connect(self.export_current_note)
    more_btn.setMenu(menu)

    # 放在置顶按钮之前。
    pin_btn = getattr(self.titlebar, "pin_btn", None)
    if pin_btn is not None:
        layout.insertWidget(max(0, layout.indexOf(pin_btn)), more_btn)
    else:
        layout.addWidget(more_btn)

    self.titlebar.more_btn = more_btn
    self.titlebar.more_menu = menu
    self.titlebar.import_menu_action = import_menu_action
    self.titlebar.export_menu_action = export_menu_action

    # 导入快捷键继续保留；导出 Ctrl+Shift+E 已由主窗口原有逻辑提供。
    import_action = QAction(self)
    import_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
    import_action.triggered.connect(self.import_note_file)
    self.addAction(import_action)
    self.import_note_action = import_action


MainWindow.__init__ = _init_with_file_menu
