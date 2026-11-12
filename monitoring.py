"""Durable local metrics and rate calculations for Mutagen Control.

All disk access is local. No telemetry is sent to an external service.
"""
from __future__ import annotations

import csv
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

METRIC_COLUMNS = (
    "cpu", "memory", "read_rate", "write_rate", "forward_out_rate",
    "forward_in_rate", "processes", "active_sessions", "problem_sessions",
)


# Remote metrics are opt-in and keyed by an SSH endpoint identifier.
# Identifiers can contain private host/user information: never include in safe reports.
REMOTE_COLUMNS = ("cpu", "mem_used", "mem_total", "agent_cpu", "agent_mem",
                  "agent_count", "net_rx_rate", "net_tx_rate", "agent_read_rate", "agent_write_rate",
                  "root_used", "root_total", "uptime_sec", "load1")


@dataclass(frozen=True)
class Sample:
    ts: float
    cpu: float = 0.0
    memory: float = 0.0
    read_rate: float = 0.0
    write_rate: float = 0.0
    forward_out_rate: float = 0.0
    forward_in_rate: float = 0.0
    processes: int = 0
    active_sessions: int = 0
    problem_sessions: int = 0


class ForwardTrafficMeter:
    """Compute bytes/sec from per-session *cumulative* forwarding counters.

    New sessions and reset counters establish a baseline instead of creating
    an artificial network spike. Results are aggregate application counters,
    not system-wide network interface traffic.
    """

    def __init__(self):
        self.previous: dict[str, tuple[float, int, int]] = {}

    def update(self, sessions: list[dict], now: float | None = None) -> tuple[float, float]:
        now = time.monotonic() if now is None else now
        current: dict[str, tuple[float, int, int]] = {}
        outgoing = incoming = 0.0
        for session in sessions:
            identifier = str(session.get("identifier") or "")
            if not identifier:
                continue
            out_total = max(0, int(session.get("totalOutboundData") or 0))
            in_total = max(0, int(session.get("totalInboundData") or 0))
            previous = self.previous.get(identifier)
            if previous and now > previous[0]:
                dt = now - previous[0]
                if out_total >= previous[1]:
                    outgoing += (out_total - previous[1]) / dt
                if in_total >= previous[2]:
                    incoming += (in_total - previous[2]) / dt
            current[identifier] = now, out_total, in_total
        self.previous = current
        return round(outgoing, 2), round(incoming, 2)


