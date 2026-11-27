"""Targeted high-yield tests to achieve >= 95% branch coverage gate."""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

import app as app_module
import mutagen_client
from connection_profiles import ConnectionProfile, ConnectionProfileStore
from mutaui.services.session_provenance import ProvenanceCapacity, ProvenanceStoreError
from mutaui.ui.connection_profiles_dialog import ConnectionProfilesDialog
from mutaui.ui.controllers.command_controller import CommandExecutionMixin
from mutaui.ui.controllers.diagnostics_controller import DiagnosticsMixin
from mutaui.ui.ssh_profile_manager import SSHProfileManagerDialog
from settings import settings_path


def _get_app() -> QApplication:
    return QApplication.instance() or QApplication([])


# -----------------------------------------------------------------------------
# 1. settings.py cross-platform branch coverage
# -----------------------------------------------------------------------------
def test_settings_path_darwin_and_linux_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 1. darwin primary exists
    monkeypatch.setattr(sys, "platform", "darwin")
    home = tmp_path / "home_darwin"
    monkeypatch.setattr(Path, "home", lambda: home)
    darwin_primary = home / "Library" / "Application Support" / "MutagenControl" / "settings.json"
    darwin_primary.parent.mkdir(parents=True, exist_ok=True)
    darwin_primary.write_text("{}", encoding="utf-8")
    assert settings_path() == darwin_primary

    # 2. darwin fallback to XDG config
    darwin_primary.unlink()
    xdg_cfg = tmp_path / "xdg_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_cfg))
    darwin_xdg = xdg_cfg / "MutagenControl" / "settings.json"
    darwin_xdg.parent.mkdir(parents=True, exist_ok=True)
    darwin_xdg.write_text("{}", encoding="utf-8")
    assert settings_path() == darwin_xdg

    # 3. darwin defaults to primary when neither exists
    darwin_xdg.unlink()
    assert settings_path() == darwin_primary

    # 4. linux primary does not exist, legacy_mutaui exists
    monkeypatch.setattr(sys, "platform", "linux")
    linux_home = tmp_path / "home_linux"
    monkeypatch.setattr(Path, "home", lambda: linux_home)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(linux_home / ".config"))
    legacy_mutaui = linux_home / ".mutaui" / "settings.json"
    legacy_mutaui.parent.mkdir(parents=True, exist_ok=True)
    legacy_mutaui.write_text("{}", encoding="utf-8")
    assert settings_path() == legacy_mutaui

    # 5. linux legacy_config in XDG exists
    legacy_config = linux_home / ".config" / "mutaui" / "settings.json"
    legacy_config.parent.mkdir(parents=True, exist_ok=True)
    legacy_config.write_text("{}", encoding="utf-8")
    assert settings_path() == legacy_config

    # 6. linux neither legacy exists -> returns primary
    legacy_mutaui.unlink()
    legacy_config.unlink()
    assert settings_path() == linux_home / ".config" / "MutagenControl" / "settings.json"


# -----------------------------------------------------------------------------
# 2. app.py linux file manager integration branches
# -----------------------------------------------------------------------------
def test_app_main_linux_file_manager_branches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    # 1. install on non-linux raises IntegrationError
    monkeypatch.setattr(sys, "platform", "win32")
    launch = SimpleNamespace(
        linux_file_manager_action="install",
        version=False,
        session_daemon_self_test=False,
    )
    monkeypatch.setattr("mutaui.services.command_line.parse_launch_command", lambda _argv: launch)
    rc = app_module.main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "Linux only" in err

    # 2. install on linux when not frozen
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    rc = app_module.main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "packaged AppImage first" in err

    # 3. install on linux frozen with APPIMAGE env var
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPIMAGE", "/opt/MutagenControl.AppImage")
    installed_target = []
    monkeypatch.setattr(
        "mutaui.services.linux_file_manager_integration.install_linux_file_manager_integration",
        lambda bin_path: (
            installed_target.append(bin_path)
            or SimpleNamespace(success=True, message="Installed ok")
        ),
    )
    rc = app_module.main()
    assert rc == 0
    assert len(installed_target) == 1

    # 4. install on linux frozen without APPIMAGE, transient extraction path
    monkeypatch.delenv("APPIMAGE", raising=False)
    monkeypatch.setattr(sys, "executable", "/tmp/.mount_mutagen1234/usr/bin/python")
    monkeypatch.setattr(
        "mutaui.services.linux_file_manager_integration.is_transient_extraction_path",
        lambda _p: True,
    )
    rc = app_module.main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "Cannot register integration from temporary AppImage" in err

    # 5. remove linux file manager action
    launch.linux_file_manager_action = "remove"
    removed = []
    monkeypatch.setattr(
        "mutaui.services.linux_file_manager_integration.remove_linux_file_manager_integration",
        lambda: removed.append(True) or SimpleNamespace(success=True, message="Removed ok"),
    )
    rc = app_module.main()
    assert rc == 0
    assert removed == [True]


