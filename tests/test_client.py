"""Tests for the CLI adapter; no Mutagen installation is required."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutagen_client import (
    MutagenClient,
    MutagenError,
    classify,
    conflict_count,
    endpoint_text,
    human_bytes,
    parse_sessions,
    problem_count,
    read_registration,
)


def test_json_export_model():
    payload = [{
        "identifier": "sync_test", "name": "web", "status": 6,
        "paused": False, "alpha": {"protocol": 0, "path": "C:\\\\dev", "files": 3},
        "beta": {"protocol": 1, "user": "root", "host": "test", "path": "/app"}
    }]
    sessions = parse_sessions(json.dumps(payload))
    assert sessions[0]["name"] == "web"
    assert classify(sessions[0], "sync") == ("active", "Watching")
    assert endpoint_text(sessions[0]["beta"]) == "root@test:/app"


def test_empty_export_and_invalid():
    assert parse_sessions("[]\n") == []
    with pytest.raises(MutagenError): parse_sessions("no sessions")
    with pytest.raises(MutagenError): parse_sessions('{"name":"foo"}')


def test_status_and_counters():
    session = {"paused": False, "status": 11, "conflicts": [1], "excludedConflicts": 2,
               "alpha": {"scanProblems": [{"path": "x"}], "excludedScanProblems": 3},
               "beta": {"transitionProblems": [1, 2]}}
    assert classify(session, "sync")[0] == "error"
    assert conflict_count(session) == 3
    assert problem_count(session) == 6
    assert classify({"paused": True, "status": 6}, "sync")[0] == "paused"
    assert classify({"paused": False, "status": 2}, "sync")[0] == "error"
    assert classify({"paused": False, "status": 3}, "forward")[0] == "active"


def test_endpoints():
    assert endpoint_text({"protocol": 11, "host": "php", "path": "/var/www"}) == "docker://php:/var/www"
    assert endpoint_text({"protocol": 0, "endpoint": "tcp:localhost:5432"}, "forward") == "tcp:localhost:5432"
    assert endpoint_text(None) == "—"
    assert human_bytes(2 * 1024**2) == "2.0 MB"


def test_command_validation_prevents_bulk_actions():
    client = MutagenClient("")
    with pytest.raises(MutagenError, match="specific session"):
        client.execute("sync", "terminate")
    with pytest.raises(MutagenError, match="Invalid command"):
        client.execute("sync", "shell", "x")
    with pytest.raises(MutagenError, match="Invalid session identifier"):
        client.execute("sync", "pause", "--all")
    with pytest.raises(MutagenError, match="Two endpoints"):
        client.execute("sync", "create")


def test_exec_without_shell_and_readonly_env(monkeypatch, tmp_path):
    exe = tmp_path / "mutagen.exe"
    exe.write_bytes(b"stub")
    captured = []
    class Completed:
        returncode = 0
        stdout = "[]"
        stderr = ""
    def fake_run(cmd, **kwargs):
        captured.append((cmd, kwargs))
        return Completed()
    import mutagen_client
    monkeypatch.setattr(mutagen_client.subprocess, "run", fake_run)
    client = MutagenClient(str(exe))
    assert client.list_sessions("sync") == []
    cmd, kwargs = captured[0]
    assert cmd[0] == str(exe)
    assert cmd[1:] == ["sync", "list", "--template", "{{ json . }}"]
    assert kwargs["env"]["MUTAGEN_DISABLE_AUTOSTART"] == "1"
    assert kwargs["stdin"] is not None
    assert "shell" not in kwargs


def test_execute_uses_exact_target_no_shell(monkeypatch, tmp_path):
    exe = tmp_path / "mutagen.exe"; exe.write_bytes(b"stub")
    commands = []
    class Completed:
        returncode = 0
        stdout = "paused"
        stderr = ""
    import mutagen_client
    monkeypatch.setattr(mutagen_client.subprocess, "run", lambda command, **kw: commands.append(command) or Completed())
    client = MutagenClient(str(exe))
    assert client.execute("sync", "pause", "sync_abc") == "paused"
    assert commands == [[str(exe), "sync", "pause", "sync_abc"]]


def test_registration_platform():
    if sys.platform != "win32":
        assert read_registration("")[0] == "unsupported"
