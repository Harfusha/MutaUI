import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mutaui.adapters.mutagen_snapshot import from_legacy_session
from mutaui.services.session_doctor import (
    SessionDoctorContext,
    _error_code,
    _int_value,
    _issue_copy,
    _recent,
    _text,
    diagnose_sessions,
)

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures"


def _context(*rows: tuple[str, dict], **changes: object) -> SessionDoctorContext:
    sync_at = changes.pop("sync_observed_at", NOW)
    forward_at = changes.pop("forward_observed_at", NOW)
    snapshots = tuple(
        from_legacy_session(kind, row, measured_at=sync_at if kind == "sync" else forward_at)
        for kind, row in rows
    )
    values: dict[str, object] = {
        "cli_available": True,
        "daemon_running": True,
        "sync_observed_at": sync_at,
        "forward_observed_at": forward_at,
        "sessions": snapshots,
    }
    values.update(changes)
    return SessionDoctorContext(**values)  # type: ignore[arg-type]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_recent_fixture_snapshots_are_authoritative_without_findings():
    context = _context(
        ("sync", _fixture("mutagen_sync.json")),
        ("forward", _fixture("mutagen_forward.json")),
    )

    report = diagnose_sessions(context, now=NOW)

    assert report.authoritative
    assert report.session_count == 2
    assert report.issues == ()


def test_missing_cli_and_offline_daemon_never_report_all_clear_for_empty_sessions():
    missing = diagnose_sessions(
        _context(
            cli_available=False,
            daemon_running=None,
            sync_observed_at=None,
            forward_observed_at=None,
        ),
        now=NOW,
    )
    offline = diagnose_sessions(
        _context(daemon_running=False, snapshot_error="daemon unavailable"), now=NOW
    )

    assert not missing.authoritative
    assert {issue.code for issue in missing.issues} >= {"cli_missing", "snapshot_stale"}
    assert not offline.authoritative
    assert {issue.code for issue in offline.issues} >= {"daemon_offline", "snapshot_stale"}


def test_paused_and_manual_sessions_are_informational_not_errors():
    paused = _fixture("mutagen_sync.json")
    paused["paused"] = True
    paused["alpha"]["connected"] = False
    manual = _fixture("mutagen_forward.json")
    manual["mode"] = "manual"
    manual["source"]["connected"] = False

    report = diagnose_sessions(_context(("sync", paused), ("forward", manual)), now=NOW)

    assert {issue.code for issue in report.issues} == {"intentional_pause", "manual_mode"}
    assert all(issue.severity == "info" for issue in report.issues)


def test_sync_root_state_and_excluded_conflicts_are_included():
    session = _fixture("mutagen_sync.json")
    session.update(status=2, excludedConflicts=3)

    report = diagnose_sessions(_context(("sync", session)), now=NOW)

    assert {issue.code for issue in report.issues} == {"root_problem", "conflicts"}
    assert all(issue.session_identifier == session["identifier"] for issue in report.issues)


def test_ssh_authentication_and_host_trust_errors_keep_evidence():
    auth = _fixture("mutagen_sync.json")
    auth["beta"]["lastError"] = "SSH authentication failed: permission denied"
    trust = _fixture("mutagen_forward.json")
    trust["destination"]["lastError"] = "unknown host key"

    report = diagnose_sessions(_context(("sync", auth), ("forward", trust)), now=NOW)

    found = {issue.code: issue for issue in report.issues}
    assert {"ssh_authentication", "ssh_host_trust"} <= found.keys()
    assert found["ssh_authentication"].technical_detail
    assert found["ssh_authentication"].observed_at == NOW
    assert all(not issue.can_auto_fix for issue in found.values())


def test_disconnected_sync_status_only_flags_remote_ssh_sessions():
    disconnected = _fixture("mutagen_sync.json")
    disconnected["status"] = 0
    local = _fixture("mutagen_sync.json")
    local["identifier"] = "local-disconnected"
    local["status"] = 0
    local["beta"] = {"protocol": 0, "path": "C:\\other"}

    report = diagnose_sessions(_context(("sync", disconnected), ("sync", local)), now=NOW)

    assert [issue.code for issue in report.issues] == ["ssh_disconnected"]
    assert report.issues[0].session_identifier == disconnected["identifier"]


