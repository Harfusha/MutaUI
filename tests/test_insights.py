import json
from types import SimpleNamespace

from insights import AlertEngine, measurement_summary, safe_diagnostic_report, state_transitions
from monitoring import HistoryStore, Sample


def test_summary_computes_raw_statistics():
    stats = measurement_summary([{"cpu": v, "memory": v*1024} for v in (1, 2, 3, 4, 100)])
    assert stats["samples"] == 5
    assert stats["fields"]["cpu"]["avg"] == 22
    assert stats["fields"]["cpu"]["p95"] == 100
    assert stats["fields"]["cpu"]["latest"] == 100
    assert measurement_summary([])["fields"]["cpu"]["max"] == 0


def test_alert_requires_continuous_violation_and_rearms_after_recovery():
    engine = AlertEngine()
    cfg = dict(enabled_cpu=True, enabled_ram=True, cpu_limit=85,
               ram_limit_mb=512, hold_seconds=10)
    assert not engine.evaluate(90, 540*1024**2, now=1, **cfg)
    assert not engine.evaluate(90, 540*1024**2, now=9, **cfg)
    assert [alert.key for alert in engine.evaluate(90, 540*1024**2, now=11, **cfg)] == ["cpu", "ram"]
    assert not engine.evaluate(90, 540*1024**2, now=15, **cfg)
    assert not engine.evaluate(0, 0, now=16, **cfg)
    assert not engine.evaluate(90, 540*1024**2, now=17, **cfg)
    assert len(engine.evaluate(90, 540*1024**2, now=27, **cfg)) == 2


def test_spikes_do_not_trigger_alerts():
    alert = AlertEngine()
    cfg = dict(cpu_limit=75, enabled_cpu=True, hold_seconds=10)
    assert alert.evaluate(90, 0, now=0, **cfg) == []
    assert alert.evaluate(10, 0, now=8, **cfg) == []
    assert alert.evaluate(80, 0, now=10, **cfg) == []
    assert alert.evaluate(80, 0, now=19, **cfg) == []
    assert len(alert.evaluate(80, 0, now=20, **cfg)) == 1


def test_transitions_avoid_busy_active_noise():
    previous = {("sync", "a"): "active", ("sync", "b"): "paused", ("forward", "f"): "error"}
    now = {("sync", "a"): "busy", ("sync", "b"): "active", ("forward", "f"): "active", ("sync", "new"): "error"}
    assert state_transitions(previous, now) == [
        ("sync", "b", "paused", "active"), ("forward", "f", "error", "active")]


def test_safe_report_never_exports_sensitive_fields():
    secret = "top-secret.example.net"
    snapshot = SimpleNamespace(binary=r"C:\\private\\bin\\mutagen.exe", daemon=True,
        version="Mutagen version 0.18.1", registration="registered", cpu=20,
        memory=32000, processes=2, error=f"could not reach {secret}",
        sync=[dict(identifier="hidden-identifier", name="private-project",
                   alpha={"path": r"C:\\private\\repo", "host": secret, "connected": True},
                   beta={"host": secret, "connected": False}, status=6,
                   conflicts=[{"path": "private-file"}], lastError="connection error private")],
        forward=[dict(identifier="private-forward", source={"endpoint": "tcp:localhost:123"},
                      destination={"host": secret}, status=3, openConnections=4)])
    data = safe_diagnostic_report(snapshot, now=123.4)
    out = json.dumps(data)
    for sensitive in (secret, "private", "hidden-identifier", "tcp:localhost", "C:\\\\private"):
        assert sensitive not in out
    assert data["sessions"][0]["conflict_count"] == 1
    assert data["sessions"][1]["open_connections"] == 4


def test_sqlite_statistics_are_based_on_raw_samples():
    h = HistoryStore(":memory:")
    for i in range(10):
        h.add(Sample(ts=100+i, cpu=float(i)))
    st = h.statistics(hours=1, now=200)
    assert st["samples"] == 10
    assert st["fields"]["cpu"]["avg"] == 4.5
    assert st["fields"]["cpu"]["p95"] == 9
    h.close()
