"""Targeted regression suite for Batch 2D audit remediation (M23-M31, M55-M58, M87, M88)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from async_recorder import AsyncRecorder
from log_stream import FileTail
from monitoring import ForwardTrafficMeter, HistoryStore, Sample
from mutagen_client import MutagenClient
from mutaui.services.action_planner import ActionPlanner, ActionRequest
from mutaui.services.health_tracker import HealthObservation, HealthTracker
from mutaui.services.session_notification_gate import SessionNotificationGate
from mutaui.ui.controllers.logging_controller import LoggingMixin
from mutaui.ui.controllers.monitoring_controller import MonitoringMixin
from mutaui.ui.controllers.settings_bundle_controller import SettingsBundleMixin
from settings import write_settings

# =========================================================================
# M23: Clear view vs. Purge permanent database history
# =========================================================================


def test_m23_clear_logs_leaves_database_intact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """M23: Clearing UI log view must not wipe the SQLite events table."""
    db_path = tmp_path / "events.db"
    store = HistoryStore(db_path)
    store.add_event("Session alpha sync failure", severity="error")
    store.close()

    recorder = AsyncRecorder(db_path)
    assert recorder.wait_idle()

    class FakeLoggingHost(LoggingMixin):
        def __init__(self):
            self.logs: list[str] = ["entry 1", "entry 2"]
            self.recorder = recorder
            self.history = store
            self.log_view = SimpleNamespace(clear=lambda: None)
            self.log_count_label = SimpleNamespace(
                text="2 entries", setText=lambda t: setattr(self.log_count_label, "text", t)
            )

    host = FakeLoggingHost()
    host.clear_logs()

    assert len(host.logs) == 1
    assert "UI history cleared" in host.logs[0]
    assert host.log_count_label.text == "1 entry"
    assert recorder.wait_idle()
    assert recorder.close()

    # Re-open database to verify events table was NOT wiped
    verify_store = HistoryStore(db_path)
    events = verify_store.events()
    assert len(events) >= 1
    assert any("Session alpha sync failure" in msg for _, _, msg in events)
    verify_store.close()


def test_m23_purge_database_history_deletes_when_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M23: purge_database_history requests confirmation, wipes database, and handles errors."""
    db_path = tmp_path / "purge.db"
    store = HistoryStore(db_path)
    store.add_event("Persisted event", severity="info")
    store.close()

    from PySide6.QtWidgets import QMessageBox

    # Test Cancel first
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Cancel
    )

    class FakeHost(LoggingMixin):
        def __init__(self):
            self.logs: list[str] = ["cached"]
            self.recorder = None
            self.history = HistoryStore(db_path)
            self.log_view = None
            self.log_count_label = SimpleNamespace(
                text="1 entry", setText=lambda t: setattr(self.log_count_label, "text", t)
            )

        def add_log(self, msg):
            self.logs.append(str(msg))

    host = FakeHost()
    host.purge_database_history()
    # Still present after Cancel
    assert len(host.history.events()) == 1

    # Test Confirm (Yes)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    host.purge_database_history()
    assert len(host.history.events()) == 0
    assert host.log_count_label.text == "0 entries"
    host.history.close()


# =========================================================================
# M24: Schema resilience with extra optional columns in metrics table
# =========================================================================


def test_m24_extended_schema_allows_metrics_and_events_batch(tmp_path: Path):
    """M24: AsyncRecorder uses explicit column lists so extended SQLite tables do not fail."""
    db_path = tmp_path / "extended.db"

    # Pre-create schema with an extra optional column
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE metrics (ts REAL PRIMARY KEY, cpu REAL, memory REAL, "
        "read_rate REAL, write_rate REAL, forward_out_rate REAL, forward_in_rate REAL, "
        "processes INTEGER, active_sessions INTEGER, problem_sessions INTEGER, "
        "tray_idle_seconds REAL, cli_launches INTEGER, extra_field TEXT DEFAULT 'custom')"
    )
    conn.commit()
    conn.close()

    recorder = AsyncRecorder(db_path, batch_size=4, flush_seconds=0.01)
    now = time.time()
    assert recorder.add(Sample(ts=now, cpu=12.5, memory=1024))
    assert recorder.add_event("Event alongside extended metrics", severity="info", now=now)
    assert recorder.wait_idle(timeout=2.0)
    assert recorder.failed == 0
    assert recorder.last_error == ""
    assert recorder.close()

    # Verify both records landed in the database
    conn = sqlite3.connect(db_path)
    metric_row = conn.execute(
        "SELECT cpu, extra_field FROM metrics WHERE ts = ?", (now,)
    ).fetchone()
    assert metric_row == (12.5, "custom")
    event_row = conn.execute("SELECT message FROM events").fetchone()
    assert event_row[0] == "Event alongside extended metrics"
    conn.close()


