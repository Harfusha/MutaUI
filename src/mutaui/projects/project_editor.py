"""Previewed in-place edits for project-owned Mutagen configuration."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mutaui.adapters.yaml_config import load_yaml_file
from mutaui.adapters.yaml_config_editor import (
    YAMLPreview,
    YAMLWriteResult,
    apply_yaml_edit,
    preview_yaml_text,
)
from mutaui.projects.native_project import (
    NativeProjectSnapshot,
    validate_native_project_text,
)


class ProjectEditError(ValueError):
    """Raised when a project YAML edit cannot be safely previewed or applied."""


@dataclass(frozen=True, slots=True)
class ProjectEditPreview:
    yaml_preview: YAMLPreview
    project_path: Path
    project_sha256: str
    proposed_sha256: str


@dataclass(frozen=True, slots=True)
class ProjectEditReceipt:
    write: YAMLWriteResult
    audit_event_id: str
    audit_complete: bool


def preview_project_yaml_edit(
    snapshot: NativeProjectSnapshot, proposed_text: str
) -> ProjectEditPreview:
    """Validate project semantics and preserve YAML comments in a byte-bound preview."""
    path = snapshot.path.expanduser().absolute()
    if path.name.casefold() not in {"mutagen.yml", "mutagen.yaml"}:
        raise ProjectEditError("Only a named mutagen.yml or mutagen.yaml can be edited.")
    if not snapshot.valid or snapshot.raw_text is None:
        raise ProjectEditError("An invalid or unreadable project cannot be edited.")
    valid, errors = validate_native_project_text(proposed_text)
    if not valid:
        raise ProjectEditError("Invalid proposed Mutagen project: " + "; ".join(errors))
    current = load_yaml_file(path)
    if not current.valid or current.sha256 != snapshot.sha256:
        raise ProjectEditError("Project changed since it was loaded; reload before editing.")
    try:
        preview = preview_yaml_text(current, proposed_text)
    except (OSError, ValueError) as exc:
        raise ProjectEditError(f"Project edit preview failed: {exc}") from exc
    return ProjectEditPreview(
        preview,
        path,
        snapshot.sha256,
        hashlib.sha256(preview.yaml_bytes).hexdigest(),
    )


def _append_audit(path: Path, record: dict[str, object]) -> None:
    if path.is_symlink():
        raise ProjectEditError("Project edit audit file cannot be a symbolic link.")
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ProjectEditError("Project edit audit path must be a regular file.")
    encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise ProjectEditError(f"Could not persist project edit audit: {exc}") from exc


def apply_project_yaml_edit(
    preview: ProjectEditPreview,
    *,
    consent: bool,
    audit_path: str | Path,
) -> ProjectEditReceipt:
    """Apply one reviewed project edit with exact-source recheck and backup."""
    if not consent:
        raise ProjectEditError("Explicit consent is required to change native project YAML.")
    target = preview.project_path.expanduser().absolute()
    audit_target = Path(audit_path).expanduser().absolute()
    if audit_target == target:
        raise ProjectEditError("Audit data must be stored outside the native project file.")
    if audit_target.exists() and os.path.samefile(audit_target, target):
        raise ProjectEditError("Audit data must not alias the native project file.")
    if not audit_target.parent.is_dir():
        raise ProjectEditError("Project edit audit directory must already exist.")
    if target.is_symlink():
        raise ProjectEditError("Native project became a symbolic link; edit refused.")
    current = load_yaml_file(target)
    if not current.valid or current.sha256 != preview.project_sha256:
        raise ProjectEditError("Native project changed after preview; no edit was applied.")

    event_id = uuid4().hex
    common = {
        "event_id": event_id,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "action": "edit_project_yaml",
        "project_path": str(target),
        "before_sha256": preview.project_sha256,
        "proposed_sha256": preview.proposed_sha256,
    }
    _append_audit(audit_target, {**common, "phase": "prepared"})
    try:
        result = apply_yaml_edit(preview.yaml_preview)
    except Exception as exc:
        _append_audit(
            audit_target,
            {**common, "phase": "failed", "error_type": type(exc).__name__},
        )
        raise
    try:
        _append_audit(
            audit_target,
            {
                **common,
                "phase": "applied",
                "backup_path": str(result.backup_path),
                "new_sha256": result.new_sha256,
            },
        )
    except ProjectEditError:
        return ProjectEditReceipt(result, event_id, False)
    return ProjectEditReceipt(result, event_id, True)
