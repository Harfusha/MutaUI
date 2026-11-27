"""Regression tests for background worker ownership, cleanup, and handle stability (M90)."""

from __future__ import annotations

import gc
import os
import threading
import weakref
from datetime import UTC, datetime
from types import SimpleNamespace

import psutil
import PySide6  # noqa: F401
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

import app as app_module
from mutaui.domain.models import Endpoint, SessionIdentity, SessionSnapshot
from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog, _InspectionSignals
from mutaui.ui.worker import (
    Worker,
    WorkerDispatcher,
    WorkerSignals,
    _run_background_task,
    cleanup_worker_dispatcher,
    deliver_worker_completion,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _TaskPayload:
    """Unique heap object per task to verify zero closure/argument retention."""

    def __init__(self, index: int) -> None:
        self.index = index


def _drain_qt_and_gc(qapp: QApplication, pool: QThreadPool) -> None:
    assert pool.waitForDone(10_000)
    qapp.processEvents()
    gc.collect()
    qapp.processEvents()
    gc.collect()


def _process_handle_count() -> int | None:
    proc = psutil.Process()
    if hasattr(proc, "num_handles"):
        return int(proc.num_handles())
    if hasattr(proc, "num_fds"):
        return int(proc.num_fds())
    return None


def test_submit_releases_workers_signals_payloads_and_handles_across_batches(
    qapp: QApplication,
) -> None:
    pool = QThreadPool()
    pool.setMaxThreadCount(4)
    host = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=pool,
        report_error=lambda _msg: None,
        close=lambda: None,
    )

    # Warm up pool threads before measuring baseline handle count.
    warmup_done = 0

    def _warmup_done() -> None:
        nonlocal warmup_done
        warmup_done += 1

    for _ in range(8):
        app_module.MainWindow.submit(host, lambda: 1, on_done=_warmup_done)
    _drain_qt_and_gc(qapp, pool)
    assert warmup_done == 8

    baseline_handles = _process_handle_count()
    payload_refs: list[weakref.ref[_TaskPayload]] = []
    completed = 0
    errors = 0

    def _on_result(_value: object) -> None:
        nonlocal completed
        completed += 1

    def _on_error(_msg: str) -> None:
        nonlocal errors
        errors += 1

    for idx in range(600):
        token = _TaskPayload(idx)
        payload_refs.append(weakref.ref(token))
        if idx % 10 == 0:
            app_module.MainWindow.submit(
                host,
                lambda t=token: (_ for _ in ()).throw(RuntimeError(f"fail-{t.index}")),
                on_result=_on_result,
                on_error=_on_error,
            )
        else:
            app_module.MainWindow.submit(
                host,
                lambda t=token: t.index,
                on_result=_on_result,
                on_error=_on_error,
            )
    del token

    _drain_qt_and_gc(qapp, pool)

    assert completed == 540
    assert errors == 60
    assert host.workers == set()
    live_workers = sum(1 for obj in gc.get_objects() if isinstance(obj, Worker))
    live_signals = sum(1 for obj in gc.get_objects() if isinstance(obj, WorkerSignals))
    live_dispatchers = sum(1 for obj in gc.get_objects() if isinstance(obj, WorkerDispatcher))
    live_payloads = sum(1 for ref in payload_refs if ref() is not None)
    assert live_workers == 0
    assert live_signals == 0
    assert live_dispatchers <= 1
    assert live_payloads == 0

    after_handles = _process_handle_count()
    if baseline_handles is not None and after_handles is not None:
        assert after_handles - baseline_handles < 32