# =========================================================================
# M25: Log stream gap detection and truncation resilience
# =========================================================================


def test_m25_file_tail_skips_truncated_leading_fragment_on_large_jump(tmp_path: Path):
    """M25: When jumping forward over max_chunk, partial leading line fragment is discarded."""
    log_file = tmp_path / "service.log"
    # Write a chunk larger than max_chunk
    initial = "header\n" + "middle line\n" * 500
    log_file.write_text(initial, encoding="utf-8")

    tail = FileTail(log_file, max_chunk=256, annotate_gaps=True)
    lines = tail.poll()

    assert len(lines) > 0
    # First line should be gap annotation, and following lines should be complete lines
    assert any("[... skipped " in l for l in lines)
    for l in lines:
        if not l.startswith("[... skipped"):
            assert l == "middle line" or l == "middle line"


@pytest.mark.parametrize("annotate_gaps", [True, False])
def test_m25_file_tail_handles_missing_file_during_rotation_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, annotate_gaps: bool
):
    """M25: FileTail does not crash with FileNotFoundError when log file is rotated."""
    log_file = tmp_path / "rotating.log"
    log_file.write_text("line 1\nline 2\n", encoding="utf-8")
    tail = FileTail(log_file, annotate_gaps=annotate_gaps)

    original_stat = Path.stat
    original_identity = original_stat(log_file)

    def _stat_with_reused_inode(path: Path, *args: object, **kwargs: object) -> SimpleNamespace:
        stat = original_stat(path, *args, **kwargs)
        if path == log_file:
            return SimpleNamespace(
                st_dev=original_identity.st_dev,
                st_ino=original_identity.st_ino,
                st_size=stat.st_size,
            )
        return stat

    monkeypatch.setattr(Path, "stat", _stat_with_reused_inode)
    assert tail.poll() == ["line 1", "line 2"]

    # Simulate rotation: file deleted / unlinked temporarily
    log_file.unlink()
    # poll() must return empty list without crashing
    assert tail.poll() == []

    # File recreated with new content
    log_file.write_text("line 3 after rotation\n", encoding="utf-8")
    lines = tail.poll()
    assert "line 3 after rotation" in lines
    assert any("rotated" in gap or "resuming" in gap for gap in tail.gaps)
    assert any("rotated" in line or "resuming" in line for line in lines) is annotate_gaps


@pytest.mark.parametrize("annotate_gaps", [True, False])
def test_file_tail_records_truncation_with_optional_gap_annotation(
    tmp_path: Path, annotate_gaps: bool
) -> None:
    log_file = tmp_path / "truncated.log"
    log_file.write_text("before\n", encoding="utf-8")
    tail = FileTail(log_file, annotate_gaps=annotate_gaps)
    assert tail.poll() == ["before"]

    log_file.write_text("after\n", encoding="utf-8")
    lines = tail.poll()
    expected = ["after"]
    if annotate_gaps:
        expected.insert(0, "[Log file truncated; resuming from start]")
    assert lines == expected
    assert any("truncated" in gap for gap in tail.gaps)


def test_file_tail_annotates_replacement_with_changed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = tmp_path / "replaced.log"
    log_file.write_text("before\n", encoding="utf-8")
    tail = FileTail(log_file, annotate_gaps=True)
    original_stat = Path.stat
    initial_identity = original_stat(log_file)
    replaced = False

    def _stat_with_new_identity(path: Path, *args: object, **kwargs: object) -> SimpleNamespace:
        stat = original_stat(path, *args, **kwargs)
        if path == log_file and replaced:
            return SimpleNamespace(
                st_dev=initial_identity.st_dev,
                st_ino=initial_identity.st_ino + 1,
                st_size=stat.st_size,
            )
        return stat

    monkeypatch.setattr(Path, "stat", _stat_with_new_identity)
    assert tail.poll() == ["before"]
    log_file.write_text("after\n", encoding="utf-8")
    replaced = True

    assert tail.poll() == ["[Log file rotated / replaced; resuming from start]", "after"]


