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

    # Test Ctrl+D troubleshooter shortcut
    from PySide6.QtGui import QShortcut

    shortcuts = window.findChildren(QShortcut)
    ctrl_d = next((s for s in shortcuts if s.key().toString() == "Ctrl+D"), None)
    assert ctrl_d is not None
    troubleshoot_called: list[bool] = []
    monkeypatch.setattr(window, "open_troubleshooter", lambda *a: troubleshoot_called.append(True))
    ctrl_d.activated.emit()
    assert troubleshoot_called == [True]

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


def test_main_window_import_locations() -> None:
    from app import MainWindow as MW1
    from mutaui.ui.main_window import MainWindow as MW2

    assert MW1 is MW2


def test_session_context_menu_and_copy_paths(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)
    window.set_page(1)

    from PySide6.QtCore import QPoint

    # 1. Right click on empty point -> nothing selected, no crash
    window.session_context_menu("sync", QPoint(9999, 9999))

    # 2. Add sample session and select
    window.snapshot.sync = [
        {
            "identifier": "sync-123",
            "name": "alpha-sync",
            "status": 6,
            "paused": False,
            "alpha": {"path": "/local/dir"},
            "beta": {"path": "/remote/dir"},
        }
    ]
    window.apply_snapshot(window.snapshot)

    # Test copy_session_paths for sync
    monkeypatch.setattr(window, "selected_session", lambda kind: window.snapshot.sync[0])
    window.copy_session_paths("sync")
    from PySide6.QtWidgets import QApplication

    assert QApplication.clipboard().text() == "/local/dir <-> /remote/dir"

    # Test copy_session_paths for forward
    fwd_sess = {
        "identifier": "fwd-456",
        "name": "my-fwd",
        "source": "tcp:localhost:8080",
        "destination": "tcp:remote:8080",
    }
    monkeypatch.setattr(window, "selected_session", lambda kind: fwd_sess)
    window.copy_session_paths("forward")
    assert QApplication.clipboard().text() == "tcp:localhost:8080 -> tcp:remote:8080"

    # Test context menu creation with menu mock
    actions_added: list[tuple[str, Any]] = []

    class DummyMenu:
        def addAction(self, text: str, callback: Any = None) -> None:
            actions_added.append((text, callback))

        def addSeparator(self) -> None:
            pass

        def exec(self, pos: Any) -> None:
            pass

    monkeypatch.setattr(app_module, "QMenu", lambda *a: DummyMenu())
    monkeypatch.setattr(
        "mutaui.ui.controllers.session_actions_controller.QMenu", lambda *a: DummyMenu()
    )
    monkeypatch.setattr(
        window.sync_table, "indexAt", lambda pt: window.sync_table.model().index(0, 0)
    )
    window.session_context_menu("sync", QPoint(10, 10))
    action_names = [a[0] for a in actions_added]
    assert any("Copy Path" in a or "Cesty" in a for a in action_names)
    assert any("Copy ID" in a or "ID" in a for a in action_names)

    window.close()


