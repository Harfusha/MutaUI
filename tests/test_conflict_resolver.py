import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from mutaui.services import conflict_resolver
from mutaui.services.action_planner import ActionPlanner
from mutaui.services.conflict_inspector import ConflictRecord
from mutaui.services.conflict_resolver import (
    ConflictResolutionError,
    apply_manual_resolution,
    prepare_manual_resolution,
)


def _case(tmp_path):
    alpha_root = tmp_path / "alpha"
    beta_root = tmp_path / "beta"
    backup_parent = tmp_path / "backups"
    alpha_root.mkdir()
    beta_root.mkdir()
    backup_parent.mkdir()
    (alpha_root / "same.txt").write_bytes(b"ALPHA")
    (beta_root / "same.txt").write_bytes(b"BETA!")
    record = ConflictRecord(
        "sync-exact-123", "Project", "same.txt", (), (), native_digest="native-conflict-1"
    )
    digest = hashlib.sha256(
        f"native-conflict-1\0{hashlib.sha256(b'ALPHA').hexdigest()}\0"
        f"{hashlib.sha256(b'BETA!').hexdigest()}".encode()
    ).hexdigest()
    plan = prepare_manual_resolution(
        ActionPlanner(now=lambda: 1.0),
        record,
        alpha_root=str(alpha_root),
        beta_root=str(beta_root),
        winner="alpha",
        backup_parent=backup_parent,
        native_digest="native-conflict-1",
        current_fingerprint=digest,
        typed_confirmation="APPLY sync-exact-123",
    )
    return alpha_root, beta_root, backup_parent, plan


def _record(plan):
    return ConflictRecord(
        plan.session_identifier,
        "Project",
        plan.relative_path,
        (),
        (),
        native_digest=plan.native_digest,
    )


def _prepare_again(plan, *, planner=None, **overrides):
    values = {
        "alpha_root": plan.alpha_root,
        "beta_root": plan.beta_root,
        "winner": plan.winner,
        "backup_parent": plan.backup_parent,
        "native_digest": plan.native_digest,
        "current_fingerprint": hashlib.sha256(
            f"{plan.native_digest}\0{plan.alpha.sha256}\0{plan.beta.sha256}".encode()
        ).hexdigest(),
        "typed_confirmation": plan.typed_confirmation,
    }
    values.update(overrides)
    return prepare_manual_resolution(
        planner or ActionPlanner(now=lambda: 1.0), _record(plan), **values
    )


def test_manual_resolver_is_feature_gated_off_by_default(tmp_path):
    alpha, beta, _backups, plan = _case(tmp_path)

    with pytest.raises(ConflictResolutionError, match="disabled"):
        apply_manual_resolution(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
            audit_path=tmp_path / "audit.jsonl",
            current_native_digest=lambda *_: "native-conflict-1",
            flush_and_verify=lambda *_: True,
        )

    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"


def test_one_file_resolution_backups_both_sides_and_verifies_convergence(tmp_path):
    alpha, beta, backups, plan = _case(tmp_path)
    audit = tmp_path / "audit.jsonl"

    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=audit,
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda session: session == "sync-exact-123",
        feature_enabled=True,
    )

    assert receipt.verified
    assert not receipt.recovery_uncertain
    assert plan.planner.audit[-1].decision == "finished"
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "alpha.backup").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "beta.backup").read_bytes() == b"BETA!"
    manifest = json.loads((receipt.backup_directory / "manifest.json").read_text())
    assert manifest["native_digest"] == "native-conflict-1"
    assert json.loads(audit.read_text().splitlines()[-1])["phase"] == "verified"


def test_changed_native_conflict_blocks_before_backup_or_file_write(tmp_path):
    alpha, beta, backup_parent, plan = _case(tmp_path)

    with pytest.raises(ConflictResolutionError, match="Native conflict changed"):
        apply_manual_resolution(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
            audit_path=tmp_path / "audit.jsonl",
            current_native_digest=lambda *_: "changed",
            flush_and_verify=lambda *_: True,
            feature_enabled=True,
        )

    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"
    assert not tuple(backup_parent.iterdir())
    assert plan.planner.audit[-1].decision == "cancelled"


