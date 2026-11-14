"""Ensure background writes never require a Qt event loop."""

import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

import async_recorder
from async_recorder import AsyncRecorder
from monitoring import HistoryStore, Sample


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_pending": 0},
        {"batch_size": 0},
        {"flush_seconds": 0},
    ],
)
def test_rejects_invalid_queue_configuration(tmp_path, kwargs):
    with pytest.raises(ValueError, match="Invalid recorder capacity"):
        AsyncRecorder(tmp_path / "invalid.db", **kwargs)


def test_rejects_in_memory_database():
    with pytest.raises(ValueError, match="file-backed database"):
        AsyncRecorder(":memory:")


def test_reports_database_startup_failure(monkeypatch, tmp_path):
    import async_recorder

    def fail_open(*args, **kwargs):
        raise OSError("database unavailable")

    monkeypatch.setattr(async_recorder, "HistoryStore", fail_open)
    recorder = AsyncRecorder(tmp_path / "unavailable.db")
    assert recorder.wait_idle(timeout=1)
    assert recorder.last_error == "database unavailable"
    assert recorder.close()


def test_startup_failure_counts_and_discards_queued_records(monkeypatch, tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def fail_after_submit(*_args, **_kwargs):
        entered.set()
        assert release.wait(timeout=2)
        raise OSError("database startup failed")

    monkeypatch.setattr(async_recorder, "HistoryStore", fail_after_submit)
    recorder = AsyncRecorder(tmp_path / "startup-queue.db")
    assert entered.wait(timeout=1)
    try:
        assert recorder.add_event("queued before startup failure")
    finally:
        release.set()

    assert recorder.wait_idle(timeout=1)
    assert recorder.failed == 1
    assert recorder.last_error == "database startup failed"
    assert recorder.close()


def test_wait_idle_times_out_while_writer_is_busy(tmp_path):
    recorder = AsyncRecorder(tmp_path / "busy.db")
    with recorder._condition:
        recorder._busy = True
    assert not recorder.wait_idle(timeout=0.01)
    with recorder._condition:
        recorder._busy = False
        recorder._condition.notify_all()
    assert recorder.close()


def test_writes_metrics_and_events_then_flushes_on_close(tmp_path):
    path = tmp_path / "metrics.db"
    recorder = AsyncRecorder(path, batch_size=16, flush_seconds=0.01)
    t = time.time()
    for i in range(70):
        assert recorder.add(Sample(ts=t + i * 0.001, cpu=i, memory=i * 4096))
    assert recorder.add_event("start", "info", now=t)
    assert recorder.add_remote("host", t, {"cpu": 19.0, "agent_count": 1})
    assert recorder.close()
    store = HistoryStore(path)
    assert store.db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 70
    assert store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert store.db.execute("SELECT COUNT(*) FROM remote_metrics").fetchone()[0] == 1
    store.close()


def test_bounded_and_nonblocking_even_when_backlogged(tmp_path):
    path = tmp_path / "bounded.db"
    recorder = AsyncRecorder(path, max_pending=8, batch_size=2)
    t = time.time()
    started = time.perf_counter()
    for i in range(500):
        recorder.add(Sample(ts=t + i * 0.001, cpu=i))
    assert time.perf_counter() - started < 2.0
    assert recorder.close()
    store = HistoryStore(path)
    assert store.db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] <= 500
    assert recorder.dropped >= 1
    store.close()


def test_close_is_idempotent_and_disallows_new_data(tmp_path):
    recorder = AsyncRecorder(tmp_path / "closed.db")
    assert recorder.close()
    assert recorder.close()
    assert not recorder.add(Sample(ts=time.time()))


def test_event_priority_when_queue_is_full(tmp_path):
    recorder = AsyncRecorder(tmp_path / "priority.db", max_pending=3, batch_size=1)
    for i in range(300):
        recorder.add(Sample(ts=time.time() + i, cpu=i))
    assert recorder.add_event("priority")
    assert recorder.close()
    store = HistoryStore(tmp_path / "priority.db")
    assert any(message == "priority" for _, _, message in store.events())
    store.close()


