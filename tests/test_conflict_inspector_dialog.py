from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PySide6.QtCore import QProcess
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QLabel, QMessageBox

import mutaui.ui.conflict_inspector_dialog as dialog_module
from mutaui.domain.models import Endpoint, SessionIdentity, SessionSnapshot
from mutaui.services.conflict_recommendations import (
    ConflictChoiceRule,
    ConflictRecommendationPolicy,
)
from mutaui.services.remote_inspector import RemoteInspectionArtifact
from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog


def _app():
    return QApplication.instance() or QApplication([])


def _snapshot(
    tmp_path: Path,
    *,
    alpha: Endpoint | None = None,
    beta: Endpoint | None = None,
    conflicts: tuple[object, ...] = (({"root": "src/main.py"}),),
    config: dict[str, object] | None = None,
    stale_reason: str | None = None,
) -> SessionSnapshot:
    return SessionSnapshot(
        identity=SessionIdentity("sync", "sync-id", "Build tree"),
        native_config=config or {},
        alpha_or_source=alpha or Endpoint("local", str(tmp_path), path=str(tmp_path)),
        beta_or_destination=beta,
        state="conflicts",
        conflicts=conflicts,
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
        stale_reason=stale_reason,
    )


def _dialog(tmp_path: Path, **kwargs):
    _app()
    return ConflictInspectorDialog((_snapshot(tmp_path, **kwargs),))


def test_empty_conflict_dialog_and_recommendation_status_paths(tmp_path):
    dialog = _dialog(tmp_path, conflicts=(), config={"excludedConflicts": 2})
    assert dialog.table.rowCount() == 0
    assert not dialog.manage_recommendations.isEnabled()
    assert "settings location" in dialog.manage_recommendations.toolTip()
    assert any(
        "omitted 2 additional conflict(s)" in label.text() for label in dialog.findChildren(QLabel)
    )
    assert "disabled" in dialog.recommendation_status.text()
    dialog._show_details()
    dialog._manage_recommendations()


def test_conflict_filter_and_selection_populate_details(tmp_path):
    dialog = _dialog(
        tmp_path,
        conflicts=(
            {
                "root": "src/main.py",
                "alphaChanges": [{"path": "src/main.py", "old": None, "new": {}}],
                "betaChanges": [{"path": "src/main.py", "old": {}, "new": None}],
            },
            {"root": "docs/readme.md"},
        ),
    )
    assert dialog.table.rowCount() == 2
    dialog.search.setText("src/main.py")
    assert dialog.table.rowCount() == 1
    dialog._show_details()
    assert "Exact session identifier: sync-id" in dialog.details.toPlainText()
    assert "added" in dialog.details.toPlainText()
    dialog.search.setText("missing")
    assert dialog.table.rowCount() == 0
    assert not dialog.open_alpha.isEnabled()
    assert not dialog.inspect_beta.isEnabled()
    assert dialog._selected() is None


def test_local_conflict_open_requires_contained_existing_path(tmp_path, monkeypatch):
    root = tmp_path / "sync"
    root.mkdir()
    target = root / "src" / "main.py"
    target.parent.mkdir()
    target.write_text("local", encoding="utf-8")
    dialog = _dialog(
        tmp_path,
        alpha=Endpoint("local", str(root), path=str(root)),
        conflicts=(({"root": "src/main.py"}),),
    )
    opened = []
    monkeypatch.setattr(dialog_module.QDesktopServices, "openUrl", lambda url: opened.append(url))
    dialog._open_selected("alpha")
    assert len(opened) == 1

    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append("info"))
    dialog._open_selected("beta")
    assert messages == ["info"]