# -----------------------------------------------------------------------------
# 3. ConnectionProfilesDialog edit, duplicate, and validation branches
# -----------------------------------------------------------------------------
def test_connection_profiles_dialog_edit_and_duplicate_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _get_app()
    store_path = tmp_path / "connection-profiles.json"
    store = ConnectionProfileStore(store_path)
    p1 = ConnectionProfile(
        id="p1",
        name="Profile 1",
        kind="sync",
        endpoint_a="/local",
        endpoint_b="user@host:/remote",
        tags=("dev",),
        favorite=False,
        defaults={"mode": "two-way-safe"},
    )
    store.add(p1)

    dlg = ConnectionProfilesDialog(None, store)

    # 1. edit_selected with no selection shows warning
    dlg.table.clearSelection()
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(str(args[-1])))
    dlg.edit_selected()
    assert any("select a profile to edit" in w.lower() for w in warned)

    # 2. edit_selected dialog cancelled
    dlg.table.selectRow(0)
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)
    dlg.edit_selected()
    assert dlg.selected_profile().name == "Profile 1"

    # 3. edit_selected invalid defaults JSON
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Accepted)
    warned.clear()
    with patch(
        "mutaui.ui.connection_profiles_dialog.QPlainTextEdit.toPlainText",
        return_value="not valid json",
    ):
        dlg.edit_selected()
    assert len(warned) == 1

    # 4. edit_selected valid defaults but not a dict
    warned.clear()
    with patch(
        "mutaui.ui.connection_profiles_dialog.QPlainTextEdit.toPlainText", return_value="[1, 2, 3]"
    ):
        dlg.edit_selected()
    assert any("must be a JSON object" in w for w in warned)

    # 5. edit_selected successful update
    warned.clear()
    with (
        patch(
            "mutaui.ui.connection_profiles_dialog.QPlainTextEdit.toPlainText",
            return_value='{"mode": "two-way-safe"}',
        ),
        patch(
            "mutaui.ui.connection_profiles_dialog.QLineEdit.text", return_value="Profile 1 Updated"
        ),
    ):
        dlg.edit_selected()
    assert next(p for p in store.profiles if p.id == "p1").name == "Profile 1 Updated"

    # 6. duplicate_selected with no selection
    dlg.table.clearSelection()
    dlg.duplicate_selected()  # does nothing safely

    # 7. duplicate_selected with selection
    dlg.table.selectRow(0)
    dlg.duplicate_selected()
    assert len(store.profiles) == 2
    dlg.close()


# -----------------------------------------------------------------------------
# 4. SSHProfileManagerDialog closeEvent, error handling, and branches
# -----------------------------------------------------------------------------
def test_ssh_profile_manager_dialog_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _get_app()
    cfg = tmp_path / "ssh_config"
    cfg.write_text("Host srv\n  HostName srv.example.com\n  User test\n", encoding="utf-8")
    dlg = SSHProfileManagerDialog(None, cfg)

    # 1. closeEvent while running: user says No -> event ignored
    dlg._running = True
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    ev = QCloseEvent()
    dlg.closeEvent(ev)
    assert not ev.isAccepted()

    # 2. closeEvent while running: user says Yes -> event accepted
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    ev2 = QCloseEvent()
    dlg.closeEvent(ev2)
    assert ev2.isAccepted()
    dlg._running = False

    # 3. reload_config with invalid config
    monkeypatch.setattr(
        "mutaui.ui.ssh_profile_manager.parse_ssh_config",
        lambda _p: SimpleNamespace(valid=False, profiles=(), warnings=["Parsing error in config"]),
    )
    dlg.reload_config()
    assert "Config could not be read safely" in dlg.config_status.text()

    # 4. resolve_selected with unexpanded directives and strict host-key checking warnings
    monkeypatch.setattr(
        "mutaui.ui.ssh_profile_manager.parse_ssh_config",
        lambda _p: SimpleNamespace(
            valid=True,
            profiles=[SimpleNamespace(alias="srv", unsupported=["Match exec"])],
            warnings=[],
        ),
    )
    dlg.reload_config()
    monkeypatch.setattr(
        "mutaui.ui.ssh_profile_manager.resolve_ssh_options",
        lambda _alias: SimpleNamespace(
            success=True,
            message="ok",
            stderr="",
            options={"stricthostkeychecking": ("no",), "hostname": ("srv.example.com",)},
        ),
    )
    dlg.resolve_selected()
    details = dlg.details.toPlainText()
    assert "Unexpanded directives" in details
    assert "WARNING: effective config disables strict host-key checking" in details

    # 5. test_selected user cancels
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    tested = []
    monkeypatch.setattr(
        "mutaui.ui.ssh_profile_manager.test_ssh_connection", lambda a: tested.append(a)
    )
    dlg.test_selected()
    assert tested == []

    # 6. test_selected failure message
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(
        "mutaui.ui.ssh_profile_manager.test_ssh_connection",
        lambda a: SimpleNamespace(
            success=False,
            message="Host key mismatch",
            stderr="Remote host identification has changed",
        ),
    )
    warns = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warns.append(str(args[-1])))
    dlg.test_selected()
    assert len(warns) == 1
    assert "Remote host identification has changed" in warns[0]

    # 7. resolve_selected on_error branch
    def _raise_resolve(_alias):
        raise RuntimeError("SSH boom")

    monkeypatch.setattr("mutaui.ui.ssh_profile_manager.resolve_ssh_options", _raise_resolve)
    dlg.resolve_selected()
    assert "SSH boom" in dlg.details.toPlainText()

    # 8. test_selected on_error branch
    def _raise_test(_alias):
        raise RuntimeError("Conn refused")

    monkeypatch.setattr("mutaui.ui.ssh_profile_manager.test_ssh_connection", _raise_test)
    warns.clear()
    dlg.test_selected()
    assert len(warns) == 1
    assert "Conn refused" in warns[0]

    dlg.close()


