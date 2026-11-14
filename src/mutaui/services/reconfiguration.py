"""Preview-only session replacement planning and native snapshot validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from forward_configuration import FORWARD_CONFIG_FIELDS
from mutaui.domain.models import SessionSnapshot
from sync_configuration import SYNC_CONFIG_FIELDS


@dataclass(frozen=True, slots=True)
class ConfigurationChange:
    path: str
    current: object
    proposed: object


@dataclass(frozen=True, slots=True)
class NativeCommandSnapshotValidation:
    exact_session_identifier: str
    source_sha256: str
    round_trip_valid: bool
    command_snapshot_available: bool
    command_snapshot_matches_target: bool
    command_arguments: tuple[str, ...] | None
    unknown_configuration_paths: tuple[str, ...]
    issues: tuple[str, ...]

    @property
    def snapshot_inputs_complete(self) -> bool:
        return (
            self.round_trip_valid
            and self.command_snapshot_available
            and self.command_snapshot_matches_target
            and not self.unknown_configuration_paths
            and not self.issues
        )


@dataclass(frozen=True, slots=True)
class ReconfigurationPreview:
    session_identifier: str
    session_kind: str
    source_sha256: str
    changes: tuple[ConfigurationChange, ...]
    validation: NativeCommandSnapshotValidation
    source_command_arguments: tuple[str, ...] | None
    clears_sync_history: bool
    triggers_rescan: bool
    execution_enabled: bool = False


def _json_compatible(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        _json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def native_config_fingerprint(value: object) -> str:
    """Return the same canonical digest used to validate a native snapshot."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _configuration_fields(kind: str) -> frozenset[tuple[str, ...]]:
    fields = SYNC_CONFIG_FIELDS if kind == "sync" else FORWARD_CONFIG_FIELDS
    if kind == "sync":
        return frozenset(("configuration", *field.path) for field in fields)
    return frozenset(field.path for field in fields)


_SYNC_SESSION_METADATA = frozenset(
    {
        "identifier",
        "name",
        "labels",
        "status",
        "paused",
        "version",
        "creatingVersion",
        "creationTime",
        "successfulCycles",
        "lastSuccessfulCycle",
        "lastError",
        "problems",
        "transitionProblems",
        "files",
        "directories",
        "symbolicLinks",
        "totalFileSize",
        "conflicts",
        "excludedConflicts",
    }
)
_ENDPOINT_METADATA = frozenset(
    {
        "protocol",
        "path",
        "endpoint",
        "host",
        "user",
        "port",
        "connected",
        "scanned",
        "directories",
        "files",
        "symbolicLinks",
        "totalFileSize",
        "scanProblems",
        "transitionProblems",
        "problems",
        "lastError",
    }
)
_SYNC_TOP_LEVEL_FIELDS = frozenset(
    field.path[0] for field in SYNC_CONFIG_FIELDS if field.endpoint is None
)
_SYNC_ENDPOINT_FIELDS = {
    side: tuple(field for field in SYNC_CONFIG_FIELDS if field.endpoint == side.upper())
    for side in ("alpha", "beta")
}


def extract_sync_configuration(native_config: Mapping[str, object]) -> dict[str, object]:
    """Extract known sync overrides from either nested or Mutagen list JSON shape."""
    nested = native_config.get("configuration")
    if isinstance(nested, Mapping):
        return dict(nested)
    result: dict[str, object] = {}
    for field in SYNC_CONFIG_FIELDS:
        current: object = native_config
        for part in field.path:
            if not isinstance(current, Mapping) or part not in current:
                break
            current = current[part]
        else:
            target = result
            for part in field.path[:-1]:
                next_value = target.get(part)
                if not isinstance(next_value, dict):
                    next_value = {}
                    target[part] = next_value
                target = next_value
            target[field.path[-1]] = current
    return result


def _unknown_flat_sync_configuration(native_config: Mapping[str, object]) -> tuple[str, ...]:
    known_paths = frozenset(field.path for field in SYNC_CONFIG_FIELDS)
    unknown: list[str] = []
    root_fields = _SYNC_TOP_LEVEL_FIELDS | {"alpha", "beta"}
    for key, value in native_config.items():
        if key in _SYNC_SESSION_METADATA or key in {"alpha", "beta"}:
            continue
        if key not in root_fields:
            unknown.append(key)
            continue
        unknown.extend(_unknown_leaf_paths(value, prefix=(key,), known_paths=known_paths))

    for side, fields in _SYNC_ENDPOINT_FIELDS.items():
        endpoint = native_config.get(side)
        if not isinstance(endpoint, Mapping):
            continue
        endpoint_known_paths = frozenset(field.path for field in fields)
        configured_roots = {field.path[1] for field in fields} | {"ignore", "symlink"}
        for key, value in endpoint.items():
            if key in _ENDPOINT_METADATA:
                continue
            if key in {"ignore", "symlink"} and isinstance(value, Mapping) and not value:
                continue
            if key not in configured_roots:
                unknown.append(f"{side}.{key}")
            else:
                unknown.extend(
                    _unknown_leaf_paths(
                        value,
                        prefix=(side, key),
                        known_paths=endpoint_known_paths,
                    )
                )
    return tuple(sorted(set(unknown)))


