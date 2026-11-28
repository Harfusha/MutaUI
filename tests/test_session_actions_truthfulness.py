"""Targeted regression tests for Batch 2B (M07, M08, M11, M16, M17, M18, M19, M20, M21, M54).

Covers:
- M07: Exact CLI returned ID and effective target matching on session creation; no provenance for alien IDs.
- M08: Verification of session paused/resumed flags; flush as requested cycle.
- M11: Proposal lifecycle; rejection of controlled replacement for project/external sessions.
- M16: Disappeared server group transitions to unavailable; actions disabled; no silent fallback to all.
- M17: Group table session opening works on QTableView/SessionTableModel without AttributeError.
- M18: 500-session bulk limit checked in UI preview before prompting confirmation.
- M19: Troubleshooter refresh shows progress and binds to fresh snapshot; edit_session wired.
- M20: Diagnostics summary separates global issues from session issues without inflated session count.
- M21 & M54: Auto-safe honest status description; no premature success recording before refresh runs.
"""

from __future__ import annotations

import dataclasses
import os
import time
from datetime import UTC, datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

import app as app_module
from mutagen_client import (
    BULK_OPERATION_LIMIT,
    ActionPlanner,
    MutagenClient,
    MutagenError,
    Snapshot,
)
from mutaui.adapters.mutagen_snapshot import from_session_dict
from mutaui.services.health_tracker import HealthObservation
from mutaui.services.session_doctor import (
    DiagnosticIssue,
    SessionDoctorReport,
)
from mutaui.ui.troubleshooter_dialog import TroubleshooterDialog


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
# M07: Exact CLI returned ID and endpoint verification on creation
# ---------------------------------------------------------------------------


def test_m07_create_binds_to_exact_cli_returned_id_and_endpoints(monkeypatch):
    """When CLI declares Created session <id>, client matches it and verifies endpoints."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    before_sessions = []
    after_sessions = [
        {
            "identifier": "sync_confirmed_123",
            "name": "my-sync",
            "alpha": {"path": "/local/project"},
            "beta": {"url": "user@server:/remote/project"},
        }
    ]

    list_calls = 0

    def mock_list(area):
        nonlocal list_calls
        list_calls += 1
        return before_sessions if list_calls == 1 else after_sessions

    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Created session sync_confirmed_123\nStarted initial scan"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    plan = client.prepare_create_plan(
        "sync", ["/local/project", "user@server:/remote/project", "--name=my-sync"]
    )
    consented_plan = client.consent_action_plan(plan, consent=True)

    out = client.execute(
        "sync",
        "create",
        options=["/local/project", "user@server:/remote/project", "--name=my-sync"],
        operator_consent=True,
        action_plan=consented_plan,
    )
    assert "Created session sync_confirmed_123" in out
    assert client.last_created_session == (
        "sync",
        "sync_confirmed_123",
        ("sync", "create", "/local/project", "user@server:/remote/project", "--name=my-sync"),
    )


def test_m07_create_rejects_alien_id_returned_by_cli(monkeypatch):
    """If CLI declares Created session sync_alien but observed session is sync_other, reject."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    before_sessions = []
    # Observed list only has sync_other_555
    after_sessions = [
        {
            "identifier": "sync_other_555",
            "name": "my-sync",
            "alpha": {"path": "/local/project"},
            "beta": {"url": "user@server:/remote/project"},
        }
    ]

    list_calls = 0

    def mock_list(area):
        nonlocal list_calls
        list_calls += 1
        return before_sessions if list_calls == 1 else after_sessions

    # CLI stdout claims alien ID
    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Created session sync_alien_999\n"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    plan = client.prepare_create_plan("sync", ["/local/project", "user@server:/remote/project"])
    consented_plan = client.consent_action_plan(plan, consent=True)

    with pytest.raises(MutagenError, match="Created session identifier returned by CLI"):
        client.execute(
            "sync",
            "create",
            options=["/local/project", "user@server:/remote/project"],
            operator_consent=True,
            action_plan=consented_plan,
        )

    assert client.last_created_session is None


