import subprocess
from pathlib import Path

import pytest

from ssh_profiles import (
    parse_ssh_config,
    parse_ssh_options,
    resolve_ssh_options,
    test_ssh_connection,
)


def test_read_only_config_reader_handles_aliases_includes_and_wildcards(tmp_path):
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    included = ssh_dir / "work.conf"
    included.write_text("Host build staging\n  User deploy\n", encoding="utf-8")
    config = ssh_dir / "config"
    original = "Include work.conf\nHost *.example.com\n  User wildcard\nHost devbox\n  HostName dev.example.net\n"
    config.write_text(original, encoding="utf-8")

    result = parse_ssh_config(config)

    assert result.valid
    assert [profile.alias for profile in result.profiles] == ["build", "staging", "devbox"]
    assert result.profiles[0].directives["user"] == ("deploy",)
    assert any("wildcard" in warning.lower() for warning in result.warnings)
    assert config.read_text(encoding="utf-8") == original


def test_config_reader_rejects_invalid_utf8_and_never_rewrites_it(tmp_path):
    config = tmp_path / "config"
    config.write_bytes(b"Host devbox\nUser \xff")

    result = parse_ssh_config(config)

    assert not result.valid
    assert config.read_bytes() == b"Host devbox\nUser \xff"


def test_config_reader_stops_processing_includes_at_file_limit(tmp_path, monkeypatch):
    includes = tmp_path / "includes"
    includes.mkdir()
    for index in range(70):
        (includes / f"{index:02}.conf").write_text(
            f"Host alias-{index}\n  User deploy\n", encoding="utf-8"
        )
    config = tmp_path / "config"
    config.write_text("Include includes/*.conf\n", encoding="utf-8")

    resolve_calls = []
    original_resolve = Path.resolve

    def counted_resolve(path, *args, **kwargs):
        resolve_calls.append(path)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", counted_resolve)

    result = parse_ssh_config(config)

    assert len(resolve_calls) <= 64
    assert sum("include file limit reached" in warning for warning in result.warnings) == 1


def test_config_reader_reports_malformed_directives_unresolved_includes_and_size_limit(tmp_path):
    config = tmp_path / "config"
    config.write_text(
        "# leading comment\n\nInclude\nInclude absent.conf\n"
        "Host good bad/alias *.example\n"
        "  User deploy\n"
        "  UnknownOption value\n"
        '  User "unterminated\n'
        "Host\n"
        "Match exec true\n",
        encoding="utf-8",
    )

    result = parse_ssh_config(config)

    assert result.valid
    assert [profile.alias for profile in result.profiles] == ["good"]
    assert result.profiles[0].directives["user"] == ("deploy",)
    assert result.profiles[0].unsupported == ("unknownoption",)
    assert result.sha256
    assert any("unresolved" in warning.lower() for warning in result.warnings)
    assert any("malformed" in warning.lower() for warning in result.warnings)
    assert any("no value" in warning.lower() for warning in result.warnings)
    assert any("match blocks" in warning.lower() for warning in result.warnings)

    oversized = parse_ssh_config(config, max_bytes=1)
    assert not oversized.valid and any("exceeds" in warning for warning in oversized.warnings)


def test_config_reader_missing_and_recursive_include_are_safe(tmp_path):
    missing = parse_ssh_config(tmp_path / "missing")
    assert missing.valid and missing.sha256 is None and missing.warnings

    config = tmp_path / "config"
    config.write_text("Include config\nHost safe\n", encoding="utf-8")
    recursive = parse_ssh_config(config)
    assert recursive.valid and any(
        "repeated or recursive" in warning.lower() for warning in recursive.warnings
    )


def test_config_reader_stops_at_include_depth_limit(tmp_path):
    for index in range(10):
        (tmp_path / f"config-{index}").write_text(
            f"Include config-{index + 1}\n" if index < 9 else "Host deepest\n",
            encoding="utf-8",
        )

    result = parse_ssh_config(tmp_path / "config-0")

    assert result.valid
    assert any("depth limit" in warning.lower() for warning in result.warnings)


def test_ssh_option_resolution_rejects_invalid_alias_and_missing_binary(monkeypatch):
    assert not resolve_ssh_options("-oProxyCommand=bad").success
    monkeypatch.setattr("ssh_profiles._find_ssh", lambda _executable=None: None)
    assert "not found" in resolve_ssh_options("safe").message
    assert "not found" in test_ssh_connection("safe").message


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (subprocess.TimeoutExpired("ssh", 1), "timed out"),
        (OSError("denied"), "Could not run"),
    ],
)
def test_ssh_option_resolution_reports_execution_failures(monkeypatch, failure, expected):
    def fail(_argv, *, timeout):
        raise failure

    monkeypatch.setattr("ssh_profiles._run_ssh", fail)
    result = resolve_ssh_options("safe", executable="ssh")
    assert not result.success and expected in result.message


def test_ssh_option_resolution_reports_return_code_and_success(monkeypatch):
    monkeypatch.setattr(
        "ssh_profiles._run_ssh",
        lambda _argv, *, timeout: subprocess.CompletedProcess(
            ["ssh"], 1, "hostname ignored", "bad alias"
        ),
    )
    failed = resolve_ssh_options("safe", executable="ssh")
    assert not failed.success and failed.stderr == "bad alias"

    monkeypatch.setattr(
        "ssh_profiles._run_ssh",
        lambda _argv, *, timeout: subprocess.CompletedProcess(
            ["ssh"], 0, "hostname example.test\nidentityfile key", ""
        ),
    )
    succeeded = resolve_ssh_options("safe", executable="ssh")
    assert succeeded.success and succeeded.options["hostname"] == ("example.test",)


