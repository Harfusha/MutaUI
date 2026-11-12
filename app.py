"""Mutagen Control 8.2 — Windows desktop companion for Mutagen CLI.

Start with: python app.py
Preview (offline demo, actions disabled): python app.py --demo
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from functools import partial

from PySide6.QtCore import (Qt, QTimer, QObject, QRunnable, QThreadPool,
                            Signal, QRectF, QPointF, QEvent)
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QKeySequence, QShortcut)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QInputDialog, QLayout,
    QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QSystemTrayIcon,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QProgressBar, QToolTip, QListWidget, QListWidgetItem,
)

from mutagen_client import (MutagenClient, MutagenError, ProcessSampler, Snapshot,
                            classify, conflict_count, endpoint_text, example_snapshot,
                            human_bytes, problem_count, read_registration)
from monitoring import HistoryStore, ForwardTrafficMeter, Sample, statistics_from_file, query_metrics_from_file
from insights import AlertEngine, safe_diagnostic_report
from endpoint_inspector import summary as inspect_session
from server_groups import group_servers, session_servers
from log_stream import FileTail, TrackedLogLines
from performance import envelope_downsample, nearest_time_index, RefreshGate, PollBackoff
from async_recorder import AsyncRecorder
from sync_profiles import PROFILES, profile_flags, native_config_text, AdaptivePolling

BG = "#0B1019"
CARD = "#141D2A"
CARD2 = "#1C2B3A"
BORDER = "#2A394A"
MUTED = "#A0AEC0"
TEXT = "#F1F6FA"
TEAL = "#61E0B9"
BLUE = "#7AAEFF"
AMBER = "#F2BF70"
RED = "#FB8696"

CSS = f"""
QWidget {{ color: {TEXT}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
QMainWindow, QWidget#main, QScrollArea, QWidget#scrollbody {{ background: {BG}; }}
QFrame#sidebar {{ background: #101824; border-right: 1px solid {BORDER}; }}
QScrollArea#navscroll, QWidget#navcontent {{ background: #101824; border: 0; }}
QListWidget {{ background:#111D2B; border:1px solid {BORDER}; border-radius:9px; padding:5px; }}
QListWidget::item {{ padding:12px; margin:2px; border-radius:7px; }}
QListWidget::item:selected {{ background:#1D4B47; color:{TEAL}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 15px; }}
QFrame#inner {{ background: #182536; border: 1px solid {BORDER}; border-radius: 11px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#eyebrow {{ color: {MUTED}; font-size: 11px; font-weight: 700; }}
QLabel#hero {{ font-size: 25px; font-weight: 750; }}
QLabel#logo {{ font-size: 21px; font-weight: 800; letter-spacing: .2px; }}
QLabel#metric {{ font-size: 28px; font-weight: 750; }}
QLabel#section {{ font-size: 16px; font-weight: 700; }}
QLabel#smallnum {{ font-size: 19px; font-weight: 700; }}
QPushButton {{ background: {CARD2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 9px;
              padding: 10px 15px; font-weight: 600; }}
QPushButton:hover {{ background: #26344E; border-color: #435675; }}
QPushButton:pressed {{ background: #344866; }}
QPushButton:disabled {{ color: #9BAAC0; background: #171E2D; border-color: #33435B; }}
QPushButton#primary {{ background: {TEAL}; color: #071A1A; border-color: {TEAL}; font-weight: 800; }}
QPushButton#primary:hover {{ background: #94F4D9; }}
QPushButton#primary:pressed {{ background: #3EC6A2; }}
QPushButton#danger {{ background: #3B2537; border-color: #734050; color: #FFACB8; }}
QPushButton#danger:hover {{ background: #513044; }}
QPushButton#nav {{ text-align: left; background: transparent; border: 1px solid transparent;
                  color: {MUTED}; border-radius: 9px; padding: 9px 13px; font-size: 13px; }}
QPushButton#nav:hover {{ background: #1A263A; color: {TEXT}; }}
QPushButton#nav:checked {{ background: #173A35; border-color: #36685F; color: {TEAL}; font-weight: 800; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{ background: #101829; color: {TEXT};
                           border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 11px;
                           min-height: 22px; selection-background-color: #385F6A; }}
QComboBox {{ padding-right: 27px; }}
QComboBox::drop-down {{ width: 23px; border: 0; }}
QComboBox::down-arrow {{ image: none; border: 2px solid {MUTED}; width: 6px; height: 6px; }}
QSpinBox {{ padding-right: 20px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {TEAL}; }}
QComboBox QAbstractItemView {{ background: #17243A; border: 1px solid {BORDER}; selection-background-color: #2D4955; }}
QTableWidget {{ background: {CARD}; alternate-background-color: #182136; border: 0; border-radius: 10px;
                gridline-color: transparent; selection-background-color: #233D4F; }}
QTableWidget::item {{ padding: 8px 8px; border-bottom: 1px solid #232F46; }}
QTableWidget::item:selected {{ color: white; }}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: 0;
                        border-bottom: 1px solid {BORDER}; padding: 11px 8px; font-size: 11px; font-weight: 750; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: #355063; border-radius: 4px; min-height: 28px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: #355063; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {BORDER}; border-radius: 4px;
                        background: #101829; }}
QCheckBox::indicator:checked {{ background: {TEAL}; border-color: {TEAL}; }}
QCheckBox::indicator:hover {{ border-color: {TEAL}; }}
QDialog {{ background: #101729; }}
QDialogButtonBox QPushButton {{ min-width: 90px; }}
QMenu {{ background: #17243A; border: 1px solid {BORDER}; border-radius: 9px; padding: 6px; }}
QMenu::item {{ padding: 9px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: #233D4F; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 10px; }}
QProgressBar {{ background:#101829; border:1px solid #33425D; border-radius:6px; min-height:16px; text-align:center; font-size: 11px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3BC8A6, stop:1 #55E6C1); border-radius:5px; }}
QToolTip {{ background: #1E2B43; border: 1px solid #41536E; color: white; padding: 7px 10px; border-radius: 6px; }}
"""


def settings_path() -> Path:
    root = Path(os.getenv("APPDATA") or str(Path.home() / ".config")) / "MutagenControl"
    return root / "settings.json"


def read_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_settings(data: dict) -> None:
    path = settings_path()
    # Atomic replacement avoids a corrupted settings file after a crash/power loss.
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".tmp", delete=False) as f:
            temp = Path(f.name)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def label(text: str, *, muted=False, size=None, bold=False) -> QLabel:
    result = QLabel(text)
    if muted:
        result.setObjectName("muted")
    if size or bold:
        style = []
        if size: style.append(f"font-size: {size}px")
        if bold: style.append("font-weight: 700")
        result.setStyleSheet(";".join(style))
    return result


def button(text: str, fn=None, *, kind="", minwidth=0) -> QPushButton:
    b = QPushButton(text)
    if kind: b.setObjectName(kind)
    if minwidth: b.setMinimumWidth(minwidth)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if fn: b.clicked.connect(fn)
    return b


def card(*, layout=None) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    l = QVBoxLayout(f)
    l.setContentsMargins(21, 19, 21, 19)
    l.setSpacing(13)
    return f, l


def separator() -> QFrame:
    f = QFrame(); f.setFixedHeight(1); f.setStyleSheet(f"background:{BORDER}; border:0")
    return f


def field_format(field: str, value: float) -> str:
    if field == "cpu": return f"{value:.1f} %"
    if field == "memory": return human_bytes(value)
    return human_bytes(value) + "/s"


class Graph(QWidget):
    """Time-aware, interactive, zero-based line/area chart with optional second series."""
    def __init__(self, color: str, parent=None, *, unit="number", secondary=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.secondary = QColor(secondary) if secondary else None
        self.unit = unit
        self.points = deque(maxlen=720)  # (timestamp, primary, secondary)
        self.timestamps = []
        self.hover_index = -1
        self._geometry_revision = 0
        self._geometry_cache = None
        self.setMouseTracking(True)
        self.setMinimumHeight(153)

    def add(self, value: float, second=None, ts=None):
        stamp = float(time.time() if ts is None else ts)
        self.points.append((stamp, float(value), float(second) if second is not None else None))
        self.timestamps = [point[0] for point in self.points]
        self._geometry_revision += 1
        self._geometry_cache = None
        self.update()

    def set_data(self, entries):
        values = envelope_downsample(
            ((float(t), float(x or 0), None if y is None else float(y))
             for t, x, y in entries), max_points=600)
        if tuple(self.points) == tuple(values):
            return
        self.points = deque(values, maxlen=720)
        self.timestamps = [point[0] for point in values]
        self.hover_index = -1
        self._geometry_revision += 1
        self._geometry_cache = None
        self.update()

    def amount(self, value):
        if self.unit == "bytes_s":
            return human_bytes(value) + "/s"
        if self.unit == "memory":
            return human_bytes(value)
        if self.unit == "percent":
            return f"{value:.1f} %"
        return f"{value:.1f}" if abs(value) < 10 else f"{value:.0f}"

    def _plot_rect(self):
        return self.rect().adjusted(68, 15, -17, -30)

    def mouseMoveEvent(self, event):
        items = list(self.points)
        area = self._plot_rect()
        if not items or not area.contains(event.position().toPoint()):
            self.hover_index = -1
            QToolTip.hideText()
            self.update()
            return
        beginning = items[0][0]
        span = max(1.0, items[-1][0] - beginning)
        fractional = max(0.0, min(1.0, (event.position().x() - area.left()) / max(1, area.width())))
        target = beginning + fractional * span
        new_index = nearest_time_index(self.timestamps, target)
        if new_index == self.hover_index:
            return  # Avoid repainting the entire chart for every mouse pixel.
        self.hover_index = new_index
        t, first, second = items[self.hover_index]
        value = self.amount(first)
        if second is not None:
            value += " / " + self.amount(second)
        QToolTip.showText(event.globalPosition().toPoint(),
                          datetime.fromtimestamp(t).strftime("%d.%m. %H:%M:%S") + "\n" + value, self)
        self.update()

    def leaveEvent(self, event):
        self.hover_index = -1
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            p.end(); return
        items = list(self.points)
        upper = max([x for _, x, _ in items] + [y for _, _, y in items if y is not None] + [1.0]) * 1.17
        if self.unit == "percent" and upper <= 100: upper = 100
        axis_font = QFont("Segoe UI"); axis_font.setPixelSize(10)
        p.setFont(axis_font)
        for idx in range(5):
            y = rect.bottom() - rect.height() * idx / 4
            p.setPen(QPen(QColor("#2A3650"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, y-9, rect.left()-9, 18), Qt.AlignmentFlag.AlignRight, self.amount(upper*idx/4))
        if not items:
            p.setPen(QColor(MUTED))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Čekám na první vzorky…")
            p.end(); return
        start, end = items[0][0], items[-1][0]
        span = max(1.0, end - start)
        p.setPen(QColor(MUTED))
        timefmt = "%H:%M:%S" if span < 1200 else "%d.%m. %H:%M"
        p.drawText(QRectF(rect.left(), rect.bottom()+8, 165, 18),
                   Qt.AlignmentFlag.AlignLeft, datetime.fromtimestamp(start).strftime(timefmt))
        p.drawText(QRectF(rect.right()-165, rect.bottom()+8, 165, 18),
                   Qt.AlignmentFlag.AlignRight, datetime.fromtimestamp(end).strftime(timefmt))
        cache_key = (self._geometry_revision, rect.left(), rect.top(), rect.width(), rect.height())
        if self._geometry_cache is None or self._geometry_cache[0] != cache_key:
            # Path generation involves hundreds of QPointF/QPainterPath allocations.
            # Cache it until new data or a resize; hover only redraws the cursor.
            render_items = (items if len(items) > 1 else
                            [items[0], (items[0][0] + 1, items[0][1], items[0][2])])
            def coords(index):
                return [QPointF(rect.left() + max(0, min(1, (t - start) / span)) * rect.width(),
                                rect.bottom() - max(0, val / upper) * rect.height())
                        for t, x, y in render_items for val in [x if index == 1 else (y or 0)]]
            max_gap = max(15.0, span / 110.0)
            def paths(points):
                runs = []
                current = [points[0]]
                for i in range(1, len(points)):
                    if render_items[i][0] - render_items[i-1][0] > max_gap:
                        runs.append(current)
                        current = []
                    current.append(points[i])
                runs.append(current)
                output = []
                for run in runs:
                    if not run:
                        continue
                    path = QPainterPath(run[0])
                    for point in run[1:]:
                        path.lineTo(point)
                    area = QPainterPath(path)
                    if len(run) > 1:
                        area.lineTo(QPointF(run[-1].x(), rect.bottom()))
                        area.lineTo(QPointF(run[0].x(), rect.bottom()))
                        area.closeSubpath()
                    output.append((path, area, run[-1], len(run)))
                return output
            primary_pts = coords(1)
            primary_paths = paths(primary_pts)
            secondary_paths = paths(coords(2)) if self.secondary else []
            self._geometry_cache = (cache_key, primary_pts, primary_paths, secondary_paths)
        else:
            _, primary_pts, primary_paths, secondary_paths = self._geometry_cache
        def draw_cached(paths_to_draw, color, fill):
            for line_path, area_path, last_point, count in paths_to_draw:
                if count == 1:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(color)
                    p.drawEllipse(last_point, 3.5, 3.5)
                    continue
                if fill:
                    gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
                    top = QColor(color); top.setAlpha(78)
                    bottom = QColor(color); bottom.setAlpha(3)
                    gradient.setColorAt(0, top); gradient.setColorAt(1, bottom)
                    p.fillPath(area_path, QBrush(gradient))
                p.setPen(QPen(color, 2.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(line_path)
            if paths_to_draw:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawEllipse(paths_to_draw[-1][2], 3.5, 3.5)
        draw_cached(primary_paths, self.color, True)
        if self.secondary:
            draw_cached(secondary_paths, self.secondary, False)
        if 0 <= self.hover_index < len(primary_pts):
            point = primary_pts[self.hover_index]
            # Vertical + horizontal crosshair
            p.setPen(QPen(QColor("#71809C"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(point.x(), rect.top()), QPointF(point.x(), rect.bottom()))
            p.drawLine(QPointF(rect.left(), point.y()), QPointF(rect.right(), point.y()))
            p.setBrush(self.color); p.setPen(QPen(QColor("#121C2D"), 2))
            p.drawEllipse(point, 5, 5)
        p.end()


class HealthRing(QWidget):
    """High-DPI, zero-timer health indicator; repaint only on status changes."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.total = 0
        self.healthy = 0
        self.setFixedSize(122, 122)
        self.setToolTip("Podíl relací bez hlášených problémů")

    def set_health(self, total: int, problem: int):
        total = max(0, int(total))
        healthy = max(0, total - max(0, int(problem)))
        if (total, healthy) != (self.total, self.healthy):
            self.total, self.healthy = total, healthy
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(18, 18, 86, 86)
        p.setPen(QPen(QColor("#314354"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(area, 0, 360 * 16)
        if self.total:
            fraction = self.healthy / self.total
            ring_color = QColor(TEAL if fraction >= .9 else AMBER if fraction >= .7 else RED)
            p.setPen(QPen(ring_color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(area, 90 * 16, -round(fraction * 360 * 16))
        p.setPen(QColor(TEXT))
        value_font = QFont("Segoe UI"); value_font.setPixelSize(23); value_font.setWeight(QFont.Weight.Bold)
        p.setFont(value_font)
        value = f"{self.healthy / self.total:.0%}" if self.total else "—"
        p.drawText(QRectF(12, 44, 98, 30), Qt.AlignmentFlag.AlignCenter, value)
        p.setPen(QColor(MUTED))
        caption_font = QFont("Segoe UI"); caption_font.setPixelSize(9)
        p.setFont(caption_font)
        p.drawText(QRectF(20, 77, 82, 13), Qt.AlignmentFlag.AlignCenter, "bez problémů")
        p.end()


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, func):
        super().__init__()
        self.func = func
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.result.emit(self.func())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


class SessionDialog(QDialog):
    def __init__(self, kind: str, parent=None, default_profile: str = "default"):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle("Nová synchronizace" if kind == "sync" else "Nové přesměrování")
        self.setMinimumWidth(520)
        box = QVBoxLayout(self)
        box.setSpacing(16); box.setContentsMargins(26, 24, 26, 22)
        box.addWidget(label("Nastavení nové relace", size=21, bold=True))
        box.addWidget(label("Cesty mohou být lokální, SSH nebo Docker. U SSH používejte předem připravené klíče.", muted=True))
        form = QFormLayout(); form.setVerticalSpacing(14); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.name = QLineEdit(); self.name.setPlaceholderText("např. muj-projekt")
        form.addRow("Název", self.name)
        self.a = QLineEdit(); self.b = QLineEdit()
        if kind == "sync":
            self.a.setPlaceholderText(r"C:\Projects\web")
            self.b.setPlaceholderText("user@server:/var/www/web")
        else:
            self.a.setPlaceholderText("tcp:localhost:8080")
            self.b.setPlaceholderText("docker://web:tcp:localhost:8080")
        rowa = QHBoxLayout(); rowa.addWidget(self.a)
        if kind == "sync": rowa.addWidget(button("…", self.browse_alpha))
        form.addRow("ALPHA" if kind == "sync" else "Zdroj", rowa)
        form.addRow("BETA" if kind == "sync" else "Cíl", self.b)
        self.mode = QComboBox()
        self.mode.addItems(["two-way-safe", "two-way-resolved", "one-way-safe", "one-way-replica"])
        self.ignore = QPlainTextEdit(); self.ignore.setFixedHeight(75)
        self.ignore.setPlaceholderText("Jeden ignorovaný vzor na řádek, např. node_modules")
        self.ignore_vcs = QCheckBox("Ignorovat .git, .svn a další VCS")
        self.pause = QCheckBox("Vytvořit pozastavenou")
        if kind == "sync":
            self.profile = QComboBox()
            for code, (title, _flags) in PROFILES.items():
                self.profile.addItem(title, code)
            self.profile.setCurrentIndex(max(0, self.profile.findData(default_profile)))
            form.addRow("Sledování změn", self.profile)
            form.addRow("Režim", self.mode)
            form.addRow("Ignorovat", self.ignore)
            form.addRow("", self.ignore_vcs)
        form.addRow("", self.pause)
        box.addLayout(form)
        info = label("Pozor: režim one-way-replica může přepisovat a mazat soubory v cíli." if kind == "sync"
                     else "Přesměrování zpřístupní cílové spojení prostřednictvím zadaného zdroje.", muted=True)
        info.setWordWrap(True); box.addWidget(info)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        controls.button(QDialogButtonBox.StandardButton.Ok).setText("Vytvořit relaci")
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText("Zrušit")
        controls.accepted.connect(self.validate); controls.rejected.connect(self.reject)
        box.addWidget(controls)

    def browse_alpha(self):
        selected = QFileDialog.getExistingDirectory(self, "Lokální složka ALPHA")
        if selected: self.a.setText(selected.replace("/", "\\") if os.name == "nt" else selected)

    def validate(self):
        if not self.a.text().strip() or not self.b.text().strip():
            QMessageBox.warning(self, "Chybějící údaje", "Vyplňte oba koncové body.")
            return
        if self.kind == "sync" and self.mode.currentText() == "one-way-replica":
            response = QMessageBox.warning(self, "Rizikový režim",
                "Režim one-way-replica může přepsat nebo odstranit data na BETA. Pokračovat?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes: return
        self.accept()

    def arguments(self):
        args = []
        if self.name.text().strip(): args.append("--name=" + self.name.text().strip())
        if self.pause.isChecked(): args.append("--paused")
        if self.kind == "sync":
            args.append("--mode=" + self.mode.currentText())
            args.extend(profile_flags(self.profile.currentData()))
            if self.ignore_vcs.isChecked(): args.append("--ignore-vcs")
            for entry in self.ignore.toPlainText().splitlines():
                if entry.strip(): args.append("--ignore=" + entry.strip())
        return [*args, self.a.text().strip(), self.b.text().strip()]


class QuickNavigator(QDialog):
    """Keyboard-first, no-network palette for switching pages instantly."""
    PAGES = ("Přehled", "Synchronizace", "Přesměrování", "Historie akcí", "Daemon",
             "Nastavení", "Monitoring", "Diagnostika", "Upozornění", "Obě strany", "Servery")
    GLYPHS = ("◈", "⇄", "↗", "≡", "◉", "⚙", "▥", "⚕", "♢", "⇄", "▣")
    CAPTIONS = (
        "Přehled relací a spotřeba systémových prostředků",
        "Správa synchronizačních relací",
        "Správa port-forwarding relací",
        "Záznamy příkazů provedených přes aplikaci",
        "Řízení a registrace Mutagen daemonu",
        "Nastavení CLI, intervalů a chování",
        "Historické grafy CPU, RAM a přenosů",
        "Problémy relací a export diagnostiky",
        "Limity prostředků a pravidla upozornění",
        "Stav ALPHA/BETA endpointů z daemonu",
        "Skupiny serverů a hromadné akce",
    )

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Rychlá navigace  ·  Ctrl+K")
        self.setMinimumSize(520, 420)
        self.target = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(23, 21, 23, 21)
        layout.setSpacing(13)
        layout.addWidget(label("Přejít na stránku", size=19, bold=True))
        hint = label("Pište název sekce · Enter / dvojklik pro přechod · Escape pro zavření", muted=True)
        layout.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Hledat stránku…")
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSpacing(2)
        layout.addWidget(self.list, 1)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.choose)
        self.list.itemActivated.connect(lambda _: self.choose())
        self.list.itemDoubleClicked.connect(lambda _: self.choose())
        self.filter("")
        self.search.setFocus()

    def filter(self, term):
        self.list.clear()
        for index, page in enumerate(self.PAGES):
            if term.casefold().strip() in page.casefold():
                glyph = self.GLYPHS[index] if index < len(self.GLYPHS) else "·"
                caption = self.CAPTIONS[index] if index < len(self.CAPTIONS) else ""
                item = QListWidgetItem(f"  {glyph}   {page}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(caption)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def choose(self):
        item = self.list.currentItem()
        if item is not None:
            self.target = int(item.data(Qt.ItemDataRole.UserRole))
            self.accept()


class MainWindow(QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.conf = read_settings()
        self.client = MutagenClient(self.conf.get("binary", ""))
        self.sampler = ProcessSampler()
        self.snapshot = example_snapshot() if demo else Snapshot(binary=self.client.binary)
        self.cpu_series = deque(maxlen=50)
        self.mem_series = deque(maxlen=50)
        try:
            self.history = HistoryStore(":memory:" if demo else settings_path().parent / "metrics.sqlite3")
        except (OSError, sqlite3.DatabaseError):
            self.history = HistoryStore()  # Still works without a writable user directory.
        # A dedicated writer connection batches commits outside the Qt event loop.
        # The demo uses in-memory SQLite and writes directly to its own connection.
        self.recorder = None if demo or self.history.path == ':memory:' else AsyncRecorder(self.history.path)
        if demo:
            self.seed_demo_history()
        self.traffic_meter = ForwardTrafficMeter()
        self.traffic_rates = (0.0, 0.0)
        self.last_metrics = {"cpu": 0, "memory": 0, "read_rate": 0, "write_rate": 0, "processes": 0}
        self.previous_states = None
        self.previous_daemon = None
        self.session_counts = (0, 0)
        self.alert_engine = AlertEngine()
        self.chart_frozen = False
        self.tail_file = None
        self.tail_lines = TrackedLogLines(maxlen=1200)
        self._tail_render_epoch = -1
        self._tail_render_count = 0
        self._tail_render_filter = ""
        self._stats_cache_at = 0.0
        self._stats_cache_range = None
        self._stats_pending = False
        self.favorites = {kind: set(str(x) for x in self.conf.get("favorites", {}).get(kind, []))
                          for kind in ("sync", "forward")}
        self.logs = deque((f"[{datetime.fromtimestamp(ts):%d.%m. %H:%M:%S}] {message}"
                           for ts, severity, message in self.history.events(800)), maxlen=800)
        self.pending_poll = False
        self.pending_action = False
        self.poll_backoff = PollBackoff(base=max(2, int(self.conf.get('interval', 4))))
        self.adaptive_policy = AdaptivePolling(
            fast=int(self.conf.get("adaptive_fast", 2)),
            idle=int(self.conf.get("adaptive_idle", 30)),
            quiet_after=int(self.conf.get("adaptive_quiet", 90)))
        self._poll_started_at = 0.0
        self.current_kind = "sync"
        self.current_id = ""
        self._allow_exit = False
        self.workers = set()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)
        self._resource_pending = False
        self._version_cache = ("", 0.0, "")
        self._chart_dashboard_gate = RefreshGate(2.8)
        self._chart_monitor_gate = RefreshGate(3.2)
        self._chart_query_pending = False
        self._chart_query_reschedule = False
        self._table_signatures = {}
        self._tail_render_pending = False
        self._eco_hidden = False
        self.setWindowTitle("Mutagen Control 8.2 · Server Manager")
        self.setMinimumSize(940, 650)
        self.resize(1480, 940)
        self.setStyleSheet(CSS)
        self.setWindowIcon(self.make_icon())
        self.create_ui()
        self.create_tray()
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.refresh(force=True))
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.refresh(force=True))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_current_session)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=partial(self.set_page, 6))
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.open_navigator)
        # Direct page shortcuts: Ctrl+1 through Ctrl+0 (pages 0–9) and Ctrl+Shift+1 for page 10
        for _i in range(10):
            _idx = _i  # capture
            QShortcut(QKeySequence(f"Ctrl+{(_i + 1) % 10 if _i < 9 else 0}"), self,
                      activated=partial(self.set_page, _idx))
        QShortcut(QKeySequence("Ctrl+Shift+1"), self, activated=partial(self.set_page, 10))
        self.add_log("Aplikace spuštěna" + (" (DEMO režim)" if demo else ""))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.poll_period_ms())
        self.metric_timer = QTimer(self)
        self.metric_timer.timeout.connect(self.refresh_resources)
        self.metric_timer.start(self.metric_period_ms())
        self.tail_timer = QTimer(self)
        self.tail_timer.timeout.connect(self.poll_tail)
        # Do not wake up the UI every 900 ms until a log file is selected.
        QTimer.singleShot(200, lambda: self.refresh(force=True))
        QTimer.singleShot(300, self.refresh_resources)

    def poll_period_ms(self) -> int:
        eco = self._eco_hidden and bool(self.conf.get("eco_tray", True))
        return self.adaptive_policy.interval(
            enabled=bool(self.conf.get("adaptive_poll", True)),
            normal=int(self.conf.get("interval", 4)), eco=eco) * 1000

    def metric_period_ms(self) -> int:
        """User-selectable detail rate, with an optional low-impact tray mode."""
        seconds = max(1, min(10, int(self.conf.get("metric_interval", 2))))
        if self._eco_hidden and self.conf.get("eco_tray", True):
            seconds = max(6, seconds)
        return seconds * 1000

    def update_polling_mode(self):
        self._eco_hidden = not self.isVisible() or self.isMinimized()
        if hasattr(self, "metric_timer"):
            self.metric_timer.setInterval(self.metric_period_ms())
        if hasattr(self, "timer"):
            self.timer.setInterval(self.poll_period_ms())

    def showEvent(self, event):
        super().showEvent(event)
        self.update_polling_mode()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.update_polling_mode()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.update_polling_mode()

    def seed_demo_history(self):
        """Populate illustrative graphs offline (only in explicitly marked demo mode)."""
        now = time.time()
        for i in range(125):
            phase = i / 5.0
            spike = 33 if i % 43 in range(12, 17) else 0
            cpu = max(0.0, 6 + 5 * math.sin(phase) + spike)
            memory = int((112 + i * 0.22 + 7 * math.sin(phase / 2)) * 1024**2)
            sample = Sample(ts=now - (124-i)*14, cpu=cpu, memory=memory,
                            read_rate=32000 + 60000*abs(math.sin(phase)),
                            write_rate=54000 + 85000*abs(math.cos(phase/1.3)),
                            forward_out_rate=18000 + 65000*abs(math.cos(phase/1.8)),
                            forward_in_rate=65000 + 100000*abs(math.sin(phase/2)),
                            processes=2, active_sessions=2, problem_sessions=0)
            self.history.add(sample)

    @staticmethod
    def make_icon() -> QIcon:
        pix = QPixmap(64, 64); pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(TEAL)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(3, 3, 58, 58), 17, 17)
        p.setBrush(QColor("#0C1B25"))
        p.drawRoundedRect(QRectF(16, 16, 11, 32), 5, 5)
        p.drawRoundedRect(QRectF(34, 16, 11, 32), 5, 5)
        p.end()
        return QIcon(pix)

    def create_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Mutagen Control")
        menu = QMenu(self)
        show_action = QAction("Otevřít Mutagen Control", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("Ukončit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action); menu.addSeparator(); menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()

    def create_ui(self):
        root = QWidget(); root.setObjectName("main")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("sidebar"); sidebar.setFixedWidth(251)
        sidelay = QVBoxLayout(sidebar); sidelay.setContentsMargins(18, 24, 18, 18); sidelay.setSpacing(7)
        logorow = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(self.make_icon().pixmap(39, 39))
        logorow.addWidget(logo)
        titles = QVBoxLayout(); titles.setSpacing(1)
        titles.addWidget(label("MUTAGEN", size=19, bold=True)); titles.addWidget(label("CONTROL  /  SERVER MANAGER", muted=True, size=10))
        logorow.addLayout(titles); logorow.addStretch()
        sidelay.addLayout(logorow); sidelay.addSpacing(17)
        nav_scroller = QScrollArea()
        nav_scroller.setObjectName("navscroll")
        nav_scroller.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroller.setWidgetResizable(True)
        nav_scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_content = QWidget(); nav_content.setObjectName("navcontent")
        nav_layout = QVBoxLayout(nav_content)
        nav_layout.setContentsMargins(0, 0, 2, 0); nav_layout.setSpacing(4)
        self.nav = []
        nav_tooltips = [
            "Ctrl+1 · Přehled stavu a grafů",
            "Ctrl+2 · Správa synchronizačních relací",
            "Ctrl+3 · Správa port-forwarding relací",
            "Ctrl+4 · Záznamy akcí",
            "Ctrl+5 · Daemon – spustit / zastavit / registrovat",
            "Ctrl+6 · Nastavení aplikace",
            "Ctrl+7 · Monitoring – historické grafy",
            "Ctrl+8 · Diagnostika a export",
            "Ctrl+9 · Upozornění na prostředky",
            "Ctrl+0 · Stav ALPHA / BETA endpointů",
            "Ctrl+Shift+1 · Skupiny serverů a hromadné akce",
        ]
        for title, glyph in [("Přehled", "◈"), ("Synchronizace", "⇄"), ("Přesměrování", "↗"),
                             ("Historie akcí", "≡"), ("Daemon", "◉"), ("Nastavení", "⚙"),
                             ("Monitoring", "▥"), ("Diagnostika", "⚕"), ("Upozornění", "♢"),
                             ("Obě strany", "⇄"), ("Servery", "▣")]:
            i = len(self.nav)
            sections = {0:"PRACOVNÍ PROSTOR", 1:"RELACE", 3:"NÁSTROJE A DIAGNOSTIKA", 9:"STAV OBOU ENDPOINTŮ", 10:"SKUPINY PODLE SERVERŮ"}
            if i in sections:
                nav_layout.addSpacing(12 if i else 1)
                nav_layout.addWidget(label(sections[i], muted=True, size=10))
            b = button(f"{glyph}    {title}", partial(self.set_page, i), kind="nav")
            b.setCheckable(True)
            b.setMinimumHeight(37)
            if i < len(nav_tooltips):
                b.setToolTip(nav_tooltips[i])
            nav_layout.addWidget(b)
            self.nav.append(b)
        nav_layout.addStretch()
        nav_scroller.setWidget(nav_content)
        sidelay.addWidget(nav_scroller, 1)
        statecard = QFrame(); statecard.setObjectName("inner")
        sc = QVBoxLayout(statecard); sc.setContentsMargins(15, 15, 15, 15)
        sc.addWidget(label("STAV MUTAGENU", muted=True, size=10))
        self.side_state = label("●  Zjišťuji…", bold=True)
        sc.addWidget(self.side_state)
        self.side_sub = label("Čekám na první aktualizaci", muted=True, size=11)
        self.side_sub.setWordWrap(True); sc.addWidget(self.side_sub)
        sidelay.addWidget(statecard)
        # Footer row: version on left, keyboard shortcut hint on right
        footer_row = QHBoxLayout(); footer_row.setSpacing(4)
        footer_row.addWidget(label("v8.2", muted=True, size=10))
        footer_row.addStretch()
        nav_hint = label("Ctrl+K  navigace", muted=True, size=10)
        nav_hint.setToolTip("Ctrl+K — rychlá navigace mezi stránkami")
        footer_row.addWidget(nav_hint)
        sidelay.addLayout(footer_row)
        outer.addWidget(sidebar)
        content = QWidget(); content.setObjectName("main")
        cr = QVBoxLayout(content); cr.setContentsMargins(31, 26, 31, 18); cr.setSpacing(18)
        topline = QHBoxLayout()
        titlearea = QVBoxLayout(); titlearea.setSpacing(3)
        self.page_name = label("Přehled", size=25, bold=True)
        self.page_caption = label("Správa Mutagenu na jednom místě", muted=True)
        titlearea.addWidget(self.page_name); titlearea.addWidget(self.page_caption)
        topline.addLayout(titlearea); topline.addStretch()
        self.updated = label("Neaktualizováno", muted=True, size=11)
        topline.addWidget(self.updated)
        nav_btn = button("⌕  Přejít  Ctrl+K", self.open_navigator)
        nav_btn.setToolTip("Ctrl+K — Rychlá navigace: přejít na libovolnou stránku")
        topline.addWidget(nav_btn)
        self.refresh_btn = button("↻  Obnovit stav", lambda: self.refresh(force=True))
        self.refresh_btn.setToolTip("Ctrl+R nebo F5 — Vynutit okamžité načtení stavu z Mutagenu")
        topline.addWidget(self.refresh_btn)
        cr.addLayout(topline)
        self.pages = QStackedWidget(); cr.addWidget(self.pages, 1)
        self.pages.addWidget(self.dashboard_page())
        self.pages.addWidget(self.sessions_page("sync"))
        self.pages.addWidget(self.sessions_page("forward"))
        self.pages.addWidget(self.logs_page())
        self.pages.addWidget(self.daemon_page())
        self.pages.addWidget(self.settings_page())
        self.pages.addWidget(self.monitoring_page())
        self.pages.addWidget(self.diagnostics_page())
        self.pages.addWidget(self.alerts_page())
        self.pages.addWidget(self.endpoints_page())
        self.pages.addWidget(self.servers_page())
        bottom = QHBoxLayout()
        self.footer = label("Mutagen CLI  /  lokální propojení", muted=True, size=11)
        bottom.addWidget(self.footer); bottom.addStretch()
        self.writer_status = label("Historie: čekám na měření", muted=True, size=10)
        bottom.addWidget(self.writer_status)
        bottom.addSpacing(15)
        bottom.addWidget(label("CPU/RAM = všechny místní procesy Mutagenu", muted=True, size=11))
        cr.addLayout(bottom)
        outer.addWidget(content, 1)
        self.set_page(0)

    def open_navigator(self):
        dialog = QuickNavigator(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.target is not None:
            self.set_page(dialog.target)

    def set_page(self, index):
        captions = [
            ("Přehled", "Aktuální stav synchronizací a spotřeba systémových prostředků"),
            ("Synchronizace", "Sledování, vytváření a správa synchronizačních relací"),
            ("Přesměrování", "Správa port-forwarding relací a přenesených dat"),
            ("Historie akcí", "Záznamy příkazů provedených přes tuto aplikaci"),
            ("Daemon", "Řízení běhu a registrace démona ve Windows"),
            ("Nastavení", "Umístění CLI, obnovení dat a chování aplikace"),
            ("Monitoring", "Historické grafy CPU, RAM, diskových operací a přenosů"),
            ("Diagnostika", "Problémy relací a bezpečný export podpůrných údajů"),
            ("Upozornění", "Limity prostředků a pravidla upozorňování"),
            ("Obě strany", "Stav ALPHA/BETA a přesměrování z lokálního Mutagen daemonu"),
            ("Servery", "Seskupení relací podle vzdálených hostitelů a hromadné akce"),
        ]
        self.pages.setCurrentIndex(index)
        self.page_name.setText(captions[index][0]); self.page_caption.setText(captions[index][1])
        for i, b in enumerate(self.nav): b.setChecked(i == index)
        if index in (0, 6):
            self.refresh_charts(force=True)
        if index == 6 and hasattr(self, "process_table"):
            self.fill_processes(self.sampler.last_processes if not self.demo else [])
        if index == 9 and hasattr(self, "endpoint_combo"):
            self.update_endpoint_details()
        if index == 7 and hasattr(self, "diagnostics_view"):
            self.update_diagnostics(self.snapshot)
        if index == 10 and hasattr(self, "server_selector"):
            self.update_server_details()
        if index in (1, 2) and hasattr(self, "sync_details"):
            self.refresh_detail("sync" if index == 1 else "forward")

    def dashboard_page(self):
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setObjectName("scrollbody")
        l = QVBoxLayout(body); l.setContentsMargins(0, 3, 2, 12); l.setSpacing(19)
        hero, hl = card()
        hero.setStyleSheet(f"QFrame#card {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #152F35,stop:1 #13212F); border:1px solid #28665D; border-radius:16px;}}")
        htop = QHBoxLayout()
        textblock = QVBoxLayout(); textblock.setSpacing(6)
        eyebrow = QHBoxLayout(); eyebrow.setSpacing(10)
        eyebrow.addWidget(label("MUTAGEN ENGINE  /  LIVE STATUS", size=11, bold=True))
        self.hero_badge = label("", size=10)
        self.hero_badge.setStyleSheet(f"color:{TEAL}; font-size:10px; font-weight:700; "
                                      f"background:#1A3A32; border:1px solid #2D6B5A; border-radius:5px; padding:1px 6px;")
        eyebrow.addWidget(self.hero_badge); eyebrow.addStretch()
        textblock.addLayout(eyebrow)
        self.hero_title = label("Kontroluji připojení…", size=22, bold=True)
        textblock.addWidget(self.hero_title)
        self.hero_sub = label("Zjišťuji stav démona a aktivních relací", muted=True)
        textblock.addWidget(self.hero_sub)
        htop.addLayout(textblock, 1)
        daemon_btn = button("Spravovat daemon  →", partial(self.set_page, 4))
        daemon_btn.setToolTip("Přejít na stránku Daemon pro spuštění, zastavení a registraci")
        htop.addWidget(daemon_btn)
        self.health_ring = HealthRing(hero)
        self.health_ring.setToolTip("Poměr relací bez hlášených problémů")
        htop.addWidget(self.health_ring)
        hl.addLayout(htop); l.addWidget(hero)
        metrics = QHBoxLayout(); metrics.setSpacing(14)
        self.metric_widgets = {}
        for key, title, note, color in [
            ("all", "Relace celkem", "Synchronizace + porty", TEXT),
            ("running", "Aktivní", "Připojeno / pracuje", TEAL),
            ("paused", "Pozastavené", "Ruční pozastavení", AMBER),
            ("errors", "Problémy", "Vyžadují pozornost", RED),
        ]:
            f, c = card()
            c.addWidget(label(title, muted=True, size=11))
            val = label("—", size=28, bold=True)
            val.setStyleSheet(f"color: {color}; font-size: 28px; font-weight: 800")
            c.addWidget(val); c.addWidget(label(note, muted=True, size=10))
            self.metric_widgets[key] = val
            metrics.addWidget(f, 1)
        l.addLayout(metrics)
        graphs = QHBoxLayout(); graphs.setSpacing(14)
        cpu_card, self.cpu_chart, self.cpu_value = self.graph_card("CPU", "%", BLUE)
        mem_card, self.mem_chart, self.mem_value = self.graph_card("RAM", "MB", TEAL)
        # Keep the C++ owner (QFrame) alive until Qt takes ownership via addWidget.
        # Fetching graph.parentWidget() from a discarded Python frame caused
        # libshiboken: Internal C++ object (Graph) already deleted on Windows.
        graphs.addWidget(cpu_card, 1)
        graphs.addWidget(mem_card, 1)
        l.addLayout(graphs)
        l.addWidget(button("▥  Otevřít kompletní monitoring a historii grafů →",
                           partial(self.set_page, 6)))
        recent, rr = card()
        titlebar = QHBoxLayout(); titlebar.addWidget(label("Synchronizační relace", size=16, bold=True)); titlebar.addStretch()
        titlebar.addWidget(button("Všechny synchronizace →", partial(self.set_page, 1)))
        rr.addLayout(titlebar)
        self.dashboard_table = self.make_table(["NÁZEV", "STAV", "ALPHA", "BETA"], height=240)
        self.dashboard_table.setToolTip("Dvojklik pro přechod na detail synchronizace")
        rr.addWidget(self.dashboard_table)
        self.dashboard_table.cellDoubleClicked.connect(self.dashboard_select)
        # Forward sessions summary row
        fwd_row = QHBoxLayout()
        fwd_row.addWidget(label("Přesměrování:", muted=True, size=11))
        self.dashboard_forward_summary = label("—", size=11)
        fwd_row.addWidget(self.dashboard_forward_summary)
        fwd_row.addStretch()
        fwd_row.addWidget(button("Všechna přesměrování →", partial(self.set_page, 2)))
        rr.addLayout(fwd_row)
        l.addWidget(recent)
        l.addStretch(); page.setWidget(body)
        return page

    def graph_card(self, title, suffix, color):
        f, vl = card()
        top = QHBoxLayout()
        top.addWidget(label(title + " · Mutagen procesy", muted=True, size=12))
        top.addStretch()
        value = label("—", size=20, bold=True)
        value.setStyleSheet(f"color:{color};font-size:20px;font-weight:700")
        top.addWidget(value); vl.addLayout(top)
        graph = Graph(color, f, unit="percent" if suffix == "%" else "memory")
        graph.setMinimumHeight(165)
        vl.addWidget(graph)
        footer = QHBoxLayout()
        footer.addWidget(label("Historie od spuštění · aktuální hodnota", muted=True, size=10))
        footer.addStretch()
        footer.addWidget(label("▥  Monitoring →", muted=True, size=10))
        vl.addLayout(footer)
        return f, graph, value

    def make_table(self, headers, height=370):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setMinimumHeight(height)
        table.setSortingEnabled(True)
        table.horizontalHeader().setMinimumSectionSize(85)
        table.setWordWrap(False)
        # Focus frame looks jarring with the dark theme — remove it
        table.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        return table

    def sessions_page(self, kind):
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget(); root.setObjectName("scrollbody")
        layout = QVBoxLayout(root); layout.setContentsMargins(0, 3, 6, 12); layout.setSpacing(16)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        top, tl = card()
        row = QHBoxLayout()
        row.addWidget(label("SPRÁVCE RELACÍ", muted=True, size=11)); row.addStretch()
        new_btn = button("+  Nová synchronizace" if kind == "sync" else "+  Nové přesměrování",
                         partial(self.create_session, kind), kind="primary")
        new_btn.setToolTip("Ctrl+N — Vytvořit novou relaci pomocí průvodce")
        row.addWidget(new_btn)
        tl.addLayout(row)
        summary = label("Zatím nejsou načteny žádné relace", muted=True)
        tl.addWidget(summary)
        bulk_row = QHBoxLayout()
        if kind == "sync":
            sync_now_btn = button("↻ Sync now · všechny", partial(self.bulk_action, "sync", "flush", "all"), kind="primary")
            sync_now_btn.setToolTip("Spustí synchronizační cyklus pro všechny aktivní (nepozastavené) relace")
            bulk_row.addWidget(sync_now_btn)
        pause_btn = button("⏸ Pozastavit všechny", partial(self.bulk_action, kind, "pause", "all"))
        pause_btn.setToolTip("Pozastaví všechny aktivní relace tohoto typu")
        bulk_row.addWidget(pause_btn)
        resume_btn = button("▶ Pokračovat všechny", partial(self.bulk_action, kind, "resume", "all"))
        resume_btn.setToolTip("Obnoví všechny pozastavené nebo chybové relace")
        bulk_row.addWidget(resume_btn)
        bulk_row.addStretch()
        tl.addLayout(bulk_row)
        layout.addWidget(top)
        table_frame, table_l = card()
        header = QHBoxLayout(); header.addWidget(label("Aktuální relace", size=16, bold=True)); header.addStretch()
        search = QLineEdit(); search.setPlaceholderText("Hledat podle názvu / cesty…")
        search.setMaximumWidth(300)
        search.setToolTip("Filtruje řádky tabulky podle názvu nebo cesty endpointu")
        search.textChanged.connect(partial(self.filter_table, kind))
        header.addWidget(search)
        filter_row = QHBoxLayout()
        if kind == "sync":
            self.sync_server_filter = QComboBox()
            self.sync_server_filter.addItem("Všechny servery", "__all__")
            self.sync_server_filter.setMinimumWidth(155)
            self.sync_server_filter.setToolTip("Filtrovat podle vzdáleného hostitele")
            self.sync_server_filter.currentIndexChanged.connect(lambda _=None: self.filter_table("sync"))
            filter_row.addWidget(self.sync_server_filter)
        states = QComboBox(); states.addItems(["Všechny stavy", "Aktivní", "Pracuje", "Pozastaveno", "Problém", "Odpojeno"])
        states.setMinimumWidth(140)
        states.setToolTip("Filtrovat relace podle aktuálního stavu")
        states.currentIndexChanged.connect(lambda _=None, k=kind: self.filter_table(k, None))
        filter_row.addWidget(states)
        favorites_only = QCheckBox("★ Oblíbené")
        favorites_only.setToolTip("Zobrazit pouze relace označené jako oblíbené")
        favorites_only.toggled.connect(lambda _checked, k=kind: self.filter_table(k))
        filter_row.addWidget(favorites_only)
        filter_row.addStretch()
        table_l.addLayout(header)
        table_l.addLayout(filter_row)
        if kind == "sync": self.sync_favorites_only = favorites_only
        else: self.forward_favorites_only = favorites_only
        if kind == "sync": self.sync_state_filter = states
        else: self.forward_state_filter = states
        if kind == "sync": self.sync_search = search
        else: self.forward_search = search
        fields = ["NÁZEV", "STAV", "ALPHA", "BETA", "KONFLIKTY"] if kind == "sync" else ["NÁZEV", "STAV", "ZDROJ", "CÍL", "SPOJENÍ"]
        table = self.make_table(fields, 225)
        table.itemSelectionChanged.connect(partial(self.on_select, kind))
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda point, k=kind: self.session_context_menu(k, point))
        table.setMinimumHeight(260)
        table.setMaximumHeight(350)
        table_l.addWidget(table)
        layout.addWidget(table_frame)
        detail, dl = card()
        hd = QHBoxLayout()
        detail_title = label("Vyberte relaci", size=16, bold=True)
        hd.addWidget(detail_title); hd.addStretch()
        detail_tag = label("", muted=True)
        hd.addWidget(detail_tag); dl.addLayout(hd)
        details = QLabel("Podrobnosti o relaci a ovládací prvky se zobrazí po výběru.")
        details.setTextFormat(Qt.TextFormat.PlainText)
        details.setWordWrap(True)
        details.setObjectName("muted")
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.setMinimumHeight(85)
        details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dl.addWidget(details)
        progress = QProgressBar()
        progress.setRange(0, 100); progress.setTextVisible(True)
        progress.setVisible(False)
        dl.addWidget(progress)
        utility_controls = QHBoxLayout()
        favorite_button = button("☆ Do oblíbených", partial(self.toggle_favorite, kind))
        favorite_button.setEnabled(False)
        utility_controls.addWidget(favorite_button)
        utility_controls.addWidget(button("Kopírovat ID", partial(self.copy_session_id, kind)))
        utility_controls.addWidget(button("Export JSON", partial(self.export_session_json, kind)))
        utility_controls.addStretch()
        dl.addLayout(utility_controls)
        if kind == "sync":
            self.sync_autostart_button = button("Start při přihlášení: zjišťuji…", self.toggle_sync_startup)
            self.sync_autostart_button.setToolTip("Nativní paused/resume + registrace daemonu; vypnutí synchronizaci ihned pozastaví.")
            startup_line = QHBoxLayout()
            startup_line.addWidget(self.sync_autostart_button)
            startup_line.addStretch()
            dl.addLayout(startup_line)
            note = label("Automatický start relace = daemon se spouští po přihlášení a relace není pozastavená. "
                         "Vypnutí auto-startu ji pozastaví i nyní; není potřeba další služba.", muted=True, size=10)
            note.setWordWrap(True)
            dl.addWidget(note)
        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(10)
        control_buttons = {}
        actions = ([("pause", "⏸  Pauza"), ("resume", "▶  Pokračovat"), ("flush", "↻  Sync now"),
                    ("reset", "Reset historie"), ("terminate", "Odstranit relaci")]
                   if kind == "sync" else [("pause", "⏸  Pauza"), ("resume", "▶  Pokračovat"), ("terminate", "Odstranit relaci")])
        for pos, (action, text) in enumerate(actions):
            b = button(text, partial(self.session_action, kind, action), kind="danger" if action in ("terminate", "reset") else "")
            b.setEnabled(False); controls.addWidget(b, pos // 3, pos % 3); control_buttons[action] = b
        dl.addLayout(controls)
        session_prefs = button("⚙ Nastavení relace", partial(self.open_session_preferences, kind))
        utility_controls.insertWidget(0, session_prefs)
        layout.addWidget(detail)
        layout.addStretch(1)
        if kind == "sync":
            self.sync_table, self.sync_summary = table, summary
            self.sync_details, self.sync_title, self.sync_tag = details, detail_title, detail_tag
            self.sync_controls = control_buttons
            self.sync_progress = progress
            self.sync_favorite_button = favorite_button
            self.sync_preferences_button = session_prefs
        else:
            self.forward_table, self.forward_summary = table, summary
            self.forward_details, self.forward_title, self.forward_tag = details, detail_title, detail_tag
            self.forward_controls = control_buttons
            self.forward_progress = progress
            self.forward_favorite_button = favorite_button
            self.forward_preferences_button = session_prefs
        page.setWidget(root)
        return page

    def logs_page(self):
        root = QWidget(); root.setObjectName("main")
        l = QVBoxLayout(root); l.setContentsMargins(0, 3, 0, 0); l.setSpacing(12)
        f, c = card(); row = QHBoxLayout()
        row.addWidget(label("Živé události relací a aplikace", size=16, bold=True)); row.addStretch()
        self.log_count_label = label("0 záznamů", muted=True, size=11)
        row.addWidget(self.log_count_label)
        export_logs_btn = button("Uložit .txt", self.export_logs)
        export_logs_btn.setToolTip("Uložit zobrazené záznamy do textového souboru")
        row.addWidget(export_logs_btn)
        clear_logs_btn = button("Vymazat", self.clear_logs)
        clear_logs_btn.setToolTip("Vymaže záznamy z tohoto zobrazení (nezmaže historii v databázi)")
        row.addWidget(clear_logs_btn)
        c.addLayout(row)
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setPlainText("\n".join(self.logs))
        self.log_view.setStyleSheet(f"font-family: Consolas, monospace; font-size:12px; background:#0A1421; color:{TEXT};")
        c.addWidget(self.log_view); l.addWidget(f, 1)
        logbox, contents = card()
        row = QHBoxLayout()
        row.addWidget(label("Live log – sledování souboru", size=16, bold=True)); row.addStretch()
        choose_btn = button("Vybrat log…", self.choose_tail_file, kind="primary")
        choose_btn.setToolTip("Vybrat lokální log soubor ke sledování v reálném čase (pouze pro čtení)")
        row.addWidget(choose_btn)
        stop_btn = button("Zastavit", self.stop_tail_file)
        stop_btn.setToolTip("Zastaví sledování aktuálního souboru")
        row.addWidget(stop_btn)
        export_btn = button("Export", self.export_tail_file)
        export_btn.setToolTip("Uložit aktuálně zobrazené řádky live logu")
        row.addWidget(export_btn)
        contents.addLayout(row)
        self.tail_info = label("Není vybrán log soubor.", muted=True, size=11)
        self.tail_info.setWordWrap(True); contents.addWidget(self.tail_info)
        filterline = QHBoxLayout()
        filterline.addWidget(label("Filtr:", muted=True))
        self.tail_filter = QLineEdit(); self.tail_filter.setPlaceholderText("Text, který se má v logu zobrazovat…")
        self.tail_filter.setToolTip("Zobrazí pouze řádky obsahující zadaný text (bez ohledu na velikost písmen)")
        self.tail_filter.textChanged.connect(self.render_tail)
        filterline.addWidget(self.tail_filter)
        self.follow_tail = QCheckBox("Sledovat konec")
        self.follow_tail.setChecked(True)
        self.follow_tail.setToolTip("Vypněte pro čtení starších záznamů bez automatického posouvání")
        filterline.addWidget(self.follow_tail)
        self.tail_count_label = label("0 řádků", muted=True, size=11)
        filterline.addWidget(self.tail_count_label)
        clear_tail_btn = button("Smazat zobrazení", self.clear_tail)
        clear_tail_btn.setToolTip("Vymaže zobrazené řádky (soubor zůstane beze změny)")
        filterline.addWidget(clear_tail_btn)
        contents.addLayout(filterline)
        self.tail_view = QPlainTextEdit(); self.tail_view.setReadOnly(True)
        self.tail_view.setMaximumBlockCount(1200)
        self.tail_view.setStyleSheet(f"font-family: Consolas, monospace; font-size:12px; background:#0A1421; color:{TEXT};")
        contents.addWidget(self.tail_view)
        l.addWidget(logbox, 1)
        note = label("Živé události výše vznikají ze změn stavu vráceného lokálním Mutagen daemonem. "
                     "Nejde o úplný interní debug log. Volitelně lze sledovat existující lokální "
                     "log soubor bez zásahu do běžícího daemonu. Aplikace pro logování nic na serveru nespouští.",
                     muted=True, size=11)
        note.setWordWrap(True); l.addWidget(note)
        return root

    def choose_tail_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Vybrat průběžně aktualizovaný log", "", "Textové logy (*.log *.txt);;Všechny soubory (*)")
        if not filename: return
        self.tail_file = FileTail(filename)
        self.tail_timer.start(900)
        self.tail_lines.clear()
        self.tail_info.setText("Sleduji pouze pro čtení: " + filename)
        self.poll_tail()

    def stop_tail_file(self):
        self.tail_file = None
        self.tail_timer.stop()
        self.tail_info.setText("Sledování logu zastaveno.")

    def clear_tail(self):
        self.tail_lines.clear()
        self.tail_view.clear()

    def poll_tail(self):
        if self.tail_file is None: return
        try:
            found = self.tail_file.poll()
        except OSError as exc:
            self.stop_tail_file()
            self.tail_info.setText("Nepodařilo se číst log: " + str(exc)[:200])
            return
        if not found: return
        self.tail_lines.extend(found)
        self.schedule_tail_render()

    def schedule_tail_render(self):
        """Merge bursts of debug output into one UI paint (~6 FPS at most)."""
        if not self._tail_render_pending:
            self._tail_render_pending = True
            QTimer.singleShot(160, self._render_pending_tail)

    def _render_pending_tail(self):
        self._tail_render_pending = False
        self.render_tail()

    def render_tail(self, *_):
        """Append only newly arrived matching lines; never reread Qt's full text.

        A filter change or explicit clear performs one full rebuild. Following
        the end is optional, so selecting an older error is not interrupted.
        """
        if not hasattr(self, 'tail_view'):
            return
        term = self.tail_filter.text().casefold().strip()
        scrollbar = self.tail_view.verticalScrollBar()
        old_position = scrollbar.value()
        auto_follow = self.follow_tail.isChecked()
        reset = (self._tail_render_epoch != self.tail_lines.epoch or
                 self._tail_render_filter != term)
        if reset:
            output = '\n'.join(line for line in self.tail_lines if not term or term in line.casefold())
            self.tail_view.setPlainText(output)
        else:
            addition = [line for line in self.tail_lines.since(self._tail_render_count)
                        if not term or term in line.casefold()]
            if addition:
                self.tail_view.appendPlainText('\n'.join(addition))
        self._tail_render_epoch = self.tail_lines.epoch
        self._tail_render_filter = term
        self._tail_render_count = self.tail_lines.total
        scrollbar.setValue(scrollbar.maximum() if auto_follow else old_position)
        if hasattr(self, "tail_count_label"):
            n = self.tail_view.document().blockCount()
            self.tail_count_label.setText(f"{n} {'řádek' if n == 1 else 'řádky' if 2 <= n <= 4 else 'řádků'}")

    def export_tail_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportovat aktuálně zobrazený live log", "mutagen-live-log.txt", "Text (*.txt)")
        if not path: return
        try:
            Path(path).write_text(self.tail_view.toPlainText() + "\n", encoding="utf-8")
        except OSError as exc:
            self.report_error(str(exc))

    def daemon_page(self):
        root = QWidget(); root.setObjectName("main")
        l = QVBoxLayout(root); l.setContentsMargins(0, 3, 0, 0); l.setSpacing(18)
        stat, sl = card()
        sl.addWidget(label("SLUŽBA MUTAGEN", muted=True, size=11))
        self.daemon_title = label("Zjišťuji stav démona…", size=22, bold=True)
        sl.addWidget(self.daemon_title)
        self.daemon_desc = label("Stav se ověřuje přes příkazové rozhraní bez automatického spouštění.", muted=True)
        self.daemon_desc.setWordWrap(True); sl.addWidget(self.daemon_desc)
        l.addWidget(stat)
        actions, al = card()
        al.addWidget(label("Životní cyklus démona", size=16, bold=True))
        r = QHBoxLayout()
        self.start_button = button("▶  Spustit daemon", partial(self.daemon_action, "start"), kind="primary")
        self.start_button.setToolTip("Spustí Mutagen daemon na pozadí příkazem 'mutagen daemon start'")
        self.stop_button = button("■  Zastavit daemon", partial(self.daemon_action, "stop"), kind="danger")
        self.stop_button.setToolTip("Zastaví daemon a tím přeruší všechny aktivní synchronizace a přesměrování")
        r.addWidget(self.start_button); r.addWidget(self.stop_button); r.addStretch()
        al.addLayout(r)
        warning_lbl = label("⚠  Zastavení démona přeruší všechny jeho synchronizace a přesměrování, dokud nebude znovu spuštěn.", muted=True)
        warning_lbl.setWordWrap(True)
        al.addWidget(warning_lbl)
        l.addWidget(actions)
        registry, reg = card()
        reg.addWidget(label("Automatické spuštění při přihlášení do Windows", size=16, bold=True))
        reg.addWidget(label("Nativní registrace daemonu přes Mutagen CLI (HKCU Run). "
                            "Po přihlášení pokračují jen nepozastavené relace; pozastavené zůstávají pozastavené.", muted=True))
        row = QHBoxLayout()
        reg_btn = button("Registrovat", partial(self.daemon_action, "register"), kind="primary")
        reg_btn.setToolTip("Zaregistruje Mutagen daemon do HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run")
        row.addWidget(reg_btn)
        unreg_btn = button("Odregistrovat", partial(self.daemon_action, "unregister"), kind="danger")
        unreg_btn.setToolTip("Odstraní registraci daemonu — daemon se po přihlášení nespustí automaticky")
        row.addWidget(unreg_btn)
        row.addStretch(); reg.addLayout(row)
        self.register_message = label("Registrace: zjišťuji stav…", muted=True)
        self.register_message.setWordWrap(True)
        reg.addWidget(self.register_message)
        # card() returns (QFrame, QVBoxLayout). Only the frame is a QWidget.
        # Passing reg (the QVBoxLayout) to addWidget() crashes on real PySide6.
        l.addWidget(registry)
        l.addStretch(); return root

    def alerts_page(self):
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setObjectName("scrollbody")
        outer = QVBoxLayout(body); outer.setContentsMargins(0, 3, 3, 15); outer.setSpacing(18)
        status, sl = card()
        sl.addWidget(label("Hlídání prostředků Mutagenu", size=17, bold=True))
        sl.addWidget(label("Upozornění se aktivuje až po souvislém překročení prahu. "
                           "Další upozornění se odešle až po návratu pod limit a novém překročení.", muted=True))
        form = QFormLayout(); form.setVerticalSpacing(15)
        self.cpu_alert_on = QCheckBox("Hlásit dlouhodobě vysoké CPU")
        self.cpu_alert_on.setChecked(bool(self.conf.get("cpu_alert_on", False)))
        form.addRow("CPU", self.cpu_alert_on)
        self.cpu_alert_limit = QSpinBox(); self.cpu_alert_limit.setRange(1, 1600)
        self.cpu_alert_limit.setSuffix(" %"); self.cpu_alert_limit.setValue(int(self.conf.get("cpu_alert_limit", 90)))
        form.addRow("Limit CPU (součet jader)", self.cpu_alert_limit)
        self.ram_alert_on = QCheckBox("Hlásit dlouhodobě vysokou RAM")
        self.ram_alert_on.setChecked(bool(self.conf.get("ram_alert_on", False)))
        form.addRow("RAM", self.ram_alert_on)
        self.ram_alert_limit = QSpinBox(); self.ram_alert_limit.setRange(64, 131072)
        self.ram_alert_limit.setSuffix(" MB"); self.ram_alert_limit.setValue(int(self.conf.get("ram_alert_limit", 1024)))
        form.addRow("Limit RAM", self.ram_alert_limit)
        self.alert_hold = QSpinBox(); self.alert_hold.setRange(5, 600)
        self.alert_hold.setSuffix(" s"); self.alert_hold.setValue(int(self.conf.get("alert_hold", 20)))
        form.addRow("Doba překročení", self.alert_hold)
        sl.addLayout(form)
        sl.addWidget(button("Uložit pravidla upozornění", self.save_alert_rules, kind="primary"))
        outer.addWidget(status)
        detail, dl = card()
        dl.addWidget(label("Aktuální hodnoty", size=16, bold=True))
        self.alert_runtime_label = label("Čekám na měření…", muted=True)
        dl.addWidget(self.alert_runtime_label)
        dl.addWidget(label("Upozornění se zapisují do Historie akcí a volitelně se zobrazují "
                           "v oznamovací oblasti Windows. CPU/RAM se vztahují ke všem místním procesům Mutagenu.", muted=True))
        outer.addWidget(detail)
        outer.addStretch()
        page.setWidget(body)
        return page

    def save_alert_rules(self):
        self.conf.update(cpu_alert_on=self.cpu_alert_on.isChecked(),
                         cpu_alert_limit=self.cpu_alert_limit.value(),
                         ram_alert_on=self.ram_alert_on.isChecked(),
                         ram_alert_limit=self.ram_alert_limit.value(),
                         alert_hold=self.alert_hold.value())
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc)); return
        self.alert_engine = AlertEngine()  # Re-arm with new thresholds
        self.add_log("Pravidla upozornění uložena")

    def settings_page(self):
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget(); root.setObjectName("scrollbody")
        layout = QVBoxLayout(root); layout.setContentsMargins(0, 3, 8, 14); layout.setSpacing(17)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        pathcard, pl = card()
        pl.addWidget(label("Instalace Mutagenu", size=16, bold=True))
        pl.addWidget(label("Aplikace komunikuje s mutagen.exe. Pokud není v systémové PATH, vyberte ho ručně.", muted=True))
        r = QHBoxLayout()
        self.binary_edit = QLineEdit(self.conf.get("binary", ""))
        self.binary_edit.setPlaceholderText(r"C:\Program Files\Mutagen\mutagen.exe   (nebo prázdné = PATH)")
        r.addWidget(self.binary_edit, 1)
        r.addWidget(button("Vybrat…", self.browse_binary)); pl.addLayout(r)
        self.version_label = label("Verze: nezjištěna", muted=True)
        pl.addWidget(self.version_label)
        layout.addWidget(pathcard)
        prefs, pr = card()
        pr.addWidget(label("Chování aplikace", size=16, bold=True))
        form = QFormLayout(); form.setVerticalSpacing(18)
        self.interval_input = QSpinBox(); self.interval_input.setRange(2, 30)
        self.interval_input.setSuffix(" s")
        self.interval_input.setMinimumWidth(160)
        self.interval_input.setValue(max(2, min(30, int(self.conf.get("interval", 4)))))
        form.addRow("Obnova relací", self.interval_input)
        self.metric_interval_input = QComboBox()
        for seconds in (1, 2, 3, 5, 10):
            self.metric_interval_input.addItem(f"{seconds} s", seconds)
        saved = int(self.conf.get("metric_interval", 2))
        self.metric_interval_input.setCurrentIndex(max(0, self.metric_interval_input.findData(saved)))
        self.metric_interval_input.setMinimumWidth(160)
        form.addRow("Vzorkování CPU/RAM", self.metric_interval_input)
        self.adaptive_input = QCheckBox("Automaticky zvýšit frekvenci čtení při aktivitě a zvolnit po zklidnění")
        self.adaptive_input.setChecked(bool(self.conf.get("adaptive_poll", True)))
        form.addRow("Adaptivní čtení stavů", self.adaptive_input)
        self.fast_interval_input = QSpinBox(); self.fast_interval_input.setRange(2, 15)
        self.fast_interval_input.setValue(int(self.conf.get("adaptive_fast", 2)))
        self.fast_interval_input.setSuffix(" s"); self.fast_interval_input.setMinimumWidth(160)
        form.addRow("Při aktivitě", self.fast_interval_input)
        self.idle_interval_input = QSpinBox(); self.idle_interval_input.setRange(5, 180)
        self.idle_interval_input.setValue(int(self.conf.get("adaptive_idle", 30)))
        self.idle_interval_input.setSuffix(" s"); self.idle_interval_input.setMinimumWidth(160)
        form.addRow("Po zklidnění", self.idle_interval_input)
        self.quiet_after_input = QSpinBox(); self.quiet_after_input.setRange(15, 900)
        self.quiet_after_input.setValue(int(self.conf.get("adaptive_quiet", 90)))
        self.quiet_after_input.setSuffix(" s"); self.quiet_after_input.setMinimumWidth(160)
        form.addRow("Doba klidu", self.quiet_after_input)
        self.new_sync_profile_input = QComboBox()
        for code, (title, _) in PROFILES.items():
            self.new_sync_profile_input.addItem(title, code)
        self.new_sync_profile_input.setCurrentIndex(max(0, self.new_sync_profile_input.findData(
            self.conf.get("new_sync_profile", "default"))))
        self.new_sync_profile_input.setMinimumWidth(290)
        form.addRow("Nové synchronizace", self.new_sync_profile_input)
        self.eco_tray_input = QCheckBox("V oznamovací oblasti snížit frekvenci měření a obnovy relací")
        self.eco_tray_input.setChecked(self.conf.get("eco_tray", True))
        form.addRow("Úsporný režim", self.eco_tray_input)
        self.tray_input = QCheckBox("Zavřením okna minimalizovat do oznamovací oblasti")
        self.tray_input.setChecked(self.conf.get("tray", True))
        form.addRow("Oznamovací oblast", self.tray_input)
        self.alert_input = QCheckBox("Upozornit v oznamovací oblasti při nově zjištěném problému")
        self.alert_input.setChecked(self.conf.get("alerts", True))
        form.addRow("Upozornění", self.alert_input)
        pr.addLayout(form)
        explanation = label("Adaptivní režim mění pouze frekvenci čtení stavů GUI. Mutagen sleduje změny souborů sám. "
                            "Profily pro nové relace nastavují nativní watch/polling při vytvoření. "
                            "Již vytvořeným relacím zde neměníme interní konfiguraci ani neomezujeme rychlost přenosu.", muted=True, size=11)
        explanation.setWordWrap(True); pr.addWidget(explanation)
        pr.addWidget(button("Uložit nastavení", self.save_settings, kind="primary"))
        layout.addWidget(prefs)
        note, nl = card()
        nl.addWidget(label("Informace a omezení", size=16, bold=True))
        text = label("• CPU, RAM a procesové I/O jsou souhrnem místních procesů Mutagenu, nikoliv jednotlivých relací.\n"
                     "• Mutagen CLI neposkytuje univerzální limit přenosové rychlosti pro existující sync; profily watch/polling platí pro nové relace.\n"
                     "• Počty souborů a konflikty pocházejí z exportovaného stavu relací.\n"
                     "• Relace mohou vytvářet SSH výzvy; doporučeny jsou bezobslužné SSH klíče.\n"
                     "• Tato aplikace není oficiálním produktem Mutagen a nemění jeho interní databázi.", muted=True)
        text.setWordWrap(True); nl.addWidget(text)
        layout.addWidget(note)
        layout.addStretch(); page.setWidget(root); return page

    def browse_binary(self):
        path, _ = QFileDialog.getOpenFileName(self, "Vyberte mutagen.exe", str(Path.home()), "Executable (*.exe);;All files (*)")
        if path: self.binary_edit.setText(path)

    def save_settings(self):
        binary = self.binary_edit.text().strip()
        client = MutagenClient(binary)
        if binary and not client.binary:
            QMessageBox.warning(self, "Neplatný soubor", "Vybraný soubor mutagen.exe neexistuje nebo není dostupný.")
            return
        self.conf.update(binary=binary, interval=self.interval_input.value(),
                         metric_interval=self.metric_interval_input.currentData(),
                         eco_tray=self.eco_tray_input.isChecked(),
                         tray=self.tray_input.isChecked(), alerts=self.alert_input.isChecked(),
                         adaptive_poll=self.adaptive_input.isChecked(),
                         adaptive_fast=self.fast_interval_input.value(),
                         adaptive_idle=self.idle_interval_input.value(),
                         adaptive_quiet=self.quiet_after_input.value(),
                         new_sync_profile=self.new_sync_profile_input.currentData())
        self.adaptive_policy.fast = self.fast_interval_input.value()
        self.adaptive_policy.idle = self.idle_interval_input.value()
        self.adaptive_policy.quiet_after = self.quiet_after_input.value()
        try:
            write_settings(self.conf)
        except OSError as exc:
            QMessageBox.critical(self, "Uložení selhalo", str(exc)); return
        self.client = client
        self.poll_backoff.base = max(2, self.interval_input.value())
        self.poll_backoff.observe(True)
        self.update_polling_mode()
        self._version_cache = ("", 0.0, "")
        self._table_signatures.clear()
        self.add_log("Nastavení uloženo")
        self.refresh(force=True)

    def add_log(self, message):
        safe_message = str(message).replace("\r", "").strip()
        self.logs.append(f"[{datetime.now():%d.%m. %H:%M:%S}] {safe_message}")
        severity = "warning" if "CHYBA" in safe_message or "POZOR" in safe_message else "info"
        if self.recorder is not None:
            self.recorder.add_event(safe_message, severity)
        else:
            try: self.history.add_event(safe_message, severity)
            except sqlite3.Error: pass
        if hasattr(self, "log_view"):
            self.log_view.appendPlainText(self.logs[-1])
            bar = self.log_view.verticalScrollBar(); bar.setValue(bar.maximum())
        if hasattr(self, "log_count_label"):
            n = len(self.logs)
            self.log_count_label.setText(f"{n} {'záznam' if n == 1 else 'záznamy' if 2 <= n <= 4 else 'záznamů'}")

    def clear_logs(self):
        self.logs.clear(); self.log_view.clear()
        if self.recorder is not None:
            self.recorder.clear_events()
        else:
            try: self.history.clear_events()
            except sqlite3.Error: pass
        self.add_log("Historie GUI vymazána")

    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(self, "Uložit historii", "mutagen-control-log.txt", "Text (*.txt)")
        if not path: return
        try:
            Path(path).write_text("\n".join(self.logs) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Chyba zápisu", str(exc))

    def submit(self, func, on_result, on_error=None, on_done=None):
        worker = Worker(func)
        self.workers.add(worker)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error or self.report_error)
        def finished():
            self.workers.discard(worker)
            if on_done: on_done()
        worker.signals.finished.connect(finished)
        self.pool.start(worker)

    def refresh(self, *, force=False):
        if not self.demo and not self.poll_backoff.can_retry(force):
            return
        if self.demo:
            self.apply_snapshot(self.snapshot)
            return
        if self.pending_poll or self.pending_action: return
        self.pending_poll = True
        self._poll_started_at = time.monotonic()
        binary = self.client.binary
        client = MutagenClient(binary)
        cached_version, cache_at, cache_binary = self._version_cache
        version_valid = cache_binary == binary and time.monotonic() - cache_at < 600
        def work():
            snap = Snapshot(binary=client.binary)
            snap.registration, snap.registration_command = read_registration(client.binary)
            if not client.binary:
                snap.error = "Není nastaven mutagen.exe. Otevřete Nastavení."
                return snap
            try:
                snap.sync = client.list_sessions("sync")
                snap.daemon = True
            except MutagenError as exc:
                snap.error = str(exc)
                return snap
            try:
                snap.forward = client.list_sessions("forward")
            except MutagenError as exc:
                snap.error = "Přesměrování: " + str(exc)
            if version_valid:
                snap.version = cached_version
            else:
                try:
                    snap.version = client.get_version().splitlines()[0]
                except MutagenError:
                    snap.version = cached_version if cache_binary == binary else ""
            return snap
        self.submit(work, self.apply_snapshot, on_done=lambda: setattr(self, "pending_poll", False))

    def refresh_resources(self):
        if self.demo:
            self.apply_resource_metrics({"cpu": 4.8, "memory": 126_877_696, "processes": 2,
                                         "read_rate": 80_000, "write_rate": 160_000,
                                         "gui_cpu": 0.4, "gui_memory": 124_000_000})
            return
        if self._resource_pending:
            return
        self._resource_pending = True
        self.submit(self.sampler.sample_detailed, self.apply_resource_metrics,
                    on_error=lambda message: self.footer.setToolTip("Měření procesů: " + message),
                    on_done=lambda: setattr(self, "_resource_pending", False))

    def apply_resource_metrics(self, data):
        # Runs in the GUI thread; psutil enumeration itself happens in QThreadPool.
        self.last_metrics = data
        cpu, ram, count = data["cpu"], data["memory"], data["processes"]
        if hasattr(self, "alert_runtime_label"):
            self.alert_runtime_label.setText(f"CPU: {cpu:.1f} %  ·  RAM: {human_bytes(ram)}  ·  Procesy: {count}")
        if not self.demo:
            for alert in self.alert_engine.evaluate(
                cpu, ram, enabled_cpu=bool(self.conf.get("cpu_alert_on", False)),
                enabled_ram=bool(self.conf.get("ram_alert_on", False)),
                cpu_limit=float(self.conf.get("cpu_alert_limit", 90)),
                ram_limit_mb=float(self.conf.get("ram_alert_limit", 1024)),
                hold_seconds=float(self.conf.get("alert_hold", 20))):
                self.add_log("POZOR: " + alert.message)
                if self.conf.get("alerts", True) and self.tray.isVisible():
                    self.tray.showMessage("Mutagen Control – limit", alert.message,
                                          QSystemTrayIcon.MessageIcon.Warning, 7000)
        if self.recorder is not None:
            if self.recorder.last_error:
                self.writer_status.setText('Historie: chyba zápisu')
                self.writer_status.setToolTip(self.recorder.last_error)
            elif self.recorder.dropped:
                self.writer_status.setText(f'Historie: vynecháno {self.recorder.dropped} vzorků')
            else:
                self.writer_status.setText('Historie: průběžně ukládána')
        else:
            self.writer_status.setText('Historie: demonstrační režim')
        if hasattr(self, "gui_usage_label"):
            self.gui_usage_label.setText(
                f"Zatížení aplikace: CPU {data.get('gui_cpu', 0):.1f} %  ·  "
                f"RAM {human_bytes(data.get('gui_memory', 0))}  ·  "
                "měřeno za proces GUI, nikoliv za Mutagen")
        self.snapshot.cpu, self.snapshot.memory, self.snapshot.processes = cpu, ram, count
        # State changes only on CLI polls, not on each CPU sample.
        active, problems = self.session_counts
        sample = Sample(ts=time.time(), cpu=cpu, memory=ram,
                        read_rate=data["read_rate"], write_rate=data["write_rate"],
                        forward_out_rate=self.traffic_rates[0], forward_in_rate=self.traffic_rates[1],
                        processes=count, active_sessions=active, problem_sessions=problems)
        if self.recorder is not None:
            if not self.recorder.add(sample):
                self.footer.setToolTip('Zapisovač historie už není dostupný')
            elif self.recorder.last_error:
                self.footer.setToolTip('Historie: ' + self.recorder.last_error)
        else:
            try: self.history.add(sample)
            except sqlite3.Error as exc: self.footer.setToolTip(str(exc))
        self.cpu_value.setText(f"{cpu:.1f} %")
        self.mem_value.setText(human_bytes(ram))
        if hasattr(self, "monitor_labels"):
            self.monitor_labels["cpu"].setText(f"{cpu:.1f} %")
            self.monitor_labels["memory"].setText(human_bytes(ram))
            self.monitor_labels["disk"].setText(f"↓ {human_bytes(data['read_rate'])}/s · ↑ {human_bytes(data['write_rate'])}/s")
            self.monitor_labels["traffic"].setText(
                f"ven {human_bytes(self.traffic_rates[0])}/s · dovnitř {human_bytes(self.traffic_rates[1])}/s")
            self.monitor_labels["sessions"].setText(f"{active} aktivních · {problems} problémů")
        if hasattr(self, "process_table") and self.pages.currentIndex() == 6:
            detail = ([{"pid": 1840, "name": "mutagen.exe", "cpu": 3.7, "memory": 100_000_000,
                        "read_rate": 50_000, "write_rate": 100_000},
                       {"pid": 2480, "name": "mutagen-agent.exe", "cpu": 1.1, "memory": 26_877_696,
                        "read_rate": 30_000, "write_rate": 60_000}] if self.demo
                      else self.sampler.last_processes)
            self.fill_processes(detail)
        self.refresh_charts()

    def fill_processes(self, processes):
        table = self.process_table
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(processes))
            for idx, proc in enumerate(processes):
                cells = [str(proc["pid"]), proc["name"], f"{proc['cpu']:.1f} %",
                         human_bytes(proc["memory"]), human_bytes(proc["read_rate"]) + "/s",
                         human_bytes(proc["write_rate"]) + "/s"]
                for col, cell in enumerate(cells):
                    item = table.item(idx, col)
                    if item is None:
                        item = QTableWidgetItem(str(cell))
                        table.setItem(idx, col, item)
                        if col in (0, 2, 3, 4, 5):
                            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    elif item.text() != str(cell):
                        item.setText(str(cell))
                    if col == 0 and item.data(Qt.ItemDataRole.UserRole) != proc["pid"]:
                        item.setData(Qt.ItemDataRole.UserRole, proc["pid"])
            table.setSortingEnabled(True)
        finally:
            table.setUpdatesEnabled(True)

    def refresh_charts(self, *args, force=False):
        if self.chart_frozen and not force: return
        page_index = self.pages.currentIndex()
        if page_index not in (0, 6):
            return  # No SQLite reads or paints for invisible chart pages.
        if not self.isVisible() and not force:
            return
        gate = self._chart_dashboard_gate if page_index == 0 else self._chart_monitor_gate
        if not gate.ready(force):
            return
        try:
            if page_index == 0:
                recent = self.history.query(hours=5/60, max_points=320)
                self.cpu_chart.set_data((r["ts"], r["cpu"], None) for r in recent)
                self.mem_chart.set_data((r["ts"], r["memory"], None) for r in recent)
                return
            if not hasattr(self, "monitor_graphs"):
                return
            hours = float(self.monitor_range.currentData())
            if self.demo or self.history.path == ':memory:':
                self.apply_monitor_chart_data(self.history.query(hours=hours), hours)
            elif not self._chart_query_pending:
                self._chart_query_pending = True
                self._chart_query_reschedule = False
                path = self.history.path
                def finished_query():
                    self._chart_query_pending = False
                    if self._chart_query_reschedule and self.pages.currentIndex() == 6:
                        self._chart_monitor_gate.reset()
                        self.refresh_charts(force=True)
                self.submit(
                    lambda: query_metrics_from_file(path, hours=hours),
                    lambda rows: self.apply_monitor_chart_data(rows, hours),
                    lambda error: self.stats_label.setToolTip('Historie grafu: ' + str(error)[:150]),
                    on_done=finished_query,
                )
            else:
                self._chart_query_reschedule = True
            # Raw P95 / max over a 48h window can require 80k+ records.
            # Read and sort it in a worker using a separate read-only SQLite
            # connection, so zooming the GUI never blocks on statistics.
            if self._stats_cache_range == hours and time.monotonic() - self._stats_cache_at < 20:
                return
            if self._stats_pending:
                return
            if self.demo or self.history.path == ':memory:':
                self.apply_statistics(self.history.statistics(hours=hours), hours)
            else:
                self._stats_pending = True
                self.stats_label.setText("Načítám statistiky vybraného období…")
                path = self.history.path
                self.submit(
                    lambda: statistics_from_file(path, hours=hours),
                    lambda data: self.apply_statistics(data, hours),
                    lambda error: self.stats_label.setText("Statistiky nelze načíst: " + str(error)[:140]),
                    on_done=lambda: setattr(self, "_stats_pending", False),
                )
        except sqlite3.Error:
            pass


    def apply_monitor_chart_data(self, rows: list[dict], hours: float):
        if self.pages.currentIndex() != 6 or float(self.monitor_range.currentData()) != hours:
            return  # Ignore asynchronous results for a previously selected range.
        mapping = {
            "cpu": ("cpu", None), "memory": ("memory", None),
            "disk": ("read_rate", "write_rate"),
            "traffic": ("forward_out_rate", "forward_in_rate"),
            "sessions": ("active_sessions", "problem_sessions"),
        }
        for name, (left, right) in mapping.items():
            self.monitor_graphs[name].set_data(
                (row["ts"], row[left], row[right] if right else None) for row in rows)


    def apply_statistics(self, stats: dict, hours: float):
        if self.pages.currentIndex() != 6 or float(self.monitor_range.currentData()) != hours:
            return  # Ignore an outdated result from another selected interval.
        self._stats_cache_at = time.monotonic()
        self._stats_cache_range = hours
        def fmt(field, unit):
            values = stats["fields"][field]
            return (f"{unit}: aktuálně {field_format(field, values['latest'])}  ·  "
                    f"průměr {field_format(field, values['avg'])}  ·  "
                    f"P95 {field_format(field, values['p95'])}  ·  "
                    f"maximum {field_format(field, values['max'])}")
        self.stats_label.setText(
            f"Naměřeno {stats['samples']} vzorků; chybějící období nejsou dopočítávána.\n"
            + fmt("cpu", "CPU") + "\n" + fmt("memory", "RAM") + "\n"
            + fmt("read_rate", "Disk čtení") + "\n" + fmt("write_rate", "Disk zápis") + "\n"
            + fmt("forward_out_rate", "Forward ven") + "\n"
            + fmt("forward_in_rate", "Forward dovnitř"))

    def apply_snapshot(self, snap):
        # Preserve separately sampled resource measurements.
        if not self.demo:
            snap.cpu, snap.memory, snap.processes = self.snapshot.cpu, self.snapshot.memory, self.snapshot.processes
        self.snapshot = snap
        if snap.daemon:
            self.adaptive_policy.observe(snap)
        self.update_polling_mode()
        if snap.version and snap.binary:
            current_version, cached_at, cached_binary = self._version_cache
            if (snap.version != current_version or snap.binary != cached_binary or
                    time.monotonic() - cached_at >= 600):
                self._version_cache = (snap.version, time.monotonic(), snap.binary)
        if not self.demo:
            self.traffic_rates = self.traffic_meter.update(snap.forward)
            self.check_alerts(snap)
        if not self.demo:
            self.poll_backoff.observe(bool(snap.daemon))
        duration_ms = (time.monotonic() - self._poll_started_at) * 1000 if self._poll_started_at else 0
        self.updated.setText("DEMO DATA" if self.demo else
            (f"Obnoveno {datetime.now():%H:%M:%S}  ·  CLI {duration_ms:.0f} ms" if snap.daemon
             else f"Daemon offline · další pokus za {self.poll_backoff.remaining():.0f} s"))
        self.version_label.setText(snap.version or "Verze: není dostupná")
        regtexts = {
            "registered": "Automatické spuštění: registrováno pro tuto instalaci",
            "unregistered": "Automatické spuštění: neregistrováno",
            "other": "Automatické spuštění: záznam ukazuje na jinou instalaci / příkaz",
            "unknown": "Automatické spuštění: stav nelze zjistit",
            "unsupported": "Automatické spuštění: zjištění dostupné jen ve Windows",
        }
        self.register_message.setText(regtexts.get(snap.registration, "Registrace: nezjištěno"))
        self.register_message.setToolTip(snap.registration_command or "Záznam v HKCU\\...\\Run\\Mutagen")
        available = bool(snap.binary)
        if not available:
            self.side_state.setText("●  CLI nenalezeno")
            self.side_state.setStyleSheet(f"color:{RED}")
            self.side_sub.setText("Vyberte mutagen.exe v Nastavení")
        elif snap.daemon:
            self.side_state.setText("●  Daemon online")
            self.side_state.setStyleSheet(f"color:{TEAL}")
            self.side_sub.setText(f"{len(snap.sync)} synchronizací · {len(snap.forward)} přesměrování")
        else:
            self.side_state.setText("●  Daemon offline")
            self.side_state.setStyleSheet(f"color:{AMBER}")
            self.side_sub.setText((snap.error or "Zatím není spuštěn")[:120])
        self.hero_title.setText("Daemon běží" if snap.daemon else "Daemon není dostupný")
        self.hero_sub.setText("Synchronizace běží na pozadí. Systém sleduje jejich stav." if snap.daemon
                              else "V části Daemon můžete službu spustit nebo otevřít Nastavení.")
        # Version badge in hero
        if hasattr(self, "hero_badge"):
            if snap.version:
                self.hero_badge.setText(snap.version)
                self.hero_badge.setVisible(True)
            else:
                self.hero_badge.setVisible(False)
        self.daemon_title.setText("●  Spuštěný" if snap.daemon else "●  Nedostupný / zastavený")
        self.daemon_title.setStyleSheet(f"color:{TEAL if snap.daemon else AMBER};font-size:22px;font-weight:750")
        self.daemon_desc.setText(("Daemon odpovídá; " + snap.error if snap.error else "Daemon odpovídá na dotazy.") if snap.daemon
                                 else (snap.error or "Daemon není spuštěný."))
        for b in (self.start_button, self.stop_button): b.setEnabled(not self.demo and available and not self.pending_action)
        all_sessions = [("sync", x) for x in snap.sync] + [("forward", x) for x in snap.forward]
        kinds = [classify(x, k)[0] for k, x in all_sessions]
        self.metric_widgets["all"].setText(str(len(all_sessions)))
        self.metric_widgets["running"].setText(str(sum(s in ("active", "busy") for s in kinds)))
        self.metric_widgets["paused"].setText(str(kinds.count("paused")))
        self.metric_widgets["errors"].setText(str(kinds.count("error")))
        self.health_ring.set_health(len(kinds), kinds.count('error'))
        self.session_counts = (sum(s in ("active", "busy") for s in kinds), kinds.count("error"))
        self.sync_summary.setText(f"{len(snap.sync)} synchronizací • {sum(bool(x.get('paused')) for x in snap.sync)} pozastavených")
        self.forward_summary.setText(f"{len(snap.forward)} přesměrování • data a aktivní spojení v detailech")
        # Dashboard forward summary line
        if hasattr(self, "dashboard_forward_summary"):
            fwd_active = sum(1 for s in snap.forward if classify(s, "forward")[0] in ("active", "busy"))
            fwd_total = len(snap.forward)
            if fwd_total:
                self.dashboard_forward_summary.setText(
                    f"{fwd_total} celkem · {fwd_active} aktivních · "
                    f"{sum(1 for s in snap.forward if s.get('openConnections', 0) > 0)} s otevřeným spojením"
                )
            else:
                self.dashboard_forward_summary.setText("Žádná přesměrování")
        # Rebuilding and re-sorting entire QTableWidgets on every 4 s poll
        # causes avoidable flicker and allocates dozens of QTableWidgetItems.
        for kind, sessions, table in (("sync", snap.sync, self.sync_table),
                                      ("forward", snap.forward, self.forward_table),
                                      ("dashboard", snap.sync[:5], self.dashboard_table)):
            actual_kind = "sync" if kind == "dashboard" else kind
            signature = tuple((s.get("identifier"), s.get("name"), s.get("paused"),
                               s.get("status"), s.get("lastError"),
                               conflict_count(s) if actual_kind == "sync" else s.get("openConnections"),
                               problem_count(s) if actual_kind == "sync" else 0,
                               endpoint_text(s.get("alpha" if actual_kind == "sync" else "source"), actual_kind),
                               endpoint_text(s.get("beta" if actual_kind == "sync" else "destination"), actual_kind),
                               s.get("identifier") in self.favorites[actual_kind]) for s in sessions)
            if signature != self._table_signatures.get(kind):
                self.fill_table(table, sessions, actual_kind, dashboard=kind == "dashboard")
                self._table_signatures[kind] = signature
                if kind != "dashboard":
                    self.filter_table(kind)
        page = self.pages.currentIndex()
        if page in (1, 2):
            self.refresh_detail("sync" if page == 1 else "forward")
        if page == 7:
            self.update_diagnostics(snap)
        self.update_endpoint_sessions(snap)
        self.update_server_groups()
        self.footer.setText("DEMO • Vypnuty všechny akce" if self.demo else
                            ("Připojeno k " + snap.binary if available else "Vyberte instalaci Mutagenu"))

    def fill_table(self, table, sessions, kind, dashboard=False):
        """Reuse existing cells when possible instead of recreating the table.

        Polls may change only a status or byte counter. Replacing every item
        reallocates objects, causes flicker, and loses scroll position.
        """
        selection = ''
        current_row = table.currentRow()
        if current_row >= 0 and table.item(current_row, 0):
            selection = table.item(current_row, 0).data(Qt.ItemDataRole.UserRole) or ''
        old_scroll = table.verticalScrollBar().value()
        table.blockSignals(True)
        sorted_before = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(sessions))
            for row, session in enumerate(sessions):
                status, description = classify(session, kind)
                identifier = session.get('identifier', '')
                name = session.get('name') or identifier[:22] or '(bez názvu)'
                if identifier in self.favorites[kind]:
                    name = '★ ' + name
                source = endpoint_text(session.get('alpha' if kind == 'sync' else 'source'), kind)
                target = endpoint_text(session.get('beta' if kind == 'sync' else 'destination'), kind)
                extra = (conflict_count(session) + problem_count(session) if kind == 'sync'
                         else session.get('openConnections', 0))
                cells = [name, description, source, target] + ([] if dashboard else [str(extra)])
                for col, content in enumerate(cells):
                    value = str(content)
                    item = table.item(row, col)
                    created = item is None
                    if created:
                        item = QTableWidgetItem(value)
                        table.setItem(row, col, item)
                    elif item.text() != value:
                        item.setText(value)
                    if created or item.toolTip() != value:
                        item.setToolTip(value)
                    if col == 0:
                        if item.data(Qt.ItemDataRole.UserRole) != identifier:
                            item.setData(Qt.ItemDataRole.UserRole, identifier)
                        if created:
                            font = item.font(); font.setBold(True); item.setFont(font)
                        color = TEXT
                    elif col == 1:
                        color = {'active': TEAL, 'busy': BLUE, 'error': RED,
                                 'paused': AMBER}.get(status, MUTED)
                    else:
                        color = MUTED
                    if created or item.foreground().color() != QColor(color):
                        item.setForeground(QColor(color))
            table.setColumnWidth(0, 195)
            table.setColumnWidth(1, 182)
            table.setColumnWidth(2, 255)
            if not dashboard:
                table.setColumnWidth(3, 265)
                table.setColumnWidth(4, 105)
            if selection:
                for row in range(table.rowCount()):
                    item = table.item(row, 0)
                    if item and item.data(Qt.ItemDataRole.UserRole) == selection:
                        table.selectRow(row)
                        break
                else:
                    table.clearSelection()
            else:
                table.clearSelection()
            table.setSortingEnabled(sorted_before)
            table.verticalScrollBar().setValue(old_scroll)
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)

    def filter_table(self, kind, value=None):
        table = self.sync_table if kind == "sync" else self.forward_table
        search = self.sync_search if kind == "sync" else self.forward_search
        filters = self.sync_state_filter if kind == "sync" else self.forward_state_filter
        needle = (value if isinstance(value, str) else search.text()).casefold().strip()
        code = {1: "active", 2: "busy", 3: "paused", 4: "error", 5: "idle"}.get(filters.currentIndex())
        only_favorites = (self.sync_favorites_only if kind == "sync" else self.forward_favorites_only).isChecked()
        server_key = self.sync_server_filter.currentData() if kind == "sync" else "__all__"
        by_id = {s.get("identifier"): s for s in (self.snapshot.sync if kind == "sync" else self.snapshot.forward)}
        for row in range(table.rowCount()):
            haystack = " ".join(table.item(row, col).text() for col in range(table.columnCount())
                                if table.item(row, col)).casefold()
            identifier = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            current = by_id.get(identifier)
            meets_state = code is None or (current is not None and classify(current, kind)[0] == code)
            meets_server = (server_key == "__all__" or (current is not None and
                             server_key in session_servers(current, kind)))
            table.setRowHidden(row, needle not in haystack or not meets_state or not meets_server or
                               (only_favorites and identifier not in self.favorites[kind]))

    def dashboard_select(self, row, col):
        item = self.dashboard_table.item(row, 0)
        if item:
            self.current_id = item.data(Qt.ItemDataRole.UserRole) or ""
            self.current_kind = "sync"
            self.set_page(1)
            for r in range(self.sync_table.rowCount()):
                x = self.sync_table.item(r, 0)
                if x and x.data(Qt.ItemDataRole.UserRole) == self.current_id:
                    self.sync_table.selectRow(r); break

    def on_select(self, kind):
        table = self.sync_table if kind == "sync" else self.forward_table
        row = table.currentRow()
        if row < 0 or not table.item(row, 0):
            if self.current_kind == kind: self.current_id = ""
        else:
            self.current_kind = kind
            self.current_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole) or ""
        self.refresh_detail(kind)

    def selected_session(self, kind):
        table = self.sync_table if kind == "sync" else self.forward_table
        row = table.currentRow()
        if row < 0 or not table.item(row, 0): return None
        identifier = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        sessions = self.snapshot.sync if kind == "sync" else self.snapshot.forward
        return next((s for s in sessions if s.get("identifier") == identifier), None)

    def refresh_detail(self, kind):
        sess = self.selected_session(kind)
        details = self.sync_details if kind == "sync" else self.forward_details
        title = self.sync_title if kind == "sync" else self.forward_title
        tag = self.sync_tag if kind == "sync" else self.forward_tag
        controls = self.sync_controls if kind == "sync" else self.forward_controls
        progress_bar = self.sync_progress if kind == "sync" else self.forward_progress
        progress_bar.hide()
        fav_button = self.sync_favorite_button if kind == "sync" else self.forward_favorite_button
        fav_button.setEnabled(bool(sess))
        fav_button.setText("★ Odebrat z oblíbených" if sess and sess.get("identifier") in self.favorites[kind]
                           else "☆ Do oblíbených")
        for b in controls.values(): b.setEnabled(bool(sess) and not self.demo and not self.pending_action)
        if kind == "sync":
            auto = self.sync_autostart_button
            auto.setEnabled(bool(sess) and not self.demo and not self.pending_action)
            if not sess:
                auto.setText("Start při přihlášení: vyberte relaci")
            elif sess.get("paused"):
                auto.setText("◯ Start po přihlášení: vypnuto")
            elif self.snapshot.registration == "registered":
                auto.setText("● Start po přihlášení: zapnuto")
            else:
                auto.setText("⚠ Zapnout start po přihlášení · registrovat daemon")
        if not sess:
            title.setText("Vyberte relaci"); tag.setText("")
            details.setText("Vyberte řádek výše pro detail, stav, statistiky a dostupné akce.")
            return
        state, description = classify(sess, kind)
        title.setText(sess.get("name") or "Relace bez názvu")
        tag.setText(description)
        tag.setStyleSheet(f"color:{ {'error': RED, 'active': TEAL, 'paused': AMBER}.get(state, BLUE) }")
        first = endpoint_text(sess.get("alpha" if kind == "sync" else "source"), kind)
        second = endpoint_text(sess.get("beta" if kind == "sync" else "destination"), kind)
        lines = [f"Identifikátor: {sess.get('identifier', '—')}",
                 f"{'ALPHA' if kind == 'sync' else 'Zdroj'}: {first}",
                 f"{'BETA' if kind == 'sync' else 'Cíl'}: {second}"]
        if kind == "sync":
            alpha = sess.get("alpha") or {}; beta = sess.get("beta") or {}
            lines += [f"Souborů: ALPHA {alpha.get('files', '—')} · BETA {beta.get('files', '—')}    |    Velikost ALPHA: {human_bytes(alpha.get('totalFileSize', 0))}",
                      f"Úspěšných cyklů: {sess.get('successfulCycles', 0)}    |    Konflikty: {conflict_count(sess)}    |    Problémy: {problem_count(sess)}"]
            stages = [("ALPHA", alpha.get("stagingProgress")), ("BETA", beta.get("stagingProgress"))]
            for target, prog in stages:
                if prog:
                    expected_size = int(prog.get("expectedSize") or 0)
                    if expected_size:
                        percentage = min(100, round(100 * float(prog.get("receivedSize") or 0) / expected_size))
                        progress_bar.setValue(percentage)
                        progress_bar.setFormat(f"Přenos do {target}: %p %")
                        progress_bar.show()
                    expected = max(1, prog.get("expectedSize", 0))
                    lines.append(f"Přenos do {target}: {prog.get('path','')} · {100*prog.get('receivedSize',0)/expected:.0f} % "
                                 f"({human_bytes(prog.get('receivedSize',0))} / {human_bytes(prog.get('expectedSize',0))})")
            confs = sess.get("conflicts") or []
            if confs: lines.append("Konflikty (první): " + json.dumps(confs[:2], ensure_ascii=False)[:450])
            probs = [*alpha.get("scanProblems", []), *alpha.get("transitionProblems", []),
                     *beta.get("scanProblems", []), *beta.get("transitionProblems", [])]
            if probs: lines.append("Problémy (první): " + json.dumps(probs[:2], ensure_ascii=False)[:450])
        else:
            lines += [f"Otevřená spojení: {sess.get('openConnections', 0)}    |    Celkem spojení: {sess.get('totalConnections', 0)}",
                      f"Směr ven: {human_bytes(sess.get('totalOutboundData',0))}    |    Směr dovnitř: {human_bytes(sess.get('totalInboundData',0))}"]
        if sess.get("lastError"): lines.append("POSLEDNÍ CHYBA: " + str(sess["lastError"]))
        custom_note = self.conf.get("session_prefs", {}).get(str(sess.get("identifier") or ""), {}).get("note")
        if custom_note: lines.append("POZNÁMKA: " + custom_note)
        details.setText("\n".join(lines))
        if "flush" in controls: controls["flush"].setEnabled(not sess.get("paused") and not self.demo and not self.pending_action)
        if "pause" in controls: controls["pause"].setEnabled(not sess.get("paused") and not self.demo and not self.pending_action)
        if "resume" in controls: controls["resume"].setEnabled(bool(sess.get("paused")) or state in ("error", "idle") if not self.demo and not self.pending_action else False)

    def open_session_preferences(self, kind):
        sess = self.selected_session(kind)
        if not sess:
            QMessageBox.information(self, "Vyberte relaci", "Nejprve vyberte relaci v tabulce.")
            return
        identifier = str(sess.get("identifier") or "")
        prefs = dict(self.conf.get("session_prefs", {}).get(identifier, {}))
        dialog = QDialog(self)
        dialog.setWindowTitle("Nastavení relace · " + (sess.get("name") or identifier[:14]))
        dialog.setMinimumWidth(480)
        box = QVBoxLayout(dialog); box.setSpacing(15); box.setContentsMargins(24, 22, 24, 22)
        box.addWidget(label("Nastavení zobrazení a upozornění", size=17, bold=True))
        notifications = QCheckBox("Upozorňovat na nově vzniklé chyby této relace")
        notifications.setChecked(bool(prefs.get("notifications", True)))
        box.addWidget(notifications)
        box.addWidget(label("Vlastní poznámka k relaci", muted=True))
        note = QLineEdit(str(prefs.get("note", ""))); note.setMaxLength(180)
        box.addWidget(note)
        if kind == "sync":
            box.addWidget(label("Skutečná konfigurace synchronizace z Mutagenu", size=14, bold=True))
            native = label(native_config_text(sess), muted=True)
            native.setWordWrap(True); native.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(native)
            explanation = label("Watch režim a rychlost polling skenů jsou parametry samotného Mutagenu, "
                                "které CLI umožňuje nastavit při vytváření relace. U existující relace je "
                                "nelze měnit tímto dialogem. GUI ani neomezuje přenosovou rychlost.", muted=True, size=11)
            explanation.setWordWrap(True); box.addWidget(explanation)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept); controls.rejected.connect(dialog.reject)
        box.addWidget(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.conf.setdefault("session_prefs", {})[identifier] = {
            "notifications": notifications.isChecked(), "note": note.text().strip()}
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc)); return
        self.refresh_detail(kind)
        self.add_log("Nastavení relace uloženo")

    def new_current_session(self):
        page = self.pages.currentIndex()
        if page in (1, 2):
            self.create_session("sync" if page == 1 else "forward")

    def toggle_favorite(self, kind):
        session = self.selected_session(kind)
        if not session: return
        identifier = str(session.get("identifier") or "")
        if not identifier: return
        favorite_ids = self.favorites[kind]
        if identifier in favorite_ids: favorite_ids.remove(identifier)
        else: favorite_ids.add(identifier)
        self.conf["favorites"] = {k: sorted(ids) for k, ids in self.favorites.items()}
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc)); return
        self._table_signatures.pop(kind, None)
        self._table_signatures.pop("dashboard", None)
        self.fill_table(self.sync_table if kind == "sync" else self.forward_table,
                        self.snapshot.sync if kind == "sync" else self.snapshot.forward, kind)
        self.filter_table(kind)
        self.refresh_detail(kind)

    def copy_session_id(self, kind):
        sess = self.selected_session(kind)
        if sess:
            QApplication.clipboard().setText(str(sess.get("identifier", "")))
            self.add_log("Identifikátor relace zkopírován do schránky")

    def export_session_json(self, kind):
        sess = self.selected_session(kind)
        if not sess: return
        path, _ = QFileDialog.getSaveFileName(self, "Export relace (může obsahovat názvy serverů a cesty)",
                                               "mutagen-session.json", "JSON (*.json)")
        if not path: return
        try:
            Path(path).write_text(json.dumps(sess, indent=2, ensure_ascii=False), encoding="utf-8")
            self.add_log("Export relace JSON dokončen")
        except OSError as exc:
            self.report_error(str(exc))

    def session_context_menu(self, kind, point):
        table = self.sync_table if kind == "sync" else self.forward_table
        item = table.itemAt(point)
        if not item: return
        table.selectRow(item.row())
        sess = self.selected_session(kind)
        if not sess: return
        menu = QMenu(table)
        menu.addAction("★ Odebrat z oblíbených" if sess.get("identifier") in self.favorites[kind] else "☆ Přidat do oblíbených",
                       lambda: self.toggle_favorite(kind))
        menu.addAction("Zkopírovat ID", lambda: self.copy_session_id(kind))
        menu.addAction("Exportovat JSON…", lambda: self.export_session_json(kind))
        menu.addSeparator()
        if not self.demo:
            if sess.get("paused"):
                menu.addAction("Pokračovat", lambda: self.session_action(kind, "resume"))
            else:
                menu.addAction("Pozastavit", lambda: self.session_action(kind, "pause"))
            if kind == "sync":
                menu.addAction("Synchronizovat nyní", lambda: self.session_action(kind, "flush"))
                menu.addAction("Zapnout start po přihlášení" if sess.get("paused") else
                               "Vypnout start po přihlášení (pozastavit)", self.toggle_sync_startup)
        menu.exec(table.viewport().mapToGlobal(point))

    def endpoints_page(self):
        """Both endpoints as reported by Mutagen itself. Never open an extra connection."""
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setObjectName("scrollbody")
        layout = QVBoxLayout(body); layout.setContentsMargins(0, 3, 3, 15); layout.setSpacing(17)
        intro, il = card()
        il.addWidget(label("Stav obou stran z Mutagen daemonu", size=18, bold=True))
        information = label(
            "Data ALPHA/BETA pocházejí z lokálního Mutagen daemonu přes příkaz 'mutagen sync list'. "
            "Nevytváříme další SSH/HTTP spojení, nic neinstalujeme na server a nespouštíme žádnou službu. "
            "Vzdálený mutagen-agent komunikuje pouze se svým stávajícím Mutagen daemonem.",
            muted=True, size=12)
        information.setWordWrap(True); il.addWidget(information)
        chooser = QHBoxLayout()
        chooser.addWidget(label("Relace:", muted=True))
        self.endpoint_combo = QComboBox(); self.endpoint_combo.setMinimumWidth(340)
        self.endpoint_combo.currentIndexChanged.connect(self.update_endpoint_details)
        chooser.addWidget(self.endpoint_combo, 1)
        chooser.addWidget(button("↻ Obnovit z Mutagenu", lambda: self.refresh(force=True)))
        il.addLayout(chooser)
        self.endpoint_status = label("Čekám na informace z lokálního daemonu.", muted=True)
        self.endpoint_status.setWordWrap(True); il.addWidget(self.endpoint_status)
        layout.addWidget(intro)
        panes = QHBoxLayout(); panes.setSpacing(14)
        self.endpoint_cards = {}
        for side in ("left", "right"):
            f, l = card()
            title = label("ALPHA" if side == "left" else "BETA", size=18, bold=True)
            address = label("—", muted=True); address.setWordWrap(True)
            conn = label("—", size=17, bold=True)
            stats = label("—", muted=True, size=12)
            stats.setWordWrap(True)
            issues = label("—", muted=True, size=12)
            issues.setWordWrap(True)
            progress = QProgressBar(); progress.setRange(0, 100); progress.hide()
            stage = label("—", muted=True, size=11); stage.setWordWrap(True)
            for el in (title, address, separator(), conn, stats, issues, progress, stage):
                l.addWidget(el)
            l.addStretch()
            self.endpoint_cards[side] = dict(title=title, address=address, conn=conn,
                                              stats=stats, issues=issues, progress=progress, stage=stage)
            panes.addWidget(f, 1)
        layout.addLayout(panes)
        bottom, bl = card()
        bl.addWidget(label("Synchronizace jako celek", size=15, bold=True))
        self.endpoint_session_info = label("—", muted=True)
        self.endpoint_session_info.setWordWrap(True)
        bl.addWidget(self.endpoint_session_info)
        layout.addWidget(bottom)
        explanation, el = card()
        el.addWidget(label("Co Mutagen neposkytuje", size=15, bold=True))
        note = label("Tento přehled neměří CPU, RAM, disk nebo síť celého serveru, ani detailní "
                     "interní logy vzdáleného agenta. Tyto údaje nejsou součástí běžného výpisu "
                     "Mutagenu a bez dodatečného vzdáleného přístupu je nelze spolehlivě získat. "
                     "Počty souborů jsou poslední známé skeny, nikoliv garantované živé čítače.",
                     muted=True, size=11)
        note.setWordWrap(True); el.addWidget(note)
        layout.addWidget(explanation)
        layout.addStretch()
        page.setWidget(body)
        return page

    def update_endpoint_sessions(self, snapshot):
        if not hasattr(self, "endpoint_combo"):
            return
        options = [("sync", x) for x in snapshot.sync] + [("forward", x) for x in snapshot.forward]
        current = self.endpoint_combo.currentData()
        keys = [(kind, str(s.get("identifier") or "")) for kind, s in options]
        old = [self.endpoint_combo.itemData(i) for i in range(self.endpoint_combo.count())]
        if keys != old:
            self.endpoint_combo.blockSignals(True)
            self.endpoint_combo.clear()
            for kind, session in options:
                sid = str(session.get("identifier") or "")
                kind_name = "SYNC" if kind == "sync" else "PORT"
                self.endpoint_combo.addItem(f"{kind_name} · {session.get('name') or sid[:22]}", (kind, sid))
            if current in keys:
                self.endpoint_combo.setCurrentIndex(keys.index(current))
            self.endpoint_combo.blockSignals(False)
        if self.pages.currentIndex() == 9 or keys != old:
            self.update_endpoint_details()

    def update_endpoint_details(self, *_):
        if not hasattr(self, "endpoint_combo"):
            return
        key = self.endpoint_combo.currentData()
        session = None
        if key:
            kind, identifier = key
            group = self.snapshot.sync if kind == "sync" else self.snapshot.forward
            session = next((s for s in group if s.get("identifier") == identifier), None)
        if not session:
            self.endpoint_status.setText("Mutagen daemon nevrátil žádnou relaci." if self.snapshot.daemon
                                         else "Lokální Mutagen daemon není dostupný.")
            self.endpoint_session_info.setText("—")
            for view in self.endpoint_cards.values():
                view['address'].setText("—")
                view['conn'].setText("Nedostupné")
                view['stats'].setText("—")
                view['issues'].setText("—")
                view['progress'].hide()
                view['stage'].setText("—")
            return
        data = inspect_session(session, kind)
        self.endpoint_status.setText(f"{data['name']} · {data['state_text']} · stav získaný z místního daemonu")
        for side, endpoint in (("left", data['left']), ("right", data['right'])):
            widgets = self.endpoint_cards[side]
            widgets['title'].setText(endpoint.side)
            widgets['address'].setText(endpoint.address)
            widgets['conn'].setText("● Připojeno" if endpoint.connected else "● Nepřipojeno")
            widgets['conn'].setStyleSheet(f"color:{TEAL if endpoint.connected else AMBER};font-size:17px;font-weight:700")
            if kind == 'sync':
                def count(number): return '—' if number is None else f'{number:,}'.replace(',', ' ')
                scan = ('Ano' if endpoint.scanned else 'Ne') if endpoint.scanned is not None else 'Neznámo'
                widgets['stats'].setText(
                    f"Sken hotov: {scan}    •    Soubory: {count(endpoint.files)}\n"
                    f"Složky: {count(endpoint.directories)}    •    Symlinky: {count(endpoint.symlinks)}\n"
                    f"Celková velikost souborů: {human_bytes(endpoint.total_file_size) if endpoint.total_file_size is not None else '—'}")
                widgets['issues'].setText(
                    f"Problémy skenu: {endpoint.scan_problems}    •    Problémy zápisu: {endpoint.transition_problems}")
                if endpoint.staging_percent is not None:
                    widgets['progress'].setValue(round(endpoint.staging_percent))
                    widgets['progress'].show()
                else:
                    widgets['progress'].hide()
                if endpoint.staging_path or endpoint.staging_percent is not None:
                    widgets['stage'].setText(
                        f"Příjem: {endpoint.staging_path or 'soubor'}\n"
                        f"{human_bytes(endpoint.staging_bytes)} / {human_bytes(endpoint.staging_expected_bytes)}"
                        f" · {endpoint.staging_files}/{endpoint.staging_expected_files} souborů")
                else:
                    widgets['stage'].setText("Nyní není hlášen aktivní příjem souboru.")
            else:
                widgets['stats'].setText("Přesměrování portů — Mutagen hlásí pouze stav připojení endpointu.")
                widgets['issues'].setText("Podrobnosti provozu jsou dostupné pro relaci jako celek.")
                widgets['progress'].hide()
                widgets['stage'].setText("—")
        if kind == 'sync':
            lines = [f"Úspěšných cyklů: {data['successful_cycles']}    •    Konfliktů: {data['conflicts']}"]
        else:
            lines = [f"Otevřená spojení: {data['open_connections']}    •    Celkem spojení: {data['total_connections']}",
                     f"Data do cíle: {human_bytes(data['total_outbound_data'])}    •    Zpět: {human_bytes(data['total_inbound_data'])}"]
        if data['last_error']:
            lines.append('Poslední chyba: ' + data['last_error'][:1200])
        self.endpoint_session_info.setText('\n'.join(lines))

    def servers_page(self):
        """Server grouping is based exclusively on endpoint URLs in local Mutagen data."""
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget(); root.setObjectName("scrollbody")
        layout = QVBoxLayout(root); layout.setSpacing(15)
        layout.setContentsMargins(0, 3, 0, 0)
        top, tl = card()
        tl.addWidget(label("Serverové skupiny", size=18, bold=True))
        desc = label("Hostitele zjišťujeme z ALPHA/BETA a zdrojových/cílových adres Mutagenu. "
                     "Žádná nová SSH spojení ani serverová služba. Alias stejného serveru může být rozpoznán jako jiný hostitel.",
                     muted=True, size=11)
        desc.setWordWrap(True); tl.addWidget(desc)
        choose = QHBoxLayout(); choose.addWidget(label("Cíl operací:"))
        self.server_selector = QComboBox(); self.server_selector.addItem("Všechny relace", "__all__")
        self.server_selector.currentIndexChanged.connect(self.update_server_details)
        choose.addWidget(self.server_selector, 1)
        choose.addWidget(button("↻ Obnovit", lambda: self.refresh(force=True)))
        tl.addLayout(choose)
        self.server_overview = self.make_table(["SERVER", "SYNC", "PORTY", "PAUZA", "PROBLÉMY"], 175)
        self.server_overview.setMaximumHeight(225)
        self.server_overview.cellDoubleClicked.connect(self.pick_server_row)
        tl.addWidget(self.server_overview)
        layout.addWidget(top)
        actions, ac = card()
        self.server_scope_label = label("Vyber server nebo všechny relace", size=15, bold=True)
        ac.addWidget(self.server_scope_label)
        first = QHBoxLayout()
        first.addWidget(button("↻ Sync now", partial(self.bulk_action, "sync", "flush", "server"), kind="primary"))
        first.addWidget(button("⏸ Pauza synchronizací", partial(self.bulk_action, "sync", "pause", "server")))
        first.addWidget(button("▶ Pokračovat synchronizace", partial(self.bulk_action, "sync", "resume", "server")))
        first.addStretch(); ac.addLayout(first)
        second = QHBoxLayout()
        second.addWidget(button("⏸ Pauza portů", partial(self.bulk_action, "forward", "pause", "server")))
        second.addWidget(button("▶ Pokračovat porty", partial(self.bulk_action, "forward", "resume", "server")))
        second.addStretch(); ac.addLayout(second)
        advanced = button("Další hromadné akce ▾", self.show_server_advanced_actions)
        ac.addWidget(advanced)
        warning = label("Hromadné příkazy používají pouze vybraná ID. Pozastavení a obnovení platí hned "
                        "a ovlivní také chování těchto relací po příštím startu daemonu. "
                        "Pro start po přihlášení do Windows musí být daemon registrován v části Daemon.", muted=True, size=11)
        warning.setWordWrap(True); ac.addWidget(warning)
        layout.addWidget(actions)
        listings, ls = card()
        ls.addWidget(label("Synchronizace vybrané skupiny · dvojklik otevře detail", muted=True))
        self.server_sync_table = self.make_table(["RELACE", "STAV", "ALPHA", "BETA"], 155)
        self.server_sync_table.setMaximumHeight(225)
        self.server_sync_table.cellDoubleClicked.connect(lambda row, col: self.open_group_session("sync", row))
        ls.addWidget(self.server_sync_table)
        self.server_sync_empty = label("Tento server nemá synchronizační relace.", muted=True)
        ls.addWidget(self.server_sync_empty)
        ls.addWidget(label("Přesměrování vybrané skupiny", muted=True))
        self.server_forward_table = self.make_table(["RELACE", "STAV", "ZDROJ", "CÍL"], 130)
        self.server_forward_table.setMaximumHeight(180)
        self.server_forward_table.cellDoubleClicked.connect(lambda row, col: self.open_group_session("forward", row))
        ls.addWidget(self.server_forward_table)
        self.server_forward_empty = label("Tento server nemá přesměrování portů.", muted=True)
        ls.addWidget(self.server_forward_empty)
        layout.addWidget(listings, 1)
        page.setWidget(root)
        return page

    def pick_server_row(self, row, col):
        item = self.server_overview.item(row, 0)
        if item:
            index = self.server_selector.findData(item.data(Qt.ItemDataRole.UserRole))
            if index >= 0: self.server_selector.setCurrentIndex(index)

    def update_server_groups(self):
        if not hasattr(self, "server_selector"):
            return
        groups = group_servers(self.snapshot.sync, self.snapshot.forward)
        self._server_groups = {g.key: g for g in groups}
        current = self.server_selector.currentData()
        choices = [("Všechny relace", "__all__")] + [(g.name, g.key) for g in groups]
        if (choices != [(self.server_selector.itemText(i), self.server_selector.itemData(i))
                       for i in range(self.server_selector.count())]):
            self.server_selector.blockSignals(True)
            self.server_selector.clear()
            for name, key in choices: self.server_selector.addItem(name, key)
            found = self.server_selector.findData(current)
            self.server_selector.setCurrentIndex(max(0, found))
            self.server_selector.blockSignals(False)
        filter_widget = self.sync_server_filter
        filter_val = filter_widget.currentData()
        if choices != [(filter_widget.itemText(i), filter_widget.itemData(i)) for i in range(filter_widget.count())]:
            filter_widget.blockSignals(True)
            filter_widget.clear()
            for name, key in choices: filter_widget.addItem(name, key)
            found = filter_widget.findData(filter_val)
            filter_widget.setCurrentIndex(max(0, found))
            filter_widget.blockSignals(False)
            self.filter_table("sync")
        view = self.server_overview
        view.setSortingEnabled(False)
        view.setUpdatesEnabled(False)
        try:
            view.setRowCount(len(groups))
            for row, group in enumerate(groups):
                values = [group.name, str(len(group.sync_ids)), str(len(group.forward_ids)),
                          str(group.paused), str(group.errors)]
                for col, value in enumerate(values):
                    item = view.item(row, col)
                    if item is None:
                        item = QTableWidgetItem(value); view.setItem(row, col, item)
                    elif item.text() != value: item.setText(value)
                    if col == 0: item.setData(Qt.ItemDataRole.UserRole, group.key)
        finally:
            view.setUpdatesEnabled(True)
        if self.pages.currentIndex() == 10:
            self.update_server_details()

    def server_targets(self, kind, scope):
        sessions = self.snapshot.sync if kind == "sync" else self.snapshot.forward
        if scope == "all":
            return list(sessions)
        key = self.server_selector.currentData() if hasattr(self, "server_selector") else "__all__"
        if key == "__all__": return list(sessions)
        return [session for session in sessions if key in session_servers(session, kind)]

    def update_server_details(self, *_):
        if not hasattr(self, "server_selector"):
            return
        key = self.server_selector.currentData()
        selection_name = self.server_selector.currentText()
        sync = self.server_targets("sync", "server")
        forward = self.server_targets("forward", "server")
        self.server_scope_label.setText(f"{selection_name} · {len(sync)} sync · {len(forward)} portů")
        self.server_sync_empty.setVisible(not sync)
        self.server_forward_empty.setVisible(not forward)
        for kind, sessions, table in (("sync", sync, self.server_sync_table),
                                      ("forward", forward, self.server_forward_table)):
            table.setSortingEnabled(False)
            table.setRowCount(len(sessions))
            for row, sess in enumerate(sessions):
                state = classify(sess, kind)[1]
                cols = [sess.get("name") or str(sess.get("identifier"))[:20], state,
                        endpoint_text(sess.get("alpha" if kind == "sync" else "source"), kind),
                        endpoint_text(sess.get("beta" if kind == "sync" else "destination"), kind)]
                for col, value in enumerate(cols):
                    item = table.item(row, col)
                    if item is None: item = QTableWidgetItem(); table.setItem(row, col, item)
                    item.setText(str(value))
                    if col == 0: item.setData(Qt.ItemDataRole.UserRole, sess.get("identifier"))

    def open_group_session(self, kind, row):
        listing = self.server_sync_table if kind == "sync" else self.server_forward_table
        item = listing.item(row, 0)
        if not item: return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        self.set_page(1 if kind == "sync" else 2)
        if kind == "sync":
            self.sync_server_filter.setCurrentIndex(0)
            self.sync_search.clear()
            self.sync_state_filter.setCurrentIndex(0)
            self.sync_favorites_only.setChecked(False)
        else:
            self.forward_search.clear()
            self.forward_state_filter.setCurrentIndex(0)
            self.forward_favorites_only.setChecked(False)
        table = self.sync_table if kind == "sync" else self.forward_table
        for index in range(table.rowCount()):
            current = table.item(index, 0)
            if current and current.data(Qt.ItemDataRole.UserRole) == identifier:
                table.selectRow(index)
                table.scrollToItem(current)
                break

    def show_server_advanced_actions(self):
        """Keep reset/termination out of the one-click toolbar."""
        menu = QMenu(self)
        menu.addAction("Reset historie synchronizací…", lambda: self.bulk_action("sync", "reset", "server"))
        menu.addSeparator()
        menu.addAction("Trvale odstranit synchronizace…", lambda: self.bulk_action("sync", "terminate", "server"))
        menu.addAction("Trvale odstranit přesměrování…", lambda: self.bulk_action("forward", "terminate", "server"))
        menu.exec(self.cursor().pos())

    def bulk_action(self, kind: str, action: str, scope: str = "all"):
        if self.demo or self.pending_action: return
        candidates = self.server_targets(kind, scope)
        if action == "flush":
            candidates = [s for s in candidates if not s.get("paused")]
        elif action == "pause":
            candidates = [s for s in candidates if not s.get("paused")]
        elif action == "resume":
            candidates = [s for s in candidates if s.get("paused") or classify(s, kind)[0] in ("error", "idle")]
        ids = [str(s.get("identifier") or "") for s in candidates]
        ids = list(dict.fromkeys(identifier for identifier in ids if identifier))
        if not ids:
            QMessageBox.information(self, "Žádné relace", "Pro tuto operaci nejsou žádné vhodné relace.")
            return
        action_name = {"flush":"Vynutit synchronizační cyklus", "pause":"Pozastavit",
                       "resume":"Pokračovat", "reset":"Resetovat historii", "terminate":"Odstranit"}[action]
        group_name = "všech relací" if scope == "all" else self.server_selector.currentText()
        body = f"{action_name} {len(ids)} konkrétních relací ({group_name})?"
        if action == "flush": body += "\n\nPříkaz zahájí synchronizaci a nebude čekat na dokončení všech přenosů."
        if action in ("pause", "resume"):
            body += "\n\nZmění se aktuální stav relací i jejich chování při dalším startu daemonu."
        if action in ("reset", "terminate"):
            body += "\n\nTato operace může změnit historii synchronizací nebo trvale odstranit relace."
        choice = QMessageBox.question(self, "Potvrdit hromadnou akci", body,
                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if choice != QMessageBox.StandardButton.Yes: return
        if action in ("reset", "terminate"):
            expected = "RESETOVAT" if action == "reset" else "ODSTRANIT"
            value, accepted = QInputDialog.getText(self, "Druhé potvrzení", 
                f"Pro potvrzení operace nad {len(ids)} relacemi napište {expected}:")
            if not accepted or value.strip() != expected:
                return
        self.pending_action = True
        self.add_log(f"Hromadná akce: {kind} {action} · {len(ids)} explicitních ID")
        client = MutagenClient(self.client.binary)
        def success(output):
            self.add_log(f"Hromadná akce odeslána: {action}, {len(ids)} relací")
            if output: self.add_log(output[:1000])
        def done():
            self.pending_action = False
            self.refresh(force=True)
        self.submit(lambda: client.execute_many(kind, action, ids), success, self.report_error, done)

    def toggle_sync_startup(self):
        """Native semantics: Mutagen persists paused/unpaused state across daemon restarts."""
        if self.demo or self.pending_action: return
        session = self.selected_session("sync")
        if not session: return
        ident = str(session.get("identifier") or "")
        if not ident: return
        if not session.get("paused"):
            if self.snapshot.registration != "registered":
                answer = QMessageBox.question(self, "Aktivovat start po přihlášení?",
                    "Synchronizace nyní běží, ale automatický start Mutagen daemonu není registrovaný. "
                    "Chceš registrovat daemon pro přihlášení do Windows? Ovlivní to i jiné aktivní relace.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    self.run_command("daemon", "register")
                return
            choice = QMessageBox.question(self, "Vypnout start synchronizace?",
                "Mutagen nemá samostatnou volbu 'nespouštět příště, ale nechat běžet nyní'. "
                "Vypnutí proto relaci okamžitě pozastaví. Pokračovat?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if choice == QMessageBox.StandardButton.Yes:
                self.run_command("sync", "pause", target=ident)
            return
        needs_registration = self.snapshot.registration != "registered"
        if needs_registration:
            response = QMessageBox.question(self, "Registrovat start Mutagen daemonu?",
                "Pro obnovení po přihlášení musí být registrován samotný Mutagen daemon. "
                "Registrace ovlivní i ostatní nepozastavené relace. "
                "Zaregistrovat daemon a pokračovat v této synchronizaci nyní?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes: return
        self.run_command("sync", "resume", target=ident, register_before=needs_registration)

    def monitoring_page(self):
        page = QScrollArea(); page.setWidgetResizable(True); page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(); body.setObjectName("scrollbody")
        layout = QVBoxLayout(body); layout.setContentsMargins(0, 3, 3, 18); layout.setSpacing(18)
        control, cl = card()
        heading = QHBoxLayout()
        heading.addWidget(label("Vývoj prostředků a provozu", size=17, bold=True))
        heading.addStretch(); heading.addWidget(label("Zobrazit:", muted=True))
        self.monitor_range = QComboBox()
        for title, hours in [("5 minut", 5/60), ("30 minut", .5), ("2 hodiny", 2),
                             ("12 hodin", 12), ("24 hodin", 24), ("48 hodin", 48)]:
            self.monitor_range.addItem(title, hours)
        self.monitor_range.setCurrentIndex(1)
        self.monitor_range.currentIndexChanged.connect(lambda _=None: self.refresh_charts(force=True))
        heading.addWidget(self.monitor_range)
        self.monitor_live_button = button("⏸ Zmrazit grafy", self.toggle_charts)
        self.monitor_live_button.setToolTip("Zastaví automatické aktualizace grafů pro snadnější prohlížení")
        heading.addWidget(self.monitor_live_button)
        png_btn = button("Uložit PNG", self.export_monitor_png)
        png_btn.setToolTip("Uloží aktuálně zobrazené grafy jako PNG obrázek")
        heading.addWidget(png_btn)
        csv_btn = button("Export CSV", self.export_metrics, kind="primary")
        csv_btn.setToolTip("Exportuje naměřená data do CSV souboru pro analýzu v externím nástroji")
        heading.addWidget(csv_btn)
        cl.addLayout(heading)
        cl.addWidget(label("Data se ukládají lokálně po dobu 48 hodin. Grafy ukazují skutečné naměřené hodnoty; "
                           "při vypnuté aplikaci vzniká v historii mezera.", muted=True, size=11))
        self.gui_usage_label = label("Zatížení aplikace: čekám na měření", muted=True, size=11)
        cl.addWidget(self.gui_usage_label)
        layout.addWidget(control)
        stats_panel, stats_layout = card()
        stats_layout.addWidget(label("Souhrn vybraného období · skutečná měření", size=15, bold=True))
        self.stats_label = QLabel("Čekám na data…")
        self.stats_label.setTextFormat(Qt.TextFormat.PlainText)
        self.stats_label.setWordWrap(True)
        self.stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_panel)
        self.monitor_graphs = {}
        self.monitor_labels = {}
        chart_specs = [
            ("cpu", "Procesor", "Spotřeba lokálních procesů Mutagenu (může přesáhnout 100 %)", BLUE, None, "percent"),
            ("memory", "Paměť RAM", "Rezidentní paměť místních procesů", TEAL, None, "memory"),
            ("disk", "Procesové diskové I/O", "Čtení (modrá) · zápis (zelená); hodnoty podle operačního systému", BLUE, TEAL, "bytes_s"),
            ("traffic", "Přesměrovaná data", "Ven (modrá) · dovnitř (zelená); počítáno z kumulativních čítačů forward relací", BLUE, TEAL, "bytes_s"),
            ("sessions", "Stav relací", "Aktivní (zelená) · problémové (červená)", TEAL, RED, "number"),
        ]
        for index in range(0, len(chart_specs), 2):
            line = QHBoxLayout(); line.setSpacing(14)
            for key, title, subtitle, color, secondary, unit in chart_specs[index:index + 2]:
                panel, content = card()
                top = QHBoxLayout(); top.addWidget(label(title, size=15, bold=True)); top.addStretch()
                val = label("—", muted=True, size=12)
                self.monitor_labels[key] = val; top.addWidget(val); content.addLayout(top)
                content.addWidget(label(subtitle, muted=True, size=10))
                graph = Graph(color, panel, unit=unit, secondary=secondary)
                graph.setMinimumHeight(205)
                content.addWidget(graph)
                self.monitor_graphs[key] = graph
                line.addWidget(panel, 1)
            if len(chart_specs[index:index+2]) == 1: line.addStretch(1)
            layout.addLayout(line)
        process_card, process_l = card()
        process_l.addWidget(label("Jednotlivé lokální procesy Mutagenu", size=16, bold=True))
        process_l.addWidget(label("Spotřeba je vztažena k procesům, nikoliv k jednotlivým synchronizačním relacím.", muted=True))
        self.process_table = self.make_table(["PID", "PROCES", "CPU", "RAM", "ČTENÍ", "ZÁPIS"], height=180)
        self.process_table.setMinimumHeight(180)
        self.process_table.setMaximumHeight(280)
        self.process_table.setColumnWidth(0, 100)
        self.process_table.setColumnWidth(1, 185)
        self.process_table.setColumnWidth(2, 95)
        self.process_table.setColumnWidth(3, 105)
        self.process_table.setColumnWidth(4, 110)
        process_l.addWidget(self.process_table)
        layout.addWidget(process_card)
        layout.addStretch(); page.setWidget(body)
        return page

    def toggle_charts(self):
        self.chart_frozen = not self.chart_frozen
        self.monitor_live_button.setText("▶ Obnovovat grafy" if self.chart_frozen else "⏸ Zmrazit grafy")
        if not self.chart_frozen: self.refresh_charts(force=True)

    def export_monitor_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Uložit aktuální grafy do PNG",
                                               "mutagen-monitoring.png", "PNG (*.png)")
        if not path: return
        # Export exactly what is visible on the monitoring page: all five graphs.
        # Render full scroll-area contents, including off-screen cards.
        # The QScrollArea owns the real visual body via its widget().
        scroll = self.pages.widget(6)
        body = scroll.widget()
        image = QPixmap(body.size())
        image.fill(QColor(BG))
        body.render(image)
        if not image.save(path, "PNG"):
            self.report_error("Nepodařilo se uložit obrázek PNG.")
        else:
            self.add_log("Monitoring uložen jako PNG")

    def export_metrics(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export monitoringu", "mutagen-metrics.csv", "CSV (*.csv)")
        if not path: return
        try:
            self.history.export_csv(path, hours=float(self.monitor_range.currentData()))
            self.add_log("Historie monitoringu exportována do CSV")
        except (sqlite3.Error, OSError) as exc:
            self.report_error(str(exc))

    def diagnostics_page(self):
        root = QWidget(); root.setObjectName("main")
        l = QVBoxLayout(root); l.setContentsMargins(0, 3, 0, 0); l.setSpacing(16)
        card1, vl = card()
        head = QHBoxLayout()
        head.addWidget(label("Diagnostický přehled", size=17, bold=True))
        head.addStretch()
        safe_btn = button("Bezpečný report JSON", self.export_safe_report, kind="primary")
        safe_btn.setToolTip("Exportuje diagnostiku bez reálných cest a adres — bezpečné pro sdílení")
        head.addWidget(safe_btn)
        full_btn = button("Úplný snapshot JSON", self.export_snapshot)
        full_btn.setToolTip("Exportuje kompletní snapshot včetně cest, adres a chybových zpráv")
        head.addWidget(full_btn)
        copy_btn = button("Kopírovat souhrn", self.copy_diagnostics)
        copy_btn.setToolTip("Zkopíruje diagnostický souhrn do schránky")
        head.addWidget(copy_btn)
        vl.addLayout(head)
        note_lbl = label("Úplný export obsahuje skutečné endpointy, cesty a chyby. Před odesláním jiné osobě zkontrolujte obsah.", muted=True)
        note_lbl.setWordWrap(True)
        vl.addWidget(note_lbl)
        self.diag_summary = QLabel("Čekám na data…"); self.diag_summary.setWordWrap(True)
        self.diag_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.diag_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vl.addWidget(self.diag_summary); l.addWidget(card1)
        problems, pl = card()
        problems_head = QHBoxLayout()
        problems_head.addWidget(label("Konflikty, chyby a problémy", size=16, bold=True))
        problems_head.addStretch()
        self.diag_problem_count = label("", muted=True, size=11)
        problems_head.addWidget(self.diag_problem_count)
        pl.addLayout(problems_head)
        self.diagnostics_view = QPlainTextEdit(); self.diagnostics_view.setReadOnly(True)
        self.diagnostics_view.setStyleSheet(f"font-family:Consolas,monospace;font-size:12px;background:#0A1421;color:{TEXT};")
        pl.addWidget(self.diagnostics_view); l.addWidget(problems, 1)
        return root

    def update_diagnostics(self, snap):
        summary = (f"Mutagen: {snap.binary or 'nenalezen'}\nVerze: {snap.version or 'nezjištěna'}\n"
                   f"Daemon: {'online' if snap.daemon else 'offline'}\n"
                   f"Procesů Mutagenu: {snap.processes} | CPU: {snap.cpu:.1f} % | RAM: {human_bytes(snap.memory)}\n"
                   f"Synchronizace: {len(snap.sync)} | Přesměrování: {len(snap.forward)}\n"
                   f"Autostart daemonu: {snap.registration}")
        if snap.error: summary += "\nChyba CLI: " + snap.error
        self.diag_summary.setText(summary)
        notes = []
        for kind, sessions in (("sync", snap.sync), ("forward", snap.forward)):
            for sess in sessions:
                state, description = classify(sess, kind)
                if state != "error": continue
                notes.append(f"[{kind}] {sess.get('name') or sess.get('identifier')} — {description}")
                if sess.get("lastError"): notes.append("  Chyba: " + str(sess["lastError"]))
                if kind == "sync":
                    for idx, conflict in enumerate(sess.get("conflicts") or []):
                        if idx >= 10: notes.append("  … další konflikty nezobrazeny"); break
                        notes.append("  Konflikt: " + json.dumps(conflict, ensure_ascii=False)[:500])
                    for side in ("alpha", "beta"):
                        endpoint = sess.get(side) or {}
                        for field in ("scanProblems", "transitionProblems"):
                            for problem in (endpoint.get(field) or [])[:10]:
                                notes.append(f"  {side}.{field}: " + json.dumps(problem, ensure_ascii=False)[:500])
        self.diagnostics_view.setPlainText("\n".join(notes) if notes else "Žádné problémové relace nebyly při poslední obnově zjištěny.")
        if hasattr(self, "diag_problem_count"):
            if notes:
                n = sum(1 for line in notes if not line.startswith("  "))
                self.diag_problem_count.setText(f"⚠  {n} problémová {'relace' if n == 1 else 'relace' if 2 <= n <= 4 else 'relací'}")
                self.diag_problem_count.setStyleSheet(f"color:{RED};font-size:11px;")
            else:
                self.diag_problem_count.setText("✓  vše OK")
                self.diag_problem_count.setStyleSheet(f"color:{TEAL};font-size:11px;")

    def export_safe_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "Bezpečný diagnostický report",
                                               "mutagen-safe-report.json", "JSON (*.json)")
        if not path: return
        try:
            data = safe_diagnostic_report(self.snapshot)
            data["resource_summary"] = self.history.statistics(hours=1)
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Bezpečný diagnostický report uložen (bez cest a adres)")
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))

    def copy_diagnostics(self):
        QApplication.clipboard().setText(self.diag_summary.text() + "\n\n" + self.diagnostics_view.toPlainText())
        self.add_log("Diagnostický souhrn zkopírován")

    def export_snapshot(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export diagnostiky", "mutagen-snapshot.json", "JSON (*.json)")
        if not path: return
        data = {"timestamp": datetime.now().isoformat(timespec="seconds"),
                "daemon": self.snapshot.daemon, "version": self.snapshot.version,
                "binary": self.snapshot.binary, "error": self.snapshot.error,
                "registration": self.snapshot.registration,
                "sync": self.snapshot.sync, "forward": self.snapshot.forward}
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Export diagnostiky dokončen")
        except OSError as exc:
            self.report_error(str(exc))

    def check_alerts(self, snap):
        # Do not misclassify sessions as deleted during a temporary daemon outage.
        if self.previous_daemon is not None and self.previous_daemon != snap.daemon:
            self.add_log("Daemon znovu odpovídá" if snap.daemon else "POZOR: Daemon neodpovídá")
        self.previous_daemon = snap.daemon
        if not snap.daemon:
            return
        from insights import state_transitions
        new_states = {(kind, sess.get("identifier")): classify(sess, kind)[0]
                      for kind, group in (("sync", snap.sync), ("forward", snap.forward)) for sess in group}
        if self.previous_states is not None:
            for kind, identifier, previous, state in state_transitions(self.previous_states, new_states):
                group = snap.sync if kind == "sync" else snap.forward
                sess = next((s for s in group if s.get("identifier") == identifier), {})
                title = sess.get("name") or str(identifier)[:14]
                if state == "error": message = f"POZOR: Relace {title} vyžaduje pozornost"
                elif previous == "error": message = f"Relace {title} se zotavila ({state})"
                elif state == "paused": message = f"Relace {title} byla pozastavena"
                elif previous == "paused": message = f"Relace {title} byla obnovena"
                else: message = f"Relace {title}: {previous} → {state}"
                self.add_log(message)
                wants_alert = self.conf.get("session_prefs", {}).get(str(identifier), {}).get("notifications", True)
                if state == "error" and wants_alert and self.conf.get("alerts", True) and self.tray.isVisible():
                    self.tray.showMessage("Mutagen Control – problém", message,
                                          QSystemTrayIcon.MessageIcon.Warning, 7000)
        self.previous_states = new_states

    def create_session(self, kind):
        if self.demo:
            QMessageBox.information(self, "Demo", "V demo režimu jsou zásahy vypnuté.")
            return
        if not self.client.binary:
            QMessageBox.warning(self, "Mutagen nenalezen", "Nejprve nastavte mutagen.exe v Nastavení.")
            self.set_page(5); return
        dlg = SessionDialog(kind, self, default_profile=self.conf.get("new_sync_profile", "default"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.run_command(kind, "create", options=dlg.arguments())

    def session_action(self, kind, action):
        sess = self.selected_session(kind)
        if not sess: return
        name = sess.get("name") or sess.get("identifier")
        if action in ("terminate", "reset"):
            if action == "terminate":
                info = (f"Opravdu trvale odstranit relaci „{name}“?\n\n"
                        "Příkaz terminate neodstraňuje soubory na koncových bodech, ale relace již nebude pokračovat.")
            else:
                info = (f"Resetovat historii synchronizace „{name}“?\n\n"
                        "Mutagen se bude chovat jako u nově vytvořené relace a může znovu vyhodnocovat změny.")
            choice = QMessageBox.warning(self, "Potvrzení operace", info,
                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if choice != QMessageBox.StandardButton.Yes: return
        self.run_command(kind, action, target=sess.get("identifier", ""))

    def daemon_action(self, action):
        if action == "stop":
            response = QMessageBox.warning(self, "Zastavit daemon?",
                "Zastavení přeruší všechny synchronizace a přesměrování spravované tímto démonem. Pokračovat?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if response != QMessageBox.StandardButton.Yes: return
        self.run_command("daemon", action)

    def run_command(self, kind, action, target="", options=None, register_before=False):
        if self.demo or self.pending_action: return
        self.pending_action = True
        self.add_log(f"Spouštím: mutagen {kind} {action}" + (" (vybraná relace)" if target else ""))
        client = MutagenClient(self.client.binary)
        def do():
            if register_before:
                client.execute("daemon", "register")
            return client.execute(kind, action, target, options)
        def success(output):
            if output: self.add_log(output[:1800])
            self.add_log(f"Dokončeno: {kind} {action}")
        def error(message):
            self.report_error(message)
        def done():
            self.pending_action = False
            QTimer.singleShot(450, lambda: self.refresh(force=True))
        self.submit(do, success, error, done)

    def report_error(self, message):
        self.add_log("CHYBA: " + message)
        QMessageBox.critical(self, "Mutagen – chyba", message)

    def show_window(self):
        self.showNormal(); self.raise_(); self.activateWindow()
        self.update_polling_mode()

    def quit_app(self):
        if self.pending_action:
            QMessageBox.information(self, "Probíhá příkaz Mutagenu",
                                    "Nejprve nechte dokončit právě spuštěný příkaz.")
            self.show_window()
            return
        self.tail_timer.stop()
        self._allow_exit = True
        self.tray.hide()
        self.close()

    def closeEvent(self, event):
        if self.pending_action and self._allow_exit:
            event.ignore()
            QMessageBox.information(self, "Probíhá příkaz Mutagenu",
                                    "Nejprve nechte dokončit právě spuštěný příkaz.")
            return
        if self.conf.get("tray", True) and QSystemTrayIcon.isSystemTrayAvailable() and not self._allow_exit:
            self.hide(); event.ignore()
        else:
            self.tail_timer.stop()
            if hasattr(self, "metric_timer"):
                self.metric_timer.stop()
            if hasattr(self, "timer"):
                self.timer.stop()
            if self.recorder is not None:
                self.recorder.close(timeout=8)
            try:
                self.history.close()
            except sqlite3.Error:
                pass
            event.accept()
            QApplication.instance().quit()


def main():
    self_test = "--self-test" in sys.argv
    if self_test:
        # A packaged EXE can prove it can load Qt and construct every page,
        # without touching the user's live Mutagen sessions.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # Windows taskbar icon groups the application with its native window.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MutagenControl.Desktop")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Mutagen Control")
    app.setOrganizationName("MutagenControl")
    app.setQuitOnLastWindowClosed(False)
    if self_test:
        from pathlib import Path
        import tempfile
        import traceback
        result_path = Path(tempfile.gettempdir()) / "mutagen-control-self-test.log"
        window = None
        try:
            window = MainWindow(demo=True)
            window.show()
            app.processEvents()
            window.apply_snapshot(window.snapshot)
            for index in range(window.pages.count()):
                window.set_page(index)
                app.processEvents()
            import shiboken6
            assert shiboken6.isValid(window.cpu_chart)
            assert shiboken6.isValid(window.mem_chart)
            assert shiboken6.isValid(window.register_message)
            window.set_page(10)
            for index in range(window.server_selector.count()):
                window.server_selector.setCurrentIndex(index)
                assert window.server_sync_table.rowCount() == len(window.server_targets("sync", "server"))
                assert window.server_forward_table.rowCount() == len(window.server_targets("forward", "server"))
            result_path.write_text("OK: GUI stranky a serverove skupiny se vykreslily.\n", encoding="utf-8")
            exit_code = 0
        except Exception:
            result_path.write_text(traceback.format_exc(), encoding="utf-8")
            exit_code = 1
        finally:
            if window is not None:
                window._allow_exit = True
                window.close()
        sys.exit(exit_code)
    window = MainWindow(demo="--demo" in sys.argv)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
