"""Tests for the isolated Mutagen daemon harness (CI-05 / F2-004 / F2-AC-010 / F2-AC-011)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import psutil
import pytest

from tests.support.mutagen_daemon import IsolatedMutagenDaemon


def _mutagen_binary() -> str | None:
    return (
        os.environ.get("MUTAGEN_BINARY") or shutil.which("mutagen") or shutil.which("mutagen.exe")
    )


def _isolated_daemon_process(daemon: IsolatedMutagenDaemon) -> psutil.Process:
    matches = []
    for process in psutil.process_iter(["pid", "environ"]):
        environment = process.info.get("environ") or {}
        if environment.get("MUTAGEN_DATA_DIRECTORY") == str(daemon.data_dir):
            matches.append(process)
    assert len(matches) == 1
    return matches[0]


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_isolated_daemon_lifecycle_phases(tmp_path: Path) -> None:
    binary = _mutagen_binary()
    assert binary is not None

    original_data_dir = os.environ.get("MUTAGEN_DATA_DIRECTORY")
    daemon = IsolatedMutagenDaemon(binary, tmp_path / "lifecycle-test")
    assert os.environ.get("MUTAGEN_DATA_DIRECTORY") == original_data_dir
    assert daemon.phase == "unstarted"

    with daemon:
        assert daemon.phase == "ready"
        assert daemon.diagnostics.ready_time >= daemon.diagnostics.start_time
        # Check active communication
        sessions = daemon.client.list_sessions("sync")
        assert isinstance(sessions, list)

    assert daemon.phase == "stopped"
    assert os.environ.get("MUTAGEN_DATA_DIRECTORY") == original_data_dir


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_isolated_daemon_repeat_cycles(tmp_path: Path) -> None:
    binary = _mutagen_binary()
    assert binary is not None

    # Exercise repeated readiness, listing, and acknowledged shutdown on the native CLI.
    for i in range(10):
        cycle_dir = tmp_path / f"cycle-{i}"
        with IsolatedMutagenDaemon(binary, cycle_dir) as daemon:
            assert daemon.phase == "ready"
            assert isinstance(daemon.client.list_sessions("sync"), list)
        assert daemon.phase == "stopped"


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_isolated_daemon_recovers_after_external_stop(tmp_path: Path) -> None:
    binary = _mutagen_binary()
    assert binary is not None
    daemon = IsolatedMutagenDaemon(binary, tmp_path / "recovery-test")

    with daemon:
        daemon.client.command(["daemon", "stop"], timeout=daemon.stop_timeout)
        daemon.start()
        assert isinstance(daemon.client.list_sessions("sync"), list)

    assert daemon.phase == "stopped"


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_isolated_daemon_recovers_after_process_crash(tmp_path: Path) -> None:
    binary = _mutagen_binary()
    assert binary is not None
    daemon = IsolatedMutagenDaemon(binary, tmp_path / "process-crash-recovery")

    with daemon:
        crashed_process = _isolated_daemon_process(daemon)
        crashed_process.kill()
        crashed_process.wait(timeout=daemon.stop_timeout)

        daemon.start()
        assert daemon.phase == "ready"
        assert isinstance(daemon.client.list_sessions("sync"), list)


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


def test_scoped_harness_never_changes_process_global_environment(tmp_path: Path):
    """Constructor and cleanup must not retarget the user's daemon or HOME."""
    binary = tmp_path / ("mutagen.exe" if os.name == "nt" else "mutagen")
    binary.write_text("disposable stub", encoding="utf-8")
    original = {
        key: os.environ.get(key) for key in ("MUTAGEN_DATA_DIRECTORY", "HOME", "USERPROFILE")
    }
    daemon = IsolatedMutagenDaemon(binary, tmp_path / "short")
    assert daemon.client._process_environment["MUTAGEN_DATA_DIRECTORY"] == str(daemon.data_dir)
    assert daemon.client._process_environment["HOME"] == str(daemon.home_dir)
    assert all(os.environ.get(key) == value for key, value in original.items())
    if os.name != "nt":
        assert len(str(daemon.data_dir)) < 70

    # The stub never started; the data dir is test-owned and not the user's.
    daemon._started = False
    daemon.client._daemon_state = lambda: False
    daemon.stop()
    assert not daemon._owned_root.exists()
    assert all(os.environ.get(key) == value for key, value in original.items())


