"""Unit tests for the interactive TroubleshooterDialog."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from PySide6.QtWidgets import QApplication

from mutaui.adapters.mutagen_snapshot import from_legacy_session
from mutaui.domain.models import DiagnosticIssue, SessionSnapshot
from mutaui.services.session_doctor import (
    SessionDoctorReport,
    get_diagnostic_remedy,
)
from mutaui.ui.troubleshooter_dialog import TroubleshooterDialog


def _dummy_session(
    identifier: str = "sess-1",
    name: str = "web-sync",
    state: str = "Watching",
    last_error: str = "",
) -> SessionSnapshot:
    raw: dict[str, Any] = {
        "identifier": identifier,
        "name": name,
        "status": 0 if state == "Disconnected" else 7,
        "lastError": last_error,
        "alpha": {"path": "C:\\repo", "connected": True},
        "beta": {"path": "/var/www", "host": "devbox", "connected": state != "Disconnected"},
    }
    return from_legacy_session(
        "sync",
        raw,
        measured_at=datetime.now(UTC),
    )


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_troubleshooter_dialog_empty_sessions() -> None:
    _app()
    dialog = TroubleshooterDialog(sessions=(), report=None)

    assert dialog.session_combo.count() == 1
    assert "No sessions" in dialog.session_combo.itemText(
        0
    ) or "Žádné relace" in dialog.session_combo.itemText(0)
    dialog.close()


def test_troubleshooter_dialog_healthy_session() -> None:
    _app()
    session = _dummy_session(identifier="healthy-1", name="Healthy Sync", state="Watching")
    report = SessionDoctorReport(
        issues=(),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dialog = TroubleshooterDialog(sessions=[session], report=report)

    assert dialog.session_combo.count() == 1
    assert "Healthy Sync" in dialog.session_combo.itemText(0)
    assert "🟢" in dialog.session_combo.itemText(0)
    dialog.close()


def test_troubleshooter_dialog_with_detected_issues() -> None:
    _app()
    session = _dummy_session(
        identifier="locked-1",
        name="Locked Project",
        state="Halted",
        last_error="open C:\\repo\\index.lock: The process cannot access the file because it is being used by another process.",
    )
    issue = DiagnosticIssue(
        code="file_locked",
        severity="error",
        confidence=0.98,
        evidence=(),
        cause="A file is locked by another running program or process.",
        explanation="A file is locked by another running program or process.",
        suggested_actions=("Close the program locking the file.",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        technical_detail="open C:\\repo\\index.lock: The process cannot access the file because it is being used by another process.",
        article_url="https://mutagen.io/documentation/synchronization/",
        session_identifier="locked-1",
        observed_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(issue,),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dialog = TroubleshooterDialog(sessions=[session], report=report, selected_identifier="locked-1")

    assert "🔴" in dialog.session_combo.itemText(0)
    assert dialog.session_combo.currentData() == "locked-1"
    dialog.close()


def test_troubleshooter_dialog_ssh_host_key_changed_command() -> None:
    _app()
    session = _dummy_session(
        identifier="ssh-1",
        name="Remote Box",
        state="Disconnected",
        last_error="ssh: connect to host dev.server.com: Host key verification failed",
    )
    issue = DiagnosticIssue(
        code="ssh_host_key_changed",
        severity="error",
        confidence=0.98,
        evidence=(),
        cause="SSH host key verification failed because the remote host key has changed.",
        explanation="SSH host key verification failed because the remote host key has changed.",
        suggested_actions=("Verify host and update known_hosts.",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        technical_detail="ssh: connect to host dev.server.com: Host key verification failed",
        article_url="https://mutagen.io/documentation/synchronization/",
        session_identifier="ssh-1",
        observed_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(issue,),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dialog = TroubleshooterDialog(sessions=[session], report=report)

    remedy = get_diagnostic_remedy(
        "ssh_host_key_changed",
        language="en",
        detail="ssh: connect to host dev.server.com: Host key verification failed",
    )
    assert "dev.server.com" in remedy.quick_command
    dialog.close()


def test_troubleshooter_dialog_actions() -> None:
    _app()
    refreshed = []
    opened_settings = []

    session = _dummy_session(identifier="act-1", name="Action Test", state="Error")
    dialog = TroubleshooterDialog(
        sessions=[session],
        report=None,
        on_refresh=lambda: refreshed.append(True),
        on_open_settings=lambda sid: opened_settings.append(sid),
    )

    # Test copy diagnostics
    dialog._copy_diagnostic_summary()
    clipboard_text = QApplication.clipboard().text()
    assert "Action Test" in clipboard_text

    # Test refresh callback
    dialog.refresh_btn.click()
    assert refreshed == [True]

    # Test open settings callback
    dialog.settings_btn.click()
    assert opened_settings == ["act-1"]
    dialog.close()


def test_troubleshooter_dialog_warning_session() -> None:
    _app()
    session = _dummy_session(identifier="warn-1", name="Warning Session", state="Watching")
    issue = DiagnosticIssue(
        code="conflicts",
        severity="warning",
        confidence=0.98,
        evidence=(),
        cause="Mutagen reports file conflicts.",
        explanation="Mutagen reports file conflicts.",
        suggested_actions=("Review conflict details.",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        technical_detail="1 file conflict",
        article_url="https://mutagen.io/documentation/synchronization/",
        session_identifier="warn-1",
        observed_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(issue,),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dialog = TroubleshooterDialog(sessions=[session], report=report)
    assert "🟠" in dialog.session_combo.itemText(0)
    dialog.close()


def test_troubleshooter_dialog_halted_fallback_card() -> None:
    _app()
    raw: dict[str, Any] = {
        "identifier": "halt-1",
        "name": "Halted Raw",
        "status": 1,
        "lastError": "Halted: empty root",
        "alpha": {"path": "C:\\empty", "connected": True},
        "beta": {"path": "/var/empty", "connected": True},
    }
    session = from_legacy_session("sync", raw, measured_at=datetime.now(UTC))
    report = SessionDoctorReport(
        issues=(),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dialog = TroubleshooterDialog(sessions=[session], report=report)
    assert "🔴" in dialog.session_combo.itemText(0)
    dialog.close()


def test_troubleshooter_dialog_quick_command_click() -> None:
    _app()
    session = _dummy_session(identifier="inotify-1", name="Inotify Limit", state="Error")
    issue = DiagnosticIssue(
        code="inotify_limit",
        severity="error",
        confidence=0.98,
        evidence=(),
        cause="Linux inotify file watch limit reached.",
        explanation="Linux inotify file watch limit reached.",
        suggested_actions=("Increase watch limit.",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        technical_detail="user limit of inotify watches reached",
        article_url="https://mutagen.io/documentation/synchronization/",
        session_identifier="inotify-1",
        observed_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(issue,),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )

    dialog = TroubleshooterDialog(sessions=[session], report=report)

    from PySide6.QtWidgets import QPushButton

    copy_btns = [
        btn
        for btn in dialog.findChildren(QPushButton)
        if "Kopírovat příkaz" in btn.text() or "Copy Command" in btn.text()
    ]
    assert len(copy_btns) == 1
    remedy = get_diagnostic_remedy("inotify_limit", language="en")
    dialog._copy_command(remedy.quick_command, copy_btns[0])
    QApplication.processEvents()
    assert "Zkopírováno!" in copy_btns[0].text() or "Copied!" in copy_btns[0].text()
    if QApplication.clipboard().text():
        assert "sudo sysctl" in QApplication.clipboard().text()
    dialog.close()


def test_troubleshooter_dialog_empty_selection_and_no_settings() -> None:
    _app()
    dialog = TroubleshooterDialog(sessions=(), report=None)
    dialog.session_combo.setCurrentIndex(-1)
    dialog._open_selected_settings()
    dialog._copy_diagnostic_summary()
    dialog._refresh_status()
    dialog.close()


def test_open_troubleshooter_controller_flow(monkeypatch: Any) -> None:
    _app()
    from types import SimpleNamespace

    import mutaui.ui.controllers.diagnostics_controller as diag_ctrl

    captured = []

    class DummyDialog:
        def __init__(self, sessions: Any, report: Any, **kwargs: Any) -> None:
            captured.append((sessions, report, kwargs))

        def exec(self) -> None:
            captured.append("exec")

    monkeypatch.setattr(diag_ctrl, "TroubleshooterDialog", DummyDialog)

    fake_window = SimpleNamespace(
        snapshot=SimpleNamespace(
            binary="mutagen.exe",
            daemon=True,
            version="0.18.1",
            error="",
            sessions_stale=False,
            cpu=10.0,
            resource_observed_at=datetime.now(UTC),
            sync=[
                None,
                {},
                {"identifier": 42},
                {"identifier": "sync-test-1", "name": "Sync Test", "status": 7},
            ],
            forward=[{"identifier": "fwd-test-1", "name": "Fwd Test", "status": 0}],
            sync_observed_at=datetime.now(UTC),
            forward_observed_at=datetime.now(UTC),
        ),
        refresh=lambda: None,
        edit_session=lambda sid: None,
    )

    diag_ctrl.DiagnosticsMixin.open_troubleshooter(fake_window, "sync-test-1")

    assert len(captured) == 2
    sessions, report, kwargs = captured[0]
    assert len(sessions) == 2
    assert kwargs["selected_identifier"] == "sync-test-1"
    assert captured[1] == "exec"


def test_troubleshooter_dialog_copy_summary_with_issue_details() -> None:
    _app()
    session = _dummy_session(identifier="copy-1", name="Copy Detail", state="Error")
    issue = DiagnosticIssue(
        code="inotify_limit",
        severity="error",
        confidence=0.98,
        evidence=(),
        cause="Linux inotify limit.",
        explanation="Linux inotify watch limit reached.",
        suggested_actions=("Increase watches.",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        technical_detail="user limit of inotify watches reached",
        article_url="https://mutagen.io/documentation/synchronization/",
        session_identifier="copy-1",
        observed_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(issue,),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=1,
        stale_kinds=(),
    )
    dialog = TroubleshooterDialog(sessions=[session], report=report)
    dialog._copy_diagnostic_summary()
    text = QApplication.clipboard().text()
    assert "user limit of inotify watches" in text
    assert "sudo sysctl" in text
    dialog.close()


def test_troubleshooter_dialog_switching_and_empty_detail_and_no_url() -> None:
    _app()
    healthy = _dummy_session(identifier="h-1", name="Healthy", state="Watching")
    err = _dummy_session(identifier="e-1", name="Error", state="Error")
    issue = DiagnosticIssue(
        code="session_error",
        severity="error",
        confidence=0.98,
        evidence=(),
        cause="Session error.",
        explanation="Session error without detail.",
        suggested_actions=("Check logs.",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        technical_detail="",
        article_url="",
        session_identifier="e-1",
        observed_at=datetime.now(UTC),
    )
    report = SessionDoctorReport(
        issues=(issue,),
        authoritative=True,
        generated_at=datetime.now(UTC),
        session_count=2,
        stale_kinds=(),
    )
    # Start with healthy session
    dialog = TroubleshooterDialog(sessions=[healthy, err], report=report, selected_identifier="h-1")
    # Switch to error session (cleans layout containing stretch spacer item)
    dialog.session_combo.setCurrentIndex(1)
    dialog.close()
