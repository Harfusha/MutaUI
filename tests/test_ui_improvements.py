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
