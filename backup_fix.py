# -*- coding: utf-8 -*-
"""定时/关闭时自动备份。

ZIP 中按实际内容生成：
    ESP32学习.html
    STM32学习.html
    未分类.html      # 仅当根目录确实存在未分类笔记时生成
    备份信息.json

每个最高级目录保存为一个可独立打开、可再次导入的软件分类 HTML。
"""
import base64
import json
import re
import time
import zipfile
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from PySide6.QtCore import QTimer

from config import DISPLAY_NAME, SETTINGS_FILE
from main_window import MainWindow
import category_export_fix as category_export


BACKUP_FORMAT = "study-notebook-backup"
BACKUP_VERSION = 1


def _default_backup_dir():
    documents = Path.home() / "Documents"
    base = documents if documents.exists() else Path.home()
    return str(base / "StudyNotebook Backups")


def _read_preferences():
    result = {
        "backup_enabled": True,
        "backup_on_close": True,
        "backup_interval_minutes": 30,
        "backup_directory": _default_backup_dir(),
    }
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                result["backup_enabled"] = bool(data.get("backup_enabled", True))
                result["backup_on_close"] = bool(data.get("backup_on_close", True))
                result["backup_interval_minutes"] = max(
                    1, min(1440, int(data.get("backup_interval_minutes", 30)))
                )
                directory = str(data.get("backup_directory", "")).strip()
                if directory:
                    result["backup_directory"] = directory
    except Exception:
        pass
    return result


def _safe_filename(text, fallback="未命名"):
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(text or fallback))
    value = value.strip().rstrip(".") or fallback
    return value[:120]


def _unique_html_name(title, used):
    base = _safe_filename(title)
    name = base + ".html"
    index = 2
    while name.casefold() in used:
        name = "%s (%d).html" % (base, index)
        index += 1
    used.add(name.casefold())
    return name


def _root_entries(self):
    ids = [
        entry_id for entry_id, info in self.notes_index.items()
        if info.get("parent") is None
    ]
    ids.sort(
        key=lambda entry_id: (
            int(self.notes_index[entry_id].get("order", 0)),
            0 if self.notes_index[entry_id].get("type", "note") == "folder" else 1,
            self.notes_index[entry_id].get("title", "").casefold(),
        )
    )
    return ids


def _build_uncategorized_html(self, note_ids):
    """把根目录下未分类笔记合并成一个 HTML，并带结构恢复数据。"""
    parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'>",
        "<title>未分类</title>",
        """
<style>
body { font-family: sans-serif; max-width: 1000px; margin: 32px auto; padding: 0 28px; line-height: 1.65; color: #222; }
h1 { border-bottom: 2px solid #ddd; padding-bottom: 10px; }
.note-section { margin: 18px 0 34px 0; }
.note-title { border-bottom: 1px solid #e6e6e6; padding-bottom: 5px; }
img { max-width: 100%; height: auto; }
</style></head><body>
""",
        "<h1>未分类</h1>",
    ]

    children = []
    for note_id in note_ids:
        info = self.notes_index.get(note_id, {})
        title = info.get("title", "未命名")
        raw = category_export._note_html(self, note_id)
        fragment = category_export._embed_images(
            category_export._body_fragment(raw)
        )
        parts.append("<section class='note-section'>")
        parts.append(
            "<h2 class='note-title'>%s</h2>" % _html_escape(title)
        )
        parts.append(fragment)
        parts.append("</section>")
        children.append(category_export._export_tree_node(self, note_id))

    payload = {
        "format": category_export.EXPORT_FORMAT,
        "version": category_export.EXPORT_VERSION,
        "root": {
            "type": "folder",
            "title": "未分类",
            "children": children,
        },
    }
    raw_payload = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    encoded = base64.b64encode(raw_payload).decode("ascii")
    parts.append(
        "<script id='%s' type='application/x-study-notebook'>%s</script>" % (
            category_export.EXPORT_DATA_ID,
            encoded,
        )
    )
    parts.append("</body></html>")
    return "\n".join(parts)


def _html_escape(text):
    import html
    return html.escape(str(text or ""))


def _next_backup_path(directory):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M")
    base = "StudyNotebook_Backup_%s" % stamp
    path = directory / (base + ".zip")
    index = 2
    while path.exists():
        path = directory / ("%s_%d.zip" % (base, index))
        index += 1
    return path


