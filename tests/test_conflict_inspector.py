from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mutaui.domain.models import Endpoint, SessionIdentity, SessionSnapshot
from mutaui.services.conflict_inspector import (
    ConflictChange,
    _change_kind,
    _changes,
    _staging_metadata,
    conflicts_for_snapshot,
    filter_conflicts,
    safe_local_conflict_path,
)


def _snapshot(
    conflicts: tuple[object, ...], *, stale_reason: str | None = None, kind: str = "sync"
) -> SessionSnapshot:
    return SessionSnapshot(
        identity=SessionIdentity(kind, "sync-exact-id", "Build tree"),
        native_config={},
        alpha_or_source=None,
        beta_or_destination=None,
        state="error",
        conflicts=conflicts,
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
        stale_reason=stale_reason,
    )


def test_native_conflicts_preserve_exact_scope_path_and_change_kinds():
    records = conflicts_for_snapshot(
        _snapshot(
            (
                {
                    "root": "src/main.py",
                    "alphaChanges": [{"path": "src/main.py", "old": {}, "new": {}}],
                    "betaChanges": [{"path": "src/main.py", "old": {}, "new": None}],
                },
            )
        )
    )

    assert len(records) == 1
    assert records[0].session_identifier == "sync-exact-id"
    assert records[0].relative_path == "src/main.py"
    assert records[0].alpha_changes[0].kind == "modified"
    assert records[0].beta_changes[0].kind == "deleted"
    assert records[0].native_digest is None


def test_unknown_conflict_details_are_not_guessed_and_filters_are_stable():
    records = conflicts_for_snapshot(_snapshot(({"root": "folder/a.txt"}, {"root": "b.txt"})))
    filtered = filter_conflicts(records, query="A.TXT")

    assert [item.relative_path for item in filtered] == ["folder/a.txt"]
    assert records[0].alpha_changes == ()
    assert records[0].beta_changes == ()
    assert filter_conflicts(records, session_identifier="other-id") == ()


def test_stale_or_forward_snapshots_do_not_produce_conflicts():
    native = ({"root": "a.txt"},)
    assert conflicts_for_snapshot(_snapshot(native, stale_reason="stale")) == ()
    assert conflicts_for_snapshot(_snapshot(native, kind="forward")) == ()


def test_safe_local_open_path_requires_existing_contained_non_symlink_target(tmp_path: Path):
    root = tmp_path / "sync"
    root.mkdir()
    nested = root / "src"
    nested.mkdir()
    target = nested / "main.py"
    target.write_text("original", encoding="utf-8")

    assert safe_local_conflict_path(str(root), "src/main.py") == target.resolve()
    assert safe_local_conflict_path(str(root), "../outside") is None
    assert safe_local_conflict_path(str(root), "missing.txt") is None
    link = root / "linked.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pass
    else:
        assert safe_local_conflict_path(str(root), "linked.txt") is None


def test_safe_local_open_path_rejects_missing_ambiguous_and_absolute_inputs(tmp_path: Path):
    root = tmp_path / "sync"
    root.mkdir()

    assert safe_local_conflict_path("", "file.txt") is None
    assert safe_local_conflict_path(str(root), "") is None
    assert safe_local_conflict_path(str(root), "(path unavailable)") is None
    assert safe_local_conflict_path(str(root), str(tmp_path / "outside.txt")) is None
    assert safe_local_conflict_path(str(root), "missing.txt") is None


def test_safe_local_open_path_rejects_linked_root_and_junction(tmp_path: Path, monkeypatch):
    root = tmp_path / "sync"
    root.mkdir()
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda candidate: candidate == root)
    assert safe_local_conflict_path(str(root), "file.txt") is None

    monkeypatch.setattr(Path, "is_symlink", original_is_symlink)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda candidate: candidate == root,
        raising=False,
    )
    assert safe_local_conflict_path(str(root), "file.txt") is None


def test_safe_local_open_path_rejects_nested_links_and_non_directory_roots(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "sync"
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    (nested / "file.txt").write_text("safe", encoding="utf-8")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda candidate: candidate == nested or original_is_symlink(candidate)
    )
    assert safe_local_conflict_path(str(root), "nested/file.txt") is None

    monkeypatch.setattr(Path, "is_symlink", original_is_symlink)
    file_root = tmp_path / "not-a-directory"
    file_root.write_text("x", encoding="utf-8")
    assert safe_local_conflict_path(str(file_root), ".") is None


