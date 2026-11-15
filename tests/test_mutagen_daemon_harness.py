"""Tests for the isolated Mutagen daemon harness (CI-05 / F2-004 / F2-AC-010 / F2-AC-011)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from mutagen_client import MutagenClient
from tests.support.mutagen_daemon import IsolatedMutagenDaemon


def _mutagen_binary() -> str | None:
    return (
        os.environ.get("MUTAGEN_BINARY") or shutil.which("mutagen") or shutil.which("mutagen.exe")
    )


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_isolated_daemon_lifecycle_phases(tmp_path: Path) -> None:
    binary = _mutagen_binary()
    assert binary is not None

    daemon = IsolatedMutagenDaemon(binary, tmp_path / "lifecycle-test")
    assert daemon.phase == "unstarted"

    with daemon:
        assert daemon.phase == "ready"
        assert daemon.diagnostics.ready_time >= daemon.diagnostics.start_time
        # Check active communication
        client = MutagenClient(binary)
        sessions = client.list_sessions("sync")
        assert isinstance(sessions, list)

    assert daemon.phase == "stopped"


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_isolated_daemon_repeat_cycles(tmp_path: Path) -> None:
    binary = _mutagen_binary()
    assert binary is not None

    # Verify 3 consecutive start/stop cycles without state corruption
    for i in range(3):
        cycle_dir = tmp_path / f"cycle-{i}"
        with IsolatedMutagenDaemon(binary, cycle_dir) as daemon:
            assert daemon.phase == "ready"
        assert daemon.phase == "stopped"


def test_isolated_daemon_timeout_records_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate a fake binary that starts but never answers sync list
    fake_bin = tmp_path / "fake_mutagen.bat" if os.name == "nt" else tmp_path / "fake_mutagen.sh"
    fake_bin.write_text("exit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)

    daemon = IsolatedMutagenDaemon(fake_bin, tmp_path / "timeout-test", readiness_timeout=0.3)

    # Mock client.command to simulate connection failure
    from mutagen_client import MutagenError

    def failing_command(cmd, **_kwargs):
        if "daemon" in cmd and "start" in cmd:
            return ""
        raise MutagenError("Error: unable to connect to daemon")

    monkeypatch.setattr(daemon.client, "command", failing_command)

    with pytest.raises(TimeoutError, match="failed to become ready"):
        daemon.start()

    assert daemon.phase == "failed"
    assert daemon.diagnostics.error is not None
    # Verify diagnostic file was written
    diag_dir = Path("test-results") / "daemon-diagnostics"
    assert diag_dir.is_dir()
    recent_diags = list(diag_dir.glob("daemon_fail_*.json"))
    assert len(recent_diags) > 0


def test_isolated_daemon_uses_compact_private_paths(tmp_path: Path) -> None:
    """Unix-domain daemon IPC must not inherit verbose test helper paths."""
    daemon = IsolatedMutagenDaemon("mutagen", tmp_path / "lifecycle-test")
    assert daemon.data_dir == tmp_path / "lifecycle-test" / "d"
    assert daemon.home_dir == tmp_path / "lifecycle-test" / "h"
    assert daemon.data_dir != Path.home() / ".mutagen"