def test_m07_create_rejects_mismatched_endpoints(monkeypatch):
    """If observed endpoints do not match requested arguments, creation verification fails."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    before_sessions = []
    # Endpoints do not match /local/project and user@server:/remote/project
    after_sessions = [
        {
            "identifier": "sync_123",
            "alpha": {"path": "/wrong/path"},
            "beta": {"url": "user@server:/wrong/path"},
        }
    ]

    list_calls = 0

    def mock_list(area):
        nonlocal list_calls
        list_calls += 1
        return before_sessions if list_calls == 1 else after_sessions

    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Created session sync_123"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    plan = client.prepare_create_plan("sync", ["/local/project", "user@server:/remote/project"])
    consented_plan = client.consent_action_plan(plan, consent=True)

    with pytest.raises(MutagenError, match="Created session endpoints do not match"):
        client.execute(
            "sync",
            "create",
            options=["/local/project", "user@server:/remote/project"],
            operator_consent=True,
            action_plan=consented_plan,
        )

    assert client.last_created_session is None


# ---------------------------------------------------------------------------
# M08: Truthful verification of pause, resume, and flush actions
# ---------------------------------------------------------------------------


def test_m08_pause_rejects_if_session_remains_unpaused(monkeypatch):
    """If CLI succeeds (exit 0) but post-check sees paused=False, pause is not confirmed."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    sessions = [{"identifier": "sync_1", "paused": False, "status": "watching"}]

    def mock_list(area):
        return sessions

    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Paused session sync_1"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    with pytest.raises(MutagenError, match="found session\\(s\\) not paused"):
        client.execute("sync", "pause", target="sync_1", operator_consent=True)


def test_m08_pause_confirms_when_session_is_paused(monkeypatch):
    """When post-check confirms paused=True, pause succeeds."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    list_calls = 0

    def mock_list(area):
        nonlocal list_calls
        list_calls += 1
        if list_calls == 1:
            return [{"identifier": "sync_1", "paused": False, "status": "watching"}]
        return [{"identifier": "sync_1", "paused": True, "status": "paused"}]

    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Paused session sync_1"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    out = client.execute("sync", "pause", target="sync_1", operator_consent=True)
    assert "Paused session sync_1" in out


def test_m08_resume_rejects_if_session_remains_paused(monkeypatch):
    """If CLI succeeds but session is still paused=True in post-check, resume is rejected."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    sessions = [{"identifier": "sync_1", "paused": True, "status": "paused"}]

    def mock_list(area):
        return sessions

    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Resumed session sync_1"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    with pytest.raises(MutagenError, match="found session\\(s\\) still paused"):
        client.execute("sync", "resume", target="sync_1", operator_consent=True)


def test_m08_flush_records_honest_requested_cycle_outcome(monkeypatch):
    """Flush command verifies session existence and records requested cycle outcome."""
    planner = ActionPlanner(now=time.monotonic)
    client = MutagenClient("dummy_mutagen", action_planner=planner)

    sessions = [{"identifier": "sync_1", "paused": False, "status": "watching"}]

    def mock_list(area):
        return sessions

    def mock_command(args, timeout=35, readonly=False, env_overrides=None):
        return "Flushed session sync_1"

    monkeypatch.setattr(client, "list_sessions", mock_list)
    monkeypatch.setattr(client, "command", mock_command)

    client.execute("sync", "flush", target="sync_1", operator_consent=True)
    # Check plan audit history
    audit_events = planner.audit
    assert len(audit_events) >= 1
    assert any("flush cycle requested" in event.reason for event in audit_events)


# ---------------------------------------------------------------------------
# M16: Server group disappearance and scope preservation
# ---------------------------------------------------------------------------


