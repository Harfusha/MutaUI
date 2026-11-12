"""Upgrading from v4 must preserve all prior historical measurements."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitoring import HistoryStore


def test_v4_remote_schema_migrates_without_data_loss(tmp_path):
    path = tmp_path / 'metrics.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE remote_metrics (
            host TEXT NOT NULL, ts REAL NOT NULL, cpu REAL, mem_used REAL,
            mem_total REAL, agent_cpu REAL, agent_mem REAL, agent_count INTEGER,
            net_rx_rate REAL, net_tx_rate REAL, agent_read_rate REAL,
            agent_write_rate REAL, PRIMARY KEY(host,ts))''')
        db.execute('INSERT INTO remote_metrics (host,ts,cpu) VALUES (?,?,?)', ('user@server:22', 1000, 20))
    store = HistoryStore(path)
    result = store.query_remote('user@server:22', hours=1, now=1010)
    assert result and result[0]['cpu'] == 20
    assert result[0]['root_total'] is None
    store.add_remote('user@server:22', 1001, dict(cpu=30, root_total=2000,
                      root_used=1000, uptime_sec=3600, load1=1.8))
    result = store.query_remote('user@server:22', hours=1, now=1010, max_points=1000)
    assert sum(r['root_used'] or 0 for r in result) == 1000
    store.close()

