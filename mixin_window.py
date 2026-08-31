# -*- coding: utf-8 -*-
import json
import time
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QGuiApplication
from config import SETTINGS_FILE

class WindowMixin:
    def set_always_on_top(self, enabled):
        geom = self.geometry()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        self.setGeometry(geom)
        self.raise_()
        self.titlebar.pin_btn.setText("取消置顶" if enabled else "置顶")
        self.save_settings()

    def available_geometry(self):
        screen = self.screen() or QGuiApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def snap_to_edge_if_needed(self):
        g = self.available_geometry()
        r = self.geometry()
        distances = {"left": abs(r.left() - g.left()), "right": abs(g.right() - r.right()), "top": abs(r.top() - g.top()), "bottom": abs(g.bottom() - r.bottom())}
        edge, dist = min(distances.items(), key=lambda x: x[1])
        if dist <= self.SNAP_DISTANCE:
            self.edge = edge
            if edge == "left":
                self.move(g.left(), max(g.top(), min(r.top(), g.bottom() - r.height() + 1)))
            elif edge == "right":
                self.move(g.right() - r.width() + 1, max(g.top(), min(r.top(), g.bottom() - r.height() + 1)))
            elif edge == "top":
                self.move(max(g.left(), min(r.left(), g.right() - r.width() + 1)), g.top())
            elif edge == "bottom":
                self.move(max(g.left(), min(r.left(), g.right() - r.width() + 1)), g.bottom() - r.height() + 1)
            self.last_inside_time = time.time()
            self.save_settings()
        else:
            self.edge = None
            self.is_edge_hidden = False
            self.save_settings()

    def hide_to_edge(self):
        if not self.edge or self.is_edge_hidden:
            return
        g = self.available_geometry()
        r = self.geometry()
        if self.edge == "left": self.move(g.left() - r.width() + self.HIDDEN_STRIP, r.top())
        elif self.edge == "right": self.move(g.right() - self.HIDDEN_STRIP + 1, r.top())
        elif self.edge == "top": self.move(r.left(), g.top() - r.height() + self.HIDDEN_STRIP)
        elif self.edge == "bottom": self.move(r.left(), g.bottom() - self.HIDDEN_STRIP + 1)
        self.is_edge_hidden = True

    def expand_from_edge(self):
        if not self.edge or not self.is_edge_hidden:
            return
        g = self.available_geometry()
        r = self.geometry()
        if self.edge == "left": self.move(g.left(), r.top())
        elif self.edge == "right": self.move(g.right() - r.width() + 1, r.top())
        elif self.edge == "top": self.move(r.left(), g.top())
        elif self.edge == "bottom": self.move(r.left(), g.bottom() - r.height() + 1)
        self.is_edge_hidden = False
        self.last_inside_time = time.time()

    def check_edge_behavior(self):
        if not self.isVisible() or self.isMinimized() or not self.edge:
            return
        pos = QCursor.pos(); g = self.available_geometry(); r = self.geometry()
        if self.is_edge_hidden:
            trigger = False
            if self.edge == "left": trigger = (g.left() <= pos.x() <= g.left()+10 and r.top()-8 <= pos.y() <= r.bottom()+8)
            elif self.edge == "right": trigger = (g.right()-10 <= pos.x() <= g.right() and r.top()-8 <= pos.y() <= r.bottom()+8)
            elif self.edge == "top": trigger = (g.top() <= pos.y() <= g.top()+10 and r.left()-8 <= pos.x() <= r.right()+8)
            elif self.edge == "bottom": trigger = (g.bottom()-10 <= pos.y() <= g.bottom() and r.left()-8 <= pos.x() <= r.right()+8)
            if trigger: self.expand_from_edge()
            return
        if self.geometry().adjusted(-8,-8,8,8).contains(pos):
            self.last_inside_time = time.time()
        elif time.time() - self.last_inside_time > 0.75:
            self.hide_to_edge()

    def save_settings(self):
        try:
            x, y = self.x(), self.y()
            if self.edge and self.is_edge_hidden:
                g = self.available_geometry()
                if self.edge == "left": x = g.left()
                elif self.edge == "right": x = g.right() - self.width() + 1
                elif self.edge == "top": y = g.top()
                elif self.edge == "bottom": y = g.bottom() - self.height() + 1
            data = {"x":x,"y":y,"w":self.width(),"h":self.height(),"edge":self.edge,"always_on_top":self.titlebar.pin_btn.isChecked(),"last_note":self.current_note_id(),"splitter_sizes":self.splitter.sizes(),"sidebar_visible":self.sidebar.isVisible(),"sidebar_width":self._last_sidebar_width if not self.sidebar.isVisible() else (self.splitter.sizes()[0] if self.splitter.sizes() else 245)}
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_settings(self):
        if not SETTINGS_FILE.exists(): return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            w = max(760, int(data.get("w", 980))); h = max(460, int(data.get("h", 700)))
            x = int(data.get("x",100)); y = int(data.get("y",100))
            self.setGeometry(x,y,w,h); self.edge = data.get("edge")
            if bool(data.get("always_on_top",False)):
                self.titlebar.pin_btn.blockSignals(True); self.titlebar.pin_btn.setChecked(True); self.titlebar.pin_btn.setText("取消置顶"); self.titlebar.pin_btn.blockSignals(False)
                self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self._last_sidebar_width = int(data.get("sidebar_width",245))
            sidebar_visible = bool(data.get("sidebar_visible",True))
            self.titlebar.sidebar_btn.blockSignals(True); self.titlebar.sidebar_btn.setChecked(sidebar_visible); self.titlebar.sidebar_btn.blockSignals(False)
            self.sidebar.setVisible(sidebar_visible)
            self.titlebar.sidebar_btn.setToolTip("隐藏笔记目录  Ctrl+Shift+L" if sidebar_visible else "显示笔记目录  Ctrl+Shift+L")
        except Exception:
            pass

    def restore_splitter(self):
        try:
            if SETTINGS_FILE.exists():
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")); sizes = data.get("splitter_sizes")
                if isinstance(sizes,list) and len(sizes)==2: self.splitter.setSizes([int(sizes[0]),int(sizes[1])])
                if not self.titlebar.sidebar_btn.isChecked(): self.sidebar.hide()
        except Exception:
            pass

    def closeEvent(self, event):
        self.save_all_open_notes(); self.save_settings(); event.accept()
