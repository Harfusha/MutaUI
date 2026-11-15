"""Synthetic sessions using the production model and an offscreen Qt table view."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

import psutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import __version__ as pyside_version  # noqa: E402
from PySide6.QtCore import QEvent, QSortFilterProxyModel, Qt  # noqa: E402
from PySide6.QtTest import QSignalSpy  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableView  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as app_module  # noqa: E402

SessionTableModel = app_module.SessionTableModel

SESSION_SIZES = (0, 1, 10, 100, 500, 1000, 5000)
REPETITIONS = 30


def session_fixtures(count: int) -> list[dict[str, object]]:
    return [
        {
            "identifier": f"synthetic-{index}",
            "name": f"Synthetic {index:04}",
            "status": 6,
            "alpha": {"path": f"C:/alpha/{index}"},
            "beta": {"path": f"C:/beta/{index}"},
        }
        for index in range(count)
    ]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 3)


def measure(count: int, repetitions: int = REPETITIONS) -> dict[str, float | int]:
    sessions = session_fixtures(count)
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    durations = []
    for _ in range(repetitions):
        start = time.perf_counter()
        model.set_sessions(sessions)
        for row in range(model.rowCount()):
            for column in range(model.columnCount()):
                model.index(row, column).data(Qt.ItemDataRole.DisplayRole)
        durations.append((time.perf_counter() - start) * 1000)
    return {
        "rows": count,
        "repetitions": repetitions,
        "p50_ms": percentile(durations, 0.50),
        "p95_ms": percentile(durations, 0.95),
        "max_ms": round(max(durations), 3),
    }


def measure_refresh_cases(count: int, repetitions: int = REPETITIONS) -> dict[str, object]:
    """Separate no-op, one-row change and structural-change refresh costs.

    Return latency distributions and model signals; do not treat synthetic
    offscreen timings as installed-GUI or live-Mutagen performance evidence.
    """
    if count < 1 or repetitions < 2:
        raise ValueError("Refresh canary requires at least one row and two repetitions")

    original = session_fixtures(count)
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    model.set_sessions(original)
    resets = QSignalSpy(model.modelReset)
    changed = QSignalSpy(model.dataChanged)
    times: dict[str, list[float]] = {
        "unchanged": [],
        "one_row_changed": [],
        "structural_change": [],
    }
    target = count // 2

    for _ in range(repetitions):
        # Real applications receive a fresh native JSON snapshot every poll.
        start = time.perf_counter()
        model.set_sessions([dict(item) for item in original])
        times["unchanged"].append((time.perf_counter() - start) * 1000)

    for i in range(repetitions):
        updated = [dict(item) for item in original]
        updated[target]["name"] = f"Edited {i:04d}"
        start = time.perf_counter()
        model.set_sessions(updated)
        times["one_row_changed"].append((time.perf_counter() - start) * 1000)

    changed_rows = changed.count()
    # Restore the original content once before measuring structural changes.
    # Otherwise the first insertion also includes an unrelated edited-name update.
    model.set_sessions(original)
    inserted = QSignalSpy(model.rowsInserted)
    removed = QSignalSpy(model.rowsRemoved)
    extra = {
        "identifier": "temporary-structural-row",
        "name": "Temporary",
        "status": 6,
    }
    for _ in range(repetitions):
        start = time.perf_counter()
        model.set_sessions([*original, extra])
        model.set_sessions(original)
        times["structural_change"].append((time.perf_counter() - start) * 1000)

    # No-op and small structural changes preserve persistent view indexes.
    # Each structural iteration inserts and removes one row without a reset.
    if (
        resets.count() != 0
        or inserted.count() != repetitions
        or removed.count() != repetitions
        or changed_rows != repetitions
    ):
        raise AssertionError(
            "Unexpected session table signals during refresh benchmark: "
            f"reset={resets.count()}, inserted={inserted.count()}, "
            f"removed={removed.count()}, changed={changed_rows}"
        )
    return {
        "rows": count,
        "repetitions": repetitions,
        "model_resets": resets.count(),
        "rows_inserted_signals": inserted.count(),
        "rows_removed_signals": removed.count(),
        "changed_row_signals": changed_rows,
        "latency_ms": {
            name: {
                "p50": percentile(values, 0.50),
                "p95": percentile(values, 0.95),
                "max": round(max(values), 3),
            }
            for name, values in times.items()
        },
    }


def measure_qt_view(count: int, repetitions: int = REPETITIONS) -> dict[str, object]:
    """Measure filtering and viewport rendering with the production session model."""
    app = QApplication.instance() or QApplication([])
    sessions = session_fixtures(count)
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    proxy = QSortFilterProxyModel()
    proxy.setFilterKeyColumn(0)
    proxy.setSourceModel(model)
    view = QTableView()
    view.setModel(proxy)
    view.resize(900, 520)
    view.show()
    app.processEvents()

    filter_text = f"Synthetic {count - 1:04d}" if count else "Synthetic"
    durations = []
    filtered_rows = 0
    viewport_rendered = False
    for _ in range(repetitions):
        start = time.perf_counter()
        model.set_sessions(sessions)
        proxy.setFilterFixedString(filter_text)
        app.processEvents()
        rendered = view.viewport().grab()
        durations.append((time.perf_counter() - start) * 1000)
        filtered_rows = proxy.rowCount()
        viewport_rendered = not rendered.isNull()

    view.close()
    app.processEvents()
    return {
        "rows": count,
        "repetitions": repetitions,
        "filtered_rows": filtered_rows,
        "viewport_rendered": viewport_rendered,
        "p50_ms": percentile(durations, 0.50),
        "p95_ms": percentile(durations, 0.95),
        "max_ms": round(max(durations), 3),
    }


def measure_main_window(count: int, repetitions: int = 5) -> dict[str, object]:
    """Measure visible offscreen MainWindow startup with isolated demo data."""
    app = QApplication.instance() or QApplication([])
    sessions = session_fixtures(count)
    startup_durations = []
    filter_render_durations = []
    visible = False
    viewport_rendered = False
    filtered_rows = 0
    original_settings_path = app_module.settings_path

    with tempfile.TemporaryDirectory(prefix="mutaui-window-benchmark-") as data_dir:
        app_module.settings_path = lambda: Path(data_dir) / "settings.json"
        try:
            for _ in range(repetitions):
                window = None
                try:
                    start = time.perf_counter()
                    window = app_module.MainWindow(demo=True)
                    window.timer.stop()
                    window.metric_timer.stop()
                    window.tail_timer.stop()
                    window.refresh = lambda **_kwargs: None
                    window.refresh_resources = lambda *_args, **_kwargs: None
                    window.set_page(1)
                    window.apply_snapshot(
                        app_module.Snapshot(binary=window.client.binary, sync=sessions)
                    )
                    window.show()
                    app.processEvents()
                    startup_durations.append((time.perf_counter() - start) * 1000)
                    visible = window.isVisible()
                    filter_text = f"Synthetic {count - 1:04d}" if count else "Synthetic"
                    filter_start = time.perf_counter()
                    window.sync_search.setText(filter_text)
                    app.processEvents()
                    filtered_rows = sum(
                        not window.sync_table.isRowHidden(row)
                        for row in range(window.sync_table.model().rowCount())
                    )
                    viewport_rendered = not window.sync_table.viewport().grab().isNull()
                    filter_render_durations.append((time.perf_counter() - filter_start) * 1000)
                finally:
                    if window is not None:
                        window._allow_exit = True
                        window.close()
                        window.history.close()
                        window.deleteLater()
                        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                        app.processEvents()
        finally:
            app_module.settings_path = original_settings_path

    return {
        "rows": count,
        "repetitions": repetitions,
        "visible": visible,
        "filtered_rows": filtered_rows,
        "viewport_rendered": viewport_rendered,
        "p50_ms": percentile(startup_durations, 0.50),
        "p95_ms": percentile(startup_durations, 0.95),
        "max_ms": round(max(startup_durations), 3),
        "filter_render_p50_ms": percentile(filter_render_durations, 0.50),
        "filter_render_p95_ms": percentile(filter_render_durations, 0.95),
        "filter_render_max_ms": round(max(filter_render_durations), 3),
    }


def run_benchmark(repetitions: int = REPETITIONS) -> dict[str, object]:
    _app = QApplication.instance() or QApplication([])
    memory = psutil.virtual_memory()
    process = psutil.Process()
    rss_before = process.memory_info().rss
    results = {
        str(count): {
            **measure(count, repetitions),
            "qt_view": measure_qt_view(count, repetitions),
        }
        for count in SESSION_SIZES
    }
    refresh_cases = {
        str(count): measure_refresh_cases(count, repetitions) for count in (1000, 5000)
    }
    main_window = measure_main_window(1000, repetitions=repetitions)
    memory_after = process.memory_info()
    unique_after = process.memory_full_info().uss
    return {
        "measurement": "offscreen MainWindow startup and SessionTableModel/Qt view filter/render",
        "limits": [
            "synthetic sessions in demo mode using temporary settings and in-memory history",
            "offscreen Qt window; excludes platform compositor, installed Mutagen, and native CLI",
            "does not establish reference-hardware acceptance",
        ],
        "machine": {
            "os": platform.platform(),
            "architecture": platform.machine(),
            "cpu_model": platform.processor() or "not reported by operating system",
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "memory_total_bytes": memory.total,
            "python": platform.python_version(),
            "pyside6": pyside_version,
            "storage_type": "not detected by this benchmark",
            "process_rss_before_bytes": rss_before,
            "process_rss_after_bytes": memory_after.rss,
            "process_uss_after_bytes": unique_after,
        },
        "results": results,
        "refresh_cases": refresh_cases,
        "main_window_1000_rows": main_window,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=REPETITIONS)
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    args = parser.parse_args()
    if args.repetitions < 2:
        parser.error("--repetitions must be at least 2")
    result = run_benchmark(args.repetitions)
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
