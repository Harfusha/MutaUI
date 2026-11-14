"""Tests for the CLI adapter; no Mutagen installation is required."""

import json
import sys

import pytest

import mutagen_client
from mutagen_client import (
    MutagenClient,
    MutagenCommandError,
    MutagenCommandTimeout,
    MutagenError,
    MutagenLaunchError,
    ProcessSampler,
    classify,
    conflict_count,
    endpoint_text,
    human_bytes,
    parse_sessions,
    problem_count,
    read_registration,
)
from mutaui.services.action_planner import ActionPlanningError


def test_json_export_model():
    payload = [
        {
            "identifier": "sync_test",
            "name": "web",
            "status": 6,
            "paused": False,
            "alpha": {"protocol": 0, "path": "C:\\\\dev", "files": 3},
            "beta": {"protocol": 1, "user": "root", "host": "test", "path": "/app"},
        }
    ]
    sessions = parse_sessions(json.dumps(payload))
    assert sessions[0]["name"] == "web"
    assert classify(sessions[0], "sync") == ("active", "Watching")
    assert endpoint_text(sessions[0]["beta"]) == "root@test:/app"


def test_empty_export_and_invalid():
    assert parse_sessions("[]\n") == []
    with pytest.raises(MutagenError):
        parse_sessions("no sessions")
    with pytest.raises(MutagenError):
        parse_sessions('{"name":"foo"}')


def test_empty_executable_discovery_returns_empty_when_nothing_is_installed(monkeypatch):
    monkeypatch.setattr(mutagen_client.shutil, "which", lambda _name: None)
    monkeypatch.setattr(mutagen_client, "_known_mutagen_locations", lambda: ())

    assert mutagen_client.clean_executable("") == ""


def test_empty_executable_discovery_prefers_a_path_binary(monkeypatch):
    monkeypatch.setattr(
        mutagen_client.shutil,
        "which",
        lambda name: "C:/tools/mutagen.exe" if name == "mutagen" else None,
    )

    assert mutagen_client.clean_executable("") == "C:/tools/mutagen.exe"


def test_status_and_counters():
    session = {
        "paused": False,
        "status": 11,
        "conflicts": [1],
        "excludedConflicts": 2,
        "alpha": {"scanProblems": [{"path": "x"}], "excludedScanProblems": 3},
        "beta": {"transitionProblems": [1, 2]},
    }
    assert classify(session, "sync")[0] == "error"
    assert conflict_count(session) == 3
    assert problem_count(session) == 6
    assert classify({"paused": True, "status": 6}, "sync")[0] == "paused"
    assert classify({"paused": False, "status": 2}, "sync")[0] == "error"
    assert classify({"paused": False, "status": 3}, "forward")[0] == "active"


def test_endpoints():
    assert (
        endpoint_text({"protocol": 11, "host": "php", "path": "/var/www"})
        == "docker://php:/var/www"
    )
    assert (
        endpoint_text({"protocol": 0, "endpoint": "tcp:localhost:5432"}, "forward")
        == "tcp:localhost:5432"
    )
    assert endpoint_text(None) == "—"
    assert human_bytes(23) == "23 B"
    assert human_bytes(1024) == "1.0 KB"
    assert human_bytes(2 * 1024**2) == "2.0 MB"
    assert human_bytes(1024**3) == "1.0 GB"
    assert human_bytes(1024**5) == "1024.0 TB"


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


