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
    from PySide6.QtWidgets import QApplication

    ssh_config = tmp_path / "config"
    ssh_config.write_text("Host devbox\n  User deploy\n", encoding="utf-8")
    qapp = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        app_module,
        "resolve_ssh_options",
        lambda _alias: pytest.fail("opening the manager must not run ssh -G"),
    )
    monkeypatch.setattr(
        app_module,
        "test_ssh_connection",
        lambda _alias: pytest.fail("opening the manager must not connect"),
    )

    dialog = app_module.SSHProfileManagerDialog(config_path=ssh_config)

    assert dialog.alias_input.count() == 1
    assert dialog.alias_input.currentText() == "devbox"
    assert "Read-only" in dialog.config_status.text()
    dialog.close()
    qapp.processEvents()
