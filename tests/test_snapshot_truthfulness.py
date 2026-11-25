"""Targeted regression tests for Batch 2A (M04, M05, M06, M70, M84, M85).

Covers:
- M04: Truthful per-kind freshness, separate timestamps, and HealthRing scope computation.
- M05: Session parser rejects malformed items, handles partial corruption, allows optional fields.
- M06: Start/Stop controls separated, explicit disabled reasons, platform-aware autostart.
- M70: Footer separates CLI path from confirmed daemon status and shows last contact.
- M84: Independent sync/forward listing; one failure does not suppress the other or fake offline.
- M85: Robust version parsing; corrupt or empty version output does not discard session lists.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import app as app_module
from mutagen_client import (
    MutagenError,
    Snapshot,
    classify_daemon_error,
    parse_sessions,
    parse_sessions_checked,
    validate_session_entry,
)
from mutaui.services.snapshot_status import (
    compute_daemon_controls,
    compute_overview_scope,
    format_daemon_status,
    format_footer_status,
    format_hero_status,
    format_registration_status,
    format_side_status,
    parse_mutagen_version_output,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    instance = app_module.MainWindow(demo=True)
    yield instance
    instance.timer.stop()
    instance.metric_timer.stop()
    instance.tail_timer.stop()
    instance._allow_exit = True
    instance.close()
    instance.history.close()


# ---------------------------------------------------------------------------
# M05: Session parsing integrity and malformed row distinction
# ---------------------------------------------------------------------------


def test_m05_empty_list_vs_invalid_entries():
    """Genuinely empty JSON returns [] without errors."""
    assert parse_sessions("[]\n") == []
    result = parse_sessions_checked("[]")
    assert result.sessions == []
    assert result.rejected_count == 0
    assert not result.incomplete


def test_m05_rejects_non_object_elements_when_all_invalid():
    """List composed entirely of non-objects or missing IDs raises MutagenError."""
    with pytest.raises(MutagenError, match="malformed session entries"):
        parse_sessions_checked('["not-a-session", 123, null]')

    with pytest.raises(MutagenError, match="malformed session entries"):
        parse_sessions_checked('[{"no_id": true}]')


def test_m05_mixed_list_retains_valid_and_marks_incomplete():
    """Mixed valid and corrupted items retain valid items and flags incomplete status."""
    raw = [
        {"identifier": "sync-1", "name": "project", "paused": False, "status": 6},
        "corrupted_entry",
        {"identifier": "", "name": "missing_id"},
        {"identifier": "sync-2", "name": "api", "paused": True, "status": 0},
    ]
    import json

    result = parse_sessions_checked(json.dumps(raw))
    assert len(result.sessions) == 2
    assert [s["identifier"] for s in result.sessions] == ["sync-1", "sync-2"]
    assert result.rejected_count == 2
    assert result.incomplete is True
    assert "non_object" in result.rejected_reasons
    assert "missing_identifier" in result.rejected_reasons

    # Standard parse_sessions retains valid rows
    compat_rows = parse_sessions(json.dumps(raw))
    assert len(compat_rows) == 2


def test_m05_allows_forward_compatible_unknown_fields():
    """New optional fields in future Mutagen releases are preserved without failure."""
    raw = [
        {
            "identifier": "sync-future",
            "name": "future-session",
            "paused": False,
            "status": 6,
            "futureEngineVersion": "2.0.0",
            "newProtocolFlag": True,
            "experimentalRouting": {"route": "direct", "metrics": [1, 2]},
        }
    ]
    import json

    result = parse_sessions_checked(json.dumps(raw))
    assert len(result.sessions) == 1
    assert result.sessions[0]["futureEngineVersion"] == "2.0.0"
    assert result.incomplete is False


def test_m05_validation_helpers_identify_exact_field_violations():
    assert validate_session_entry("string") == "non_object"
    assert validate_session_entry({}) == "missing_identifier"
    assert validate_session_entry({"identifier": "   "}) == "missing_identifier"
    assert validate_session_entry({"identifier": "x", "name": 123}) == "invalid_name"
    assert validate_session_entry({"identifier": "x", "paused": "yes"}) == "invalid_paused"
    assert validate_session_entry({"identifier": "x", "status": True}) == "invalid_status"
    assert validate_session_entry({"identifier": "x", "alpha": "not-dict"}) == "invalid_endpoint"
    assert validate_session_entry({"identifier": "x", "alpha": {"path": "/tmp"}}) is None


# ---------------------------------------------------------------------------
# M84: Independent Sync and Forward listing (all 4 combinations)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sync_fails", "fwd_fails", "expected_daemon", "expected_sync_st", "expected_fwd_st"),
    [
        (False, False, True, "fresh", "fresh"),
        (False, True, True, "fresh", "unavailable"),
        (True, False, True, "unavailable", "fresh"),
        (True, True, False, "unavailable", "unavailable"),
    ],
)
def test_m84_independent_sync_and_forward_combinations(
    window, monkeypatch, sync_fails, fwd_fails, expected_daemon, expected_sync_st, expected_fwd_st
):
    class DualClient:
        def __init__(self, binary):
            self.binary = binary

        def list_sessions(self, kind):
            if kind == "sync" and sync_fails:
                raise MutagenError("sync list timed out")
            if kind == "forward" and fwd_fails:
                raise MutagenError("forward list socket closed")
            return [{"identifier": f"{kind}-1"}]

        def get_version(self):
            return "0.18.1"

    captured = []
    window.demo = False
    window.client = SimpleNamespace(binary="mutagen.exe")
    window._version_cache = ("0.18.1", app_module.time.monotonic(), "mutagen.exe")
    monkeypatch.setattr(app_module, "MutagenClient", DualClient)
    monkeypatch.setattr(app_module, "read_registration", lambda _b: ("registered", "reg_cmd"))

    def capture_submit(work, on_result, on_error=None, on_done=None):
        captured.append(work())
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", capture_submit)
    window.refresh(force=True)

    snap = captured[0]
    assert snap.daemon == expected_daemon
    assert snap.sync_status == expected_sync_st
    assert snap.forward_status == expected_fwd_st
    if sync_fails and not fwd_fails:
        assert snap.forward == [{"identifier": "forward-1"}]
        assert snap.sync == []
        assert "Sync: sync list timed out" in snap.error
    elif fwd_fails and not sync_fails:
        assert snap.sync == [{"identifier": "sync-1"}]
        assert snap.forward == []
        assert "Forwarding: forward list socket closed" in snap.error


# ---------------------------------------------------------------------------
# M85: Version check robustness (empty, corrupt, multiline)
# ---------------------------------------------------------------------------


def test_m85_parse_mutagen_version_output_scenarios():
    # Clean standard version
    ver, st, err = parse_mutagen_version_output("0.18.1\n")
    assert ver == "0.18.1"
    assert st == "fresh"

    # Multi-line output
    ver, st, err = parse_mutagen_version_output("Mutagen version 0.18.1\nBuild commit: abcdef\n")
    assert ver == "Mutagen version 0.18.1"
    assert st == "fresh"
    assert "multi-line" in err

    # Completely empty output
    ver, st, err = parse_mutagen_version_output("\n\n   \n")
    assert ver == ""
    assert st == "unavailable"

    # Control chars / corrupt binary output
    ver, st, err = parse_mutagen_version_output("\x00\x01\x02\x03corrupt")
    assert ver == ""
    assert st == "invalid"


def test_m85_refresh_with_empty_version_retains_sessions_without_crash(window, monkeypatch):
    class EmptyVersionClient:
        def __init__(self, binary):
            self.binary = binary

        def list_sessions(self, kind):
            return [{"identifier": f"{kind}-id"}]

        def get_version(self):
            return ""  # Empty output that previously caused IndexError on splitlines()[0]

    captured = []
    window.demo = False
    window.client = SimpleNamespace(binary="mutagen.exe")
    window._version_cache = ("", 0.0, "")
    monkeypatch.setattr(app_module, "MutagenClient", EmptyVersionClient)
    monkeypatch.setattr(app_module, "read_registration", lambda _b: ("registered", "cmd"))

    def capture_submit(work, on_result, on_error=None, on_done=None):
        snap = work()
        captured.append(snap)
        on_result(snap)
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", capture_submit)
    window.refresh(force=True)

    snap = captured[0]
    assert len(snap.sync) == 1
    assert len(snap.forward) == 1
    assert snap.daemon is True
    assert snap.version_status == "unavailable"
    assert window._version_label_text == "Version: unavailable"


# ---------------------------------------------------------------------------
# M04: Overview truthfulness and HealthRing scope calculation
# ---------------------------------------------------------------------------


def test_m04_overview_scope_both_fresh():
    now = datetime.now(tz=UTC)
    snap = Snapshot(
        binary="mutagen.exe",
        daemon=True,
        sync=[{"identifier": "s1", "paused": False, "status": 6}],
        forward=[{"identifier": "f1", "paused": False, "status": 3}],
        sync_status="fresh",
        forward_status="fresh",
        sync_observed_at=now,
        forward_observed_at=now,
    )
    scope = compute_overview_scope(
        snap, app_module.classify, retry_seconds=5, duration_ms=12.0, refreshed_time="12:00:00"
    )
    assert scope.ring_scope == "current"
    assert scope.ring_total == 2
    assert scope.ring_problem == 0
    assert "Current" in scope.scope_banner.en
    assert "Aktuální" in scope.scope_banner.cs
    assert scope.metric_values["all"] == "2"


def test_m04_overview_scope_partial_forward_failure():
    now = datetime.now(tz=UTC)
    past = now - timedelta(minutes=5)
    snap = Snapshot(
        binary="mutagen.exe",
        daemon=True,
        sync=[{"identifier": "s1", "paused": False, "status": 6}],
        forward=[{"identifier": "f1", "paused": False, "status": 3}],
        sync_status="fresh",
        forward_status="stale",
        sync_observed_at=now,
        forward_observed_at=past,
        forward_error="forward timeout",
    )
    scope = compute_overview_scope(
        snap, app_module.classify, retry_seconds=5, duration_ms=12.0, refreshed_time="12:00:00"
    )
    assert scope.ring_scope == "partial"
    assert scope.ring_total == 1  # Ring includes ONLY fresh sync sessions!
    assert "Current" in scope.scope_banner.en and "Last known" in scope.scope_banner.en
    assert "Aktuální" in scope.scope_banner.cs and "Poslední známý" in scope.scope_banner.cs
    assert "Current" in scope.sync_state_tag.en
    assert "Last known" in scope.forward_state_tag.en


def test_m04_overview_scope_completely_offline():
    past = datetime.now(tz=UTC) - timedelta(minutes=10)
    snap = Snapshot(
        binary="mutagen.exe",
        daemon=False,
        sync=[{"identifier": "s1", "paused": False, "status": 6}],
        forward=[{"identifier": "f1", "paused": False, "status": 3}],
        sync_status="stale",
        forward_status="stale",
        sync_observed_at=past,
        forward_observed_at=past,
        error="daemon connection refused",
    )
    scope = compute_overview_scope(
        snap, app_module.classify, retry_seconds=10, duration_ms=12.0, refreshed_time="12:00:00"
    )
    assert scope.ring_scope == "stale"
    assert scope.ring_total == 0  # Stale data is NEVER shown as active healthy sessions!
    assert "Last known" in scope.scope_banner.en
    assert "Poslední známý" in scope.scope_banner.cs


def test_m04_health_ring_widget_renders_scope_indicators(qapp):
    from PySide6.QtGui import QPixmap

    from mutaui.ui.widgets.health_ring import HealthRing

    ring = HealthRing()
    pix = QPixmap(122, 122)

    ring.set_health(10, 0, scope="current")
    assert ring.total == 10
    assert ring.healthy == 10
    assert ring.scope == "current"
    ring.render(pix)

    # In partial scope, amber/red ring color is used
    ring.set_health(10, 1, scope="partial")
    ring.render(pix)
    ring.set_health(10, 5, scope="partial")
    ring.render(pix)

    # In stale or unavailable mode, ring indicates unavailable/stale status
    ring.set_health(0, 0, scope="stale")
    assert ring.scope == "stale"
    assert ring.total == 0
    ring.render(pix)

    ring.set_health(0, 0, scope="unavailable")
    assert ring.scope == "unavailable"
    ring.render(pix)
    ring.close()


# ---------------------------------------------------------------------------
# M06: Daemon controls (Start vs Stop enablement) & platform registration
# ---------------------------------------------------------------------------


def test_m06_daemon_controls_policy():
    # Confirmed running: Start disabled, Stop enabled
    running_snap = Snapshot(binary="mutagen.exe", daemon=True, daemon_state="running")
    policy = compute_daemon_controls(running_snap, demo=False, pending_action=False)
    assert not policy.enable_start
    assert policy.enable_stop
    assert "running" in policy.hint.en

    # Confirmed stopped: Start enabled, Stop disabled
    stopped_snap = Snapshot(binary="mutagen.exe", daemon=False, daemon_state="stopped")
    policy = compute_daemon_controls(stopped_snap, demo=False, pending_action=False)
    assert policy.enable_start
    assert not policy.enable_stop
    assert "stopped" in policy.hint.en

    # Unconfigured: both disabled
    unconfigured_snap = Snapshot(binary="", daemon=False, daemon_state="unconfigured")
    policy = compute_daemon_controls(unconfigured_snap, demo=False, pending_action=False)
    assert not policy.enable_start
    assert not policy.enable_stop
    assert "Settings" in policy.hint.en

    # Unavailable/timeout: suggest diagnostics
    unavail_snap = Snapshot(
        binary="mutagen.exe", daemon=False, daemon_state="unavailable", error="CLI timed out"
    )
    policy = compute_daemon_controls(unavail_snap, demo=False, pending_action=False)
    assert not policy.enable_start
    assert not policy.enable_stop
    assert policy.suggest_diagnostics is True


def test_m06_classify_daemon_error():
    assert classify_daemon_error("Mutagen daemon is not running") == "stopped"
    assert classify_daemon_error("unable to connect to daemon") == "stopped"
    assert classify_daemon_error("command timed out after 12 s") == "unavailable"
    assert classify_daemon_error("Failed to launch Mutagen: Access is denied") == "unavailable"


def test_m06_registration_text_platform_hints():
    reg_en_win, hint_win = format_registration_status("registered", platform_name="win32")
    assert "HKCU" in hint_win

    reg_en_mac, hint_mac = format_registration_status("unsupported", platform_name="darwin")
    assert "launchd" in hint_mac
    assert "launchd" in reg_en_mac.en
    assert "macOS" in reg_en_mac.cs

    reg_en_lin, hint_lin = format_registration_status("unsupported", platform_name="linux")
    assert "systemd" in hint_lin or "XDG" in hint_lin
    assert "systemd" in reg_en_lin.en
    assert "Linuxu" in reg_en_lin.cs


# ---------------------------------------------------------------------------
# M70: Truthful status bar / footer representation
# ---------------------------------------------------------------------------


def test_m70_footer_four_distinct_states():
    # 1. Binary not configured
    no_bin = Snapshot(binary="", daemon=False, daemon_state="unconfigured")
    footer_no_bin = format_footer_status(no_bin, demo=False)
    assert "Select a Mutagen installation" in footer_no_bin.en
    assert "Vyberte instalaci" in footer_no_bin.cs

    # 2. Binary configured, daemon confirmed stopped
    stopped = Snapshot(binary="C:/tools/mutagen.exe", daemon=False, daemon_state="stopped")
    footer_stopped = format_footer_status(stopped, demo=False)
    assert "Daemon stopped" in footer_stopped.en
    assert "Služba zastavena" in footer_stopped.cs
    assert "C:/tools/mutagen.exe" in footer_stopped.en
    assert "Connected to" not in footer_stopped.en

    # 3. Binary configured, daemon confirmed running
    running = Snapshot(binary="C:/tools/mutagen.exe", daemon=True, daemon_state="running")
    footer_running = format_footer_status(running, demo=False)
    assert "Daemon running" in footer_running.en
    assert "Služba běží" in footer_running.cs
    assert "C:/tools/mutagen.exe" in footer_running.en

    # 4. Outage / offline after previous contact
    contact_time = datetime(2026, 11, 24, 15, 30, 0, tzinfo=UTC)
    offline = Snapshot(
        binary="C:/tools/mutagen.exe",
        daemon=False,
        daemon_state="unavailable",
        last_contact_at=contact_time,
        sessions_stale=True,
    )
    footer_offline = format_footer_status(offline, demo=False)
    assert "Connection unverified" in footer_offline.en
    assert "last contact" in footer_offline.en
    assert "Připojení neověřeno" in footer_offline.cs
    assert "poslední kontakt" in footer_offline.cs


def test_m70_mainwindow_footer_updates_correctly(window):
    window.demo = False

    # Stopped state
    snap_stopped = Snapshot(
        binary="C:/tools/mutagen.exe",
        daemon=False,
        daemon_state="stopped",
        sessions_stale=False,
    )
    window.apply_snapshot(snap_stopped)
    assert "Daemon stopped" in window.footer.text()
    assert "Connected to" not in window.footer.text()

    # Running state
    snap_running = Snapshot(
        binary="C:/tools/mutagen.exe",
        daemon=True,
        daemon_state="running",
        sync_status="fresh",
        forward_status="fresh",
    )
    window.apply_snapshot(snap_running)
    assert "Daemon running" in window.footer.text()


def test_snapshot_status_coverage_matrix():
    """Exercise remaining presentation branches in snapshot_status for 100% coverage."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC)

    # 1. Daemon controls states
    demo_policy = compute_daemon_controls(Snapshot(), demo=True, pending_action=False)
    assert not demo_policy.enable_start and not demo_policy.enable_stop

    pending_policy = compute_daemon_controls(Snapshot(), demo=False, pending_action=True)
    assert not pending_policy.enable_start and not pending_policy.enable_stop

    checking_snap = Snapshot(binary="mutagen.exe")
    checking_snap.daemon_state = "checking"
    checking_policy = compute_daemon_controls(checking_snap, demo=False, pending_action=False)
    assert not checking_policy.enable_start and not checking_policy.enable_stop

    # 2. Footer states
    demo_footer = format_footer_status(Snapshot(), demo=True)
    assert "DEMO" in demo_footer.en

    chk_footer = format_footer_status(checking_snap, demo=False)
    assert "Checking daemon status" in chk_footer.en

    stale_running = Snapshot(
        binary="mutagen.exe",
        daemon=True,
        daemon_state="running",
        sessions_stale=True,
    )
    stale_running_footer = format_footer_status(stale_running, demo=False)
    assert "partial / stale" in stale_running_footer.en

    stopped_with_ts = Snapshot(
        binary="mutagen.exe",
        daemon=False,
        daemon_state="stopped",
        last_contact_at=now,
    )
    assert "last contact" in format_footer_status(stopped_with_ts, demo=False).en

    unverified_no_ts = Snapshot(
        binary="mutagen.exe",
        daemon=False,
        daemon_state="unavailable",
        error="probe failed",
    )
    assert "Connection unverified" in format_footer_status(unverified_no_ts, demo=False).en

    # 3. Daemon page status formatting
    unconf_daemon = format_daemon_status(Snapshot(binary="", daemon_state="unconfigured"))
    assert unconf_daemon[2] == "red"

    chk_daemon = format_daemon_status(checking_snap)
    assert chk_daemon[2] == "amber"

    running_with_err = format_daemon_status(
        Snapshot(binary="mutagen.exe", daemon=True, daemon_state="running", error="notice")
    )
    assert "notice" in running_with_err[1].en

    running_ver_note = format_daemon_status(
        Snapshot(
            binary="mutagen.exe",
            daemon=True,
            daemon_state="running",
            version_status="invalid",
            version_error="unreadable",
        )
    )
    assert "unreadable" in running_ver_note[1].en

    stopped_with_contact = format_daemon_status(stopped_with_ts)
    assert "Last contact" in stopped_with_contact[1].en

    unavail_status = format_daemon_status(unverified_no_ts)
    assert unavail_status[2] == "red"

    # 4. Hero card formatting
    assert "not configured" in format_hero_status(Snapshot(binary=""))[0].en
    assert "Checking connection" in format_hero_status(checking_snap)[0].en
    assert "partial session status" in format_hero_status(stale_running)[0].en
    assert "Daemon is stopped" in format_hero_status(stopped_with_ts)[0].en
    assert "unverified" in format_hero_status(unverified_no_ts)[0].en

    # 5. Sidebar badge formatting
    def fake_plural(count, words):
        return words[0] if count == 1 else words[2]

    assert "not found" in format_side_status(Snapshot(binary=""), czech_plural=fake_plural)[0].en
    assert "Checking daemon" in format_side_status(checking_snap, czech_plural=fake_plural)[0].en
    assert "partial" in format_side_status(stale_running, czech_plural=fake_plural)[1].en
    assert "offline" in format_side_status(stopped_with_ts, czech_plural=fake_plural)[0].en
    assert (
        "offline"
        in format_side_status(
            Snapshot(binary="m.exe", daemon_state="stopped"), czech_plural=fake_plural
        )[0].en
    )
    assert "unavailable" in format_side_status(unverified_no_ts, czech_plural=fake_plural)[0].en

    # 6. Updated banner variants in compute_overview_scope
    # Variant A: daemon running with stale sessions
    scope_a = compute_overview_scope(
        stale_running,
        app_module.classify,
        retry_seconds=5,
        duration_ms=10.0,
        refreshed_time="12:00:00",
    )
    assert "showing last successful sessions" in scope_a.updated_banner.en

    # Variant B: daemon offline without stale sessions
    clean_offline = Snapshot(
        binary="mutagen.exe",
        daemon=False,
        daemon_state="stopped",
        sessions_stale=False,
    )
    scope_b = compute_overview_scope(
        clean_offline,
        app_module.classify,
        retry_seconds=7,
        duration_ms=10.0,
        refreshed_time="12:00:00",
    )
    assert "retrying in 7 s" in scope_b.updated_banner.en

    # Variant C: daemon running with sessions_stale and explicit error
    stale_with_err = Snapshot(
        binary="mutagen.exe",
        daemon=True,
        daemon_state="running",
        sessions_stale=True,
        error="forward list unavailable",
    )
    scope_c = compute_overview_scope(
        stale_with_err,
        app_module.classify,
        retry_seconds=5,
        duration_ms=10.0,
        refreshed_time="12:00:00",
    )
    assert "forward list unavailable" in scope_c.updated_banner.en

    # Variant D: daemon offline with sessions_stale (showing last successful)
    stale_offline = Snapshot(
        binary="mutagen.exe",
        daemon=False,
        daemon_state="stopped",
        sessions_stale=True,
    )
    scope_d = compute_overview_scope(
        stale_offline,
        app_module.classify,
        retry_seconds=6,
        duration_ms=10.0,
        refreshed_time="12:00:00",
    )
    assert "showing last successful sessions" in scope_d.updated_banner.en
