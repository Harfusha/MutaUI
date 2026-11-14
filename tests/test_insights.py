import json
from datetime import UTC, datetime
from types import SimpleNamespace

from insights import (
    AlertEngine,
    _measured_number,
    _number,
    _safe_age_seconds,
    local_self_check,
    measurement_summary,
    safe_diagnostic_report,
    session_log_report,
    state_transitions,
)
from monitoring import HistoryStore, Sample


def test_local_self_check_checks_paths_database_and_runtime_without_writes(tmp_path):
    app_file = tmp_path / "app.py"
    app_file.write_text("# local app", encoding="utf-8")
    history = HistoryStore(tmp_path / "history.sqlite3")
    try:
        report = local_self_check(
            app_path=app_file,
            settings_path=tmp_path / "settings.json",
            history=history,
            qt_version="6.8.3",
            mutagen_version="Mutagen 0.18.1",
        )
    finally:
        history.close()
    assert report["schema"] == "mutagen-control-self-check-v1"
    assert report["remote_writes"] is False
    assert {check["status"] for check in report["checks"].values()} == {"ok"}


def test_local_self_check_reports_missing_cli_and_broken_database(tmp_path):
    history = HistoryStore()
    history.close()
    report = local_self_check(
        app_path=tmp_path / "missing.py",
        settings_path=tmp_path / "missing" / "settings.json",
        history=history,
        qt_version="",
        mutagen_version="",
    )
    assert report["checks"]["application_path"]["status"] == "warning"
    assert report["checks"]["settings_path"]["status"] == "warning"
    assert report["checks"]["history_database"]["status"] == "error"
    assert report["checks"]["mutagen_cli"]["status"] == "warning"


def test_summary_computes_raw_statistics():
    stats = measurement_summary([{"cpu": v, "memory": v * 1024} for v in (1, 2, 3, 4, 100)])
    assert stats["samples"] == 5
    assert stats["fields"]["cpu"]["avg"] == 22
    assert stats["fields"]["cpu"]["p95"] == 100
    assert stats["fields"]["cpu"]["latest"] == 100
    assert measurement_summary([])["fields"]["cpu"]["max"] is None


def test_summary_ignores_missing_metrics_instead_of_reporting_zero():
    stats = measurement_summary(
        [
            {"cpu": None, "forward_out_rate": None},
            {"cpu": 12.0, "forward_out_rate": 80.0},
            {"cpu": None, "forward_out_rate": None},
        ]
    )

    assert stats["fields"]["cpu"] == {
        "min": 12.0,
        "avg": 12.0,
        "p95": 12.0,
        "max": 12.0,
        "latest": None,
        "measured_samples": 1,
    }
    assert stats["fields"]["forward_out_rate"]["latest"] is None
    assert stats["fields"]["forward_out_rate"]["avg"] == 80.0


def test_alert_requires_continuous_violation_and_rearms_after_recovery():
    engine = AlertEngine()
    cfg = dict(enabled_cpu=True, enabled_ram=True, cpu_limit=85, ram_limit_mb=512, hold_seconds=10)
    assert not engine.evaluate(90, 540 * 1024**2, now=1, **cfg)
    assert not engine.evaluate(90, 540 * 1024**2, now=9, **cfg)
    assert [alert.key for alert in engine.evaluate(90, 540 * 1024**2, now=11, **cfg)] == [
        "cpu",
        "ram",
    ]
    assert not engine.evaluate(90, 540 * 1024**2, now=15, **cfg)
    assert not engine.evaluate(0, 0, now=16, **cfg)
    assert not engine.evaluate(90, 540 * 1024**2, now=17, **cfg)
    assert len(engine.evaluate(90, 540 * 1024**2, now=27, **cfg)) == 2


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
    now = {
        ("sync", "a"): "busy",
        ("sync", "b"): "active",
        ("forward", "f"): "active",
        ("sync", "new"): "error",
    }
    assert state_transitions(previous, now) == [
        ("sync", "b", "paused", "active"),
        ("forward", "f", "error", "active"),
    ]


def test_safe_report_never_exports_sensitive_fields():
    sensitive_host = "top-secret.example.net"
    sensitive_values = (
        sensitive_host,
        "private-ssh-user",
        "PRIVATE-KEY-CONTENT-FIXTURE",
        "EXAMPLE_DOTENV_VALUE=fixture-secret",
    )
    snapshot = SimpleNamespace(
        binary=r"C:\\private\\bin\\mutagen.exe",
        daemon=True,
        version="Mutagen version 0.18.1",
        registration="registered",
        cpu=20,
        memory=32000,
        processes=2,
        error=f"could not reach {sensitive_host}",
        sync=[
            dict(
                identifier="hidden-identifier",
                name="private-project",
                alpha={
                    "path": r"C:\\private\\repo",
                    "host": sensitive_host,
                    "username": "private-ssh-user",
                    "privateKey": "PRIVATE-KEY-CONTENT-FIXTURE",
                    "dotenv": "EXAMPLE_DOTENV_VALUE=fixture-secret",
                    "connected": True,
                },
                beta={"host": sensitive_host, "connected": False},
                status=6,
                conflicts=[{"path": "private-file"}],
                lastError="connection error private",
            )
        ],
        forward=[
            dict(
                identifier="private-forward",
                source={"endpoint": "tcp:localhost:123"},
                destination={"host": sensitive_host},
                status=3,
                openConnections=4,
            )
        ],
    )
    data = safe_diagnostic_report(snapshot, now=123.4)
    out = json.dumps(data)
    for sensitive in (
        *sensitive_values,
        "private",
        "hidden-identifier",
        "tcp:localhost",
        "C:\\\\private",
    ):
        assert sensitive not in out
    assert data["sessions"][0]["conflict_count"] == 1
    assert data["sessions"][1]["open_connections"] == 4