def test_clean_executable_finds_windows_program_files_install_after_path(tmp_path, monkeypatch):
    install = tmp_path / "Program Files" / "Mutagen"
    install.mkdir(parents=True)
    binary = install / "mutagen.exe"
    binary.write_bytes(b"test executable")
    monkeypatch.setattr(mutagen_client.sys, "platform", "win32")
    monkeypatch.setattr(mutagen_client.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert mutagen_client.clean_executable("") == str(binary)


def test_clean_executable_finds_linux_user_bin_after_path(tmp_path, monkeypatch):
    install = tmp_path / ".local" / "bin"
    install.mkdir(parents=True)
    binary = install / "mutagen"
    binary.write_bytes(b"test executable")
    monkeypatch.setattr(mutagen_client.sys, "platform", "linux")
    monkeypatch.setattr(mutagen_client.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(mutagen_client.shutil, "which", lambda _name: None)
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramW6432", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert mutagen_client.clean_executable("") == str(binary)


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
    assert kwargs["shell"] is False


def test_execute_uses_exact_target_no_shell(monkeypatch, tmp_path):
    exe = tmp_path / "mutagen.exe"
    exe.write_bytes(b"stub")
    commands = []

    class Completed:
        returncode = 0
        stdout = "paused"
        stderr = ""

    import mutagen_client

    monkeypatch.setattr(
        mutagen_client.subprocess,
        "run",
        lambda command, **kw: commands.append(command) or Completed(),
    )
    client = MutagenClient(str(exe))
    native_row = {"identifier": "sync_abc", "configuration": {"mode": "two-way-safe"}}
    client.list_sessions = lambda _area: [native_row]
    fingerprint = client.session_preflight_fingerprint([native_row])
    assert (
        client.execute(
            "sync",
            "pause",
            "sync_abc",
            operator_consent=True,
            expected_preflight_fingerprint=fingerprint,
        )
        == "paused"
    )
    assert commands == [[str(exe), "sync", "pause", "sync_abc"]]
    assert [event.decision for event in client.action_planner.audit] == [
        "planned",
        "consented",
        "finished",
    ]


def test_execute_refuses_stale_session_snapshot_before_mutation(monkeypatch, tmp_path):
    exe = tmp_path / "mutagen.exe"
    exe.write_bytes(b"stub")
    commands = []

    class Completed:
        returncode = 0
        stdout = "paused"
        stderr = ""

    import mutagen_client

    monkeypatch.setattr(
        mutagen_client.subprocess,
        "run",
        lambda command, **kw: commands.append(command) or Completed(),
    )
    client = MutagenClient(str(exe))
    original = {"identifier": "sync_abc", "configuration": {"mode": "two-way-safe"}}
    changed = {"identifier": "sync_abc", "configuration": {"mode": "one-way-safe"}}
    client.list_sessions = lambda _area: [changed]

    with pytest.raises(MutagenError, match="changed after its action preview"):
        client.execute(
            "sync",
            "pause",
            "sync_abc",
            operator_consent=True,
            expected_preflight_fingerprint=client.session_preflight_fingerprint([original]),
        )

    assert commands == []
    assert client.action_planner.audit[-1].decision == "stale"


def test_preflight_ignores_live_counters_but_tracks_configuration():
    original = {
        "identifier": "sync_abc",
        "configuration": {"mode": "two-way-safe"},
        "status": 6,
        "files": 20,
        "conflicts": [],
    }
    active = {**original, "status": 9, "files": 24}
    changed = {**active, "configuration": {"mode": "one-way-safe"}}

    fingerprint = MutagenClient.session_preflight_fingerprint([original])

    assert MutagenClient.session_preflight_fingerprint([active]) == fingerprint
    assert MutagenClient.session_preflight_fingerprint([changed]) != fingerprint


def test_execute_requires_explicit_consent_before_native_preflight():
    client = MutagenClient("")
    client.list_sessions = lambda _area: pytest.fail("preflight must not run before consent")

    with pytest.raises(MutagenError, match="explicit operator confirmation"):
        client.execute("sync", "pause", "sync_abc")


def test_daemon_start_uses_planned_exact_command_and_native_postcheck(monkeypatch):
    import mutagen_client

    state = {"running": False}

    class PlannedDaemonClient(MutagenClient):
        def _daemon_state(self):
            return state["running"]

        def command(self, arguments, *, timeout):
            assert arguments == ["daemon", "start"]
            assert timeout == 40
            state["running"] = True
            return "started"

    monkeypatch.setattr(mutagen_client, "read_registration", lambda _binary: ("unsupported", ""))
    client = PlannedDaemonClient("mutagen")
    plan = client.prepare_daemon_plan("start")
    assert plan.target_ids[0].startswith("daemon:")
    plan = client.consent_action_plan(plan, consent=True)

    result = client.execute("daemon", "start", operator_consent=True, action_plan=plan)

    assert result == "started"
    assert client.action_planner.audit[-1].decision == "finished"
    assert client.action_planner.audit[-1].target_ids == plan.target_ids


def test_daemon_stop_requires_typed_r3_confirmation_and_verifies_stopped(monkeypatch):
    import mutagen_client

    state = {"running": True}

    class PlannedDaemonClient(MutagenClient):
        def _daemon_state(self):
            return state["running"]

        def command(self, arguments, *, timeout):
            assert arguments == ["daemon", "stop"]
            state["running"] = False
            return "stopped"

    monkeypatch.setattr(mutagen_client, "read_registration", lambda _binary: ("unsupported", ""))
    client = PlannedDaemonClient("mutagen")
    plan = client.prepare_daemon_plan("stop")
    assert plan.risk == "R3"
    assert plan.requires_typed_confirmation
    plan = client.consent_action_plan(
        plan,
        consent=True,
        typed_confirmation=plan.typed_confirmation,
    )

    result = client.execute("daemon", "stop", operator_consent=True, action_plan=plan)

    assert result == "stopped"
    assert client.action_planner.audit[-1].decision == "finished"


def test_daemon_action_rejects_changed_preflight_without_running_command(monkeypatch):
    import mutagen_client

    class ChangingDaemonClient(MutagenClient):
        def __init__(self):
            super().__init__("mutagen")
            self.states = iter((False, True))
            self.commands = []

        def _daemon_state(self):
            return next(self.states)

        def command(self, arguments, *, timeout):
            self.commands.append(arguments)
            return "unexpected"

    monkeypatch.setattr(mutagen_client, "read_registration", lambda _binary: ("unsupported", ""))
    client = ChangingDaemonClient()
    plan = client.prepare_daemon_plan("start")
    plan = client.consent_action_plan(plan, consent=True)

    with pytest.raises(MutagenError, match="changed after its action preview"):
        client.execute("daemon", "start", operator_consent=True, action_plan=plan)

    assert client.commands == []
    assert client.action_planner.audit[-1].decision == "stale"


def test_daemon_actions_reject_session_targets_and_unplanned_execution():
    client = MutagenClient("mutagen")
    with pytest.raises(MutagenError, match="do not accept session targets"):
        client.execute("daemon", "start", target="unexpected")
    with pytest.raises(MutagenError, match="consented exact daemon ActionPlan"):
        client.execute("daemon", "start", operator_consent=True)


def test_postcheck_failure_closes_plan_as_stale(monkeypatch, tmp_path):
    exe = tmp_path / "mutagen.exe"
    exe.write_bytes(b"stub")
    commands = []

    class Completed:
        returncode = 0
        stdout = "paused"
        stderr = ""

    import mutagen_client

    monkeypatch.setattr(
        mutagen_client.subprocess,
        "run",
        lambda command, **kw: commands.append(command) or Completed(),
    )
    client = MutagenClient(str(exe))
    native_row = {"identifier": "sync_abc", "configuration": {"mode": "two-way-safe"}}
    calls = 0

    def list_sessions(_area):
        nonlocal calls
        calls += 1
        return [native_row] if calls == 1 else []

    client.list_sessions = list_sessions
    fingerprint = client.session_preflight_fingerprint([native_row])

    with pytest.raises(MutagenError, match="post-check"):
        client.execute(
            "sync",
            "pause",
            "sync_abc",
            operator_consent=True,
            expected_preflight_fingerprint=fingerprint,
        )

    assert commands == [[str(exe), "sync", "pause", "sync_abc"]]
    assert client.action_planner.audit[-1].decision == "stale"


def test_create_requires_reviewed_plan_and_verifies_new_native_id():
    class CreateClient(MutagenClient):
        def __init__(self, session_batches):
            super().__init__("")
            self.session_batches = iter(session_batches)
            self.commands = []

        def list_sessions(self, _area):
            return next(self.session_batches)

        def command(self, arguments, *, timeout):
            self.commands.append((arguments, timeout))
            return "created"

    options = ["--name=created-exact", "--mode=two-way-safe", "/alpha", "/beta"]
    created = {"identifier": "sync-new-exact", "name": "created-exact"}
    client = CreateClient([[], [created]])
    plan = client.prepare_create_plan("sync", options)
    plan = client.consent_action_plan(plan, consent=True)

    output = client.execute(
        "sync",
        "create",
        options=options,
        operator_consent=True,
        action_plan=plan,
    )

    assert output == "created"
    assert client.commands == [(["sync", "create", *options], 120)]
    assert client.action_planner.audit[-1].decision == "finished"
    assert "sync-new-exact" in client.action_planner.audit[-1].reason
    assert client.last_created_session == (
        "sync",
        "sync-new-exact",
        ("sync", "create", *options),
    )


def test_replica_create_requires_backup_and_exact_typed_confirmation():
    client = MutagenClient("")
    options = ["--mode=one-way-replica", "/alpha", "/beta"]

    with pytest.raises(ActionPlanningError, match="backup strategy"):
        client.prepare_create_plan("sync", options)

    backup_choice = "operator-confirmed-recoverable-beta-backup"
    plan = client.prepare_create_plan("sync", options, backup_choice=backup_choice)
    assert plan.risk == "R3"
    assert plan.requires_typed_confirmation

    with pytest.raises(ActionPlanningError, match="Typed confirmation"):
        client.consent_action_plan(
            plan,
            consent=True,
            typed_confirmation="APPLY wrong-target",
            backup_choice=backup_choice,
        )
    assert client.action_planner.audit[-1].decision == "cancelled"


def test_create_postcheck_refuses_ambiguous_new_session_ids():
    class AmbiguousCreateClient(MutagenClient):
        def __init__(self):
            super().__init__("")
            self.session_batches = iter(
                [
                    [],
                    [
                        {"identifier": "sync-new-a", "name": "first"},
                        {"identifier": "sync-new-b", "name": "second"},
                    ],
                ]
            )

        def list_sessions(self, _area):
            return next(self.session_batches)

        def command(self, _arguments, *, timeout):
            assert timeout == 120
            return "created"

    client = AmbiguousCreateClient()
    options = ["--mode=two-way-safe", "/alpha", "/beta"]
    plan = client.prepare_create_plan("sync", options)
    plan = client.consent_action_plan(plan, consent=True)

    with pytest.raises(MutagenError, match="new exact session ID could not be verified"):
        client.execute(
            "sync",
            "create",
            options=options,
            operator_consent=True,
            action_plan=plan,
        )

    assert client.action_planner.audit[-1].decision == "stale"


def test_registration_platform():
    if sys.platform != "win32":
        assert read_registration("")[0] == "unsupported"


def test_forward_create_fails_closed_when_socket_option_is_not_advertised(monkeypatch):
    client = MutagenClient("mutagen")
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        return "Options:\n  --socket-overwrite-mode=<mode>\n"

    monkeypatch.setattr(client, "command", command)

    with pytest.raises(MutagenError, match="not supported by the installed Mutagen"):
        client.prepare_create_plan(
            "forward",
            [
                "--socket-owner-source=operator",
                "unix:/tmp/source.sock",
                "unix:/tmp/destination.sock",
            ],
        )

    assert calls == [(["forward", "create", "--help"], {"readonly": True, "timeout": 5})]


def test_forward_create_accepts_socket_options_advertised_by_installed_cli(monkeypatch):
    client = MutagenClient("mutagen")
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        return (
            "Options:\n"
            "  --socket-owner-source=<owner>\n"
            "  --socket-permission-mode-destination=<mode>\n"
        )

    monkeypatch.setattr(client, "command", command)
    options = [
        "--socket-owner-source=operator",
        "--socket-permission-mode-destination=0600",
        "unix:/tmp/source.sock",
        "unix:/tmp/destination.sock",
    ]

    plan = client.prepare_create_plan("forward", options)

    assert plan.argv == ("forward", "create", *options)
    assert plan.risk == "R2"
    assert calls == [(["forward", "create", "--help"], {"readonly": True, "timeout": 5})]


def test_forward_socket_overwrite_uses_high_risk_plan(monkeypatch):
    client = MutagenClient("mutagen")
    monkeypatch.setattr(
        client,
        "command",
        lambda *_args, **_kwargs: "Options:\n  --socket-overwrite-mode-source=<mode>\n",
    )

    plan = client.prepare_create_plan(
        "forward",
        [
            "--socket-overwrite-mode-source=overwrite",
            "unix:/tmp/source.sock",
            "tcp:localhost:8080",
        ],
    )

    assert plan.action == "forward_socket_overwrite"
    assert plan.risk == "R3"


def test_command_requires_a_discoverable_binary_and_supported_environment(tmp_path, monkeypatch):
    # This case verifies the missing-binary path even when integration tests
    # expose an isolated Mutagen executable through PATH.
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(MutagenError, match="was not found"):
        MutagenClient("").command(["version"])
    missing = MutagenClient("mutagen")
    missing.binary = str(tmp_path / "missing-mutagen.exe")
    with pytest.raises(MutagenError, match="executable not found"):
        missing.command(["version"])

    binary = tmp_path / "mutagen.exe"
    binary.write_bytes(b"fake")
    client = MutagenClient(str(binary))
    with pytest.raises(MutagenError, match="Unsupported Mutagen environment"):
        client.command(["version"], env_overrides={"OTHER": "x"})
    with pytest.raises(MutagenError, match="absolute path"):
        client.command(["version"], env_overrides={"MUTAGEN_DATA_DIRECTORY": "relative"})


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "message"),
    [
        (1, "fallback output", "command failed", "command failed"),
        (1, "fallback output", "", "fallback output"),
        (2, "", "", "Exit code: 2"),
    ],
)
def test_command_reports_native_failure_details(
    tmp_path, monkeypatch, returncode, stdout, stderr, message
):
    binary = tmp_path / "mutagen.exe"
    binary.write_bytes(b"fake")
    client = MutagenClient(str(binary))
    monkeypatch.setattr(
        mutagen_client.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr}
        )(),
    )

    with pytest.raises(MutagenCommandError, match=message):
        client.command(["version"])


