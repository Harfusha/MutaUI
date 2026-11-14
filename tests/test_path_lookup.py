import ntpath
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mutaui.domain.models import Endpoint, SessionIdentity, SessionSnapshot
from mutaui.services.path_lookup import _is_within_path, find_local_sessions_for_path


def _snapshot(identifier, root, *, stale_reason=None, kind="sync"):
    return SessionSnapshot(
        identity=SessionIdentity(kind, identifier, identifier),
        native_config={},
        alpha_or_source=Endpoint("local", str(root), path=str(root)) if kind == "sync" else None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
        stale_reason=stale_reason,
    )


def test_local_path_lookup_returns_all_overlapping_exact_ids(tmp_path):
    root = tmp_path / "sync"
    nested = root / "nested"
    nested.mkdir(parents=True)
    file = nested / "file.txt"
    file.write_text("x", encoding="utf-8")
    snapshots = (
        _snapshot("outer", root),
        _snapshot("inner", nested),
        _snapshot("broken", tmp_path / "non-existent"),
    )

    assert find_local_sessions_for_path(snapshots, file) == ("inner", "outer")
    assert find_local_sessions_for_path(snapshots, tmp_path / "missing") == ()
    sibling = tmp_path / "sync-old"
    sibling.mkdir()
    assert find_local_sessions_for_path(snapshots, sibling) == ()


def test_local_path_lookup_resolves_directory_symlinks(tmp_path):
    root = tmp_path / "real-root"
    root.mkdir()
    file = root / "nested.txt"
    file.write_text("x", encoding="utf-8")
    alias = tmp_path / "linked-root"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.fail(f"Directory symlinks are unavailable: {exc}")
        # Fixed command; only pytest-owned temporary paths reach cmd.exe.
        command_processor = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
        junction = subprocess.run(  # noqa: S603
            [command_processor, "/c", "mklink", "/J", str(alias), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode:
            pytest.fail(f"Could not create a temporary directory junction: {junction.stderr}")

    assert find_local_sessions_for_path((_snapshot("linked", root),), alias / file.name) == (
        "linked",
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows path lookup is case-insensitive")
def test_local_path_lookup_accepts_case_folded_windows_paths(tmp_path):
    root = tmp_path / "MixedCase"
    root.mkdir()
    file = root / "Nested" / "File.txt"
    file.parent.mkdir()
    file.write_text("x", encoding="utf-8")
    case_variant = Path(str(file).swapcase())

    assert find_local_sessions_for_path((_snapshot("casefold", root),), case_variant) == (
        "casefold",
    )


def test_local_path_lookup_ignores_stale_and_non_sync_sessions(tmp_path):
    root = tmp_path / "sync"
    root.mkdir()
    snapshots = (
        _snapshot("stale", root, stale_reason="old"),
        _snapshot("forward", root, kind="forward"),
    )
    assert find_local_sessions_for_path(snapshots, root) == ()


@pytest.mark.parametrize(
    ("root", "candidate", "expected"),
    (
        (r"C:\Sync", r"c:\sync\Nested\file.txt", True),
        (r"C:\Sync", r"C:\Sync-old\file.txt", False),
        (r"C:\Sync", r"D:\Sync\file.txt", False),
        (r"\\server\share\Sync", r"\\SERVER\SHARE\sync\file.txt", True),
        (r"\\server\share\Sync", r"\\server\share2\Sync\file.txt", False),
    ),
)
def test_windows_path_containment(root, candidate, expected):
    assert (
        _is_within_path(root, candidate, commonpath=ntpath.commonpath, normcase=ntpath.normcase)
        is expected
    )


def test_local_path_lookup_matches_local_beta_and_skips_non_directories(tmp_path):
    root = tmp_path / "sync-beta"
    root.mkdir()
    file_in_root = root / "hello.txt"
    file_in_root.write_text("ok", encoding="utf-8")

    single_file = tmp_path / "standalone.txt"
    single_file.write_text("not a dir", encoding="utf-8")

    beta_snapshot = SessionSnapshot(
        identity=SessionIdentity("sync", "beta-only", "beta-only"),
        native_config={},
        alpha_or_source=Endpoint("ssh", "user@remote:/var/data"),
        beta_or_destination=Endpoint("local", str(root), path=str(root)),
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    file_snapshot = SessionSnapshot(
        identity=SessionIdentity("sync", "file-root", "file-root"),
        native_config={},
        alpha_or_source=Endpoint("local", str(single_file), path=str(single_file)),
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    assert find_local_sessions_for_path((beta_snapshot, file_snapshot), file_in_root) == (
        "beta-only",
    )
