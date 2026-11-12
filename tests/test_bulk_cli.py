"""Bulk commands are explicit, safe and never use shell or --all."""
import pytest
import mutagen_client
from mutagen_client import MutagenClient, MutagenError


def test_sync_now_many_uses_skip_wait_and_exact_ids(tmp_path, monkeypatch):
    binary = tmp_path / "mutagen.exe"
    binary.write_bytes(b"test")
    captured = []
    class Response:
        returncode = 0
        stdout = "ok"
        stderr = ""
    monkeypatch.setattr(mutagen_client.subprocess, "run", lambda args, **kwargs: captured.append((args, kwargs)) or Response())
    cli = MutagenClient(str(binary))
    assert cli.execute_many("sync", "flush", ["x", "y", "x"]) == "ok"
    argv, kwargs = captured[0]
    assert argv[1:] == ["sync", "flush", "--skip-wait", "x", "y"]
    assert "shell" not in kwargs
    assert kwargs["stdin"] is not None


def test_bulk_commands_require_explicit_safe_targets():
    cli = MutagenClient("")
    for targets in ([], ["--all"], ["x", "-a"], ["abc other"], [None]):
        with pytest.raises(MutagenError):
            cli.execute_many("sync", "pause", targets)
    with pytest.raises(MutagenError):
        cli.execute_many("daemon", "stop", ["a"])
    with pytest.raises(MutagenError):
        cli.execute_many("forward", "flush", ["a"])
    with pytest.raises(MutagenError):
        cli.execute_many("sync", "pause", ["x"]*501)


def test_native_windows_startup_interpretation():
    from mutagen_client import native_sync_startup_state
    assert native_sync_startup_state({"paused": True}, "registered") == "paused"
    assert native_sync_startup_state({"paused": False}, "registered") == "enabled"
    assert native_sync_startup_state({"paused": False}, "unregistered") == "needs-registration"
    assert native_sync_startup_state({"paused": False}, "other") == "needs-registration"
