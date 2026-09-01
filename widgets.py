# -*- coding: utf-8 -*-
import time
from pathlib import Path
from PySide6.QtCore import Qt, QRect, QPoint, QUrl, Signal
from PySide6.QtGui import (
    QPixmap, QTextCursor, QTextImageFormat, QPainter, QPen, QColor, QPolygon
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QLineEdit, QDialog, QScrollArea
)
from config import ASSETS_DIR, DISPLAY_NAME


class SearchLineEdit(QLineEdit):
    search_next = Signal()
    search_previous = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.search_previous.emit()
            else:
                self.search_next.emit()
            return
        super().keyPressEvent(event)


class ImageViewer(QDialog):
    def __init__(self, pixmap, title="图片查看", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 650)
        self.setMinimumSize(480, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(pixmap)
        label.setMinimumSize(pixmap.size())
        content_layout.addWidget(label)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)


class FoldGutter(QWidget):
    """显示在富文本编辑器左侧的标题折叠三角。"""

    WIDTH = 24

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFixedWidth(self.WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点击三角折叠 / 展开标题内容")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(251, 251, 251))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(95, 95, 95))

        block = self.editor.document().begin()
        while block.isValid():
            level = self.editor.heading_level(block)
            if level > 0 and block.isVisible():
                rect = self.editor.cursorRect(QTextCursor(block))
                y = rect.center().y()
                if -10 <= y <= self.height() + 10:
                    cx = 12
                    if self.editor.is_heading_folded(block):
                        points = QPolygon([
                            QPoint(cx - 3, y - 5),
                            QPoint(cx - 3, y + 5),
                            QPoint(cx + 4, y),
                        ])
                    else:
                        points = QPolygon([
                            QPoint(cx - 5, y - 3),
                            QPoint(cx + 5, y - 3),
                            QPoint(cx, y + 4),
                        ])
                    painter.drawPolygon(points)
            block = block.next()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            block = self.editor.heading_block_at_view_y(event.position().toPoint().y())
            if block and block.isValid():
                self.editor.toggle_heading_fold(block)
                event.accept()
                return
        super().mousePressEvent(event)


class NoteEditor(QTextEdit):
    image_inserted = Signal()
    fold_state_changed = Signal()

    def __init__(self, note_id, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.folded_heading_keys = set()
        self._applying_fold_visibility = False
        self.setAcceptRichText(True)
        self.setPlaceholderText(
            "在这里记录学习内容……\n\n"
            "Ctrl+1 / 2 / 3 可设置标题层级。\n"
            "标题左侧三角可折叠内容。\n"
            "Ctrl+V 可直接粘贴截图，Ctrl+Shift+S 可区域截图。"
        )
        self.setStyleSheet("""
            QTextEdit {
                border: none;
                padding: 14px;
                background: #fbfbfb;
                color: #222;
                selection-background-color: #b8d7ff;
                font-size: 15px;
            }
        """)

        # 给标题折叠三角预留一条类似代码编辑器的 gutter。
        self.setViewportMargins(FoldGutter.WIDTH, 0, 0, 0)
        self.fold_gutter = FoldGutter(self)
        self.verticalScrollBar().valueChanged.connect(self.fold_gutter.update)
        self.textChanged.connect(self._on_document_changed_for_folding)
        self.cursorPositionChanged.connect(self.fold_gutter.update)
        self._position_fold_gutter()

    # ---------- 标题折叠 ----------
    def heading_level(self, block):
        if not block or not block.isValid():
            return 0
        try:
            return int(block.blockFormat().headingLevel())
        except Exception:
            return 0

    def heading_key(self, block):
        """用 层级 + 标题文字 + 同名序号 作为跨保存的折叠标识。"""
        if not block or not block.isValid():
            return None
        level = self.heading_level(block)
        if level <= 0:
            return None
        text = block.text().strip()
        occurrence = 0
        b = self.document().begin()
        while b.isValid():
            if self.heading_level(b) == level and b.text().strip() == text:
                occurrence += 1
            if b == block:
                break
            b = b.next()
        return "%d|%s|%d" % (level, text, occurrence)

    def folded_heading_keys_list(self):
        return sorted(self.folded_heading_keys)

    def set_folded_heading_keys(self, keys):
        self.folded_heading_keys = set(str(k) for k in (keys or []))
        self.apply_fold_visibility()

    def is_heading_folded(self, block):
        key = self.heading_key(block)
        return bool(key and key in self.folded_heading_keys)

    def heading_block_at_view_y(self, y):
        block = self.document().begin()
        best = None
        best_distance = 10 ** 9
        while block.isValid():
            if block.isVisible() and self.heading_level(block) > 0:
                rect = self.cursorRect(QTextCursor(block))
                if rect.top() - 4 <= y <= rect.bottom() + 4:
                    return block
                distance = abs(rect.center().y() - y)
                if distance < best_distance:
                    best = block
                    best_distance = distance
            block = block.next()
        return best if best_distance <= 10 else None

    def current_heading_block(self):
        block = self.textCursor().block()
        if self.heading_level(block) > 0:
            return block
        # 正文中使用顶部“折叠/展开”时，作用于最近的上级标题。
        level_stack = []
        b = self.document().begin()
        while b.isValid() and b.position() <= block.position():
            level = self.heading_level(b)
            if level > 0:
                while level_stack and level_stack[-1][0] >= level:
                    level_stack.pop()
                level_stack.append((level, b))
            b = b.next()
        return level_stack[-1][1] if level_stack else None

    def toggle_current_heading_fold(self):
        block = self.current_heading_block()
        if block and block.isValid():
            self.toggle_heading_fold(block)
            return True
        return False

    def toggle_heading_fold(self, block):
        key = self.heading_key(block)
        if not key:
            return
        if key in self.folded_heading_keys:
            self.folded_heading_keys.remove(key)
        else:
            self.folded_heading_keys.add(key)
        self.apply_fold_visibility()
        self.fold_state_changed.emit()

    def expand_all_headings(self):
        if not self.folded_heading_keys:
            return
        self.folded_heading_keys.clear()
        self.apply_fold_visibility()
        self.fold_state_changed.emit()

    def expand_for_position(self, position):
        """搜索跳转到折叠区时，自动展开遮住目标的所有上级标题。"""
        changed = False
        stack = []
        block = self.document().begin()
        while block.isValid() and block.position() <= position:
            level = self.heading_level(block)
            if level > 0:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, block))
            block = block.next()

        for _, heading_block in stack:
            key = self.heading_key(heading_block)
            if key in self.folded_heading_keys:
                self.folded_heading_keys.remove(key)
                changed = True

        if changed:
            self.apply_fold_visibility()
            self.fold_state_changed.emit()
        return changed

    def apply_fold_visibility(self):
        if self._applying_fold_visibility:
            return
        self._applying_fold_visibility = True
        try:
            folded_levels = []
            block = self.document().begin()
            while block.isValid():
                level = self.heading_level(block)
                if level > 0:
                    while folded_levels and level <= folded_levels[-1]:
                        folded_levels.pop()

                    hidden_by_parent = bool(folded_levels)
                    block.setVisible(not hidden_by_parent)

                    key = self.heading_key(block)
                    if key in self.folded_heading_keys:
                        folded_levels.append(level)
                else:
                    block.setVisible(not bool(folded_levels))
                block = block.next()

            doc = self.document()
            doc.markContentsDirty(0, doc.characterCount())
            self.viewport().update()
            self.fold_gutter.update()
        finally:
            self._applying_fold_visibility = False

    def _on_document_changed_for_folding(self):
        if self._applying_fold_visibility:
            return
        # 编辑标题或在标题上方插入内容后，重新计算折叠范围。
        if self.folded_heading_keys:
            self.apply_fold_visibility()
        self.fold_gutter.update()

    def _position_fold_gutter(self):
        vp = self.viewport()
        self.fold_gutter.setGeometry(1, vp.y(), FoldGutter.WIDTH, vp.height())
        self.fold_gutter.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_fold_gutter()
        self.fold_gutter.update()

    # ---------- 图片 ----------
    def note_assets_dir(self):
        path = ASSETS_DIR / self.note_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_clipboard_image(self, image):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = self.note_assets_dir() / (
            "paste_%s_%03d.png" % (stamp, int(time.time() * 1000) % 1000)
        )
        image.save(str(path))
        self.insert_image_file(path)
        self.image_inserted.emit()

    def insert_image_file(self, path):
        path = Path(path)
        if not path.exists():
            return
        cursor = self.textCursor()
        cursor.beginEditBlock()
        fmt = QTextImageFormat()
        fmt.setName(QUrl.fromLocalFile(str(path)).toString())
        pix = QPixmap(str(path))
        if not pix.isNull():
            max_w = max(300, self.viewport().width() - 50)
            if pix.width() > max_w:
                ratio = max_w / float(pix.width())
                fmt.setWidth(max_w)
                fmt.setHeight(int(pix.height() * ratio))
        cursor.insertBlock()
        cursor.insertImage(fmt)
        cursor.insertBlock()
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def insertFromMimeData(self, source):
        if source.hasImage():
            try:
                self.save_clipboard_image(source.imageData())
                return
            except Exception:
                pass
        if source.hasUrls():
            inserted = False
            for url in source.urls():
                if url.isLocalFile():
                    p = Path(url.toLocalFile())
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                        target = self.note_assets_dir() / (
                            "drop_%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), p.name)
                        )
                        try:
                            target.write_bytes(p.read_bytes())
                            self.insert_image_file(target)
                            inserted = True
                        except Exception:
                            pass
            if inserted:
                self.image_inserted.emit()
                return
        super().insertFromMimeData(source)

    def mouseDoubleClickEvent(self, event):
        cursor = self.cursorForPosition(event.position().toPoint())
        fmt = cursor.charFormat()
        if fmt.isImageFormat():
            src = fmt.toImageFormat().name()
            local_path = None
            if src.startswith("file:"):
                local_path = QUrl(src).toLocalFile()
            else:
                p = Path(src)
                if p.exists():
                    local_path = str(p)
            if local_path and Path(local_path).exists():
                pix = QPixmap(local_path)
                if not pix.isNull():
                    ImageViewer(pix, Path(local_path).name, self).exec()
                    return
        super().mouseDoubleClickEvent(event)