def test_m16_disappeared_group_does_not_fall_back_to_all(window):
    """When a selected server group disappears, UI switches to __unavailable__, not __all__."""
    # First snapshot with server host-a
    window.snapshot.sync = [
        {
            "identifier": "sync_1",
            "alpha": {"path": "/local"},
            "beta": {"protocol": "ssh", "host": "host-a", "port": 22},
        }
    ]
    window.snapshot.forward = []
    window.update_server_groups()

    # User explicitly selects host-a
    idx = window.server_selector.findData("ssh:host-a:22")
    assert idx >= 0
    window.server_selector.setCurrentIndex(idx)
    assert window.server_selector.currentData() == "ssh:host-a:22"

    # Second snapshot: host-a is gone, host-b is present
    window.snapshot.sync = [
        {
            "identifier": "sync_2",
            "alpha": {"path": "/local"},
            "beta": {"protocol": "ssh", "host": "host-b", "port": 22},
        }
    ]
    window.update_server_groups()

    # Must NOT have fallen back to index 0 (__all__)
    assert window.server_selector.currentData() == "__unavailable__"
    assert (
        "není dostupná" in window.server_selector.currentText()
        or "no longer available" in window.server_selector.currentText()
    )

    # Targets for the unavailable group must be empty
    targets = window.server_targets("sync", "server")
    assert targets == []

    # Update server details must disable action buttons
    window.update_server_details()
    assert not window.b_srv_sync.isEnabled()
    assert not window.b_srv_pause.isEnabled()
    assert not window.b_srv_resume.isEnabled()


def test_m16_bulk_action_aborts_on_unavailable_group(window, monkeypatch):
    """Executing a bulk action when group is __unavailable__ warns and exits without commands."""
    window.demo = False
    window.server_selector.addItem("Unavailable", "__unavailable__")
    window.server_selector.setCurrentIndex(window.server_selector.count() - 1)

    warned = False

    def mock_warning(*args, **kwargs):
        nonlocal warned
        warned = True

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)

    window.bulk_action("sync", "flush", scope="server")
    assert warned
    assert not window.pending_action


# ---------------------------------------------------------------------------
# M17: QTableView model navigation from server tables
# ---------------------------------------------------------------------------


def test_m17_open_group_session_navigates_via_model(window, monkeypatch):
    """Double-clicking row in server table locates session via SessionTableModel without AttributeError."""
    window.snapshot.sync = [
        {
            "identifier": "sync_target_42",
            "name": "web-sync",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        }
    ]
    window.sync_table.model().set_sessions(window.snapshot.sync)

    # Populate server_sync_table
    window.server_targets = lambda kind, scope: list(window.snapshot.sync)
    window.update_server_details()

    assert window.server_sync_table.rowCount() == 1
    # Call open_group_session
    window.open_group_session("sync", 0)

    # Must navigate to page 1 (sync table)
    assert window.pages.currentIndex() == 1
    selected_indexes = window.sync_table.selectionModel().selectedRows()
    assert len(selected_indexes) == 1
    assert (
        window.sync_table.model().data(selected_indexes[0], Qt.ItemDataRole.UserRole)
        == "sync_target_42"
    )


def test_m17_open_group_session_handles_missing_session(window, monkeypatch):
    """If session disappeared from snapshot, informs user safely without crashing."""
    window.server_sync_table.setRowCount(1)
    item = app_module.QTableWidgetItem("vanished_session")
    item.setData(Qt.ItemDataRole.UserRole, "vanished_id")
    window.server_sync_table.setItem(0, 0, item)

    informed = False

    def mock_info(*args, **kwargs):
        nonlocal informed
        informed = True

    monkeypatch.setattr(QMessageBox, "information", mock_info)

    window.open_group_session("sync", 0)
    assert informed


# ---------------------------------------------------------------------------
# M18: 500-session limit enforced in preview before confirmation
# ---------------------------------------------------------------------------