class HistoryStore:
    """SQLite time series with bounded retention and aggregated chart queries."""

    def __init__(self, path: Path | str = ":memory:", retention_hours: int = 48):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.retention_hours = retention_hours
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
        # History is replaceable measurement data; NORMAL reduces sync-to-disk
        # overhead while retaining SQLite consistency and WAL crash recovery.
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS metrics (ts REAL PRIMARY KEY, cpu REAL, memory REAL, "
                        "read_rate REAL, write_rate REAL, forward_out_rate REAL, forward_in_rate REAL, "
                        "processes INTEGER, active_sessions INTEGER, problem_sessions INTEGER)")
        self.db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                        "ts REAL NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
        self.db.execute("CREATE TABLE IF NOT EXISTS remote_metrics (host TEXT NOT NULL, ts REAL NOT NULL, "
                        "cpu REAL, mem_used REAL, mem_total REAL, agent_cpu REAL, agent_mem REAL, "
                        "agent_count INTEGER, net_rx_rate REAL, net_tx_rate REAL, "
                        "agent_read_rate REAL, agent_write_rate REAL, root_used REAL, root_total REAL, "
                        "uptime_sec REAL, load1 REAL, PRIMARY KEY (host, ts))")
        # Migration from v4 without discarding any historical metrics.
        existing_cols = {row[1] for row in self.db.execute("PRAGMA table_info(remote_metrics)")}
        for col in ("root_used", "root_total", "uptime_sec", "load1"):
            if col not in existing_cols:
                self.db.execute(f"ALTER TABLE remote_metrics ADD COLUMN {col} REAL")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_remote_ts ON remote_metrics(ts)")
        self.db.commit()
        self._last_prune = 0.0

    def add(self, sample: Sample):
        values = (sample.ts,) + tuple(getattr(sample, k) for k in METRIC_COLUMNS)
        self.db.execute("INSERT OR REPLACE INTO metrics VALUES (" + ",".join("?" for _ in values) + ")", values)
        self.db.commit()
        if sample.ts - self._last_prune > 600:
            self.prune(sample.ts)
            self._last_prune = sample.ts

    def prune(self, now: float | None = None):
        now = time.time() if now is None else now
        self.db.execute("DELETE FROM metrics WHERE ts < ?", (now - self.retention_hours * 3600,))
        self.db.execute("DELETE FROM events WHERE ts < ?", (now - 30 * 86400,))
        self.db.execute("DELETE FROM remote_metrics WHERE ts < ?", (now - self.retention_hours * 3600,))
        self.db.commit()

    def query(self, hours: float = 1.0, max_points: int = 440, now: float | None = None) -> list[dict]:
        """Return one aggregated point per interval, within the selected window."""
        hours = max(1 / 60, min(float(hours), self.retention_hours))
        max_points = max(10, min(2000, int(max_points)))
        now = time.time() if now is None else now
        interval = max(1.0, hours * 3600 / max_points)
        cols = ", ".join(f"AVG({col})" for col in METRIC_COLUMNS)
        cursor = self.db.execute(
            f"SELECT AVG(ts), {cols} FROM metrics WHERE ts >= ? AND ts <= ? "
            "GROUP BY CAST(ts / ? AS INTEGER) ORDER BY CAST(ts / ? AS INTEGER)",
            (now - hours * 3600, now, interval, interval),
        )
        return [{"ts": ts, **dict(zip(METRIC_COLUMNS, fields))} for ts, *fields in cursor]

    def statistics(self, hours: float = 1.0, now: float | None = None) -> dict:
        """Summary of raw measurements over the range (not downsampled chart points)."""
        from insights import measurement_summary
        now = time.time() if now is None else now
        hours = max(1 / 60, min(float(hours), self.retention_hours))
        cols = ", ".join(METRIC_COLUMNS)
        rows = [dict(zip(METRIC_COLUMNS, values)) for values in self.db.execute(
            f"SELECT {cols} FROM metrics WHERE ts >= ? AND ts <= ? ORDER BY ts",
            (now - hours * 3600, now))]
        return measurement_summary(rows)

    def export_csv(self, path: Path | str, hours: float = 24.0, now: float | None = None):
        """Export full-resolution samples for the selected period, not chart averages."""
        now = time.time() if now is None else now
        hours = max(1 / 60, min(float(hours), self.retention_hours))
        with open(path, "w", newline="", encoding="utf-8-sig") as target:
            writer = csv.writer(target)
            writer.writerow(("timestamp_unix",) + METRIC_COLUMNS)
            for row in self.db.execute("SELECT ts, " + ", ".join(METRIC_COLUMNS) +
                                       " FROM metrics WHERE ts >= ? AND ts <= ? ORDER BY ts", (now - hours * 3600, now)):
                writer.writerow(row)

    def add_event(self, message: str, severity: str = "info", now: float | None = None):
        now = time.time() if now is None else now
        self.db.execute("INSERT INTO events(ts, severity, message) VALUES (?,?,?)", (now, severity, message))
        self.db.commit()

    def events(self, limit: int = 500) -> list[tuple[float, str, str]]:
        return list(reversed(self.db.execute(
            "SELECT ts, severity, message FROM events ORDER BY id DESC LIMIT ?", (max(1, min(limit, 5000)),)
        ).fetchall()))

    def clear_events(self):
        self.db.execute("DELETE FROM events")
        self.db.commit()

    def add_remote(self, host: str, ts: float, data: dict):
        """Save one opt-in sample from a remote SSH endpoint."""
        values = [host, float(ts)] + [data.get(col) for col in REMOTE_COLUMNS]
        columns = ("host", "ts") + REMOTE_COLUMNS
        self.db.execute("INSERT OR REPLACE INTO remote_metrics (" + ",".join(columns) + ") VALUES (" +
                        ",".join("?" for _ in values) + ")", values)
        self.db.commit()
        if ts - self._last_prune > 600:
            self.prune(ts)
            self._last_prune = ts

    def query_remote(self, host: str, hours: float = 1.0,
                     max_points: int = 320, now: float | None = None) -> list[dict]:
        """Aggregate only a selected host's metrics, preserving NULL rates."""
        now = time.time() if now is None else now
        hours = max(1 / 60, min(float(hours), self.retention_hours))
        interval = max(1.0, hours * 3600 / max(10, min(1000, int(max_points))))
        columns = ", ".join("AVG(" + col + ")" for col in REMOTE_COLUMNS)
        cursor = self.db.execute(
            f"SELECT AVG(ts), {columns} FROM remote_metrics WHERE host=? AND ts>=? AND ts<=? "
            "GROUP BY CAST(ts / ? AS INTEGER) ORDER BY CAST(ts / ? AS INTEGER)",
            (host, now - hours * 3600, now, interval, interval),
        )
        return [{"ts": ts, **dict(zip(REMOTE_COLUMNS, values))} for ts, *values in cursor]

    def export_remote(self, path: Path | str, host: str, hours: float = 24.0):
        """Export a chosen host's raw measurements. Host strings are private."""
        after = time.time() - max(1 / 60, min(float(hours), self.retention_hours)) * 3600
        with open(path, "w", newline="", encoding="utf-8-sig") as target:
            writer = csv.writer(target)
            writer.writerow(("host", "timestamp_unix") + REMOTE_COLUMNS)
            cursor = self.db.execute(
                "SELECT host, ts, " + ",".join(REMOTE_COLUMNS) +
                " FROM remote_metrics WHERE host=? AND ts>=? ORDER BY ts", (host, after))
            writer.writerows(cursor)

    def close(self):
        self.db.close()


