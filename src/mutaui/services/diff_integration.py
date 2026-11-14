"""Copy conflict inputs safely and launch a user-selected diff executable."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from mutaui.services.conflict_inspector import safe_local_conflict_path


class DiffIntegrationError(ValueError):
    """Raised when a local diff copy or executable is outside the safe contract."""


@dataclass(frozen=True, slots=True)
class DiffCopy:
    path: Path
    size_bytes: int
    sha256: str


def external_diff_arguments(
    executable: str | Path,
    left_copy: str | Path,
    right_copy: str | Path,
) -> tuple[str, ...]:
    """Validate all three paths and return a shell-free exact argv tuple."""
    binary = Path(executable).expanduser().absolute()
    if binary.is_symlink() or not binary.is_file():
        raise DiffIntegrationError("Select an existing regular diff-tool executable.")
    copies = (Path(left_copy), Path(right_copy))
    if any(source.is_symlink() or not source.is_file() for source in copies):
        raise DiffIntegrationError("Diff inputs must be existing regular local copies.")
    return (str(binary), *(str(source.absolute()) for source in copies))


def copy_local_conflict_for_diff(
    endpoint_root: str,
    relative_path: str,
    *,
    destination_directory: str | Path,
    max_bytes: int = 16 * 1024 * 1024,
) -> DiffCopy:
    """Make a stable, bounded, non-symlink local copy beside the remote artifact."""
    source = safe_local_conflict_path(endpoint_root, relative_path)
    if source is None or source.is_symlink():
        raise DiffIntegrationError("Local conflict path is missing or outside its endpoint root.")
    before = source.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
        raise DiffIntegrationError("Local conflict must be a regular file within the size limit.")
    destination_root = Path(destination_directory).resolve(strict=True)
    if not destination_root.is_dir():
        raise DiffIntegrationError("Diff copies require an existing private temporary directory.")
    target = destination_root / "local-conflict-copy"
    digest = hashlib.sha256()
    total = 0
    created_target = False
    try:
        with source.open("rb") as source_stream:
            output = target.open("xb")
            created_target = True
            with output:
                while True:
                    chunk = source_stream.read(min(65536, max_bytes - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise DiffIntegrationError(
                            "Local conflict changed or exceeded the size limit."
                        )
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        after = source.stat()
        if (
            total != before.st_size
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ino != before.st_ino
        ):
            raise DiffIntegrationError("Local conflict changed while its diff copy was made.")
        target.chmod(stat.S_IREAD)
        return DiffCopy(target, total, digest.hexdigest())
    except Exception:
        if created_target:
            target.unlink(missing_ok=True)
        raise