# -----------------------------------------------------------------------------
# 5. DiagnosticsController export and troubleshooter branches
# -----------------------------------------------------------------------------
def test_diagnostics_controller_export_and_coalescing_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _get_app()

    class DummyWindow(DiagnosticsMixin):
        def __init__(self) -> None:
            from mutagen_client import Snapshot

            self.snapshot = Snapshot()
            self.logs: list[str] = []
            self.pending_action = True
            self._active_troubleshooter = None
            self.errors: list[str] = []

        def add_log(self, text: str) -> None:
            self.logs.append(text)

        def report_error(self, text: str) -> None:
            self.errors.append(text)

    win = DummyWindow()

    # 1. export_safe_diagnostics cancelled (path empty)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    win.export_safe_diagnostics()
    assert win.logs == []

    # 2. export_safe_diagnostics success
    export_target = tmp_path / "safe.json"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args: (str(export_target), "JSON (*.json)")
    )
    win.export_safe_diagnostics()
    assert export_target.is_file()
    assert "Safe diagnostics export complete" in win.logs[-1]

    # 3. export_safe_diagnostics write error
    monkeypatch.setattr(Path, "write_text", MagicMock(side_effect=OSError("Disk full")))
    win.export_safe_diagnostics()
    assert "Disk full" in win.errors[-1]

    # 4. export_snapshot cancelled (path empty)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    win.export_snapshot()

    # 5. export_snapshot cancelled at confirmation dialog
    snap_target = tmp_path / "snap.json"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args: (str(snap_target), "JSON (*.json)")
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    win.export_snapshot()
    assert not snap_target.exists()


# -----------------------------------------------------------------------------
# 6. CommandExecutionMixin preflight fingerprint & provenance capacity branches
# -----------------------------------------------------------------------------
def test_command_controller_preflight_and_provenance_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _get_app()

    class DummyCommandWindow(CommandExecutionMixin):
        def __init__(self) -> None:
            self.demo = False
            self.pending_action = False
            self.client = SimpleNamespace(
                binary="mutagen",
                last_created_session=("sync", "s-123", ("sync", "create", "/a", "/b")),
            )
            self.action_planner = SimpleNamespace(cancel=MagicMock())
            self.session_provenance = SimpleNamespace(
                record=MagicMock(),
                capacity=lambda: ProvenanceCapacity(
                    record_count=98,
                    max_records=100,
                    file_bytes=9800,
                    max_store_bytes=10000,
                    is_near_limit=True,
                    is_full=False,
                ),
            )
            self.logs: list[str] = []
            self.errors: list[str] = []

        def add_log(self, text: str) -> None:
            self.logs.append(text)

        def report_error(self, text: str) -> None:
            self.errors.append(text)

        def submit(self, work, on_result=None, on_error=None, on_done=None) -> None:
            try:
                res = work()
                if on_result:
                    on_result(res)
            except Exception as exc:
                if on_error:
                    on_error(str(exc))
            self.pending_action = False
            if on_done:
                on_done()

    win = DummyCommandWindow()

    # 1. Preflight fingerprint mismatch aborts command
    create_plan = SimpleNamespace(
        plan_id="plan-1",
        argv=["sync", "create", "/a", "/b"],
        preflight_fingerprint="outdated-fp-12345",
        description="Create session",
        risk="low",
        backup_required=False,
        backup_choice=None,
        requires_typed_confirmation=False,
    )
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warned.append(str(args[-1])))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(
        "mutagen_client.create_plan_fingerprint",
        lambda _argv: "fresh-new-fingerprint-67890",
    )
    monkeypatch.setattr(
        "mutagen_client.MutagenClient.prepare_create_plan",
        lambda *args, **kwargs: create_plan,
    )

    win.run_command("sync", "create", options=["/a", "/b"])
    win.action_planner.cancel.assert_called_once_with("plan-1")
    assert any("modified after preflight" in w for w in warned)

    # 2. Matching fingerprint runs and logs provenance near capacity
    monkeypatch.setattr(
        "mutagen_client.create_plan_fingerprint",
        lambda _argv: "matching-fp",
    )
    create_plan.preflight_fingerprint = "matching-fp"
    monkeypatch.setattr(
        "mutagen_client.MutagenClient.prepare_create_plan",
        lambda *args, **kwargs: create_plan,
    )
    monkeypatch.setattr(
        "mutagen_client.MutagenClient.consent_action_plan",
        lambda *args, **kwargs: create_plan,
    )
    monkeypatch.setattr(
        "mutagen_client.MutagenClient.execute",
        lambda *args, **kwargs: "Created session s-123",
    )
    orig_init = mutagen_client.MutagenClient.__init__

    def fake_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self.last_created_session = ("sync", "s-123", ("sync", "create", "/a", "/b"))

    monkeypatch.setattr(mutagen_client.MutagenClient, "__init__", fake_init)

    win.run_command("sync", "create", options=["/a", "/b"])
    assert any("near capacity" in log for log in win.logs)

    # 3. Provenance record error logs warning without failing
    win.session_provenance.record = MagicMock(side_effect=ProvenanceStoreError("DB locked"))
    win.run_command("sync", "create", options=["/a", "/b"])
    assert any("provenance was not saved" in log for log in win.logs)