def test_changed_file_after_preview_blocks_before_backup_or_file_write(tmp_path):
    alpha, beta, backup_parent, plan = _case(tmp_path)
    (beta / "same.txt").write_bytes(b"CHANGED AFTER PREVIEW")

    with pytest.raises(ConflictResolutionError, match="BETA file changed after preview"):
        apply_manual_resolution(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
            audit_path=tmp_path / "audit.jsonl",
            current_native_digest=lambda *_: "native-conflict-1",
            flush_and_verify=lambda *_: True,
            feature_enabled=True,
        )

    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"CHANGED AFTER PREVIEW"
    assert not tuple(backup_parent.iterdir())


def test_failed_native_verification_restores_original_losing_copy(tmp_path):
    alpha, beta, _backups, plan = _case(tmp_path)

    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: False,
        feature_enabled=True,
    )

    assert not receipt.verified
    assert receipt.rollback_attempted
    assert receipt.recovery_uncertain
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"
    assert (receipt.backup_directory / "alpha.backup").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "beta.backup").read_bytes() == b"BETA!"


def test_native_conflict_change_after_backup_retains_backups_without_replacement(tmp_path):
    alpha, beta, _backups, plan = _case(tmp_path)
    digests = iter(("native-conflict-1", "changed-after-backup"))

    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: next(digests),
        flush_and_verify=lambda *_: True,
        feature_enabled=True,
    )

    assert not receipt.verified
    assert not receipt.rollback_attempted
    assert not receipt.recovery_uncertain
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"
    assert (receipt.backup_directory / "alpha.backup").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "beta.backup").read_bytes() == b"BETA!"


def test_replace_failure_before_commit_keeps_sources_and_both_backups(tmp_path, monkeypatch):
    alpha, beta, _backups, plan = _case(tmp_path)

    def fail_replace(*_args, **_kwargs):
        raise OSError("injected replace failure")

    monkeypatch.setattr(conflict_resolver, "_atomic_replace", fail_replace)
    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: True,
        feature_enabled=True,
    )

    assert not receipt.verified
    assert not receipt.rollback_attempted
    assert not receipt.recovery_uncertain
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"
    assert (receipt.backup_directory / "alpha.backup").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "beta.backup").read_bytes() == b"BETA!"


def test_failed_restore_keeps_backups_and_marks_recovery_uncertain(tmp_path, monkeypatch):
    alpha, beta, _backups, plan = _case(tmp_path)
    original_replace = conflict_resolver._atomic_replace
    replace_calls = 0

    def fail_restore_on_second_replace(*args, **kwargs):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("injected restore failure")
        original_replace(*args, **kwargs)

    monkeypatch.setattr(conflict_resolver, "_atomic_replace", fail_restore_on_second_replace)
    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: False,
        feature_enabled=True,
    )

    assert replace_calls == 2
    assert not receipt.verified
    assert receipt.rollback_attempted
    assert receipt.recovery_uncertain
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "alpha.backup").read_bytes() == b"ALPHA"
    assert (receipt.backup_directory / "beta.backup").read_bytes() == b"BETA!"


def test_verified_result_reports_when_final_audit_write_fails(tmp_path, monkeypatch):
    alpha, beta, _backups, plan = _case(tmp_path)
    audit = tmp_path / "audit.jsonl"
    original_append = conflict_resolver._append_audit

    def fail_final_audit(path, record):
        if record.get("phase") == "verified":
            raise OSError("injected audit failure")
        original_append(path, record)

    monkeypatch.setattr(conflict_resolver, "_append_audit", fail_final_audit)
    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=audit,
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: True,
        feature_enabled=True,
    )

    assert receipt.verified
    assert not receipt.audit_complete
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"ALPHA"
    assert json.loads(audit.read_text().splitlines()[-1])["phase"] == "prepared"
    assert plan.planner.audit[-1].decision == "finished"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"native_digest": "stale"}, "current native conflict digest"),
        ({"winner": "gamma"}, "Choose exactly ALPHA or BETA"),
        ({"current_fingerprint": "stale"}, "File fingerprint changed"),
    ],
)
def test_prepare_rejects_stale_or_invalid_conflict_choices(tmp_path, overrides, message):
    _alpha, _beta, _backups, plan = _case(tmp_path)

    with pytest.raises(ConflictResolutionError, match=message):
        _prepare_again(plan, **overrides)


