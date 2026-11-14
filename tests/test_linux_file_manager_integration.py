import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from mutaui.services.command_line import parse_launch_command

MODULE_NAME = "mutaui.services.linux_file_manager_integration"


@pytest.fixture
def integration_module():
    if importlib.util.find_spec(MODULE_NAME) is None:
        pytest.skip("Linux file-manager integration module is not implemented yet")
    return importlib.import_module(MODULE_NAME)


def test_linux_file_manager_integration_module_exists():
    assert importlib.util.find_spec(MODULE_NAME) is not None, (
        "Linux file-manager integration module is missing"
    )


@pytest.mark.parametrize(
    ("arguments", "action"),
    [
        (["--install-linux-file-manager-integration"], "install"),
        (["--remove-linux-file-manager-integration"], "remove"),
    ],
)
def test_linux_file_manager_integration_requires_explicit_cli_action(arguments, action):
    launch = parse_launch_command(arguments)

    assert launch.linux_file_manager_action == action


def test_install_is_opt_in_idempotent_and_adds_both_user_level_hooks(integration_module, tmp_path):
    executable = tmp_path / "Muta UI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"

    assert (
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )
        == "installed"
    )
    assert (
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )
        == "already_installed"
    )

    nautilus = data_home / "nautilus" / "scripts" / "MutaUI" / "Open folder in MutaUI"
    dolphin = data_home / "kio" / "servicemenus" / "mutaui-open-folder.desktop"
    assert nautilus.is_file()
    assert "NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" in nautilus.read_text(encoding="utf-8")
    assert "--open-folder" in nautilus.read_text(encoding="utf-8")
    assert dolphin.is_file()
    assert "MimeType=inode/directory;" in dolphin.read_text(encoding="utf-8")
    assert "--open-folder %f" in dolphin.read_text(encoding="utf-8")


def test_uninstall_removes_only_unchanged_owned_hooks(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        executable, data_home=data_home, platform_name="linux"
    )

    assert (
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )
        == "removed"
    )
    assert not (data_home / "nautilus" / "scripts" / "MutaUI" / "Open folder in MutaUI").exists()
    assert not (data_home / "kio" / "servicemenus" / "mutaui-open-folder.desktop").exists()
    assert not (data_home / "mutaui" / "integrations" / "linux-file-manager.json").exists()


def test_install_refuses_existing_unowned_hook_without_partial_writes(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    existing = data_home / "nautilus" / "scripts" / "MutaUI" / "Open folder in MutaUI"
    existing.parent.mkdir(parents=True)
    existing.write_text("user-owned content", encoding="utf-8")

    with pytest.raises(integration_module.IntegrationError, match="conflict"):
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )

    assert existing.read_text(encoding="utf-8") == "user-owned content"
    assert not (data_home / "kio" / "servicemenus" / "mutaui-open-folder.desktop").exists()


def test_install_refuses_relocation_until_old_hooks_are_removed(integration_module, tmp_path):
    first = tmp_path / "first" / "MutaUI.AppImage"
    second = tmp_path / "second" / "MutaUI.AppImage"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first app")
    second.write_bytes(b"second app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        first, data_home=data_home, platform_name="linux"
    )
    nautilus = data_home / "nautilus/scripts/MutaUI/Open folder in MutaUI"
    original = nautilus.read_bytes()

    with pytest.raises(integration_module.IntegrationError, match="different executable"):
        integration_module.install_linux_file_manager_integration(
            second, data_home=data_home, platform_name="linux"
        )

    assert nautilus.read_bytes() == original
    assert (
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )
        == "removed"
    )


def test_uninstall_refuses_modified_hook_and_preserves_all_files(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        executable, data_home=data_home, platform_name="linux"
    )
    nautilus = data_home / "nautilus" / "scripts" / "MutaUI" / "Open folder in MutaUI"
    nautilus.write_text("user edit", encoding="utf-8")

    with pytest.raises(integration_module.IntegrationError, match="modified"):
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )

    assert nautilus.read_text(encoding="utf-8") == "user edit"
    assert (data_home / "kio" / "servicemenus" / "mutaui-open-folder.desktop").is_file()


def test_linux_hooks_reject_non_linux_installation(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"

    with pytest.raises(integration_module.IntegrationError, match="Linux only"):
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="win32"
        )

    assert not data_home.exists()


