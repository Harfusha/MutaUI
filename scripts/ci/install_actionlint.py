"""Centralized installer and checksum verification for actionlint."""

from __future__ import annotations

import hashlib
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

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


def install_actionlint(target_dir: Path | str | None = None) -> Path:
    if target_dir is None:
        runner_temp = os.environ.get("RUNNER_TEMP") or os.environ.get("TEMP") or "/tmp"
        target_dir = Path(runner_temp) / "actionlint"
    else:
        target_dir = Path(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir.parent / "actionlint.tar.gz"

    print(f"Downloading actionlint v{ACTIONLINT_VERSION} from {ACTIONLINT_URL}...")
    urllib.request.urlretrieve(ACTIONLINT_URL, archive_path)

    print("Verifying SHA-256 digest...")
    verify_sha256(archive_path, ACTIONLINT_SHA256)

    print(f"Extracting actionlint to {target_dir}...")
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extract("actionlint", path=target_dir)

    binary_path = target_dir / "actionlint"
    if binary_path.exists():
        binary_path.chmod(0o755)
    print(f"actionlint successfully verified and installed at {binary_path}")
    return binary_path


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        install_actionlint(dest)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