def test_prepare_rejects_identical_files_same_file_and_backup_inside_sync_root(tmp_path):
    alpha, beta, _backups, plan = _case(tmp_path)
    (beta / "same.txt").write_bytes((alpha / "same.txt").read_bytes())
    with pytest.raises(ConflictResolutionError, match="identical contents"):
        _prepare_again(plan)

    (beta / "same.txt").write_bytes(b"BETA!")
    with pytest.raises(ConflictResolutionError, match="different local files"):
        _prepare_again(plan, beta_root=str(alpha))
    with pytest.raises(ConflictResolutionError, match="outside both sync roots"):
        _prepare_again(plan, backup_parent=alpha)


def test_prepare_rejects_non_directory_backup_parent(tmp_path):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    backup_file = tmp_path / "backup-file"
    backup_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ConflictResolutionError, match="existing regular backup directory"):
        _prepare_again(plan, backup_parent=backup_file)


def test_prepare_rejects_symbolic_link_sync_root(tmp_path, monkeypatch):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self == Path(plan.alpha_root) or original(self),
    )

    with pytest.raises(ConflictResolutionError, match="roots cannot be symbolic links"):
        _prepare_again(plan)


def test_prepare_skips_uncomparable_backup_root_when_commonpath_rejects(monkeypatch, tmp_path):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    original = conflict_resolver.os.path.commonpath

    def reject_backup_comparison(paths):
        if str(plan.backup_parent) in paths:
            raise ValueError("different drives")
        return original(paths)

    monkeypatch.setattr(conflict_resolver.os.path, "commonpath", reject_backup_comparison)

    prepared = _prepare_again(plan)

    assert prepared.action_plan.state == "consented"


def test_prepare_rejects_planner_that_did_not_consent(monkeypatch, tmp_path):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    original_consent = ActionPlanner.consent

    def refuse(self, *args, **kwargs):
        action = original_consent(self, *args, **kwargs)
        return replace(action, state="prepared")

    monkeypatch.setattr(ActionPlanner, "consent", refuse)

    with pytest.raises(ConflictResolutionError, match="did not reach consented state"):
        _prepare_again(plan)


@pytest.mark.parametrize("kind", ["directory", "stale", "late_symlink", "late_change"])
def test_atomic_replace_rechecks_target_before_write(kind, monkeypatch, tmp_path):
    target = tmp_path / "target.txt"
    target.write_bytes(b"before")
    digest = hashlib.sha256(b"before").hexdigest()

    if kind == "directory":
        target.unlink()
        target.mkdir()
    elif kind == "stale":
        monkeypatch.setattr(Path, "read_bytes", lambda _self: b"changed")
        digest = hashlib.sha256(b"before").hexdigest()
    elif kind == "late_symlink":
        original = Path.is_symlink
        seen = 0

        def flip_symlink(self):
            nonlocal seen
            if self == target:
                seen += 1
                return seen > 1
            return original(self)

        monkeypatch.setattr(Path, "is_symlink", flip_symlink)
    elif kind == "late_change":
        reads = 0

        def change_between_reads(self):
            nonlocal reads
            if self == target:
                reads += 1
                return b"before" if reads == 1 else b"changed"
            return Path.read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", change_between_reads)

    with pytest.raises(ConflictResolutionError):
        conflict_resolver._atomic_replace(
            target, b"after", mode=0o600, expected_existing_sha256=digest
        )

    if kind == "directory":
        assert target.is_dir()
    else:
        with target.open("rb") as stream:
            assert stream.read() == b"before"


def test_prepare_wrong_confirmation_cancels_planner_lease(tmp_path):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    planner = ActionPlanner(now=lambda: 1.0)

    with pytest.raises(ConflictResolutionError, match="exact session-ID confirmation"):
        _prepare_again(plan, planner=planner, typed_confirmation="APPLY another-session")

    assert planner.audit[-1].decision == "cancelled"