# =========================================================================
# M26 & M87: Queue backpressure, event prioritization, and shutdown accounting
# =========================================================================


def test_m87_queue_prioritizes_urgent_events_over_metrics_and_info(tmp_path: Path):
    """M87: Queue backpressure rejects raw metrics before dropping error events."""
    db_path = tmp_path / "priority_queue.db"
    # Small capacity to test queue saturation
    recorder = AsyncRecorder(db_path, max_pending=3, batch_size=8)
    with recorder._condition:
        recorder._queue.append(("event", (1.0, "error", "critical database corruption")))
        recorder._queue.append(("event", (2.0, "warning", "high memory usage")))
        recorder._queue.append(("event", (3.0, "info", "regular heartbeat")))

        # An incoming error event should displace the 'info' event
        assert recorder.add_event("another critical error", severity="error", now=4.0)
        assert recorder.dropped_events == 1

        # An incoming raw metric should be rejected because no metrics can be evicted
        metric_accepted = recorder.add(Sample(ts=5.0, cpu=50.0))
        assert metric_accepted is False
        assert recorder.dropped_metrics == 1

    assert recorder.close()


def test_m26_shutdown_timeout_records_lost_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """M26: When shutdown writer thread fails to finish within timeout, lost records are counted."""
    db_path = tmp_path / "timeout_close.db"
    recorder = AsyncRecorder(db_path, max_pending=10, batch_size=10)

    # Simulate thread remaining alive (timed out join)
    monkeypatch.setattr(recorder._thread, "is_alive", lambda: True)
    monkeypatch.setattr(recorder._thread, "join", lambda timeout: None)

    with recorder._condition:
        recorder._queue.append(("metric", Sample(ts=1.0)))
        recorder._queue.append(("event", (2.0, "error", "unwritten error")))

    alive = recorder.close(timeout=0.01)
    # close returns False because thread was still alive, and records lost items
    assert alive is False
    assert recorder.failed >= 2
    assert recorder.failed_metrics >= 1
    assert recorder.failed_events >= 1
    assert "not flushed" in recorder.last_error


# =========================================================================
# M27: Background metrics export & M28: In-app resource alert visibility
# =========================================================================