def test_session_dialog_initial_path(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    sample_dir = tmp_path / "my_project"
    sample_dir.mkdir()
    from mutaui.ui.session_dialog import SessionDialog

    dlg = SessionDialog("sync", initial_path=str(sample_dir))
    assert dlg.a.text() == str(sample_dir)
    assert dlg.name.text() == "my_project"
    dlg.close()


def test_main_window_drag_and_drop(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    folder = tmp_path / "dropped_folder"
    folder.mkdir()

    from PySide6.QtCore import QMimeData, QUrl

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder))])

    accepted: list[str] = []

    class DummyDragEvent:
        def __init__(self, data: QMimeData) -> None:
            self._data = data

        def mimeData(self) -> QMimeData:
            return self._data

        def acceptProposedAction(self) -> None:
            accepted.append("proposed")

        def ignore(self) -> None:
            accepted.append("ignored")

    dummy_event = DummyDragEvent(mime)
    window.dragEnterEvent(dummy_event)  # type: ignore[arg-type]
    assert accepted == ["proposed"]

    accepted.clear()
    window.dragMoveEvent(dummy_event)  # type: ignore[arg-type]
    assert accepted == ["proposed"]

    import os

    created: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        window,
        "create_session",
        lambda kind, initial_path=None: created.append((kind, initial_path)),
    )
    window.dropEvent(dummy_event)  # type: ignore[arg-type]
    assert created == [("sync", os.path.normpath(str(folder)))]
    assert window.pages.currentIndex() == 1

    # Test non-directory file rejected
    non_dir = tmp_path / "file.txt"
    non_dir.write_text("hello", encoding="utf-8")
    mime2 = QMimeData()
    mime2.setUrls([QUrl.fromLocalFile(str(non_dir))])
    dummy_event2 = DummyDragEvent(mime2)
    accepted.clear()
    window.dragEnterEvent(dummy_event2)  # type: ignore[arg-type]
    assert accepted == ["ignored"]

    window.close()


