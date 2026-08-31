# -*- coding: utf-8 -*-
import time
import re
import base64
import mimetypes
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox
from widgets import SnipOverlay

class SaveCaptureMixin:
    def schedule_save(self):
        self.status.setText("正在记录修改…")
        self.autosave_timer.start()

    def save_note(self, note_id):
        editor = self.open_editors.get(note_id)
        if not editor or note_id not in self.notes_index:
            return
        try:
            html = editor.toHtml()
            self.note_path(note_id).write_text(html, encoding="utf-8")
            preview = editor.toPlainText().strip().replace("\n", " ")
            self.notes_index[note_id]["preview"] = preview[:600]
            self.notes_index[note_id]["modified"] = time.time()
            self.save_index()
            self.status.setText("已自动保存  " + time.strftime("%H:%M:%S"))
        except Exception as e:
            self.status.setText("保存失败")
            QMessageBox.warning(self, "保存失败", str(e))

    def save_current_note(self):
        note_id = self.current_note_id()
        if note_id:
            self.save_note(note_id)
            self.refresh_note_list()

    def save_all_open_notes(self):
        for note_id in list(self.open_editors.keys()):
            self.save_note(note_id)
        self.refresh_note_list()

    def standalone_html(self, editor):
        html = editor.toHtml()
        pattern = re.compile(r'src=["\\\']([^"\\\']+)["\\\']', re.IGNORECASE)
        def repl(match):
            src = match.group(1)
            if src.startswith("data:"):
                return match.group(0)
            local_path = None
            if src.startswith("file:"):
                local_path = QUrl(src).toLocalFile()
            else:
                p = Path(src)
                if p.exists():
                    local_path = str(p)
            if not local_path:
                return match.group(0)
            p = Path(local_path)
            if not p.exists() or not p.is_file():
                return match.group(0)
            try:
                mime, _ = mimetypes.guess_type(str(p))
                if not mime:
                    mime = "image/png"
                b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                return 'src="data:%s;base64,%s"' % (mime, b64)
            except Exception:
                return match.group(0)
        return pattern.sub(repl, html)

    def export_current_note(self):
        editor = self.current_editor()
        if not editor:
            return
        note_id = editor.note_id
        self.save_note(note_id)
        title = self.notes_index.get(note_id, {}).get("title", "学习笔记")
        safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip() or "学习笔记"
        documents = Path.home() / "Documents"
        if not documents.exists():
            documents = Path.home()
        default_name = documents / ("%s.html" % safe_title)
        filename, selected_filter = QFileDialog.getSaveFileName(self, "导出学习笔记", str(default_name), "HTML 笔记 (*.html);;纯文本 (*.txt)")
        if not filename:
            self.status.setText("已取消导出")
            return
        path = Path(filename)
        try:
            if path.suffix.lower() == ".txt" or "纯文本" in selected_filter:
                if path.suffix.lower() != ".txt":
                    path = path.with_suffix(".txt")
                path.write_text(editor.toPlainText(), encoding="utf-8")
            else:
                if path.suffix.lower() not in (".html", ".htm"):
                    path = path.with_suffix(".html")
                path.write_text(self.standalone_html(editor), encoding="utf-8")
            self.status.setText("已导出：" + path.name)
            QMessageBox.information(self, "导出成功", "笔记已导出到：\n%s" % str(path))
        except Exception as e:
            self.status.setText("导出失败")
            QMessageBox.warning(self, "导出失败", str(e))

    def start_capture(self):
        editor = self.current_editor()
        if not editor:
            self.create_new_note()
            editor = self.current_editor()
        if not editor:
            return
        self.save_current_note()
        screen = self.screen() or QGuiApplication.primaryScreen()
        self.hide()
        def begin():
            self.snip = SnipOverlay(screen)
            self.snip.captured.connect(self.finish_capture)
            self.snip.cancelled.connect(self.cancel_capture)
        QTimer.singleShot(180, begin)

    def finish_capture(self, pix):
        editor = self.current_editor()
        if editor is None:
            self.show()
            return
        stamp = time.strftime("%Y%m%d_%H%M%S")
        assets_dir = editor.note_assets_dir()
        path = assets_dir / ("snip_%s.png" % stamp)
        idx = 1
        while path.exists():
            path = assets_dir / ("snip_%s_%d.png" % (stamp, idx))
            idx += 1
        pix.save(str(path), "PNG")
        self.show()
        self.raise_()
        self.activateWindow()
        editor.setFocus()
        editor.insert_image_file(path)
        self.save_current_note()
        self.snip = None

    def cancel_capture(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.snip = None
