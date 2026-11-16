from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QWidget

from benchmarks.session_table_benchmark import (
    SESSION_SIZES,
    measure,
    measure_main_window,
    measure_qt_view,
    measure_refresh_cases,
    percentile,
    session_fixtures,
)


def _forbid_global_qt_pumps(monkeypatch):
    def reject_process_events(*_args, **_kwargs):
        raise AssertionError("Benchmark must not process the global Qt event queue")

    def reject_unscoped_posted_events(receiver=None, *_args, **_kwargs):
        if receiver is None:
            raise AssertionError("Benchmark must not send posted events to every Qt object")

    monkeypatch.setattr(QApplication, "processEvents", reject_process_events)
    monkeypatch.setattr(QCoreApplication, "sendPostedEvents", reject_unscoped_posted_events)


def test_fixtures_cover_requested_sizes_without_external_paths():
    assert SESSION_SIZES == (0, 1, 10, 100, 500, 1000, 5000)
    fixtures = session_fixtures(2)
    assert [item["identifier"] for item in fixtures] == ["synthetic-0", "synthetic-1"]
    assert all(item["alpha"]["path"].startswith("C:/alpha/") for item in fixtures)


def test_percentile_selects_bounded_order_statistic():
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.50) == 3.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0


def test_model_benchmark_reports_latency_distribution():
    result = measure(1, repetitions=3)
    assert result["rows"] == 1
    assert result["repetitions"] == 3
    assert 0 <= result["p50_ms"] <= result["max_ms"]
    assert result["p50_ms"] <= result["p95_ms"] <= result["max_ms"]


def test_qt_view_benchmark_filters_and_renders_the_session_model(monkeypatch):
    _forbid_global_qt_pumps(monkeypatch)
    result = measure_qt_view(1000, repetitions=3)

    assert result["rows"] == 1000
    assert result["filtered_rows"] == 1
    assert result["viewport_rendered"] is True
    assert result["repetitions"] == 3
    assert 0 <= result["p50_ms"] <= result["p95_ms"] <= result["max_ms"]


def test_qt_view_benchmark_does_not_process_an_outer_loop_deferred_delete():
    QApplication.instance() or QApplication([])
    pending = QWidget()
    deleted = []
    pending.destroyed.connect(lambda: deleted.append(True))
    nested_loop = QEventLoop()

    def defer_delete_and_exit():
        pending.deleteLater()
        nested_loop.quit()

    QTimer.singleShot(0, defer_delete_and_exit)
    nested_loop.exec()
    assert deleted == []

    measure_qt_view(1, repetitions=1)

    assert deleted == []


def test_main_window_benchmark_does_not_process_an_outer_loop_deferred_delete():
    QApplication.instance() or QApplication([])
    pending = QWidget()
    deleted = []
    pending.destroyed.connect(lambda: deleted.append(True))
    nested_loop = QEventLoop()

    def defer_delete_and_exit():
        pending.deleteLater()
        nested_loop.quit()

    QTimer.singleShot(0, defer_delete_and_exit)
    nested_loop.exec()
    assert deleted == []

    measure_main_window(1, repetitions=1)

    assert deleted == []


def test_main_window_benchmark_uses_demo_data_and_isolated_settings(monkeypatch):
    _forbid_global_qt_pumps(monkeypatch)
    result = measure_main_window(5, repetitions=2)

    assert result["rows"] == 5
    assert result["repetitions"] == 2
    assert result["visible"] is True
    assert result["filtered_rows"] == 1
    assert result["viewport_rendered"] is True
    assert 0 <= result["p50_ms"] <= result["p95_ms"] <= result["max_ms"]
    assert 0 <= result["filter_render_p50_ms"] <= result["filter_render_p95_ms"]


def test_session_table_refresh_canary_distinguishes_noop_and_changes():
    result = measure_refresh_cases(10, repetitions=3)
    assert result["rows"] == 10
    assert result["repetitions"] == 3
    assert result["model_resets"] == 0
    assert result["rows_inserted_signals"] == 3
    assert result["rows_removed_signals"] == 3
    assert result["changed_row_signals"] == 3
    for case in ("unchanged", "one_row_changed", "structural_change"):
        timings = result["latency_ms"][case]
        assert 0 <= timings["p50"] <= timings["p95"] <= timings["max"]