def test_command_translates_timeout_and_launch_errors(tmp_path, monkeypatch):
    binary = tmp_path / "mutagen.exe"
    binary.write_bytes(b"fake")
    client = MutagenClient(str(binary))
    monkeypatch.setattr(
        mutagen_client.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            mutagen_client.subprocess.TimeoutExpired("mutagen", 5)
        ),
    )
    with pytest.raises(MutagenCommandTimeout, match="timed out after 35 s"):
        client.command(["version"])

    monkeypatch.setattr(
        mutagen_client.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("launch failed")),
    )
    with pytest.raises(MutagenLaunchError, match="launch failed"):
        client.command(["version"])


def test_command_timeout_terminates_real_child_process(tmp_path):
    import psutil

    marker = tmp_path / "child.pid"
    code = (
        "import os,time; "
        f"open({str(marker)!r}, 'w', encoding='ascii').write(str(os.getpid())); "
        "time.sleep(30)"
    )
    client = MutagenClient(sys.executable)

    with pytest.raises(MutagenCommandTimeout, match="timed out after 2 s"):
        client.command(["-c", code], timeout=2)

    child_pid = int(marker.read_text(encoding="ascii"))
    assert not psutil.pid_exists(child_pid)


@pytest.mark.parametrize("second_read,expected_read_rate", [(180, 40.0), (80, 0.0)])
def test_process_sampler_tracks_only_mutagen_and_ignores_counter_resets(
    monkeypatch, second_read, expected_read_rate
):
    from types import SimpleNamespace

    class GuiProcess:
        def cpu_percent(self, *, interval):
            assert interval is None
            return 4.5

        def memory_info(self):
            return SimpleNamespace(rss=500)

    class Process:
        pid = 12
        info = {"name": "Mutagen.exe", "memory_info": SimpleNamespace(rss=200)}

        def __init__(self):
            self.cpu = 1.0
            self.read = 100
            self.write = 200

        def create_time(self):
            return 1.0

        def cpu_times(self):
            return SimpleNamespace(user=self.cpu, system=0.0)

        def io_counters(self):
            return SimpleNamespace(read_bytes=self.read, write_bytes=self.write)

    process = Process()
    monkeypatch.setattr(mutagen_client.psutil, "Process", lambda _pid: GuiProcess())
    sampler = ProcessSampler()
    monkeypatch.setattr(
        mutagen_client.psutil,
        "process_iter",
        lambda _attrs: [SimpleNamespace(info={"name": "python.exe"}), process],
    )
    times = iter((1.0, 3.0))
    monkeypatch.setattr(mutagen_client.time, "monotonic", lambda: next(times))

    first = sampler.sample_detailed()
    process.cpu = 2.0
    process.read = second_read
    process.write = 100
    second = sampler.sample_detailed()

    assert first["processes"] == 1
    assert second["cpu"] == 50.0
    assert second["read_rate"] == expected_read_rate
    assert second["write_rate"] == 0.0
    assert second["memory"] == 200
    assert second["gui_cpu"] == 4.5
    assert sampler.last_processes[0]["name"] == "mutagen.exe"