def test_scan_transition_staging_permissions_symlink_and_forward_errors_are_classified():
    sync = _fixture("mutagen_sync.json")
    sync["alpha"].update(
        scanProblems=["scan failed", "permission denied", "symlink target invalid"],
        transitionProblems=["transition failed"],
    )
    staged = _fixture("mutagen_sync.json")
    staged["identifier"] = "staging-session"
    staged["lastError"] = "temporary directory staging failed"
    forward = _fixture("mutagen_forward.json")
    forward["source"]["connected"] = False
    forward["destination"]["connected"] = False

    report = diagnose_sessions(
        _context(("sync", sync), ("sync", staged), ("forward", forward)), now=NOW
    )

    codes = {issue.code for issue in report.issues}
    assert {
        "scan_problem",
        "transition_problem",
        "permission_problem",
        "symlink_problem",
        "staging_problem",
        "forward_source_problem",
        "forward_destination_problem",
    } <= codes
    assert all(not issue.can_auto_fix for issue in report.issues)


def test_error_classification_covers_all_root_problem_phrases():
    phrases = (
        "root is missing",
        "root missing",
        "root is empty",
        "root changed type",
        "deleted root",
        "halted: empty root",
        "halted: root type change",
    )

    assert {_error_code(phrase, kind="sync") for phrase in phrases} == {"root_problem"}


def test_doctor_deduplicates_same_session_scan_findings_and_reports_excluded_counters():
    session = _fixture("mutagen_sync.json")
    session["alpha"].update(scanProblems=["scan failed"])
    session.update(excludedScanProblems=2, excludedTransitionProblems=1)

    report = diagnose_sessions(_context(("sync", session)), now=NOW)

    scan_findings = [issue for issue in report.issues if issue.code == "scan_problem"]
    assert len(scan_findings) == 1
    assert scan_findings[0].evidence


def test_generic_last_errors_and_problems_fall_back_to_session_error():
    last_error = _fixture("mutagen_sync.json")
    last_error["lastError"] = "unclassified backend failure"
    problem = _fixture("mutagen_sync.json")
    problem["identifier"] = "problem-session"
    problem["alpha"]["scanProblems"] = ["unclassified problem"]

    context = _context(("sync", last_error), ("sync", problem))
    second = replace(context.sessions[1], state="error")
    context = replace(context, sessions=(replace(context.sessions[0], state="error"), second))
    report = diagnose_sessions(context, now=NOW)

    assert [issue.code for issue in report.issues].count("session_error") == 2


def test_forward_failure_without_an_endpoint_identifier_uses_generic_error_code():
    assert _error_code("connection refused", kind="forward") is None
    assert (
        _error_code("connection refused", kind="forward", endpoint_name="source")
        == "forward_source_problem"
    )


def test_empty_generic_error_session_gets_session_error_issue():
    context = _context(("sync", _fixture("mutagen_sync.json")))
    error = replace(context.sessions[0], state="error", conflicts=(), problems=(), counters={})

    report = diagnose_sessions(replace(context, sessions=(error,)), now=NOW)

    assert [issue.code for issue in report.issues] == ["session_error"]


def test_stale_snapshots_and_stale_resource_samples_are_not_authoritative_or_current():
    session = _fixture("mutagen_sync.json")
    session["conflicts"] = [{"path": "file.txt"}]
    context = _context(
        ("sync", session),
        sync_observed_at=NOW - timedelta(minutes=5),
        resource_observed_at=NOW - timedelta(minutes=5),
        cpu_percent=99.0,
    )

    report = diagnose_sessions(context, now=NOW)

    assert not report.authoritative
    assert {issue.code for issue in report.issues} == {"snapshot_stale", "conflicts"}
    assert all(not issue.can_auto_fix for issue in report.issues)


def test_high_cpu_requires_a_recent_measurement():
    current = diagnose_sessions(_context(resource_observed_at=NOW, cpu_percent=91.0), now=NOW)
    unknown = diagnose_sessions(_context(resource_observed_at=None, cpu_percent=99.0), now=NOW)

    assert any(issue.code == "high_cpu" for issue in current.issues)
    assert all(issue.code != "high_cpu" for issue in unknown.issues)


def test_session_doctor_helpers_fail_closed_for_untyped_and_future_evidence():
    assert _recent(NOW - timedelta(seconds=60), NOW, 60)
    assert not _recent(NOW + timedelta(seconds=1), NOW, 60)
    assert _int_value(True) == 0
    assert _int_value(-1) == 0
    assert _int_value("9") == 0
    assert _int_value(9) == 9
    assert _text({"host": "remote", "code": 3}) == "host: remote code: 3"
    assert _text(object()).startswith("<object object at")
    assert _error_code("permission denied", kind="sync") == "permission_problem"
    assert _error_code("unknown diagnostic", kind="sync") is None
    assert _error_code("connection refused", kind="forward") is None
    assert _issue_copy("unknown") == (
        "Mutagen reported a session issue.",
        "Review the native evidence.",
        "https://mutagen.io/documentation/synchronization/",
    )