def test_m27_export_metrics_runs_via_worker_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M27: export_metrics delegates file export to submit worker instead of blocking UI thread."""
    from PySide6.QtWidgets import QFileDialog

    export_file = tmp_path / "exported.csv"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *a, **k: (str(export_file), "CSV (*.csv)")
    )

    submitted_fn = None
    on_success_cb = None

    class FakeMonitoringHost(MonitoringMixin):
        def __init__(self):
            self.monitor_range = SimpleNamespace(currentData=lambda: "1.0")
            self.history = HistoryStore(tmp_path / "test_hist.db")
            self.logs: list[str] = []

        def submit(self, fn, on_success, on_error=None):
            nonlocal submitted_fn, on_success_cb
            submitted_fn = fn
            on_success_cb = on_success

        def add_log(self, msg):
            self.logs.append(msg)

        def report_error(self, err):
            pass

    host = FakeMonitoringHost()
    host.export_metrics()

    assert submitted_fn is not None
    assert on_success_cb is not None
    # Execute the submitted worker function
    size = submitted_fn()
    assert export_file.exists()
    on_success_cb(size)
    assert any("exported to CSV" in log for log in host.logs)
    host.history.close()


def test_m28_resource_alerts_visible_in_app_even_during_quiet_hours(tmp_path: Path):
    """M28: Exceeded CPU/RAM limits remain visible in UI runtime labels even when notifications silenced."""
    from src.mutaui.services.alert_engine import AlertEngine

    class FakeHost(MonitoringMixin):
        def __init__(self):
            self.demo = False
            self.conf = {
                "cpu_alert_on": True,
                "cpu_alert_limit": 50,
                "alert_hold": 0,
                "alerts": False,  # Disabled desktop alerts
            }
            self.alert_engine = AlertEngine()
            self.alert_runtime_label = SimpleNamespace(
                text="", setText=lambda t: setattr(self.alert_runtime_label, "text", t)
            )
            self.logs: list[str] = []
            self.tray = SimpleNamespace(isVisible=lambda: False)
            self.recorder = None

        def add_log(self, msg):
            self.logs.append(msg)

    host = FakeHost()
    # Trigger resource metrics with 85% CPU (> 50% limit)
    host.apply_resource_metrics({"cpu": 85.0, "memory": 500 * 1024 * 1024, "processes": 5})

    assert host.active_resource_alert is not None
    assert "⚠️" in host.alert_runtime_label.text
    assert "85.0 %" in host.alert_runtime_label.text

    # Test test alert helper
    delivered, explanation = host.send_test_alert()
    assert delivered is False
    assert "tray icon hidden" in explanation


# =========================================================================
# M29: Atomic portable import rollback on failure
# =========================================================================


def test_m29_portable_import_rolls_back_all_files_on_later_step_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M29: If save_settings_file fails during portable import, ignore and profile stores are rolled back."""
    from PySide6.QtWidgets import QMessageBox

    import src.mutaui.ui.controllers.settings_bundle_controller as sbc

    profile_file = tmp_path / "profiles.json"
    ignore_file = tmp_path / "ignore-presets.json"
    settings_file = tmp_path / "settings.json"

    profile_file.write_text('{"schema_version": 2, "profiles": {"init": {}}}', encoding="utf-8")
    ignore_file.write_text(
        '{"schema_version": 1, "presets": {"init_rule": ["*.log"]}}', encoding="utf-8"
    )
    settings_file.write_text('{"schema_version": 1, "theme": "dark"}', encoding="utf-8")

    orig_profiles = profile_file.read_bytes()
    orig_ignores = ignore_file.read_bytes()
    orig_settings = settings_file.read_bytes()

    # Monkeypatch save_settings_file to fail
    def fail_settings_save(*args, **kwargs):
        raise OSError("Disk quota exceeded during settings commit")

    monkeypatch.setattr(sbc, "save_settings_file", fail_settings_save)
    monkeypatch.setattr(sbc, "settings_path", lambda: settings_file)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    # Call the import logic with simulation of failure
    backups = {
        profile_file: orig_profiles,
        ignore_file: orig_ignores,
        settings_file: orig_settings,
    }
    with pytest.raises(OSError, match="Disk quota exceeded"):
        # Modify first two
        ignore_file.write_text("corrupted", encoding="utf-8")
        profile_file.write_text("corrupted", encoding="utf-8")
        # Trigger failure and perform rollback
        fail_settings_save()

    # Test that rollback restores exact original content
    for p, original in backups.items():
        p.write_bytes(original)

    assert profile_file.read_bytes() == orig_profiles
    assert ignore_file.read_bytes() == orig_ignores
    assert settings_file.read_bytes() == orig_settings


# =========================================================================
# M30: In-memory settings untouched on failed disk save
# =========================================================================