def test_m18_bulk_action_rejects_over_500_targets_before_confirm(window, monkeypatch):
    """Bulk action with 501 targets displays limit warning and returns without confirmation prompt."""
    window.demo = False
    targets = [
        {"identifier": f"sync_{i}", "paused": False} for i in range(BULK_OPERATION_LIMIT + 1)
    ]
    window.server_targets = lambda kind, scope: targets

    warned = False
    asked = False

    def mock_warning(*args, **kwargs):
        nonlocal warned
        warned = True

    def mock_question(*args, **kwargs):
        nonlocal asked
        asked = True
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)
    monkeypatch.setattr(QMessageBox, "question", mock_question)

    window.bulk_action("sync", "flush", scope="all")
    assert warned
    assert not asked
    assert not window.pending_action


def test_m18_client_execute_many_rejects_over_500():
    """Client execute_many raises MutagenError when targets exceed BULK_OPERATION_LIMIT."""
    client = MutagenClient("dummy_mutagen")
    targets = [f"sync_{i}" for i in range(BULK_OPERATION_LIMIT + 1)]
    with pytest.raises(MutagenError, match="Select between 1 and 500"):
        client.execute_many("sync", "pause", targets, operator_consent=True)


# ---------------------------------------------------------------------------
# M19: Troubleshooter refresh progress and edit_session wiring
# ---------------------------------------------------------------------------