class SnipOverlay(QWidget):
    captured = Signal(QPixmap)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__(None)
        self.screen = screen
        self.origin = QPoint()
        self.current = QPoint()
        self.selecting = False
        self.shot = screen.grabWindow(0)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(screen.geometry())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.shot)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self.selecting:
            rect = QRect(self.origin, self.current).normalized()
            if rect.width() > 2 and rect.height() > 2:
                painter.drawPixmap(rect, self.shot, rect)
                painter.setPen(QPen(QColor(60, 160, 255), 2))
                painter.drawRect(rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.current = self.origin
            self.selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.selecting:
            self.current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.selecting:
            self.current = event.position().toPoint()
            rect = QRect(self.origin, self.current).normalized()
            self.selecting = False
            if rect.width() >= 8 and rect.height() >= 8:
                dpr = self.shot.devicePixelRatio()
                pixel_rect = QRect(
                    int(rect.x() * dpr), int(rect.y() * dpr),
                    int(rect.width() * dpr), int(rect.height() * dpr)
                )
                pix = self.shot.copy(pixel_rect)
                pix.setDevicePixelRatio(1.0)
                self.captured.emit(pix)
                self.close()
            else:
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
        else:
            super().keyPressEvent(event)


class ResizeHandle(QWidget):
    def __init__(self, window, edges, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.edges = edges
        self.start_global = None
        self.start_geometry = None
        if edges in (("left", "top"), ("right", "bottom")):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (("right", "top"), ("left", "bottom")):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif "left" in edges or "right" in edges:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_global = event.globalPosition().toPoint()
            self.start_geometry = self.window.geometry()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.start_global is None or self.start_geometry is None:
            return
        p = event.globalPosition().toPoint()
        dx = p.x() - self.start_global.x()
        dy = p.y() - self.start_global.y()
        g = QRect(self.start_geometry)
        min_w = self.window.minimumWidth()
        min_h = self.window.minimumHeight()
        if "left" in self.edges:
            g.setLeft(min(g.left() + dx, g.right() - min_w + 1))
        if "right" in self.edges:
            g.setRight(max(g.right() + dx, g.left() + min_w - 1))
        if "top" in self.edges:
            g.setTop(min(g.top() + dy, g.bottom() - min_h + 1))
        if "bottom" in self.edges:
            g.setBottom(max(g.bottom() + dy, g.top() + min_h - 1))
        self.window.setGeometry(g)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_global = None
            self.start_geometry = None
            self.window.save_settings()
            event.accept()


class TitleBar(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.drag_offset = None
        self.setFixedHeight(40)
        self.setStyleSheet(
            "QWidget { background: #ececec; } "
            "QPushButton { border: none; padding: 5px 9px; background: transparent; color: #333; } "
            "QPushButton:hover { background: #dcdcdc; } "
            "QPushButton#closeButton:hover { background: #e81123; color: white; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(2)
        self.title = QLabel(DISPLAY_NAME)
        self.title.setStyleSheet("font-weight: 600; color: #333;")
        layout.addWidget(self.title)
        layout.addStretch()
        self.sidebar_btn = QPushButton("目录")
        self.sidebar_btn.setCheckable(True)
        self.sidebar_btn.setChecked(True)
        self.new_btn = QPushButton("新建")
        self.capture_btn = QPushButton("截图")
        self.export_btn = QPushButton("导出")
        self.pin_btn = QPushButton("置顶")
        self.pin_btn.setCheckable(True)
        self.min_btn = QPushButton("—")
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeButton")
        for b in (
            self.sidebar_btn, self.new_btn, self.capture_btn, self.export_btn,
            self.pin_btn, self.min_btn, self.close_btn
        ):
            layout.addWidget(b)
        self.sidebar_btn.toggled.connect(window.set_sidebar_visible)
        self.new_btn.clicked.connect(window.create_new_note)
        self.capture_btn.clicked.connect(window.start_capture)
        self.export_btn.clicked.connect(window.export_current_note)
        self.pin_btn.toggled.connect(window.set_always_on_top)
        self.min_btn.clicked.connect(window.showMinimized)
        self.close_btn.clicked.connect(window.close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = (
                event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
            )
            self.window.expand_from_edge()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = None
            self.window.snap_to_edge_if_needed()
            event.accept()