def test_file_evidence_rejects_missing_nonregular_symlink_oversize_and_race(tmp_path, monkeypatch):
    target = tmp_path / "regular.txt"
    target.write_bytes(b"small")

    monkeypatch.setattr(conflict_resolver, "safe_local_conflict_path", lambda *_args: None)
    with pytest.raises(ConflictResolutionError, match="existing contained local files"):
        conflict_resolver._file_evidence(str(tmp_path), "missing.txt")

    monkeypatch.setattr(conflict_resolver, "safe_local_conflict_path", lambda *_args: tmp_path)
    with pytest.raises(ConflictResolutionError, match="bounded regular files"):
        conflict_resolver._file_evidence(str(tmp_path), "directory")

    monkeypatch.setattr(conflict_resolver, "safe_local_conflict_path", lambda *_args: target)
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == target)
    with pytest.raises(ConflictResolutionError, match="existing contained local files"):
        conflict_resolver._file_evidence(str(tmp_path), "regular.txt")

    monkeypatch.setattr(Path, "is_symlink", lambda _self: False)
    monkeypatch.setattr(conflict_resolver, "MAX_CONFLICT_BYTES", 4)
    with pytest.raises(ConflictResolutionError, match="bounded regular files"):
        conflict_resolver._file_evidence(str(tmp_path), "regular.txt")

    original_lstat = Path.lstat
    calls = 0

    def smaller_initial_stat(path):
        nonlocal calls
        if path == target:
            calls += 1
            actual = original_lstat(path)
            if calls == 1:
                return SimpleNamespace(
                    st_size=4,
                    st_mtime_ns=actual.st_mtime_ns,
                    st_ino=actual.st_ino,
                    st_mode=actual.st_mode,
                )
        return original_lstat(path)

    target.write_bytes(b"more-than-limit")
    monkeypatch.setattr(Path, "lstat", smaller_initial_stat)
    with pytest.raises(ConflictResolutionError, match="exceeds the size limit"):
        conflict_resolver._file_evidence(str(tmp_path), "regular.txt")


def test_file_evidence_rejects_file_changed_during_inspection(tmp_path, monkeypatch):
    target = tmp_path / "same.txt"
    target.write_bytes(b"content")
    original_lstat = Path.lstat
    calls = 0

    def changed_second_stat(path):
        nonlocal calls
        if path == target:
            calls += 1
            actual = original_lstat(path)
            if calls == 2:
                return SimpleNamespace(
                    st_size=actual.st_size,
                    st_mtime_ns=actual.st_mtime_ns + 1,
                    st_ino=actual.st_ino,
                    st_mode=actual.st_mode,
                )
        return original_lstat(path)

    monkeypatch.setattr(conflict_resolver, "safe_local_conflict_path", lambda *_args: target)
    monkeypatch.setattr(Path, "is_symlink", lambda _self: False)
    monkeypatch.setattr(Path, "lstat", changed_second_stat)
    with pytest.raises(ConflictResolutionError, match="changed while it was inspected"):
        conflict_resolver._file_evidence(str(tmp_path), "same.txt")


@pytest.mark.parametrize(
    ("consent", "typed_confirmation", "audit_path", "message"),
    [
        (False, "APPLY sync-exact-123", "audit.jsonl", "consented R3 ActionPlan"),
        (True, "wrong", "audit.jsonl", "Typed confirmation does not match"),
        (True, "APPLY sync-exact-123", "missing/audit.jsonl", "safe local audit destination"),
    ],
)
def test_apply_rejects_missing_consent_confirmation_or_audit_target(
    tmp_path, consent, typed_confirmation, audit_path, message
):
    alpha, beta, _backups, plan = _case(tmp_path)

    with pytest.raises(ConflictResolutionError, match=message):
        apply_manual_resolution(
            plan,
            consent=consent,
            typed_confirmation=typed_confirmation,
            audit_path=tmp_path / audit_path,
            current_native_digest=lambda *_: "native-conflict-1",
            flush_and_verify=lambda *_: True,
            feature_enabled=True,
        )

    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"


def test_initial_audit_failure_stops_before_backup_or_file_changes(tmp_path, monkeypatch):
    alpha, beta, backups, plan = _case(tmp_path)

    def fail_audit(*_args, **_kwargs):
        raise OSError("audit unavailable")

    monkeypatch.setattr(conflict_resolver, "_append_audit", fail_audit)
    with pytest.raises(ConflictResolutionError, match="audit could not be persisted"):
        apply_manual_resolution(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
            audit_path=tmp_path / "audit.jsonl",
            current_native_digest=lambda *_: "native-conflict-1",
            flush_and_verify=lambda *_: True,
            feature_enabled=True,
        )

    assert not tuple(backups.iterdir())
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"BETA!"


def test_alpha_change_after_preview_blocks_before_backup(tmp_path):
    alpha, beta, backups, plan = _case(tmp_path)
    (alpha / "same.txt").write_bytes(b"changed alpha")

    with pytest.raises(ConflictResolutionError, match="ALPHA file changed after preview"):
        apply_manual_resolution(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
            audit_path=tmp_path / "audit.jsonl",
            current_native_digest=lambda *_: "native-conflict-1",
            flush_and_verify=lambda *_: True,
            feature_enabled=True,
        )

    assert not tuple(backups.iterdir())
    assert (beta / "same.txt").read_bytes() == b"BETA!"


