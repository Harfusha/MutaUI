"""Feature-gated manual single-file conflict resolution for local/local syncs."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from mutaui.services.action_planner import (
    ActionPlan,
    ActionPlanner,
    ActionPlanningError,
    ActionRequest,
)
from mutaui.services.conflict_inspector import ConflictRecord, safe_local_conflict_path

Winner = Literal["alpha", "beta"]
MANUAL_RESOLUTION_ENABLED = False
MAX_CONFLICT_BYTES = 16 * 1024 * 1024


class ConflictResolutionError(ValueError):
    """Raised when one-file resolution lacks exact scope or fresh evidence."""


@dataclass(frozen=True, slots=True)
class FileEvidence:
    path: Path
    sha256: str
    size_bytes: int
    modified_ns: int
    mode: int


@dataclass(frozen=True, slots=True)
class ManualResolutionPlan:
    planner: ActionPlanner
    action_plan: ActionPlan
    session_identifier: str
    relative_path: str
    alpha_root: str
    beta_root: str
    alpha: FileEvidence
    beta: FileEvidence
    winner: Winner
    backup_parent: Path
    native_digest: str
    typed_confirmation: str


@dataclass(frozen=True, slots=True)
class ManualResolutionReceipt:
    backup_directory: Path | None
    resolved_side: Path | None
    verified: bool
    rollback_attempted: bool
    recovery_uncertain: bool
    message: str
    audit_complete: bool = True


def _file_evidence(root: str, relative_path: str) -> FileEvidence:
    path = safe_local_conflict_path(root, relative_path)
    if path is None or path.is_symlink():
        raise ConflictResolutionError("Both conflict sides must be existing contained local files.")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CONFLICT_BYTES:
        raise ConflictResolutionError("Only bounded regular files can enter manual resolution.")
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            total += len(chunk)
            if total > MAX_CONFLICT_BYTES:
                raise ConflictResolutionError("Conflict file exceeds the size limit.")
            digest.update(chunk)
    after = path.lstat()
    if (after.st_size, after.st_mtime_ns, after.st_ino) != (
        info.st_size,
        info.st_mtime_ns,
        info.st_ino,
    ):
        raise ConflictResolutionError("Conflict file changed while it was inspected.")
    return FileEvidence(path, digest.hexdigest(), total, info.st_mtime_ns, info.st_mode)


def prepare_manual_resolution(
    planner: ActionPlanner,
    record: ConflictRecord,
    *,
    alpha_root: str,
    beta_root: str,
    winner: Winner,
    backup_parent: str | Path,
    native_digest: str,
    current_fingerprint: str,
    typed_confirmation: str,
) -> ManualResolutionPlan:
    """Build and consent one exact R3 plan after choosing a winner and backup scope."""
    if not native_digest or native_digest != record.native_digest:
        raise ConflictResolutionError("A current native conflict digest is required.")
    if winner not in {"alpha", "beta"}:
        raise ConflictResolutionError("Choose exactly ALPHA or BETA as the winning copy.")
    if Path(alpha_root).is_symlink() or Path(beta_root).is_symlink():
        raise ConflictResolutionError("Sync roots cannot be symbolic links for manual resolution.")
    alpha = _file_evidence(alpha_root, record.relative_path)
    beta = _file_evidence(beta_root, record.relative_path)
    if alpha.path == beta.path:
        raise ConflictResolutionError("ALPHA and BETA must resolve to different local files.")
    if alpha.sha256 == beta.sha256:
        raise ConflictResolutionError(
            "Both sides already have identical contents; no conflict remains."
        )
    parent = Path(backup_parent).expanduser().absolute()
    if parent.is_symlink() or not parent.is_dir():
        raise ConflictResolutionError("Choose an existing regular backup directory.")
    resolved_parent = parent.resolve(strict=True)
    for endpoint_root in (alpha_root, beta_root):
        resolved_root = Path(endpoint_root).expanduser().resolve(strict=True)
        try:
            common_path = os.path.commonpath((str(resolved_root), str(resolved_parent)))
        except ValueError:
            continue
        if common_path == str(resolved_root):
            raise ConflictResolutionError("Conflict backups must stay outside both sync roots.")
    fingerprint = hashlib.sha256(
        f"{native_digest}\0{alpha.sha256}\0{beta.sha256}".encode()
    ).hexdigest()
    if current_fingerprint != fingerprint:
        raise ConflictResolutionError("File fingerprint changed; refresh the preview.")
    path_token = hashlib.sha256(record.relative_path.encode("utf-8")).hexdigest()[:16]
    action = planner.prepare(
        ActionRequest(
            action="resolve_conflict",
            target_ids=(record.session_identifier,),
            argv=("conflict", "resolve", record.session_identifier, record.relative_path, winner),
            preflight_fingerprint=fingerprint,
            affected_paths=(f"conflict:{path_token}",),
            capabilities=("resolve_conflict",),
            backup_choice="backup-both-sides-outside-sync-roots",
        )
    )
    exact_phrase = action.typed_confirmation
    if not exact_phrase or typed_confirmation != exact_phrase:
        planner.cancel(action.plan_id)
        raise ConflictResolutionError("Type the exact session-ID confirmation from the preview.")
    consented = planner.consent(
        action.plan_id,
        consent=True,
        current_preflight_fingerprint=fingerprint,
        typed_confirmation=typed_confirmation,
        backup_choice=action.backup_choice,
    )
    if consented.state != "consented":
        raise ConflictResolutionError("Exact conflict plan did not reach consented state.")
    return ManualResolutionPlan(
        planner,
        consented,
        record.session_identifier,
        record.relative_path,
        alpha_root,
        beta_root,
        alpha,
        beta,
        winner,
        resolved_parent,
        native_digest,
        exact_phrase,
    )


def _append_audit(path: Path, record: dict[str, object]) -> None:
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_replace(
    target: Path, payload: bytes, *, mode: int, expected_existing_sha256: str
) -> None:
    if target.is_symlink() or not target.is_file():
        raise ConflictResolutionError("Target changed type or became a symlink; write refused.")
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected_existing_sha256:
        raise ConflictResolutionError("Target changed immediately before replacement.")
    fd, temp_name = tempfile.mkstemp(prefix=".mutaui-conflict-", dir=target.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(mode))
        if target.is_symlink():
            raise ConflictResolutionError("Target became a symlink; write refused.")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected_existing_sha256:
            raise ConflictResolutionError("Target changed during replacement preflight.")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _apply_manual_resolution(
    plan: ManualResolutionPlan,
    *,
    consent: bool,
    typed_confirmation: str,
    audit_path: str | Path,
    current_native_digest: Callable[[str, str], str | None],
    flush_and_verify: Callable[[str], bool],
    feature_enabled: bool = MANUAL_RESOLUTION_ENABLED,
) -> ManualResolutionReceipt:
    """Back up both local copies, recheck freshness, replace one file, verify or restore."""
    if not feature_enabled:
        raise ConflictResolutionError("Manual conflict resolution is disabled by its safety gate.")
    if not consent or plan.action_plan.state != "consented":
        raise ConflictResolutionError("A consented R3 ActionPlan is required.")
    if typed_confirmation != plan.typed_confirmation:
        raise ConflictResolutionError("Typed confirmation does not match the exact target.")
    audit_target = Path(audit_path).expanduser().absolute()
    if audit_target.is_symlink() or not audit_target.parent.is_dir():
        raise ConflictResolutionError("A safe local audit destination is required.")
    backup_directory = plan.backup_parent / f"mutaui-conflict-{uuid4().hex}"
    event_id = uuid4().hex
    record: dict[str, object] = {
        "event_id": event_id,
        "session_identifier": plan.session_identifier,
        "relative_path_sha256": hashlib.sha256(plan.relative_path.encode()).hexdigest(),
        "alpha_sha256": plan.alpha.sha256,
        "beta_sha256": plan.beta.sha256,
        "winner": plan.winner,
        "phase": "prepared",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        _append_audit(audit_target, record)
    except OSError as exc:
        raise ConflictResolutionError("Local resolution audit could not be persisted.") from exc
    if current_native_digest(plan.session_identifier, plan.relative_path) != plan.native_digest:
        raise ConflictResolutionError(
            "Native conflict changed after preview; nothing was modified."
        )
    if _file_evidence(plan.alpha_root, plan.relative_path).sha256 != plan.alpha.sha256:
        raise ConflictResolutionError("ALPHA file changed after preview; nothing was modified.")
    if _file_evidence(plan.beta_root, plan.relative_path).sha256 != plan.beta.sha256:
        raise ConflictResolutionError("BETA file changed after preview; nothing was modified.")
    backup_directory.mkdir()
    alpha_bytes = plan.alpha.path.read_bytes()
    beta_bytes = plan.beta.path.read_bytes()
    if (
        hashlib.sha256(alpha_bytes).hexdigest() != plan.alpha.sha256
        or hashlib.sha256(beta_bytes).hexdigest() != plan.beta.sha256
    ):
        return ManualResolutionReceipt(
            backup_directory, None, False, False, False, "File changed during backup."
        )
    for name, payload in (("alpha.backup", alpha_bytes), ("beta.backup", beta_bytes)):
        with (backup_directory / name).open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    (backup_directory / "alpha.backup").chmod(stat.S_IREAD)
    (backup_directory / "beta.backup").chmod(stat.S_IREAD)
    manifest = {
        "session_identifier": plan.session_identifier,
        "relative_path_sha256": record["relative_path_sha256"],
        "alpha_sha256": plan.alpha.sha256,
        "beta_sha256": plan.beta.sha256,
        "native_digest": plan.native_digest,
    }
    with (backup_directory / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, sort_keys=True))
        stream.flush()
        os.fsync(stream.fileno())
    (backup_directory / "manifest.json").chmod(stat.S_IREAD)
    if current_native_digest(plan.session_identifier, plan.relative_path) != plan.native_digest:
        return ManualResolutionReceipt(
            backup_directory, None, False, False, False, "Conflict changed; backups retained."
        )

    target, target_evidence = (
        (plan.beta.path, plan.beta) if plan.winner == "alpha" else (plan.alpha.path, plan.alpha)
    )
    winner_bytes = alpha_bytes if plan.winner == "alpha" else beta_bytes
    replacement_applied = False
    try:
        current_target = target.read_bytes()
        if hashlib.sha256(current_target).hexdigest() != target_evidence.sha256:
            raise ConflictResolutionError("Losing side changed after backup; no write performed.")
        _atomic_replace(
            target,
            winner_bytes,
            mode=target_evidence.mode,
            expected_existing_sha256=target_evidence.sha256,
        )
        replacement_applied = True
        expected_hash = plan.alpha.sha256 if plan.winner == "alpha" else plan.beta.sha256
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash:
            raise ConflictResolutionError("File convergence check failed.")
        if not flush_and_verify(plan.session_identifier):
            raise ConflictResolutionError("Native flush or convergence verification failed.")
    except Exception as exc:
        if not replacement_applied:
            return ManualResolutionReceipt(
                backup_directory,
                None,
                False,
                False,
                False,
                f"Resolution stopped before replacement ({type(exc).__name__}); both backups retained.",
            )
        try:
            current_target = target.read_bytes()
            expected_winner = plan.alpha.sha256 if plan.winner == "alpha" else plan.beta.sha256
            if hashlib.sha256(current_target).hexdigest() != expected_winner:
                raise ConflictResolutionError(
                    "Target changed after replacement; automatic restore refused."
                )
            original = beta_bytes if plan.winner == "alpha" else alpha_bytes
            _atomic_replace(
                target,
                original,
                mode=target_evidence.mode,
                expected_existing_sha256=expected_winner,
            )
            restored = hashlib.sha256(target.read_bytes()).hexdigest() == target_evidence.sha256
            _append_audit(
                audit_target,
                {**record, "phase": "restored" if restored else "restore-unverified"},
            )
            return ManualResolutionReceipt(
                backup_directory,
                None,
                False,
                True,
                True,
                f"Resolution failed ({type(exc).__name__}); original file restore {'verified' if restored else 'uncertain'}.",
            )
        except Exception as restore_exc:
            return ManualResolutionReceipt(
                backup_directory,
                None,
                False,
                True,
                True,
                f"Resolution failed ({type(exc).__name__}); restore uncertain ({type(restore_exc).__name__}).",
            )
    try:
        _append_audit(
            audit_target,
            {**record, "phase": "verified", "backup_directory": str(backup_directory)},
        )
    except OSError:
        return ManualResolutionReceipt(
            backup_directory,
            target,
            True,
            False,
            False,
            "One conflict file was resolved and verified; audit completion could not be recorded.",
            False,
        )
    return ManualResolutionReceipt(
        backup_directory,
        target,
        True,
        False,
        False,
        "One conflict file was resolved and verified.",
    )


def apply_manual_resolution(
    plan: ManualResolutionPlan,
    *,
    consent: bool,
    typed_confirmation: str,
    audit_path: str | Path,
    current_native_digest: Callable[[str, str], str | None],
    flush_and_verify: Callable[[str], bool],
    feature_enabled: bool = MANUAL_RESOLUTION_ENABLED,
) -> ManualResolutionReceipt:
    """Run the gated resolver and close the exact-target ActionPlan lease."""
    try:
        receipt = _apply_manual_resolution(
            plan,
            consent=consent,
            typed_confirmation=typed_confirmation,
            audit_path=audit_path,
            current_native_digest=current_native_digest,
            flush_and_verify=flush_and_verify,
            feature_enabled=feature_enabled,
        )
    except Exception:
        if plan.action_plan.state == "consented":
            with suppress(ActionPlanningError):
                plan.planner.cancel(plan.action_plan.plan_id)
        raise
    if receipt.verified:
        plan.planner.finish(
            plan.action_plan.plan_id,
            verified_target_ids=(plan.session_identifier,),
            outcome=receipt.message,
        )
    elif plan.action_plan.state == "consented":
        with suppress(ActionPlanningError):
            plan.planner.cancel(plan.action_plan.plan_id)
    return receipt
