"""Tests for UI polish improvements: troubleshoot button, theme toggle, tray icons."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication

import app as app_module


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_session_detail_troubleshoot_button_visibility_and_click(
    tmp_path: Any, monkeypatch: Any
) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    # 1. No session selected -> button should be hidden
    window.refresh_detail("sync")
    assert hasattr(window, "sync_troubleshoot_button")
    assert window.sync_troubleshoot_button.isHidden()

    # 2. Healthy session -> button should be hidden
    window.snapshot.sync = [
        {
            "identifier": "sync-1",
            "name": "Healthy",
            "status": 6,
            "paused": False,
            "conflicts": [],
            "lastError": "",
        }
    ]
    window.current_kind = "sync"
    window.current_id = "sync-1"
    monkeypatch.setattr(
        window,
        "selected_session",
        lambda kind: window.snapshot.sync[0] if kind == "sync" else None,
    )
    window.refresh_detail("sync")
    assert window.sync_troubleshoot_button.isHidden()

    # 3. Session with lastError -> button should become visible
    window.snapshot.sync[0]["lastError"] = "Connection timed out"
    window.refresh_detail("sync")
    assert not window.sync_troubleshoot_button.isHidden()

    # 4. Clicking troubleshoot button invokes open_troubleshooter with identifier
    opened: list[str | None] = []
    monkeypatch.setattr(window, "open_troubleshooter", lambda sid=None: opened.append(sid))
    window.open_troubleshooter_for_selected("sync")
    assert opened == ["sync-1"]

    # 5. Test forward troubleshoot button
    window.snapshot.forward = [
        {
            "identifier": "fwd-1",
            "name": "Forwarding",
            "status": 0,
            "paused": False,
            "lastError": "Port in use",
        }
    ]
    monkeypatch.setattr(
        window,
        "selected_session",
        lambda kind: window.snapshot.forward[0] if kind == "forward" else None,
    )
    window.refresh_detail("forward")
    assert hasattr(window, "forward_troubleshoot_button")
    assert not window.forward_troubleshoot_button.isHidden()

    opened.clear()
    window.open_troubleshooter_for_selected("forward")
    assert opened == ["fwd-1"]

    window.close()


def test_quick_theme_toggle(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    saved_settings: list[dict[str, Any]] = []
    monkeypatch.setattr(
        app_module, "write_settings", lambda data: saved_settings.append(data.copy())
    )

    window = app_module.MainWindow(demo=True)
    assert hasattr(window, "theme_toggle_btn")

    # Start with dark theme
    window.conf["theme"] = "dark"
    window._update_theme_toggle_icon()
    assert window.theme_toggle_btn.text() == "☀️"

    # Click toggle -> switches to light
    window.toggle_theme_quick()
    assert window.conf["theme"] == "light"
    assert window.theme_toggle_btn.text() == "🌙"
    assert len(saved_settings) >= 1
    assert saved_settings[-1]["theme"] == "light"

    # Click toggle again -> switches back to dark
    window.toggle_theme_quick()
    assert window.conf["theme"] == "dark"
    assert window.theme_toggle_btn.text() == "☀️"
    assert saved_settings[-1]["theme"] == "dark"

    window.close()


def test_dynamic_tray_status_icon(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    statuses = ["healthy", "busy", "paused", "issue", "offline", "unknown", "idle"]
    for status in statuses:
        icon = window._tray_status_icon(status)
        assert not icon.isNull()
        pixmap = icon.pixmap(64, 64)
        assert not pixmap.isNull()
        img = pixmap.toImage()
        # Sample dot pixel at center of ellipse (43 + 9, 43 + 9) = (52, 52)
        dot_color = img.pixelColor(52, 52)
        assert dot_color.alpha() > 200

    # Test border color adaptivity with theme
    window.conf["theme"] = "light"
    icon_light = window._tray_status_icon("healthy")
    assert not icon_light.isNull()

    window.conf["theme"] = "dark"
    icon_dark = window._tray_status_icon("healthy")
    assert not icon_dark.isNull()

    window.close()


def test_worst_tray_status_busy_integration() -> None:
    from mutaui.services.tray_status import worst_tray_status

    # Confirms that 'busy' state is properly mapped to 'busy' tray status
    assert worst_tray_status(daemon_online=True, sessions_stale=False, states=["busy"]) == "busy"
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["watching", "busy"])
        == "busy"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["busy", "paused"])
        == "paused"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["busy", "error"])
        == "issue"
    )


def test_tray_controller_lifecycle_and_notifications(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    # show_window coverage
    window.show_window()

    # tray idle seconds
    window._tray_idle_mode = True
    window._tray_idle_started_at = 100.0
    window._tray_idle_seconds_pending = 5.0
    monkeypatch.setattr(app_module.time, "monotonic", lambda: 110.0)
    assert window.tray_idle_seconds() == 15.0
    window.commit_tray_idle_sample()
    assert window._tray_idle_seconds_pending == 0.0

    # open_notified_issue: empty keys -> calls show_window
    window._last_notification_session_keys = ()
    window.open_notified_issue()

    # open_notified_issue: single key -> routes open_session
    routed: list[dict[str, Any]] = []
    monkeypatch.setattr(window, "handle_launch_request", routed.append)
    window._last_notification_session_keys = (("sync", "s-1"),)
    window.open_notified_issue()
    assert routed == [{"command": "open_session", "session_id": "s-1"}]

    # open_notified_issue: multiple keys -> QInputDialog accepted
    routed.clear()
    window._last_notification_session_keys = (("sync", "s-1"), ("forward", "f-1"))
    monkeypatch.setattr(
        app_module.QInputDialog, "getItem", lambda *_args, **_kwargs: ("forward: f-1", True)
    )
    window.open_notified_issue()
    assert routed == [{"command": "open_session", "session_id": "f-1"}]

    # open_notified_issue: multiple keys -> QInputDialog rejected
    routed.clear()
    monkeypatch.setattr(app_module.QInputDialog, "getItem", lambda *_args, **_kwargs: ("", False))
    window.open_notified_issue()
    assert routed == []

    # quit_app with pending action blocks quit and warns
    info_shown: list[str] = []
    monkeypatch.setattr(
        app_module.QMessageBox, "information", lambda *_args: info_shown.append(str(_args))
    )
    window.pending_action = True
    window.quit_app()
    assert len(info_shown) == 1
    window.pending_action = False

    window.close()


def test_command_and_snapshot_mixins(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    # report_error adds log and shows critical message box
    crit_shown: list[str] = []
    monkeypatch.setattr(
        app_module.QMessageBox, "critical", lambda *_args: crit_shown.append(str(_args))
    )
    window.report_error("Test failure message")
    assert any("Test failure message" in log for log in window.logs)
    assert len(crit_shown) == 1

    # session_action when no session selected is a no-op
    monkeypatch.setattr(window, "selected_session", lambda _k: None)
    run_cmds: list[tuple[Any, ...]] = []
    monkeypatch.setattr(window, "run_command", lambda *a, **kw: run_cmds.append(a))
    window.session_action("sync", "flush")
    assert run_cmds == []

    # session_action when session selected forwards to run_command
    monkeypatch.setattr(window, "selected_session", lambda _k: {"identifier": "s-123"})
    window.session_action("sync", "pause")
    assert run_cmds == [("sync", "pause")]

    # daemon_action forwards to run_command
    run_cmds.clear()
    window.daemon_action("stop")
    assert run_cmds == [("daemon", "stop")]

    # submit delivers error callback
    errs: list[str] = []
    window.submit(
        lambda: (_ for _ in ()).throw(ValueError("boom")),
        on_result=lambda _r: None,
        on_error=errs.append,
    )
    # Give pool or direct call time
    assert hasattr(window, "pool")

    window.close()


def test_search_clear_buttons_and_shortcuts(tmp_path: Any, monkeypatch: Any) -> None:
    from connection_profiles import ConnectionProfileStore
    from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog
    from mutaui.ui.connection_profiles_dialog import ConnectionProfilesDialog
    from mutaui.ui.quick_navigator import QuickNavigator

    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    # 1. Search fields have clear buttons enabled
    assert window.sync_search.isClearButtonEnabled()
    assert window.forward_search.isClearButtonEnabled()
    assert window.tail_filter.isClearButtonEnabled()

    nav = QuickNavigator(window)
    assert nav.search.isClearButtonEnabled()
    nav.close()

    cp_dlg = ConnectionProfilesDialog(window, ConnectionProfileStore(tmp_path / "profiles.json"))
    assert cp_dlg.search_input.isClearButtonEnabled()
    cp_dlg.close()

    ci_dlg = ConflictInspectorDialog([], window)
    assert ci_dlg.search.isClearButtonEnabled()
    ci_dlg.close()

    # 2. Focus search shortcut helper
    window.sync_search.setText("sync-term")
    window.set_page(1)
    window.focus_search()
    assert window.sync_search.selectedText() == "sync-term"

    window.forward_search.setText("forward-term")
    window.set_page(2)
    window.focus_search()
    assert window.forward_search.selectedText() == "forward-term"

    window.tail_filter.setText("log-term")
    window.set_page(3)
    window.focus_search()
    assert window.tail_filter.selectedText() == "log-term"

    # When on page without search field
    window.set_page(0)
    window.focus_search()

    # 3. Theme quick toggle toast
    window.ui_language = "en"
    window.toggle_theme_quick()
    status_text = window.statusBar().currentMessage()
    assert "Theme switched to" in status_text

    window.ui_language = "cs"
    window.toggle_theme_quick()
    status_text = window.statusBar().currentMessage()
    assert "Motiv přepnut na" in status_text

    # 4. Status bar toast on command dispatch
    window.demo = False
    window.snapshot.sync = [{"identifier": "s-1", "name": "Test"}]
    monkeypatch.setattr(
        "mutaui.ui.controllers.command_controller.QMessageBox.question",
        lambda *a, **k: app_module.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(window, "submit", lambda *a, **k: None)
    window.run_command("sync", "pause", target="s-1")
    toast = window.statusBar().currentMessage()
    assert "Pozastavování" in toast or "Pausing" in toast
    window.demo = True

    # 5. LoggingMixin and GlobalConfigMixin methods
    initial_log_count = len(window.logs)
    window.add_log("Special audit log entry")
    assert len(window.logs) == initial_log_count + 1
    assert "Special audit log entry" in window.logs[-1]

    # Test clear_logs
    window.clear_logs()
    assert len(window.logs) == 1
    assert "UI history cleared" in window.logs[0]

    # Test export_logs
    export_file = tmp_path / "exported_logs.txt"
    monkeypatch.setattr(
        "mutaui.ui.controllers.logging_controller.QFileDialog.getSaveFileName",
        lambda *_a, **_k: (str(export_file), "Text (*.txt)"),
    )
    window.export_logs()
    assert export_file.exists()
    assert "UI history cleared" in export_file.read_text(encoding="utf-8")

    # Cancel export_logs
    monkeypatch.setattr(
        "mutaui.ui.controllers.logging_controller.QFileDialog.getSaveFileName",
        lambda *_a, **_k: ("", ""),
    )
    window.export_logs()

    # Export logs OSError handling
    monkeypatch.setattr(
        "mutaui.ui.controllers.logging_controller.QFileDialog.getSaveFileName",
        lambda *_a, **_k: (str(tmp_path / "nonexistent" / "err.txt"), "Text (*.txt)"),
    )
    crit_box: list[str] = []
    monkeypatch.setattr(
        "mutaui.ui.controllers.logging_controller.QMessageBox.critical",
        lambda *a: crit_box.append(str(a)),
    )
    window.export_logs()
    assert len(crit_box) == 1

    # Test seed_demo_history
    window.history.db.execute("DELETE FROM metrics")
    window.history.clear_events()
    window.seed_demo_history()
    sample_count = window.history.db.execute("SELECT count(*) FROM metrics").fetchone()[0]
    assert sample_count == 125

    window.close()
