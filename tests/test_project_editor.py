import json
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import mutaui.projects.project_editor as project_editor
from mutaui.projects.native_project import load_native_project
from mutaui.projects.project_editor import (
    ProjectEditError,
    apply_project_yaml_edit,
    preview_project_yaml_edit,
)
from mutaui.ui.project_yaml_editor_dialog import ProjectYamlEditorDialog

PROJECT = "# keep this comment\nsync:\n  app:\n    alpha: ./src\n    beta: host:/srv\n    mode: two-way-safe\n"
PROPOSAL = PROJECT.replace("two-way-safe", "one-way-safe")


def test_project_edit_preview_is_exact_comment_preserving_and_does_not_write(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    snapshot = load_native_project(path)

    preview = preview_project_yaml_edit(snapshot, PROPOSAL)

    assert "two-way-safe" in preview.yaml_preview.diff
    assert "one-way-safe" in preview.yaml_preview.diff
    assert "# keep this comment" in preview.yaml_preview.yaml_text
    assert path.read_text(encoding="utf-8") == PROJECT


def test_project_edit_requires_valid_semantics_and_fresh_source(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    snapshot = load_native_project(path)

    with pytest.raises(ProjectEditError, match="Invalid proposed"):
        preview_project_yaml_edit(snapshot, "sync: []\n")

    path.write_text(PROJECT.replace("./src", "./external"), encoding="utf-8")
    with pytest.raises(ProjectEditError, match="changed since it was loaded"):
        preview_project_yaml_edit(snapshot, PROPOSAL)


def test_project_edit_consent_backup_audit_and_stale_write_guards(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    preview = preview_project_yaml_edit(load_native_project(path), PROPOSAL)
    audit = tmp_path / "project-edit.jsonl"

    with pytest.raises(ProjectEditError, match="Explicit consent"):
        apply_project_yaml_edit(preview, consent=False, audit_path=audit)
    assert not audit.exists()

    result = apply_project_yaml_edit(preview, consent=True, audit_path=audit)

    assert result.audit_complete
    assert result.write.backup_path.read_text(encoding="utf-8") == PROJECT
    assert path.read_text(encoding="utf-8") == PROPOSAL
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "applied"]
    assert events[1]["new_sha256"] == result.write.new_sha256

    with pytest.raises(ProjectEditError, match="changed after preview"):
        apply_project_yaml_edit(preview, consent=True, audit_path=audit)


def test_project_yaml_editor_stages_diff_and_requires_consent(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    dialog = ProjectYamlEditorDialog(load_native_project(path), tmp_path / "audit.jsonl")
    dialog.editor.setPlainText(PROPOSAL)
    dialog.stage_edit()

    assert "one-way-safe" in dialog.diff.toPlainText()
    assert not dialog.apply_button.isEnabled()
    dialog.consent.setChecked(True)
    assert dialog.apply_button.isEnabled()
    assert path.read_text(encoding="utf-8") == PROJECT
    assert app is not None


def test_project_preview_rejects_wrong_name_and_invalid_snapshot(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    snapshot = load_native_project(path)

    with pytest.raises(ProjectEditError, match="named mutagen.yml"):
        preview_project_yaml_edit(replace(snapshot, path=tmp_path / "other.yml"), PROPOSAL)
    with pytest.raises(ProjectEditError, match="invalid or unreadable"):
        preview_project_yaml_edit(replace(snapshot, valid=False), PROPOSAL)


def test_project_edit_rejects_audit_alias_and_missing_directory(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    preview = preview_project_yaml_edit(load_native_project(path), PROPOSAL)

    with pytest.raises(ProjectEditError, match="outside the native project"):
        apply_project_yaml_edit(preview, consent=True, audit_path=path)
    with pytest.raises(ProjectEditError, match="directory must already exist"):
        apply_project_yaml_edit(
            preview, consent=True, audit_path=tmp_path / "missing" / "audit.jsonl"
        )


def test_project_edit_rejects_hardlink_audit_alias_and_new_symlink(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    preview = preview_project_yaml_edit(load_native_project(path), PROPOSAL)
    hardlink = tmp_path / "audit-alias.jsonl"
    try:
        hardlink.hardlink_to(path)
    except OSError:
        pytest.skip("hard links unavailable on this filesystem")
    with pytest.raises(ProjectEditError, match="must not alias"):
        apply_project_yaml_edit(preview, consent=True, audit_path=hardlink)

    alias_target = tmp_path / "original.yml"
    path.replace(alias_target)
    try:
        path.symlink_to(alias_target)
    except OSError:
        return
    with pytest.raises(ProjectEditError, match="became a symbolic link"):
        apply_project_yaml_edit(preview, consent=True, audit_path=tmp_path / "fresh-audit.jsonl")


def test_project_edit_rechecks_symlink_before_write(tmp_path, monkeypatch):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    preview = preview_project_yaml_edit(load_native_project(path), PROPOSAL)
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda candidate: candidate == path or original_is_symlink(candidate),
    )

    with pytest.raises(ProjectEditError, match="became a symbolic link"):
        apply_project_yaml_edit(preview, consent=True, audit_path=tmp_path / "fresh-audit.jsonl")


def test_project_edit_records_failed_write_and_reports_incomplete_final_audit(
    tmp_path, monkeypatch
):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    preview = preview_project_yaml_edit(load_native_project(path), PROPOSAL)
    write_yaml_edit = project_editor.apply_yaml_edit
    monkeypatch.setattr(
        project_editor,
        "apply_yaml_edit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("write failed")),
    )

    with pytest.raises(OSError, match="write failed"):
        apply_project_yaml_edit(preview, consent=True, audit_path=audit)
    assert [json.loads(line)["phase"] for line in audit.read_text().splitlines()] == [
        "prepared",
        "failed",
    ]

    path.write_text(PROJECT, encoding="utf-8")
    preview = preview_project_yaml_edit(load_native_project(path), PROPOSAL)
    monkeypatch.setattr(project_editor, "apply_yaml_edit", write_yaml_edit)
    append = project_editor._append_audit
    calls = 0

    def fail_applied_audit(audit_path, record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ProjectEditError("audit unavailable")
        append(audit_path, record)

    monkeypatch.setattr(project_editor, "_append_audit", fail_applied_audit)
    receipt = apply_project_yaml_edit(preview, consent=True, audit_path=audit)

    assert not receipt.audit_complete
    assert path.read_text(encoding="utf-8") == PROPOSAL


def test_project_yaml_dialog_requires_staged_consent_and_confirmed_apply(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    dialog = ProjectYamlEditorDialog(load_native_project(path), tmp_path / "audit.jsonl")
    dialog.apply_edit()
    dialog.consent.setChecked(True)
    dialog.apply_edit()
    assert not dialog.apply_button.isEnabled()

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )
    dialog.editor.setPlainText("sync: [broken\n")
    dialog.stage_edit()
    assert dialog.preview is None
    assert not dialog.apply_button.isEnabled()
    assert warnings

    dialog.editor.setPlainText(PROPOSAL)
    dialog.stage_edit()
    dialog.consent.setChecked(True)
    assert dialog.apply_button.isEnabled()
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    dialog.apply_edit()
    assert dialog.receipt is None
    assert path.read_text(encoding="utf-8") == PROJECT

    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    infos = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda _parent, _title, message: infos.append(message)
    )
    dialog.apply_edit()
    assert dialog.receipt is not None
    assert path.read_text(encoding="utf-8") == PROPOSAL
    assert "Backup:" in infos[0]


def test_project_yaml_editor_dialog_shows_warning_when_apply_fails(tmp_path, monkeypatch):
    _app = QApplication.instance() or QApplication([])
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT, encoding="utf-8")
    dialog = ProjectYamlEditorDialog(load_native_project(path), audit_path=tmp_path / "audit.jsonl")
    dialog.editor.setPlainText(PROPOSAL)
    dialog.stage_edit()
    dialog.consent.setChecked(True)

    warnings = []
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(
        QMessageBox, "warning", lambda _parent, _title, message: warnings.append(message)
    )

    def _fail_apply(*_args, **_kwargs):
        raise ProjectEditError("disk full during save")

    monkeypatch.setattr("mutaui.ui.project_yaml_editor_dialog.apply_project_yaml_edit", _fail_apply)
    dialog.apply_edit()
    assert warnings == ["disk full during save"]
    assert dialog.receipt is None


def test_project_audit_append_refuses_symbolic_links_and_nonfiles(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    original_is_symlink = type(audit).is_symlink
    monkeypatch.setattr(
        type(audit),
        "is_symlink",
        lambda candidate: candidate == audit or original_is_symlink(candidate),
    )
    with pytest.raises(ProjectEditError, match="symbolic link"):
        project_editor._append_audit(audit, {"phase": "prepared"})

    monkeypatch.setattr(type(audit), "is_symlink", original_is_symlink)
    audit.mkdir()
    with pytest.raises(ProjectEditError, match="regular file"):
        project_editor._append_audit(audit, {"phase": "prepared"})
