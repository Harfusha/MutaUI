"""Centralized installer and checksum verification for actionlint."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

MAX_ACTIONLINT_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_ACTIONLINT_BINARY_BYTES = 32 * 1024 * 1024

ACTIONLINT_VERSION = "1.7.12"
ACTIONLINT_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
ACTIONLINT_URL = (
    f"https://github.com/rhysd/actionlint/releases/download/v{ACTIONLINT_VERSION}/"
    f"actionlint_{ACTIONLINT_VERSION}_linux_amd64.tar.gz"
)


def verify_sha256(file_path: Path, expected_hash: str) -> bool:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest().lower()
    if actual_hash != expected_hash.lower():
        raise ValueError(
            f"SHA-256 verification failed for {file_path}:\n"
            f"  Expected: {expected_hash.lower()}\n"
            f"  Actual:   {actual_hash}"
        )
    return True


def download_actionlint_archive(destination: Path) -> None:
    """Bound download size and time before inspecting even a verified artifact."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Download into a disposable staging file, never into an executable archive
    # that a later installer invocation could mistake for a verified artifact.
    staged: Path | None = None
    try:
        with (
            urllib.request.urlopen(ACTIONLINT_URL, timeout=30) as response,
            tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".actionlint-download-", delete=False
            ) as output,
        ):
            staged = Path(output.name)
            total = 0
            while chunk := response.read(65536):
                total += len(chunk)
                if total > MAX_ACTIONLINT_ARCHIVE_BYTES:
                    raise ValueError("actionlint archive exceeds size limit")
                output.write(chunk)
        os.replace(staged, destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def extract_verified_actionlint(archive_path: Path, target_dir: Path) -> Path:
    """Extract only the expected regular ELF file; never follow tar links."""
    target_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, mode="r:gz") as archive:
        member = archive.getmember("actionlint")
        if not member.isfile() or member.size <= 0 or member.size > MAX_ACTIONLINT_BINARY_BYTES:
            raise ValueError("actionlint archive must contain a bounded regular binary")
        binary = archive.extractfile(member)
        if binary is None:
            raise ValueError("Missing actionlint binary payload")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".actionlint-", dir=target_dir, delete=False
            ) as output:
                temporary = Path(output.name)
                shutil.copyfileobj(binary, output, length=65536)
            temporary.chmod(0o755)
            destination = target_dir / "actionlint"
            os.replace(temporary, destination)
            return destination
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def install_actionlint(target_dir: Path | str | None = None) -> Path:
    if target_dir is None:
        runner_temp = os.environ.get("RUNNER_TEMP") or os.environ.get("TEMP") or "/tmp"
        target_dir = Path(runner_temp) / "actionlint"
    else:
        target_dir = Path(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir.parent / "actionlint.tar.gz"

    print(f"Downloading pinned actionlint v{ACTIONLINT_VERSION}...")
    download_actionlint_archive(archive_path)
    verify_sha256(archive_path, ACTIONLINT_SHA256)
    binary_path = extract_verified_actionlint(archive_path, target_dir)
    print(f"actionlint successfully verified and installed at {binary_path}")
    return binary_path


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        install_actionlint(dest)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
