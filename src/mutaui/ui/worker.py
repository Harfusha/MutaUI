from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self.func = func
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.func())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()
