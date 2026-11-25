from __future__ import annotations

import itertools
import weakref
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

_WORKER_TASK_IDS = itertools.count(1)


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class WorkerDispatcher(QObject):
    """Single GUI-thread signal bridge shared by background tasks of one window."""

    completed = Signal(int, bool, object)


class Worker(QRunnable):
    def __init__(self, func: Callable[[], Any]) -> None:
        super().__init__()
        self.func: Callable[[], Any] | None = func
        self.signals: WorkerSignals | None = WorkerSignals()

    def run(self) -> None:
        func = self.func
        signals = self.signals
        self.func = None
        if func is None or signals is None:
            return
        try:
            signals.result.emit(func())
        except Exception as exc:
            signals.error.emit(str(exc))
        finally:
            func = None
            signals.finished.emit()


def _run_background_task(
    task_id: int,
    work: Callable[[], Any],
    dispatcher_ref: weakref.ref[WorkerDispatcher],
) -> None:
    is_error = False
    payload: Any = None
    try:
        payload = work()
    except Exception as exc:
        is_error = True
        payload = str(exc)
    finally:
        work = None  # type: ignore[assignment]
    dispatcher = dispatcher_ref()
    if dispatcher is not None:
        with suppress(RuntimeError):
            dispatcher.completed.emit(task_id, is_error, payload)


def _host_resolver(host: Any) -> tuple[Callable[[], Any], bool]:
    try:
        return weakref.ref(host), True
    except TypeError:
        return (lambda: host), False


def _ensure_host_dict(host: Any, attr: str) -> dict[int, Any]:
    existing = getattr(host, attr, None)
    if isinstance(existing, dict):
        return existing
    created: dict[int, Any] = {}
    setattr(host, attr, created)
    return created


def deliver_worker_completion(
    host: Any,
    task_id: int,
    is_error: bool,
    payload: object,
) -> None:
    """Deliver a finished background task result/error on the GUI thread and free callbacks."""
    host.workers.discard(task_id)
    callbacks = getattr(host, "_worker_callbacks", None)
    entry = callbacks.pop(task_id, None) if isinstance(callbacks, dict) else None
    if entry is not None:
        on_result, on_error, on_done = entry
        del entry
        try:
            if not host._shutdown_pending:
                if is_error:
                    (on_error or host.report_error)(str(payload))
                elif on_result is not None:
                    on_result(payload)
        finally:
            try:
                if on_done is not None and not host._shutdown_pending:
                    on_done()
            finally:
                on_result = None
                on_error = None
                on_done = None
                payload = None
    if getattr(host, "_worker_dispatcher_ephemeral", False) and not host.workers:
        cleanup_worker_dispatcher(host)
    if host._shutdown_pending and not host.workers:
        QTimer.singleShot(0, host.close)


def ensure_worker_dispatcher(
    host: Any,
) -> tuple[WorkerDispatcher, dict[int, tuple[Any, Any, Any]]]:
    """Lazily initialize the single per-host WorkerDispatcher without strong reference cycles."""
    callbacks = _ensure_host_dict(host, "_worker_callbacks")
    dispatcher = getattr(host, "_worker_dispatcher", None)
    if dispatcher is None:
        dispatcher = WorkerDispatcher()
        resolve_host, is_weakrefable = _host_resolver(host)

        def _on_completed(task_id: int, is_error: bool, payload: object) -> None:
            resolved_host = resolve_host()
            if resolved_host is not None:
                deliver_worker_completion(resolved_host, task_id, is_error, payload)

        connection = dispatcher.completed.connect(_on_completed)
        host._worker_dispatcher = dispatcher
        host._worker_dispatcher_connection = connection
        host._worker_dispatcher_ephemeral = not is_weakrefable
    return dispatcher, callbacks


def cleanup_worker_dispatcher(host: Any) -> None:
    """Disconnect and delete the host's WorkerDispatcher and clear callback maps."""
    connection = getattr(host, "_worker_dispatcher_connection", None)
    host._worker_dispatcher_connection = None
    if connection is not None:
        with suppress(RuntimeError, TypeError):
            QObject.disconnect(connection)
    dispatcher = getattr(host, "_worker_dispatcher", None)
    host._worker_dispatcher = None
    if dispatcher is not None:
        with suppress(RuntimeError):
            dispatcher.deleteLater()
    callbacks = getattr(host, "_worker_callbacks", None)
    if isinstance(callbacks, dict):
        callbacks.clear()


def _submit_custom_pool_worker(
    host: Any,
    task_id: int,
    work: Callable[[], Any],
    on_result: Callable[[Any], None] | None,
    on_error: Callable[[str], None] | None,
    on_done: Callable[[], None] | None,
) -> None:
    worker = Worker(work)
    signals = worker.signals
    assert signals is not None
    callbacks = _ensure_host_dict(host, "_worker_callbacks")
    registry = _ensure_host_dict(host, "_legacy_worker_registry")
    host.workers.add(task_id)
    callbacks[task_id] = (on_result, on_error, on_done)
    resolve_host, _ = _host_resolver(host)

    def _cleanup_signals() -> None:
        entry = registry.pop(task_id, None)
        if entry is None:
            return
        done_worker, done_signals, connections = entry
        done_worker.func = None
        done_worker.signals = None
        for conn in connections:
            with suppress(RuntimeError, TypeError):
                QObject.disconnect(conn)
        connections.clear()
        with suppress(RuntimeError):
            done_signals.deleteLater()

    def _deliver(is_error: bool, payload: object) -> None:
        resolved_host = resolve_host()
        if resolved_host is not None:
            deliver_worker_completion(resolved_host, task_id, is_error, payload)
        _cleanup_signals()

    def _finished() -> None:
        _cleanup_signals()
        resolved_host = resolve_host()
        if resolved_host is not None and task_id in resolved_host.workers:
            deliver_worker_completion(resolved_host, task_id, False, None)

    conns = [
        signals.result.connect(lambda result: _deliver(False, result)),
        signals.error.connect(lambda message: _deliver(True, message)),
        signals.finished.connect(_finished),
    ]
    registry[task_id] = (worker, signals, conns)
    try:
        host.pool.start(worker)
    except Exception:
        callbacks.pop(task_id, None)
        host.workers.discard(task_id)
        _cleanup_signals()
        raise


def submit_background_task(
    host: Any,
    work: Callable[[], Any],
    on_result: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Submit background work without retaining completed Worker/WorkerSignals instances."""
    if host._shutdown_pending:
        return
    task_id = next(_WORKER_TASK_IDS)
    if isinstance(host.pool, QThreadPool):
        dispatcher, callbacks = ensure_worker_dispatcher(host)
        dispatcher_ref = weakref.ref(dispatcher)
        host.workers.add(task_id)
        callbacks[task_id] = (on_result, on_error, on_done)

        def _execute() -> None:
            _run_background_task(task_id, work, dispatcher_ref)

        try:
            host.pool.start(_execute)
        except Exception:
            callbacks.pop(task_id, None)
            host.workers.discard(task_id)
            raise
        return

    _submit_custom_pool_worker(host, task_id, work, on_result, on_error, on_done)