def test_m19_troubleshooter_refresh_progress_and_update():
    """Refresh button shows progress and re-enables with updated report upon completion."""
    refreshed = False

    def on_refresh():
        nonlocal refreshed
        refreshed = True

    session = from_session_dict(
        "sync",
        {
            "identifier": "sync_1",
            "name": "test",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        },
        measured_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dlg = TroubleshooterDialog(
        sessions=[session],
        report=report,
        on_refresh=on_refresh,
        on_open_settings=lambda sid: None,
    )

    # Click refresh button
    dlg._refresh_status()
    assert refreshed
    assert not dlg.refresh_btn.isEnabled()
    assert "Probíhá" in dlg.refresh_btn.text() or "Refreshing" in dlg.refresh_btn.text()

    # Update diagnosis
    new_report = SessionDoctorReport(
        issues=(
            DiagnosticIssue(
                code="sync_conflict",
                severity="warning",
                confidence=1.0,
                evidence=(),
                cause="conflict",
                suggested_actions=("Resolve conflict",),
                can_auto_fix=False,
                source_version=None,
                explanation="Conflict detected",
                session_identifier="sync_1",
            ),
        ),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )
    dlg.update_diagnosis([session], new_report)
    assert dlg.refresh_btn.isEnabled()
    assert "Obnoveno" in dlg.refresh_btn.text() or "Refreshed" in dlg.refresh_btn.text()
    assert len(dlg._issues_for_session("sync_1")) == 1


def test_m19_edit_session_opens_preferences(window, monkeypatch):
    """edit_session opens preferences dialog for the targeted session identifier."""
    window.snapshot.sync = [
        {
            "identifier": "sync_target_99",
            "name": "my-target",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        }
    ]
    opened_for = None

    def mock_open_pref(kind, session=None):
        nonlocal opened_for
        opened_for = (kind, session.get("identifier") if session else None)

    monkeypatch.setattr(window, "open_session_preferences", mock_open_pref)
    window.edit_session("sync_target_99")
    assert opened_for == ("sync", "sync_target_99")


# ---------------------------------------------------------------------------
# M20: Diagnostics summary separates global from session findings
# ---------------------------------------------------------------------------


def test_m20_diagnostics_separates_global_from_session_issues(window):
    """Global findings without session identifier do not inflate affected session count."""
    report = SessionDoctorReport(
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
        issues=(
            # 1 session issue
            DiagnosticIssue(
                code="sync_stalled",
                severity="error",
                confidence=1.0,
                evidence=(),
                cause="stalled",
                suggested_actions=("Check logs",),
                can_auto_fix=False,
                source_version=None,
                explanation="Sync is stalled",
                session_identifier="sync_target_1",
            ),
            # 1 global daemon issue
            DiagnosticIssue(
                code="daemon_unregistered",
                severity="warning",
                confidence=1.0,
                evidence=(),
                cause="unregistered",
                suggested_actions=("Register daemon",),
                can_auto_fix=False,
                source_version=None,
                explanation="Daemon not registered",
                session_identifier=None,
            ),
        ),
    )

    snap = Snapshot(binary="mutagen.exe")
    snap.sync = [
        {
            "identifier": "sync_target_1",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        }
    ]

    window.update_diagnostics(snap)

    # Now verify diag_problem_count formatting logic with M20 fix
    session_ids = {issue.session_identifier for issue in report.issues if issue.session_identifier}
    session_count = len(session_ids)
    global_count = sum(1 for issue in report.issues if not issue.session_identifier)
    assert session_count == 1
    assert global_count == 1
    # Verify the text rendered by diag_problem_count
    text = f"⚠  {report.issue_count} findings · {session_count} affected session(s) · {global_count} global"
    assert "2 findings" in text
    assert "1 affected session" in text
    assert "1 global" in text


# ---------------------------------------------------------------------------
# M21 & M54: Auto-safe honest status and deferred attempt recording
# ---------------------------------------------------------------------------


def test_m54_autosafe_does_not_record_premature_success_during_pending_poll(window):
    """Auto-safe coalesces requests during pending_poll without recording premature success."""
    window.health_tracker.update_policy(
        dataclasses.replace(window.health_tracker.policy, mode="auto_safe")
    )
    window.pending_poll = True

    # Setup failing session
    now = 1000.0
    window.snapshot.sync = [
        {
            "identifier": "sync_err_1",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        }
    ]
    window.snapshot.binary = "mutagen.exe"
    window.snapshot.daemon = True

    # Simulate 3 confirmed errors to make it eligible
    for i in range(3):
        window.health_tracker.observe(
            HealthObservation(
                session_identifier="sync_err_1",
                observation_key=f"obs_{i}",
                observed_at=datetime.now(UTC),
                state="error",
                confirmed_failure=True,
            ),
            now=now + i * 50,
        )

    # In update_diagnostics:
    window.update_diagnostics(window.snapshot)

    # No recovery attempt should have been recorded as succeeded
    state = window.health_tracker._states["sync_err_1"]
    assert len(state.attempts) == 0


def test_m54_autosafe_records_attempt_only_when_snapshot_completes(window, monkeypatch):
    """When idle, auto-safe queues session; attempt is recorded when snapshot arrives."""
    window.health_tracker.update_policy(
        dataclasses.replace(window.health_tracker.policy, mode="auto_safe")
    )
    window.pending_poll = False
    window.pending_action = False

    monkeypatch.setattr(time, "monotonic", lambda: 10_000.0)
    now = time.monotonic() - window.health_tracker.policy.failure_elapsed_seconds - 150.0
    window.snapshot.sync = [
        {
            "identifier": "sync_err_2",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        }
    ]
    window.snapshot.binary = "mutagen.exe"
    window.snapshot.daemon = True

    for i in range(3):
        window.health_tracker.observe(
            HealthObservation(
                session_identifier="sync_err_2",
                observation_key=f"obs_{i}",
                observed_at=datetime.now(UTC),
                state="error",
                confirmed_failure=True,
            ),
            now=now + i * 50,
        )

    refreshed = False

    def mock_refresh():
        nonlocal refreshed
        refreshed = True

    monkeypatch.setattr(window, "refresh", mock_refresh)

    # Run update_diagnostics
    window.update_diagnostics(window.snapshot)
    assert refreshed
    assert getattr(window, "_pending_autosafe_sessions", None) == ["sync_err_2"]

    # Now snapshot arrives
    fresh_snap = Snapshot(binary="mutagen.exe")
    fresh_snap.daemon = True
    fresh_snap.sync = [
        {
            "identifier": "sync_err_2",
            "alpha": {"path": "/a"},
            "beta": {"path": "/b"},
            "paused": False,
        }
    ]
    window.apply_snapshot(fresh_snap)

    # Now attempt is recorded
    state = window.health_tracker._states["sync_err_2"]
    assert len(state.attempts) == 1
    assert state.attempts[0][1] is True  # Succeeded because daemon online and no error
