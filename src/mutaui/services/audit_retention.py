"""Operational audit file rotation, retention and safety rules."""

from __future__ import annotations

import contextlib
import json
import os
import stat
from pathlib import Path
from typing import Any

MAX_AUDIT_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB per audit file
MAX_AUDIT_BACKUPS = 3  # Keep up to 3 rotated copies (.1, .2, .3)


class AuditRetentionError(OSError):
    """Raised when writing to an audit file violates safety or retention rules."""


def safe_append_audit_record(
    path: Path | str,
    record: dict[str, object],
    *,
    max_bytes: int = MAX_AUDIT_FILE_BYTES,
    max_backups: int = MAX_AUDIT_BACKUPS,
) -> None:
    """Safely append a JSONL audit record with symlink protection and bounded rotation."""
    audit_path = Path(path).expanduser().absolute()
    if audit_path.is_symlink():
        raise AuditRetentionError("Audit file cannot be a symbolic link.")
    if audit_path.exists() and not stat.S_ISREG(audit_path.lstat().st_mode):
        raise AuditRetentionError("Audit path must be a regular file.")
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    if audit_path.exists() and audit_path.stat().st_size >= max_bytes:
        rotate_audit_file(audit_path, max_backups=max_backups)

    payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    descriptor = os.open(audit_path, flags, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def rotate_audit_file(path: Path, *, max_backups: int = MAX_AUDIT_BACKUPS) -> None:
    """Rotate path to path.1, path.1 to path.2, etc., safely removing the oldest."""
    for i in range(max_backups, 0, -1):
        src = path.with_name(f"{path.name}.{i - 1}" if i > 1 else path.name)
        dst = path.with_name(f"{path.name}.{i}")
        if i == max_backups and dst.exists():
            dst.unlink(missing_ok=True)
        if src.exists():
            with contextlib.suppress(OSError):
                os.replace(src, dst)


def audit_file_status(path: Path | str) -> dict[str, Any]:
    """Inspect size, record count, and retention state of an operational audit file."""
    audit_path = Path(path).expanduser().absolute()
    if not audit_path.exists() or not audit_path.is_file():
        return {"exists": False, "bytes": 0, "records": 0, "backups": 0}
    size = audit_path.stat().st_size
    records = 0
    try:
        with audit_path.open("r", encoding="utf-8", errors="replace") as stream:
            for _ in stream:
                records += 1
    except OSError:
        pass
    backups = sum(
        1 for i in range(1, 10) if audit_path.with_name(f"{audit_path.name}.{i}").exists()
    )
    return {
        "exists": True,
        "bytes": size,
        "records": records,
        "backups": backups,
        "max_bytes": MAX_AUDIT_FILE_BYTES,
        "max_backups": MAX_AUDIT_BACKUPS,
    }