def test_safe_local_open_path_rejects_resolved_target_escape(tmp_path: Path, monkeypatch):
    root = tmp_path / "sync"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    original_resolve = Path.resolve

    def escape_target(candidate, *args, **kwargs):
        if candidate == target:
            return outside
        return original_resolve(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", escape_target)
    assert safe_local_conflict_path(str(root), "file.txt") is None


def test_conflict_normalizers_cover_unknown_changes_and_optional_staging():
    assert _change_kind({"old": None, "new": {}}) == "added"
    assert _change_kind({}) == "unknown"
    assert _changes("not-a-sequence", "root.txt") == ()
    assert _changes([None, {"old": None, "new": None}], "root.txt") == (
        ConflictChange("root.txt", "unknown"),
    )
    assert _staging_metadata({"alphaState": None, "betaState": {}}) is None
    assert (
        _staging_metadata({"alphaState": {"stagingProgress": {"path": "/tmp/a"}}})
        == "alphaState: {'path': '/tmp/a'}"
    )


def test_conflict_snapshot_uses_unknown_path_and_rejects_non_directories(tmp_path: Path):
    records = conflicts_for_snapshot(_snapshot((None, {"root": None, "digest": "sha256:abc"})))
    assert len(records) == 1
    assert records[0].relative_path == "(path unavailable)"
    assert records[0].native_digest == "sha256:abc"

    root_file = tmp_path / "not-a-directory"
    root_file.write_text("data", encoding="utf-8")
    assert safe_local_conflict_path(str(root_file), "child.txt") is None
    assert safe_local_conflict_path("\x00", "child.txt") is None


def test_qt_inspector_displays_native_conflicts_read_only():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog

    app = QApplication.instance() or QApplication([])
    snapshot = _snapshot(
        (
            {
                "root": "src/main.py",
                "alphaChanges": [{"path": "src/main.py", "old": {}, "new": {}}],
                "betaChanges": [{"path": "src/main.py", "old": None, "new": {}}],
            },
        )
    )
    dialog = ConflictInspectorDialog((snapshot,))
    try:
        app.processEvents()
        assert dialog.table.rowCount() == 1
        dialog.table.selectRow(0)
        assert "sync-exact-id" in dialog.details.toPlainText()
        assert "modified: src/main.py" in dialog.details.toPlainText()
        assert not dialog.open_alpha.isEnabled()
        assert not dialog.open_beta.isEnabled()
        assert not dialog.inspect_alpha.isEnabled()
    finally:
        dialog.close()


def test_qt_inspector_shows_only_opted_in_exact_path_advice(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from mutaui.services.conflict_recommendations import (
        ConflictChoiceRule,
        ConflictRecommendationPolicy,
        save_recommendation_policy,
    )
    from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog

    app = QApplication.instance() or QApplication([])
    snapshot = _snapshot(
        (
            {
                "root": "src/main.py",
                "alphaChanges": [{"path": "src/main.py", "old": {}, "new": {}}],
                "betaChanges": [{"path": "src/main.py", "old": None, "new": {}}],
            },
        )
    )
    policy = ConflictRecommendationPolicy(
        (ConflictChoiceRule("keep-alpha", "src/main.py", "alpha", "Reviewed source wins."),),
        enabled=True,
    )
    path = tmp_path / "conflict-recommendations.json"
    save_recommendation_policy(path, policy)
    dialog = ConflictInspectorDialog((snapshot,), recommendation_path=path)
    try:
        dialog.table.selectRow(0)
        text = dialog.details.toPlainText()
        assert "ADVISORY ONLY" in text
        assert "Exact session identifier: sync-exact-id" in text
        assert "Exact conflict path: src/main.py" in text
        assert "Preferred side: ALPHA" in text
        assert "Reviewed source wins." in text
        assert not hasattr(dialog, "resolve_conflict")
    finally:
        dialog.close()
        app.processEvents()


def test_qt_inspector_fails_closed_for_corrupt_advice_sidecar(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog

    app = QApplication.instance() or QApplication([])
    snapshot = _snapshot(
        (
            {
                "root": "src/main.py",
                "alphaChanges": [{"path": "src/main.py", "old": {}, "new": {}}],
            },
        )
    )
    path = tmp_path / "conflict-recommendations.json"
    original = b'{"schema_version": 99, "enabled": true, "rules": []}'
    path.write_bytes(original)
    dialog = ConflictInspectorDialog((snapshot,), recommendation_path=path)
    try:
        dialog.table.selectRow(0)
        assert "could not be loaded" in dialog.recommendation_status.text()
        assert "ADVISORY ONLY" not in dialog.details.toPlainText()
        assert dialog.manage_recommendations.isEnabled()
        assert path.read_bytes() == original
    finally:
        dialog.close()
        app.processEvents()


def test_qt_remote_inspection_is_only_offered_for_known_ssh_endpoint_and_audit(tmp_path):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog

    app = QApplication.instance() or QApplication([])
    snapshot = _snapshot(
        (
            {
                "root": "src/main.py",
                "alphaChanges": [{"path": "src/main.py", "old": {}, "new": {}}],
            },
        )
    )
    snapshot = replace(
        snapshot,
        alpha_or_source=Endpoint(
            "ssh",
            "user@build:/srv/project",
            host="build",
            user="user",
            path="/srv/project",
        ),
    )
    dialog = ConflictInspectorDialog((snapshot,), audit_path=tmp_path / "remote-audit.jsonl")
    try:
        app.processEvents()
        assert dialog.inspect_alpha.isEnabled()
        assert not dialog.inspect_beta.isEnabled()
    finally:
        dialog.close()