def test_dolphin_exec_argument_escapes_desktop_entry_syntax(integration_module):
    encoded = integration_module._desktop_exec_arg('/tmp/Muta UI $`"%\\app')

    assert encoded == '"/tmp/Muta UI \\$\\`\\"%%\\\\app"'


def test_install_rejects_symlinked_hook_path(integration_module, monkeypatch, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    data_home.mkdir()
    symlink_component = data_home / "nautilus"
    original_is_symlink = Path.is_symlink

    def is_symlink(path):
        if path == symlink_component:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(integration_module.Path, "is_symlink", is_symlink)

    with pytest.raises(integration_module.IntegrationError, match="symlink"):
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )


def test_install_rejects_relative_data_home(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    with pytest.raises(integration_module.IntegrationError, match="absolute path"):
        integration_module.install_linux_file_manager_integration(
            executable, data_home="relative/data", platform_name="linux"
        )


def test_install_uses_xdg_data_home_when_no_directory_is_passed(
    integration_module, monkeypatch, tmp_path
):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))

    assert (
        integration_module.install_linux_file_manager_integration(executable, platform_name="linux")
        == "installed"
    )
    assert (data_home / "nautilus/scripts/MutaUI/Open folder in MutaUI").is_file()


def test_install_uses_default_user_data_home_when_xdg_is_unset(
    integration_module, monkeypatch, tmp_path
):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(integration_module.Path, "home", lambda: tmp_path)

    assert (
        integration_module.install_linux_file_manager_integration(executable, platform_name="linux")
        == "installed"
    )
    assert (tmp_path / ".local/share/nautilus/scripts/MutaUI/Open folder in MutaUI").is_file()


@pytest.mark.parametrize("unsafe_root_kind", ["file", "child_file"])
def test_install_rejects_non_directory_path_components(
    integration_module, tmp_path, unsafe_root_kind
):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    if unsafe_root_kind == "file":
        data_home.write_text("not a directory", encoding="utf-8")
    else:
        data_home.mkdir()
        (data_home / "nautilus").write_text("not a directory", encoding="utf-8")

    with pytest.raises(
        integration_module.IntegrationError, match="not a safe directory|not a directory"
    ):
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )


def test_install_rejects_invalid_packaged_executable(integration_module, tmp_path):
    with pytest.raises(integration_module.IntegrationError, match="existing absolute"):
        integration_module.install_linux_file_manager_integration(
            "relative/app", data_home=tmp_path / "xdg-data", platform_name="linux"
        )
    with pytest.raises(integration_module.IntegrationError, match="existing absolute"):
        integration_module.install_linux_file_manager_integration(
            tmp_path / "missing-app", data_home=tmp_path / "xdg-data", platform_name="linux"
        )


@pytest.mark.parametrize(
    "unsafe_ancestor", ["missing-root-parent", "existing-root", "nested-parent"]
)
def test_make_parents_rejects_unsafe_existing_ancestors(
    integration_module, tmp_path, unsafe_ancestor
):
    if unsafe_ancestor == "missing-root-parent":
        blocked_parent = tmp_path / "blocked"
        blocked_parent.write_text("file", encoding="utf-8")
        root = blocked_parent / "data"
        destination = root / "nautilus/hook"
    elif unsafe_ancestor == "existing-root":
        root = tmp_path / "data"
        root.write_text("file", encoding="utf-8")
        destination = root / "nautilus/hook"
    else:
        root = tmp_path / "data"
        root.mkdir()
        (root / "nautilus").write_text("file", encoding="utf-8")
        destination = root / "nautilus/hook"

    with pytest.raises(
        integration_module.IntegrationError, match="not a safe directory|not a directory"
    ):
        integration_module._make_parents(root, destination, [])


def test_uninstall_rejects_non_string_ownership_hash(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        executable, data_home=data_home, platform_name="linux"
    )
    manifest_path = data_home / "mutaui/integrations/linux-file-manager.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["nautilus/scripts/MutaUI/Open folder in MutaUI"] = 42
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(integration_module.IntegrationError, match="invalid hashes"):
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )


def test_uninstall_rejects_manifest_path_that_is_a_directory(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        executable, data_home=data_home, platform_name="linux"
    )
    manifest_path = data_home / "mutaui/integrations/linux-file-manager.json"
    manifest_path.unlink()
    manifest_path.mkdir()

    with pytest.raises(integration_module.IntegrationError, match="missing or unsafe"):
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )


def test_uninstall_rejects_missing_managed_hook(integration_module, tmp_path):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        executable, data_home=data_home, platform_name="linux"
    )
    (data_home / "kio/servicemenus/mutaui-open-folder.desktop").unlink()

    with pytest.raises(integration_module.IntegrationError, match="modified or removed"):
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )


@pytest.mark.parametrize("failed_write", [1, 2])
def test_install_rolls_back_partial_files_and_directories(
    integration_module, monkeypatch, tmp_path, failed_write
):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "nested" / "xdg-data"
    original_write = integration_module._write_exclusive
    writes = 0

    def fail_selected_write(path, contents, mode):
        nonlocal writes
        writes += 1
        if writes == failed_write:
            raise OSError("simulated write failure")
        original_write(path, contents, mode)

    monkeypatch.setattr(integration_module, "_write_exclusive", fail_selected_write)
    with pytest.raises(integration_module.IntegrationError, match="simulated write failure"):
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )

    assert not data_home.exists()
    assert not data_home.parent.exists()


def test_install_rolls_back_and_reraises_unsafe_path_failure(
    integration_module, monkeypatch, tmp_path
):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "nested" / "xdg-data"
    original_make_parents = integration_module._make_parents
    calls = 0

    def fail_second_parent_creation(root, destination, created_dirs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise integration_module.IntegrationError("simulated unsafe path")
        original_make_parents(root, destination, created_dirs)

    monkeypatch.setattr(integration_module, "_make_parents", fail_second_parent_creation)
    with pytest.raises(integration_module.IntegrationError, match="simulated unsafe path"):
        integration_module.install_linux_file_manager_integration(
            executable, data_home=data_home, platform_name="linux"
        )

    assert not data_home.exists()
    assert not data_home.parent.exists()


@pytest.mark.parametrize(
    "manifest_text",
    [
        "not-json",
        '{"version": 999, "files": {}, "executable": "/tmp/app"}',
        '{"version": 2, "files": [], "executable": "/tmp/app"}',
        '{"version": 2, "files": {}, "executable": "/tmp/app"}',
        '{"version": 2, "files": {"nautilus/scripts/MutaUI/Open folder in MutaUI": "x", "kio/servicemenus/mutaui-open-folder.desktop": "y"}, "executable": "relative"}',
    ],
)
def test_uninstall_rejects_invalid_ownership_manifest(integration_module, tmp_path, manifest_text):
    executable = tmp_path / "MutaUI.AppImage"
    executable.write_bytes(b"app")
    data_home = tmp_path / "xdg-data"
    integration_module.install_linux_file_manager_integration(
        executable, data_home=data_home, platform_name="linux"
    )
    manifest = data_home / "mutaui/integrations/linux-file-manager.json"
    manifest.write_text(manifest_text, encoding="utf-8")

    with pytest.raises(integration_module.IntegrationError, match="manifest"):
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )


def test_remove_reports_not_installed_and_rejects_unowned_orphan(integration_module, tmp_path):
    data_home = tmp_path / "xdg-data"
    assert (
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )
        == "not_installed"
    )

    orphan = data_home / "kio/servicemenus/mutaui-open-folder.desktop"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("user-owned", encoding="utf-8")
    with pytest.raises(integration_module.IntegrationError, match="without an ownership"):
        integration_module.remove_linux_file_manager_integration(
            data_home=data_home, platform_name="linux"
        )


def test_exclusive_write_removes_new_path_when_stream_open_fails(
    integration_module, monkeypatch, tmp_path
):
    destination = tmp_path / "managed-hook"
    monkeypatch.setattr(integration_module.os, "open", lambda *_args: 42)

    def fail_fdopen(*_args):
        raise OSError("simulated stream failure")

    monkeypatch.setattr(integration_module.os, "fdopen", fail_fdopen)
    with pytest.raises(OSError, match="simulated stream failure"):
        integration_module._write_exclusive(destination, b"content", 0o600)

    assert not destination.exists()