def test_remote_endpoint_and_inspection_cancel_guards(tmp_path, monkeypatch):
    ssh = Endpoint("ssh", "alice@example:/srv", host="example", user="alice", path="/srv")
    dialog = _dialog(tmp_path, beta=ssh, conflicts=(({"root": "src/main.py"}),))
    record = dialog._selected()
    assert record is not None
    assert dialog._remote_endpoint(record, "beta") is None
    assert dialog._remote_endpoint(record, "alpha") is None
    dialog_with_audit = ConflictInspectorDialog(
        (_snapshot(tmp_path, beta=ssh),), audit_path=tmp_path / "audit.jsonl"
    )
    audited_record = dialog_with_audit._selected()
    assert audited_record is not None
    assert dialog_with_audit._remote_endpoint(audited_record, "beta") == ssh

    dialog._inspect_selected_remote("beta")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    dialog_with_audit._inspect_selected_remote("beta")
    assert dialog_with_audit._inspection_task is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("/tmp/key", ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    dialog_with_audit._inspect_selected_remote("beta")
    assert dialog_with_audit._inspection_task is None


@pytest.mark.parametrize(
    ("host", "user", "path", "audit_path"),
    [
        (None, "alice", "/srv", "audit"),
        ("example", None, "/srv", "audit"),
        ("example", "alice", None, "audit"),
        ("example", "alice", "/srv", None),
    ],
)
def test_remote_endpoint_rejects_incomplete_or_stale_target(tmp_path, host, user, path, audit_path):
    endpoint = Endpoint("ssh", "incomplete", host=host, user=user, path=path)
    snapshot = _snapshot(tmp_path, beta=endpoint)
    dialog = ConflictInspectorDialog(
        (snapshot,), audit_path=tmp_path / audit_path if audit_path else None
    )

    record = dialog._selected()
    assert record is not None
    assert dialog._remote_endpoint(record, "beta") is None


def test_remote_endpoint_rejects_stale_snapshot_for_existing_conflict_record(tmp_path):
    ssh = Endpoint("ssh", "alice@example:/srv", host="example", user="alice", path="/srv")
    current = _snapshot(tmp_path, beta=ssh)
    dialog = ConflictInspectorDialog((current,), audit_path=tmp_path / "audit.jsonl")
    record = dialog._selected()
    assert record is not None
    dialog._snapshots[record.session_identifier] = _snapshot(
        tmp_path, beta=ssh, stale_reason="snapshot is stale"
    )

    assert dialog._remote_endpoint(record, "beta") is None


def test_inspection_completion_handles_error_unexpected_and_changed_target(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("warning"))
    dialog._inspection_completed(None, RuntimeError("network failed"))
    assert messages == ["warning"]
    dialog._inspection_completed(object(), None)
    assert dialog._remote_artifact is None

    temp = TemporaryDirectory()
    artifact_path = Path(temp.name) / "copy"
    artifact_path.write_text("remote", encoding="utf-8")
    artifact = RemoteInspectionArtifact(
        artifact_path, "/srv/main.py", 6, "digest", True, None, "host-key", temp
    )
    dialog._inspection_target = ("different-id", "other.py")
    dialog._inspection_completed(artifact, None)
    assert dialog._remote_artifact is None
    assert not artifact_path.exists()


def test_remote_copy_compare_guards_and_diff_lifecycle(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append("info"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("warning"))
    dialog._open_remote_copy()
    dialog._compare_remote_with_local()
    assert messages == []

    dialog._diff_process = None
    dialog._close_pending = False
    dialog._diff_finished()
    dialog._diff_error(QProcess.ProcessError.FailedToStart)
    assert messages == []


def test_recommendation_policy_load_and_advice_are_exact_and_manual(tmp_path):
    rule = ConflictChoiceRule("rule1", "src/main.py", "alpha", "Prefer reviewed source")
    policy = ConflictRecommendationPolicy((rule,), enabled=True)
    dialog = ConflictInspectorDialog((_snapshot(tmp_path),), recommendation_policy=policy)
    assert "Exact-path advice is enabled" in dialog.recommendation_status.text()
    assert "ADVISORY ONLY" in dialog.details.toPlainText()
    assert "Preferred side: ALPHA" in dialog.details.toPlainText()

    invalid_policy = tmp_path / "invalid-policy.json"
    invalid_policy.write_text("not json", encoding="utf-8")
    failed = ConflictInspectorDialog((_snapshot(tmp_path),), recommendation_path=invalid_policy)
    assert "could not be loaded" in failed.recommendation_status.text()


def test_recommendation_manager_cancel_save_and_write_failure(tmp_path, monkeypatch):
    policy_path = tmp_path / "recommendations.json"
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("warning"))

    class Manager:
        policy = ConflictRecommendationPolicy(
            (ConflictChoiceRule("rule1", "src/main.py", "beta", "Review BETA"),),
            enabled=True,
        )

        def __init__(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(dialog_module, "ConflictRecommendationsDialog", Manager)
    dialog = ConflictInspectorDialog((_snapshot(tmp_path),), recommendation_path=policy_path)
    dialog._manage_recommendations()
    assert not policy_path.exists()

    Manager.exec = lambda self: QDialog.DialogCode.Accepted
    dialog._manage_recommendations()
    assert policy_path.is_file()
    assert dialog._recommendation_policy.enabled
    assert "Exact-path advice is enabled" in dialog.recommendation_status.text()

    monkeypatch.setattr(
        dialog_module,
        "save_recommendation_policy",
        lambda *_args: (_ for _ in ()).throw(dialog_module.RecommendationPolicyError("disk full")),
    )
    dialog._manage_recommendations()
    assert messages == ["warning"]


def test_inspection_completion_success_replaces_artifact_and_close_cleans(tmp_path):
    root = tmp_path / "sync"
    target = root / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("local copy", encoding="utf-8")
    snapshot = _snapshot(
        tmp_path,
        alpha=Endpoint("local", str(root), path=str(root)),
        conflicts=(({"root": "src/main.py"}),),
    )
    dialog = ConflictInspectorDialog((snapshot,))

    old_temp = TemporaryDirectory()
    old_path = Path(old_temp.name) / "old"
    old_path.write_text("old", encoding="utf-8")
    old_artifact = RemoteInspectionArtifact(old_path, "/old", 3, "old", True, None, "key", old_temp)
    new_temp = TemporaryDirectory()
    new_path = Path(new_temp.name) / "remote"
    new_path.write_text("remote", encoding="utf-8")
    new_artifact = RemoteInspectionArtifact(
        new_path, "/remote", 6, "new", False, 1, "key", new_temp
    )
    dialog._remote_artifact = old_artifact
    dialog._inspection_target = ("sync-id", "src/main.py")
    dialog._inspection_side = "beta"
    dialog._inspection_completed(new_artifact, None)

    assert not old_path.exists()
    assert dialog._remote_artifact is new_artifact
    assert dialog.open_remote_copy.isEnabled()
    assert dialog.compare_remote_local.isEnabled()

    dialog.closeEvent(QCloseEvent())
    assert dialog._remote_artifact is None
    assert not new_path.exists()


@pytest.mark.parametrize("artifact_result", ["artifact", "unexpected"])
def test_pending_close_finishes_after_inspection_and_cleans_artifact(tmp_path, artifact_result):
    dialog = _dialog(tmp_path)
    temporary = TemporaryDirectory()
    artifact_path = Path(temporary.name) / "copy"
    artifact_path.write_text("remote", encoding="utf-8")
    artifact = RemoteInspectionArtifact(
        artifact_path, "/remote", 6, "hash", True, None, "key", temporary
    )
    completed = []
    dialog.close = lambda: completed.append(True)
    dialog._close_pending = True

    result = artifact if artifact_result == "artifact" else object()
    dialog._inspection_completed(result, None)

    assert completed == [True]
    assert artifact_path.exists() is (artifact_result == "unexpected")
    assert dialog._remote_artifact is None
    artifact.close()


def test_compare_remote_copy_rejects_missing_local_and_reports_copy_errors(
    tmp_path, monkeypatch, request
):
    ssh = Endpoint("ssh", "alice@example:/srv", host="example", user="alice", path="/srv")
    remote_only = _dialog(tmp_path, alpha=ssh, conflicts=(({"root": "src/main.py"}),))
    temp = TemporaryDirectory()
    remote = Path(temp.name) / "remote"
    remote.write_text("remote", encoding="utf-8")
    artifact = RemoteInspectionArtifact(remote, "/srv/main.py", 6, "hash", True, None, "key", temp)
    request.addfinalizer(artifact.close)
    remote_only._remote_artifact = artifact
    remote_only._remote_artifact_side = "alpha"

    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append("info"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("warning"))
    remote_only._compare_remote_with_local()
    assert messages == ["info"]

    root = tmp_path / "local"
    target = root / "src" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("local", encoding="utf-8")
    local_remote = _dialog(
        tmp_path,
        alpha=ssh,
        beta=Endpoint("local", str(root), path=str(root)),
        conflicts=(({"root": "src/main.py"}),),
    )
    local_remote._remote_artifact = artifact
    local_remote._remote_artifact_side = "alpha"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    local_remote._compare_remote_with_local()
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args: ("diff-tool", ""),
    )
    monkeypatch.setattr(
        dialog_module,
        "copy_local_conflict_for_diff",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("copy failed")),
    )
    local_remote._compare_remote_with_local()
    assert messages == ["info", "warning"]


