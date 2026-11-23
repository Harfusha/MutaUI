"""Event logging and export mixin for MainWindow."""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QMessageBox

from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.widgets.basic import append_plain_text_preserving_view


class LoggingMixin:
    """Mixin managing application event logs, persistent history recording, and exports."""

    def add_log(self: Any, message: object) -> None:
        safe_message = str(message).replace("\r", "").strip()
        self.logs.append(f"[{datetime.now():%d.%m. %H:%M:%S}] {safe_message}")
        severity = "warning" if "ERROR" in safe_message or "WARNING" in safe_message else "info"
        if self.recorder is not None:
            self.recorder.add_event(safe_message, severity)
        else:
            with suppress(sqlite3.Error):
                self.history.add_event(safe_message, severity)
        if hasattr(self, "log_view"):
            append_plain_text_preserving_view(self.log_view, self.logs[-1], follow_end=True)
        if hasattr(self, "log_count_label"):
            n = len(self.logs)
            self.log_count_label.setText(
                f"{n} {'entry' if n == 1 else 'entries' if 2 <= n <= 4 else 'entries'}"
            )

    def clear_logs(self: Any) -> None:
        self.logs.clear()
        self.log_view.clear()
        if self.recorder is not None:
            self.recorder.clear_events()
        else:
            with suppress(sqlite3.Error):
                self.history.clear_events()
        self.add_log("UI history cleared")

    def export_logs(self: Any) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Save History", active_language()),
            "mutagen-control-log.txt",
            translate_text("Text (*.txt)", active_language()),
        )
        if not path:
            return
        try:
            Path(path).write_text("\n".join(self.logs) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, translate_text("Write Error", active_language()), str(exc))
