"""Versioned user ignore presets and staged .gitignore/.dockerignore conversion."""

from __future__ import annotations

import fnmatch
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

IGNORE_SCHEMA_VERSION = 1
MAX_IGNORE_FILE_BYTES = 1024 * 1024
MAX_PRESETS = 1000
MAX_RULES_PER_PRESET = 256


class IgnorePresetError(ValueError):
    """An ignore preset or conversion cannot be safely applied."""


@dataclass(frozen=True, slots=True)
class IgnorePreset:
    id: str
    name: str
    description: str
    patterns: tuple[str, ...]
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class IgnorePresetLoad:
    presets: tuple[IgnorePreset, ...]
    valid: bool
    schema_version: int | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IgnoreRulePreview:
    line: int
    raw: str
    pattern: str | None
    supported: bool
    reason: str
    overrides: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class IgnoreConversionPreview:
    source_format: Literal["gitignore", "dockerignore"]
    rules: tuple[IgnoreRulePreview, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IgnorePresetImportPreview:
    preset: IgnorePreset
    action: Literal["create", "merge", "skip", "conflict"]
    reason: str


@dataclass(frozen=True, slots=True)
class IgnoreMatchExplanation:
    path: str
    ignored: bool
    matched_rule: str | None
    scope: str | None
    note: str


def validate_ignore_pattern(pattern: str) -> str:
    if not isinstance(pattern, str) or not pattern or len(pattern) > 1024:
        raise IgnorePresetError("Ignore rules must be 1–1024 characters.")
    if "\x00" in pattern or "\n" in pattern or "\r" in pattern:
        raise IgnorePresetError("Ignore rule contains a control character.")
    body = pattern[1:] if pattern.startswith("!") else pattern
    if (
        not body
        or re.match(r"^[A-Za-z]:[/\\]", body)
        or body.startswith("//")
        or body.startswith("~/")
        or body.startswith("~\\")
    ):
        raise IgnorePresetError("Ignore rules must be relative to a synchronization root.")
    if any(segment == ".." for segment in body.replace("\\", "/").split("/")):
        raise IgnorePresetError("Ignore rules cannot traverse outside a synchronization root.")
    if "\\" in body:
        raise IgnorePresetError("Backslash escapes are unsupported in saved native ignore rules.")
    return pattern


def path_aware_ignore_rule(sync_root: str | Path, selected_file: str | Path) -> str:
    """Return a safe exact, sync-root-relative rule for one selected regular file."""
    root_input = Path(sync_root).expanduser().absolute()
    file_input = Path(selected_file).expanduser().absolute()
    try:
        relative_input = file_input.relative_to(root_input)
        root = root_input.resolve(strict=True)
        selected = file_input.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise IgnorePresetError("Choose an existing file inside the synchronization root.") from exc
    if not root.is_dir() or not selected.is_file() or file_input.is_symlink():
        raise IgnorePresetError("Quick Ignore only accepts an existing regular file.")
    try:
        relative_resolved = selected.relative_to(root)
    except ValueError as exc:
        raise IgnorePresetError("Selected file resolves outside the synchronization root.") from exc
    if relative_input != relative_resolved:
        raise IgnorePresetError("Symlinked path components cannot be used for Quick Ignore.")
    if any(
        (root_input.joinpath(*relative_input.parts[:index])).is_symlink()
        for index in range(1, len(relative_input.parts) + 1)
    ):
        raise IgnorePresetError("Symlinked path components cannot be used for Quick Ignore.")
    pattern = relative_input.as_posix()
    if any(character in pattern for character in "*?[]") or pattern.startswith(("!", "#")):
        raise IgnorePresetError("This filename uses ignore syntax characters; add a rule manually.")
    return validate_ignore_pattern(pattern)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_preset(raw: object) -> IgnorePreset:
    fields = {"id", "name", "description", "patterns", "created_at", "updated_at"}
    if not isinstance(raw, dict) or set(raw) != fields:
        raise IgnorePresetError("Ignore preset has unknown or missing fields.")
    identifier, name, description = raw["id"], raw["name"], raw["description"]
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identifier):
        raise IgnorePresetError("Ignore preset ID is invalid.")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise IgnorePresetError("Ignore preset name must be 1–120 characters.")
    if not isinstance(description, str) or len(description) > 500:
        raise IgnorePresetError("Ignore preset description must be at most 500 characters.")
    patterns = raw["patterns"]
    if not isinstance(patterns, list) or len(patterns) > MAX_RULES_PER_PRESET:
        raise IgnorePresetError(f"Ignore preset must contain at most {MAX_RULES_PER_PRESET} rules.")
    clean = tuple(validate_ignore_pattern(pattern) for pattern in patterns)
    created, updated = raw["created_at"], raw["updated_at"]
    if not isinstance(created, str) or not isinstance(updated, str):
        raise IgnorePresetError("Ignore preset timestamps must be strings.")
    return IgnorePreset(identifier, name.strip(), description, clean, created, updated)