def _backup_info(self, created_at, reason, category_files, uncategorized_count):
    # 记录原始索引，后续可以在此基础上继续做“一键恢复整个 ZIP”。
    index_snapshot = {}
    for entry_id, info in self.notes_index.items():
        if not isinstance(info, dict):
            continue
        index_snapshot[entry_id] = {
            "type": info.get("type", "note"),
            "title": info.get("title", "未命名"),
            "parent": info.get("parent"),
            "order": int(info.get("order", 0)),
            "expanded": bool(info.get("expanded", True)) if info.get("type") == "folder" else None,
            "folded_headings": info.get("folded_headings", []) if info.get("type") == "note" else None,
        }

    return {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "application": DISPLAY_NAME,
        "created_at": created_at,
        "reason": reason,
        "backup_interval_minutes": int(getattr(self, "backup_interval_minutes", 30)),
        "category_files": category_files,
        "uncategorized_file": "未分类.html" if uncategorized_count > 0 else None,
        "uncategorized_note_count": int(uncategorized_count),
        "notes_index": index_snapshot,
    }


def _create_backup(self, reason="manual", notify=False):
    if getattr(self, "_backup_in_progress", False):
        return None

    directory = str(getattr(self, "backup_directory", "") or "").strip()
    if not directory:
        return None

    self._backup_in_progress = True
    try:
        # 先保存编辑器中尚未落盘的最新内容。
        self.save_all_open_notes()
        self.save_index()

        backup_path = _next_backup_path(directory)
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")
        category_files = []
        root_entries = _root_entries(self)
        uncategorized = [
            entry_id for entry_id in root_entries
            if self.notes_index.get(entry_id, {}).get("type", "note") != "folder"
        ]

        # 只有真的存在未分类笔记时，才预留“未分类.html”这个名字。
        used_names = {"备份信息.json".casefold()}
        if uncategorized:
            used_names.add("未分类.html".casefold())

        with zipfile.ZipFile(
            backup_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            for entry_id in root_entries:
                info = self.notes_index.get(entry_id, {})
                if info.get("type", "note") != "folder":
                    continue

                filename = _unique_html_name(
                    info.get("title", "未命名分类"), used_names
                )
                content, note_count = category_export._build_category_html(self, entry_id)
                archive.writestr(filename, content.encode("utf-8"))
                category_files.append({
                    "title": info.get("title", "未命名分类"),
                    "file": filename,
                    "note_count": int(note_count),
                })

            # 根目录有散落笔记时才生成；没有就完全不创建这个 HTML。
            if uncategorized:
                uncategorized_html = _build_uncategorized_html(self, uncategorized)
                archive.writestr(
                    "未分类.html", uncategorized_html.encode("utf-8")
                )

            info = _backup_info(
                self,
                created_at,
                reason,
                category_files,
                len(uncategorized),
            )
            archive.writestr(
                "备份信息.json",
                json.dumps(info, ensure_ascii=False, indent=2).encode("utf-8"),
            )

        self._last_backup_path = str(backup_path)
        self._last_backup_time = time.time()
        if hasattr(self, "status"):
            label = "自动备份" if reason != "manual" else "备份"
            self.status.setText("%s完成  %s" % (label, time.strftime("%H:%M:%S")))

        if notify:
            QMessageBox.information(
                self,
                "备份完成",
                "备份已保存到：\n%s" % str(backup_path),
            )
        return backup_path
    except Exception as exc:
        if hasattr(self, "status"):
            self.status.setText("备份失败")
        if notify:
            QMessageBox.warning(self, "备份失败", str(exc))
        return None
    finally:
        self._backup_in_progress = False


class BackupSettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("备份设置")
        self.resize(520, 230)

        outer = QVBoxLayout(self)
        tip = QLabel(
            "备份会生成一个 ZIP：每个实际存在的最高级目录各保存为一个 HTML；"
            "只有根目录存在未分类笔记时才生成未分类.html；备份信息.json 始终保留。"
        )
        tip.setWordWrap(True)
        outer.addWidget(tip)

        form = QFormLayout()

        self.enabled_box = QCheckBox("启用定时自动备份")
        self.enabled_box.setChecked(bool(window.backup_enabled))
        form.addRow("定时备份：", self.enabled_box)

        self.interval_box = QSpinBox()
        self.interval_box.setRange(1, 1440)
        self.interval_box.setValue(int(window.backup_interval_minutes))
        self.interval_box.setSuffix(" 分钟")
        form.addRow("备份间隔：", self.interval_box)

        self.close_box = QCheckBox("每次关闭软件时自动备份")
        self.close_box.setChecked(bool(window.backup_on_close))
        form.addRow("关闭时备份：", self.close_box)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(str(window.backup_directory))
        browse_btn = QPushButton("选择…")
        browse_btn.clicked.connect(self.choose_directory)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)
        form.addRow("保存位置：", path_row)

        outer.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def choose_directory(self):
        start = self.path_edit.text().strip() or _default_backup_dir()
        chosen = QFileDialog.getExistingDirectory(
            self, "选择备份保存位置", start
        )
        if chosen:
            self.path_edit.setText(chosen)

    def values(self):
        return {
            "enabled": self.enabled_box.isChecked(),
            "on_close": self.close_box.isChecked(),
            "interval": self.interval_box.value(),
            "directory": self.path_edit.text().strip(),
        }


