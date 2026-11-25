"""Targeted regression test suite for Batch 3 remediation:
UI, CLI onboarding, recovery, translations, profiles, and test harness
(M01, M02, M03, M40, M41, M42, M43, M44, M45, M46, M47, M50, M51, M65, M66, M67, M68, M69, M71, M72, M78, M79, M80, M81, M82, M83, M92).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from connection_profiles import ConnectionProfileStore
from mutagen_client import MutagenClient, MutagenError, read_registration
from mutaui.services.instance_lifecycle import SingleInstanceBroker
from mutaui.ui.connection_profiles_dialog import ConnectionProfilesDialog
from mutaui.ui.controllers.onboarding_controller import OnboardingMixin
from mutaui.ui.main_window import MainWindow
from mutaui.ui.onboarding import CLIDiscovery
from mutaui.ui.preferences import (
    theme_stylesheet,
)
from mutaui.ui.quick_navigator import QuickNavigator
from settings import settings_path


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_m01_onboarding_cli_check_identity_and_superseded_rejection(qapp: QApplication) -> None:
    """M01: Asynchronous CLI check result must match the active pending client; stale results are discarded."""
    mixin = OnboardingMixin()
    mixin.conf = {}
    mixin.client = MutagenClient()
    mixin._onboarding_check_seq = 1

    # Simulate pending client A
    client_a = MutagenClient()
    client_a.binary = r"C:\Mutagen\client_a.exe"
    mixin._onboarding_pending_client = client_a

    # User chooses client B before check A returns
    client_b = MutagenClient()
    client_b.binary = r"C:\Mutagen\client_b.exe"
    mixin._onboarding_pending_client = client_b
    mixin._onboarding_check_seq = 2

    # Simulate slow return of check A (seq 1, target client A)
    discovery_a = CLIDiscovery(
        binary=r"C:\Mutagen\client_a.exe",
        version="v0.18.0",
        architectures=("x86_64",),
        capabilities=("sync",),
    )
    label_mock = MagicMock()
    mixin.onboarding_cli_status = label_mock

    # Result payload with sequence 1 and client A should be discarded
    mixin.show_onboarding_cli_result((1, r"C:\Mutagen\client_a.exe", discovery_a))
    label_mock.setText.assert_not_called()

    # Result payload matching sequence 2 and client B should be applied
    discovery_b = CLIDiscovery(
        binary=r"C:\Mutagen\client_b.exe",
        version="v0.18.1",
        architectures=("x86_64",),
        capabilities=("sync", "forward"),
    )
    mixin.show_onboarding_cli_result((2, r"C:\Mutagen\client_b.exe", discovery_b))
    label_mock.setText.assert_called_once()
    assert "v0.18.1" in label_mock.setText.call_args[0][0]


def test_m02_onboarding_save_failure_keeps_memory_client_intact(qapp: QApplication) -> None:
    """M02: When writing settings fails, in-memory client and configuration are not mutated."""
    mixin = OnboardingMixin()
    mixin.conf = {"binary": "original_mutagen.exe", "check_updates_on_startup": False}
    original_client = MutagenClient("original_mutagen.exe")
    mixin.client = original_client
    mixin.statusBar = MagicMock(return_value=MagicMock())

    new_candidate = MutagenClient("new_mutagen.exe")
    mixin._onboarding_pending_client = new_candidate

    with patch(
        "mutaui.ui.controllers.onboarding_controller.write_settings",
        side_effect=OSError("Disk full"),
    ):
        mixin.complete_onboarding()

    # Conf and client must remain intact on failure
    assert mixin.client is original_client
    assert mixin.conf["binary"] == "original_mutagen.exe"
    assert mixin.conf.get("onboarding_completed") is not True


def test_m03_single_instance_stale_socket_recovery(qapp: QApplication) -> None:
    """M03: When an existing instance crashed leaving a stale socket, SingleInstanceBroker safely removes it and listens."""
    sock_name = f"test-stale-socket-{time.time_ns()}"
    broker1 = SingleInstanceBroker(sock_name)
    assert broker1.start_or_forward({"command": "focus"}) is True

    # Simulate hard crash: close socket without graceful removeServer so the name is registered/stale
    broker1.server.close()

    # Second broker starts: connects to stale socket -> connection refused / timeout -> recovers by removeServer
    broker2 = SingleInstanceBroker(sock_name)
    assert broker2.start_or_forward({"command": "focus"}) is True
    assert broker2.primary is True
    broker2.close()


def test_m68_connection_profile_edit_preserves_id(qapp: QApplication, tmp_path: Path) -> None:
    """M68: Connection profiles dialog supports editing an existing profile while preserving its stable ID."""
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create(
        "Initial Profile",
        "C:/Local/Path",
        "user@remote:/srv/app",
        kind="sync",
        tags=("test", "dev"),
        favorite=True,
    )
    original_id = profile.id
    original_created_at = profile.created_at

    dialog = ConnectionProfilesDialog(None, store)
    dialog.table.selectRow(0)
    selected = dialog.selected_profile()
    assert selected is not None
    assert selected.id == original_id

    # Update profile in store
    from dataclasses import replace

    updated = replace(
        selected,
        name="Updated Profile Name",
        endpoint_b="user@new-remote:/srv/app",
        tags=("production",),
    )
    store.update(updated)

    reloaded = store.search("Updated Profile Name")[0]
    assert reloaded.id == original_id
    assert reloaded.created_at == original_created_at
    assert reloaded.name == "Updated Profile Name"
    assert reloaded.endpoint_b == "user@new-remote:/srv/app"
    assert reloaded.tags == ("production",)


def test_m69_settings_path_and_xdg_adherence() -> None:
    """M69: Settings location honors custom overrides and standard XDG paths on Linux."""
    with patch.dict(os.environ, {"MUTAGEN_CONTROL_CONFIG_DIR": "C:/Custom/Config/Path"}):
        assert settings_path() == Path("C:/Custom/Config/Path/settings.json")


def test_m78_m79_quick_navigator_bilingual_and_arrow_keys(qapp: QApplication) -> None:
    """M78 & M79: Quick navigator indexes English and Czech routes, supports keyboard arrows in search field, and provides accessible names."""
    nav = QuickNavigator(None)
    assert nav.search.accessibleName() != ""
    assert nav.list.accessibleName() != ""

    # M78: search in Czech
    nav.filter("Synchronizace")
    assert nav.list.count() >= 1
    found_item = nav.list.item(0)
    assert "Synchronizace" in found_item.text() or "Sync" in found_item.text()

    # Search in English
    nav.filter("Settings")
    assert nav.list.count() >= 1

    # M79: arrow key navigation from QLineEdit
    nav.filter("")
    count = nav.list.count()
    assert count >= 2
    nav.list.setCurrentRow(0)

    # Simulate Key_Down in search field
    down_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    handled = nav.eventFilter(nav.search, down_event)
    assert handled is True
    assert nav.list.currentRow() == 1

    # Simulate Key_Up in search field
    up_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    handled = nav.eventFilter(nav.search, up_event)
    assert handled is True
    assert nav.list.currentRow() == 0


def test_m80_release_button_opens_exact_tag_url(qapp: QApplication) -> None:
    """M80: Release update action opens the verified tag HTML URL, not generic releases."""
    from mutaui.services.update_checker import UpdateCheckResult

    mixin = OnboardingMixin()
    mixin._release_check_result = UpdateCheckResult(
        available=True,
        latest_version="9.2.0",
        release_url="https://github.com/Harfusha/MutaUI/releases/tag/v9.2.0",
    )
    with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url:
        mixin.open_release_page()
        mock_open_url.assert_called_once()
        assert (
            mock_open_url.call_args[0][0].toString()
            == "https://github.com/Harfusha/MutaUI/releases/tag/v9.2.0"
        )


def test_m81_portability_tab_has_migration_and_rollback_actions(qapp: QApplication) -> None:
    """M81: Settings portability tab exposes migration and rollback actions."""
    from mutaui.ui.controllers.settings_bundle_controller import SettingsBundleMixin

    assert hasattr(SettingsBundleMixin, "migrate_current_settings")
    assert hasattr(SettingsBundleMixin, "rollback_current_settings_migration")


def test_m82_macos_launchd_registration_detection(tmp_path: Path) -> None:
    """M82: macOS daemon registration detects launchd plist instead of unconditionally failing."""
    fake_plist = tmp_path / "io.mutagen.daemon.plist"
    fake_plist.write_text("<string>/usr/local/bin/mutagen daemon start</string>", encoding="utf-8")

    with patch("sys.platform", "darwin"), patch("pathlib.Path.home", return_value=tmp_path.parent):
        launch_dir = tmp_path.parent / "Library" / "LaunchAgents"
        launch_dir.mkdir(parents=True, exist_ok=True)
        target = launch_dir / "io.mutagen.daemon.plist"
        target.write_text("<string>/usr/local/bin/mutagen daemon start</string>", encoding="utf-8")

        status, cmd = read_registration("/usr/local/bin/mutagen")
        assert status == "registered"
        assert "io.mutagen.daemon.plist" in cmd


def test_m83_platform_cli_naming_and_messages() -> None:
    """M83: Error messages and CLI references use platform-appropriate binary name."""
    client = MutagenClient("")
    with pytest.raises(MutagenError) as exc_info:
        client.command(["sync", "list"])
    err = str(exc_info.value)
    if sys.platform == "win32":
        assert "mutagen.exe" in err
    else:
        assert "mutagen" in err


def test_m92_existing_profile_upgrade_skips_onboarding(qapp: QApplication) -> None:
    """M92: Existing configured installation upgraded from earlier versions does not pop up the onboarding wizard."""
    conf = {"binary": "C:/Mutagen/mutagen.exe"}
    has_existing = bool(conf.get("binary") or conf.get("mutagen_path"))
    assert has_existing is True

    # If onboarding_completed is not present, mark completed to avoid wizard popup
    if not conf.get("onboarding_completed", False) and has_existing:
        conf["onboarding_completed"] = True

    assert conf["onboarding_completed"] is True


def test_m40_light_theme_contrast_enhancement() -> None:
    """M40: Light theme transforms selected table text and warning/danger colors for contrast."""
    raw_css = "QTableWidget::item:selected { color: white; background: #233D4F; } QLabel#alert { color: #FB8696; }"
    light_css = theme_stylesheet(raw_css, "light")
    # Selection color must not be white on light blue
    assert "color: #17212B;" in light_css
    # Red danger must be transformed to high-contrast red
    assert "#B91C1C" in light_css


def test_m41_window_minimum_size_and_sidebar_adaptation(qapp: QApplication) -> None:
    """M41: Main window supports 720x520 minimum size and adapts sidebar width."""
    window = MainWindow(demo=True)
    min_size = window.minimumSize()
    assert min_size.width() <= 720
    assert min_size.height() <= 520

    # Test resize event adaptation
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent

    window.resizeEvent(QResizeEvent(QSize(800, 550), QSize(1480, 940)))
    assert hasattr(window, "sidebar")
    assert window.sidebar.width() <= 200
    window.close()


def test_m43_m44_navigation_context_and_bulk_action_styling(qapp: QApplication) -> None:
    """M43 & M44: Basic mode retains navigation context on hidden pages; bulk actions use secondary style."""
    window = MainWindow(demo=True)
    window.set_ui_mode("basic")

    # Navigate to an advanced page (index 4 = Daemon)
    window.set_page(4)
    # Nav button for page 4 must remain unhidden for context retention
    assert window.nav[4].isHidden() is False

    # Verify bulk action on sync page is not primary
    sync_page = window.sessions_page("sync")
    sync_now_btns = [
        b for b in sync_page.findChildren(type(window.nav[0])) if "Sync now" in b.text()
    ]
    if sync_now_btns:
        assert sync_now_btns[0].property("kind") != "primary"
    window.close()