def statistics_from_file(path: Path | str, hours: float = 1.0,
                         retention_hours: int = 48, now: float | None = None) -> dict:
    """Compute exact raw-sample statistics on a separate SQLite read connection.

    Intended for a QThreadPool worker so that 48h of samples never forces a
    percentile sort on the GUI thread. Read-only URI cannot change the DB.
    """
    from insights import measurement_summary
    now = time.time() if now is None else now
    hours = max(1 / 60, min(float(hours), retention_hours))
    path = Path(path)
    if str(path) == ':memory:':
        raise ValueError('In-memory database must be read via its originating connection')
    uri = path.resolve().as_uri() + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        names = ', '.join(METRIC_COLUMNS)
        rows = [dict(zip(METRIC_COLUMNS, values)) for values in connection.execute(
            f'SELECT {names} FROM metrics WHERE ts >= ? AND ts <= ? ORDER BY ts',
            (now - hours * 3600, now))]
        return measurement_summary(rows)
    finally:
        connection.close()


def query_metrics_from_file(path: Path | str, hours: float = 1.0,
                            max_points: int = 440, retention_hours: int = 48,
                            now: float | None = None) -> list[dict]:
    """Read chart bins on a separate, read-only SQLite connection.

    Heavy GROUP BY queries for 48 hours of 1 Hz telemetry must not freeze the
    Qt thread. This is intentionally the same query as HistoryStore.query.
    """
    path = Path(path)
    if str(path) == ':memory:':
        raise ValueError('Use HistoryStore.query for an in-memory demo database')
    now = time.time() if now is None else now
    hours = max(1 / 60, min(float(hours), retention_hours))
    max_points = max(10, min(2000, int(max_points)))
    interval = max(1.0, hours * 3600 / max_points)
    uri = path.resolve().as_uri() + '?mode=ro'
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        cols = ', '.join(f'AVG({col})' for col in METRIC_COLUMNS)
        cursor = connection.execute(
            f'SELECT AVG(ts), {cols} FROM metrics WHERE ts >= ? AND ts <= ? '
            'GROUP BY CAST(ts / ? AS INTEGER) ORDER BY CAST(ts / ? AS INTEGER)',
            (now - hours * 3600, now, interval, interval))
        return [{'ts': ts, **dict(zip(METRIC_COLUMNS, values))} for ts, *values in cursor]
    finally:
        connection.close()
