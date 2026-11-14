"""Read-only normalization and filtering for native sync conflicts."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mutaui.domain.models import SessionSnapshot

ChangeKind = Literal["added", "deleted", "modified", "unknown"]


@dataclass(frozen=True, slots=True)
class ConflictChange:
    path: str
    kind: ChangeKind


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    session_identifier: str
    session_name: str
    relative_path: str
    alpha_changes: tuple[ConflictChange, ...]
    beta_changes: tuple[ConflictChange, ...]
    native_digest: str | None = None
    staging_metadata: str | None = None


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _change_kind(value: Mapping[str, object]) -> ChangeKind:
    old = value.get("old")
    new = value.get("new")
    if old is None and new is not None:
        return "added"
    if old is not None and new is None:
        return "deleted"
    if old is not None and new is not None:
        return "modified"
    return "unknown"


def _changes(raw: object, conflict_root: str) -> tuple[ConflictChange, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    result: list[ConflictChange] = []
    for item in raw:
        record = _mapping(item)
        if record is None:
            continue
        path_value = record.get("path")
        path = path_value if isinstance(path_value, str) and path_value else conflict_root
        result.append(ConflictChange(path, _change_kind(record)))
    return tuple(result)


def _staging_metadata(config: Mapping[str, object]) -> str | None:
    states = []
    for side in ("alphaState", "betaState"):
        endpoint_state = _mapping(config.get(side))
        if endpoint_state is None:
            continue
        progress = endpoint_state.get("stagingProgress")
        if progress is not None:
            states.append(f"{side}: {progress}")
    return "; ".join(states) if states else None


def conflicts_for_snapshot(snapshot: SessionSnapshot) -> tuple[ConflictRecord, ...]:
    """Normalize only native fields; omitted metadata remains unknown."""
    if snapshot.identity.kind != "sync" or snapshot.stale_reason:
        return ()

    records: list[ConflictRecord] = []
    for raw in snapshot.conflicts:
        conflict = _mapping(raw)
        if conflict is None:
            continue
        root = conflict.get("root")
        if not isinstance(root, str) or not root:
            root = "(path unavailable)"
        digest_value = conflict.get("digest")
        records.append(
            ConflictRecord(
                session_identifier=snapshot.identity.identifier,
                session_name=snapshot.identity.name or snapshot.identity.identifier,
                relative_path=root,
                alpha_changes=_changes(conflict.get("alphaChanges"), root),
                beta_changes=_changes(conflict.get("betaChanges"), root),
                native_digest=digest_value if isinstance(digest_value, str) else None,
                staging_metadata=_staging_metadata(snapshot.native_config),
            )
        )
    return tuple(records)


def filter_conflicts(
    records: Sequence[ConflictRecord], *, query: str = "", session_identifier: str = ""
) -> tuple[ConflictRecord, ...]:
    needle = query.casefold().strip()
    filtered = (
        record
        for record in records
        if (not session_identifier or record.session_identifier == session_identifier)
        and (
            not needle
            or needle in record.relative_path.casefold()
            or needle in record.session_name.casefold()
            or needle in record.session_identifier.casefold()
        )
    )
    return tuple(
        sorted(
            filtered, key=lambda item: (item.session_name.casefold(), item.relative_path.casefold())
        )
    )


def safe_local_conflict_path(root: str, relative_path: str) -> Path | None:
    """Resolve an existing local conflict path without escaping its endpoint root."""
    if not root or not relative_path or relative_path == "(path unavailable)":
        return None
    candidate_part = Path(relative_path)
    if candidate_part.is_absolute() or any(part in ("..", "") for part in candidate_part.parts):
        return None
    try:
        lexical_root = Path(root).expanduser().absolute()
        if lexical_root.is_symlink() or bool(getattr(lexical_root, "is_junction", lambda: False)()):
            return None
        lexical_target = lexical_root
        for part in candidate_part.parts:
            lexical_target = lexical_target / part
            if lexical_target.is_symlink() or bool(
                getattr(lexical_target, "is_junction", lambda: False)()
            ):
                return None
        resolved_root = lexical_root.resolve(strict=True)
        resolved_target = lexical_target.resolve(strict=True)
        if not resolved_root.is_dir():
            return None
        if os.path.commonpath((str(resolved_root), str(resolved_target))) != str(resolved_root):
            return None
        return resolved_target
    except (OSError, RuntimeError, ValueError):
        return None