def test_safe_report_keeps_unobserved_resource_metrics_missing():
    snapshot = SimpleNamespace(
        binary="",
        daemon=False,
        version="",
        registration="unknown",
        cpu=0,
        memory=0,
        processes=0,
        resource_observed_at=None,
        sync=[],
        forward=[],
    )

    data = safe_diagnostic_report(snapshot, now=123.4)

    assert data["local_processes"] is None
    assert data["cpu_percent_total"] is None
    assert data["memory_bytes_total"] is None


def test_safe_report_includes_environment_freshness_and_only_safe_problem_codes():
    snapshot = SimpleNamespace(
        binary=r"C:\\private\\mutagen.exe",
        daemon=True,
        version="Mutagen version 0.18.1",
        registration="registered",
        cpu=20,
        memory=32000,
        processes=2,
        error="secret host details",
        sessions_stale=False,
        sync_observed_at=datetime.fromtimestamp(190, UTC),
        forward_observed_at=None,
        resource_observed_at=datetime.fromtimestamp(180, UTC),
        sync=[],
        forward=[],
    )

    data = safe_diagnostic_report(
        snapshot,
        now=200,
        application_version="8.2.0",
        qt_version="6.8.3",
        problem_codes=("ssh_authentication", r"C:\\private\\host"),
        build_id="../private",
    )

    assert data["application_version"] == "8.2.0"
    assert data["runtime"]["qt_version"] == "6.8.3"
    assert data["freshness"] == {
        "sessions_stale": False,
        "sync_age_seconds": 10,
        "forward_age_seconds": None,
        "resource_age_seconds": 20,
    }
    assert data["problem_codes"] == ["ssh_authentication"]
    assert data["ci_build_id"] is None
    payload = json.dumps(data)
    assert "private" not in payload
    assert "host details" not in payload


def test_session_log_report_excludes_raw_details_by_default():
    events = [(10.5, "warning", "private host /srv/private user alice")]
    log_lines = ["ssh private.example: key token-secret"]

    report = session_log_report(events, log_lines, now=20)
    payload = json.dumps(report)

    assert report["event_count"] == 1
    assert report["monitored_line_count"] == 1
    assert report["events"] == [{"timestamp_unix": 10.5, "severity": "warning"}]
    assert report["monitored_log_lines"] == []
    for secret in ("private host", "/srv/private", "alice", "private.example", "token-secret"):
        assert secret not in payload


def test_session_log_report_sensitivity_controls_are_independent():
    events = [(10.5, "warning", "private host /srv/private user alice")]
    log_lines = ["ssh private.example: key token-secret"]

    event_details = session_log_report(events, log_lines, now=20, include_event_messages=True)
    assert event_details["events"][0]["message"] == events[0][2]
    assert event_details["monitored_log_lines"] == []

    log_details = session_log_report(events, log_lines, now=20, include_monitored_log_lines=True)
    assert log_details["events"] == [{"timestamp_unix": 10.5, "severity": "warning"}]
    assert log_details["monitored_log_lines"] == log_lines


def test_session_log_report_caps_records_and_marks_truncation():
    events = [(float(i), "info", f"event-{i}") for i in range(501)]
    log_lines = [f"line-{i}" for i in range(1201)]

    report = session_log_report(
        events, log_lines, now=2000, include_event_messages=True, include_monitored_log_lines=True
    )

    assert report["event_count"] == 501
    assert report["event_count_capped"] is True
    assert report["events"][0]["message"] == "event-1"
    assert report["events"][-1]["message"] == "event-500"
    assert report["monitored_line_count"] == 1201
    assert report["monitored_line_count_capped"] is True
    assert len(report["monitored_log_lines"]) == 1200
    assert report["monitored_log_lines"][0] == "line-1"


def test_sqlite_statistics_are_based_on_raw_samples():
    h = HistoryStore(":memory:")
    for i in range(10):
        h.add(Sample(ts=100 + i, cpu=float(i)))
    st = h.statistics(hours=1, now=200)
    assert st["samples"] == 10
    assert st["fields"]["cpu"]["avg"] == 4.5
    assert st["fields"]["cpu"]["p95"] == 9
    h.close()


def test_number_and_safe_age_seconds_handle_invalid_or_overflow_inputs():
    assert _number("invalid") == 0.0
    assert _number(float("inf")) == 0.0
    assert _number(float("nan")) == 0.0
    assert _measured_number("invalid") is None
    assert _measured_number(float("inf")) is None
    assert _measured_number(float("nan")) is None
    assert _safe_age_seconds("not-a-datetime", 100.0) is None

    class BadDate(datetime):
        def timestamp(self):
            raise OverflowError("overflow")

    assert _safe_age_seconds(BadDate(2026, 1, 1), 100.0) is None