def _unknown_leaf_paths(
    value: object,
    *,
    prefix: tuple[str, ...],
    known_paths: frozenset[tuple[str, ...]],
) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        if not value and not any(path[: len(prefix)] == prefix for path in known_paths):
            return (".".join(prefix),)
        unknown: list[str] = []
        for key, item in value.items():
            if not isinstance(key, str):
                unknown.append(".".join((*prefix, "<non-string-key>")))
            else:
                unknown.extend(
                    _unknown_leaf_paths(
                        item,
                        prefix=(*prefix, key),
                        known_paths=known_paths,
                    )
                )
        return tuple(unknown)
    if prefix not in known_paths:
        return (".".join(prefix),)
    return ()


def _flatten(value: object, prefix: tuple[str, ...] = ()) -> dict[str, object]:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            result.update(_flatten(item, (*prefix, str(key))))
        return result
    return {".".join(prefix): value}


def validate_native_command_snapshot(
    snapshot: SessionSnapshot,
    *,
    command_arguments: Sequence[str] | None,
    command_target_identifier: str | None,
) -> NativeCommandSnapshotValidation:
    """Validate preservation and exact provenance; never infer missing argv."""
    issues: list[str] = []
    round_trip_valid = True
    source_sha256 = ""
    try:
        serialized = _canonical_json(snapshot.native_config)
        restored = json.loads(serialized)
        round_trip_valid = _canonical_json(restored) == serialized
        source_sha256 = native_config_fingerprint(snapshot.native_config)
    except (TypeError, ValueError, OverflowError):
        round_trip_valid = False
        issues.append("Native session snapshot is not losslessly JSON round-trippable.")

    if not round_trip_valid and not issues:
        issues.append("Native session snapshot changed during round-trip validation.")

    argv: tuple[str, ...] | None = None
    if command_arguments is not None:
        if not command_arguments or any(
            not isinstance(item, str) or not item or "\x00" in item for item in command_arguments
        ):
            issues.append("Native command snapshot contains an invalid argument list.")
        else:
            argv = tuple(command_arguments)
            if any(item.casefold() in {"--all", "--all=true"} for item in argv):
                issues.append("Native command snapshot uses forbidden broad targeting.")
    else:
        issues.append(
            "Original native create arguments are unavailable; lossless replay is unproven."
        )

    exact_match = command_target_identifier == snapshot.identity.identifier
    if not exact_match:
        issues.append("Command snapshot target does not match the exact native session identifier.")

    known_paths = _configuration_fields(snapshot.identity.kind)
    unknown: list[str] = []
    if snapshot.identity.kind == "sync":
        config = snapshot.native_config.get("configuration")
        if isinstance(config, Mapping):
            unknown.extend(
                _unknown_leaf_paths(config, prefix=("configuration",), known_paths=known_paths)
            )
        elif config is not None:
            unknown.append("configuration")
        else:
            unknown.extend(_unknown_flat_sync_configuration(snapshot.native_config))
    else:
        for key in ("configurationSource", "configurationDestination"):
            config = snapshot.native_config.get(key)
            if config is None:
                continue
            if not isinstance(config, Mapping):
                unknown.append(key)
                continue
            unknown.extend(_unknown_leaf_paths(config, prefix=(key,), known_paths=known_paths))
    return NativeCommandSnapshotValidation(
        exact_session_identifier=snapshot.identity.identifier,
        source_sha256=source_sha256,
        round_trip_valid=round_trip_valid,
        command_snapshot_available=argv is not None,
        command_snapshot_matches_target=exact_match,
        command_arguments=argv,
        unknown_configuration_paths=tuple(sorted(set(unknown))),
        issues=tuple(issues),
    )


def build_reconfiguration_preview(
    snapshot: SessionSnapshot,
    proposed_configuration: Mapping[str, Any],
    *,
    command_arguments: Sequence[str] | None = None,
    command_target_identifier: str | None = None,
) -> ReconfigurationPreview:
    """Create a structured diff only; this function has no execution path."""
    if snapshot.stale_reason:
        raise ValueError("A stale native snapshot cannot be used for replacement preview.")
    if not snapshot.identity.identifier:
        raise ValueError("An exact session identifier is required.")
    try:
        proposed_copy = json.loads(_canonical_json(proposed_configuration))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Proposed configuration is not valid finite JSON data.") from exc

    native_configuration = (
        extract_sync_configuration(snapshot.native_config)
        if snapshot.identity.kind == "sync"
        else snapshot.native_config.get("configuration", {})
    )
    if not isinstance(native_configuration, Mapping):
        native_configuration = {}
    current_flat = _flatten(native_configuration)
    proposed_flat = _flatten(proposed_copy)
    changes = tuple(
        ConfigurationChange(
            path=key,
            current=current_flat.get(key, "(Mutagen default or not reported)"),
            proposed=proposed_flat.get(key, "(removed in proposal)"),
        )
        for key in sorted(current_flat.keys() | proposed_flat.keys())
        if current_flat.get(key, object()) != proposed_flat.get(key, object())
    )
    validation = validate_native_command_snapshot(
        snapshot,
        command_arguments=command_arguments,
        command_target_identifier=command_target_identifier,
    )
    return ReconfigurationPreview(
        session_identifier=snapshot.identity.identifier,
        session_kind=snapshot.identity.kind,
        source_sha256=validation.source_sha256,
        changes=changes,
        validation=validation,
        source_command_arguments=tuple(command_arguments)
        if command_arguments is not None
        else None,
        clears_sync_history=snapshot.identity.kind == "sync",
        triggers_rescan=True,
        execution_enabled=False,
    )
