"""No Qt/Mutagen dependency: local metrics and rate handling."""

import csv
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring import (
    ForwardTrafficMeter,
    HistoryStore,
    Sample,
    query_metrics_from_file,
    statistics_from_file,
)


def session(name, outbound, inbound):
    return dict(identifier=name, totalOutboundData=outbound, totalInboundData=inbound)


def test_forward_rates_and_first_baseline():
    tracker = ForwardTrafficMeter()
    assert tracker.update([session("a", 1000, 500)], now=1) == (0, 0)
    assert tracker.update([session("a", 1500, 1500)], now=3) == (250, 500)
    assert tracker.update([session("a", 1800, 1700), session("b", 9000, 8000)], now=4) == (300, 200)
    assert tracker.update([session("a", 5, 4), session("b", 9400, 8300)], now=6) == (200, 150)
    assert tracker.update([], now=8) == (0, 0)
    assert tracker.update([session("a", 100, 400)], now=9) == (0, 0)


def test_forward_rates_ignore_counter_updates_without_elapsed_time():
    tracker = ForwardTrafficMeter()
    assert tracker.update([session("session", 100, 200)], now=5) == (0, 0)
    assert tracker.update([session("session", 500, 700)], now=5) == (0, 0)


def test_forward_rates_skip_sessions_without_an_identifier():
    tracker = ForwardTrafficMeter()

    assert tracker.update([{"totalOutboundData": 100, "totalInboundData": 200}], now=5) == (
        0,
        0,
    )
    assert tracker.previous == {}


def test_store_persistence_aggregate_and_export(tmp_path):
    filepath = tmp_path / "metrics.sqlite3"
    store = HistoryStore(filepath)
    store.add(Sample(ts=1000, cpu=20, memory=100, read_rate=25, processes=1, active_sessions=1))
    store.add(Sample(ts=1001, cpu=40, memory=200, read_rate=50, processes=2, active_sessions=2))
    store.add(Sample(ts=1002, cpu=60, memory=300, read_rate=75, processes=3, active_sessions=3))
    store.add_event("Started", now=1000)
    assert store.events() == [(1000, "info", "Started")]
    store.close()
    store = HistoryStore(filepath)
    rows = store.query(hours=1, now=1010, max_points=10)
    assert rows
    assert max(r["cpu"] for r in rows) >= 40
    assert all(r["memory"] >= 100 for r in rows)
    path = tmp_path / "metrics.csv"
    store.export_csv(path, hours=1, now=1010)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        export = list(csv.DictReader(stream))
    assert len(export) == 3
    assert export[0]["cpu"] == "20.0"
    assert "forward_out_rate" in export[0]
    store.clear_events()
    assert store.events() == []
    store.close()


