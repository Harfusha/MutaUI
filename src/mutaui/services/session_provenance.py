"""Private, local-only creation provenance for exact Mutagen session IDs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_STORE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10_000
MAX_ARGUMENTS = 256
MAX_ARGUMENT_LENGTH = 16_384
_SECRET_SHAPED = re.compile(r"(?i)(?:password|token|secret|credential)\s*=")
_SECRET_FLAGS = {
    "--password",
    "--token",
    "--secret",
    "--credential",
    "--configuration-file",
}


class ProvenanceStoreError(ValueError):
    """Raised when saved creation provenance is unsafe or malformed."""


@dataclass(frozen=True, slots=True)
class SessionProvenance:
    session_identifier: str
    create_arguments: tuple[str, ...]
    created_at: str


class SessionProvenanceStore:
    """Atomic, non-portable store keyed only by native session identifier."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, session_identifier: str) -> SessionProvenance | None:
        records = self._read()
        raw = records.get(session_identifier)
        if raw is None:
            return None
        return self._decode_record(session_identifier, raw)

    def record(self, session_identifier: str, arguments: tuple[str, ...] | list[str]) -> None:
        identifier = _validate_identifier(session_identifier)
        argv = _validate_create_arguments(arguments)
        records = self._read()
        existing = records.get(identifier)
        if existing is not None:
            decoded = self._decode_record(identifier, existing)
            if decoded.create_arguments != argv:
                raise ProvenanceStoreError("Creation provenance for this exact ID already exists.")
            return
        if len(records) >= MAX_RECORDS:
            raise ProvenanceStoreError("Creation provenance store is full.")
        created_at = datetime.now(UTC).isoformat(timespec="seconds")
        records[identifier] = {
            "create_arguments": list(argv),
            "created_at": created_at,
            "integrity_sha256": _record_digest(identifier, argv, created_at),
        }
        self._write(records)

    def _read(self) -> dict[str, Any]:
        if self.path.is_symlink():
            raise ProvenanceStoreError("Creation provenance file cannot be a symbolic link.")
        try:
            size = self.path.stat().st_size
            if size > MAX_STORE_BYTES:
                raise ProvenanceStoreError("Creation provenance file exceeds the size limit.")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProvenanceStoreError(
                "Creation provenance file is unreadable or malformed."
            ) from exc
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "records"}:
            raise ProvenanceStoreError("Creation provenance file has an invalid schema.")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ProvenanceStoreError("Creation provenance schema is unsupported.")
        records = payload.get("records")
        if not isinstance(records, dict) or len(records) > MAX_RECORDS:
            raise ProvenanceStoreError(
                "Creation provenance records are invalid or exceed the limit."
            )
        for identifier, raw in records.items():
            _validate_identifier(identifier)
            self._decode_record(identifier, raw)
        return records

    def _decode_record(self, identifier: str, raw: Any) -> SessionProvenance:
        if not isinstance(raw, dict) or set(raw) != {
            "create_arguments",
            "created_at",
            "integrity_sha256",
        }:
            raise ProvenanceStoreError("Creation provenance record has an invalid shape.")
        argv = _validate_create_arguments(raw["create_arguments"])
        created_at = raw["created_at"]
        digest = raw["integrity_sha256"]
        if not isinstance(created_at, str) or len(created_at) > 64:
            raise ProvenanceStoreError("Creation provenance timestamp is invalid.")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ProvenanceStoreError("Creation provenance integrity digest is invalid.")
        if not hmac.compare_digest(digest, _record_digest(identifier, argv, created_at)):
            raise ProvenanceStoreError("Creation provenance integrity check failed.")
        return SessionProvenance(identifier, argv, created_at)

    def _write(self, records: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ProvenanceStoreError("Creation provenance file cannot be a symbolic link.")
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".session-provenance-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temp_path = Path(stream.name)
                if os.name != "nt":
                    os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
                json.dump(
                    {"schema_version": SCHEMA_VERSION, "records": records},
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
        except OSError as exc:
            raise ProvenanceStoreError(f"Could not save creation provenance: {exc}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)


def _validate_identifier(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 2048
        or any(character.isspace() or ord(character) < 32 for character in value)
        or value.startswith("-")
    ):
        raise ProvenanceStoreError("A valid exact native session identifier is required.")
    return value


def _validate_create_arguments(arguments: object) -> tuple[str, ...]:
    if not isinstance(arguments, (list, tuple)) or not 4 <= len(arguments) <= MAX_ARGUMENTS:
        raise ProvenanceStoreError("Creation provenance needs a bounded create argument list.")
    argv = tuple(arguments)
    if argv[0] not in {"sync", "forward"} or argv[1] != "create":
        raise ProvenanceStoreError("Only exact native session create arguments can be recorded.")
    if any(
        not isinstance(argument, str)
        or not argument
        or len(argument) > MAX_ARGUMENT_LENGTH
        or "\x00" in argument
        or _SECRET_SHAPED.search(argument)
        for argument in argv
    ):
        raise ProvenanceStoreError(
            "Creation provenance contains invalid or secret-shaped arguments."
        )
    if any(
        argument.casefold() in {"--all", "--all=true"}
        or argument.split("=", 1)[0].casefold() in _SECRET_FLAGS
        for argument in argv
    ):
        raise ProvenanceStoreError("Broad or sensitive create options cannot be recorded.")
    return argv


def _record_digest(identifier: str, argv: tuple[str, ...], created_at: str) -> str:
    canonical = json.dumps(
        {
            "session_identifier": identifier,
            "create_arguments": list(argv),
            "created_at": created_at,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
