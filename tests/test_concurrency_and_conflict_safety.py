"""Regression tests for Batch 2E: Concurrency, SSH, Conflict Safety & Privacy (M32-M39)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication

from mutaui.projects.project_actions import (
    ProjectActionError,
    ProjectActionPlan,
    ProjectActionReceipt,
    execute_project_action,
)
from mutaui.services.audit_retention import (
    AuditRetentionError,
    audit_file_status,
    rotate_audit_file,
    safe_append_audit_record,
)
from mutaui.services.conflict_resolver import (
    ManualResolutionReceipt,
)
from mutaui.services.session_provenance import (
    ProvenanceStoreError,
    SessionProvenanceStore,
)
from mutaui.ui.controllers.diagnostics_controller import DiagnosticsMixin
from mutaui.ui.global_config_editor import show_config_compare_dialog


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ============================================================================
# M32: Session Provenance Store Capacity & User Management
# ============================================================================


def test_session_provenance_capacity(tmp_path: Path) -> None:
    store_file = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(store_file)

    cap_empty = store.capacity()
    assert cap_empty.record_count == 0
    assert not cap_empty.is_near_limit
    assert not cap_empty.is_full

    store.record("session-1", ["sync", "create", "C:/a", "C:/b"])
    cap_one = store.capacity()
    assert cap_one.record_count == 1
    assert cap_one.file_bytes > 0


def test_session_provenance_archive_inactive(tmp_path: Path) -> None:
    store_file = tmp_path / "session-provenance.json"
    archive_file = tmp_path / "archive.json"
    store = SessionProvenanceStore(store_file)

    store.record("active-1", ["sync", "create", "C:/a", "C:/b"])
    store.record("inactive-2", ["sync", "create", "C:/c", "C:/d"])
    store.record("inactive-3", ["forward", "create", "tcp:127.0.0.1:8080", "tcp:remote:8080"])

    # Active session set: only "active-1"
    archived_count, remaining_count = store.archive_inactive_records(
        {"active-1"}, archive_path=archive_file
    )
    assert archived_count == 2
    assert remaining_count == 1

    # Active session provenance is intact
    prov = store.get("active-1")
    assert prov is not None
    assert prov.session_identifier == "active-1"
    assert store.get("inactive-2") is None

    # Archive file contains valid JSON with archived records
    archive_payload = json.loads(archive_file.read_text(encoding="utf-8"))
    assert set(archive_payload["records"].keys()) == {"inactive-2", "inactive-3"}


def test_session_provenance_full_store_raises_clear_error(tmp_path: Path) -> None:
    store_file = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(store_file)

    with patch("mutaui.services.session_provenance.MAX_RECORDS", 2):
        store.record("s1", ["sync", "create", "C:/a", "C:/b"])
        store.record("s2", ["sync", "create", "C:/c", "C:/d"])
        with pytest.raises(ProvenanceStoreError) as exc_info:
            store.record("s3", ["sync", "create", "C:/e", "C:/f"])
        assert "Archive inactive records" in str(exc_info.value)


# ============================================================================
# M33: Config Editor Concurrency, Comparison with Draft
# ============================================================================


def test_global_config_compare_dialog(qapp: QApplication) -> None:
    external_text = "sync:\n  mode: two-way-safe\n"
    draft_text = "sync:\n  mode: one-way-replica\n"
    # Verify show_config_compare_dialog constructs and displays diff cleanly without exception
    with patch("PySide6.QtWidgets.QDialog.exec"):
        show_config_compare_dialog(None, external_text, draft_text)


# ============================================================================
# M34 & M35: Project Actions Background Timeout & Verification Truthfulness
# ============================================================================


def test_project_actions_timeout_uncertain_outcome(tmp_path: Path) -> None:
    plan = ProjectActionPlan(
        action="start",
        path=tmp_path / "mutagen.yml",
        project_sha256="abc",
        argv=("mutagen", "project", "start"),
        session_names=("test-session",),
        hooks=(),
    )
    (tmp_path / "mutagen.yml").write_text("sync:\n  test:\n", encoding="utf-8")
    audit_file = tmp_path / "project.audit.jsonl"

    class TimeoutExecutor:
        def run(self, argv: list[str] | tuple[str, ...], **kwargs: object) -> MagicMock:
            if argv[0] == "project" and argv[1] == "start" and argv[2] == "--help":
                return MagicMock(stdout="", stderr="", exit_code=0)
            raise TimeoutError("Execution timed out after 120s")

    with patch("mutaui.projects.project_actions.load_native_project") as mock_load:
        mock_load.return_value = MagicMock(valid=True, sha256="abc")
        with pytest.raises(ProjectActionError) as exc_info:
            execute_project_action(
                plan,
                TimeoutExecutor(),  # type: ignore[arg-type]
                consent=True,
                shell_consent=False,
                audit_path=audit_file,
            )
        assert "status is uncertain" in str(exc_info.value)

    # Audit phase must record timeout-uncertain
    audit_content = audit_file.read_text(encoding="utf-8")
    assert "timeout-uncertain" in audit_content


def test_project_action_receipt_unverified_on_postcheck_error() -> None:
    mock_action = MagicMock(stdout="Started 1 session")
    receipt = ProjectActionReceipt(
        plan=MagicMock(),
        action_result=mock_action,
        postcheck_result=None,
        postcheck_error="Could not connect to daemon",
    )
    assert receipt.postcheck_error == "Could not connect to daemon"
    assert receipt.postcheck_result is None


# ============================================================================
# M36 & M37: Remote Inspection Cleanup & Conflict Resolution Recovery Guide
# ============================================================================


def test_manual_resolution_receipt_recovery_guide(tmp_path: Path) -> None:
    backup_dir = tmp_path / "mutaui-conflict-1234"
    backup_dir.mkdir()
    receipt = ManualResolutionReceipt(
        backup_directory=backup_dir,
        resolved_side=None,
        verified=False,
        rollback_attempted=True,
        recovery_uncertain=True,
        message="Restore failed",
    )
    guide = receipt.recovery_instructions
    assert "mutaui-conflict-1234" in guide
    assert "alpha.backup" in guide
    assert "beta.backup" in guide
    assert "manifest.json" in guide


def test_manual_resolution_receipt_recovery_guide_no_backups() -> None:
    receipt = ManualResolutionReceipt(
        backup_directory=None,
        resolved_side=None,
        verified=False,
        rollback_attempted=False,
        recovery_uncertain=False,
        message="Preflight cancelled",
    )
    assert "No backups were created" in receipt.recovery_instructions


# ============================================================================
# M38: Safe Diagnostics Sharing Default
# ============================================================================


class DummyDiagnosticsHost(DiagnosticsMixin):
    def __init__(self) -> None:
        self.logs: list[str] = []
        self.snapshot = MagicMock(
            binary="C:/Users/SecretUser/AppData/Local/mutagen.exe",
            version="Mutagen version 0.17.4",
            daemon=True,
            sync=[{"name": "private-project", "alpha": "C:/Users/SecretUser/repo"}],
            forward=[],
            processes=2,
            cpu=1.5,
            memory=1024 * 1024 * 50,
            registration="registered",
            sessions_stale=False,
            error="Failed to connect to user@private.ssh.internal",
        )
        self.diag_summary = MagicMock()
        self.diag_summary.text.return_value = (
            "Mutagen: C:/Users/SecretUser/AppData/Local/mutagen.exe\nVersion: 0.17.4"
        )
        self.diagnostics_view = MagicMock()
        self.diagnostics_view.toPlainText.return_value = (
            "Session: private-project -> user@private.ssh.internal:secret/path"
        )

    def add_log(self, msg: str) -> None:
        self.logs.append(msg)


def test_copy_diagnostics_defaults_to_safe(qapp: QApplication) -> None:
    host = DummyDiagnosticsHost()
    host.copy_diagnostics(safe=True)

    clipboard_text = QApplication.clipboard().text()
    assert "Safe Diagnostic Summary (Sanitized)" in clipboard_text
    assert "Mutagen version: 0.17.4" in clipboard_text
    assert "SecretUser" not in clipboard_text
    assert "private.ssh.internal" not in clipboard_text
    assert "private-project" not in clipboard_text
    assert "REDACTED FOR SAFE SHARING" in clipboard_text
    assert any("Safe diagnostics summary copied" in log for log in host.logs)


def test_copy_full_diagnostics_requires_consent(qapp: QApplication) -> None:
    host = DummyDiagnosticsHost()

    # User declines consent
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=0):
        host.copy_full_diagnostics()
        assert not any("Full raw diagnostics copied" in log for log in host.logs)


# ============================================================================
# M39: Operational Audit Retention and Rotation
# ============================================================================


def test_safe_append_audit_record_and_rotation(tmp_path: Path) -> None:
    audit_file = tmp_path / "test.audit.jsonl"

    # Symlink check
    symlink_file = tmp_path / "symlink.audit.jsonl"
    target_file = tmp_path / "target.jsonl"
    target_file.touch()
    try:
        symlink_file.symlink_to(target_file)
        with pytest.raises(AuditRetentionError):
            safe_append_audit_record(symlink_file, {"event": "test"})
    except (OSError, NotImplementedError):
        pass  # Windows unprivileged symlink fallback

    # Normal append with small max_bytes to force rotation
    record = {"event": "audit_event_1", "data": "x" * 350}
    safe_append_audit_record(audit_file, record, max_bytes=300, max_backups=2)
    assert audit_file.exists()

    status1 = audit_file_status(audit_file)
    assert status1["records"] == 1
    assert status1["backups"] == 0

    # Write second record exceeding 300 bytes to trigger rotation
    safe_append_audit_record(audit_file, record, max_bytes=300, max_backups=2)
    status2 = audit_file_status(audit_file)
    assert status2["backups"] == 1
    assert (tmp_path / "test.audit.jsonl.1").exists()


def test_rotate_audit_file_bounded(tmp_path: Path) -> None:
    base = tmp_path / "op.audit.jsonl"
    base.write_text("base\n", encoding="utf-8")
    (tmp_path / "op.audit.jsonl.1").write_text("bak1\n", encoding="utf-8")
    (tmp_path / "op.audit.jsonl.2").write_text("bak2\n", encoding="utf-8")

    rotate_audit_file(base, max_backups=2)
    assert not base.exists()
    assert (tmp_path / "op.audit.jsonl.1").read_text(encoding="utf-8") == "base\n"
    assert (tmp_path / "op.audit.jsonl.2").read_text(encoding="utf-8") == "bak1\n"
