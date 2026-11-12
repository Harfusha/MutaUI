"""No Qt/Mutagen dependency: local metrics and rate handling."""
from pathlib import Path
import csv
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from monitoring import HistoryStore, ForwardTrafficMeter, Sample


def session(name, outbound, inbound):
    return dict(identifier=name, totalOutboundData=outbound, totalInboundData=inbound)


def test_forward_rates_and_first_baseline():
    tracker = ForwardTrafficMeter()
    assert tracker.update([session('a', 1000, 500)], now=1) == (0, 0)
    assert tracker.update([session('a', 1500, 1500)], now=3) == (250, 500)
    assert tracker.update([session('a', 1800, 1700), session('b', 9000, 8000)], now=4) == (300, 200)
    assert tracker.update([session('a', 5, 4), session('b', 9400, 8300)], now=6) == (200, 150)
    assert tracker.update([], now=8) == (0, 0)
    assert tracker.update([session('a', 100, 400)], now=9) == (0, 0)


def test_store_persistence_aggregate_and_export(tmp_path):
    filepath = tmp_path / 'metrics.sqlite3'
    store = HistoryStore(filepath)
    store.add(Sample(ts=1000, cpu=20, memory=100, read_rate=25, processes=1, active_sessions=1))
    store.add(Sample(ts=1001, cpu=40, memory=200, read_rate=50, processes=2, active_sessions=2))
    store.add(Sample(ts=1002, cpu=60, memory=300, read_rate=75, processes=3, active_sessions=3))
    store.add_event('Started', now=1000)
    assert store.events() == [(1000, 'info', 'Started')]
    store.close()
    store = HistoryStore(filepath)
    rows = store.query(hours=1, now=1010, max_points=10)
    assert rows
    assert max(r['cpu'] for r in rows) >= 40
    assert all(r['memory'] >= 100 for r in rows)
    path = tmp_path / 'metrics.csv'
    store.export_csv(path, hours=1, now=1010)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        export = list(csv.DictReader(stream))
    assert len(export) == 3
    assert export[0]['cpu'] == '20.0'
    assert 'forward_out_rate' in export[0]
    store.clear_events()
    assert store.events() == []
    store.close()


def test_retention_and_query_bounding(tmp_path):
    store = HistoryStore(tmp_path / 'm.sqlite', retention_hours=48)
    store.add(Sample(ts=0, cpu=100))
    store.add(Sample(ts=180001, cpu=25))
    store.prune(180001)
    assert len(store.query(hours=48, now=180005)) == 1
    for i in range(1000):
        store.add(Sample(ts=180100 + i, cpu=i / 10))
    assert len(store.query(hours=1, max_points=30, now=181100)) <= 32
    store.close()


def test_process_sampler_calculates_deltas_and_excludes_other_apps(monkeypatch):
    import mutagen_client
    from types import SimpleNamespace

    class Process:
        pid = 42
        info = {"name": "mutagen.exe", "memory_info": SimpleNamespace(rss=123456)}
        total = 3
        read = 100
        write = 200
        def create_time(self): return 10
        def cpu_times(self): return SimpleNamespace(user=self.total, system=0)
        def io_counters(self): return SimpleNamespace(read_bytes=self.read, write_bytes=self.write)

    process = Process()
    monkeypatch.setattr(mutagen_client.psutil, 'process_iter', lambda fields: [process])
    import time
    timestamps = iter([10, 12])
    monkeypatch.setattr(time, 'monotonic', lambda: next(timestamps))
    sampler = mutagen_client.ProcessSampler()
    first = sampler.sample_detailed()
    assert first['cpu'] == 0 and first['memory'] == 123456 and first['processes'] == 1
    process.total += 1
    process.read += 400
    process.write += 1000
    second = sampler.sample_detailed()
    assert second['cpu'] == 50
    assert second['read_rate'] == 200 and second['write_rate'] == 500
    assert sampler.last_processes[0]['pid'] == 42


def test_separate_chart_connection_returns_same_bins(tmp_path):
    import time
    from monitoring import query_metrics_from_file, HistoryStore, Sample
    path = tmp_path / 'chart.sqlite3'
    store = HistoryStore(path)
    now = time.time()
    for i in range(300):
        store.add(Sample(ts=now - 300 + i, cpu=(i % 11)*5, memory=100+i))
    first = store.query(hours=.5, max_points=25, now=now)
    second = query_metrics_from_file(path, hours=.5, max_points=25, now=now)
    assert first == second
    store.close()