def test_submit_shutdown_ignores_late_callbacks_and_schedules_close(qapp: QApplication) -> None:
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    gate = threading.Event()
    started = threading.Event()
    events: list[str] = []
    closed: list[bool] = []
    host = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=pool,
        report_error=lambda msg: events.append(f"report:{msg}"),
        close=lambda: closed.append(True),
    )

    def _slow_work() -> str:
        started.set()
        gate.wait(timeout=5.0)
        return "done"

    app_module.MainWindow.submit(
        host,
        _slow_work,
        on_result=lambda val: events.append(f"result:{val}"),
        on_error=lambda err: events.append(f"error:{err}"),
        on_done=lambda: events.append("done"),
    )
    assert started.wait(timeout=5.0)
    assert len(host.workers) == 1

    # Simulate shutdown requested while worker is still running.
    host._shutdown_pending = True
    app_module.MainWindow.submit(
        host,
        lambda: events.append("should_not_run"),
        on_result=lambda _v: events.append("late_result"),
    )
    gate.set()
    _drain_qt_and_gc(qapp, pool)

    assert host.workers == set()
    assert events == []
    assert closed == [True]


def test_submit_cleans_up_when_pool_start_raises(qapp: QApplication) -> None:
    class _FailingPool:
        def start(self, _runnable: object) -> None:
            raise RuntimeError("pool saturated")

    host = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=_FailingPool(),
        report_error=lambda _msg: None,
        close=lambda: None,
    )
    try:
        app_module.MainWindow.submit(host, lambda: 1, on_result=lambda _v: None)
    except RuntimeError as exc:
        assert "pool saturated" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError from failing pool")
    assert host.workers == set()


def test_mainwindow_close_after_worker_burst_leaves_no_live_workers(
    tmp_path, monkeypatch, qapp: QApplication
) -> None:
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    win = app_module.MainWindow(demo=True)
    win.timer.stop()
    win.metric_timer.stop()
    win.tail_timer.stop()

    results: list[int] = []
    for idx in range(50):
        win.submit(lambda i=idx: i, on_result=results.append)
    _drain_qt_and_gc(qapp, win.pool)

    assert len(results) == 50
    assert win.workers == set()

    win._allow_exit = True
    event = QCloseEvent()
    win.closeEvent(event)
    assert event.isAccepted()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    gc.collect()

    assert sum(1 for obj in gc.get_objects() if isinstance(obj, Worker)) == 0
    assert sum(1 for obj in gc.get_objects() if isinstance(obj, WorkerSignals)) == 0
    assert sum(1 for obj in gc.get_objects() if isinstance(obj, WorkerDispatcher)) == 0


def test_submit_cleans_up_when_qthreadpool_start_raises(qapp: QApplication) -> None:
    class _FailingQtPool(QThreadPool):
        def start(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("qt pool failed")

    host = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=_FailingQtPool(),
        report_error=lambda _msg: None,
        close=lambda: None,
    )
    with pytest.raises(RuntimeError, match="qt pool failed"):
        app_module.MainWindow.submit(host, lambda: 1, on_result=lambda _v: None)
    assert host.workers == set()
    cleanup_worker_dispatcher(host)


def test_submit_custom_pool_fallback_and_cleanup(qapp: QApplication) -> None:
    class _SyncWorkerPool:
        def start(self, runnable: object) -> None:
            runnable.run()  # type: ignore[attr-defined]

    results: list[object] = []
    errors: list[str] = []
    done_count = 0

    def _inc_done() -> None:
        nonlocal done_count
        done_count += 1

    host = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=_SyncWorkerPool(),
        report_error=errors.append,
        close=lambda: None,
    )
    app_module.MainWindow.submit(host, lambda: "ok", on_result=results.append, on_done=_inc_done)
    app_module.MainWindow.submit(
        host,
        lambda: (_ for _ in ()).throw(RuntimeError("bad")),
        on_done=_inc_done,
    )
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    assert results == ["ok"]
    assert errors == ["bad"]
    assert done_count == 2
    assert host.workers == set()
    assert sum(1 for obj in gc.get_objects() if isinstance(obj, Worker)) == 0
    assert sum(1 for obj in gc.get_objects() if isinstance(obj, WorkerSignals)) == 0


