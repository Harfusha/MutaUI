"""Ensure background writes never require a Qt event loop."""
import sqlite3
import time

from async_recorder import AsyncRecorder
from monitoring import HistoryStore, Sample


def test_writes_metrics_and_events_then_flushes_on_close(tmp_path):
    path = tmp_path / 'metrics.db'
    recorder = AsyncRecorder(path, batch_size=16, flush_seconds=.01)
    t = time.time()
    for i in range(70):
        assert recorder.add(Sample(ts=t + i * .001, cpu=i, memory=i * 4096))
    assert recorder.add_event('start', 'info', now=t)
    assert recorder.add_remote('host', t, {'cpu': 19.0, 'agent_count': 1})
    assert recorder.close()
    store = HistoryStore(path)
    assert store.db.execute('SELECT COUNT(*) FROM metrics').fetchone()[0] == 70
    assert store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 1
    assert store.db.execute('SELECT COUNT(*) FROM remote_metrics').fetchone()[0] == 1
    store.close()


def test_bounded_and_nonblocking_even_when_backlogged(tmp_path):
    path = tmp_path / 'bounded.db'
    recorder = AsyncRecorder(path, max_pending=8, batch_size=2)
    t = time.time()
    started = time.perf_counter()
    for i in range(500):
        recorder.add(Sample(ts=t + i*.001, cpu=i))
    assert time.perf_counter() - started < 2.0
    assert recorder.close()
    store = HistoryStore(path)
    assert store.db.execute('SELECT COUNT(*) FROM metrics').fetchone()[0] <= 500
    assert recorder.dropped >= 1
    store.close()


def test_close_is_idempotent_and_disallows_new_data(tmp_path):
    recorder = AsyncRecorder(tmp_path / 'closed.db')
    assert recorder.close()
    assert recorder.close()
    assert not recorder.add(Sample(ts=time.time()))


def test_event_priority_when_queue_is_full(tmp_path):
    recorder = AsyncRecorder(tmp_path / 'priority.db', max_pending=3, batch_size=1)
    for i in range(300):
        recorder.add(Sample(ts=time.time() + i, cpu=i))
    assert recorder.add_event('priority')
    assert recorder.close()
    store = HistoryStore(tmp_path / 'priority.db')
    assert any(message == 'priority' for _,_,message in store.events())
    store.close()


def test_clearing_events_preserves_following_new_event(tmp_path):
    path = tmp_path / 'history.db'
    recorder = AsyncRecorder(path)
    recorder.add_event('old')
    recorder.clear_events()
    recorder.add_event('new')
    assert recorder.close()
    store = HistoryStore(path)
    assert [message for _,_,message in store.events()] == ['new']
    store.close()
