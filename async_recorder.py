"""Non-blocking SQLite event/metric writer for the GUI.

The UI never waits for SQLite commits: inserts are coalesced and performed by
one dedicated thread. A separate connection is used for GUI reads; SQLite WAL
provides consistent committed snapshots. Queue is bounded to cap memory usage.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from monitoring import METRIC_COLUMNS, REMOTE_COLUMNS, HistoryStore, Sample


class AsyncRecorder:
    """A single-writer, bounded, ordered, best-effort metrics/event recorder.

    On a clean close, the queue is drained. During forced process termination,
    only not-yet-committed measurements can be lost. `dropped` counts any
    records discarded because the producer outran the database.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_pending: int = 4096,
        batch_size: int = 64,
        flush_seconds: float = 0.4,
        retention_hours: int = 48,
    ):
        if str(path) == ":memory:":
            raise ValueError("Use a file-backed database for the background recorder")
        if max_pending < 1 or batch_size < 1 or flush_seconds <= 0:
            raise ValueError("Invalid recorder capacity or flush interval")
        self.path = str(path)
        self.retention_hours = retention_hours
        self.max_pending = max_pending
        self.batch_size = batch_size
        self.flush_seconds = flush_seconds
        self._queue: deque[tuple[str, Any]] = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._busy = False
        self.dropped = 0
        self.dropped_metrics = 0
        self.dropped_events = 0
        self.failed = 0
        self.failed_metrics = 0
        self.failed_events = 0
        self.last_error = ""
        self._thread = threading.Thread(target=self._run, daemon=True, name="MutagenHistoryWriter")
        self._thread.start()

    def _submit(self, kind: str, value: Any) -> bool:
        with self._condition:
            if self._closed:
                return False
            if len(self._queue) >= self.max_pending:
                # Prioritize high-severity operator events over metrics and info events.
                is_urgent_event = (
                    kind == "event"
                    and isinstance(value, tuple)
                    and len(value) >= 2
                    and value[1] in ("error", "warning")
                )
                metric_idx = next(
                    (i for i, (k, _) in enumerate(self._queue) if k in ("metric", "remote")),
                    None,
                )
                if metric_idx is not None:
                    # Drop a raw metric sample first to preserve events
                    del self._queue[metric_idx]
                    self.dropped += 1
                    self.dropped_metrics += 1
                elif is_urgent_event:
                    # An urgent event can displace an info event or oldest item
                    info_idx = next(
                        (
                            i
                            for i, (k, v) in enumerate(self._queue)
                            if k == "event"
                            and isinstance(v, tuple)
                            and len(v) >= 2
                            and v[1] == "info"
                        ),
                        None,
                    )
                    victim = info_idx if info_idx is not None else 0
                    del self._queue[victim]
                    self.dropped += 1
                    self.dropped_events += 1
                elif kind == "event":
                    # An info event can displace another info event, but cannot displace urgent events
                    info_idx = next(
                        (
                            i
                            for i, (k, v) in enumerate(self._queue)
                            if k == "event"
                            and isinstance(v, tuple)
                            and len(v) >= 2
                            and v[1] == "info"
                        ),
                        None,
                    )
                    if info_idx is not None:
                        del self._queue[info_idx]
                        self.dropped += 1
                        self.dropped_events += 1
                    else:
                        # Only urgent events in queue; reject incoming non-urgent event
                        self.dropped += 1
                        self.dropped_events += 1
                        return False
                else:
                    # Metric with no metrics left to evict; reject metric to preserve events
                    self.dropped += 1
                    self.dropped_metrics += 1
                    return False
            self._queue.append((kind, value))
            self._condition.notify()
            return True

    def add(self, sample: Sample) -> bool:
        return self._submit("metric", sample)

    def add_event(self, message: str, severity: str = "info", now: float | None = None) -> bool:
        return self._submit("event", (time.time() if now is None else now, severity, message))

    def add_remote(self, host: str, ts: float, data: dict[str, Any]) -> bool:
        return self._submit("remote", (host, float(ts), dict(data)))

    def clear_events(self) -> bool:
        return self._submit("clear_events", None)

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Testing/shutdown aid, not called during normal GUI rendering."""
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._queue or self._busy:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def close(self, timeout: float = 10.0) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        self._thread.join(timeout)
        alive = self._thread.is_alive()
        if alive:
            with self._condition:
                if self._queue:
                    lost_count = len(self._queue)
                    self.failed += lost_count
                    for k, _ in self._queue:
                        if k in ("metric", "remote"):
                            self.failed_metrics += 1
                        elif k == "event":
                            self.failed_events += 1
                    self.last_error = f"Recorder timed out during shutdown; {lost_count} pending items not flushed."
        return not alive

    def _run(self) -> None:
        store = None
        try:
            store = HistoryStore(self.path, retention_hours=self.retention_hours)
            metric_columns = ("ts", *METRIC_COLUMNS)
            last_prune = time.monotonic()
            while True:
                with self._condition:
                    if not self._queue and not self._closed:
                        self._condition.wait(self.flush_seconds)
                    if not self._queue and self._closed:
                        return
                    if not self._queue:
                        continue
                    # Coalesce a short burst into one transaction. This avoids
                    # a fsync/commit for each line of a noisy debug session.
                    until = time.monotonic() + self.flush_seconds
                    while not self._closed and len(self._queue) < self.batch_size:
                        left = until - time.monotonic()
                        if left <= 0:
                            break
                        self._condition.wait(left)
                    batch = [
                        self._queue.popleft() for _ in range(min(self.batch_size, len(self._queue)))
                    ]
                    self._busy = True
                try:
                    with store.db:
                        for kind, value in batch:
                            if kind == "metric":
                                fields = (value.ts,) + tuple(
                                    getattr(value, col) for col in METRIC_COLUMNS
                                )
                                store.db.execute(
                                    f"INSERT OR REPLACE INTO metrics ({', '.join(metric_columns)}) VALUES ("
                                    + ",".join("?" for _ in fields)
                                    + ")",
                                    fields,
                                )
                            elif kind == "remote":
                                host, ts, data = value
                                fields = (host, ts) + tuple(data.get(col) for col in REMOTE_COLUMNS)
                                columns = ("host", "ts") + REMOTE_COLUMNS
                                store.db.execute(
                                    "INSERT OR REPLACE INTO remote_metrics ("
                                    + ",".join(columns)
                                    + ") VALUES ("
                                    + ",".join("?" for _ in fields)
                                    + ")",
                                    fields,
                                )
                            elif kind == "event":
                                store.db.execute(
                                    "INSERT INTO events(ts, severity, message) VALUES (?,?,?)",
                                    value,
                                )
                            elif kind == "clear_events":
                                store.db.execute("DELETE FROM events")
                            else:
                                raise ValueError(f"Unknown async recorder record kind: {kind!r}")
                    if time.monotonic() - last_prune >= 600:
                        store.prune()
                        last_prune = time.monotonic()
                except (sqlite3.Error, OSError, ValueError) as exc:
                    self.failed += len(batch)
                    for k, _ in batch:
                        if k in ("metric", "remote"):
                            self.failed_metrics += 1
                        elif k == "event":
                            self.failed_events += 1
                    self.last_error = str(exc)[:250]
                finally:
                    with self._condition:
                        self._busy = False
                        self._condition.notify_all()
        except (sqlite3.Error, OSError) as exc:
            self.last_error = str(exc)[:250]
            with self._condition:
                lost_count = len(self._queue)
                self.failed += lost_count
                for k, _ in self._queue:
                    if k in ("metric", "remote"):
                        self.failed_metrics += 1
                    elif k == "event":
                        self.failed_events += 1
                self._queue.clear()
                self._busy = False
                self._condition.notify_all()
        finally:
            if store is not None:
                store.close()