@pytest.mark.parametrize(
    ("result", "success", "host_key_error"),
    [
        (subprocess.CompletedProcess(["ssh"], 0, "connected", ""), True, False),
        (
            subprocess.CompletedProcess(["ssh"], 255, "", "Host key verification failed"),
            False,
            True,
        ),
        (subprocess.CompletedProcess(["ssh"], 255, "", "network unreachable"), False, False),
    ],
)
def test_ssh_connection_reports_success_and_host_key_failures(
    monkeypatch, result, success, host_key_error
):
    monkeypatch.setattr("ssh_profiles._find_ssh", lambda _executable=None: "ssh")
    monkeypatch.setattr("ssh_profiles._run_ssh", lambda _argv, *, timeout: result)

    checked = test_ssh_connection("safe")

    assert checked.success is success
    assert checked.host_key_error is host_key_error


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (subprocess.TimeoutExpired("ssh", 1), "timed out"),
        (OSError("denied"), "Could not run"),
    ],
)
def test_ssh_connection_reports_execution_failures(monkeypatch, failure, expected):
    monkeypatch.setattr("ssh_profiles._find_ssh", lambda _executable=None: "ssh")

    def fail(_argv, *, timeout):
        raise failure

    monkeypatch.setattr("ssh_profiles._run_ssh", fail)
    result = test_ssh_connection("safe")
    assert not result.success and expected in result.message


def test_ssh_g_output_preserves_effective_values_and_multiple_identity_files():
    result = parse_ssh_options(
        "hostname server.example\nuser deploy\nport 2222\n"
        "identityfile ~/.ssh/id_ed25519\nidentityfile ~/.ssh/work_key\n"
        "stricthostkeychecking yes\nuserknownhostsfile ~/.ssh/known_hosts\n"
    )

    assert result["hostname"] == "server.example"
    assert result["identityfile"] == ("~/.ssh/id_ed25519", "~/.ssh/work_key")
    assert result["stricthostkeychecking"] == ("yes",)


def test_ssh_g_uses_shell_false_and_rejects_option_injection(monkeypatch):
    calls = []

    class Completed:
        returncode = 0
        stdout = "hostname host.example\nuser adam\n"
        stderr = ""

    monkeypatch.setattr("ssh_profiles.shutil.which", lambda _name: "C:/OpenSSH/ssh.exe")
    monkeypatch.setattr(
        "ssh_profiles.subprocess.run",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or Completed(),
    )

    result = resolve_ssh_options("devbox")

    assert result.success
    assert result.options["hostname"] == ("host.example",)
    assert calls[0][0] == ["C:/OpenSSH/ssh.exe", "-G", "devbox"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] <= 10
    assert not resolve_ssh_options("--config=evil").success


def test_connection_test_keeps_strict_host_key_and_batch_mode(monkeypatch):
    calls = []

    class Completed:
        returncode = 255
        stdout = ""
        stderr = "Host key verification failed."

    monkeypatch.setattr("ssh_profiles.shutil.which", lambda _name: "ssh")
    monkeypatch.setattr(
        "ssh_profiles.subprocess.run",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or Completed(),
    )

    result = test_ssh_connection("devbox")

    assert not result.success
    assert result.host_key_error
    assert "StrictHostKeyChecking=yes" in calls[0][0]
    assert "BatchMode=yes" in calls[0][0]
    assert not any("StrictHostKeyChecking=no" in arg for arg in calls[0][0])
    assert calls[0][1]["shell"] is False


@pytest.mark.parametrize(
    "stderr",
    [
        "No ED25519 host key is known for devbox and you have requested strict checking.",
        "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!\nOffending ED25519 key in known_hosts:7",
    ],
)
def test_connection_test_identifies_unknown_and_changed_host_keys(monkeypatch, stderr):
    class Completed:
        returncode = 255
        stdout = ""

    Completed.stderr = stderr
    monkeypatch.setattr("ssh_profiles.shutil.which", lambda _name: "ssh")
    monkeypatch.setattr("ssh_profiles.subprocess.run", lambda *_args, **_kwargs: Completed())

    result = test_ssh_connection("devbox")

    assert not result.success
    assert result.host_key_error


def test_connection_test_accepts_only_successful_strict_host_key_check(monkeypatch):
    calls = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("ssh_profiles.shutil.which", lambda _name: "ssh")
    monkeypatch.setattr(
        "ssh_profiles.subprocess.run",
        lambda argv, **kwargs: calls.append((argv, kwargs)) or Completed(),
    )

    result = test_ssh_connection("devbox")

    assert result.success
    assert "StrictHostKeyChecking=yes" in calls[0][0]
    assert not any("StrictHostKeyChecking=no" in arg for arg in calls[0][0])


def test_ssh_manager_lists_aliases_without_running_ssh(tmp_path, monkeypatch):
    import os

    import pytest

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    app_module = pytest.importorskip("app")
    ssh_dialog_module = pytest.importorskip("mutaui.ui.ssh_profile_dialog")
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    ssh_config = tmp_path / "config"
    ssh_config.write_text("Host devbox\n  User deploy\n", encoding="utf-8")
    _qapp = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        ssh_dialog_module,
        "resolve_ssh_options",
        lambda _alias: pytest.fail("opening the manager must not run ssh -G"),
    )
    monkeypatch.setattr(
        ssh_dialog_module,
        "test_ssh_connection",
        lambda _alias: pytest.fail("opening the manager must not connect"),
    )

    dialog = app_module.SSHProfileManagerDialog(config_path=ssh_config)

    assert dialog.alias_input.count() == 1
    assert dialog.alias_input.currentText() == "devbox"
    assert "Read-only" in dialog.config_status.text()
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)