def load_ignore_presets(path: str | Path) -> IgnorePresetLoad:
    target = Path(path)
    try:
        if target.stat().st_size > 5 * MAX_IGNORE_FILE_BYTES:
            raise IgnorePresetError("Ignore preset store exceeds its size limit.")
        raw_bytes = target.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except FileNotFoundError:
        return IgnorePresetLoad((), True, IGNORE_SCHEMA_VERSION)
    except (OSError, UnicodeError, json.JSONDecodeError, IgnorePresetError) as exc:
        return IgnorePresetLoad((), False, None, (f"Ignore preset store could not be read: {exc}",))
    try:
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "presets"}:
            raise IgnorePresetError("Ignore preset store has unknown or missing fields.")
        version = raw["schema_version"]
        if type(version) is not int or version != IGNORE_SCHEMA_VERSION:
            raise IgnorePresetError(f"Unsupported ignore preset schema: {version!r}.")
        entries = raw["presets"]
        if not isinstance(entries, list) or len(entries) > MAX_PRESETS:
            raise IgnorePresetError(
                f"Ignore preset store must contain at most {MAX_PRESETS} presets."
            )
        presets = tuple(_parse_preset(entry) for entry in entries)
        if len({preset.id for preset in presets}) != len(presets):
            raise IgnorePresetError("Ignore preset IDs must be unique.")
        return IgnorePresetLoad(presets, True, version)
    except IgnorePresetError as exc:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        return IgnorePresetLoad((), False, version, (str(exc),))


class IgnorePresetStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        loaded = load_ignore_presets(self.path)
        if not loaded.valid:
            raise IgnorePresetError(
                "Cannot change invalid ignore presets: " + "; ".join(loaded.warnings)
            )
        self.presets = list(loaded.presets)
        self._source_bytes = self.path.read_bytes() if self.path.exists() else None

    def create(self, name: str, patterns: tuple[str, ...], description: str = "") -> IgnorePreset:
        now = _timestamp()
        preset = _parse_preset(
            {
                "id": uuid4().hex,
                "name": name,
                "description": description,
                "patterns": list(patterns),
                "created_at": now,
                "updated_at": now,
            }
        )
        self._save([*self.presets, preset])
        return preset

    def update(
        self, identifier: str, *, name: str, patterns: tuple[str, ...], description: str = ""
    ) -> IgnorePreset:
        old = next((preset for preset in self.presets if preset.id == identifier), None)
        if old is None:
            raise KeyError(identifier)
        updated = _parse_preset(
            {
                "id": old.id,
                "name": name,
                "description": description,
                "patterns": list(patterns),
                "created_at": old.created_at,
                "updated_at": _timestamp(),
            }
        )
        self._save([updated if preset.id == identifier else preset for preset in self.presets])
        return updated

    def delete(self, identifier: str) -> None:
        remaining = [preset for preset in self.presets if preset.id != identifier]
        if len(remaining) == len(self.presets):
            raise KeyError(identifier)
        self._save(remaining)

    def _save(self, presets: list[IgnorePreset]) -> None:
        if len(presets) > MAX_PRESETS:
            raise IgnorePresetError(
                f"Ignore preset store must contain at most {MAX_PRESETS} presets."
            )
        checked = tuple(_parse_preset(_preset_json(preset)) for preset in presets)
        if len({preset.id for preset in checked}) != len(checked):
            raise IgnorePresetError("Ignore preset IDs must be unique.")
        current_bytes = self.path.read_bytes() if self.path.exists() else None
        if current_bytes != self._source_bytes:
            raise IgnorePresetError("Ignore preset store changed on disk; reload before editing.")
        payload = (
            json.dumps(
                {
                    "schema_version": IGNORE_SCHEMA_VERSION,
                    "presets": [_preset_json(p) for p in checked],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".ignore-presets-", suffix=".tmp", dir=self.path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                backup = self.path.with_suffix(self.path.suffix + ".bak")
                if backup.exists():
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                    backup = self.path.with_name(f"{self.path.name}.{stamp}.bak")
                with backup.open("xb") as stream:
                    stream.write(self.path.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                directory = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        self.presets = list(checked)
        self._source_bytes = self.path.read_bytes()

    def search(self, query: str = "") -> tuple[IgnorePreset, ...]:
        needle = query.casefold().strip()
        return tuple(
            preset
            for preset in self.presets
            if not needle
            or needle in preset.name.casefold()
            or needle in preset.description.casefold()
        )


def _preset_json(preset: IgnorePreset) -> dict[str, object]:
    return {
        "id": preset.id,
        "name": preset.name,
        "description": preset.description,
        "patterns": list(preset.patterns),
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }


def preset_to_record(preset: IgnorePreset) -> dict[str, object]:
    """Return the strict portable representation of a validated preset."""
    return _preset_json(preset)


def parse_preset_record(raw: object) -> IgnorePreset:
    """Validate one preset received from a portable bundle."""
    return _parse_preset(raw)


def preview_preset_import(
    incoming: list[object] | tuple[object, ...],
    existing: list[IgnorePreset] | tuple[IgnorePreset, ...],
) -> tuple[IgnorePresetImportPreview, ...]:
    presets = tuple(_parse_preset(value) for value in incoming)
    by_id = {preset.id: preset for preset in existing}
    fingerprints = {_preset_fingerprint(preset) for preset in existing}
    result: list[IgnorePresetImportPreview] = []
    for preset in presets:
        current = by_id.get(preset.id)
        if current and _preset_fingerprint(current) == _preset_fingerprint(preset):
            result.append(
                IgnorePresetImportPreview(preset, "skip", "Same ID and content already exist.")
            )
        elif current:
            result.append(
                IgnorePresetImportPreview(preset, "conflict", "Same ID has different content.")
            )
        elif _preset_fingerprint(preset) in fingerprints:
            result.append(
                IgnorePresetImportPreview(preset, "skip", "Equivalent preset already exists.")
            )
        else:
            result.append(IgnorePresetImportPreview(preset, "create", "New preset."))
    return tuple(result)


def apply_preset_import(
    store: IgnorePresetStore,
    incoming: list[object] | tuple[object, ...],
    choices: dict[str, str],
) -> tuple[str, ...]:
    fresh = load_ignore_presets(store.path)
    if not fresh.valid or list(fresh.presets) != store.presets:
        raise IgnorePresetError("Ignore presets changed after preview; reload and review again.")
    preview = preview_preset_import(incoming, store.presets)
    next_presets = list(store.presets)
    by_id = {preset.id: index for index, preset in enumerate(next_presets)}
    outcomes: list[str] = []
    for item in preview:
        choice = choices.get(item.preset.id, "skip")
        if choice not in {"create", "merge", "skip"}:
            raise IgnorePresetError(f"Invalid import choice for preset {item.preset.id}.")
        if choice == "merge" and item.action != "conflict":
            raise IgnorePresetError("Merge is available only for a conflicting stable ID.")
        index = by_id.get(item.preset.id)
        if item.action == "conflict" and choice == "merge":
            assert index is not None
            next_presets[index] = item.preset
            outcomes.append("merge")
        elif choice == "create":
            preset = item.preset
            if index is not None:
                preset = IgnorePreset(
                    uuid4().hex,
                    preset.name,
                    preset.description,
                    preset.patterns,
                    preset.created_at,
                    preset.updated_at,
                )
            next_presets.append(preset)
            by_id[preset.id] = len(next_presets) - 1
            outcomes.append("create")
        else:
            outcomes.append("skip")
    if next_presets != store.presets:
        store._save(next_presets)
    return tuple(outcomes)


def _preset_fingerprint(preset: IgnorePreset) -> str:
    fields = (preset.name.casefold(), preset.description, preset.patterns)
    return json.dumps(fields, ensure_ascii=False, separators=(",", ":"))


def _supported_syntax(pattern: str) -> bool:
    body = pattern[1:] if pattern.startswith("!") else pattern
    if any(char.isspace() for char in body):
        return False
    if re.search(r"[^A-Za-z0-9._/!*?\[\]-]", body):
        return False
    return body.count("[") == body.count("]")


def _possible_overrides(pattern: str, previous: list[tuple[int, str]]) -> tuple[int, ...]:
    if not pattern.startswith("!"):
        return ()
    target = pattern[1:]
    matches = []
    for line, earlier in previous:
        root = earlier.rstrip("/")
        if (
            fnmatch.fnmatchcase(target, earlier)
            or target == root
            or target.startswith(root + "/")
            or earlier in {"*", "**", "**/*"}
        ):
            matches.append(line)
    return tuple(matches)


def parse_ignore_file(
    source: str | bytes,
    *,
    source_format: Literal["gitignore", "dockerignore"],
    max_bytes: int = MAX_IGNORE_FILE_BYTES,
) -> IgnoreConversionPreview:
    if source_format not in {"gitignore", "dockerignore"}:
        raise IgnorePresetError("Unsupported ignore source format.")
    try:
        data = source if isinstance(source, bytes) else source.encode("utf-8")
        if len(data) > max_bytes:
            raise IgnorePresetError(f"Ignore source exceeds {max_bytes} bytes.")
        text = data.decode("utf-8")
    except (UnicodeError, IgnorePresetError) as exc:
        raise IgnorePresetError(str(exc)) from exc
    rules: list[IgnoreRulePreview] = []
    previous: list[tuple[int, str]] = []
    warnings: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw:
            rules.append(IgnoreRulePreview(number, raw, None, False, "Blank line; skipped."))
            continue
        if raw.startswith("#"):
            rules.append(IgnoreRulePreview(number, raw, None, False, "Comment; skipped."))
            continue
        reason = "Supported pattern; order retained."
        supported = True
        candidate = raw
        if raw != raw.strip():
            supported, reason = (
                False,
                "Leading/trailing whitespace can change source-format semantics.",
            )
        elif raw.startswith("\\"):
            supported, reason = (
                False,
                "Escaped comment/negation syntax is not converted automatically.",
            )
        elif source_format == "dockerignore" and (raw.startswith("/") or raw.endswith("/")):
            supported, reason = (
                False,
                "Docker path normalization differs; rooted/directory-only pattern skipped.",
            )
        else:
            try:
                validate_ignore_pattern(candidate)
            except IgnorePresetError as exc:
                supported, reason = False, str(exc)
            if supported and not _supported_syntax(candidate):
                supported, reason = (
                    False,
                    "Pattern syntax is outside the verified conversion subset.",
                )
        overrides = _possible_overrides(candidate, previous) if supported else ()
        if supported and overrides:
            reason = "May override earlier ignore rule(s): " + ", ".join(map(str, overrides))
        if supported and not candidate.startswith("!"):
            previous.append((number, candidate))
        rules.append(
            IgnoreRulePreview(
                number, raw, candidate if supported else None, supported, reason, overrides
            )
        )
    if any(rule.overrides for rule in rules):
        warnings.append(
            "Negation rules may re-include content excluded by an earlier rule; review the order."
        )
    if any(not rule.supported and rule.pattern is None and rule.raw for rule in rules):
        warnings.append("Some source lines were skipped; unsupported rules were not added.")
    return IgnoreConversionPreview(source_format, tuple(rules), tuple(warnings))


def apply_converted_rules(
    preview: IgnoreConversionPreview, selected_lines: set[int]
) -> tuple[str, ...]:
    supported = {rule.line: rule.pattern for rule in preview.rules if rule.supported}
    if selected_lines - set(supported):
        raise IgnorePresetError("Only supported preview rows can be applied.")
    result: list[str] = []
    for rule in preview.rules:
        if rule.line in selected_lines and rule.pattern not in result:
            result.append(rule.pattern or "")
    return tuple(result)


def explain_ignore_path(
    path: str,
    *,
    global_rules: tuple[str, ...] = (),
    project_rules: tuple[str, ...] = (),
    session_rules: tuple[str, ...] = (),
) -> IgnoreMatchExplanation:
    """Return an explicitly approximate, ordered preview for a sync-root-relative path."""
    if not isinstance(path, str) or not path or "\x00" in path:
        raise IgnorePresetError("Enter a non-empty relative path.")
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or any(part in {".", ".."} for part in normalized.split("/")):
        raise IgnorePresetError("Path must stay inside the synchronization root.")
    if re.match(r"^[A-Za-z]:", normalized):
        raise IgnorePresetError("Path must be relative to the synchronization root.")
    ignored = False
    last_rule = None
    last_scope = None
    for scope, rules in (
        ("global", global_rules),
        ("project", project_rules),
        ("session", session_rules),
    ):
        for raw in rules:
            pattern = validate_ignore_pattern(raw)
            negated = pattern.startswith("!")
            body = pattern[1:] if negated else pattern
            directory_only = body.endswith("/")
            body = body.strip("/")
            if not body:
                continue
            if "/" in body:
                matched = fnmatch.fnmatchcase(normalized, body)
                if directory_only:
                    matched = matched or normalized.startswith(body + "/")
            else:
                components = normalized.split("/")
                matched = any(fnmatch.fnmatchcase(part, body) for part in components)
            if matched:
                ignored = not negated
                last_rule, last_scope = pattern, scope
    return IgnoreMatchExplanation(
        normalized,
        ignored,
        last_rule,
        last_scope,
        "Approximate preview only; confirm behavior with the installed Mutagen CLI.",
    )


def format_ignore_layers(
    *,
    global_rules: tuple[str, ...] = (),
    project_rules: tuple[str, ...] = (),
    session_rules: tuple[str, ...] = (),
) -> str:
    """Render ordered known rules by layer for a reviewable preview."""
    layers = (
        ("Global", global_rules),
        ("Project", project_rules),
        ("Session", session_rules),
    )
    return "\n".join(
        f"{name}:\n"
        + (
            "\n".join(f"  {index}. {rule}" for index, rule in enumerate(rules, 1))
            or "  (none loaded)"
        )
        for name, rules in layers
    )