def test_troubleshooter_diagnostic_report_export(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    from datetime import UTC, datetime

    from mutaui.adapters.mutagen_snapshot import from_legacy_session
    from mutaui.domain.models import DiagnosticIssue
    from mutaui.ui.troubleshooter_dialog import TroubleshooterDialog

    raw = {
        "identifier": "sync-test",
        "name": "TestSync",
        "status": 0,
        "lastError": "agent incompatible",
        "alpha": {"path": "C:\\repo"},
        "beta": {"path": "/var/www"},
    }
    sess = from_legacy_session("sync", raw, measured_at=datetime.now(UTC))
    issue = DiagnosticIssue(
        code="agent_incompatible",
        severity="error",
        confidence=0.98,
        evidence=(),
        cause="version mismatch",
        suggested_actions=("upgrade",),
        can_auto_fix=False,
        source_version="0.18.1",
        certainty="confirmed",
        explanation="Mutagen agent version mismatch",
        technical_detail="remote agent 0.17 != local 0.18",
        article_url="",
        session_identifier="sync-test",
        observed_at=datetime.now(UTC),
    )

    class MockReport:
        def __init__(self, issues: list[DiagnosticIssue]) -> None:
            self.issues = tuple(issues)

        def issues_for_session(self, sid: str) -> list[DiagnosticIssue]:
            return [i for i in self.issues if i.session_identifier == sid]

        def unassociated_issues(self) -> list[DiagnosticIssue]:
            return []

    dlg = TroubleshooterDialog([sess], MockReport([issue]), selected_identifier="sync-test")  # type: ignore[arg-type]

    # 1. Test markdown report generation
    md_report = dlg._generate_diagnostic_report("markdown")
    assert "# MutaUI Diagnostic Report" in md_report
    assert "TestSync" in md_report

    # 2. Test JSON report generation
    import json

    json_report = dlg._generate_diagnostic_report("json")
    data = json.loads(json_report)
    assert data["session"]["identifier"] == "sync-test"
    assert len(data["issues"]) == 1
    assert data["issues"][0]["code"] == "agent_incompatible"

    # 3. Test export button and file dialog for markdown
    target_md = tmp_path / "report.md"
    monkeypatch.setattr(
        "mutaui.ui.troubleshooter_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target_md), "Markdown (*.md)"),
    )
    dlg._export_diagnostic_report()
    assert target_md.exists()
    assert "# MutaUI Diagnostic Report" in target_md.read_text(encoding="utf-8")

    # 4. Test export to JSON
    target_json = tmp_path / "report.json"
    monkeypatch.setattr(
        "mutaui.ui.troubleshooter_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target_json), "JSON (*.json)"),
    )
    dlg._export_diagnostic_report()
    assert target_json.exists()
    assert "sync-test" in target_json.read_text(encoding="utf-8")

    dlg.close()


def test_drag_and_drop_comprehensive(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    class MockMimeData:
        def __init__(self, urls: list[Any] | None = None) -> None:
            self._urls = urls

        def hasUrls(self) -> bool:
            return self._urls is not None

        def urls(self) -> list[Any]:
            return self._urls or []

    class MockUrl:
        def __init__(self, path: str, is_local: bool = True) -> None:
            self._path = path
            self._is_local = is_local

        def isLocalFile(self) -> bool:
            return self._is_local

        def toLocalFile(self) -> str:
            return self._path

    class MockDragEvent:
        def __init__(self, mime: MockMimeData) -> None:
            self._mime = mime
            self.accepted = False
            self.ignored = False

        def mimeData(self) -> MockMimeData:
            return self._mime

        def acceptProposedAction(self) -> None:
            self.accepted = True

        def ignore(self) -> None:
            self.ignored = True

    # 1. No URLs
    ev = MockDragEvent(MockMimeData(None))
    window.dragEnterEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    ev = MockDragEvent(MockMimeData(None))
    window.dragMoveEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    ev = MockDragEvent(MockMimeData(None))
    window.dropEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    # 2. Non-local URL
    non_local_url = MockUrl("http://example.com/dir", is_local=False)
    ev = MockDragEvent(MockMimeData([non_local_url]))
    window.dragEnterEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    ev = MockDragEvent(MockMimeData([non_local_url]))
    window.dragMoveEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    ev = MockDragEvent(MockMimeData([non_local_url]))
    window.dropEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    # 3. Local URL but is a file (not dir)
    file_path = tmp_path / "regular_file.txt"
    file_path.write_text("hello", encoding="utf-8")
    file_url = MockUrl(str(file_path), is_local=True)
    ev = MockDragEvent(MockMimeData([file_url]))
    window.dragEnterEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    ev = MockDragEvent(MockMimeData([file_url]))
    window.dragMoveEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    ev = MockDragEvent(MockMimeData([file_url]))
    window.dropEvent(ev)  # type: ignore[arg-type]
    assert ev.ignored and not ev.accepted

    # 4. Valid dir URL
    dir_path = tmp_path / "valid_folder"
    dir_path.mkdir()
    dir_url = MockUrl(str(dir_path), is_local=True)

    ev = MockDragEvent(MockMimeData([dir_url]))
    window.dragEnterEvent(ev)  # type: ignore[arg-type]
    assert ev.accepted and not ev.ignored

    ev = MockDragEvent(MockMimeData([dir_url]))
    window.dragMoveEvent(ev)  # type: ignore[arg-type]
    assert ev.accepted and not ev.ignored

    handled: list[str] = []
    monkeypatch.setattr(window, "handle_dropped_folder", lambda p: handled.append(p))
    ev = MockDragEvent(MockMimeData([dir_url]))
    window.dropEvent(ev)  # type: ignore[arg-type]
    assert ev.accepted and not ev.ignored
    assert len(handled) == 1

    window.close()


def test_main_window_theme_branches(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    # _update_theme_toggle_icon without button
    orig_btn = getattr(window, "theme_toggle_btn", None)
    del window.theme_toggle_btn
    window._update_theme_toggle_icon()
    if orig_btn is not None:
        window.theme_toggle_btn = orig_btn

    # toggle_theme_quick in czech with statusbar
    window.ui_language = "cs"
    window.toggle_theme_quick()
    assert window.conf.get("theme") in ("light", "dark")

    # toggle_theme_quick in english without statusbar
    window.ui_language = "en"
    monkeypatch.setattr(window, "statusBar", lambda: None)
    window.toggle_theme_quick()

    window.close()


def test_troubleshooter_export_report_edge_cases(tmp_path: Any, monkeypatch: Any) -> None:
    from datetime import UTC, datetime

    from mutaui.adapters.mutagen_snapshot import from_legacy_session
    from mutaui.domain.models import DiagnosticIssue
    from mutaui.ui.troubleshooter_dialog import TroubleshooterDialog

    raw = {
        "identifier": "sync-edge",
        "name": "EdgeSync",
        "status": 0,
        "lastError": "err",
        "alpha": {"path": "C:\\a"},
        "beta": {"path": "/b"},
    }
    sess = from_legacy_session("sync", raw, measured_at=datetime.now(UTC))

    class EmptyReport:
        def __init__(self) -> None:
            self.issues: tuple[Any, ...] = ()

        def issues_for_session(self, sid: str) -> list[DiagnosticIssue]:
            return []

        def unassociated_issues(self) -> list[DiagnosticIssue]:
            return []

    dlg = TroubleshooterDialog([sess], EmptyReport(), selected_identifier="sync-edge")  # type: ignore[arg-type]

    # Markdown generation with 0 issues in english and czech
    dlg._czech = False
    md_en = dlg._generate_diagnostic_report("markdown")
    assert "No active issues detected." in md_en

    dlg._czech = True
    md_cs = dlg._generate_diagnostic_report("markdown")
    assert "Nebyly zjištěny žádné aktivní problémy." in md_cs

    # Session not found in dialog._export_diagnostic_report
    monkeypatch.setattr(dlg.session_combo, "currentData", lambda: "nonexistent")
    dlg._export_diagnostic_report()

    # Cancelled file dialog (empty path)
    monkeypatch.setattr(dlg.session_combo, "currentData", lambda: "sync-edge")
    monkeypatch.setattr(
        "mutaui.ui.troubleshooter_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: ("", ""),
    )
    dlg._export_diagnostic_report()

    # OSError on file write triggers QMessageBox.critical
    critical_called: list[Any] = []
    monkeypatch.setattr(
        "mutaui.ui.troubleshooter_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(tmp_path / "bad.md"), "Markdown (*.md)"),
    )
    import builtins

    orig_open = builtins.open

    def bad_open(*args: Any, **kwargs: Any) -> Any:
        if "bad.md" in str(args[0]):
            raise OSError("Permission denied")
        return orig_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", bad_open)
    monkeypatch.setattr(
        "mutaui.ui.troubleshooter_dialog.QMessageBox.critical",
        lambda *a, **k: critical_called.append(a),
    )
    dlg._export_diagnostic_report()
    assert len(critical_called) == 1

    dlg.close()


def test_app_main_cli_branches(monkeypatch: Any) -> None:
    monkeypatch.setattr("sys.argv", ["app.py", "--version"])
    assert app_module.main() == 0

    monkeypatch.setattr("sys.argv", ["app.py", "--install-linux-file-manager"])
    monkeypatch.setattr("sys.platform", "win32")
    assert app_module.main() == 2

    monkeypatch.setattr("sys.argv", ["app.py", "--remove-linux-file-manager"])
    monkeypatch.setattr("sys.platform", "win32")
    assert app_module.main() == 2


def test_session_double_click_and_filter_status(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)
    window.apply_snapshot(window.snapshot)

    # 1. Double click on invalid index -> nothing happens
    from PySide6.QtCore import QModelIndex

    opened: list[str] = []
    monkeypatch.setattr(window, "open_session_preferences", lambda kind: opened.append(kind))
    window.session_double_click("sync", QModelIndex())
    assert opened == []

    # 2. Double click on valid row -> opens session preferences
    valid_index = window.sync_table.model().index(0, 0)
    window.session_double_click("sync", valid_index)
    assert opened == ["sync"]

    # 3. Filter table shows status bar message
    window.ui_language = "en"
    window.sync_search.setText("demo")
    window.filter_table("sync")
    assert "Showing" in window.statusBar().currentMessage()

    window.ui_language = "cs"
    window.filter_table("sync")
    assert "Zobrazeno" in window.statusBar().currentMessage()

    window.close()


def test_shortcuts_f1_and_ctrl_comma(tmp_path: Any, monkeypatch: Any) -> None:
    _app()
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.MainWindow(demo=True)

    nav_opened: list[bool] = []
    monkeypatch.setattr(window, "open_navigator", lambda: nav_opened.append(True))
    from PySide6.QtGui import QKeySequence, QShortcut

    # Find F1 shortcut
    f1_shortcuts = [s for s in window.findChildren(QShortcut) if s.key() == QKeySequence("F1")]
    assert len(f1_shortcuts) == 1
    f1_shortcuts[0].activated.emit()
    assert nav_opened == [True]

    # Find Ctrl+, shortcut
    settings_shortcuts = [
        s for s in window.findChildren(QShortcut) if s.key() == QKeySequence("Ctrl+,")
    ]
    assert len(settings_shortcuts) == 1
    settings_shortcuts[0].activated.emit()
    assert window.pages.currentIndex() == 5

    window.close()


def test_modern_adapters() -> None:
    from datetime import UTC, datetime

    from mutaui.adapters.cli_executor import MutagenCliExecutor
    from mutaui.adapters.mutagen_snapshot import from_session_dict

    raw = {
        "identifier": "mod-sync",
        "name": "Modern",
        "status": 0,
        "alpha": {"path": "C:\\a"},
        "beta": {"path": "/b"},
    }
    snap = from_session_dict("sync", raw, measured_at=datetime.now(UTC))
    assert snap.identity.identifier == "mod-sync"
    assert snap.identity.name == "Modern"

    class FakeClient:
        def command(self, args: list[str], *, timeout: int = 35, readonly: bool = False) -> str:
            return "ok"

    executor = MutagenCliExecutor(FakeClient())
    res = executor.run(["sync", "list"], timeout_seconds=10)
    assert res.stdout == "ok"
    assert res.returncode == 0


def test_button_metrics_prevent_descender_clipping() -> None:
    """Verify primary and standard buttons provide sufficient vertical height for font descenders."""
    app = _app()
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QPushButton, QStyle, QStyleOptionButton

    from mutaui.ui.styles.main_stylesheet import CSS

    app.setStyleSheet(CSS)

    btn = QPushButton("+ Create first sync session")
    btn.setObjectName("primary")
    btn.adjustSize()

    opt = QStyleOptionButton()
    opt.initFrom(btn)
    opt.text = btn.text()

    cr = btn.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, opt, btn)
    fm = QFontMetrics(btn.font())

    # Contents rect must be tall enough for font height plus descenders
    assert cr.height() >= 22
    assert cr.height() >= fm.height()
    # Button overall height must comfortably accommodate the font and vertical padding
    assert btn.sizeHint().height() >= 36


def test_empty_state_guided_onboarding_and_diagnostics_hub(monkeypatch: Any) -> None:
    """Verify empty states offer guided onboarding and diagnostics page has related tool links."""
    _app()
    from PySide6.QtWidgets import QFrame, QPushButton

    window = app_module.MainWindow(demo=True)
    window.set_page(1)

    empty_frame = window.findChild(QFrame, "syncEmptyStateFrame")
    assert empty_frame is not None

    buttons = empty_frame.findChildren(QPushButton)
    btn_texts = [b.text() for b in buttons]
    assert "+ Create first sync session" in btn_texts
    assert "Troubleshoot…" in btn_texts

    troubleshoot_clicked = []
    monkeypatch.setattr(
        window, "open_troubleshooter", lambda *_args: troubleshoot_clicked.append(True)
    )
    troubleshoot_btn = next(b for b in buttons if b.text() == "Troubleshoot…")
    troubleshoot_btn.click()
    assert troubleshoot_clicked == [True]

    # Test diagnostics page quick hub links
    window.set_page(7)
    diag_page = window.pages.widget(7)
    diag_buttons = diag_page.findChildren(QPushButton)
    diag_texts = [b.text() for b in diag_buttons]
    assert any("Daemon" in t for t in diag_texts)
    assert any("Action History" in t for t in diag_texts)
    assert any("Monitoring" in t for t in diag_texts)

    window.close()