def test_full_event_queue_drops_oldest_when_no_measurement_can_be_evicted(tmp_path):
    path = tmp_path / "events-only.db"
    recorder = AsyncRecorder(path, max_pending=2, batch_size=8)
    with recorder._condition:
        recorder._queue.extend(
            [
                ("event", (1.0, "info", "oldest")),
                ("event", (2.0, "info", "retained")),
            ]
        )
        assert recorder.add_event("newest", now=3.0)
        assert recorder.dropped == 1

    assert recorder.close()
    store = HistoryStore(path)
    assert [message for _, _, message in store.events()] == ["retained", "newest"]
    store.close()


def test_clearing_events_preserves_following_new_event(tmp_path):
    path = tmp_path / "history.db"
    recorder = AsyncRecorder(path)
    recorder.add_event("old")
    recorder.clear_events()
    recorder.add_event("new")
    assert recorder.close()
    store = HistoryStore(path)
    assert [message for _, _, message in store.events()] == ["new"]
    store.close()


def test_unknown_internal_record_kind_is_reported(tmp_path):
    recorder = AsyncRecorder(tmp_path / "unknown-kind.db", batch_size=1)
    with recorder._condition:
        recorder._queue.append(("unknown", None))
        recorder._condition.notify_all()

    assert recorder.wait_idle(timeout=1)
    assert recorder.failed == 1
    assert recorder.last_error == "Unknown async recorder record kind: 'unknown'"
    assert recorder.close()


def test_database_write_failure_is_counted_and_close_remains_nonblocking(tmp_path, monkeypatch):
    class BrokenDatabase:
        def __enter__(self):
            raise sqlite3.OperationalError("disk full")

        def __exit__(self, *_args):
            return False

    class BrokenStore:
        db = BrokenDatabase()

        def __init__(self, *_args, **_kwargs):
            self.closed = False

        def close(self):
            self.closed = True

    stores = []

    def create_store(*args, **kwargs):
        store = BrokenStore(*args, **kwargs)
        stores.append(store)
        return store

    monkeypatch.setattr(async_recorder, "HistoryStore", create_store)
    recorder = AsyncRecorder(tmp_path / "broken.db", batch_size=1)
    assert recorder.add_event("will fail")

    assert recorder.wait_idle(timeout=1)
    assert recorder.failed == 1
    assert recorder.last_error == "disk full"
    assert recorder.close()
    assert stores[0].closed


def test_idle_wakeup_and_batch_coalescing_timeout_paths(tmp_path, monkeypatch):
    class TrackingCondition(threading.Condition):
        def __init__(self):
            super().__init__()
            self.waited_twice = threading.Event()
            self.wait_count = 0

        def wait(self, timeout=None):
            self.wait_count += 1
            if self.wait_count >= 2:
                self.waited_twice.set()
            return super().wait(timeout)

    monkeypatch.setattr(
        async_recorder,
        "threading",
        SimpleNamespace(Condition=TrackingCondition, Thread=threading.Thread),
    )
    idle = AsyncRecorder(tmp_path / "idle.db", flush_seconds=0.005)
    assert idle._condition.waited_twice.wait(1)
    assert idle.close()

    recorder = AsyncRecorder(tmp_path / "coalesce.db", batch_size=4, flush_seconds=0.01)
    assert recorder.add_event("one record")
    assert recorder.wait_idle(timeout=1)
    assert recorder.close()


def test_clear_event_batch_runs_prune_after_retention_interval(tmp_path, monkeypatch):
    class Database:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            return None

    class Store:
        db = Database()

        def __init__(self, *_args, **_kwargs):
            self.pruned = False

        def prune(self):
            self.pruned = True

        def close(self):
            pass

    stores = []

    def create_store(*args, **kwargs):
        store = Store(*args, **kwargs)
        stores.append(store)
        return store

    ticks = iter((0.0, 601.0, 1202.0, 1803.0))
    monkeypatch.setattr(async_recorder, "HistoryStore", create_store)
    monkeypatch.setattr(
        async_recorder,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks), time=time.time),
    )
    recorder = AsyncRecorder(tmp_path / "prune.db", batch_size=2)
    with recorder._condition:
        recorder._queue.extend(
            [
                ("event", (1.0, "info", "old")),
                ("clear_events", None),
            ]
        )
    assert recorder.close()

    assert stores[0].pruned
