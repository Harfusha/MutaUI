"""Opt-in local-daemon integration test; never touches the user's normal daemon."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime

import pytest

from forward_configuration import forward_configuration_rows
from ignore_presets import path_aware_ignore_rule
from mutagen_client import MutagenClient, MutagenError
from mutaui.adapters.cli_executor import LegacyMutagenExecutor
from mutaui.adapters.mutagen_snapshot import from_legacy_session
from mutaui.projects.native_project import load_native_project
from mutaui.projects.project_actions import (
    execute_project_action,
    plan_project_action,
    prepare_action_plan,
)
from mutaui.services.action_planner import ActionPlanner, ActionRequest
from mutaui.services.reconfiguration import (
    build_reconfiguration_preview,
    extract_sync_configuration,
    validate_native_command_snapshot,
)
from mutaui.services.replacement import (
    MutagenReplacementBackend,
    ReplacementRequest,
    replace_non_project_session,
)
from mutaui.services.replacement_command import render_sync_replacement_arguments
from mutaui.ui.onboarding import detect_binary_architectures


def _mutagen_binary():
    return (
        os.environ.get("MUTAGEN_BINARY") or shutil.which("mutagen") or shutil.which("mutagen.exe")
    )


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_installed_mutagen_binary_architecture_is_detectable():
    assert detect_binary_architectures(_mutagen_binary())


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_real_mutagen_safe_report_export_uses_isolated_cli_snapshot(tmp_path, monkeypatch):
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    import app as app_module

    binary = _mutagen_binary()
    daemon_data = tmp_path / "isolated-daemon"
    destination = tmp_path / "safe-report.json"
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module, "read_registration", lambda _binary: ("unregistered", ""))
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )

    client = MutagenClient(binary)
    window = None
    daemon_started = False
    try:
        client.command(["daemon", "start"], timeout=20)
        daemon_started = True

        qapp = QApplication.instance() or QApplication([])
        assert qapp is not None
        window = app_module.MainWindow(demo=False, history_path=tmp_path / "history.sqlite")
        window.client = client
        window._version_cache = ("", 0.0, "")
        window.timer.stop()
        window.metric_timer.stop()
        window.tail_timer.stop()

        loop = QEventLoop()
        wait_timer = QTimer()
        wait_timer.setInterval(10)

        def finish_when_snapshot_is_ready():
            observed = window.snapshot
            if (
                (observed.sync_observed_at and observed.forward_observed_at)
                or not window.pending_poll
                or time.monotonic() >= deadline
            ):
                loop.quit()

        deadline = time.monotonic() + 20
        wait_timer.timeout.connect(finish_when_snapshot_is_ready)
        wait_timer.start()
        window.refresh(force=True)
        loop.exec()
        wait_timer.stop()

        snapshot = window.snapshot
        assert not window.pending_poll
        assert snapshot.daemon
        assert snapshot.sync_observed_at is not None
        assert snapshot.forward_observed_at is not None
        assert snapshot.version

        window.export_safe_report()

        exported = json.loads(destination.read_text(encoding="utf-8"))
        payload = json.dumps(exported, ensure_ascii=False)
        assert exported["schema"] == "mutagen-control-safe-diagnostics-v1"
        assert exported["daemon_running"] is True
        assert exported["mutagen_version"] != "unknown"
        assert str(binary) not in payload
        assert str(daemon_data) not in payload
    finally:
        if window is not None:
            window.timer.stop()
            window.metric_timer.stop()
            window.tail_timer.stop()
            window.pool.waitForDone(10000)
            window._allow_exit = True
            window.close()
            window.history.close()
        if daemon_started:
            with suppress(Exception):
                client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_frozen_real_mutagen_refresh_does_not_spawn_process_storm(tmp_path, monkeypatch):
    import psutil
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    import app as app_module

    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")

    def binary_process_ids():
        found = set()
        expected = os.path.normcase(os.path.realpath(binary))
        for process in psutil.process_iter(["pid", "exe"]):
            try:
                executable = process.info.get("exe")
                if executable and os.path.normcase(os.path.realpath(executable)) == expected:
                    found.add(process.info["pid"])
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
        return found

    client = MutagenClient(binary)
    before_daemon = binary_process_ids()
    daemon_pid = None
    window = None
    try:
        client.command(["daemon", "start"], timeout=20)
        new_daemons = binary_process_ids() - before_daemon
        assert len(new_daemons) == 1
        daemon_pid = new_daemons.pop()
        daemon = psutil.Process(daemon_pid)
        qapp = QApplication.instance() or QApplication([])
        monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
        monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
        monkeypatch.setattr(app_module, "read_registration", lambda _binary: ("unregistered", ""))
        window = app_module.MainWindow(demo=False, history_path=tmp_path / "history.sqlite")
        window.client = type("ClientRef", (), {"binary": binary})()
        window._version_cache = ("3.2.1", app_module.time.monotonic(), binary)
        window.timer.stop()
        window.metric_timer.stop()
        window.tail_timer.stop()

        event_loop = QEventLoop()
        pulse_times = []
        max_pulse_gap = 0.0
        refresh_requests = 0
        peak_cli_processes = 0

        def record_pulse():
            nonlocal max_pulse_gap
            now = app_module.time.monotonic()
            if pulse_times:
                max_pulse_gap = max(max_pulse_gap, now - pulse_times[-1])
            pulse_times.append(now)

        pulse_timer = QTimer()
        pulse_timer.setInterval(10)
        pulse_timer.timeout.connect(record_pulse)
        request_timer = QTimer()
        request_timer.setInterval(50)

        def request_refresh():
            nonlocal refresh_requests
            if refresh_requests == 20:
                request_timer.stop()
                return
            window.refresh(force=refresh_requests % 2 == 0)
            refresh_requests += 1

        request_timer.timeout.connect(request_refresh)
        process_timer = QTimer()
        process_timer.setInterval(200)

        def observe_cli_processes():
            nonlocal peak_cli_processes
            live = binary_process_ids() - {daemon_pid}
            peak_cli_processes = max(peak_cli_processes, len(live))

        process_timer.timeout.connect(observe_cli_processes)
        stop_timer = QTimer()
        stop_timer.setSingleShot(True)
        stop_timer.timeout.connect(event_loop.quit)

        daemon.suspend()
        window.refresh()
        pulse_timer.start()
        request_timer.start()
        process_timer.start()
        stop_timer.start(2000)
        event_loop.exec()
        pulse_timer.stop()
        request_timer.stop()
        process_timer.stop()
        observe_cli_processes()

        assert refresh_requests == 20
        assert len(pulse_times) >= 50
        assert max_pulse_gap < 0.75
        assert window.pending_poll is True
        assert peak_cli_processes == 1
    finally:
        if window is not None:
            window._refresh_again = False
        if daemon_pid is not None:
            with suppress(psutil.NoSuchProcess):
                daemon = psutil.Process(daemon_pid)
                if daemon.status() == psutil.STATUS_STOPPED:
                    daemon.resume()
        if window is not None:
            window.timer.stop()
            window.metric_timer.stop()
            window.tail_timer.stop()
            window.pool.waitForDone(10000)
            qapp.processEvents()
            window._allow_exit = True
            window.close()
            window.history.close()
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_gui_exit_tray_exit_and_restart_leave_isolated_daemon_running(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(tmp_path / "daemon-data"))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    gui_lifecycle = """
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
import app as app_module
from mutagen_client import MutagenClient

