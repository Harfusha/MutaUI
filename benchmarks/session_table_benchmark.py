"""Synthetic Qt model benchmark. It does not run a GUI, daemon, or network call."""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, Qt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import SessionTableModel  # noqa: E402


def measure(count: int, repetitions: int = 5) -> float:
    sessions = [
        {"identifier": f"synthetic-{index}", "name": f"Synthetic {index:04}", "status": 6,
         "alpha": {"path": f"C:/alpha/{index}"}, "beta": {"path": f"C:/beta/{index}"}}
        for index in range(count)
    ]
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    durations = []
    for _ in range(repetitions):
        start = time.perf_counter()
        model.set_sessions(sessions)
        for row in range(model.rowCount()):
            for column in range(model.columnCount()):
                model.index(row, column).data(Qt.ItemDataRole.DisplayRole)
        durations.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(durations), 3)


if __name__ == "__main__":
    QCoreApplication([])
    print(json.dumps({str(count): measure(count) for count in (10, 100, 500, 1000)}, indent=2))