def _show_backup_settings(self):
    dialog = BackupSettingsDialog(self)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    values = dialog.values()
    if not values["directory"]:
        QMessageBox.warning(self, "备份设置", "请选择备份保存位置。")
        return

    self.backup_enabled = bool(values["enabled"])
    self.backup_on_close = bool(values["on_close"])
    self.backup_interval_minutes = int(values["interval"])
    self.backup_directory = values["directory"]
    self.save_settings()
    self._update_backup_timer()
    self.status.setText("备份设置已保存")


def _update_backup_timer(self):
    timer = getattr(self, "backup_timer", None)
    if timer is None:
        return
    timer.stop()
    if bool(getattr(self, "backup_enabled", True)):
        timer.setInterval(int(self.backup_interval_minutes) * 60 * 1000)
        timer.start()


_original_save_settings = MainWindow.save_settings


def _save_settings_with_backup(self):
    _original_save_settings(self)
    try:
        data = {}
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        data["backup_enabled"] = bool(getattr(self, "backup_enabled", True))
        data["backup_on_close"] = bool(getattr(self, "backup_on_close", True))
        data["backup_interval_minutes"] = int(
            getattr(self, "backup_interval_minutes", 30)
        )
        data["backup_directory"] = str(
            getattr(self, "backup_directory", _default_backup_dir())
        )
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


_original_init = MainWindow.__init__


def _init_with_backup(self, *args, **kwargs):
    prefs = _read_preferences()
    self.backup_enabled = prefs["backup_enabled"]
    self.backup_on_close = prefs["backup_on_close"]
    self.backup_interval_minutes = prefs["backup_interval_minutes"]
    self.backup_directory = prefs["backup_directory"]
    self._backup_in_progress = False
    self._last_backup_path = None
    self._last_backup_time = None

    _original_init(self, *args, **kwargs)

    self.backup_timer = QTimer(self)
    self.backup_timer.setSingleShot(False)
    self.backup_timer.timeout.connect(
        lambda: self.create_backup(reason="timer", notify=False)
    )
    self._update_backup_timer()

    menu = getattr(self.titlebar, "more_menu", None)
    if menu is not None:
        menu.addSeparator()
        backup_now_action = menu.addAction("立即备份")
        backup_settings_action = menu.addAction("备份设置…")
        backup_now_action.triggered.connect(
            lambda: self.create_backup(reason="manual", notify=True)
        )
        backup_settings_action.triggered.connect(self.show_backup_settings)
        self.backup_now_action = backup_now_action
        self.backup_settings_action = backup_settings_action


_original_close_event = MainWindow.closeEvent


def _close_event_with_backup(self, event):
    try:
        if bool(getattr(self, "backup_on_close", True)):
            self.create_backup(reason="close", notify=False)
    except Exception:
        pass
    _original_close_event(self, event)


MainWindow.create_backup = _create_backup
MainWindow.show_backup_settings = _show_backup_settings
MainWindow._update_backup_timer = _update_backup_timer
MainWindow.save_settings = _save_settings_with_backup
MainWindow.__init__ = _init_with_backup
MainWindow.closeEvent = _close_event_with_backup
