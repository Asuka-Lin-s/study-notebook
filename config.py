# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

APP_NAME = "EdgeStudyNotebook"
DISPLAY_NAME = "学习笔记"

def app_data_dir():
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    (path / "notes").mkdir(parents=True, exist_ok=True)
    (path / "assets").mkdir(parents=True, exist_ok=True)
    return path

DATA_DIR = app_data_dir()
NOTES_DIR = DATA_DIR / "notes"
ASSETS_DIR = DATA_DIR / "assets"
INDEX_FILE = DATA_DIR / "notes_index.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
LEGACY_NOTE_FILE = DATA_DIR / "note.html"

def clean_text_from_html(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
