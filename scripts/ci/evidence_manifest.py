"""Bind generated JUnit and coverage artifacts to the exact verified checkout.

Only a successful run_tests.py invocation may generate this manifest. CI report
verification fails closed on absent/mismatched SHA, run ID, or artifact digests.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_git_sha() -> str:
    git_binary = shutil.which("git")
    if not git_binary:
        raise FileNotFoundError("Git executable required for verified provenance")
    return subprocess.check_output(
        [git_binary, "rev-parse", "HEAD"],
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=10,
    ).strip()


def working_tree_is_dirty() -> bool:
    git_binary = shutil.which("git")
    if not git_binary:
        raise FileNotFoundError("Git executable required for verified provenance")
    return bool(
        subprocess.check_output(
            [git_binary, "status", "--porcelain", "--untracked-files=all"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
    )


def create_evidence_manifest(junit_path: Path, coverage_path: Path) -> Path:
    """Create an atomic manifest only for existing, newly validated artifacts."""
    commit = verified_git_sha()
    dirty = working_tree_is_dirty()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        expected = os.environ.get("GITHUB_SHA")
        if not expected or commit != expected:
            raise ValueError("CI checkout does not match GITHUB_SHA")
        if dirty:
            raise ValueError("CI checkout is dirty")
        if not os.environ.get("GITHUB_RUN_ID"):
            raise ValueError("CI run ID is required for evidence provenance")
    manifest_path = junit_path.parent / "evidence.json"
    manifest: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "commit": commit,
        "working_tree_dirty": dirty,
        "ci_run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "junit_sha256": file_sha256(junit_path),
        "coverage_sha256": file_sha256(coverage_path),
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    staging = manifest_path.with_suffix(".json.tmp")
    try:
        staging.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, manifest_path)
    finally:
        staging.unlink(missing_ok=True)
    return manifest_path


def verify_evidence_manifest(
    junit_path: Path,
    coverage_path: Path,
    *,
    expected_commit: str,
    expected_run_id: str,
) -> bool:
    """Reject missing or reused test evidence; never silently infer provenance."""
    path = junit_path.parent / "evidence.json"
    if not path.is_file() or not junit_path.is_file() or not coverage_path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return bool(
            isinstance(data, dict)
            and data.get("schema") == SCHEMA_VERSION
            and data.get("commit") == expected_commit
            and data.get("working_tree_dirty") is False
            and data.get("ci_run_id") == expected_run_id
            and data.get("junit_sha256") == file_sha256(junit_path)
            and data.get("coverage_sha256") == file_sha256(coverage_path)
        )
    except (ValueError, OSError, TypeError):
        return False