def test_failure_artifacts_do_not_expose_paths_or_native_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    executable = tmp_path / ("mutagen.exe" if os.name == "nt" else "mutagen")
    executable.write_text("dummy", encoding="utf-8")
    daemon = IsolatedMutagenDaemon(executable, tmp_path / "case")
    daemon.data_dir.mkdir(parents=True, exist_ok=True)
    (daemon.data_dir / "daemon.log").write_text(
        "private-key-content-and-user-hostname", encoding="utf-8"
    )
    daemon._capture_failure_diagnostics(
        "unable to connect to private-user@example.org /home/private-user"
    )
    artifacts = list((tmp_path / "test-results" / "daemon-diagnostics").glob("*.json"))
    assert len(artifacts) == 1
    text = artifacts[0].read_text(encoding="utf-8")
    assert '"error_category": "connection"' in text
    assert '"daemon_log_present": true' in text
    assert "private-user" not in text
    assert "private-key-content" not in text
    assert str(daemon.data_dir) not in text
    daemon.client._daemon_state = lambda: False
    daemon.stop()


def test_unacknowledged_stop_keeps_diagnostic_data(tmp_path: Path, monkeypatch) -> None:
    from mutagen_client import MutagenCommandTimeout

    executable = tmp_path / ("mutagen.exe" if os.name == "nt" else "mutagen")
    executable.write_text("dummy", encoding="utf-8")
    daemon = IsolatedMutagenDaemon(executable, tmp_path / "case")
    daemon.data_dir.mkdir(parents=True)
    daemon._start_attempted = True

    def reject_stop(_arguments, **_kwargs):
        raise MutagenCommandTimeout("timed out")

    monkeypatch.setattr(daemon.client, "command", reject_stop)
    monkeypatch.setattr(daemon.client, "_daemon_state", lambda: False)
    daemon.stop()
    assert daemon.phase == "stop_failed"
    assert daemon.data_dir.exists()
    # Manual removal of test-owned fixture after validating non-destructive stop.
    import shutil

    shutil.rmtree(daemon._owned_root)


def test_delayed_child_shutdown_keeps_cleanup_safe(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / ("mutagen.exe" if os.name == "nt" else "mutagen")
    executable.write_text("stub", encoding="utf-8")
    daemon = IsolatedMutagenDaemon(executable, tmp_path / "case", stop_timeout=1.0)
    daemon.data_dir.mkdir(parents=True)
    daemon._start_attempted = True
    polls = iter((True, True, False))
    monkeypatch.setattr(daemon.client, "command", lambda _args, **_kwargs: "")
    monkeypatch.setattr(daemon.client, "_daemon_state", lambda: next(polls))
    daemon.stop()
    assert daemon.phase == "stopped"
    assert not daemon.data_dir.exists()


def test_still_running_child_prevents_destructive_cleanup(tmp_path: Path, monkeypatch) -> None:
    executable = tmp_path / ("mutagen.exe" if os.name == "nt" else "mutagen")
    executable.write_text("stub", encoding="utf-8")
    daemon = IsolatedMutagenDaemon(executable, tmp_path / "case", stop_timeout=0.01)
    daemon.data_dir.mkdir(parents=True)
    daemon._start_attempted = True
    monkeypatch.setattr(daemon.client, "command", lambda _args, **_kwargs: "")
    monkeypatch.setattr(daemon.client, "_daemon_state", lambda: True)
    daemon.stop()
    assert daemon.phase == "stop_failed"
    assert daemon.data_dir.exists()
    shutil.rmtree(daemon._owned_root)


def test_isolated_daemon_uses_compact_private_paths(tmp_path: Path) -> None:
    """Unix-domain daemon IPC must not inherit verbose test helper paths."""
    daemon = IsolatedMutagenDaemon("mutagen", tmp_path / "lifecycle-test")
    assert daemon.data_dir.parent == daemon.home_dir.parent
    assert daemon.data_dir.parent.name.startswith("mu-")
    assert daemon.data_dir.name == "data"
    assert daemon.home_dir.name == "home"
    assert max(len(str(daemon.data_dir)), len(str(daemon.home_dir))) < 100
    assert daemon.data_dir != Path.home() / ".mutagen"
