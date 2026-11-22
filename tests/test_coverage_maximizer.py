"""High-precision tests targeting remaining branch and statement gaps across MutaUI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import app as app_module
from connection_profiles import (
    ConnectionProfile,
    ConnectionProfileStore,
    ProfileStoreError,
)
from ignore_presets import (
    IgnorePresetError,
    IgnorePresetStore,
    _parse_preset,
    _supported_syntax,
    validate_ignore_pattern,
)
from mutaui.ui.global_config_editor import (
    browse_global_config,
    load_global_config,
    preview_global_config,
)
from mutaui.ui.settings_migration import (
    migrate_local_settings,
    rollback_local_settings_migration,
)
from portable_bundle import _sanitize_records


def _get_app() -> QApplication:
    return QApplication.instance() or QApplication([])


# -----------------------------------------------------------------------------
# 1. settings_migration.py coverage
# -----------------------------------------------------------------------------
def test_settings_migration_error_and_cancellation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _get_app()
    dummy_window = SimpleNamespace()
    warned: list[str] = []
    informed: list[str] = []

    monkeypatch.setattr(
        "mutaui.ui.settings_migration.QMessageBox.warning",
        lambda *args: warned.append(str(args[-1])),
    )
    monkeypatch.setattr(
        "mutaui.ui.settings_migration.QMessageBox.information",
        lambda *args: informed.append(str(args[-1])),
    )

    # 1.1 migrate_local_settings OSError branch
    def fail_migrate(_path: Any) -> Any:
        raise OSError("Disk write failed")

    monkeypatch.setattr("mutaui.ui.settings_migration.migrate_settings_file", fail_migrate)
    migrate_local_settings(dummy_window, tmp_path / "settings.json")
    assert any("Disk write failed" in w for w in warned)

    # 1.2 migrate_local_settings without backup_path
    monkeypatch.setattr(
        "mutaui.ui.settings_migration.migrate_settings_file",
        lambda _p: SimpleNamespace(message="Migrated successfully", backup_path=None),
    )
    migrate_local_settings(dummy_window, tmp_path / "settings.json")
    assert any("Migrated successfully" in i for i in informed)

    # 1.3 rollback cancelled at file picker
    monkeypatch.setattr(
        "mutaui.ui.settings_migration.QFileDialog.getOpenFileName",
        lambda *a, **k: ("", ""),
    )
    rollback_local_settings_migration(dummy_window, tmp_path / "settings.json")

    # 1.4 rollback cancelled at question prompt
    monkeypatch.setattr(
        "mutaui.ui.settings_migration.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(tmp_path / "backup.bak"), "Backups"),
    )
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        "mutaui.ui.settings_migration.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Cancel,
    )
    rollback_local_settings_migration(dummy_window, tmp_path / "settings.json")

    # 1.5 rollback raising OSError
    monkeypatch.setattr(
        "mutaui.ui.settings_migration.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )

    def fail_rollback(_p: Any, _b: Any) -> Any:
        raise OSError("Permission denied restoring backup")

    monkeypatch.setattr("mutaui.ui.settings_migration.rollback_settings_migration", fail_rollback)
    rollback_local_settings_migration(dummy_window, tmp_path / "settings.json")
    assert any("Permission denied restoring backup" in w for w in warned)


# -----------------------------------------------------------------------------
# 2. global_config_editor.py coverage
# -----------------------------------------------------------------------------
def test_global_config_editor_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _get_app()
    warned: list[str] = []
    informed: list[str] = []

    monkeypatch.setattr(
        "mutaui.ui.global_config_editor.QMessageBox.information",
        lambda *a: informed.append(str(a[-1])),
    )
    monkeypatch.setattr(
        "mutaui.ui.global_config_editor.QMessageBox.warning",
        lambda *a: warned.append(str(a[-1])),
    )

    class FakeInput:
        def __init__(self, val: str = "") -> None:
            self._text = val

        def text(self) -> str:
            return self._text

        def setText(self, val: str) -> None:
            self._text = val

    class FakeEditor:
        def __init__(self) -> None:
            self._text = ""
            self._read_only = False

        def setPlainText(self, val: str) -> None:
            self._text = val

        def toPlainText(self) -> str:
            return self._text

        def setReadOnly(self, val: bool) -> None:
            self._read_only = val

    class FakeButton:
        def __init__(self) -> None:
            self._enabled = True

        def setEnabled(self, val: bool) -> None:
            self._enabled = val

    window = SimpleNamespace(
        global_config_path_input=FakeInput(""),
        global_config_editor=FakeEditor(),
        global_yaml_recovery_button=FakeButton(),
        global_config_status=FakeInput(""),
        _global_config_snapshot=None,
    )

    # 2.1 browse_global_config
    monkeypatch.setattr(
        "mutaui.ui.global_config_editor.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(tmp_path / "global.yml"), ""),
    )
    browse_global_config(window)
    assert window.global_config_path_input.text() == str(tmp_path / "global.yml")

    # 2.2 load_global_config empty path
    window.global_config_path_input.setText("")
    load_global_config(window)
    assert any("Choose the config file first" in i for i in informed)

    # 2.3 preview_global_config without loaded snapshot
    preview_global_config(window)
    assert any("Load a config file first" in i for i in informed)

    # 2.4 preview_global_config with invalid config
    from mutaui.adapters.yaml_config_editor import InvalidConfigForWrite

    window._global_config_snapshot = SimpleNamespace(valid=True, text="sync:\n  mode: one-way")

    def fail_preview(*_a: Any, **_k: Any) -> Any:
        raise InvalidConfigForWrite("Invalid indentation in draft")

    monkeypatch.setattr("mutaui.ui.global_config_editor.preview_yaml_text", fail_preview)
    preview_global_config(window)
    assert any("Invalid indentation" in w for w in warned)

    # 2.5 preview_global_config cancel in dialog
    preview_obj = SimpleNamespace(diff="--- a\n+++ b\n")
    monkeypatch.setattr(
        "mutaui.ui.global_config_editor.preview_yaml_text",
        lambda *a, **k: preview_obj,
    )

    class FakeMsgBox(QMessageBox):
        def __init__(self, *a: Any) -> None:
            super().__init__()
            self._custom_buttons: list[Any] = []

        def addButton(self, text: str, role: Any) -> Any:
            btn = super().addButton(text, role)
            self._custom_buttons.append(btn)
            return btn

        def exec(self) -> int:
            return 0

        def clickedButton(self) -> Any:
            # Return reject / cancel button
            return self._custom_buttons[1] if len(self._custom_buttons) > 1 else None

    monkeypatch.setattr("mutaui.ui.global_config_editor.QMessageBox", FakeMsgBox)
    preview_global_config(window)

    # 2.6 preview_global_config apply raising OSError
    class FakeMsgBoxApply(FakeMsgBox):
        def clickedButton(self) -> Any:
            return self._custom_buttons[0] if self._custom_buttons else None

    monkeypatch.setattr("mutaui.ui.global_config_editor.QMessageBox", FakeMsgBoxApply)

    def fail_apply(*_a: Any) -> Any:
        raise OSError("Permission denied saving config")

    monkeypatch.setattr("mutaui.ui.global_config_editor.apply_yaml_edit", fail_apply)
    preview_global_config(window)
    assert any("Permission denied saving config" in w for w in warned)

    # 2.7 preview_global_config apply success
    def succeed_apply(*_a: Any) -> Any:
        return SimpleNamespace(
            path=str(tmp_path / "global.yml"),
            backup_path=str(tmp_path / "global.yml.bak"),
            new_sha256="abc12345",
        )

    monkeypatch.setattr("mutaui.ui.global_config_editor.apply_yaml_edit", succeed_apply)
    monkeypatch.setattr(
        "mutaui.ui.global_config_editor.load_yaml_file",
        lambda _p: SimpleNamespace(valid=True, text="updated content", sha256="abc12345"),
    )
    preview_global_config(window)
    assert "Saved safely" in window.global_config_status.text()


# -----------------------------------------------------------------------------
# 3. settings_bundle_controller.py coverage
# -----------------------------------------------------------------------------
def test_settings_bundle_controller_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _get_app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)
    window.set_page(5)

    warned: list[str] = []
    criticals: list[str] = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda *a: warned.append(str(a[-1])),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "critical",
        lambda *a: criticals.append(str(a[-1])),
    )

    # 3.1 browse_binary
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: ("C:\\bin\\mutagen.exe", ""),
    )
    window.browse_binary()
    assert window.binary_edit.text() == "C:\\bin\\mutagen.exe"

    # 3.2 manage_ignore_presets with error
    def fail_preset_dialog(*_a: Any, **_k: Any) -> Any:
        raise IgnorePresetError("Corrupt preset JSON")

    monkeypatch.setattr(
        app_module,
        "IgnorePresetManagerDialog",
        fail_preset_dialog,
    )
    window.manage_ignore_presets()
    assert any("Corrupt preset JSON" in w for w in warned)

    # 3.3 manage_connection_profiles with invalid store
    monkeypatch.setattr(
        app_module,
        "load_profile_store",
        lambda _p: SimpleNamespace(valid=False, warnings=["Schema version invalid"]),
    )
    window.manage_connection_profiles()
    assert any("Schema version invalid" in w for w in warned)

    # 3.4 manage_ssh_profiles
    exec_called = []
    monkeypatch.setattr(
        app_module,
        "SSHProfileManagerDialog",
        lambda _w: SimpleNamespace(exec=lambda: exec_called.append(True)),
    )
    window.manage_ssh_profiles()
    assert exec_called == [True]

    # 3.5 save_settings failure (OSError)
    def fail_write(_conf: Any) -> None:
        raise OSError("Read-only file system")

    monkeypatch.setattr(app_module, "write_settings", fail_write)
    window.binary_edit.setText("")
    window.save_settings()
    assert any("Read-only file system" in c for c in criticals)

    window.close()


# -----------------------------------------------------------------------------
# 4. diagnostics_controller.py coverage
# -----------------------------------------------------------------------------
def test_diagnostics_controller_branches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _get_app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)
    window.set_page(5)

    informed: list[str] = []
    reported_errors: list[str] = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda *a: informed.append(str(a[-1])),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *a, **k: app_module.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window, "report_error", lambda err: reported_errors.append(str(err)))

    # 4.1 run_local_self_check in EN and CS
    from mutaui.ui.preferences import set_active_language

    set_active_language("en")
    window.run_local_self_check()
    assert len(informed) >= 1
    assert "Application path:" in informed[-1]

    set_active_language("cs")
    window.run_local_self_check()
    assert "Cesta aplikace:" in informed[-1]

    # 4.2 copy_diagnostics
    window.diag_summary.setText("Summary text")
    window.diagnostics_view.setPlainText("Diagnostics text")
    window.copy_diagnostics()
    assert "Summary text" in QApplication.clipboard().text()

    # 4.3 export_snapshot with write OSError
    target_json = tmp_path / "snap.json"
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(target_json), "JSON"),
    )

    orig_write_text = Path.write_text

    def fail_write_snap(self: Path, *args: Any, **kwargs: Any) -> Any:
        if "snap.json" in str(self):
            raise OSError("Access denied exporting snapshot")
        return orig_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_write_snap)
    window.export_snapshot()
    assert any("Access denied exporting snapshot" in e for e in reported_errors)

    # 4.4 export_session_log_snapshot with write OSError
    def fail_write_text(*args: Any, **kwargs: Any) -> Any:
        raise OSError("Disk quota exceeded for log snapshot")

    monkeypatch.setattr(Path, "write_text", fail_write_text)
    window.export_session_log_snapshot()
    assert any("Disk quota exceeded" in e for e in reported_errors)

    window.close()


# -----------------------------------------------------------------------------
# 5. command_controller.py coverage
# -----------------------------------------------------------------------------
def test_command_controller_preflight_and_error_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _get_app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)
    window.set_page(5)
    window.demo = False  # Enable real command path testing

    errors: list[str] = []
    monkeypatch.setattr(window, "report_error", lambda err: errors.append(str(err)))

    # 5.1 create_plan preparation failure
    def fail_prepare_create(*a: Any, **k: Any) -> Any:
        raise ValueError("Invalid target paths for session create")

    monkeypatch.setattr(
        "mutaui.ui.controllers.command_controller.MutagenClient.prepare_create_plan",
        fail_prepare_create,
    )
    window.run_command("sync", "create", options=["/a", "/b"])
    assert any("Invalid target paths" in e for e in errors)

    # 5.2 daemon_plan preparation failure
    def fail_prepare_daemon(*a: Any, **k: Any) -> Any:
        raise ValueError("Cannot stop daemon during active migration")

    monkeypatch.setattr(
        "mutaui.ui.controllers.command_controller.MutagenClient.prepare_daemon_plan",
        fail_prepare_daemon,
    )
    window.run_command("daemon", "stop")
    assert any("Cannot stop daemon" in e for e in errors)

    # 5.3 daemon_plan consent failure
    daemon_plan = SimpleNamespace(
        description="Stop daemon",
        risk="High",
        argv=["daemon", "stop"],
        requires_typed_confirmation=False,
        plan_id="p-1",
    )
    monkeypatch.setattr(
        "mutaui.ui.controllers.command_controller.MutagenClient.prepare_daemon_plan",
        lambda *a, **k: daemon_plan,
    )
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        "mutaui.ui.controllers.command_controller.QMessageBox.question",
        lambda *a, **k: QMessageBox.StandardButton.Yes,
    )

    def fail_consent(*a: Any, **k: Any) -> Any:
        raise ValueError("Consent token expired")

    monkeypatch.setattr(
        "mutaui.ui.controllers.command_controller.MutagenClient.consent_action_plan",
        fail_consent,
    )
    window.run_command("daemon", "stop")
    assert any("Consent token expired" in e for e in errors)

    window.close()


# -----------------------------------------------------------------------------
# 6. ignore_presets.py & connection_profiles.py & portable_bundle.py gaps
# -----------------------------------------------------------------------------
def test_ignore_presets_edge_cases(tmp_path: Path) -> None:
    # 6.1 Backslash in pattern body
    with pytest.raises(IgnorePresetError, match="Backslash escapes are unsupported"):
        validate_ignore_pattern("foo\\bar")

    # 6.2 Pattern with whitespace in _supported_syntax
    assert not _supported_syntax("dir with space/file")

    # 6.3 Store delete nonexistent ID
    store_file = tmp_path / "presets.json"
    store_file.write_text(json.dumps({"schema_version": 1, "presets": []}), encoding="utf-8")
    store = IgnorePresetStore(store_file)
    with pytest.raises(KeyError):
        store.delete("nonexistent_id")

    # 6.4 Invalid preset structure
    with pytest.raises(IgnorePresetError, match="timestamps must be strings"):
        _parse_preset(
            {
                "id": "valid-id",
                "name": "Preset",
                "description": "Desc",
                "patterns": ["*.pyc"],
                "created_at": 1234567,  # invalid timestamp type
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

    # 6.5 Preset name too long
    with pytest.raises(IgnorePresetError, match="name must be 1–120"):
        _parse_preset(
            {
                "id": "valid-id",
                "name": "x" * 121,
                "description": "Desc",
                "patterns": [],
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            }
        )


def test_connection_profiles_edge_cases(tmp_path: Path) -> None:
    store_file = tmp_path / "profiles.json"
    store_file.write_text(json.dumps({"schema_version": 1, "profiles": []}), encoding="utf-8")
    store = ConnectionProfileStore(store_file)

    p1 = ConnectionProfile(
        id="prof-1",
        name="Profile 1",
        kind="sync",
        endpoint_a="C:\\local",
        endpoint_b="server:/remote",
        defaults={},
    )
    store.add(p1)

    # Duplicate add
    with pytest.raises(ProfileStoreError, match="already exists"):
        store.add(p1)

    # Update nonexistent
    with pytest.raises(KeyError):
        store.update(ConnectionProfile("unknown", "X", "sync", "/a", "/b", {}))

    # Delete nonexistent
    with pytest.raises(KeyError):
        store.delete("unknown")


def test_portable_bundle_sanitizer_edge_cases() -> None:
    warnings: list[str] = []
    # Not a list or exceeds 10,000 items
    with pytest.raises(ValueError, match="bounded list"):
        _sanitize_records("not a list", warnings, include_local_paths=False)  # type: ignore[arg-type]

    # Item not a dict
    with pytest.raises(ValueError, match="must be objects"):
        _sanitize_records(["string_item"], warnings, include_local_paths=False)  # type: ignore[list-item]
