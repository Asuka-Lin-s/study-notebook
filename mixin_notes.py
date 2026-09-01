# -*- coding: utf-8 -*-
import json
import time
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem, QMessageBox, QInputDialog, QMenu
from config import NOTES_DIR, ASSETS_DIR, INDEX_FILE, SETTINGS_FILE, LEGACY_NOTE_FILE, clean_text_from_html
from widgets import NoteEditor

ENTRY_ID_ROLE = Qt.ItemDataRole.UserRole
ENTRY_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1


class NotesMixin:
    def load_index(self):
        self.notes_index = {}
        if INDEX_FILE.exists():
            try:
                raw = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.notes_index = raw
            except Exception:
                self.notes_index = {}

        normalized = {}
        for order, (entry_id, info) in enumerate(self.notes_index.items()):
            if not isinstance(info, dict):
                continue
            kind = info.get("type", "note")
            if kind not in ("note", "folder"):
                kind = "note"
            info["type"] = kind
            info.setdefault("parent", None)
            info.setdefault("order", order)
            info.setdefault("created", time.time())
            info.setdefault("modified", info.get("created", time.time()))
            if kind == "note":
                info.setdefault("preview", "")
            else:
                info.setdefault("expanded", True)
            normalized[entry_id] = info
        self.notes_index = normalized

        for entry_id, info in self.notes_index.items():
            parent_id = info.get("parent")
            if parent_id not in self.notes_index:
                info["parent"] = None
            elif self.notes_index[parent_id].get("type") != "folder":
                info["parent"] = None

        for entry_id, info in self.notes_index.items():
            seen = {entry_id}
            parent_id = info.get("parent")
            while parent_id:
                if parent_id in seen:
                    info["parent"] = None
                    break
                seen.add(parent_id)
                parent_id = self.notes_index.get(parent_id, {}).get("parent")

        self.save_index()

    def save_index(self):
        try:
            INDEX_FILE.write_text(json.dumps(self.notes_index, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def migrate_legacy_note(self):
        if any(v.get("type", "note") == "note" for v in self.notes_index.values()):
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

    def _valid_folder(self, folder_id):
        return folder_id in self.notes_index and self.notes_index[folder_id].get("type") == "folder"

    def _next_order(self, parent_id):
        siblings = [int(info.get("order", 0)) for info in self.notes_index.values() if info.get("parent") == parent_id]
        return (max(siblings) + 1) if siblings else 0

    def selected_parent_folder(self):
        item = self.note_list.currentItem()
        if not item:
            return None
        entry_id = item.data(0, ENTRY_ID_ROLE)
        kind = item.data(0, ENTRY_TYPE_ROLE)
        if kind == "folder":
            return entry_id
        return self.notes_index.get(entry_id, {}).get("parent")

    def create_note_record(self, title, parent_id=None):
        if not self._valid_folder(parent_id):
            parent_id = None
        note_id = uuid.uuid4().hex
        now = time.time()
        self.notes_index[note_id] = {
            "type": "note",
            "title": title,
            "parent": parent_id,
            "order": self._next_order(parent_id),
            "created": now,
            "modified": now,
            "preview": "",
        }
        self.note_path(note_id).write_text("", encoding="utf-8")
        self.save_index()
        return note_id

    def create_folder_record(self, title, parent_id=None):
        if not self._valid_folder(parent_id):
            parent_id = None
        folder_id = uuid.uuid4().hex
        now = time.time()
        self.notes_index[folder_id] = {
            "type": "folder",
            "title": title,
            "parent": parent_id,
            "order": self._next_order(parent_id),
            "created": now,
            "modified": now,
            "expanded": True,
        }
        self.save_index()
        return folder_id

    def create_new_note(self):
        parent_id = self.selected_parent_folder()
        existing = {v.get("title", "") for v in self.notes_index.values()}
        n = 1
        title = "新笔记"
        while title in existing:
            n += 1
            title = "新笔记 %d" % n
        note_id = self.create_note_record(title, parent_id)
        self.refresh_note_list()
        self.open_note_exclusive(note_id)
        item = self.tree_items.get(note_id)
        if item:
            self.note_list.setCurrentItem(item)
        editor = self.open_editors.get(note_id)
        if editor:
            editor.setFocus()

    def create_new_folder(self):
        parent_id = self.selected_parent_folder()
        existing = {v.get("title", "") for v in self.notes_index.values()}
        n = 1
        title = "新文件夹"
        while title in existing:
            n += 1
            title = "新文件夹 %d" % n
        folder_id = self.create_folder_record(title, parent_id)
        if parent_id in self.notes_index:
            self.notes_index[parent_id]["expanded"] = True
        self.save_index()
        self.refresh_note_list()
        item = self.tree_items.get(folder_id)
        if item:
            self.note_list.setCurrentItem(item)

    def rename_entry(self, entry_id):
        info = self.notes_index.get(entry_id)
        if not info:
            return
        old = info.get("title", "未命名")
        label = "文件夹名称：" if info.get("type") == "folder" else "笔记名称："
        new, ok = QInputDialog.getText(self, "重命名", label, text=old)
        if not ok:
            return
        new = new.strip()
        if not new:
            return
        info["title"] = new
        info["modified"] = time.time()
        self.save_index()
        self.refresh_note_list()
        if info.get("type") == "note" and entry_id in self.open_editors:
            idx = self.tabs.indexOf(self.open_editors[entry_id])
            if idx >= 0:
                self.tabs.setTabText(idx, new)

    def rename_selected_note(self):
        item = self.note_list.currentItem()
        if item:
            self.rename_entry(item.data(0, ENTRY_ID_ROLE))

    def _children_ids(self, parent_id):
        children = [entry_id for entry_id, info in self.notes_index.items() if info.get("parent") == parent_id]
        children.sort(key=lambda eid: self.notes_index[eid].get("order", 0))
        return children

    def _descendant_ids(self, folder_id):
        result = []
        for child_id in self._children_ids(folder_id):
            result.append(child_id)
            if self.notes_index.get(child_id, {}).get("type") == "folder":
                result.extend(self._descendant_ids(child_id))
        return result

    def _delete_note_files(self, note_id):
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

    def delete_entry(self, entry_id):
        info = self.notes_index.get(entry_id)
        if not info:
            return
        if info.get("type") == "folder":
            descendants = self._descendant_ids(entry_id)
            note_count = sum(1 for eid in descendants if self.notes_index.get(eid, {}).get("type") == "note")
            message = "确定删除文件夹“%s”吗？\n\n其中的 %d 篇笔记和子文件夹也会一起删除。" % (info.get("title", "未命名"), note_count)
        else:
            descendants = []
            message = "确定删除“%s”吗？\n\n该笔记和它保存的截图都会删除。" % info.get("title", "未命名")
        reply = QMessageBox.question(
            self, "删除", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ids_to_delete = descendants + [entry_id]
        for eid in ids_to_delete:
            if self.notes_index.get(eid, {}).get("type") == "note":
                self._delete_note_files(eid)
        for eid in ids_to_delete:
            self.notes_index.pop(eid, None)
        self.save_index()
        self.refresh_note_list()
        if not any(v.get("type") == "note" for v in self.notes_index.values()):
            self.create_new_note()

    def delete_selected_note(self):
        item = self.note_list.currentItem()
        if item:
            self.delete_entry(item.data(0, ENTRY_ID_ROLE))

    def show_note_context_menu(self, pos):
        item = self.note_list.itemAt(pos)
        if not item:
            return
        entry_id = item.data(0, ENTRY_ID_ROLE)
        kind = item.data(0, ENTRY_TYPE_ROLE)
        menu = QMenu(self)
        if kind == "folder":
            new_note_act = menu.addAction("新建子笔记")
            new_folder_act = menu.addAction("新建子文件夹")
            menu.addSeparator()
            rename_act = menu.addAction("重命名")
            delete_act = menu.addAction("删除文件夹")
            chosen = menu.exec(self.note_list.viewport().mapToGlobal(pos))
            if chosen == new_note_act:
                self.note_list.setCurrentItem(item)
                self.create_new_note()
            elif chosen == new_folder_act:
                self.note_list.setCurrentItem(item)
                self.create_new_folder()
            elif chosen == rename_act:
                self.rename_entry(entry_id)
            elif chosen == delete_act:
                self.delete_entry(entry_id)
        else:
            open_act = menu.addAction("打开")
            rename_act = menu.addAction("重命名")
            delete_act = menu.addAction("删除")
            chosen = menu.exec(self.note_list.viewport().mapToGlobal(pos))
            if chosen == open_act:
                self.open_note_exclusive(entry_id)
            elif chosen == rename_act:
                self.rename_entry(entry_id)
            elif chosen == delete_act:
                self.delete_entry(entry_id)

    def _entry_matches_search(self, entry_id, keyword):
        info = self.notes_index[entry_id]
        if info.get("type") == "folder":
            return keyword in info.get("title", "").lower()
        haystack = (info.get("title", "") + " " + info.get("preview", "")).lower()
        if keyword in haystack:
            return True
        try:
            body = clean_text_from_html(self.note_path(entry_id).read_text(encoding="utf-8"))
            return keyword in body.lower()
        except Exception:
            return False

    def _ancestor_ids(self, entry_id):
        result = []
        parent_id = self.notes_index.get(entry_id, {}).get("parent")
        while parent_id and parent_id in self.notes_index:
            result.append(parent_id)
            parent_id = self.notes_index[parent_id].get("parent")
        return result

    def _visible_ids_for_search(self, keyword):
        if not keyword:
            return set(self.notes_index.keys())
        visible = set()
        for entry_id in self.notes_index:
            if self._entry_matches_search(entry_id, keyword):
                visible.add(entry_id)
                visible.update(self._ancestor_ids(entry_id))
                if self.notes_index[entry_id].get("type") == "folder":
                    visible.update(self._descendant_ids(entry_id))
        return visible

    def refresh_note_list(self):
        keyword = self.search_box.text().strip().lower()
        visible_ids = self._visible_ids_for_search(keyword)
        current_id = self.current_note_id()
        self.note_list.blockSignals(True)
        self.note_list.clear()
        self.tree_items = {}

        children_by_parent = {}
        for entry_id, info in self.notes_index.items():
            if entry_id not in visible_ids:
                continue
            parent_id = info.get("parent")
            if parent_id not in visible_ids:
                parent_id = None
            children_by_parent.setdefault(parent_id, []).append(entry_id)

        def sort_key(entry_id):
            info = self.notes_index[entry_id]
            return (0 if info.get("type") == "folder" else 1, int(info.get("order", 0)), info.get("title", "").lower())

        for ids in children_by_parent.values():
            ids.sort(key=sort_key)

        def add_children(parent_id, parent_item=None):
            for entry_id in children_by_parent.get(parent_id, []):
                info = self.notes_index[entry_id]
                kind = info.get("type", "note")
                item = QTreeWidgetItem([info.get("title", "未命名")])
                item.setData(0, ENTRY_ID_ROLE, entry_id)
                item.setData(0, ENTRY_TYPE_ROLE, kind)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                if kind == "folder":
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDropEnabled)
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
                    preview = info.get("preview", "")
                    if preview:
                        item.setToolTip(0, preview[:300])
                if parent_item is None:
                    self.note_list.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                self.tree_items[entry_id] = item
                if kind == "folder":
                    add_children(entry_id, item)
                    item.setExpanded(True if keyword else bool(info.get("expanded", True)))

        add_children(None)
        self.note_list.blockSignals(False)
        if current_id in self.tree_items:
            self.note_list.setCurrentItem(self.tree_items[current_id])

    def on_tree_item_expanded(self, item):
        entry_id = item.data(0, ENTRY_ID_ROLE)
        if self.notes_index.get(entry_id, {}).get("type") == "folder":
            self.notes_index[entry_id]["expanded"] = True
            self.save_index()

    def on_tree_item_collapsed(self, item):
        entry_id = item.data(0, ENTRY_ID_ROLE)
        if self.notes_index.get(entry_id, {}).get("type") == "folder":
            self.notes_index[entry_id]["expanded"] = False
            self.save_index()

    def sync_tree_hierarchy(self, *args):
        def walk(parent_item, parent_id):
            count = self.note_list.topLevelItemCount() if parent_item is None else parent_item.childCount()
            for order in range(count):
                item = self.note_list.topLevelItem(order) if parent_item is None else parent_item.child(order)
                entry_id = item.data(0, ENTRY_ID_ROLE)
                if entry_id not in self.notes_index:
                    continue
                self.notes_index[entry_id]["parent"] = parent_id
                self.notes_index[entry_id]["order"] = order
                if self.notes_index[entry_id].get("type") == "folder":
                    walk(item, entry_id)
        walk(None, None)
        self.save_index()

    def open_initial_note(self):
        note_ids = [eid for eid, info in self.notes_index.items() if info.get("type") == "note"]
        if not note_ids:
            self.create_new_note()
            return
        last_note = None
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                last_note = data.get("last_note")
        except Exception:
            pass
        if last_note not in note_ids:
            last_note = max(note_ids, key=lambda nid: self.notes_index[nid].get("modified", 0))
        self.open_note(last_note)

    def open_note_from_item(self, item, column=0):
        entry_id = item.data(0, ENTRY_ID_ROLE)
        if item.data(0, ENTRY_TYPE_ROLE) == "note":
            self.open_note_exclusive(entry_id)

    def open_note_exclusive(self, note_id):
        if note_id not in self.notes_index or self.notes_index[note_id].get("type") != "note":
            return
        for i in range(self.tabs.count() - 1, -1, -1):
            widget = self.tabs.widget(i)
            if isinstance(widget, NoteEditor) and widget.note_id != note_id:
                self.close_tab(i, save_first=True)
        self.open_note(note_id)

    def open_note(self, note_id):
        if note_id not in self.notes_index or self.notes_index[note_id].get("type") != "note":
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
        self.attach_format_tracking(editor)
        self.open_editors[note_id] = editor
        title = self.notes_index[note_id].get("title", "未命名")
        idx = self.tabs.addTab(editor, title)
        self.tabs.setCurrentIndex(idx)
        editor.setFocus()
        self.rebuild_search_matches()
        self.highlight_search_keyword()
        self.sync_heading_combo()

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
        item = self.tree_items.get(widget.note_id)
        if item:
            self.note_list.setCurrentItem(item)

    def current_editor(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, NoteEditor) else None

    def current_note_id(self):
        e = self.current_editor()
        return e.note_id if e else None