@pytest.mark.parametrize("started", [True, False])
def test_external_diff_process_start_is_reported_and_owned(tmp_path, monkeypatch, started):
    local_root = tmp_path / "local"
    local_file = local_root / "src" / "main.py"
    local_file.parent.mkdir(parents=True)
    local_file.write_text("local", encoding="utf-8")
    ssh = Endpoint("ssh", "alice@example:/srv", host="example", user="alice", path="/srv")
    local = Endpoint("local", str(local_root), path=str(local_root))
    dialog = ConflictInspectorDialog((_snapshot(tmp_path, alpha=ssh, beta=local),))
    remote_temp = TemporaryDirectory()
    remote_path = Path(remote_temp.name) / "remote.py"
    remote_path.write_text("remote", encoding="utf-8")
    dialog._remote_artifact = RemoteInspectionArtifact(
        remote_path, "/srv/src/main.py", 6, "hash", True, None, "key", remote_temp
    )
    dialog._remote_artifact_side = "alpha"
    record = dialog._selected()
    assert record is not None
    dialog._remote_artifact_target = (record.session_identifier, record.relative_path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("fake-diff", ""))
    monkeypatch.setattr(
        dialog_module,
        "external_diff_arguments",
        lambda executable, left, right: [executable, "--", str(left), str(right)],
    )

    class Signal:
        def connect(self, _callback):
            pass

    class Process:
        def __init__(self, _parent):
            self.finished = Signal()
            self.errorOccurred = Signal()
            self.program = None
            self.arguments = None
            self.started = False

        def setProgram(self, program):
            self.program = program

        def setArguments(self, arguments):
            self.arguments = arguments

        def start(self):
            self.started = True

        def waitForStarted(self, _timeout):
            return started

    monkeypatch.setattr(dialog_module, "QProcess", Process)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))

    dialog._compare_remote_with_local()

    if started:
        assert dialog._diff_process is not None
        assert dialog._diff_process.program == "fake-diff"
        assert dialog._diff_process.started
        assert warnings == []
        dialog._diff_process = None
    else:
        assert dialog._diff_process is None
        assert warnings == ["The selected diff tool did not start."]
    dialog._remote_artifact.close()