def test_settings_and_history_recover_after_process_crash(tmp_path):
    from settings import load_settings

    repo_root = Path(__file__).resolve().parents[1]
    code = """
import os
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, str(Path(sys.argv[1]) / "src"))
from monitoring import HistoryStore, Sample
from settings import DEFAULT_SETTINGS, write_settings
root = Path(sys.argv[2])
write_settings(root / "settings.json", {**DEFAULT_SETTINGS, "theme": "dark"})
(root / "settings.json").write_bytes(b"{")
store = HistoryStore(root / "metrics.sqlite3")
store.add(Sample(ts=1000, cpu=20, memory=100, read_rate=25, processes=1, active_sessions=1))
store.db.execute("BEGIN IMMEDIATE")
store.db.execute(
    "INSERT INTO metrics VALUES (?,?,?,?,?,?,?,?,?,?)",
    (1001, 99, 999, 0, 0, 0, 0, 1, 1, 0),
)
(root / "crashed").write_text("ready", encoding="ascii")
os._exit(23)
"""

    result = subprocess.run(  # noqa: S603 - fixed in-test Python crash fixture
        [sys.executable, "-c", code, str(repo_root), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 23, result.stderr
    assert (tmp_path / "crashed").read_text(encoding="ascii") == "ready"
    settings = load_settings(tmp_path / "settings.json")
    assert settings.values["theme"] == "dark"
    assert any("last valid settings backup" in warning.lower() for warning in settings.warnings)
    corrupt_backups = list(tmp_path.glob("settings.json.corrupt.*.bak"))
    assert len(corrupt_backups) == 1
    assert corrupt_backups[0].read_bytes() == b"{"

    store = HistoryStore(tmp_path / "metrics.sqlite3")
    assert store.db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    rows = store.db.execute("SELECT ts, cpu FROM metrics ORDER BY ts").fetchall()
    assert rows == [(1000.0, 20.0)]
    store.close()


def test_unmeasured_sample_fields_remain_missing_in_history_and_csv(tmp_path):
    store = HistoryStore(tmp_path / "missing-metrics.sqlite3")
    store.add(Sample(ts=1000))

    rows = store.query(hours=1, now=1010, max_points=10)
    assert rows[0]["cpu"] is None
    assert rows[0]["memory"] is None
    assert rows[0]["forward_out_rate"] is None

    path = tmp_path / "missing-metrics.csv"
    store.export_csv(path, hours=1, now=1010)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["cpu"] == ""
    assert row["memory"] == ""
    assert row["forward_out_rate"] == ""
    store.close()


def test_retention_and_query_bounding(tmp_path):
    store = HistoryStore(tmp_path / "m.sqlite", retention_hours=48)
    store.add(Sample(ts=0, cpu=100))
    store.add(Sample(ts=180001, cpu=25))
    store.prune(180001)
    assert len(store.query(hours=48, now=180005)) == 1
    for i in range(1000):
        store.add(Sample(ts=180100 + i, cpu=i / 10))
    assert len(store.query(hours=1, max_points=30, now=181100)) <= 32
    store.close()


def test_process_sampler_calculates_deltas_and_excludes_other_apps(monkeypatch):
    from types import SimpleNamespace

    import mutagen_client

    class Process:
        pid = 42
        info = {"name": "mutagen.exe", "memory_info": SimpleNamespace(rss=123456)}
        total = 3
        read = 100
        write = 200

        def create_time(self):
            return 10

        def cpu_times(self):
            return SimpleNamespace(user=self.total, system=0)

        def io_counters(self):
            return SimpleNamespace(read_bytes=self.read, write_bytes=self.write)

    process = Process()
    monkeypatch.setattr(mutagen_client.psutil, "process_iter", lambda fields: [process])
    import time

    timestamps = iter([10, 12])
    monkeypatch.setattr(time, "monotonic", lambda: next(timestamps))
    sampler = mutagen_client.ProcessSampler()
    first = sampler.sample_detailed()
    assert first["cpu"] == 0 and first["memory"] == 123456 and first["processes"] == 1
    process.total += 1
    process.read += 400
    process.write += 1000
    second = sampler.sample_detailed()
    assert second["cpu"] == 50
    assert second["read_rate"] == 200 and second["write_rate"] == 500
    assert sampler.last_processes[0]["pid"] == 42


def test_separate_chart_connection_returns_same_bins(tmp_path):
    import time

    from monitoring import HistoryStore, Sample, query_metrics_from_file

    path = tmp_path / "chart.sqlite3"
    store = HistoryStore(path)
    now = time.time()
    for i in range(300):
        store.add(Sample(ts=now - 300 + i, cpu=(i % 11) * 5, memory=100 + i))
    first = store.query(hours=0.5, max_points=25, now=now)
    second = query_metrics_from_file(path, hours=0.5, max_points=25, now=now)
    assert first == second
    store.close()


def test_file_statistics_and_chart_queries_clamp_ranges_and_reject_memory_databases(tmp_path):
    path = tmp_path / "statistics.sqlite3"
    store = HistoryStore(path)
    store.add(Sample(ts=1000, cpu=20, memory=100))
    store.add(Sample(ts=1001, cpu=40, memory=200))
    store.close()

    summary = statistics_from_file(path, hours=1000, retention_hours=48, now=1010)
    assert summary
    assert query_metrics_from_file(path, hours=0, max_points=1, now=1010)
    assert query_metrics_from_file(path, hours=1000, max_points=5000, now=1010)
    with pytest.raises(ValueError, match="In-memory database"):
        statistics_from_file(":memory:")
    with pytest.raises(ValueError, match="HistoryStore.query"):
        query_metrics_from_file(":memory:")