def test_process_sampler_handles_unavailable_os_counters_and_memory(monkeypatch):
    from types import SimpleNamespace

    class GuiProcess:
        def cpu_percent(self, *, interval):
            raise OSError("process disappeared")

        def memory_info(self):
            raise OSError("process disappeared")

    class Process:
        pid = 22
        info = {"name": "mutagen-agent"}

        def create_time(self):
            return 2.0

        def cpu_times(self):
            return SimpleNamespace(user=1.0, system=0.5)

        def io_counters(self):
            raise OSError("I/O counters unavailable")

        def memory_info(self):
            raise OSError("memory unavailable")

    class BrokenProcess:
        info = {"name": "mutagen"}

        def create_time(self):
            raise OSError("process exited")

    monkeypatch.setattr(mutagen_client.psutil, "Process", lambda _pid: GuiProcess())
    sampler = ProcessSampler()
    monkeypatch.setattr(
        mutagen_client.psutil,
        "process_iter",
        lambda _attrs: [SimpleNamespace(info={}), BrokenProcess(), Process()],
    )
    monkeypatch.setattr(mutagen_client.time, "monotonic", lambda: 1.0)

    result = sampler.sample_detailed()

    assert result["processes"] == 1
    assert result["memory"] == 0
    assert result["gui_cpu"] == 0.0
    assert result["gui_memory"] == 0
    assert sampler.last_processes[0]["read_rate"] == 0.0