def test_inspection_approval_starts_bounded_task_and_rejects_incomplete_endpoint(
    tmp_path, monkeypatch
):
    ssh = Endpoint("ssh", "alice@example:/srv", host="example", user="alice", path="/srv")
    dialog = ConflictInspectorDialog(
        (_snapshot(tmp_path, beta=ssh),), audit_path=tmp_path / "audit.jsonl"
    )
    started = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("/tmp/key", ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(dialog._inspection_pool, "start", lambda task: started.append(task))

    dialog._inspect_selected_remote("beta")

    assert len(started) == 1
    assert started[0] is dialog._inspection_task
    assert dialog._inspection_task.request.hostname == "example"
    assert dialog._inspection_task.request.relative_path == "src/main.py"

    incomplete = _dialog(tmp_path)
    monkeypatch.setattr(
        incomplete,
        "_remote_endpoint",
        lambda *_args: Endpoint("ssh", "incomplete", user="alice", path="/srv"),
    )
    incomplete._audit_path = tmp_path / "audit.jsonl"
    incomplete._inspect_selected_remote("beta")
    assert incomplete._inspection_task is None


def test_completion_without_selected_conflict_and_remote_copy_open(tmp_path, monkeypatch):
    empty = _dialog(tmp_path, conflicts=())
    empty._inspection_completed(None, None)
    assert empty._remote_artifact is None

    dialog = _dialog(tmp_path)
    temporary = TemporaryDirectory()
    remote_path = Path(temporary.name) / "remote"
    remote_path.write_text("remote", encoding="utf-8")
    artifact = RemoteInspectionArtifact(
        remote_path, "/remote", 6, "hash", True, None, "key", temporary
    )
    selected = dialog._selected()
    assert selected is not None
    dialog._inspection_target = (selected.session_identifier, selected.relative_path)
    dialog._inspection_side = "alpha"
    dialog._inspection_completed(artifact, None)
    assert dialog._remote_artifact is artifact
    dialog._remote_artifact = artifact
    opened = []
    monkeypatch.setattr(dialog_module.QDesktopServices, "openUrl", lambda url: opened.append(url))
    dialog._open_remote_copy()
    assert len(opened) == 1
    artifact.close()


def test_diff_close_and_error_paths_defer_dialog_close(tmp_path, monkeypatch):
    dialog = _dialog(tmp_path)
    closed = []
    warnings = []
    dialog.close = lambda: closed.append(True)
    dialog._close_pending = True
    dialog._diff_process = object()
    dialog._diff_finished()
    assert closed == [True]

    class Process:
        def state(self):
            return QProcess.ProcessState.NotRunning

    dialog._diff_process = Process()
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))
    dialog._close_pending = False
    dialog._diff_error(QProcess.ProcessError.FailedToStart)
    assert warnings == ["The selected diff tool failed to start."]
    assert closed == [True]

    dialog._diff_process = Process()
    dialog._close_pending = True
    dialog._diff_error(QProcess.ProcessError.FailedToStart)
    assert warnings == ["The selected diff tool failed to start."] * 2
    assert closed == [True, True]


def test_close_event_defers_while_inspection_or_diff_is_active(tmp_path):
    dialog = _dialog(tmp_path)

    class Event:
        ignored = False

        def ignore(self):
            self.ignored = True

    event = Event()
    dialog._inspection_task = object()
    dialog.closeEvent(event)
    assert event.ignored
    assert dialog._close_pending

    class Process:
        def state(self):
            return QProcess.ProcessState.Running

    dialog._inspection_task = None
    dialog._diff_process = Process()
    event = Event()
    dialog.closeEvent(event)
    assert event.ignored