def test_worker_second_run_and_background_helper_branches(qapp: QApplication) -> None:
    w = Worker(lambda: 7)
    w.run()
    assert w.func is None
    w.run()  # no-op when func is already cleared

    dispatcher = WorkerDispatcher()
    received: list[tuple[int, bool, object]] = []
    dispatcher.completed.connect(lambda tid, err, payload: received.append((tid, err, payload)))
    disp_ref = weakref.ref(dispatcher)
    _run_background_task(11, lambda: "ok", disp_ref)
    _run_background_task(12, lambda: (_ for _ in ()).throw(RuntimeError("err")), disp_ref)
    qapp.processEvents()
    assert received == [(11, False, "ok"), (12, True, "err")]

    del dispatcher
    gc.collect()
    assert disp_ref() is None
    _run_background_task(13, lambda: "dropped", disp_ref)


def test_custom_pool_failure_and_empty_cleanup(qapp: QApplication) -> None:
    class _RaisingPool:
        def start(self, _runnable: object) -> None:
            raise RuntimeError("custom boom")

    host = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=_RaisingPool(),
        report_error=lambda _msg: None,
        close=lambda: None,
    )
    with pytest.raises(RuntimeError, match="custom boom"):
        app_module.MainWindow.submit(host, lambda: 1, on_result=lambda _v: None)
    assert host.workers == set()
    cleanup_worker_dispatcher(host)
    deliver_worker_completion(host, 999999, False, None)

    class _SignalsOnlyFinishPool:
        def start(self, runnable: object) -> None:
            runnable.signals.finished.emit()  # type: ignore[attr-defined]

    done_flags: list[bool] = []
    host_finish = SimpleNamespace(
        workers=set(),
        _shutdown_pending=False,
        pool=_SignalsOnlyFinishPool(),
        report_error=lambda _msg: None,
        close=lambda: None,
    )
    app_module.MainWindow.submit(
        host_finish,
        lambda: 1,
        on_done=lambda: done_flags.append(True),
    )
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    assert host_finish.workers == set()
    assert done_flags == [True]


def test_conflict_inspector_task_cleans_up_signals_and_request(tmp_path, monkeypatch, qapp) -> None:
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    ssh = Endpoint("ssh", "alice@example:/srv", host="example", user="alice", path="/srv")
    local = Endpoint("local", str(tmp_path), path=str(tmp_path))
    snap = SessionSnapshot(
        identity=SessionIdentity("sync", "sync-1", "sync-1"),
        native_config={},
        alpha_or_source=local,
        beta_or_destination=ssh,
        state="conflicts",
        conflicts=({"root": "src/main.py"},),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 24, tzinfo=UTC),
    )
    dialog = ConflictInspectorDialog((snap,), audit_path=tmp_path / "audit.jsonl")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("/tmp/key", ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)
    monkeypatch.setattr(dialog._inspection_pool, "start", lambda _task: None)

    gc.collect()
    baseline_signals = sum(1 for obj in gc.get_objects() if isinstance(obj, _InspectionSignals))
    dialog._inspect_selected_remote("beta")
    task = dialog._inspection_task
    assert task is not None
    sig_ref = weakref.ref(task.signals)
    dialog._inspection_completed(None, RuntimeError("boom"))
    assert dialog._inspection_task is None
    assert task.request is None
    assert task.signals is None
    del task
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    gc.collect()
    assert sig_ref() is None
    assert (
        sum(1 for obj in gc.get_objects() if isinstance(obj, _InspectionSignals))
        <= baseline_signals
    )
    dialog.close()


def test_worker_clears_callable_after_run_and_error(qapp: QApplication) -> None:
    token_ok = _TaskPayload(1)
    ref_ok = weakref.ref(token_ok)
    w_ok = Worker(lambda t=token_ok: t.index)
    del token_ok
    w_ok.run()
    assert w_ok.func is None
    gc.collect()
    assert ref_ok() is None

    token_err = _TaskPayload(2)
    ref_err = weakref.ref(token_err)
    w_err = Worker(lambda t=token_err: (_ for _ in ()).throw(ValueError(str(t.index))))
    del token_err
    w_err.run()
    assert w_err.func is None
    gc.collect()
    assert ref_err() is None