@pytest.mark.parametrize(
    ("raw", "expected", "result"),
    [
        ('"C:/Mutagen/mutagen.exe" daemon start', "C:/Mutagen/mutagen.exe", "registered"),
        ("other command", "C:/Mutagen/mutagen.exe", "other"),
        (17, "C:/Mutagen/mutagen.exe", "unknown"),
    ],
)
def test_windows_registration_classifies_read_only_registry_values(
    monkeypatch, raw, expected, result
):
    from types import SimpleNamespace

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    fake_winreg = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_READ=1,
        OpenKey=lambda *_args: Key(),
        QueryValueEx=lambda *_args: (raw, 1),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(mutagen_client.sys, "platform", "win32")

    assert read_registration(expected)[0] == result


def test_daemon_planning_rejects_invalid_and_unsupported_registration_actions(monkeypatch):
    monkeypatch.setattr(mutagen_client, "read_registration", lambda _binary: ("unsupported", ""))
    client = MutagenClient("mutagen")

    with pytest.raises(MutagenError, match="Invalid daemon command"):
        client.prepare_daemon_plan("restart")
    with pytest.raises(MutagenError, match="unsupported on this platform"):
        client.prepare_daemon_plan("register")

    fingerprint = client._daemon_fingerprint("start", probe=False)
    assert len(fingerprint) == 64


