"""Preview and safely apply explicit edits to a global Mutagen YAML file."""

from __future__ import annotations

import difflib
import hashlib
import os
import stat
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml.comments import CommentedMap

from .yaml_config import YAMLReadResult, load_yaml_file, parse_yaml_bytes, render_yaml_preview


class InvalidConfigForWrite(ValueError):
    """Raised when source or staged configuration cannot be safely serialized."""


class ConcurrentConfigChange(RuntimeError):
    """The source changed since it was loaded; caller must resolve the collision."""

    options = ("reload", "merge", "cancel")

    def __init__(self, latest: YAMLReadResult):
        super().__init__("Mutagen configuration changed externally; reload, merge, or cancel.")
        self.latest = latest


@dataclass(frozen=True, slots=True)
class YAMLProvenance:
    path: Path
    sha256: str
    raw_bytes: bytes
    encoding: str
    newline: str
    mode: int | None


@dataclass(frozen=True, slots=True)
class YAMLPreview:
    provenance: YAMLProvenance
    yaml_text: str
    yaml_bytes: bytes
    diff: str


@dataclass(frozen=True, slots=True)
class YAMLWriteResult:
    path: Path
    backup_path: Path
    sha256: str
    new_sha256: str


def _deep_update(target: CommentedMap, changes: Mapping[str, Any]) -> None:
    for key, value in changes.items():
        if not isinstance(key, str):
            raise InvalidConfigForWrite("Mutagen configuration keys must be strings.")
        current = target.get(key)
        if isinstance(current, CommentedMap) and isinstance(value, Mapping):
            _deep_update(current, value)
        else:
            target[key] = value


def _provenance(snapshot: YAMLReadResult) -> YAMLProvenance:
    if not snapshot.valid or snapshot.document is None or not snapshot.source_path:
        raise InvalidConfigForWrite("Invalid YAML source cannot be edited or overwritten.")
    path = Path(snapshot.source_path).absolute()
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise InvalidConfigForWrite(f"Could not inspect YAML file permissions: {exc}.") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise InvalidConfigForWrite(
            "Only a regular, non-symlink Mutagen config file can be edited."
        )
    return YAMLProvenance(
        path=path,
        sha256=snapshot.sha256,
        raw_bytes=snapshot.raw_bytes,
        encoding=snapshot.encoding or "utf-8",
        newline=snapshot.newline or "\n",
        mode=metadata.st_mode,
    )


def preview_yaml_edit(snapshot: YAMLReadResult, changes: Mapping[str, Any]) -> YAMLPreview:
    """Apply a deep mapping patch in memory and return serialized text plus diff."""
    provenance = _provenance(snapshot)
    if not isinstance(changes, Mapping):
        raise InvalidConfigForWrite("Staged YAML changes must be a mapping.")
    assert snapshot.document is not None
    document = deepcopy(snapshot.document)  # round-trip container retains comments
    _deep_update(document, changes)
    try:
        rendered = render_yaml_preview(document)
        if provenance.newline != "\n":
            rendered = rendered.replace("\n", provenance.newline)
        if provenance.encoding == "utf-8-sig":
            rendered = "\ufeff" + rendered
    except Exception as exc:
        raise InvalidConfigForWrite(f"Staged YAML cannot be serialized: {exc}.") from exc
    return preview_yaml_text(snapshot, rendered)


def preview_yaml_text(snapshot: YAMLReadResult, proposed_text: str) -> YAMLPreview:
    """Validate edited YAML text and produce a provenance-bound diff preview."""
    provenance = _provenance(snapshot)
    if not isinstance(proposed_text, str):
        raise InvalidConfigForWrite("Staged YAML must be text.")
    rendered = proposed_text
    # QTextEdit exposes normalized LF text; restore the source's dominant style.
    if provenance.newline != "\n":
        rendered = rendered.replace("\r\n", "\n").replace("\n", provenance.newline)
    if provenance.encoding == "utf-8-sig" and not rendered.startswith("\ufeff"):
        rendered = "\ufeff" + rendered
    try:
        output = rendered.encode(provenance.encoding)
    except (UnicodeError, LookupError) as exc:
        raise InvalidConfigForWrite(f"Staged YAML cannot be encoded: {exc}.") from exc
    validated = parse_yaml_bytes(output, source_path=str(provenance.path))
    if not validated.valid:
        raise InvalidConfigForWrite(f"Staged YAML failed validation: {validated.error}")
    old_text = provenance.raw_bytes.decode(provenance.encoding)
    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            rendered.splitlines(keepends=True),
            fromfile=f"{provenance.path} (current)",
            tofile=f"{provenance.path} (preview)",
        )
    )
    return YAMLPreview(provenance, rendered, output, diff)


def _backup_name(path: Path, suffix: str | None) -> Path:
    if suffix is not None:
        backup = path.with_name(path.name + suffix)
        if backup.exists():
            raise FileExistsError(f"Backup already exists: {backup}")
        return backup
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = path.with_name(f"{path.name}.{stamp}.bak")
    serial = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.{stamp}.{serial}.bak")
        serial += 1
    return candidate


def _flush_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_windows(target: Path, temporary: Path, backup: Path) -> None:
    import ctypes
    from ctypes import wintypes

    replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    replace_file.restype = wintypes.BOOL
    if not replace_file(str(target), str(temporary), str(backup), 0x00000001, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def apply_yaml_edit(preview: YAMLPreview, *, backup_suffix: str | None = None) -> YAMLWriteResult:
    """Write a reviewed preview only if its exact source bytes are still current."""
    provenance = preview.provenance
    path = provenance.path
    if path.is_symlink():
        raise InvalidConfigForWrite("Mutagen config became a symlink; write cancelled.")
    current = load_yaml_file(path)
    if not current.valid or current.sha256 != provenance.sha256:
        raise ConcurrentConfigChange(current)

    backup = _backup_name(path, backup_suffix)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(preview.yaml_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        if provenance.mode is not None:
            os.chmod(temporary, provenance.mode)

        # Close the edit-vs-write race as far as the platform's atomic replace allows.
        if path.is_symlink():
            raise InvalidConfigForWrite("Mutagen config became a symlink; write cancelled.")
        current = load_yaml_file(path)
        if not current.valid or current.sha256 != provenance.sha256:
            raise ConcurrentConfigChange(current)
        if os.name == "nt":
            _replace_windows(path, temporary, backup)
        else:
            with backup.open("xb") as stream:
                stream.write(provenance.raw_bytes)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        _flush_directory(path.parent)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)

    return YAMLWriteResult(
        path=path,
        backup_path=backup,
        sha256=provenance.sha256,
        new_sha256=hashlib.sha256(preview.yaml_bytes).hexdigest(),
    )