settings = Path(sys.argv[1])
binary = sys.argv[2]
app_module.settings_path = lambda: settings
qapp = QApplication.instance() or QApplication([])
client = MutagenClient(binary)

def assert_daemon_running(stage):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if client._daemon_state():
            return
        time.sleep(0.1)
    raise AssertionError(f"daemon did not remain available after {stage}")

def open_window():
    return app_module.MainWindow(demo=True)

def close_for_cleanup(window):
    window.timer.stop()
    window.metric_timer.stop()
    window.tail_timer.stop()
    window._allow_exit = True
    window.close()
    window.history.close()

normal_exit = open_window()
normal_exit.conf["tray"] = False
normal_exit.close()
assert_daemon_running("normal GUI exit")

tray_exit = open_window()
tray_exit.quit_app()
assert_daemon_running("tray quit")

restarted = open_window()
assert_daemon_running("GUI restart")
close_for_cleanup(restarted)
"""

    try:
        client.command(["daemon", "start"], timeout=20)
        deadline = time.monotonic() + 5
        while not client._daemon_state() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert client._daemon_state(), "isolated Mutagen daemon failed to become ready"
        result = subprocess.run(  # noqa: S603 - runs this test's fixed GUI lifecycle script
            [sys.executable, "-c", gui_lifecycle, str(tmp_path / "settings.json"), binary],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_gui_reads_existing_isolated_session_without_mutating_it(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(tmp_path / "daemon-data"))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    client = MutagenClient(binary)
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    options = [
        f"--name=mutaui-gui-{uuid.uuid4().hex[:10]}",
        "--sync-mode=two-way-safe",
        str(alpha),
        str(beta),
    ]
    created_identifier = None
    gui_snapshot = """
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
import app as app_module
from mutagen_client import MutagenClient