@pytest.mark.parametrize(
    "options",
    [
        ["--all", "/alpha", "/beta"],
        ["--mode=two-way-safe", "/alpha\x00", "/beta"],
        ["--mode=two-way-safe", 17, "/beta"],
    ],
)
def test_create_plan_rejects_broad_and_malformed_arguments(options):
    with pytest.raises(MutagenError, match="invalid or broad argument"):
        MutagenClient("mutagen").prepare_create_plan("sync", options)


@pytest.mark.parametrize(
    "option",
    [
        "--socket-unrecognized=owner",
        "--socket-owner-source",
        "--socket-owner-source=",
        "--socket-owner-source=bad\nvalue",
    ],
)
def test_forward_create_rejects_invalid_socket_option_syntax(option):
    with pytest.raises(MutagenError, match="socket option"):
        MutagenClient("mutagen").prepare_create_plan(
            "forward", [option, "unix:/tmp/source", "unix:/tmp/destination"]
        )


def test_session_action_requires_every_exact_target_before_planning():
    client = MutagenClient("mutagen")
    client.list_sessions = lambda _area: []

    with pytest.raises(MutagenError, match="exact session no longer exists"):
        client._planned_session_action(
            "sync",
            "pause",
            ["missing-id"],
            ["sync", "pause", "missing-id"],
            expected_fingerprint="snapshot",
            operator_consent=True,
            timeout=40,
        )