def test_ignore_presets_edge_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ignore_presets import (
        IGNORE_SCHEMA_VERSION,
        MAX_IGNORE_FILE_BYTES,
        MAX_PRESETS,
        MAX_RULES_PER_PRESET,
        IgnorePreset,
        IgnorePresetError,
        IgnorePresetStore,
        _parse_preset,
        load_ignore_presets,
        path_aware_ignore_rule,
    )

    root = tmp_path / "root"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("hello", encoding="utf-8")

    # Symlink check in path_aware_ignore_rule
    calls = []

    def mock_is_symlink(self: Path) -> bool:
        calls.append(self)
        return len(calls) > 1

    with (
        patch.object(Path, "is_symlink", mock_is_symlink),
        pytest.raises(IgnorePresetError, match="Symlinked path components"),
    ):
        path_aware_ignore_rule(root, target)

    with pytest.raises(IgnorePresetError, match="Ignore preset ID is invalid"):
        _parse_preset(
            {
                "id": "invalid id with spaces!",
                "name": "n",
                "description": "d",
                "patterns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

    with pytest.raises(IgnorePresetError, match="at most 500 characters"):
        _parse_preset(
            {
                "id": "valid_id",
                "name": "n",
                "description": "x" * 501,
                "patterns": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

    with pytest.raises(IgnorePresetError, match="at most"):
        _parse_preset(
            {
                "id": "valid_id",
                "name": "n",
                "description": "d",
                "patterns": ["p"] * (MAX_RULES_PER_PRESET + 1),
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )

    store_file = tmp_path / "large_store.json"
    store_file.write_text("{}", encoding="utf-8")
    with patch.object(Path, "stat") as mock_stat:
        mock_stat.return_value.st_size = 6 * MAX_IGNORE_FILE_BYTES
        res = load_ignore_presets(store_file)
        assert not res.valid
        assert any("exceeds its size limit" in w for w in res.warnings)

    ver_file = tmp_path / "bad_ver.json"
    ver_file.write_text(json.dumps({"schema_version": 999, "presets": []}), encoding="utf-8")
    res = load_ignore_presets(ver_file)
    assert not res.valid
    assert any("Unsupported ignore preset schema" in w for w in res.warnings)

    bad_entries = tmp_path / "bad_entries.json"
    bad_entries.write_text(
        json.dumps({"schema_version": IGNORE_SCHEMA_VERSION, "presets": "not-a-list"}),
        encoding="utf-8",
    )
    res = load_ignore_presets(bad_entries)
    assert not res.valid

    dup_file = tmp_path / "dup.json"
    dup_file.write_text(
        json.dumps(
            {
                "schema_version": IGNORE_SCHEMA_VERSION,
                "presets": [
                    {
                        "id": "same",
                        "name": "A",
                        "description": "",
                        "patterns": [],
                        "created_at": "t",
                        "updated_at": "t",
                    },
                    {
                        "id": "same",
                        "name": "B",
                        "description": "",
                        "patterns": [],
                        "created_at": "t",
                        "updated_at": "t",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    res = load_ignore_presets(dup_file)
    assert not res.valid
    assert any("must be unique" in w for w in res.warnings)

    store = IgnorePresetStore(tmp_path / "store.json")
    too_many = [
        IgnorePreset(f"id_{i}", f"Name {i}", "", (), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
        for i in range(MAX_PRESETS + 1)
    ]
    with pytest.raises(IgnorePresetError, match="at most"):
        store._save(too_many)

    dup_presets = [
        IgnorePreset("same", "Name 1", "", (), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        IgnorePreset("same", "Name 2", "", (), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    ]
    with pytest.raises(IgnorePresetError, match="must be unique"):
        store._save(dup_presets)

    valid_preset = [
        IgnorePreset(
            "p1", "Preset 1", "Desc", ("pattern/*",), "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
        )
    ]
    orig_open = os.open

    def mock_open(path: Any, *args: Any, **kwargs: Any) -> int:
        if str(path) == str(store.path.parent):
            return 999
        return orig_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "name", "posix")
    with (
        patch("os.open", side_effect=mock_open),
        patch("os.fsync") as mock_fsync,
        patch("os.close"),
    ):
        store._save(valid_preset)
        assert mock_fsync.called


def test_mutagen_client_edge_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    from mutagen_client import (
        MutagenError,
        Snapshot,
        _endpoint_matches,
        read_registration,
        validate_session_rows,
    )

    assert _endpoint_matches("user@host:/path", "") is True
    assert _endpoint_matches("tcp:localhost:8080", "tcp:localhost:8080") is True

    with pytest.raises(MutagenError, match="malformed session entries"):
        validate_session_rows(["not-a-dict"], allow_all_invalid_error=True)

    s1 = Snapshot(daemon_state="checking", error="Forward connection failed")
    assert s1.forward_error == "Forward connection failed"
    s2 = Snapshot(daemon_state="checking", error="Sync failed abruptly")
    assert s2.sync_error == "Sync failed abruptly"
    assert s2.daemon_state == "unconfigured"

    monkeypatch.setattr(sys, "platform", "linux")
    assert read_registration("/bin/mutagen") == ("unsupported", "")

    monkeypatch.setattr(sys, "platform", "darwin")
    with patch.object(Path, "is_file", return_value=True):
        with patch.object(Path, "read_text", return_value="<plist>/bin/mutagen</plist>"):
            reg, _ = read_registration("/bin/mutagen")
            assert reg == "registered"
        with patch.object(Path, "read_text", return_value="<plist>other</plist>"):
            reg, _ = read_registration("/bin/mutagen")
            assert reg == "other"
    with patch.object(Path, "is_file", return_value=False):
        assert read_registration("/bin/mutagen") == ("unsupported", "")


def test_session_dialog_forward_and_risky_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_app()
    from connection_profiles import ConnectionProfile
    from mutaui.ui.session_dialog import SessionDialog

    prof = ConnectionProfile(
        id="p1",
        name="AdvForward",
        kind="forward",
        endpoint_a="unix:/tmp/source.sock",
        endpoint_b="unix:/tmp/dest.sock",
        defaults={
            "source.socket.overwriteMode": "overwrite",
            "source.socket.owner": "1000",
            "source.socket.group": "1000",
            "source.socket.permissionMode": "0600",
        },
    )

    diag = SessionDialog(kind="forward", ui_mode="advanced", saved_profiles=(prof,))
    diag.a.setText("unix:/tmp/source.sock")
    diag.b.setText("unix:/tmp/dest.sock")

    # Connection profile population
    if diag.connection_profile is not None:
        diag.connection_profile.setCurrentIndex(1)
        diag.apply_connection_profile()
        if diag.socket_overwrite_source is not None:
            assert diag.socket_overwrite_source.currentData() == "overwrite"
        if diag.socket_owner_source is not None:
            assert diag.socket_owner_source.text() == "1000"

        # Connection profile reset (index 0)
        diag.connection_profile.setCurrentIndex(0)
        diag.apply_connection_profile()
        if diag.socket_overwrite_source is not None:
            assert diag.socket_overwrite_source.currentIndex() == 0

    # Test unix socket inspection unavailable
    if diag.socket_overwrite_source is not None:
        diag.socket_overwrite_source.setCurrentIndex(
            diag.socket_overwrite_source.findData("overwrite")
        )
    diag.a.setText("unix:/tmp/source.sock")
    diag.b.setText("unix:/tmp/dest.sock")
    with patch("forward_configuration.local_unix_socket_entry_type", return_value="unavailable"):
        err = diag.forward_socket_error()
        assert err is not None
        assert "cannot be safely inspected" in err

    with (
        patch.object(diag, "forward_socket_error", return_value="Test socket error"),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        diag.validate()
        assert mock_warn.called

    with patch.object(diag, "forward_socket_error", return_value=None):
        if diag.socket_overwrite_source is not None:
            diag.socket_overwrite_source.setCurrentIndex(
                diag.socket_overwrite_source.findData("overwrite")
            )
        with (
            patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No),
            patch.object(diag, "accept") as mock_accept,
        ):
            diag.validate()
            assert not mock_accept.called

    sync_diag = SessionDialog(kind="sync", ui_mode="advanced")
    sync_diag.a.setText("C:/tmp/a")
    sync_diag.b.setText("C:/tmp/b")
    sync_diag.mode.setCurrentText("two-way-resolved")

    with (
        patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No),
        patch.object(sync_diag, "accept") as mock_accept,
    ):
        sync_diag.validate()
        assert not mock_accept.called

    sync_diag.mode.setCurrentText("one-way-replica")
    sync_diag.replica_backup.setChecked(False)
    with (
        patch.object(
            QMessageBox, "warning", side_effect=[QMessageBox.StandardButton.Yes, None]
        ) as mock_warn,
        patch.object(sync_diag, "accept") as mock_accept,
    ):
        sync_diag.validate()
        assert not mock_accept.called
        assert mock_warn.call_count == 2

    fwd_public = SessionDialog(kind="forward", ui_mode="basic")
    fwd_public.a.setText("tcp:0.0.0.0:8080")
    fwd_public.b.setText("tcp:127.0.0.1:8080")
    with (
        patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No),
        patch.object(fwd_public, "accept") as mock_accept,
    ):
        fwd_public.validate()
        assert not mock_accept.called


def test_servers_endpoints_controller_branches() -> None:
    _get_app()
    from mutaui.ui.controllers.servers_endpoints_controller import ServersEndpointsMixin

    class DummyServers(QWidget, ServersEndpointsMixin):
        def __init__(self) -> None:
            super().__init__()
            self.ui_language = "en"
            self.snapshot = SimpleNamespace(sync=[], forward=[])
            self._server_groups = {}
            self.pages = SimpleNamespace(currentIndex=lambda: 0)
            self.server_scope_label = QLabel()
            self.server_sync_empty = QLabel()
            self.server_forward_empty = QLabel()
            self.server_sync_table = QTableWidget(2, 2)
            self.server_forward_table = QTableWidget(2, 2)
            self.sync_table = QTableWidget(2, 2)
            self.sync_table.model = lambda: SimpleNamespace(
                row_for_identifier=lambda s: 0 if s == "s1" else -1, index=lambda r, c: None
            )
            self.sync_table.scrollTo = MagicMock()
            self.forward_table = QTableWidget(2, 2)
            self.sync_server_filter = QComboBox()
            self.server_overview = QTableWidget(2, 5)
            self.page_index = 0
            self.update_endpoint_details = MagicMock()
            self.filter_table = MagicMock()
            self.fit_table_to_rows = MagicMock()

        def set_page(self, page: int) -> None:
            self.page_index = page

        def server_targets(self, kind: str, target: str) -> list[dict[str, Any]]:
            return [
                {
                    "identifier": "sess_1",
                    "name": "Session 1",
                    "paused": False,
                    "alpha": {"path": "C:/a"},
                    "beta": {"path": "C:/b"},
                    "source": "80",
                    "destination": "8080",
                }
            ]

    with patch(
        "mutaui.ui.controllers.servers_endpoints_controller.QMessageBox.information"
    ) as mock_info:
        dummy = DummyServers()
        dummy.update_endpoint_sessions(dummy.snapshot)

        dummy.endpoint_combo = QComboBox()
        dummy.snapshot.sync = [{"identifier": "s1", "name": "Sync1"}]
        dummy.snapshot.forward = [{"identifier": "f1", "name": "Fwd1"}]
        dummy.update_endpoint_sessions(dummy.snapshot)
        assert dummy.endpoint_combo.count() == 2

        dummy.update_server_groups()
        dummy.server_selector = QComboBox()
        dummy.update_server_groups()
        assert dummy.server_selector.count() >= 1

        del dummy.server_selector
        dummy.update_server_details()

        dummy.server_selector = QComboBox()
        dummy.server_selector.addItem("Unavailable", "__unavailable__")
        btn = QPushButton()
        dummy.b_srv_sync = btn
        dummy.update_server_details()
        assert not btn.isEnabled()

        dummy.server_selector.clear()
        dummy.server_selector.addItem("All Sessions", "__all__")
        dummy.update_server_details()
        assert btn.isEnabled()

        # Row 99 empty -> returns early
        dummy.open_group_session("sync", 99)

        item = QTableWidgetItem("Session 1")
        item.setData(Qt.ItemDataRole.UserRole, "s1")
        dummy.server_sync_table.setItem(0, 0, item)
        dummy.focus_session_from_navigator = MagicMock(return_value=True)
        dummy.open_group_session("sync", 0)
        assert dummy.focus_session_from_navigator.called

        dummy.focus_session_from_navigator = MagicMock(return_value=False)
        dummy.sync_server_filter.addItem("All")
        dummy.sync_search = QLabel()
        dummy.sync_search.clear = MagicMock()
        dummy.sync_state_filter = QComboBox()
        dummy.sync_state_filter.addItem("All")
        dummy.sync_favorites_only = QPushButton()
        dummy.sync_favorites_only.setChecked = MagicMock()

        table_item = QTableWidgetItem("s1")
        table_item.setData(Qt.ItemDataRole.UserRole, "s1")
        dummy.sync_table.setItem(0, 0, table_item)
        dummy.open_group_session("sync", 0)
        assert dummy.page_index == 1

        item_unknown = QTableWidgetItem("Unknown")
        item_unknown.setData(Qt.ItemDataRole.UserRole, "unknown_id")
        dummy.server_sync_table.setRowCount(2)
        dummy.server_sync_table.setItem(1, 0, item_unknown)
        dummy.open_group_session("sync", 1)
        assert mock_info.called


def test_snapshot_controller_branches() -> None:
    _get_app()
    from mutagen_client import MutagenClient, MutagenError, MutagenLaunchError, Snapshot
    from mutaui.ui.controllers.snapshot_controller import SnapshotLifecycleMixin

    class DummySnapshot(SnapshotLifecycleMixin):
        def __init__(self) -> None:
            self.demo = False
            self.pending_poll = False
            self.pending_action = False
            self._refresh_generation = 0
            self._refresh_again = False
            self.client = SimpleNamespace(
                binary=str(Path(sys.executable)), list_sessions=MagicMock()
            )
            self.snapshot = Snapshot(sync=[], forward=[], binary=str(Path(sys.executable)))
            self._version_cache = ("0.18.1", time.monotonic(), str(Path(sys.executable)))
            self._last_snapshot_received_monotonic = None
            self._poll_started_at = 0.0
            self.health_tracker = SimpleNamespace(note_environment_event=MagicMock())
            self.logs = []
            self.updated = QLabel()
            self.hero_title = QLabel()
            self.hero_sub = QLabel()
            self.hero_badge = QLabel()
            self.daemon_title = QLabel()
            self.daemon_desc = QLabel()
            self.daemon_diagnostics_button = QPushButton()
            self.metric_widgets = defaultdict(QLabel)
            self.overview_scope_label = QLabel()
            self.register_message = QLabel()
            self.side_state = QLabel()
            self.side_sub = QLabel()
            self.start_button = QPushButton()
            self.stop_button = QPushButton()
            self.daemon_action_hint = QLabel()
            self.health_ring = SimpleNamespace(
                set_health=MagicMock(), setProperty=MagicMock(), setToolTip=MagicMock()
            )
            self.sync_summary = QLabel()
            self.forward_summary = QLabel()
            self.update_polling_mode = MagicMock()
            self.check_alerts = MagicMock()
            self.poll_backoff = SimpleNamespace(
                can_retry=lambda force: True,
                observe=MagicMock(),
                remaining=MagicMock(return_value=0),
            )
            self.sync_table = QTableWidget()
            self.forward_table = QTableWidget()
            self.dashboard_table = QTableWidget()
            self.favorites = {"sync": set(), "forward": set()}
            self._table_signatures = {}
            self.pages = SimpleNamespace(currentIndex=lambda: 0)
            self.footer = QLabel()
            self.fill_table = MagicMock()
            self.filter_table = MagicMock()
            self.refresh_detail = MagicMock()
            self.update_server_groups = MagicMock()
            self.update_server_details = MagicMock()
            self.update_endpoint_sessions = MagicMock()
            self.update_endpoint_details = MagicMock()

        def add_log(self, msg: str) -> None:
            self.logs.append(msg)

    ctrl = DummySnapshot()
    ctrl.poll_backoff.can_retry = lambda force: False
    ctrl.refresh(force=False)
    assert ctrl._refresh_generation == 0

    ctrl.poll_backoff.can_retry = lambda force: True
    ctrl.pending_action = True
    ctrl.refresh()
    assert ctrl._refresh_generation == 0

    ctrl.pending_action = False
    ctrl.pending_poll = True
    ctrl.refresh(force=True)
    assert ctrl._refresh_again is True

    # Run work function with errors
    ctrl.pending_poll = False
    with patch("mutaui.ui.controllers.snapshot_controller.submit_background_task") as mock_submit:
        ctrl.refresh(force=True)
        assert mock_submit.called
        work_fn = mock_submit.call_args[0][1]

        # Case 1: single error
        with patch.object(
            MutagenClient,
            "list_sessions_checked",
            side_effect=[
                MutagenError("Single sync error"),
                SimpleNamespace(sessions=[], incomplete=False, rejected_count=0),
            ],
        ):
            snap1 = work_fn()
            assert "Single sync error" in snap1.error

        # Case 2: multiple errors with launch error
        with patch.object(
            MutagenClient,
            "list_sessions_checked",
            side_effect=[MutagenError("Sync err"), MutagenLaunchError("CLI failed")],
        ):
            snap2 = work_fn()
            assert snap2.daemon_state == "unavailable"

    # apply_snapshot: wake event detection (>180s)
    ctrl._last_snapshot_received_monotonic = 10.0
    with patch("time.monotonic", return_value=300.0):
        new_snap = Snapshot(sync=[], forward=[], binary=str(Path(sys.executable)), version="0.18.1")
        ctrl.apply_snapshot(new_snap)
        assert ctrl.health_tracker.note_environment_event.called
        assert ctrl.hero_badge.isVisible()

    new_snap2 = Snapshot(sync=[], forward=[], binary=str(Path(sys.executable)), version="")
    ctrl.apply_snapshot(new_snap2)
    assert not ctrl.hero_badge.isVisible()


def test_session_actions_controller_branches() -> None:
    _get_app()
    from mutaui.ui.controllers.session_actions_controller import SessionActionsMixin

    class DummySessionActions(SessionActionsMixin):
        def __init__(self) -> None:
            self.demo = False
            self.pending_action = False
            self.snapshot = SimpleNamespace(
                sync=[{"identifier": "s1", "name": "Sync 1", "paused": True}],
                forward=[
                    {
                        "identifier": "f1",
                        "name": "Fwd 1",
                        "source": "tcp::80",
                        "destination": "tcp::8080",
                    }
                ],
                registration="registered",
            )
            self.sync_details = QLabel()
            self.sync_title = QLabel()
            self.sync_tag = QLabel()
            self.sync_controls = {
                "pause": QPushButton(),
                "resume": QPushButton(),
                "flush": QPushButton(),
            }
            self.sync_progress = QPushButton()
            self.sync_favorite_button = QPushButton()
            self.sync_autostart_button = QPushButton()
            self.sync_troubleshoot_button = QPushButton()

            self.forward_details = QLabel()
            self.forward_title = QLabel()
            self.forward_tag = QLabel()
            self.forward_controls = {"pause": QPushButton(), "resume": QPushButton()}
            self.forward_progress = QPushButton()
            self.forward_favorite_button = QPushButton()

            self.conf = {"session_prefs": {}, "favorites": {"sync": [], "forward": []}}
            self.favorites = {"sync": set(), "forward": set()}
            self._table_signatures = {}
            self.sync_table = QTableWidget(1, 1)
            self.forward_table = QTableWidget(1, 1)
            self.errors = []
            self.logs = []
            self.filter_table = MagicMock()

        def selected_session(self, kind: str) -> dict[str, Any] | None:
            if getattr(self, "_no_selected", False):
                return None
            if kind == "sync":
                return self.snapshot.sync[0]
            return self.snapshot.forward[0]

        def report_error(self, err: str) -> None:
            self.errors.append(err)

        def add_log(self, msg: str) -> None:
            self.logs.append(msg)

        def fill_table(self, *args: Any, **kwargs: Any) -> None:
            pass

    act = DummySessionActions()
    act.refresh_detail("sync")
    assert "off" in act.sync_autostart_button.text()

    act._no_selected = True
    act.refresh_detail("sync")
    assert "Select a session" in act.sync_title.text()
    act._no_selected = False

    act.edit_session("")

    with patch.object(QMessageBox, "information") as mock_info:
        act.edit_session("non_existent_id")
        assert mock_info.called

    act.toggle_favorite("sync")

    with patch(
        "mutaui.ui.controllers.session_actions_controller.write_settings",
        side_effect=OSError("Disk full"),
    ):
        act.toggle_favorite("sync")
        assert any("Disk full" in e for e in act.errors)

    with patch.object(act, "selected_session", return_value=None):
        act.export_session_json("sync")
        act.copy_session_paths("sync")

    act.copy_session_paths("sync")
    act.copy_session_paths("forward")

    act.session_context_menu("sync", QPoint(-1, -1))


def test_coverage_gap_closers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _get_app()
    import connection_profiles
    import forward_configuration
    import sync_configuration

    # 1. sync_configuration socket arguments
    args = [
        "--socket-overwrite-mode=overwrite",
        "--socket-overwrite-mode-source=leave",
        "--socket-overwrite-mode-destination=overwrite",
        "--socket-owner-source=user1",
        "--socket-owner-destination=user2",
        "--socket-group-source=grp1",
        "--socket-group-destination=grp2",
        "--socket-permission-mode-source=0600",
        "--socket-permission-mode-destination=0660",
    ]
    eff = sync_configuration.build_effective_forward_configuration(None, command_arguments=args)
    assert eff.valid
    res_dict = eff.as_mapping()
    assert res_dict["source.socket.overwriteMode"] == "leave"
    assert res_dict["destination.socket.overwriteMode"] == "overwrite"
    assert res_dict["source.socket.owner"] == "user1"
    assert res_dict["destination.socket.owner"] == "user2"
    assert res_dict["source.socket.group"] == "grp1"
    assert res_dict["destination.socket.group"] == "grp2"
    assert res_dict["source.socket.permissionMode"] == "0600"
    assert res_dict["destination.socket.permissionMode"] == "0660"

    # sync_configuration OSError paths
    fake_unreadable = tmp_path / "unreadable.yml"
    with patch.object(Path, "read_bytes", side_effect=OSError("Read error")):
        fp, ok = sync_configuration.compute_global_config_fingerprint(fake_unreadable)
        assert fp == "unreadable" and not ok
        eff_err = sync_configuration.load_effective_forward_configuration(fake_unreadable, [])
        assert not eff_err.valid

    # 2. forward_configuration classifications & validations
    c1 = forward_configuration.classify_forward_listener("tcp:8080")
    assert c1.port is None and c1.host == "8080"
    c2 = forward_configuration.classify_forward_listener("tcp:localhost:notaport")
    assert c2.port is None and c2.is_loopback
    c3 = forward_configuration.classify_forward_listener("tcp:[::1]:8080")
    assert c3.is_loopback and c3.port == 8080
    c_empty = forward_configuration.classify_forward_listener("   ")
    assert c_empty.scope == "empty"
    c_other = forward_configuration.classify_forward_listener("custom://foobar")
    assert c_other.scope == "other"

    with pytest.raises(ValueError, match="octal string"):
        forward_configuration.validate_forward_proposal("source.socket.permissionMode", "999")
    with pytest.raises(ValueError, match="non-empty string"):
        forward_configuration.validate_forward_proposal("source.socket.owner", "")
    with pytest.raises(ValueError, match="Unsupported forwarding"):
        forward_configuration.validate_forward_proposal("unknown.key", "val")
    with pytest.raises(ValueError, match="Unsupported forwarding"):
        forward_configuration.ForwardConfigurationDraft({}).propose("unknown.key", "val")

    # 3. connection_profiles validation & load branches
    with pytest.raises(connection_profiles.ProfileStoreError, match="must be strings"):
        connection_profiles._clean_defaults("sync", {123: "val"})  # type: ignore

    with pytest.raises(connection_profiles.ProfileStoreError, match="supported fields"):
        connection_profiles._parse_profile({"id": "1", "unknown_field": True})

    with pytest.raises(connection_profiles.ProfileStoreError, match="Profile name"):
        connection_profiles._parse_profile(
            {"id": "1", "name": "", "kind": "sync", "endpoint_a": "a", "endpoint_b": "b"}
        )

    with pytest.raises(connection_profiles.ProfileStoreError, match="1–120 characters"):
        connection_profiles._parse_profile(
            {"id": "1", "name": "a" * 121, "kind": "sync", "endpoint_a": "a", "endpoint_b": "b"}
        )

    with pytest.raises(connection_profiles.ProfileStoreError, match="4096 characters"):
        connection_profiles._parse_profile(
            {"id": "1", "name": "n", "kind": "sync", "endpoint_a": "a" * 4097, "endpoint_b": "b"}
        )

    with pytest.raises(connection_profiles.ProfileStoreError, match="NUL"):
        connection_profiles._parse_profile(
            {"id": "1", "name": "n", "kind": "sync", "endpoint_a": "a\x00", "endpoint_b": "b"}
        )

    with pytest.raises(connection_profiles.ProfileStoreError, match="boolean"):
        connection_profiles._parse_profile(
            {
                "id": "1",
                "name": "n",
                "kind": "sync",
                "endpoint_a": "a",
                "endpoint_b": "b",
                "favorite": 1,
            }
        )

    store_file = tmp_path / "profiles.json"
    store_file.write_text(json.dumps({"schema_version": 1, "profiles": "not_a_list"}))
    res_load = connection_profiles.load_profile_store(store_file)
    assert not res_load.valid

    store_file.write_text(json.dumps({"schema_version": 999, "profiles": []}))
    res_load2 = connection_profiles.load_profile_store(store_file)
    assert not res_load2.valid

    store_file.write_text(json.dumps({"schema_version": "1", "profiles": []}))
    res_load_str = connection_profiles.load_profile_store(store_file)
    assert not res_load_str.valid

    # posix save branch
    valid_store_file = tmp_path / "valid_profiles.json"
    prof = connection_profiles.ConnectionProfile(
        id="p1",
        name="Prof1",
        kind="sync",
        endpoint_a="a",
        endpoint_b="b",
        favorite=False,
        tags=(),
        defaults={},
        created_at="now",
        updated_at="now",
    )
    store = connection_profiles.ConnectionProfileStore(valid_store_file)
    orig_open = os.open

    def mock_fsync_open(path, flags, *args):
        if str(path) == str(valid_store_file.parent):
            return 999
        return orig_open(path, flags, *args)

    with (
        patch("connection_profiles.os.name", "posix"),
        patch("connection_profiles.os.open", side_effect=mock_fsync_open),
        patch("connection_profiles.os.fsync"),
        patch("connection_profiles.os.close"),
    ):
        store._save([prof])

    # 4. SettingsBundleMixin branches
    from mutaui.ui.controllers.settings_bundle_controller import SettingsBundleMixin

    class DummyBundle(SettingsBundleMixin):
        def __init__(self) -> None:
            self.client = SimpleNamespace(binary=None)
            self.action_planner = None

    db = DummyBundle()
    with patch("mutaui.ui.settings_migration.migrate_local_settings") as mock_mig:
        db.migrate_current_settings()
        assert mock_mig.called

    with patch("mutaui.ui.settings_migration.rollback_local_settings_migration") as mock_rb:
        db.rollback_current_settings_migration()
        assert mock_rb.called

    with patch(
        "mutaui.ui.controllers.settings_bundle_controller.SSHProfileManagerDialog"
    ) as mock_ssh_dlg:
        mock_ssh_dlg.return_value.exec = MagicMock()
        db.manage_ssh_profiles()
        assert mock_ssh_dlg.called

    with (
        patch(
            "mutaui.ui.controllers.settings_bundle_controller.NativeProjectManagerDialog",
            side_effect=OSError("Proj error"),
        ),
        patch.object(QMessageBox, "warning") as mock_warn,
    ):
        db.manage_native_projects()
        assert mock_warn.called

    # 5. SessionTableMixin & MonitoringMixin edge branches
    from PySide6.QtCore import QModelIndex

    from mutaui.ui.controllers.monitoring_controller import MonitoringMixin
    from mutaui.ui.controllers.session_table_controller import SessionTableMixin

    class DummyTable(SessionTableMixin, MonitoringMixin):
        def __init__(self) -> None:
            self.pending_poll = True
            self.refresh = MagicMock()
            self._pending_launch_requests = []
            self.current_kind = "sync"
            self.current_id = ""
            self.conf = {"alerts": False}
            self.tray = SimpleNamespace(isVisible=lambda: False)
            self.add_log = MagicMock()

    dt = DummyTable()
    dt.session_double_click("sync", QModelIndex())
    dt.dashboard_select(QModelIndex())
    dt._start_initial_refresh()
    assert not dt.refresh.called
    delivered, alert_msg = dt.send_test_alert()
    assert not delivered