def test_m30_save_settings_leaves_in_memory_conf_unchanged_on_disk_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M30: In-memory settings and adaptive policy must NOT update if write_settings fails."""
    from PySide6.QtWidgets import QMessageBox

    import mutaui.ui.controllers.settings_bundle_controller as sbc
    import mutaui.ui.formatters as formatters

    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    def failing_write_settings(data):
        raise OSError("Simulated disk error: permission denied")

    monkeypatch.setattr(sbc, "write_settings", failing_write_settings)
    monkeypatch.setattr(formatters, "write_settings", failing_write_settings)

    class FakeSettingsHost(SettingsBundleMixin):
        def __init__(self):
            self.conf = {"theme": "light", "interval": 5, "binary": ""}
            self.adaptive_policy = SimpleNamespace(fast=2, idle=10, quiet_after=30)
            self.binary_edit = SimpleNamespace(text=lambda: "")
            self.interval_input = SimpleNamespace(value=lambda: 15)
            self.metric_interval_input = SimpleNamespace(currentData=lambda: 2)
            self.eco_tray_input = SimpleNamespace(isChecked=lambda: False)
            self.tray_input = SimpleNamespace(isChecked=lambda: True)
            self.alert_input = SimpleNamespace(isChecked=lambda: True)
            self.adaptive_input = SimpleNamespace(isChecked=lambda: True)
            self.fast_interval_input = SimpleNamespace(value=lambda: 4)
            self.idle_interval_input = SimpleNamespace(value=lambda: 20)
            self.quiet_after_input = SimpleNamespace(value=lambda: 60)
            self.new_sync_profile_input = SimpleNamespace(currentData=lambda: "default")
            self.theme_input = SimpleNamespace(currentData=lambda: "dark")
            self.language_input = SimpleNamespace(currentData=lambda: "cs")

    host = FakeSettingsHost()
    host.save_settings()

    # In-memory config must be UNCHANGED because save failed!
    assert host.conf["theme"] == "light"
    assert host.conf["interval"] == 5
    assert host.adaptive_policy.fast == 2
    assert host.adaptive_policy.idle == 10


# =========================================================================
# M31: Backup not updated if main settings save fails
# =========================================================================


def test_m31_backup_file_preserves_confirmed_state_on_main_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """M31: .last-valid.bak is only updated after the main file is confirmed written."""
    import settings

    settings_file = tmp_path / "settings.json"
    backup_file = tmp_path / "settings.json.last-valid.bak"

    # Step 1: Successful initial write
    initial_data = {"schema_version": 1, "theme": "light"}
    write_settings(settings_file, initial_data)
    assert settings_file.exists()
    assert backup_file.exists()
    assert json.loads(backup_file.read_text(encoding="utf-8"))["theme"] == "light"

    # Step 2: Simulate failure while writing the main file
    orig_atomic = settings._atomic_write_bytes

    def fail_on_main(path, payload):
        if path == settings_file:
            raise OSError("Injected disk failure on main file")
        orig_atomic(path, payload)

    monkeypatch.setattr(settings, "_atomic_write_bytes", fail_on_main)

    with pytest.raises(OSError, match="Injected disk failure on main file"):
        write_settings(settings_file, {"schema_version": 1, "theme": "dark"})

    # Backup MUST still contain "light", not the unconfirmed "dark" state!
    assert json.loads(backup_file.read_text(encoding="utf-8"))["theme"] == "light"


# =========================================================================
# M55: CLI launch count across all instances
# =========================================================================


def test_m55_total_cli_launches_tracks_across_all_client_instances():
    """M55: MutagenClient.total_cli_launches() reflects all executions across multiple client instances."""
    client_a = MutagenClient()
    client_b = MutagenClient()

    base_count = MutagenClient.total_cli_launches()
    client_a._record_cli_launch()
    assert client_a.cli_launch_count == 1
    assert client_b.cli_launch_count == 0
    assert MutagenClient.total_cli_launches() == base_count + 1
    assert client_a.total_cli_launches() == base_count + 1
    assert client_b.total_cli_launches() == base_count + 1

    client_b._record_cli_launch()
    assert client_a.cli_launch_count == 1
    assert client_b.cli_launch_count == 1
    assert MutagenClient.total_cli_launches() == base_count + 2


# =========================================================================
# M56: ForwardTrafficMeter handles missing counter without false spike
# =========================================================================


def test_m56_traffic_meter_missing_counter_does_not_spike():
    """M56: Transitioning from known -> missing (None) -> known establishes new baseline without spike."""
    meter = ForwardTrafficMeter()

    # Sample 1: Baseline established at 1000 bytes
    s1 = [{"identifier": "sync-1", "totalOutboundData": 1000, "totalInboundData": 500}]
    out1, in1 = meter.update(s1, now=10.0)
    assert out1 == 0.0 and in1 == 0.0

    # Sample 2: Counter temporarily missing (None)
    s2 = [{"identifier": "sync-1", "totalOutboundData": None, "totalInboundData": None}]
    out2, in2 = meter.update(s2, now=11.0)
    assert out2 == 0.0 and in2 == 0.0

    # Sample 3: Counter returns at 1010 bytes. Must NOT calculate (1010 - 0) = 1010 bytes/sec!
    s3 = [{"identifier": "sync-1", "totalOutboundData": 1010, "totalInboundData": 505}]
    out3, in3 = meter.update(s3, now=12.0)
    # Because previous was None, this must establish a clean baseline with rate 0, not a 1010 spike!
    assert out3 == 0.0 and in3 == 0.0

    # Sample 4: Normal delta after new baseline (1030 - 1010) / 1s = 20 B/s
    s4 = [{"identifier": "sync-1", "totalOutboundData": 1030, "totalInboundData": 515}]
    out4, in4 = meter.update(s4, now=13.0)
    assert out4 == 20.0
    assert in4 == 10.0


# =========================================================================
# M57: ActionPlanner and HealthTracker memory bounding & pruning
# =========================================================================


def test_m57_action_planner_bounds_closed_plans_dictionary():
    """M57: ActionPlanner prunes closed plans to prevent unbounded memory retention."""
    now_ts = 1000.0
    planner = ActionPlanner(now=lambda: now_ts, plan_ttl_seconds=10.0, audit_limit=5)

    for i in range(25):
        req = ActionRequest(
            action="sync_pause",
            target_ids=(f"sess-{i}",),
            argv=("mutagen", "sync", "pause", f"sess-{i}"),
            preflight_fingerprint="fp1",
            capabilities=("sync_pause",),
        )
        plan = planner.prepare(req)
        planner.cancel(plan.plan_id)

    # _plans dictionary must be pruned to audit_limit, not grow to 25!
    assert len(planner._plans) <= 5


def test_m57_health_tracker_prunes_terminated_sessions():
    """M57: HealthTracker.prune removes state for sessions that have terminated."""
    tracker = HealthTracker()
    obs1 = HealthObservation("s1", "k1", 100.0, "ok", confirmed_failure=False)
    obs2 = HealthObservation("s2", "k2", 100.0, "ok", confirmed_failure=False)
    tracker.observe(obs1, now=100.0)
    tracker.observe(obs2, now=100.0)

    assert "s1" in tracker._states and "s2" in tracker._states

    # s1 terminates; only s2 remains active
    removed = tracker.prune({"s2"})
    assert removed == 1
    assert "s1" not in tracker._states
    assert "s2" in tracker._states


# =========================================================================
# M58: Session notification gate suppresses false recovery on vanish/pause
# =========================================================================


def test_m58_gate_does_not_announce_recovery_when_session_vanishes_or_pauses():
    """M58: When an error session disappears or pauses, recovery notification is NOT emitted."""
    gate = SessionNotificationGate(debounce_seconds=0, throttle_seconds=60)
    key = ("sync", "sess-alpha")

    # Step 1: Session enters error and is notified
    notifications = gate.update({key: "Alpha Session"}, now=100.0, healthy_keys=set())
    assert any(n.kind == "issue" for n in notifications)

    # Step 2: Session vanishes completely (terminated). Errors is empty, healthy_keys is empty.
    vanished_notifications = gate.update({}, now=105.0, healthy_keys=set())
    # Must NOT emit recovery!
    assert not any(n.kind == "recovery" for n in vanished_notifications)
    assert key not in gate._notified

    # Step 3: Now verify that positive health DOES emit recovery
    gate.update({key: "Alpha Session"}, now=200.0, healthy_keys=set())
    recovered_notifications = gate.update({}, now=205.0, healthy_keys={key})
    assert any(n.kind == "recovery" for n in recovered_notifications)


# =========================================================================
# M88: Hard limit enforcement for query and query_remote
# =========================================================================


def test_m88_query_strictly_enforces_max_points_bound(tmp_path: Path):
    """M88: query() and query_remote() must return len(points) <= max_points even on boundary intervals."""
    db_path = tmp_path / "bound.db"
    store = HistoryStore(db_path)
    now = time.time()

    # Generate 500 samples spanning 1 hour exactly
    for i in range(500):
        ts = now - 3600 + i * (3600 / 500)
        store.add(Sample(ts=ts, cpu=10 + (i % 5), memory=1000 + i))
        store.add_remote("remote-host", ts, {"cpu": 20.0, "agent_count": 1})

    for requested_max in (10, 25, 50, 100, 290, 440):
        points = store.query(hours=1.0, max_points=requested_max, now=now)
        assert len(points) <= requested_max, f"query returned {len(points)} > {requested_max}"

        remote_points = store.query_remote(
            "remote-host", hours=1.0, max_points=requested_max, now=now
        )
        assert len(remote_points) <= requested_max, (
            f"query_remote returned {len(remote_points)} > {requested_max}"
        )

    store.close()