def test_create_execution_rejects_a_consent_for_different_arguments():
    client = MutagenClient("")
    planned = client.prepare_create_plan("sync", ["--mode=two-way-safe", "/a", "/b"])
    consented = client.consent_action_plan(planned, consent=True)

    with pytest.raises(MutagenError, match="do not match"):
        client._execute_planned_create(
            ["sync", "create", "--mode=two-way-safe", "/other", "/b"],
            consented,
            operator_consent=True,
            timeout=120,
        )

    assert client.action_planner.audit[-1].decision == "cancelled"


def test_execute_terminate_refuses_a_session_that_remains_in_native_status():
    native = {"identifier": "sync-exact", "name": "Sync target"}

    class Client(MutagenClient):
        def __init__(self):
            super().__init__("mutagen")
            self.snapshots = iter(([native], [native]))

        def list_sessions(self, _area):
            return next(self.snapshots)

        def command(self, _args, *, timeout):
            return "terminated"

    client = Client()
    fingerprint = client.session_preflight_fingerprint([native])

    with pytest.raises(MutagenError, match="terminated session still present"):
        client.execute(
            "sync",
            "terminate",
            "sync-exact",
            operator_consent=True,
            expected_preflight_fingerprint=fingerprint,
        )

    assert client.action_planner.audit[-1].decision == "stale"


