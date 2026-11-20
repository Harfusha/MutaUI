"""System tray and lifecycle controller mixin for MainWindow."""

from __future__ import annotations

import time
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from mutaui.ui.formatters import localized_action
from mutaui.ui.localization import set_localized_tooltip
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.styles.main_stylesheet import TEAL
from mutaui.ui.tray_status import update_tray_status as update_tray_status_ui


class TrayMixin:
    """Mixin providing system tray management, icon coloring, and window lifecycle."""

    @staticmethod
    def make_icon() -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(TEAL))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(3, 3, 58, 58), 17, 17)
        p.setBrush(QColor("#0C1B25"))
        p.drawRoundedRect(QRectF(16, 16, 11, 32), 5, 5)
        p.drawRoundedRect(QRectF(34, 16, 11, 32), 5, 5)
        p.end()
        return QIcon(pix)

    def create_tray(self: Any) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self._last_notification_session_keys = ()
        set_localized_tooltip(self.tray, "Mutagen Control")
        menu = QMenu(self)
        show_action = localized_action("Open Mutagen Control", self)
        show_action.triggered.connect(self.show_window)
        quit_action = localized_action("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self.show_window()
                if reason == QSystemTrayIcon.ActivationReason.DoubleClick
                else None
            )
        )
        self.tray.messageClicked.connect(self.open_notified_issue)
        if hasattr(self, "snapshot") and self.snapshot is not None:
            self.update_tray_status(self.snapshot, {})
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _tray_status_icon(self: Any, status: str) -> QIcon:
        pixmap = self.windowIcon().pixmap(64, 64)
        painter = QPainter(pixmap)
        colors = {
            "issue": "#EF4444",
            "paused": "#F59E0B",
            "busy": "#38BDF8",
            "healthy": "#22C55E",
            "idle": "#64748B",
            "offline": "#EF4444",
            "unknown": "#A78BFA",
        }
        border_color = "#FFFFFF" if getattr(self, "conf", {}).get("theme") == "light" else "#0B1019"
        painter.setPen(QPen(QColor(border_color), 2))
        painter.setBrush(QColor(colors.get(status, colors["unknown"])))
        painter.drawEllipse(43, 43, 18, 18)
        painter.end()
        return QIcon(pixmap)

    def update_tray_status(self: Any, snap: Any, states: Mapping[tuple[str, str], str]) -> None:
        update_tray_status_ui(self.tray, self._tray_status_icon, snap, states)

    def open_notified_issue(self: Any) -> None:
        keys = self._last_notification_session_keys
        if not keys:
            self.show_window()
            return
        if len(keys) == 1:
            kind, identifier = keys[0]
        else:
            labels = [f"{kind}: {identifier}" for kind, identifier in keys]
            selected, accepted = QInputDialog.getItem(
                self,
                translate_text("Session issues", active_language()),
                translate_text("Choose the session to open", active_language()),
                labels,
                0,
                False,
            )
            if not accepted:
                return
            kind, identifier = keys[labels.index(selected)]
        self.handle_launch_request({"command": "open_session", "session_id": identifier})

    def tray_idle_seconds(self: Any) -> float:
        now = time.monotonic()
        elapsed = float(self._tray_idle_seconds_pending)
        if self._tray_idle_mode and self._tray_idle_started_at is not None:
            elapsed += max(0.0, now - float(self._tray_idle_started_at))
        return float(round(elapsed, 3))

    def commit_tray_idle_sample(self: Any) -> None:
        self._tray_idle_seconds_pending = 0.0
        self._tray_idle_started_at = time.monotonic() if self._tray_idle_mode else None

    def show_window(self: Any) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_polling_mode()

    def quit_app(self: Any) -> None:
        if self.pending_action:
            QMessageBox.information(
                self,
                translate_text("Mutagen Command in Progress", active_language()),
                translate_text("Wait for the current command to finish first.", active_language()),
            )
            self.show_window()
            return
        self.tail_timer.stop()
        self._allow_exit = True
        self.tray.hide()
        self.close()

    def closeEvent(self: Any, event: QCloseEvent) -> None:
        if self.pending_action and self._allow_exit:
            event.ignore()
            QMessageBox.information(
                self,
                translate_text("Mutagen Command in Progress", active_language()),
                translate_text("Wait for the current command to finish first.", active_language()),
            )
            return
        if (
            self.conf.get("tray", True)
            and QSystemTrayIcon.isSystemTrayAvailable()
            and not self._allow_exit
        ):
            self.hide()
            event.ignore()
        else:
            self.tail_timer.stop()
            if hasattr(self, "metric_timer"):
                self.metric_timer.stop()
            if hasattr(self, "timer"):
                self.timer.stop()
            if self.workers:
                self._shutdown_pending = True
                self.statusBar().showMessage(
                    translate_text(
                        "Waiting for background tasks to finish before closing…",
                        active_language(),
                    )
                )
                event.ignore()
                return
            if self.recorder is not None:
                self.recorder.close(timeout=8)
            with suppress(Exception):
                self.history.close()
            self._shutdown_pending = False
            event.accept()
            app_inst = QApplication.instance()
            if app_inst is not None:
                app_inst.quit()