binary, settings_path, expected_identifier = sys.argv[1:]
app_module.settings_path = lambda: Path(settings_path)
real_client = MutagenClient
app_module.MutagenClient = lambda _binary='', **kwargs: real_client(binary, **kwargs)
qapp = QApplication.instance() or QApplication([])
window = app_module.MainWindow()
window.refresh(force=True)
deadline = time.monotonic() + 20
while time.monotonic() < deadline:
    qapp.processEvents()
    if any(item.get("identifier") == expected_identifier for item in window.snapshot.sync):
        break
    time.sleep(0.02)
assert any(item.get("identifier") == expected_identifier for item in window.snapshot.sync), (
    "GUI refresh did not display the pre-existing native session"
)
window.timer.stop()
window.metric_timer.stop()
window.tail_timer.stop()
window._allow_exit = True
window.close()
window.history.close()
assert expected_identifier in {
    item.get("identifier") for item in real_client(binary).list_sessions("sync")
}, "GUI refresh or exit removed the pre-existing session"
"""

    try:
        client.command(["daemon", "start"], timeout=20)
        readiness_deadline = time.monotonic() + 15
        while True:
            try:
                client.list_sessions("sync")
                break
            except MutagenError:
                if time.monotonic() >= readiness_deadline:
                    raise
                time.sleep(0.2)
        plan = client.prepare_create_plan("sync", options)
        plan = client.consent_action_plan(plan, consent=True)
        client.execute("sync", "create", options=options, operator_consent=True, action_plan=plan)
        created_identifier = client.last_created_session[1]
        result = subprocess.run(  # noqa: S603 - runs this test's fixed GUI snapshot script
            [
                sys.executable,
                "-c",
                gui_snapshot,
                binary,
                str(tmp_path / "settings.json"),
                created_identifier,
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        if created_identifier:
            with suppress(Exception):
                sessions = client.list_sessions("sync")
                selected = next(
                    item for item in sessions if item.get("identifier") == created_identifier
                )
                client.execute(
                    "sync",
                    "terminate",
                    created_identifier,
                    operator_consent=True,
                    expected_preflight_fingerprint=client.session_preflight_fingerprint([selected]),
                )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_local_sync_against_isolated_mutagen_daemon(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    marker = alpha / "mutaui-integration.txt"
    marker.write_text("local daemon integration\n", encoding="utf-8")
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    name = "mutaui-test-" + uuid.uuid4().hex[:12]
    created_identifier = None

    try:
        client.command(["daemon", "start"], timeout=20)
        ready_deadline = time.monotonic() + 20
        while True:
            try:
                client.command(
                    ["sync", "list", "--template", "{{ json . }}"],
                    timeout=2,
                    readonly=True,
                )
                break
            except MutagenError as exc:
                if "unable to connect to daemon" not in str(exc).casefold():
                    raise
                if time.monotonic() >= ready_deadline:
                    raise
                time.sleep(0.2)
        create_options = [
            f"--name={name}",
            "--sync-mode=two-way-safe",
            str(alpha),
            str(beta),
        ]
        create_plan = client.prepare_create_plan("sync", create_options)
        create_plan = client.consent_action_plan(create_plan, consent=True)
        client.execute(
            "sync",
            "create",
            options=create_options,
            operator_consent=True,
            action_plan=create_plan,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            sessions = client.list_sessions("sync")
            created = next((item for item in sessions if item.get("name") == name), None)
            if created:
                created_identifier = created.get("identifier")
            if (beta / marker.name).exists():
                assert (beta / marker.name).read_text(
                    encoding="utf-8"
                ) == "local daemon integration\n"
                break
            time.sleep(0.25)
        else:
            pytest.fail("Mutagen did not synchronize the local marker within 30 seconds")
        assert created_identifier
        original = next(
            item
            for item in client.list_sessions("sync")
            if item.get("identifier") == created_identifier
        )
        original_configuration = extract_sync_configuration(original)
        snapshot = from_legacy_session("sync", original, measured_at=datetime.now(UTC))
        original_arguments = ("sync", "create", *create_options)
        help_text = client.command(["sync", "create", "--help"], readonly=True)
        proposals = {"watch.mode": "force-poll"}
        replacement_arguments = render_sync_replacement_arguments(
            original_arguments, proposals, help_text
        )
        replacement_configuration = json.loads(json.dumps(original_configuration))
        replacement_configuration.setdefault("watch", {})["mode"] = "force-poll"
        validation = validate_native_command_snapshot(
            snapshot,
            command_arguments=original_arguments,
            command_target_identifier=created_identifier,
        )
        preview = build_reconfiguration_preview(
            snapshot,
            replacement_configuration,
            command_arguments=original_arguments,
            command_target_identifier=created_identifier,
        )
        assert validation.snapshot_inputs_complete
        assert preview.changes
        planner = ActionPlanner(now=time.monotonic)
        plan = planner.prepare(
            ActionRequest(
                action="sync_reconfigure",
                target_ids=(created_identifier,),
                argv=replacement_arguments,
                preflight_fingerprint=preview.source_sha256,
                capabilities=("sync_reconfigure",),
            )
        )
        plan = planner.consent(
            plan.plan_id,
            consent=True,
            current_preflight_fingerprint=preview.source_sha256,
        )
        audit_events = []
        receipt = replace_non_project_session(
            ReplacementRequest(
                plan=plan,
                previous_session_identifier=created_identifier,
                source_sha256=preview.source_sha256,
                old_create_arguments=original_arguments,
                new_create_arguments=replacement_arguments,
                old_configuration={"configuration": original_configuration},
                new_configuration={"configuration": replacement_configuration},
                snapshot_validation=validation,
            ),
            MutagenReplacementBackend(client),
            consent=True,
            audit=audit_events.append,
        )
        assert receipt.verified and receipt.new_session_identifier
        assert receipt.new_session_identifier != created_identifier
        assert [event.phase for event in audit_events] == ["preflight", "terminate", "postcheck"]
        created_identifier = receipt.new_session_identifier

        current = next(
            item
            for item in client.list_sessions("sync")
            if item.get("identifier") == created_identifier
        )
        current_configuration = extract_sync_configuration(current)
        current_snapshot = from_legacy_session("sync", current, measured_at=datetime.now(UTC))
        current_validation = validate_native_command_snapshot(
            current_snapshot,
            command_arguments=replacement_arguments,
            command_target_identifier=created_identifier,
        )
        failed_arguments = (*replacement_arguments, "--mutaui-invalid-option")
        current_preview = build_reconfiguration_preview(
            current_snapshot,
            current_configuration,
            command_arguments=replacement_arguments,
            command_target_identifier=created_identifier,
        )
        restore_planner = ActionPlanner(now=time.monotonic)
        restore_plan = restore_planner.prepare(
            ActionRequest(
                action="sync_reconfigure",
                target_ids=(created_identifier,),
                argv=failed_arguments,
                preflight_fingerprint=current_preview.source_sha256,
                capabilities=("sync_reconfigure",),
            )
        )
        restore_plan = restore_planner.consent(
            restore_plan.plan_id,
            consent=True,
            current_preflight_fingerprint=current_preview.source_sha256,
        )
        restore_events = []
        restore_receipt = replace_non_project_session(
            ReplacementRequest(
                plan=restore_plan,
                previous_session_identifier=created_identifier,
                source_sha256=current_preview.source_sha256,
                old_create_arguments=replacement_arguments,
                new_create_arguments=failed_arguments,
                old_configuration={"configuration": current_configuration},
                new_configuration={"configuration": current_configuration},
                snapshot_validation=current_validation,
            ),
            MutagenReplacementBackend(client),
            consent=True,
            audit=restore_events.append,
        )
        assert not restore_receipt.verified
        assert restore_receipt.restore_attempted
        assert restore_receipt.restored_session_identifier
        assert not restore_receipt.recovery_uncertain
        assert [event.phase for event in restore_events] == [
            "preflight",
            "terminate",
            "replacement",
            "restore",
        ]
        created_identifier = restore_receipt.restored_session_identifier
    finally:
        if created_identifier:
            with suppress(Exception):
                sessions = client.list_sessions("sync")
                current = next(
                    item for item in sessions if item.get("identifier") == created_identifier
                )
                client.execute(
                    "sync",
                    "terminate",
                    created_identifier,
                    operator_consent=True,
                    expected_preflight_fingerprint=client.session_preflight_fingerprint([current]),
                )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_mutagen_ignore_order_and_negation_match_live_sync(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    for name in ("ignored.txt", "keep.txt", "other.log", "data.bin"):
        (alpha / name).write_text(name, encoding="utf-8")
    (alpha / "logs").mkdir()
    exact_ignored = alpha / "logs" / "private report.txt"
    exact_ignored.write_text("private", encoding="utf-8")
    exact_rule = path_aware_ignore_rule(alpha, exact_ignored)
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    session_name = "mutaui-ignore-" + uuid.uuid4().hex[:12]
    session_identifier = None
    try:
        client.command(["daemon", "start"], timeout=20)
        options = [
            f"--name={session_name}",
            "--no-global-configuration",
            "--mode=two-way-safe",
            "--ignore=*.txt",
            "--ignore=!keep.txt",
            f"--ignore={exact_rule}",
            str(alpha),
            str(beta),
        ]
        plan = client.prepare_create_plan("sync", options)
        plan = client.consent_action_plan(plan, consent=True)
        client.execute("sync", "create", options=options, operator_consent=True, action_plan=plan)
        deadline = time.monotonic() + 20
        expected = {"keep.txt", "other.log", "data.bin", "logs"}
        while time.monotonic() < deadline:
            sessions = client.list_sessions("sync")
            current = next((item for item in sessions if item.get("name") == session_name), None)
            if current:
                session_identifier = current.get("identifier")
            if expected.issubset({item.name for item in beta.iterdir()}):
                break
            time.sleep(0.2)
        assert session_identifier
        assert {item.name for item in beta.iterdir()} == expected
        assert not (beta / "logs" / exact_ignored.name).exists()
    finally:
        if session_identifier:
            with suppress(Exception):
                sessions = client.list_sessions("sync")
                current = next(
                    item for item in sessions if item.get("identifier") == session_identifier
                )
                client.execute(
                    "sync",
                    "terminate",
                    session_identifier,
                    operator_consent=True,
                    expected_preflight_fingerprint=client.session_preflight_fingerprint([current]),
                )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_mutagen_global_defaults_are_inherited_and_cli_values_win(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    user_home = tmp_path / "isolated-home"
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    user_home.mkdir()
    alpha.mkdir()
    beta.mkdir()
    (alpha / "kept.txt").write_text("kept", encoding="utf-8")
    (alpha / "ignored.log").write_text("ignored", encoding="utf-8")
    (user_home / ".mutagen.yml").write_text(
        "sync:\n  defaults:\n    mode: one-way-safe\n    watch:\n      mode: no-watch\n    ignore:\n      paths:\n        - '*.log'\n      vcs: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    session_name = "mutaui-global-" + uuid.uuid4().hex[:12]
    session_identifier = None
    try:
        client.command(["daemon", "start"], timeout=20)
        daemon_deadline = time.monotonic() + 15
        while True:
            try:
                client.command(
                    ["sync", "list", "--template", "{{ json . }}"],
                    timeout=2,
                    readonly=True,
                )
                break
            except MutagenError as exc:
                if time.monotonic() >= daemon_deadline:
                    raise AssertionError(
                        "Isolated Mutagen daemon did not become ready in 15 seconds."
                    ) from exc
                time.sleep(0.2)
        options = [
            f"--name={session_name}",
            "--mode=two-way-safe",
            "--watch-mode=force-poll",
            "--watch-polling-interval=15",
            "--ignore=*.tmp",
            "--no-ignore-vcs",
            str(alpha),
            str(beta),
        ]
        plan = client.prepare_create_plan("sync", options)
        plan = client.consent_action_plan(plan, consent=True)
        client.execute("sync", "create", options=options, operator_consent=True, action_plan=plan)

        deadline = time.monotonic() + 15
        session = None
        while time.monotonic() < deadline:
            sessions = client.list_sessions("sync")
            session = next((item for item in sessions if item.get("name") == session_name), None)
            if session:
                session_identifier = session.get("identifier")
                break
            time.sleep(0.2)
        assert session is not None
        configuration = extract_sync_configuration(session)
        assert configuration["mode"] == "two-way-safe"
        assert configuration["watch"]["mode"] == "force-poll"
        assert configuration["watch"]["pollingInterval"] == 15
        assert configuration["ignore"]["paths"] == ["*.log", "*.tmp"]
        assert configuration["ignore"]["vcs"] is False
        assert (beta / "kept.txt").is_file()
        assert not (beta / "ignored.log").exists()
    finally:
        if session_identifier:
            with suppress(Exception):
                current = next(
                    item
                    for item in client.list_sessions("sync")
                    if item.get("identifier") == session_identifier
                )
                client.execute(
                    "sync",
                    "terminate",
                    session_identifier,
                    operator_consent=True,
                    expected_preflight_fingerprint=client.session_preflight_fingerprint([current]),
                )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_mutagen_forward_inherits_global_socket_defaults(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    user_home = tmp_path / "isolated-home"
    user_home.mkdir()
    (user_home / ".mutagen.yml").write_text(
        "forward:\n  defaults:\n    socket:\n      overwriteMode: overwrite\n      owner: operator\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        source_port = probe.getsockname()[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        destination_port = probe.getsockname()[1]
    client = MutagenClient(binary)
    session_name = "mutaui-forward-global-" + uuid.uuid4().hex[:12]
    session_identifier = None
    try:
        client.command(["daemon", "start"], timeout=20)
        options = [
            f"--name={session_name}",
            f"tcp:localhost:{source_port}",
            f"tcp:localhost:{destination_port}",
        ]
        plan = client.prepare_create_plan("forward", options)
        plan = client.consent_action_plan(plan, consent=True)
        client.execute(
            "forward", "create", options=options, operator_consent=True, action_plan=plan
        )

        deadline = time.monotonic() + 15
        session = None
        while time.monotonic() < deadline:
            sessions = client.list_sessions("forward")
            session = next((item for item in sessions if item.get("name") == session_name), None)
            if session:
                session_identifier = session.get("identifier")
                break
            time.sleep(0.2)
        assert session is not None
        assert session["socket"]["overwriteMode"] == "overwrite"
        assert session["socket"]["owner"] == "operator"
        rows = {row.key: row for row in forward_configuration_rows(session)}
        assert rows["source.socket.overwriteMode"].current_value == "overwrite"
        assert rows["destination.socket.owner"].current_value == "operator"
    finally:
        if session_identifier:
            with suppress(Exception):
                current = next(
                    item
                    for item in client.list_sessions("forward")
                    if item.get("identifier") == session_identifier
                )
                client.execute(
                    "forward",
                    "terminate",
                    session_identifier,
                    operator_consent=True,
                    expected_preflight_fingerprint=client.session_preflight_fingerprint([current]),
                )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_mutagen_forward_reports_source_port_conflict(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    user_home = tmp_path / "isolated-home"
    user_home.mkdir()
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setenv("USERPROFILE", str(user_home))
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    session_name = "mutaui-forward-port-conflict-" + uuid.uuid4().hex[:12]
    session_identifier = None

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        source_port = occupied.getsockname()[1]
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            destination_port = probe.getsockname()[1]

        client.command(["daemon", "start"], timeout=20)
        try:
            options = [
                f"--name={session_name}",
                f"tcp:localhost:{source_port}",
                f"tcp:localhost:{destination_port}",
            ]
            plan = client.prepare_create_plan("forward", options)
            plan = client.consent_action_plan(plan, consent=True)
            client.execute(
                "forward", "create", options=options, operator_consent=True, action_plan=plan
            )

            deadline = time.monotonic() + 15
            session = None
            while time.monotonic() < deadline:
                session = next(
                    (
                        item
                        for item in client.list_sessions("forward")
                        if item.get("name") == session_name
                    ),
                    None,
                )
                if session and session.get("lastError"):
                    break
                time.sleep(0.2)

            assert session is not None
            session_identifier = session.get("identifier")
            error = session.get("lastError", "")
            assert "listen" in error.lower()
            assert str(source_port) in error
        finally:
            if session_identifier:
                with suppress(Exception):
                    current = next(
                        item
                        for item in client.list_sessions("forward")
                        if item.get("identifier") == session_identifier
                    )
                    client.execute(
                        "forward",
                        "terminate",
                        session_identifier,
                        operator_consent=True,
                        expected_preflight_fingerprint=client.session_preflight_fingerprint(
                            [current]
                        ),
                    )
            with suppress(Exception):
                client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_local_unix_forward_leave_preserves_entry_and_overwrite_is_explicit(tmp_path, monkeypatch):
    import sys

    if os.name == "nt" and sys.getwindowsversion().build < 17063:
        pytest.skip("Windows Unix sockets require build 17063 or newer")
    binary = _mutagen_binary()
    assert binary
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("USERPROFILE", str(isolated_home))
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(tmp_path / "daemon-data"))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    leave_name = "mutaui-unix-leave-" + uuid.uuid4().hex[:10]
    overwrite_name = "mutaui-unix-overwrite-" + uuid.uuid4().hex[:10]
    socket_path = tmp_path / "source.sock"
    socket_path.write_text("preserve until overwrite is selected", encoding="utf-8")

    def create_forward(name, mode):
        options = [
            f"--name={name}",
            f"--socket-overwrite-mode-source={mode}",
            "--socket-permission-mode-source=0600",
            f"unix:{socket_path}",
            "tcp:localhost:1",
        ]
        plan = client.prepare_create_plan("forward", options)
        consented = client.consent_action_plan(
            plan,
            consent=True,
            typed_confirmation=plan.typed_confirmation,
        )
        client.execute(
            "forward",
            "create",
            options=options,
            operator_consent=True,
            action_plan=consented,
        )

    try:
        client.command(["daemon", "start"], timeout=20)
        with suppress(MutagenError):
            create_forward(leave_name, "leave")
        assert socket_path.is_file()
        assert socket_path.read_text(encoding="utf-8") == "preserve until overwrite is selected"

        create_forward(overwrite_name, "overwrite")

        overwrite_session = next(
            item for item in client.list_sessions("forward") if item.get("name") == overwrite_name
        )
        if hasattr(socket, "AF_UNIX"):

            def socket_accepts_connection():
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                        probe.settimeout(1)
                        probe.connect(str(socket_path))
                    return True
                except OSError:
                    return False

            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not socket_accepts_connection():
                time.sleep(0.2)
            assert socket_accepts_connection(), overwrite_session
        else:
            try:
                preserved_contents = socket_path.read_text(encoding="utf-8")
            except OSError:
                preserved_contents = None
            assert preserved_contents != "preserve until overwrite is selected"
        assert overwrite_session["status"] == "forwarding"
        assert overwrite_session["source"]["connected"] is True
        assert overwrite_session["source"]["socket"]["overwriteMode"] == "overwrite"
        assert overwrite_session["source"]["socket"]["permissionMode"] == "0600"
    finally:
        for name in (leave_name, overwrite_name):
            with suppress(Exception):
                current = next(
                    item for item in client.list_sessions("forward") if item.get("name") == name
                )
                client.execute(
                    "forward",
                    "terminate",
                    current["identifier"],
                    operator_consent=True,
                    expected_preflight_fingerprint=client.session_preflight_fingerprint([current]),
                )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_native_project_start_and_terminate_against_isolated_mutagen(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    (alpha / "project-check.txt").write_text("project integration\n", encoding="utf-8")
    project_file = tmp_path / "mutagen.yml"
    project_file.write_text(
        "sync:\n  integration:\n    alpha: ./alpha\n    beta: ./beta\n",
        encoding="utf-8",
    )
    audit_path = tmp_path / "project-audit.jsonl"
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    executor = LegacyMutagenExecutor(client)
    planner = ActionPlanner(now=time.monotonic)

    def run_project_action(action):
        project_plan = plan_project_action(load_native_project(project_file), action)
        action_plan = prepare_action_plan(project_plan, planner)
        action_plan = planner.consent(
            action_plan.plan_id,
            consent=True,
            current_preflight_fingerprint=project_plan.project_sha256,
            typed_confirmation=action_plan.typed_confirmation,
        )
        return execute_project_action(
            project_plan,
            executor,
            consent=True,
            audit_path=audit_path,
            action_planner=planner,
            action_plan=action_plan,
        )

    try:
        client.command(["daemon", "start"], timeout=20)
        start_receipt = run_project_action("start")
        assert start_receipt.verified, start_receipt.postcheck_error
        deadline = time.monotonic() + 20
        while not (beta / "project-check.txt").is_file() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert (beta / "project-check.txt").read_text(encoding="utf-8") == "project integration\n"

        terminate_receipt = run_project_action("terminate")
        assert terminate_receipt.verified, terminate_receipt.postcheck_error
        assert '"phase":"completed"' in audit_path.read_text(encoding="utf-8")
    finally:
        with suppress(Exception):
            client.command(
                ["project", "terminate", "--project-file", str(project_file)], timeout=30
            )
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)
