"""Read-only parsing and change previews for native Mutagen project YAML."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from ruamel.yaml.comments import CommentedMap

from mutaui.adapters.yaml_config import YAMLReadResult, load_yaml_file, parse_yaml_bytes

PROJECT_STORE_SCHEMA = 1
PROJECT_STORE_MAX_BYTES = 1024 * 1024
PROJECT_HOOKS = (
    "beforeCreate",
    "afterCreate",
    "beforePause",
    "afterPause",
    "beforeResume",
    "afterResume",
    "beforeTerminate",
    "afterTerminate",
)


class ProjectStoreError(ValueError):
    """Raised when a local project-reference store is invalid or stale."""


@dataclass(frozen=True, slots=True)
class ProjectSession:
    name: str
    kind: str
    flush_on_create: bool | None
    alpha_or_source: str | None
    beta_or_destination: str | None
    effective_settings: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class NativeProjectSnapshot:
    path: Path
    sha256: str
    raw_bytes: bytes
    raw_text: str | None
    valid: bool
    sessions: tuple[ProjectSession, ...] = ()
    sync_defaults: tuple[str, ...] = ()
    forward_defaults: tuple[str, ...] = ()
    sync_default_settings: tuple[tuple[str, str], ...] = ()
    forward_default_settings: tuple[tuple[str, str], ...] = ()
    hooks: tuple[tuple[str, tuple[str, ...]], ...] = ()
    commands: tuple[tuple[str, str], ...] = ()
    unknown_root_keys: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class ProjectReference:
    id: str
    name: str
    path: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ProjectReferenceLoad:
    references: tuple[ProjectReference, ...]
    valid: bool
    warnings: tuple[str, ...] = ()


def _mapping(value: Any, label: str, warnings: list[str]) -> CommentedMap | None:
    if value is None:
        return None
    if not isinstance(value, CommentedMap):
        warnings.append(f"{label} is not a YAML mapping.")
        return None
    return value


def _names(mapping: CommentedMap | None, label: str, warnings: list[str]) -> tuple[str, ...]:
    if mapping is None:
        return ()
    names: list[str] = []
    for key, value in mapping.items():
        if not isinstance(key, str):
            warnings.append(f"{label} contains a non-text key.")
            continue
        if key == "defaults":
            if _mapping(value, f"{label}.defaults", warnings) is not None:
                continue
        elif _mapping(value, f"{label}.{key}", warnings) is not None:
            names.append(key)
    return tuple(names)


def load_native_project(path: str | Path) -> NativeProjectSnapshot:
    target = Path(path).expanduser().absolute()
    parsed: YAMLReadResult = load_yaml_file(target)
    if not parsed.valid or parsed.document is None:
        return NativeProjectSnapshot(
            target,
            parsed.sha256,
            parsed.raw_bytes,
            parsed.text,
            False,
            error=parsed.error or "Native project YAML is invalid.",
        )

    document = parsed.document
    warnings: list[str] = []
    sync = _mapping(document.get("sync"), "sync", warnings)
    forward = _mapping(document.get("forward"), "forward", warnings)
    sync_names = _names(sync, "sync", warnings)
    forward_names = _names(forward, "forward", warnings)
    records: list[ProjectSession] = []
    for kind, mapping, names, first, second in (
        ("sync", sync, sync_names, "alpha", "beta"),
        ("forward", forward, forward_names, "source", "destination"),
    ):
        if mapping is None:
            continue
        for name in names:
            value = mapping.get(name)
            flush = value.get("flushOnCreate") if kind == "sync" else None
            if flush is not None and type(flush) is not bool:
                warnings.append(f"{kind}.{name}.flushOnCreate is not a boolean.")
                flush = None
            defaults = (
                sync.get("defaults")
                if kind == "sync" and sync is not None
                else forward.get("defaults")
                if kind == "forward" and forward is not None
                else None
            )
            effective = dict(defaults.items()) if isinstance(defaults, CommentedMap) else {}
            effective.update(value)
            endpoints: list[str | None] = []
            for endpoint in (first, second):
                endpoint_value = value.get(endpoint)
                if not isinstance(endpoint_value, str):
                    warnings.append(f"{kind}.{name}.{endpoint} is missing or not text.")
                    endpoints.append(None)
                else:
                    endpoints.append(endpoint_value)
            records.append(
                ProjectSession(
                    name,
                    kind,
                    flush,
                    endpoints[0],
                    endpoints[1],
                    tuple((str(key), str(item)) for key, item in effective.items()),
                )
            )
    sync_defaults = _mapping(sync.get("defaults") if sync else None, "sync.defaults", warnings)
    forward_defaults = _mapping(
        forward.get("defaults") if forward else None, "forward.defaults", warnings
    )
    hooks: list[tuple[str, tuple[str, ...]]] = []
    for key in PROJECT_HOOKS:
        value = document.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            warnings.append(f"{key} must be a list of command strings.")
            continue
        hooks.append((key, tuple(value)))
    raw_commands = document.get("commands")
    commands: list[tuple[str, str]] = []
    if raw_commands is not None:
        command_map = _mapping(raw_commands, "commands", warnings)
        if command_map is not None:
            for key, value in command_map.items():
                if isinstance(key, str) and isinstance(value, str):
                    commands.append((key, value))
                else:
                    warnings.append("commands entries must map names to command strings.")
    known = {"sync", "forward", "commands", *PROJECT_HOOKS}
    return NativeProjectSnapshot(
        target,
        parsed.sha256,
        parsed.raw_bytes,
        parsed.text,
        True,
        tuple(records),
        tuple(str(key) for key in sync_defaults) if sync_defaults is not None else (),
        tuple(str(key) for key in forward_defaults) if forward_defaults is not None else (),
        tuple((str(key), str(value)) for key, value in sync_defaults.items())
        if sync_defaults
        else (),
        tuple((str(key), str(value)) for key, value in forward_defaults.items())
        if forward_defaults
        else (),
        tuple(hooks),
        tuple(commands),
        tuple(str(key) for key in document if key not in known),
        tuple(warnings),
    )


def project_diff(before: NativeProjectSnapshot, after: NativeProjectSnapshot) -> str:
    if before.path != after.path:
        raise ValueError("Project diff requires the same native project path.")
    if before.raw_text is None or after.raw_text is None:
        return "Diff unavailable: one version is not valid UTF-8 text."
    if before.sha256 == after.sha256:
        return "No external changes detected."
    return "".join(
        difflib.unified_diff(
            before.raw_text.splitlines(keepends=True),
            after.raw_text.splitlines(keepends=True),
            fromfile=f"{before.path} (loaded)",
            tofile=f"{after.path} (current)",
        )
    )


def validate_native_project_text(text: str) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(text, str):
        return False, ("Project content must be text.",)
    try:
        raw_bytes = text.encode("utf-8")
    except UnicodeError:
        return False, ("Project content must be valid UTF-8 text.",)
    parsed = parse_yaml_bytes(raw_bytes)
    if not parsed.valid or parsed.document is None:
        return False, (parsed.error or "Native project YAML is invalid.",)
    document = parsed.document
    errors: list[str] = []
    if not any(key in document for key in ("sync", "forward")):
        errors.append("Declare sync or forward sessions before creating a project.")
    for kind, first, second in (
        ("sync", "alpha", "beta"),
        ("forward", "source", "destination"),
    ):
        entries = document.get(kind)
        if entries is None:
            continue
        if not isinstance(entries, CommentedMap):
            errors.append(f"{kind} must be a YAML mapping.")
            continue
        for name, config in entries.items():
            if not isinstance(name, str) or not isinstance(config, CommentedMap):
                errors.append(f"{kind} entries must map text names to YAML mappings.")
                continue
            if name == "defaults":
                continue
            if not isinstance(config.get(first), str) or not isinstance(config.get(second), str):
                errors.append(f"{kind}.{name} requires text {first} and {second} endpoints.")
            if (
                kind == "sync"
                and "flushOnCreate" in config
                and type(config["flushOnCreate"]) is not bool
            ):
                errors.append(f"sync.{name}.flushOnCreate must be a boolean.")
    for hook in PROJECT_HOOKS:
        value = document.get(hook)
        if value is not None and (
            not isinstance(value, list) or any(not isinstance(item, str) for item in value)
        ):
            errors.append(f"{hook} must be a list of command strings.")
    commands = document.get("commands")
    if commands is not None:
        if not isinstance(commands, CommentedMap):
            errors.append("commands must be a YAML mapping.")
        elif any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in commands.items()
        ):
            errors.append("commands entries must map text names to command strings.")
    return not errors, tuple(errors)


def create_native_project_file(
    path: str | Path, text: str, *, audit_path: str | Path
) -> NativeProjectSnapshot:
    target = Path(path).expanduser().absolute()
    audit_target = Path(audit_path).expanduser().absolute()
    if audit_target == target:
        raise ProjectStoreError("Project audit must be stored in a separate local file.")
    if target.name.casefold() not in {"mutagen.yml", "mutagen.yaml"}:
        raise ProjectStoreError("New project file must be named mutagen.yml or mutagen.yaml.")
    valid, errors = validate_native_project_text(text)
    if not valid:
        raise ProjectStoreError("Cannot create invalid native project: " + "; ".join(errors))
    if not target.parent.is_dir():
        raise ProjectStoreError("Project directory must already exist.")
    if target.exists():
        raise ProjectStoreError(
            "Project file already exists; existing native YAML is never overwritten."
        )

    payload = text.encode("utf-8")
    event_id = uuid4().hex
    _append_project_audit(
        audit_target,
        {
            "event_id": event_id,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "phase": "prepared",
            "action": "create_project_file",
            "project_path": str(target),
            "content_sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=target.parent, prefix=".mutagen-project-", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, target)
    except OSError as exc:
        _append_project_audit(
            audit_target,
            {
                "event_id": event_id,
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "phase": "failed",
                "action": "create_project_file",
                "error": str(exc),
            },
        )
        raise
    finally:
        temporary.unlink(missing_ok=True)
    snapshot = load_native_project(target)
    try:
        _append_project_audit(
            audit_target,
            {
                "event_id": event_id,
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "phase": "created",
                "action": "create_project_file",
                "project_path": str(target),
                "project_sha256": snapshot.sha256,
            },
        )
    except OSError as exc:
        raise ProjectStoreError(
            f"Project file was created at {target}, but audit completion failed: {exc}"
        ) from exc
    return snapshot


def _append_project_audit(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parse_reference(value: object) -> ProjectReference:
    fields = {"id", "name", "path", "created_at"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ProjectStoreError("Project reference has unknown or missing fields.")
    identifier, name, path, created = (value[key] for key in ("id", "name", "path", "created_at"))
    if not isinstance(identifier, str) or not identifier or len(identifier) > 80:
        raise ProjectStoreError("Project reference ID is invalid.")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ProjectStoreError("Project reference name must be 1–120 characters.")
    if not isinstance(path, str) or not Path(path).is_absolute() or len(path) > 4096:
        raise ProjectStoreError("Project reference path must be absolute.")
    if not isinstance(created, str):
        raise ProjectStoreError("Project reference timestamp is invalid.")
    return ProjectReference(identifier, name.strip(), str(Path(path)), created)


def load_project_references(path: str | Path) -> ProjectReferenceLoad:
    target = Path(path)
    try:
        if target.stat().st_size > PROJECT_STORE_MAX_BYTES:
            raise ProjectStoreError("Project reference store exceeds its size limit.")
        data = target.read_bytes()
        value = json.loads(data.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {"schema_version", "projects"}:
            raise ProjectStoreError("Project reference store has unknown or missing fields.")
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != PROJECT_STORE_SCHEMA
        ):
            raise ProjectStoreError("Project reference schema is unsupported.")
        entries = value["projects"]
        if not isinstance(entries, list) or len(entries) > 1000:
            raise ProjectStoreError("Project reference list is invalid or too large.")
        refs = tuple(_parse_reference(item) for item in entries)
        if len({item.id for item in refs}) != len(refs) or len(
            {item.path.casefold() for item in refs}
        ) != len(refs):
            raise ProjectStoreError("Project reference IDs and paths must be unique.")
        return ProjectReferenceLoad(refs, True)
    except FileNotFoundError:
        return ProjectReferenceLoad((), True)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return ProjectReferenceLoad((), False, (str(exc),))


class ProjectReferenceStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        loaded = load_project_references(self.path)
        if not loaded.valid:
            raise ProjectStoreError(
                "Cannot edit invalid project references: " + "; ".join(loaded.warnings)
            )
        self.references = list(loaded.references)
        self._source_bytes = self.path.read_bytes() if self.path.exists() else None

    def add(self, path: str | Path, name: str | None = None) -> ProjectReference:
        project_path = str(Path(path).expanduser().absolute())
        existing = next(
            (item for item in self.references if item.path.casefold() == project_path.casefold()),
            None,
        )
        if existing is not None:
            return existing
        project_name = name.strip() if name is not None else ""
        if not project_name:
            project_name = Path(project_path).parent.name or Path(project_path).stem
        reference = ProjectReference(
            uuid4().hex,
            project_name[:120],
            project_path,
            datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._save([*self.references, reference])
        return reference

    def remove(self, identifier: str) -> None:
        remaining = [item for item in self.references if item.id != identifier]
        if len(remaining) == len(self.references):
            raise KeyError(identifier)
        self._save(remaining)

    def _save(self, references: list[ProjectReference]) -> None:
        current = self.path.read_bytes() if self.path.exists() else None
        if current != self._source_bytes:
            raise ProjectStoreError("Project references changed on disk; reload before editing.")
        payload = (
            json.dumps(
                {
                    "schema_version": PROJECT_STORE_SCHEMA,
                    "projects": [
                        {
                            "id": item.id,
                            "name": item.name,
                            "path": item.path,
                            "created_at": item.created_at,
                        }
                        for item in references
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if current is not None:
            backup = self.path.with_suffix(self.path.suffix + ".bak")
            if backup.exists():
                backup = self.path.with_name(
                    f"{self.path.name}.{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.bak"
                )
            with backup.open("xb") as stream:
                stream.write(current)
                stream.flush()
                os.fsync(stream.fileno())
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=self.path.parent,
            prefix=".mutagen-projects-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.references = list(references)
        self._source_bytes = self.path.read_bytes()