def test_file_change_during_backup_stops_before_replacement(tmp_path, monkeypatch):
    alpha, beta, _backups, plan = _case(tmp_path)
    original_read_bytes = Path.read_bytes

    def changed_alpha_read(path):
        if path == plan.alpha.path:
            return original_read_bytes(path) + b"changed during backup"
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", changed_alpha_read)
    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: True,
        feature_enabled=True,
    )

    assert not receipt.verified
    assert receipt.message == "File changed during backup."
    assert (alpha / "same.txt").read_bytes() == b"ALPHAchanged during backup"
    assert (beta / "same.txt").read_bytes() == b"BETA!"


def test_losing_side_changed_after_backup_stops_without_replacement(tmp_path, monkeypatch):
    alpha, beta, _backups, plan = _case(tmp_path)
    audit = tmp_path / "audit.jsonl"
    original_read_bytes = Path.read_bytes
    beta_reads = 0

    def change_losing_side(self):
        nonlocal beta_reads
        if self == beta / "same.txt":
            beta_reads += 1
            if beta_reads == 2:
                return b"BETA changed after backup"
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", change_losing_side)
    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=audit,
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: True,
        feature_enabled=True,
    )

    assert not receipt.verified
    assert "stopped before replacement" in receipt.message
    assert beta_reads >= 2
    assert original_read_bytes(alpha / "same.txt") == b"ALPHA"
    assert original_read_bytes(beta / "same.txt") == b"BETA!"


def test_convergence_failure_refuses_automatic_restore_after_target_changes(tmp_path, monkeypatch):
    alpha, beta, _backups, plan = _case(tmp_path)
    audit = tmp_path / "audit.jsonl"
    original_atomic_replace = conflict_resolver._atomic_replace

    def corrupt_after_replace(target, payload, *, mode, expected_existing_sha256):
        original_atomic_replace(
            target,
            payload,
            mode=mode,
            expected_existing_sha256=expected_existing_sha256,
        )
        target.write_bytes(b"changed immediately after replacement")

    monkeypatch.setattr(conflict_resolver, "_atomic_replace", corrupt_after_replace)
    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=audit,
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: True,
        feature_enabled=True,
    )

    assert not receipt.verified
    assert receipt.rollback_attempted
    assert receipt.recovery_uncertain
    assert "restore uncertain" in receipt.message
    assert (alpha / "same.txt").read_bytes() == b"ALPHA"
    assert (beta / "same.txt").read_bytes() == b"changed immediately after replacement"


def test_apply_exception_does_not_cancel_action_that_is_not_consented(tmp_path):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    plan = replace(plan, action_plan=replace(plan.action_plan, state="prepared"))

    with pytest.raises(ConflictResolutionError, match="disabled"):
        apply_manual_resolution(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
            audit_path=tmp_path / "audit.jsonl",
            current_native_digest=lambda *_: "native-conflict-1",
            flush_and_verify=lambda *_: True,
            feature_enabled=False,
        )

    assert plan.action_plan.state == "prepared"


def test_apply_unverified_receipt_does_not_cancel_action_that_is_not_consented(
    monkeypatch, tmp_path
):
    _alpha, _beta, _backups, plan = _case(tmp_path)
    plan = replace(plan, action_plan=replace(plan.action_plan, state="prepared"))
    monkeypatch.setattr(
        conflict_resolver,
        "_apply_manual_resolution",
        lambda *_args, **_kwargs: SimpleNamespace(verified=False),
    )

    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda *_: True,
    )

    assert not receipt.verified
    assert plan.action_plan.state == "prepared"


def test_beta_winner_updates_only_alpha_and_verifies(tmp_path):
    alpha, beta, _backups, initial = _case(tmp_path)
    plan = _prepare_again(initial, winner="beta")

    receipt = apply_manual_resolution(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
        audit_path=tmp_path / "audit.jsonl",
        current_native_digest=lambda *_: "native-conflict-1",
        flush_and_verify=lambda session: session == "sync-exact-123",
        feature_enabled=True,
    )

    assert receipt.verified
    assert receipt.resolved_side == alpha / "same.txt"
    assert (alpha / "same.txt").read_bytes() == b"BETA!"
    assert (beta / "same.txt").read_bytes() == b"BETA!"
