import time

from monitoring import HistoryStore


def test_remote_history_does_not_mix_servers_and_exports_csv(tmp_path):
    store = HistoryStore(tmp_path / "metrics.sqlite3")
    now = time.time()
    data = dict(cpu=13, mem_used=250, mem_total=1000, agent_cpu=None,
                agent_mem=50, agent_count=1, net_rx_rate=None,
                net_tx_rate=None, agent_read_rate=10, agent_write_rate=30)
    store.add_remote("deploy@server:22", now-5, data)
    store.add_remote("bob@another:22", now-5, {**data, "cpu": 88})
    rows = store.query_remote("deploy@server:22", hours=.5, now=now)
    assert len(rows) == 1 and rows[0]["cpu"] == 13
    assert rows[0]["agent_cpu"] is None
    path = tmp_path / "remote.csv"
    store.export_remote(path, "deploy@server:22")
    output = path.read_text(encoding="utf-8-sig")
    assert "deploy@server:22" in output
    assert "bob@another:22" not in output
    store.close()