def test_registration_platform_fallback_and_windows_value_classification(monkeypatch):
    monkeypatch.setattr(mutagen_client.sys, "platform", "darwin")
    assert read_registration("/usr/bin/mutagen") == ("unsupported", "")
    assert mutagen_client._known_mutagen_locations()[0].as_posix() == "/opt/homebrew/bin/mutagen"

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    binary = r"C:\Mutagen\mutagen.exe"
    expected = f'"{binary}" daemon start'

    class Winreg:
        HKEY_CURRENT_USER = object()
        KEY_READ = 1

        @staticmethod
        def OpenKey(*_args):
            return Key()

        @staticmethod
        def QueryValueEx(_key, _name):
            return expected, 1

    monkeypatch.setattr(mutagen_client.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", Winreg)
    assert read_registration(binary) == ("registered", expected)


def test_execute_many_deduplicates_explicit_targets_and_keeps_flush_nonblocking(monkeypatch):
    client = MutagenClient("")
    captured = {}

    def planned(area, action, targets, arguments, **kwargs):
        captured.update(area=area, action=action, targets=targets, arguments=arguments, **kwargs)
        return "planned"

    monkeypatch.setattr(client, "_planned_session_action", planned)

    result = client.execute_many(
        "sync",
        "flush",
        ["session-a", "session-a", "session-b"],
        operator_consent=True,
        expected_preflight_fingerprint="snapshot-hash",
    )

    assert result == "planned"
    assert captured["targets"] == ["session-a", "session-b"]
    assert captured["arguments"] == ["sync", "flush", "--skip-wait", "session-a", "session-b"]
    assert captured["expected_fingerprint"] == "snapshot-hash"
    assert captured["timeout"] == 120


@pytest.mark.parametrize(
    "action,daemon_running,registration,expected_error",
    [
        ("start", False, "unregistered", "could not find the started daemon"),
        ("stop", True, "unregistered", "daemon still running"),
        ("register", False, "unregistered", "could not verify daemon registration"),
        ("unregister", False, "registered", "could not verify registration removal"),
    ],
)
def test_planned_daemon_actions_fail_when_native_postcheck_does_not_converge(
    monkeypatch, action, daemon_running, registration, expected_error
):
    client = MutagenClient("mutagen")
    commands = []
    state = {"running": daemon_running, "registration": registration}
    monkeypatch.setattr(client, "_daemon_state", lambda: state["running"])
    monkeypatch.setattr(
        mutagen_client,
        "read_registration",
        lambda _binary: (state["registration"], "mutagen daemon " + state["registration"]),
    )
    monkeypatch.setattr(
        client,
        "command",
        lambda args, **_kwargs: commands.append(args) or "completed",
    )
    plan = client.prepare_daemon_plan(action)
    consented = client.consent_action_plan(
        plan, consent=True, typed_confirmation=plan.typed_confirmation
    )

    with pytest.raises(MutagenError, match=expected_error):
        client.execute("daemon", action, operator_consent=True, action_plan=consented)

    assert commands == [["daemon", action]]


def test_command_requires_absolute_isolated_mutagen_data_directory(monkeypatch):
    client = MutagenClient("mutagen")
    client.binary = "mutagen.exe"
    monkeypatch.setattr(mutagen_client.os.path, "isfile", lambda _path: True)

    with pytest.raises(MutagenError, match="data directory must be an absolute path"):
        client.command(
            ["daemon", "start"],
            env_overrides={"MUTAGEN_DATA_DIRECTORY": "relative-test-data"},
        )


def test_command_forwards_only_the_valid_isolated_data_directory(tmp_path, monkeypatch):
    client = MutagenClient("mutagen")
    client.binary = "mutagen.exe"
    captured = {}
    monkeypatch.setattr(mutagen_client.os.path, "isfile", lambda _path: True)

    def run(argv, **kwargs):
        captured.update(argv=argv, kwargs=kwargs)
        return mutagen_client.subprocess.CompletedProcess(argv, 0, "version", "")

    monkeypatch.setattr(mutagen_client.subprocess, "run", run)
    data_directory = str(tmp_path / "isolated-mutagen-data")

    assert (
        client.command(
            ["version"],
            readonly=True,
            env_overrides={"MUTAGEN_DATA_DIRECTORY": data_directory},
        )
        == "version"
    )
    assert captured["argv"] == ["mutagen.exe", "version"]
    assert captured["kwargs"]["env"]["MUTAGEN_DATA_DIRECTORY"] == data_directory
    assert captured["kwargs"]["env"]["MUTAGEN_DISABLE_AUTOSTART"] == "1"
    assert captured["kwargs"]["env"]["NO_COLOR"] == "1"


def test_list_sessions_rejects_unsupported_kind_before_cli(monkeypatch):
    client = MutagenClient("mutagen")
    monkeypatch.setattr(
        client, "command", lambda *_args, **_kwargs: pytest.fail("CLI must not run")
    )

    with pytest.raises(ValueError, match="Unknown session type"):
        client.list_sessions("daemon")


def test_create_execution_requires_consent_and_a_consented_exact_plan():
    client = MutagenClient("mutagen")
    with pytest.raises(MutagenError, match="explicit operator confirmation"):
        client.execute("sync", "create", options=["/alpha", "/beta"])
    with pytest.raises(MutagenError, match="consented create ActionPlan"):
        client.execute("sync", "create", options=["/alpha", "/beta"], operator_consent=True)


def test_create_plan_rejects_missing_exact_endpoint():
    with pytest.raises(MutagenError, match="two exact endpoints"):
        MutagenClient("mutagen").prepare_create_plan("sync", ["/alpha"])


def test_execute_many_non_flush_does_not_inject_flush_only_flag(monkeypatch):
    client = MutagenClient("mutagen")
    captured = {}

    def planned(area, action, targets, arguments, **kwargs):
        captured.update(area=area, action=action, targets=targets, arguments=arguments)
        return "planned"

    monkeypatch.setattr(client, "_planned_session_action", planned)
    assert client.execute_many("sync", "pause", ["session-one"], operator_consent=True) == "planned"
    assert captured["arguments"] == ["sync", "pause", "session-one"]
