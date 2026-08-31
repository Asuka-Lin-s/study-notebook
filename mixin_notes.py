# -*- coding: utf-8 -*-
import json
import time
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QInputDialog, QMenu
from config import NOTES_DIR, ASSETS_DIR, INDEX_FILE, SETTINGS_FILE, LEGACY_NOTE_FILE, clean_text_from_html
from widgets import NoteEditor

class NotesMixin:
    def load_index(self):
        if INDEX_FILE.exists():
            try:
                raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.notes_index = raw
            except Exception:
                self.notes_index = {}

    def save_index(self):
        try:
            INDEX_FILE.write_text(json.dumps(self.notes_index, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def migrate_legacy_note(self):
        if self.notes_index:
            return
        if LEGACY_NOTE_FILE.exists():
            try:
                html = LEGACY_NOTE_FILE.read_text(encoding="utf-8")
                if clean_text_from_html(html):
                    note_id = self.create_note_record("旧版便签")
                    self.note_path(note_id).write_text(html, encoding="utf-8")
                    self.notes_index[note_id]["preview"] = clean_text_from_html(html)[:180]
                    self.save_index()
            except Exception:
                pass

    def note_path(self, note_id):
        return NOTES_DIR / ("%s.html" % note_id)

    def create_note_record(self, title):
        note_id = uuid.uuid4().hex
        now = time.time()
        self.notes_index[note_id] = {"title": title, "created": now, "modified": now, "preview": ""}
        self.note_path(note_id).write_text("", encoding="utf-8")
        self.save_index()
        return note_id

    def create_new_note(self):
        n = 1
        existing = {v.get("title", "") for v in self.notes_index.values()}
        title = "新笔记"
        while title in existing:
            n += 1
            title = "新笔记 %d" % n
        note_id = self.create_note_record(title)
        self.refresh_note_list()
        self.open_note_exclusive(note_id)
        editor = self.open_editors.get(note_id)
        if editor:
            editor.setFocus()

    def rename_note(self, note_id):
        info = self.notes_index.get(note_id)
        if not info:
            return
        old = info.get("title", "未命名")
        new, ok = QInputDialog.getText(self, "重命名笔记", "笔记名称：", text=old)
        if not ok:
            return
        new = new.strip()
        if not new:
            return
        info["title"] = new
        info["modified"] = time.time()
        self.save_index()
        self.refresh_note_list()
        if note_id in self.open_editors:
            idx = self.tabs.indexOf(self.open_editors[note_id])
            if idx >= 0:
                self.tabs.setTabText(idx, new)

    def rename_selected_note(self):
        item = self.note_list.currentItem()
        if item:
            self.rename_note(item.data(Qt.ItemDataRole.UserRole))

    def delete_note(self, note_id):
        info = self.notes_index.get(note_id)
        if not info:
            return
        reply = QMessageBox.question(self, "删除笔记", "确定删除“%s”吗？\n\n该笔记和它保存的截图都会删除。" % info.get("title", "未命名"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        if note_id in self.open_editors:
            idx = self.tabs.indexOf(self.open_editors[note_id])
            if idx >= 0:
                self.close_tab(idx, save_first=False)
        try:
            self.note_path(note_id).unlink(missing_ok=True)
        except Exception:
            pass
        assets = ASSETS_DIR / note_id
        if assets.exists():
            import shutil
            try:
                shutil.rmtree(assets)
            except Exception:
                pass
        self.notes_index.pop(note_id, None)
        self.save_index()
        self.refresh_note_list()
        if not self.notes_index:
            self.create_new_note()

    def delete_selected_note(self):
        item = self.note_list.currentItem()
        if item:
            self.delete_note(item.data(Qt.ItemDataRole.UserRole))

    def show_note_context_menu(self, pos):
        item = self.note_list.itemAt(pos)
        if not item:
            return
        note_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        open_act = menu.addAction("打开")
        rename_act = menu.addAction("重命名")
        delete_act = menu.addAction("删除")
        chosen = menu.exec(self.note_list.mapToGlobal(pos))
        if chosen == open_act:
            self.open_note_exclusive(note_id)
        elif chosen == rename_act:
            self.rename_note(note_id)
        elif chosen == delete_act:
            self.delete_note(note_id)

    def refresh_note_list(self):
        keyword = self.search_box.text().strip().lower()
        self.note_list.clear()
        items = sorted(self.notes_index.items(), key=lambda kv: kv[1].get("modified", 0), reverse=True)
        for note_id, info in items:
            title = info.get("title", "未命名")
            preview = info.get("preview", "")
            haystack = (title + " " + preview).lower()
            if keyword and keyword not in haystack:
                try:
                    body = clean_text_from_html(self.note_path(note_id).read_text(encoding="utf-8"))
                    haystack = (haystack + " " + body.lower())
                    if keyword not in haystack:
                        continue
                except Exception:
                    continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, note_id)
            if preview:
                item.setToolTip(preview[:300])
            self.note_list.addItem(item)

    def open_initial_note(self):
        if not self.notes_index:
            self.create_new_note()
            return
        last_note = None
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                last_note = data.get("last_note")
        except Exception:
            pass
        if last_note not in self.notes_index:
            last_note = max(self.notes_index, key=lambda nid: self.notes_index[nid].get("modified", 0))
        self.open_note(last_note)

    def open_note_from_item(self, item):
        self.open_note_exclusive(item.data(Qt.ItemDataRole.UserRole))

    def open_note_exclusive(self, note_id):
        if note_id not in self.notes_index:
            return
        for i in range(self.tabs.count() - 1, -1, -1):
            widget = self.tabs.widget(i)
            if isinstance(widget, NoteEditor) and widget.note_id != note_id:
                self.close_tab(i, save_first=True)
        self.open_note(note_id)

    def open_note(self, note_id):
        if note_id not in self.notes_index:
            return
        if note_id in self.open_editors:
            idx = self.tabs.indexOf(self.open_editors[note_id])
            if idx >= 0:
                self.tabs.setCurrentIndex(idx)
            return
        editor = NoteEditor(note_id)
        try:
            path = self.note_path(note_id)
            if path.exists():
                html = path.read_text(encoding="utf-8")
                if html:
                    editor.setHtml(html)
        except Exception:
            pass
        editor.textChanged.connect(self.schedule_save)
        editor.image_inserted.connect(self.schedule_save)
        self.open_editors[note_id] = editor
        title = self.notes_index[note_id].get("title", "未命名")
        idx = self.tabs.addTab(editor, title)
        self.tabs.setCurrentIndex(idx)
        editor.setFocus()
        self.rebuild_search_matches()
        self.highlight_search_keyword()

    def close_tab(self, index, save_first=True):
        widget = self.tabs.widget(index)
        if not isinstance(widget, NoteEditor):
            self.tabs.removeTab(index)
            return
        note_id = widget.note_id
        if save_first:
            self.save_note(note_id)
        self.open_editors.pop(note_id, None)
        self.search_positions.pop(note_id, None)
        self.search_indices.pop(note_id, None)
        self.tabs.removeTab(index)
        widget.deleteLater()

    def sync_list_selection_to_tab(self, index):
        widget = self.tabs.widget(index)
        if not isinstance(widget, NoteEditor):
            return
        note_id = widget.note_id
        for i in range(self.note_list.count()):
            item = self.note_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == note_id:
                self.note_list.setCurrentItem(item)
                break

    def current_editor(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, NoteEditor) else None

    def current_note_id(self):
        e = self.current_editor()
        return e.note_id if e else None
