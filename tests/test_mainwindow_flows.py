"""Offline tests for GUI interactions and asynchronous refresh decisions."""

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QCloseEvent, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

import app as app_module
import mutaui.services.instance_lifecycle as instance_lifecycle


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    instance = app_module.MainWindow(demo=True)
    yield instance
    instance.timer.stop()
    instance.metric_timer.stop()
    instance.tail_timer.stop()
    instance._allow_exit = True
    instance.close()
    instance.history.close()


def test_quick_navigator_filters_words_and_selects_page(window):
    navigator = app_module.QuickNavigator(window)

    navigator.filter("ENDPOINT daemon")
    assert navigator.list.count() == 1
    assert navigator.list.item(0).data(app_module.Qt.ItemDataRole.UserRole) == 9

    navigator.choose()
    assert navigator.target == 9

    navigator.filter("no matching page")
    assert navigator.list.count() == 0
    navigator.target = None
    navigator.choose()
    assert navigator.target is None
    navigator.close()


def test_quick_navigator_exposes_commands_and_session_match(window):
    navigator = app_module.QuickNavigator(
        window,
        commands=[
            ("open_project", None, None, "Open native project", "mutagen yaml"),
            ("focus_session", "sync", "sync-123", "Focus sync: source", "source sync-123"),
            ("flush_session", "sync", "sync-123", "Flush sync: source", "source sync-123"),
        ],
    )

    navigator.filter("sync-123")
    assert navigator.list.count() == 2
    navigator.choose()
    assert navigator.command == ("focus_session", "sync", "sync-123")

    navigator.filter("open native project")
    assert navigator.list.count() == 1
    navigator.choose()
    assert navigator.command == ("open_project", None, None)
    navigator.close()


@pytest.mark.parametrize(
    ("kind", "table_name", "search_name", "state_name", "favorites_name"),
    [
        ("sync", "sync_table", "sync_search", "sync_state_filter", "sync_favorites_only"),
        (
            "forward",
            "forward_table",
            "forward_search",
            "forward_state_filter",
            "forward_favorites_only",
        ),
    ],
)
def test_focus_session_from_navigator_clears_filters_and_selects_row(
    window, monkeypatch, kind, table_name, search_name, state_name, favorites_name
):
    raw = getattr(window.snapshot, kind)[0]
    identifier = raw["identifier"]

    class Model:
        def row_for_identifier(self, candidate):
            return 3 if candidate == identifier else -1

        @staticmethod
        def index(row, column):
            return row, column

    class Table:
        def model(self):
            return Model()

        def selectRow(self, row):
            self.selected_row = row

        def scrollTo(self, index):
            self.scrolled_to = index

    table = Table()
    monkeypatch.setattr(window, table_name, table)
    monkeypatch.setattr(window, "set_page", lambda index: window.pages.setCurrentIndex(index))
    monkeypatch.setattr(window, "filter_table", lambda *_args: None)
    search = getattr(window, search_name)
    state_filter = getattr(window, state_name)
    favorites = getattr(window, favorites_name)
    search.setText("no-match")
    state_filter.setCurrentIndex(1)
    favorites.setChecked(True)
    if kind == "sync":
        window.sync_server_filter.setCurrentIndex(1)

    window.focus_session_from_navigator(kind, identifier)

    assert window.pages.currentIndex() == (1 if kind == "sync" else 2)
    assert search.text() == ""
    assert state_filter.currentIndex() == 0
    assert favorites.isChecked() is False
    assert table.selected_row == 3
    assert table.scrolled_to == (3, 0)
    if kind == "sync":
        assert window.sync_server_filter.currentIndex() == 0


@pytest.mark.parametrize(("kind", "identifier"), [("unknown", "sync-1"), ("sync", "")])
def test_focus_session_from_navigator_ignores_invalid_request(window, kind, identifier):
    current_page = window.pages.currentIndex()

    window.focus_session_from_navigator(kind, identifier)

    assert window.pages.currentIndex() == current_page


def test_focus_session_from_navigator_keeps_page_when_identifier_is_missing(window):
    window.focus_session_from_navigator("forward", "missing-session")

    assert window.pages.currentIndex() == 2
    assert window.forward_table.selectionModel().selectedRows() == []


@pytest.mark.parametrize(
    ("kind", "metric_key", "expected_index"),
    [
        ("sync", "all", 0),
        ("sync", "running", 3),
        ("forward", "paused", 4),
        ("forward", "errors", 5),
    ],
)
def test_open_metric_sessions_routes_to_correct_filter(window, kind, metric_key, expected_index):
    filters = window.sync_state_filter if kind == "sync" else window.forward_state_filter
    search = window.sync_search if kind == "sync" else window.forward_search
    favorites = window.sync_favorites_only if kind == "sync" else window.forward_favorites_only
    search.setText("no-match")
    favorites.setChecked(True)

    window.open_metric_sessions(kind, metric_key)

    assert window.pages.currentIndex() == (1 if kind == "sync" else 2)
    assert filters.currentIndex() == expected_index
    assert search.text() == ""
    assert favorites.isChecked() is False


@pytest.mark.parametrize(
    ("metric_key", "expected_counts"),
    [("all", (2, 2)), ("running", (2, 0)), ("paused", (0, 1)), ("errors", (0, 1))],
)
def test_show_metric_menu_counts_both_kinds_and_routes_actions(
    window, monkeypatch, metric_key, expected_counts
):
    class Signal:
        def connect(self, callback):
            self.callback = callback

    class Action:
        def __init__(self, text):
            self.text = text
            self.triggered = Signal()

    class Menu:
        instance = None

        def __init__(self, _parent):
            self.actions = []
            Menu.instance = self

        def addAction(self, text):
            action = Action(text)
            self.actions.append(action)
            return action

        def exec(self, _position):
            self.executed = True

    class Button:
        @staticmethod
        def rect():
            return SimpleNamespace(bottomLeft=lambda: "bottom-left")

        @staticmethod
        def mapToGlobal(position):
            return ("global", position)

    sessions = [
        {"state": "active"},
        {"state": "busy"},
        {"state": "paused"},
        {"state": "error"},
    ]
    window.snapshot = SimpleNamespace(sync=sessions[:2], forward=sessions[2:])
    window.metric_widgets = {metric_key: Button()}
    opened = []
    monkeypatch.setattr(app_module, "QMenu", Menu)
    monkeypatch.setattr(app_module, "classify", lambda session, _kind: (session["state"], ""))
    monkeypatch.setattr(
        window, "open_metric_sessions", lambda kind, key: opened.append((kind, key))
    )

    window.show_metric_menu(metric_key)

    menu = Menu.instance
    assert menu.executed
    assert len(menu.actions) == 2
    assert [
        str(count) in action.text
        for count, action in zip(expected_counts, menu.actions, strict=True)
    ] == [
        True,
        True,
    ]
    for action in menu.actions:
        action.triggered.callback(False)
    assert opened == [("sync", metric_key), ("forward", metric_key)]


def test_open_navigator_builds_searchable_session_commands_and_flush_gate(window, monkeypatch):
    eligible = {
        "identifier": "sync-live",
        "name": "Live sync",
        "alpha": "./source",
        "beta": {"host": "example.org", "path": "/srv/app"},
        "tags": ["production", "daily"],
    }
    window.snapshot = SimpleNamespace(
        sync=[
            None,
            {"name": "missing identifier"},
            eligible,
            {"identifier": "paused", "paused": True},
        ],
        forward=[{"identifier": "forward-live", "source": 42, "tags": "not-a-list"}],
        sessions_stale=False,
    )
    window.demo = False
    window.pending_action = False

    class Navigator:
        captured = None

        def __init__(self, _parent, commands):
            Navigator.captured = commands

        def exec(self):
            return app_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "QuickNavigator", Navigator)

    window.open_navigator()

    commands = Navigator.captured
    assert [(command[0], command[1], command[2]) for command in commands] == [
        ("doctor", None, None),
        ("open_project", None, None),
        ("focus_session", "sync", "sync-live"),
        ("flush_session", "sync", "sync-live"),
        ("focus_session", "sync", "paused"),
        ("focus_session", "forward", "forward-live"),
    ]
    searchable = commands[2][4]
    assert all(
        term in searchable
        for term in ("sync-live", "Live sync", "./source", "example.org", "/srv/app", "production")
    )


@pytest.mark.parametrize(
    ("command", "target", "accepted", "project_path", "expected"),
    [
        (("doctor", None, None), None, True, "", [("page", 7)]),
        (("open_project", None, None), None, True, "", []),
        (
            ("open_project", None, None),
            None,
            True,
            "C:/repo/mutagen.yml",
            [("launch", "C:/repo/mutagen.yml")],
        ),
        (
            ("focus_session", "forward", "forward-1"),
            None,
            True,
            "",
            [("focus", "forward", "forward-1")],
        ),
        (
            ("flush_session", "sync", "sync-1"),
            None,
            True,
            "",
            [("focus", "sync", "sync-1"), ("action", "sync", "flush")],
        ),
        (None, 4, True, "", [("page", 4)]),
        (None, 4, False, "", []),
    ],
)
def test_open_navigator_routes_dialog_result(
    window, monkeypatch, command, target, accepted, project_path, expected
):
    window.snapshot = SimpleNamespace(sync=[], forward=[], sessions_stale=False)
    window.demo = True
    events = []

    class Navigator:
        def __init__(self, _parent, commands):
            self.command = command
            self.target = target

        def exec(self):
            result = app_module.QDialog.DialogCode.Accepted
            return result if accepted else app_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "QuickNavigator", Navigator)
    monkeypatch.setattr(window, "set_page", lambda index: events.append(("page", index)))
    monkeypatch.setattr(
        window,
        "focus_session_from_navigator",
        lambda kind, identifier: events.append(("focus", kind, identifier)),
    )
    monkeypatch.setattr(
        window, "session_action", lambda kind, action: events.append(("action", kind, action))
    )
    monkeypatch.setattr(
        window, "handle_launch_request", lambda message: events.append(("launch", message["path"]))
    )
    monkeypatch.setattr(
        app_module.QFileDialog, "getOpenFileName", lambda *_args: (project_path, "")
    )

    window.open_navigator()

    assert events == expected


@pytest.mark.parametrize(
    ("command", "expected_page"),
    [("focus", None), ("doctor", 7), ("unknown", None)],
)
def test_handle_launch_request_routes_simple_commands(qapp, monkeypatch, command, expected_page):
    events = []
    fake_window = SimpleNamespace(
        showNormal=lambda: events.append("show"),
        raise_=lambda: events.append("raise"),
        activateWindow=lambda: events.append("activate"),
        set_page=lambda page: events.append(("page", page)),
    )

    app_module.MainWindow.handle_launch_request(fake_window, {"command": command})

    expected = ["show", "raise", "activate"]
    if expected_page is not None:
        expected.append(("page", expected_page))
    assert events == expected


def test_handle_launch_request_validates_and_opens_native_project(qapp, monkeypatch, tmp_path):
    from mutaui.ui import project_viewer

    warnings = []
    opened = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")

    class Dialog:
        def __init__(self, path, **kwargs):
            opened.append((path, kwargs))

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr(project_viewer, "NativeProjectViewerDialog", Dialog)
    fake_window = SimpleNamespace(
        showNormal=lambda: None,
        raise_=lambda: None,
        activateWindow=lambda: None,
        client=SimpleNamespace(binary=None),
    )

    app_module.MainWindow.handle_launch_request(
        fake_window, {"command": "open_project", "path": str(tmp_path / "notes.txt")}
    )
    assert warnings == ["Choose a mutagen.yml or mutagen.yaml file."]
    assert opened == []

    app_module.MainWindow.handle_launch_request(
        fake_window, {"command": "open_project", "path": str(tmp_path / "MUTAGEN.YAML")}
    )
    assert opened[0][0].name == "MUTAGEN.YAML"
    assert opened[0][1]["executor"] is None
    assert opened[0][1]["audit_path"].name == "mutagen-project-actions.jsonl"
    assert opened[1] == "exec"


@pytest.mark.parametrize(
    ("observed_at", "stale", "expected_stale"),
    [
        (app_module.datetime(2026, 11, 13, tzinfo=app_module.UTC), False, None),
        (None, False, "Native snapshot is stale or has no observation timestamp"),
        (
            app_module.datetime(2026, 11, 13, tzinfo=app_module.UTC),
            True,
            "Native snapshot is stale or has no observation timestamp",
        ),
    ],
)
def test_open_conflict_inspector_uses_valid_sync_rows_and_marks_staleness(
    qapp, monkeypatch, tmp_path, observed_at, stale, expected_stale
):
    captured = []

    class Dialog:
        def __init__(self, sessions, _parent, **kwargs):
            captured.append((sessions, kwargs))

        def exec(self):
            captured.append("exec")

    monkeypatch.setattr(app_module, "ConflictInspectorDialog", Dialog)
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
    fake_window = SimpleNamespace(
        snapshot=SimpleNamespace(
            sync=[None, {}, {"identifier": 42}, {"identifier": "sync-1"}],
            sync_observed_at=observed_at,
            sessions_stale=stale,
        )
    )

    app_module.MainWindow.open_conflict_inspector(fake_window)

    sessions, kwargs = captured[0]
    assert len(sessions) == 1
    assert sessions[0].identity.identifier == "sync-1"
    assert sessions[0].stale_reason == expected_stale
    assert kwargs["audit_path"].name == "mutagen-remote-inspection.jsonl"
    assert kwargs["recommendation_path"].name == "conflict-recommendations.json"
    assert captured[1] == "exec"


def test_fill_processes_reuses_table_cells_and_updates_changed_values(window, monkeypatch):
    monkeypatch.setattr(window, "fit_table_to_rows", lambda _table: None)
    process = {
        "pid": 120,
        "name": "mutagen.exe",
        "cpu": 4.5,
        "memory": 2_000_000,
        "read_rate": 1024,
        "write_rate": 2048,
    }

    window.fill_processes([process])
    table = window.process_table
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "120"
    assert table.item(0, 0).data(app_module.Qt.ItemDataRole.UserRole) == 120
    assert table.item(0, 1).text() == "mutagen.exe"

    window.fill_processes([process.copy()])
    changed = {**process, "name": "mutagen-agent.exe", "pid": 121}
    window.fill_processes([changed])
    assert table.item(0, 0).text() == "121"
    assert table.item(0, 0).data(app_module.Qt.ItemDataRole.UserRole) == 121
    assert table.item(0, 1).text() == "mutagen-agent.exe"

    window.fill_processes([])
    assert table.rowCount() == 0


@pytest.mark.parametrize(
    ("frozen", "page", "visible", "ready", "expected_queries"),
    [
        (True, 0, True, True, 0),
        (False, 2, True, True, 0),
        (False, 0, False, True, 0),
        (False, 0, True, False, 0),
        (False, 0, True, True, 1),
    ],
)
def test_refresh_charts_respects_visibility_and_cadence_gates(
    frozen, page, visible, ready, expected_queries
):
    events = []

    class Gate:
        def ready(self, force=False):
            events.append(("ready", force))
            return ready

    class Chart:
        def set_data(self, rows):
            events.append(("chart", list(rows)))

    fake_window = SimpleNamespace(
        chart_frozen=frozen,
        pages=SimpleNamespace(currentIndex=lambda: page),
        isVisible=lambda: visible,
        _chart_dashboard_gate=Gate(),
        _chart_monitor_gate=Gate(),
        history=SimpleNamespace(
            query=lambda **kwargs: (
                events.append(("query", kwargs)) or [{"ts": 1, "cpu": 2, "memory": 3}]
            )
        ),
        cpu_chart=Chart(),
        mem_chart=Chart(),
    )

    app_module.MainWindow.refresh_charts(fake_window)

    assert sum(event[0] == "query" for event in events) == expected_queries
    assert sum(event[0] == "chart" for event in events) == expected_queries * 2


def test_refresh_monitor_charts_uses_demo_history_and_statistics():
    events = []
    history_rows = [{"ts": 2, "cpu": 3}]
    stats = {"p95": 90, "maximum": 99}
    fake_window = SimpleNamespace(
        chart_frozen=False,
        pages=SimpleNamespace(currentIndex=lambda: 6),
        isVisible=lambda: True,
        _chart_dashboard_gate=SimpleNamespace(ready=lambda _force: True),
        _chart_monitor_gate=SimpleNamespace(ready=lambda _force: True),
        monitor_graphs=object(),
        monitor_range=SimpleNamespace(currentData=lambda: 2),
        demo=True,
        history=SimpleNamespace(
            path=":memory:",
            query=lambda **kwargs: events.append(("query", kwargs)) or history_rows,
            statistics=lambda **kwargs: events.append(("statistics", kwargs)) or stats,
        ),
        _chart_query_pending=False,
        _chart_query_reschedule=False,
        _stats_cache_range=None,
        _stats_cache_at=0,
        _stats_pending=False,
        apply_monitor_chart_data=lambda rows, hours: events.append(("monitor", rows, hours)),
        apply_statistics=lambda values, hours: events.append(("stats", values, hours)),
    )

    app_module.MainWindow.refresh_charts(fake_window)

    assert ("monitor", history_rows, 2.0) in events
    assert ("stats", stats, 2.0) in events
    assert [event[0] for event in events] == ["query", "monitor", "statistics", "stats"]


def test_refresh_monitor_charts_runs_database_work_in_workers(monkeypatch):
    events = []
    rows = [{"ts": 4, "cpu": 5}]
    stats = {"p95": 70, "maximum": 90}
    monkeypatch.setattr(app_module, "query_metrics_from_file", lambda path, hours: rows)
    monkeypatch.setattr(app_module, "statistics_from_file", lambda path, hours: stats)
    monkeypatch.setattr(
        app_module, "set_localized_text", lambda widget, text: events.append(("status", text))
    )

    def submit(function, on_result, on_error=None, on_done=None):
        result = function()
        on_result(result)
        if on_done:
            on_done()

    fake_window = SimpleNamespace(
        chart_frozen=False,
        pages=SimpleNamespace(currentIndex=lambda: 6),
        isVisible=lambda: True,
        _chart_dashboard_gate=SimpleNamespace(ready=lambda _force: True),
        _chart_monitor_gate=SimpleNamespace(ready=lambda _force: True, reset=lambda: None),
        monitor_graphs=object(),
        monitor_range=SimpleNamespace(currentData=lambda: 3),
        demo=False,
        history=SimpleNamespace(path="history.sqlite"),
        _chart_query_pending=False,
        _chart_query_reschedule=False,
        _stats_cache_range=None,
        _stats_cache_at=0,
        _stats_pending=False,
        stats_label=SimpleNamespace(setText=lambda text: events.append(("status", text))),
        submit=submit,
        apply_monitor_chart_data=lambda values, hours: events.append(("monitor", values, hours)),
        apply_statistics=lambda values, hours: events.append(("stats", values, hours)),
    )

    app_module.MainWindow.refresh_charts(fake_window)

    assert ("monitor", rows, 3.0) in events
    assert ("stats", stats, 3.0) in events
    assert fake_window._chart_query_pending is False
    assert fake_window._stats_pending is False


def test_refresh_monitor_charts_defers_stats_when_cache_is_fresh():
    events = []
    fake_window = SimpleNamespace(
        chart_frozen=False,
        pages=SimpleNamespace(currentIndex=lambda: 6),
        isVisible=lambda: True,
        _chart_dashboard_gate=SimpleNamespace(ready=lambda _force: True),
        _chart_monitor_gate=SimpleNamespace(ready=lambda _force: True),
        monitor_graphs=object(),
        monitor_range=SimpleNamespace(currentData=lambda: 3),
        demo=True,
        history=SimpleNamespace(
            path=":memory:",
            query=lambda **_kwargs: [],
            statistics=lambda **_kwargs: events.append("statistics"),
        ),
        _chart_query_pending=False,
        _chart_query_reschedule=False,
        _stats_cache_range=3.0,
        _stats_cache_at=app_module.time.monotonic(),
        _stats_pending=False,
        apply_monitor_chart_data=lambda *_args: events.append("monitor"),
        apply_statistics=lambda *_args: events.append("stats"),
    )

    app_module.MainWindow.refresh_charts(fake_window)

    assert events == ["monitor"]


def test_refresh_resources_uses_demo_values_and_deduplicates_pending_work():
    events = []
    demo_window = SimpleNamespace(
        demo=True,
        apply_resource_metrics=lambda values: events.append(("demo", values)),
    )
    app_module.MainWindow.refresh_resources(demo_window)
    assert events[0][0] == "demo"

    pending_window = SimpleNamespace(demo=False, _resource_pending=True)
    app_module.MainWindow.refresh_resources(pending_window)
    assert pending_window._resource_pending is True

    sampled = []
    worker = SimpleNamespace(sample_detailed=lambda: "sample")

    def submit(function, on_result, on_error=None, on_done=None):
        sampled.append(function())
        on_result("metrics")
        if on_done:
            on_done()

    live_window = SimpleNamespace(
        demo=False,
        _resource_pending=False,
        sampler=worker,
        submit=submit,
        apply_resource_metrics=lambda values: sampled.append(values),
    )
    app_module.MainWindow.refresh_resources(live_window)
    assert sampled == ["sample", "metrics"]
    assert live_window._resource_pending is False


@pytest.mark.parametrize(
    ("recorder", "expected_status", "expected_tooltip"),
    [
        (None, "History: demo mode", None),
        (SimpleNamespace(last_error="disk error", dropped=2), "History: write error", "disk error"),
        (SimpleNamespace(last_error="", dropped=3), "History: skipped 3 samples", None),
        (SimpleNamespace(last_error="", dropped=0), "History: saving continuously", None),
    ],
)
def test_apply_resource_metrics_updates_history_status_and_snapshot(
    recorder, expected_status, expected_tooltip
):
    events = []

    class Label:
        text = ""
        tooltip = ""

        def __init__(self):
            self.properties = {}

        def setText(self, text):
            self.text = text

        def setToolTip(self, text):
            self.tooltip = text

        def setProperty(self, key, value):
            self.properties[key] = value

        def property(self, key):
            return self.properties.get(key)

    class Recorder:
        def __init__(self, source):
            self.last_error = source.last_error
            self.dropped = source.dropped

        def add(self, _sample):
            return True

    label = Label()
    footer = Label()
    snapshot = SimpleNamespace(cpu=0, memory=0, processes=0, resource_observed_at=None)
    history = SimpleNamespace(add=lambda sample: events.append(sample))
    fake_window = SimpleNamespace(
        demo=True,
        conf={},
        recorder=Recorder(recorder) if recorder is not None else None,
        writer_status=label,
        footer=footer,
        snapshot=snapshot,
        session_counts=(2, 1),
        traffic_rates=(0, 0),
        _traffic_sample_pending=False,
        cpu_value=Label(),
        mem_value=Label(),
        history=history,
        ui_language="en",
        refresh_charts=lambda: events.append("charts"),
    )

    app_module.MainWindow.apply_resource_metrics(
        fake_window,
        {"cpu": 4.5, "memory": 2048, "processes": 2, "read_rate": 1, "write_rate": 2},
    )

    assert fake_window.writer_status.text == expected_status
    assert fake_window.writer_status.tooltip == (expected_tooltip or "")
    assert snapshot.cpu == 4.5
    assert snapshot.memory == 2048
    assert snapshot.processes == 2
    assert snapshot.resource_observed_at is not None
    assert events[-1] == "charts"


@pytest.mark.parametrize(
    ("alerts_enabled", "tray_visible", "quiet", "expected_notifications"),
    [
        (True, True, False, 1),
        (False, True, False, 0),
        (True, False, False, 0),
        (True, True, True, 0),
    ],
)
def test_apply_resource_metrics_shows_alerts_only_when_enabled_and_tray_visible(
    monkeypatch, alerts_enabled, tray_visible, quiet, expected_notifications
):
    monkeypatch.setattr(app_module, "quiet_hours_active", lambda *_args, **_kwargs: quiet)
    notifications = []
    logs = []
    label = SimpleNamespace(
        setText=lambda _text: None,
        setToolTip=lambda _text: None,
        setProperty=lambda _key, _value: None,
        property=lambda _key: None,
    )
    alert = SimpleNamespace(message="CPU limit exceeded")
    fake_window = SimpleNamespace(
        demo=False,
        conf={"alerts": alerts_enabled},
        alert_engine=SimpleNamespace(evaluate=lambda *_args, **_kwargs: [alert]),
        tray=SimpleNamespace(
            isVisible=lambda: tray_visible,
            showMessage=lambda *args: notifications.append(args),
        ),
        recorder=None,
        writer_status=label,
        snapshot=SimpleNamespace(cpu=0, memory=0, processes=0, resource_observed_at=None),
        session_counts=(0, 0),
        traffic_rates=(0, 0),
        _traffic_sample_pending=False,
        cpu_value=label,
        mem_value=label,
        history=SimpleNamespace(add=lambda _sample: None),
        ui_language="en",
        add_log=logs.append,
        refresh_charts=lambda: None,
    )

    app_module.MainWindow.apply_resource_metrics(
        fake_window,
        {"cpu": 95, "memory": 2048, "processes": 2, "read_rate": 1, "write_rate": 2},
    )

    assert len(notifications) == expected_notifications
    assert logs == ["WARNING: CPU limit exceeded"]


def test_ssh_profile_manager_resolves_alias_safely(window, monkeypatch, tmp_path):
    profile = SimpleNamespace(alias="deploy", unsupported=("Match exec",))
    parsed = SimpleNamespace(valid=True, profiles=(profile,), warnings=("Wildcard ignored",))
    monkeypatch.setattr(app_module, "parse_ssh_config", lambda _path: parsed)
    manager = app_module.SSHProfileManagerDialog(window, tmp_path / "config")
    monkeypatch.setattr(
        app_module,
        "resolve_ssh_options",
        lambda _alias: SimpleNamespace(
            success=True,
            message="",
            stderr="",
            options={
                "hostname": ("example.org",),
                "identityfile": (str(tmp_path / "private-key"),),
                "stricthostkeychecking": ("no",),
            },
        ),
    )

    manager.resolve_selected()

    details = manager.details.toPlainText()
    assert "Alias: deploy" in details
    assert "hostname: example.org" in details
    assert "key file exists: False (contents not read)" in details
    assert "Unexpanded directives in config listing: Match exec" in details
    assert "disables strict host-key checking" in details

    manager._config_valid = False
    manager.details.setPlainText("unchanged")
    manager.resolve_selected()
    assert manager.details.toPlainText() == "unchanged"
    manager._config_valid = True
    manager.alias_input.setCurrentIndex(-1)
    manager.details.setPlainText("no selection")
    manager.resolve_selected()
    assert manager.details.toPlainText() == "no selection"
    manager.close()


@pytest.mark.parametrize(
    ("valid", "profiles", "enabled"),
    [(False, (), False), (True, (), False), (True, (SimpleNamespace(alias="deploy"),), True)],
)
def test_ssh_profile_manager_reload_gates_aliases(
    window, monkeypatch, tmp_path, valid, profiles, enabled
):
    monkeypatch.setattr(
        app_module,
        "parse_ssh_config",
        lambda _path: SimpleNamespace(valid=valid, profiles=profiles, warnings=("read notice",)),
    )

    manager = app_module.SSHProfileManagerDialog(window, tmp_path / "config")

    assert manager.alias_input.isEnabled() is enabled
    assert manager.alias_input.count() == len(profiles)
    if not valid:
        assert "SSH operations are disabled" in manager.config_status.text()
    manager.close()


def test_ssh_profile_manager_reports_failed_resolution_and_connection(
    window, monkeypatch, tmp_path
):
    profile = SimpleNamespace(alias="deploy", unsupported=())
    monkeypatch.setattr(
        app_module,
        "parse_ssh_config",
        lambda _path: SimpleNamespace(valid=True, profiles=(profile,), warnings=()),
    )
    manager = app_module.SSHProfileManagerDialog(window, tmp_path / "config")
    monkeypatch.setattr(
        app_module,
        "resolve_ssh_options",
        lambda _alias: SimpleNamespace(success=False, message="ssh -G failed", stderr="bad config"),
    )

    manager.resolve_selected()
    assert "ssh -G failed" in manager.details.toPlainText()
    assert "bad config" in manager.details.toPlainText()

    prompts = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args: app_module.QMessageBox.StandardButton.Cancel,
    )
    monkeypatch.setattr(app_module, "test_ssh_connection", lambda _alias: prompts.append("called"))
    manager.test_selected()
    assert prompts == []

    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args: app_module.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        app_module,
        "test_ssh_connection",
        lambda _alias: SimpleNamespace(
            success=False, message="connection failed", stderr="host key rejected"
        ),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(message),
    )

    manager.test_selected()

    assert len(messages) == 1
    assert "connection failed" in messages[0]
    assert "host key rejected" in messages[0]
    manager.close()


def test_ssh_profile_manager_reports_successful_connection(window, monkeypatch, tmp_path):
    profile = SimpleNamespace(alias="deploy", unsupported=())
    monkeypatch.setattr(
        app_module,
        "parse_ssh_config",
        lambda _path: SimpleNamespace(valid=True, profiles=(profile,), warnings=()),
    )
    manager = app_module.SSHProfileManagerDialog(window, tmp_path / "config")
    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args: app_module.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    monkeypatch.setattr(
        app_module,
        "test_ssh_connection",
        lambda _alias: SimpleNamespace(success=True, message="Connected", stderr=""),
    )

    manager.test_selected()

    assert messages == ["Connected"]
    manager.close()


@pytest.mark.parametrize(
    ("demo", "pending", "stale"),
    [(True, False, False), (False, True, False), (False, False, True)],
)
def test_sync_replacement_requires_fresh_live_snapshot(qapp, monkeypatch, demo, pending, stale):
    warnings = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    fake_window = SimpleNamespace(
        demo=demo,
        pending_action=pending,
        snapshot=SimpleNamespace(sessions_stale=stale, sync_observed_at=None, sync=[]),
    )

    app_module.MainWindow.review_sync_replacement(fake_window, "sync-1")

    assert warnings == ["Refresh current native sessions first."]


@pytest.mark.parametrize(
    ("observed_at", "sessions", "expected"),
    [
        (None, [], "Session status is stale. Refresh and review again."),
        (
            app_module.datetime(2000, 1, 1, tzinfo=app_module.UTC),
            [],
            "Session status is stale. Refresh and review again.",
        ),
        (app_module.datetime.now(app_module.UTC), [], "The exact session is no longer loaded."),
        (
            app_module.datetime.now(app_module.UTC),
            [{"identifier": "sync-1", "labels": ["malformed"]}],
            "Project-owned sessions must be changed through their native project workflow.",
        ),
        (
            app_module.datetime.now(app_module.UTC),
            [{"identifier": "sync-1", "labels": {"io.mutagen.project": "project-1"}}],
            "Project-owned sessions must be changed through their native project workflow.",
        ),
    ],
)
def test_sync_replacement_rejects_stale_missing_or_project_owned_target(
    qapp, monkeypatch, observed_at, sessions, expected
):
    warnings = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    fake_window = SimpleNamespace(
        demo=False,
        pending_action=False,
        snapshot=SimpleNamespace(sessions_stale=False, sync_observed_at=observed_at, sync=sessions),
    )

    app_module.MainWindow.review_sync_replacement(fake_window, "sync-1")

    assert warnings == [expected]


def test_sync_replacement_requires_verified_provenance_and_saved_proposal(qapp, monkeypatch):
    errors = []
    observed_at = app_module.datetime.now(app_module.UTC)
    session = {"identifier": "sync-1", "labels": {}}
    fake_window = SimpleNamespace(
        demo=False,
        pending_action=False,
        snapshot=SimpleNamespace(
            sessions_stale=False, sync_observed_at=observed_at, sync=[session]
        ),
        report_error=errors.append,
        session_provenance=SimpleNamespace(get=lambda _identifier: None),
        conf={},
    )

    app_module.MainWindow.review_sync_replacement(fake_window, "sync-1")

    assert errors == ["This session has no verified local creation provenance."]

    errors.clear()
    fake_window.session_provenance.get = lambda _identifier: SimpleNamespace(
        create_arguments=("sync", "create", "source", "target")
    )
    fake_window.conf = {"session_prefs": {"sync-1": {"configuration_proposal": {}}}}

    app_module.MainWindow.review_sync_replacement(fake_window, "sync-1")

    assert errors == ["Save at least one configuration proposal before replacement."]


@pytest.mark.parametrize(
    ("proposal", "changes", "expected"),
    [
        (
            {"mode": "two-way-safe"},
            (),
            "The native snapshot is incomplete, contains unknown fields, or has no effective changes.",
        ),
        (
            {"mode": "one-way-replica"},
            (SimpleNamespace(path="mode", current="two-way-safe", proposed="one-way-replica"),),
            "Replica mode is a destructive R3 change and cannot use this replacement flow.",
        ),
    ],
)
def test_sync_replacement_rejects_noop_and_replica_proposals(
    window, monkeypatch, proposal, changes, expected
):
    identifier = "sync-exact-1"
    window.demo = False
    window.pending_action = False
    window.snapshot = SimpleNamespace(
        sessions_stale=False,
        sync_observed_at=datetime.now(app_module.UTC),
        sync=[{"identifier": identifier, "labels": {}}],
    )
    window.conf = {"session_prefs": {identifier: {"configuration_proposal": proposal}}}
    monkeypatch.setattr(
        window.session_provenance,
        "get",
        lambda _identifier: SimpleNamespace(
            create_arguments=("sync", "create", "--mode=two-way-safe", "source", "target")
        ),
    )
    monkeypatch.setattr(
        window.client,
        "command",
        lambda *_args, **_kwargs: "--mode string (two-way-safe|one-way-replica)",
    )
    monkeypatch.setattr(
        app_module, "extract_sync_configuration", lambda _session: {"mode": "two-way-safe"}
    )
    monkeypatch.setattr(
        app_module,
        "render_sync_replacement_arguments",
        lambda *_args: ("sync", "create", "--mode=one-way-replica", "source", "target"),
    )
    monkeypatch.setattr(app_module, "from_legacy_session", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        app_module,
        "validate_native_command_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(snapshot_inputs_complete=True),
    )
    monkeypatch.setattr(
        app_module,
        "build_reconfiguration_preview",
        lambda *_args, **_kwargs: SimpleNamespace(source_sha256="source-hash", changes=changes),
    )
    errors = []
    monkeypatch.setattr(window, "report_error", errors.append)

    window.review_sync_replacement(identifier)

    assert errors == [expected]
    assert window.pending_action is False


def test_sync_replacement_cancels_prepared_plan_without_consent(qapp, monkeypatch):
    observed_at = app_module.datetime.now(app_module.UTC)
    session = {"identifier": "sync-1", "labels": {}}
    plan = SimpleNamespace(plan_id="plan-1", target_ids=("sync-1",))
    cancellations = []
    fake_client = SimpleNamespace(
        command=lambda *_args, **_kwargs: "Options:\n  --sync-mode=<mode>\n",
        action_planner=SimpleNamespace(
            prepare=lambda _request: plan,
            cancel=cancellations.append,
        ),
    )
    fake_window = SimpleNamespace(
        demo=False,
        pending_action=False,
        snapshot=SimpleNamespace(
            sessions_stale=False, sync_observed_at=observed_at, sync=(session,)
        ),
        session_provenance=SimpleNamespace(
            get=lambda _identifier: SimpleNamespace(
                create_arguments=("sync", "create", "source", "target")
            )
        ),
        conf={"session_prefs": {"sync-1": {"configuration_proposal": {"mode": "two-way-safe"}}}},
        client=fake_client,
        report_error=lambda _message: pytest.fail("unexpected replacement error"),
    )
    monkeypatch.setattr(
        app_module, "extract_sync_configuration", lambda _session: {"mode": "two-way-safe"}
    )
    monkeypatch.setattr(
        app_module,
        "render_sync_replacement_arguments",
        lambda *_args: ["sync", "create", "--sync-mode=two-way-safe", "source", "target"],
    )
    monkeypatch.setattr(app_module, "from_legacy_session", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        app_module,
        "validate_native_command_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(snapshot_inputs_complete=True),
    )
    monkeypatch.setattr(
        app_module,
        "build_reconfiguration_preview",
        lambda *_args, **_kwargs: SimpleNamespace(
            source_sha256="source-hash",
            changes=(
                SimpleNamespace(path="mode", current="two-way-safe", proposed="two-way-safe"),
            ),
        ),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args: app_module.QMessageBox.StandardButton.No,
    )

    app_module.MainWindow.review_sync_replacement(fake_window, "sync-1")

    assert cancellations == ["plan-1"]
    assert fake_window.pending_action is False


def test_close_event_defers_application_exit_while_worker_is_active(window):
    window._allow_exit = True
    window.workers.add(object())
    event = QCloseEvent()

    try:
        window.closeEvent(event)
        assert not event.isAccepted()
        assert window._shutdown_pending
    finally:
        window.workers.clear()
        window._shutdown_pending = False


def test_endpoint_session_selector_and_details_follow_language(window):
    window.set_page(9)
    window.update_endpoint_sessions(window.snapshot)
    assert window.endpoint_combo.count() > 0
    window.apply_ui_language("cs")

    assert "Sledování změn" in window.endpoint_combo.currentText()
    assert "Sledování změn" in window.endpoint_status.text()
    assert window.endpoint_cards["left"]["conn"].text() == "● Připojeno"

    window.apply_ui_language("en")

    assert "Watching" in window.endpoint_combo.currentText()
    assert "Watching" in window.endpoint_status.text()
    assert window.endpoint_cards["left"]["conn"].text() == "● Connected"


def test_selected_session_uses_native_id_when_display_name_collides(window):
    first = {"identifier": "sync-first", "name": "sync-target"}
    second = {"identifier": "sync-target", "name": "Duplicate"}
    window.apply_snapshot(app_module.Snapshot(binary=window.client.binary, sync=[first, second]))

    row = window.sync_table.model().row_for_identifier("sync-first")
    window.sync_table.selectRow(row)

    assert window.selected_session("sync") is first


def test_fill_table_preserves_exact_selection_and_clears_removed_session(window):
    first = {"identifier": "sync-first", "name": "First"}
    second = {"identifier": "sync-second", "name": "Second"}
    table = window.sync_table

    window.fill_table(table, [first, second], "sync")
    selected_row = table.model().row_for_identifier("sync-second")
    assert selected_row >= 0
    table.selectRow(selected_row)
    table.setCurrentIndex(table.model().index(selected_row, 0))
    assert (
        table.currentIndex().siblingAtColumn(0).data(app_module.Qt.ItemDataRole.UserRole)
        == "sync-second"
    )
    window.fill_table(table, [first, second], "sync")
    assert (
        table.currentIndex().siblingAtColumn(0).data(app_module.Qt.ItemDataRole.UserRole)
        == "sync-second"
    )

    window.fill_table(table, [first], "sync")
    assert not table.selectionModel().hasSelection()


def test_metric_chart_preserves_missing_measurements_instead_of_drawing_zero(window):
    chart = window.cpu_chart
    chart.set_data([(1.0, None, None), (2.0, 5.0, None)])

    assert list(chart.points) == [(1.0, None, None), (2.0, 5.0, None)]
    assert chart.amount(None) == "—"
    assert not chart.grab().isNull()


def test_advanced_forward_overwrite_discloses_remote_path_is_uninspected(qapp, monkeypatch):
    dialog = app_module.SessionDialog("forward", ui_mode="advanced")
    dialog.a.setText("operator@example.test:unix:/run/mutagen-forward.sock")
    dialog.b.setText("tcp:localhost:8080")
    dialog.socket_overwrite_source.setCurrentIndex(
        dialog.socket_overwrite_source.findData("overwrite")
    )
    warnings = []

    def capture_warning(*args):
        warnings.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(app_module.QMessageBox, "warning", capture_warning)
    dialog.validate()

    assert len(warnings) == 1
    assert "remote path not inspected" in warnings[0][2]
    dialog.close()


def test_forward_favorites_action_uses_selected_language(window):
    window.set_page(2)
    window.apply_ui_language("cs")
    window.forward_table.selectRow(0)

    assert window.forward_favorite_button.text() == "☆ Přidat k oblíbeným"


def test_settings_page_is_lazy_without_changing_its_route(window):
    assert window.pages.count() == 11
    assert not window.pages.is_page_built(5)

    window.set_page(5)

    assert window.pages.is_page_built(5)
    assert window.pages.currentIndex() == 5
    assert window.page_name.text() == "Settings"

    window.set_page(0)
    window.set_page(5)
    assert window.pages.widget(5) is not None


def test_settings_exposes_ssh_and_portable_data_tools(window):
    window.set_page(5)
    titles = {button.text() for button in window.findChildren(app_module.QPushButton)}

    assert "Inspect SSH Profiles…" in titles
    assert "Export Portable Bundle…" in titles
    assert "Import Portable Bundle…" in titles
    assert "Migrate Settings with Backup…" in titles
    assert "Rollback Settings Migration…" in titles


def test_health_settings_persist_and_update_tracker_without_running_recovery(window):
    page = window.alerts_page()
    window.health_mode.setCurrentIndex(window.health_mode.findData("assisted"))
    window.health_failure_count.setValue(4)
    window.health_failure_elapsed.setValue(180)
    window.quiet_hours_enabled.setChecked(True)
    window.quiet_hours_start.setTime(app_module.QTime(21, 30))
    window.quiet_hours_end.setTime(app_module.QTime(6, 45))

    window.save_alert_rules()

    assert window.conf["health_mode"] == "assisted"
    assert window.health_tracker.policy.mode == "assisted"
    assert window.health_tracker.policy.failure_count_threshold == 4
    assert window.health_tracker.policy.failure_elapsed_seconds == 180
    assert window.conf["quiet_hours_enabled"] is True
    assert window.conf["quiet_hours_start"] == "21:30"
    assert window.conf["quiet_hours_end"] == "06:45"
    assert not window.pending_action
    page.close()


def test_portable_bundle_actions_export_import_and_rollback_settings(window, tmp_path, monkeypatch):
    from connection_profiles import ConnectionProfileStore, load_profile_store
    from portable_bundle import build_bundle, load_bundle
    from settings import load_settings, write_settings

    profile_path = app_module.settings_path().with_name("connection-profiles.json")
    outgoing = ConnectionProfileStore(profile_path)
    outgoing.create("Outgoing", "./source", "deploy@host:/dest", kind="sync")
    exported_path = tmp_path / "portable.json"
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(exported_path), "JSON (*.json)"),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: app_module.QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *_args: None)

    window.export_portable_bundle()

    exported = load_bundle(exported_path.read_bytes())
    assert exported.valid
    assert len(exported.data["items"]["connection_profiles"]) == 1

    incoming_store = ConnectionProfileStore(tmp_path / "incoming-profiles.json")
    incoming = incoming_store.create("Incoming", "./input", "host:/output", kind="sync")
    incoming_path = tmp_path / "incoming.json"
    incoming_path.write_text(
        build_bundle([incoming], {"theme": "dark"}, app_version="8.2").text,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(incoming_path), "JSON (*.json)"),
    )
    monkeypatch.setattr(
        app_module.PortableImportPreviewDialog,
        "exec",
        lambda _dialog: app_module.QDialog.DialogCode.Accepted,
    )
    monkeypatch.setattr(
        app_module.PortableImportPreviewDialog,
        "profile_choices",
        lambda _dialog: {incoming.id: "create"},
    )
    monkeypatch.setattr(
        app_module.PortableImportPreviewDialog,
        "selected_preferences",
        lambda _dialog: {"theme"},
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: app_module.QMessageBox.StandardButton.Yes,
    )
    current_settings_path = app_module.settings_path()
    write_settings(
        current_settings_path,
        {
            "schema_version": 1,
            "session_prefs": {"local-id": {"note": "local note", "notifications": False}},
        },
    )

    window.import_portable_bundle()

    assert incoming.id in {profile.id for profile in load_profile_store(profile_path).profiles}
    current = load_settings(current_settings_path).values
    assert current["theme"] == "dark"
    assert current["session_prefs"]["local-id"]["note"] == "local note"

    legacy_bytes = b'{"theme":"light","favorites":{"sync":["s1"],"forward":[]}}\n'
    current_settings_path.write_bytes(legacy_bytes)
    window.migrate_local_settings()
    backup = next(tmp_path.glob("settings.json.pre-migration.*.bak"))
    assert backup.read_bytes() == legacy_bytes
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(backup), "Backup"),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: app_module.QMessageBox.StandardButton.Yes,
    )

    window.rollback_local_settings_migration()

    assert current_settings_path.read_bytes() == legacy_bytes


def test_settings_tooltips_use_registry_metadata(window):
    window.set_page(5)
    assert window.interval_input.toolTip() == app_module.setting_tooltip("interval", "en")
    assert window.theme_input.toolTip() == app_module.setting_tooltip("theme", "en")

    window.set_page(8)
    assert window.cpu_alert_limit.toolTip() == app_module.setting_tooltip("cpu_alert_limit", "en")


def test_settings_page_loads_global_mutagen_yaml_without_saving(tmp_path, window):
    config = tmp_path / "mutagen.yml"
    original = b"# keep\nsync:\n  defaults:\n    watch: true\n"
    config.write_bytes(original)
    window.set_page(5)
    window.global_config_path_input.setText(str(config))

    window.load_global_config()

    assert window.global_config_editor.toPlainText().startswith("# keep")
    assert window._global_config_snapshot.valid
    assert config.read_bytes() == original


def test_global_yaml_editor_defaults_to_mutagens_native_user_config(window):
    window.set_page(5)

    assert window.global_config_path_input.text() == str(app_module.Path.home() / ".mutagen.yml")


def test_invalid_global_yaml_opens_read_only_recovery_view_and_copy(tmp_path, monkeypatch, window):
    config = tmp_path / "mutagen.yml"
    source = "sync: [broken\n"
    config.write_text(source, encoding="utf-8")
    window.set_page(5)
    window.global_config_path_input.setText(str(config))
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *_args: None)
    captured = {}

    def inspect_dialog(dialog):
        captured["source"] = dialog.findChild(QPlainTextEdit, "globalYamlRecoverySource")
        captured["copy"] = dialog.findChild(QPushButton, "copyGlobalYamlRecovery")
        return 0

    monkeypatch.setattr(app_module.QDialog, "exec", inspect_dialog)
    window.load_global_config()

    assert window._global_config_snapshot.valid is False
    assert window.global_config_editor.isReadOnly()
    window.show_global_yaml_recovery()
    assert captured["source"].toPlainText() == source
    assert captured["source"].isReadOnly()
    captured["copy"].click()
    assert app_module.QApplication.clipboard().text().replace("\r\n", "\n") == source
    assert config.read_text(encoding="utf-8") == source


@pytest.mark.parametrize(
    ("choice", "expected_editor", "expected_baseline"),
    [
        ("Reload external changes", "external", "external"),
        ("Keep draft and merge manually", "draft", "external"),
        ("Cancel", "draft", "original"),
    ],
)
def test_global_yaml_external_change_offers_reload_merge_or_cancel(
    tmp_path, monkeypatch, window, choice, expected_editor, expected_baseline
):
    config = tmp_path / "mutagen.yml"
    original = b"sync:\n  defaults:\n    watch: true\n"
    external = b"sync:\n  defaults:\n    watch: false\n"
    draft = "sync:\n  defaults:\n    watch: true\n    probeMode: accelerated\n"
    config.write_bytes(original)
    window.set_page(5)
    window.global_config_path_input.setText(str(config))
    window.load_global_config()
    original_snapshot = window._global_config_snapshot
    window.global_config_editor.setPlainText(draft)
    config.write_bytes(external)

    selected_buttons = []

    def execute_dialog(dialog):
        label = "Save reviewed changes" if not selected_buttons else choice
        selected_buttons.append(
            next(button for button in dialog.buttons() if button.text() == label)
        )
        return 0

    monkeypatch.setattr(app_module.QMessageBox, "exec", execute_dialog)
    monkeypatch.setattr(
        app_module.QMessageBox, "clickedButton", lambda _dialog: selected_buttons[-1]
    )

    window.preview_global_config()

    assert config.read_bytes() == external
    if expected_editor == "external":
        assert window.global_config_editor.toPlainText() == external.decode()
    else:
        assert window.global_config_editor.toPlainText() == draft
    expected_baseline_bytes = external if expected_baseline == "external" else original
    assert window._global_config_snapshot.raw_bytes == expected_baseline_bytes
    if expected_baseline == "original":
        assert window._global_config_snapshot is original_snapshot


def test_advanced_session_settings_show_full_raw_native_json(window, monkeypatch):
    session = {
        "identifier": "exact-session-id",
        "name": "Example",
        "paused": False,
        "futureNativeOption": {"preserved": [1, 2]},
    }
    monkeypatch.setattr(window, "selected_session", lambda _kind: session)
    dialogs = []
    monkeypatch.setattr(app_module.QDialog, "exec", lambda dialog: dialogs.append(dialog) or 0)

    window.set_ui_mode("advanced")
    window.open_session_preferences("sync")
    settings_dialog = dialogs[-1]
    raw_button = settings_dialog.findChild(QPushButton, "rawNativeSessionJson")
    assert raw_button is not None
    raw_button.click()

    raw_dialog = dialogs[-1]
    raw_view = raw_dialog.findChild(QPlainTextEdit, "rawNativeSessionJsonSource")
    assert raw_view is not None
    assert raw_view.isReadOnly()
    assert json.loads(raw_view.toPlainText()) == session
    raw_dialog.findChild(QPushButton, "copyRawNativeSessionJson").click()
    assert json.loads(app_module.QApplication.clipboard().text()) == session

    window.set_ui_mode("basic")
    window.open_session_preferences("sync")
    assert dialogs[-1].findChild(QPushButton, "rawNativeSessionJson") is None


def test_basic_advanced_switch_preserves_in_progress_settings_drafts(window):
    settings_page = next(
        index for index, route in enumerate(app_module.PAGE_ROUTES) if route.route_id == "settings"
    )
    draft = "# unsaved draft\nsync:\n  defaults:\n    watch:\n      mode: force-poll\n"

    window.set_ui_mode("advanced")
    window.set_page(settings_page)
    window.binary_edit.setText("C:/tools/mutagen-custom.exe")
    window.interval_input.setValue(9)
    window.metric_interval_input.setCurrentIndex(window.metric_interval_input.count() - 1)
    window.adaptive_input.setChecked(False)
    window.fast_interval_input.setValue(7)
    window.idle_interval_input.setValue(45)
    window.quiet_after_input.setValue(180)
    window.new_sync_profile_input.setCurrentIndex(window.new_sync_profile_input.count() - 1)
    window.eco_tray_input.setChecked(False)
    window.tray_input.setChecked(False)
    window.alert_input.setChecked(False)
    window.global_config_editor.setPlainText(draft)
    settings_values = (
        window.binary_edit.text(),
        window.interval_input.value(),
        window.metric_interval_input.currentData(),
        window.adaptive_input.isChecked(),
        window.fast_interval_input.value(),
        window.idle_interval_input.value(),
        window.quiet_after_input.value(),
        window.new_sync_profile_input.currentData(),
        window.eco_tray_input.isChecked(),
        window.tray_input.isChecked(),
        window.alert_input.isChecked(),
    )
    window.set_ui_mode("basic")

    assert window.pages.currentIndex() == settings_page

    window.set_ui_mode("advanced")
    window.set_page(settings_page)
    assert window.global_config_editor.toPlainText() == draft
    assert (
        window.binary_edit.text(),
        window.interval_input.value(),
        window.metric_interval_input.currentData(),
        window.adaptive_input.isChecked(),
        window.fast_interval_input.value(),
        window.idle_interval_input.value(),
        window.quiet_after_input.value(),
        window.new_sync_profile_input.currentData(),
        window.eco_tray_input.isChecked(),
        window.tray_input.isChecked(),
        window.alert_input.isChecked(),
    ) == settings_values


def test_sync_mode_help_explains_direction_and_data_loss_for_every_mode(window):
    dialog = app_module.SessionDialog("sync", window, ui_mode="advanced", executable="mutagen.exe")
    expected_phrases = {
        "two-way-safe": ("changes from alpha and beta flow both ways", "manual resolution"),
        "two-way-resolved": (
            "alpha wins every conflict",
            "beta changes can be overwritten or deleted",
        ),
        "one-way-safe": (
            "only changes from alpha to beta propagate",
            "beta-only content is preserved",
            "deletions of alpha content on beta are restored from alpha",
        ),
        "one-way-replica": (
            "exact copy of alpha",
            "deletes beta-only content",
            "overwrites beta changes",
        ),
    }

    for mode, phrases in expected_phrases.items():
        dialog.mode.setCurrentText(mode)
        description = dialog.mode_help.text().casefold()
        assert all(phrase in description for phrase in phrases), mode

    dialog.close()


def test_sync_mode_help_is_czech_when_czech_is_selected(window):
    previous_language = app_module.active_language()
    app_module.set_active_language("cs")
    dialog = app_module.SessionDialog("sync", window, ui_mode="advanced", executable="mutagen.exe")
    expected_phrases = {
        "two-way-safe": ("obousměrná synchronizace", "ručnímu vyřešení"),
        "two-way-resolved": ("alpha vyhrává každý konflikt", "změnu na beta"),
        "one-way-safe": ("změny z alpha na beta", "obsah pouze na beta zůstává"),
        "one-way-replica": ("přesnou kopií alpha", "smaže obsah jen na beta"),
    }
    try:
        for mode, phrases in expected_phrases.items():
            dialog.mode.setCurrentText(mode)
            description = dialog.mode_help.text().casefold()
            assert all(phrase in description for phrase in phrases), mode
    finally:
        dialog.close()
        app_module.set_active_language(previous_language)


def test_basic_advanced_switch_preserves_in_progress_sync_wizard_draft(window):
    dialog = app_module.SessionDialog("sync", window, ui_mode="basic", executable="mutagen.exe")
    window.show()
    dialog.show()
    QApplication.processEvents()
    dialog.name.setText("draft-sync")
    dialog.a.setText("C:/alpha")
    dialog.b.setText("user@host:/beta")
    dialog.mode.setCurrentText("one-way-safe")
    dialog.profile.setCurrentIndex(dialog.profile.findData("fast_poll"))
    dialog.ignore.setPlainText("*.tmp\n!keep.tmp")
    arguments = dialog.arguments()

    window.set_ui_mode("advanced")
    QApplication.processEvents()
    assert dialog.isVisible()
    assert dialog.arguments() == arguments
    window.set_ui_mode("basic")
    QApplication.processEvents()
    assert dialog.isVisible()
    assert dialog.arguments() == arguments

    dialog.close()


def test_basic_advanced_switch_preserves_in_progress_forward_wizard_draft(window):
    dialog = app_module.SessionDialog(
        "forward", window, ui_mode="advanced", executable="mutagen.exe"
    )
    window.show()
    dialog.show()
    QApplication.processEvents()
    dialog.name.setText("draft-forward")
    dialog.a.setText("tcp:localhost:8080")
    dialog.b.setText("tcp:localhost:9000")
    dialog.socket_owner_source.setText("user-x")
    dialog.socket_permission_source.setText("600")
    arguments = dialog.arguments()

    window.set_ui_mode("basic")
    QApplication.processEvents()
    assert dialog.isVisible()
    assert dialog.arguments() == arguments
    window.set_ui_mode("advanced")
    QApplication.processEvents()
    assert dialog.isVisible()
    assert dialog.arguments() == arguments

    dialog.close()


def test_basic_advanced_switch_preserves_advanced_history_page_draft(window):
    logs_page = next(
        index
        for index, route in enumerate(app_module.PAGE_ROUTES)
        if route.route_id == "action-history"
    )
    window.set_ui_mode("advanced")
    window.set_page(logs_page)
    window.tail_filter.setText("SSH connection timed out")
    QApplication.processEvents()

    window.set_ui_mode("basic")
    assert window.pages.currentIndex() == 0
    assert window.nav[logs_page].isHidden()
    assert window.tail_filter.text() == "SSH connection timed out"

    window.set_ui_mode("advanced")
    assert not window.nav[logs_page].isHidden()
    window.set_page(logs_page)
    assert window.tail_filter.text() == "SSH connection timed out"


def test_basic_advanced_switch_preserves_alert_and_recovery_drafts(window):
    alerts_page = next(
        index for index, route in enumerate(app_module.PAGE_ROUTES) if route.route_id == "alerts"
    )
    window.set_ui_mode("advanced")
    window.set_page(alerts_page)
    window.cpu_alert_on.setChecked(True)
    window.cpu_alert_limit.setValue(135)
    window.ram_alert_limit.setValue(3072)
    window.health_mode.setCurrentIndex(window.health_mode.findData("assisted"))
    window.health_failure_count.setValue(6)
    draft = (
        window.cpu_alert_on.isChecked(),
        window.cpu_alert_limit.value(),
        window.ram_alert_limit.value(),
        window.health_mode.currentData(),
        window.health_failure_count.value(),
    )
    settings_before_switch = dict(window.conf)

    window.set_ui_mode("basic")
    assert window.pages.currentIndex() == 0
    assert window.nav[alerts_page].isHidden()
    assert window.conf == settings_before_switch
    assert (
        window.cpu_alert_on.isChecked(),
        window.cpu_alert_limit.value(),
        window.ram_alert_limit.value(),
        window.health_mode.currentData(),
        window.health_failure_count.value(),
    ) == draft

    window.set_ui_mode("advanced")
    assert not window.nav[alerts_page].isHidden()
    window.set_page(alerts_page)
    assert (
        window.cpu_alert_on.isChecked(),
        window.cpu_alert_limit.value(),
        window.ram_alert_limit.value(),
        window.health_mode.currentData(),
        window.health_failure_count.value(),
    ) == draft


def test_basic_advanced_switch_preserves_monitoring_period_draft(window):
    monitoring_page = next(
        index
        for index, route in enumerate(app_module.PAGE_ROUTES)
        if route.route_id == "monitoring"
    )
    window.set_ui_mode("advanced")
    window.set_page(monitoring_page)
    selected_period = window.monitor_range.findData(48)
    assert selected_period >= 0
    window.monitor_range.setCurrentIndex(selected_period)

    window.set_ui_mode("basic")
    assert window.pages.currentIndex() == 0
    assert window.nav[monitoring_page].isHidden()
    assert window.monitor_range.currentData() == 48

    window.set_ui_mode("advanced")
    assert not window.nav[monitoring_page].isHidden()
    window.set_page(monitoring_page)
    assert window.monitor_range.currentData() == 48


def test_basic_advanced_switch_preserves_endpoint_search_draft(window):
    endpoints_page = next(
        index for index, route in enumerate(app_module.PAGE_ROUTES) if route.route_id == "endpoints"
    )
    window.set_ui_mode("advanced")
    window.set_page(endpoints_page)
    window.endpoint_combo.setEditText("remote endpoint search")

    window.set_ui_mode("basic")
    assert window.pages.currentIndex() == 0
    assert window.nav[endpoints_page].isHidden()
    assert window.endpoint_combo.currentText() == "remote endpoint search"

    window.set_ui_mode("advanced")
    assert not window.nav[endpoints_page].isHidden()
    window.set_page(endpoints_page)
    assert window.endpoint_combo.currentText() == "remote endpoint search"


def test_basic_advanced_switch_preserves_server_scope_selection(window):
    servers_page = next(
        index for index, route in enumerate(app_module.PAGE_ROUTES) if route.route_id == "servers"
    )
    window.set_ui_mode("advanced")
    window.set_page(servers_page)
    session = {
        "identifier": "sync-server",
        "alpha": {"protocol": 0, "path": "C:/local"},
        "beta": {"protocol": 1, "host": "prod.example.com", "port": 0, "path": "/src"},
        "paused": False,
        "status": 6,
    }
    window.apply_snapshot(app_module.Snapshot(binary=window.client.binary, sync=[session]))
    server_index = window.server_selector.findData("ssh:prod.example.com:22")
    assert server_index >= 0
    window.server_selector.setCurrentIndex(server_index)

    window.set_ui_mode("basic")
    assert window.pages.currentIndex() == 0
    assert window.nav[servers_page].isHidden()
    assert window.server_selector.currentData() == "ssh:prod.example.com:22"

    window.set_ui_mode("advanced")
    assert not window.nav[servers_page].isHidden()
    window.set_page(servers_page)
    assert window.server_selector.currentData() == "ssh:prod.example.com:22"


def test_basic_mode_hides_empty_advanced_navigation_sections(window):
    window.set_ui_mode("basic")

    assert window.nav_section_labels["endpoints"].isHidden()
    assert window.nav_section_labels["servers"].isHidden()
    assert not window.nav_section_labels["action-history"].isHidden()

    window.set_ui_mode("advanced")
    assert not window.nav_section_labels["endpoints"].isHidden()
    assert not window.nav_section_labels["servers"].isHidden()


def test_safe_support_report_exports_metadata_and_event_counts_without_event_text(
    tmp_path, monkeypatch, window
):
    output = tmp_path / "safe-report.json"
    sensitive = "private-host.example"
    window.snapshot = app_module.Snapshot(
        binary=r"C:\\private\\mutagen.exe",
        daemon=True,
        version="Mutagen version 0.18.1",
        error=f"connection to {sensitive} failed",
    )
    window._safe_problem_codes = ("ssh_host_trust",)
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(output), "JSON (*.json)"),
    )
    monkeypatch.setattr(
        window.history,
        "events",
        lambda limit: [(1.0, "error", f"secret log text {sensitive}")],
    )
    monkeypatch.setattr(window.history, "statistics", lambda **_kwargs: {"samples": 0})
    monkeypatch.setattr(window, "add_log", lambda _message: None)
    monkeypatch.setenv("GITHUB_RUN_ID", "123456")

    window.export_safe_report()

    payload = output.read_text(encoding="utf-8")
    data = json.loads(payload)
    assert data["application_version"] == "8.2.0"
    assert data["problem_codes"] == ["ssh_host_trust"]
    assert data["event_counts"] == {"recent_events": 1, "capped": False}
    assert data["ci_build_id"] == "123456"
    assert sensitive not in payload
    assert "secret log text" not in payload
    assert "C:\\\\private" not in payload


def test_sync_session_settings_show_native_and_proposed_config_read_only(monkeypatch, window):
    session = {
        "identifier": "exact-session-id",
        "name": "Example",
        "watch": {"mode": 1, "pollingInterval": 20},
        "scanMode": 2,
    }
    monkeypatch.setattr(window, "selected_session", lambda _kind: session)
    observed = {}

    def inspect_dialog(dialog):
        table = dialog.findChild(QTableWidget)
        observed["rows"] = table.rowCount()
        observed["headers"] = [
            table.horizontalHeaderItem(i).text() for i in range(table.columnCount())
        ]
        observed["native_watch"] = next(
            table.item(row, 1).text()
            for row in range(table.rowCount())
            if table.item(row, 0).text() == "Watch mode"
        )
        observed["buttons"] = QDialog.DialogCode.Rejected
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    window.open_session_preferences("sync")

    assert observed["rows"] >= 40
    assert observed["headers"][-1] == "Proposed value"
    assert observed["native_watch"] == "1"
    assert window.conf.get("session_prefs", {}).get("exact-session-id") is None


def test_forward_session_settings_save_socket_proposal_only(monkeypatch, window):
    session = {
        "identifier": "exact-forward-id",
        "name": "Local Socket",
        "configurationDestination": {"socket": {"overwriteMode": "leave"}},
    }
    monkeypatch.setattr(window, "selected_session", lambda _kind: session)
    monkeypatch.setattr(window, "refresh_detail", lambda _kind: None)

    def propose_overwrite(dialog):
        table = dialog.findChild(QTableWidget)
        row = next(
            index
            for index in range(table.rowCount())
            if table.item(index, 0).text() == "Destination overwrite mode"
        )
        assert table.item(row, 1).text() == '"leave"'
        table.item(row, 5).setText("overwrite")
        dialog.findChild(QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", propose_overwrite)
    window.open_session_preferences("forward")

    stored = app_module.load_settings(app_module.settings_path()).values
    assert stored["session_prefs"]["exact-forward-id"]["forward_configuration_proposal"] == {
        "destination.socket.overwriteMode": "overwrite"
    }
    assert session["configurationDestination"]["socket"]["overwriteMode"] == "leave"


def test_ui_mode_switch_is_ephemeral_and_filters_advanced_navigation(window):
    settings_file = app_module.settings_path()
    assert not settings_file.exists()
    window.set_ui_mode("advanced")
    assert all(
        not button.isHidden()
        for route, button in zip(app_module.PAGE_ROUTES, window.nav, strict=True)
    )

    window.set_ui_mode("basic")
    for route, button in zip(app_module.PAGE_ROUTES, window.nav, strict=True):
        assert button.isHidden() is (route.route_id in app_module.ADVANCED_ROUTE_IDS)
    assert not settings_file.exists()


def test_language_switch_updates_navigation_page_header_and_returns_to_english(
    window, tmp_path, monkeypatch
):
    profile_dialog = app_module.ConnectionProfilesDialog(
        window, app_module.ConnectionProfileStore(tmp_path / "connection-profiles.json")
    )
    window.apply_snapshot(window.snapshot)
    window.update_server_groups()
    window.apply_ui_language("cs")
    window.set_page(10)
    window.update_server_details()

    tables = [
        *window.findChildren(app_module.QTableView),
        *window.findChildren(QTableWidget),
    ]
    assert tables
    missing_accessibility = [
        (type(table).__name__, table.objectName(), table.accessibleName())
        for table in tables
        if table.focusPolicy() != app_module.Qt.FocusPolicy.StrongFocus
        or not table.accessibleName()
    ]
    assert not missing_accessibility, missing_accessibility
    sync_table = next(
        table
        for table in tables
        if table.property("mutauiSourceAccessibleName") == "Sync sessions table"
    )
    assert sync_table.accessibleName() == "Tabulka synchronizačních relací"
    forwarding_model = window.forward_table.model()
    assert forwarding_model.headerData(0, app_module.Qt.Orientation.Horizontal) == "NÁZEV"
    assert forwarding_model.data(forwarding_model.index(0, 1)) == "Přesměrování aktivní"
    assert "přesměrování" in window.forward_summary.text()
    favorite_button = next(
        button
        for button in window.findChildren(app_module.QPushButton)
        if button.property("mutauiSourceText") == "☆ Add to Favorites"
    )
    assert favorite_button.text() == "☆ Přidat k oblíbeným"

    window.set_page(0)
    assert window.windowTitle() == "Mutagen Control 8.2 · Správce serverů"
    assert window.footer.text() == "DEMO • Všechny akce jsou vypnuté"
    assert window.daemon_title.text() == "●  Spuštěno"
    assert window.daemon_desc.text() == "Služba Mutagen odpovídá."
    assert window.server_overview.horizontalHeaderItem(1).text() == "SYNCHRONIZACE"
    assert window.server_selector.itemText(0) == "Všechny relace"
    assert window.server_scope_label.text().startswith("Všechny relace ·")
    assert window.page_name.text() == "Přehled"
    assert window.page_caption.text() == "Aktuální stav synchronizace a využití prostředků systému"
    assert window.nav[5].text().endswith("Nastavení")
    assert window.nav[5].toolTip() == "Ctrl+6 · Nastavení aplikace"
    assert window.mode_selector.itemText(0) == "Základní"
    assert window.nav_section_labels["overview"].text() == "PRACOVNÍ PROSTOR"
    assert window.side_state.text() == "●  Služba Mutagen je spuštěna"
    assert window.side_sub.text() == "3 relace · 1 přesměrování"
    file_dialog_args = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args: file_dialog_args.append(args) or ("", ""),
    )
    window.choose_onboarding_cli()
    assert file_dialog_args[0][1] == "Vyberte spustitelný soubor Mutagenu"
    assert file_dialog_args[0][3] == "Všechny soubory (*)"
    window.set_page(5)
    settings_labels = {
        widget.property("mutauiSourceText"): widget.text()
        for widget in window.findChildren(app_module.QLabel)
        if isinstance(widget.property("mutauiSourceText"), str)
    }
    assert settings_labels["Display and Language"] == "Zobrazení a jazyk"
    assert settings_labels["Connection Profiles"] == "Profily připojení"
    assert settings_labels["Session Refresh"] == "Obnovování relací"
    assert window.binary_edit.placeholderText().endswith("(nebo prázdné = PATH)")
    checkbox_texts = {
        widget.property("mutauiSourceText"): widget.text()
        for widget in window.findChildren(app_module.QCheckBox)
        if isinstance(widget.property("mutauiSourceText"), str)
    }
    assert checkbox_texts["Minimize on close"] == "Při zavření minimalizovat"
    assert checkbox_texts["Enable power-saving mode"] == "Zapnout úsporný režim"
    assert all(
        widget.wordWrap()
        for widget in window.findChildren(app_module.QLabel)
        if isinstance(widget.property("mutauiSourceText"), str)
        and len(widget.property("mutauiSourceText")) >= 72
    )
    actions = {
        widget.property("mutauiSourceText"): widget.text()
        for widget in window.findChildren(app_module.QAction)
        if isinstance(widget.property("mutauiSourceText"), str)
    }
    assert actions["Open Mutagen Control"] == "Otevřít Mutagen Control"
    assert profile_dialog.kind_filter.itemText(0) == "Všechny typy"

    window.apply_ui_language("en")
    assert sync_table.accessibleName() == "Sync sessions table"
    assert forwarding_model.headerData(0, app_module.Qt.Orientation.Horizontal) == "NAME"
    assert forwarding_model.data(forwarding_model.index(0, 1)) == "Forwarding active"
    assert favorite_button.text() == "☆ Add to Favorites"
    assert window.windowTitle() == "Mutagen Control 8.2 · Server Manager"
    assert window.footer.text() == "DEMO • All actions are disabled"
    assert window.page_name.text() == "Settings"
    assert window.server_overview.horizontalHeaderItem(1).text() == "SYNC"
    assert window.server_selector.itemText(0) == "All Sessions"
    assert window.server_scope_label.text().startswith("All Sessions ·")
    assert window.nav[5].text().endswith("Settings")
    assert window.binary_edit.placeholderText().endswith("(or blank = PATH)")
    assert profile_dialog.kind_filter.itemText(0) == "All types"
    assert (
        next(
            widget.text()
            for widget in window.findChildren(app_module.QCheckBox)
            if widget.property("mutauiSourceText") == "Minimize on close"
        )
        == "Minimize on close"
    )
    assert (
        next(
            widget.text()
            for widget in window.findChildren(app_module.QCheckBox)
            if widget.property("mutauiSourceText") == "Enable power-saving mode"
        )
        == "Enable power-saving mode"
    )
    assert app_module._czech_plural(1, ("jedna", "několik", "mnoho")) == "jedna"
    assert app_module._czech_plural(3, ("jedna", "několik", "mnoho")) == "několik"
    assert app_module._czech_plural(12, ("jedna", "několik", "mnoho")) == "mnoho"
    profile_dialog.close()


def test_settings_page_does_not_require_horizontal_scrolling(window, qapp):
    window.resize(1380, 900)
    window.show()
    window.set_ui_mode("advanced")
    window.set_page(5)
    qapp.processEvents()

    settings = window.pages.widget(5)
    assert settings.horizontalScrollBar().maximum() == 0


def test_onboarding_wizard_is_explicit_and_finish_persists_only_local_completion(window):
    settings_file = app_module.settings_path()
    assert not settings_file.exists()

    window.open_onboarding()
    wizard = window.onboarding_wizard
    assert len(wizard.pageIds()) == 3
    assert not settings_file.exists()

    wizard.accept()
    assert app_module.read_settings()["onboarding_completed"] is True
    wizard.close()


def test_onboarding_release_check_requires_explicit_opt_in(window):
    window.open_onboarding()
    wizard = window.onboarding_wizard

    assert window.onboarding_update_check.isChecked() is False
    window.onboarding_update_check.setChecked(True)
    wizard.accept()

    settings = app_module.read_settings()
    assert settings["onboarding_completed"] is True
    assert settings["check_updates_on_startup"] is True
    wizard.close()


def test_manual_release_check_requires_opt_in_and_uses_public_metadata(window, monkeypatch):
    from mutaui.services.update_checker import UpdateCheckResult

    window.demo = False
    page = window.alerts_page()
    assert page is not None
    requests = []

    def fake_check_for_update(*, current_version, enabled):
        requests.append((current_version, enabled))
        return UpdateCheckResult(
            latest_version="8.3.0",
            available=True,
            release_url="https://github.com/Harfusha/MutaUI/releases/tag/v8.3.0",
        )

    def inline_submit(func, on_result, on_error=None, on_done=None):
        try:
            on_result(func())
        except Exception as exc:
            if on_error is not None:
                on_error(str(exc))
        finally:
            if on_done is not None:
                on_done()

    monkeypatch.setattr(app_module, "check_for_update", fake_check_for_update)
    monkeypatch.setattr(window, "submit", inline_submit)

    window.check_for_release_update()
    assert requests == []
    assert window.update_check_button.isEnabled() is False

    window.check_updates_on_startup.setChecked(True)
    assert window.update_check_button.isEnabled() is True
    window.check_for_release_update()

    assert requests == [(app_module.APP_VERSION, True)]
    assert window.update_status_label.text() == "A newer release is available: v8.3.0."


def test_startup_release_check_requires_saved_opt_in_and_can_run_without_alerts_page(
    window, monkeypatch
):
    submitted = []

    def collect_submit(func, _on_result, _on_error=None, _on_done=None):
        submitted.append(func)

    monkeypatch.setattr(window, "submit", collect_submit)
    window.check_for_release_update_on_startup()
    assert submitted == []

    window.demo = False
    window.conf.update(onboarding_completed=True, check_updates_on_startup=False)
    window.check_for_release_update_on_startup()
    assert submitted == []

    window.conf["check_updates_on_startup"] = True
    window.check_for_release_update_on_startup()
    assert len(submitted) == 1
    assert window._release_check_running is True

    window.check_for_release_update(startup=True)
    assert len(submitted) == 1
    window._release_check_finished()
    assert window._release_check_running is False


def test_release_check_status_covers_pending_error_and_latest_states(window):
    from mutaui.services.update_checker import UpdateCheckResult

    window.refresh_release_check_status()
    page = window.alerts_page()
    assert page is not None
    assert window.update_status_label.text() == "Update status has not been checked."

    window._release_check_running = True
    window.refresh_release_check_status()
    assert window.update_status_label.text() == "Checking for releases…"
    window._release_check_running = False

    window._release_check_error = True
    window.refresh_release_check_status()
    assert window.update_status_label.text() == "Release check failed. See GitHub Releases."
    window._release_check_error = False

    window._release_check_result = UpdateCheckResult(None, False, None)
    window.refresh_release_check_status()
    assert window.update_status_label.text() == "Update status has not been checked."

    window._release_check_result = UpdateCheckResult("8.3.0", False, None)
    window.refresh_release_check_status()
    assert window.update_status_label.text() == "Latest published release: v8.3.0."

    window.open_release_button = None
    window.refresh_release_check_status()


def test_release_check_preference_save_persists_onboarding_choice(window, monkeypatch):
    page = window.alerts_page()
    assert page is not None
    errors = []
    monkeypatch.setattr(window, "report_error", errors.append)
    window.check_updates_on_startup.setChecked(True)

    window.save_release_check_preference()

    assert errors == []
    assert app_module.read_settings()["check_updates_on_startup"] is True

    def fail_write(_settings):
        raise OSError("settings are read-only")

    monkeypatch.setattr(app_module, "write_settings", fail_write)
    window.check_updates_on_startup.setChecked(False)
    window.save_release_check_preference()
    assert errors == ["settings are read-only"]


def test_release_check_handles_missing_optional_alert_widgets(window, monkeypatch):
    submitted = []
    window.demo = False
    window.conf["check_updates_on_startup"] = True
    window.update_check_button = None
    window.check_updates_on_startup = None
    del window.update_status_label
    monkeypatch.setattr(window, "submit", lambda *args: submitted.append(args))

    window.check_for_release_update(startup=True)
    assert len(submitted) == 1
    window._release_check_finished()
    window.refresh_release_check_status()


def test_session_dialog_validation_blocks_missing_and_risky_inputs(window, monkeypatch):
    warnings = []
    warning_text = []

    def reject_warning(*args):
        warnings.append(args[1])
        warning_text.append(args[2])
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        reject_warning,
    )
    dialog = app_module.SessionDialog("sync", window, ui_mode="advanced")
    dialog.validate()
    assert warnings == ["Invalid Endpoint"]
    assert dialog.result() == 0

    dialog.a.setText("C:/source")
    dialog.b.setText("user@host:/target")
    dialog.mode.setCurrentText("two-way-resolved")
    dialog.validate()
    assert warnings[-1] == "Risky Mode"
    assert "ALPHA" in warning_text[-1]
    assert dialog.result() == 0

    dialog.mode.setCurrentText("one-way-replica")
    assert not dialog.replica_backup.isHidden()
    assert dialog.backup_choice is None
    dialog.validate()
    assert warnings[-1] == "Risky Mode"
    assert "delete" in warning_text[-1].lower()
    assert dialog.result() == 0

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    dialog.validate()
    assert dialog.result() == 0
    dialog.replica_backup.setChecked(True)
    dialog.validate()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.backup_choice == "operator-confirmed-recoverable-beta-backup"
    dialog.close()


def test_message_dialog_static_copy_uses_active_language(window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: seen.append(args) or QMessageBox.StandardButton.No,
    )
    window.apply_ui_language("cs")
    dialog = app_module.SessionDialog("sync", window, ui_mode="advanced")
    dialog.validate()

    assert seen[0][1] == "Neplatný koncový bod"
    assert seen[0][2] == "Zadejte oba koncové body."
    dialog.close()
    window.apply_ui_language("en")


def test_session_dialog_arguments_drop_blank_ignores(window):
    dialog = app_module.SessionDialog("sync", window)
    dialog.name.setText(" nightly ")
    dialog.pause.setChecked(True)
    dialog.ignore_vcs.setChecked(True)
    dialog.ignore.setPlainText(" *.tmp \n\n cache \n")
    dialog.a.setText(" C:/source ")
    dialog.b.setText(" user@host:/target ")

    arguments = dialog.arguments()
    assert "--name=nightly" in arguments
    assert "--paused" in arguments
    assert "--ignore-vcs" in arguments
    assert "--ignore=*.tmp" in arguments
    assert "--ignore=cache" in arguments
    assert "--ignore=" not in arguments
    assert arguments[-2:] == ["C:/source", "user@host:/target"]
    dialog.close()


def test_advanced_forward_dialog_builds_endpoint_specific_socket_options(window):
    dialog = app_module.SessionDialog("forward", window, ui_mode="advanced")
    dialog.a.setText("unix:/tmp/source.sock")
    dialog.b.setText("unix:/tmp/destination.sock")
    dialog.socket_overwrite_source.setCurrentIndex(1)
    dialog.socket_owner_source.setText("service")
    dialog.socket_group_destination.setText("operators")
    dialog.socket_permission_destination.setText("0660")

    arguments = dialog.arguments()

    assert "--socket-overwrite-mode-source=overwrite" in arguments
    assert "--socket-owner-source=service" in arguments
    assert "--socket-group-destination=operators" in arguments
    assert "--socket-permission-mode-destination=0660" in arguments
    assert arguments[-2:] == ["unix:/tmp/source.sock", "unix:/tmp/destination.sock"]
    dialog.close()


def test_forward_socket_options_require_matching_unix_endpoint(window):
    dialog = app_module.SessionDialog("forward", window, ui_mode="advanced")
    dialog.a.setText("tcp:localhost:8080")
    dialog.b.setText("tcp:localhost:8081")
    dialog.socket_owner_source.setText("service")

    error = dialog.forward_socket_error()

    assert error == app_module.translate_text(
        "Socket settings for {side} require a Unix socket endpoint.",
        app_module.active_language(),
    ).format(side="Source")
    dialog.close()


def test_basic_forward_dialog_defaults_unix_socket_overwrite_to_leave(window):
    dialog = app_module.SessionDialog("forward", window)
    dialog.a.setText("unix:/tmp/source.sock")
    dialog.b.setText("tcp:localhost:8080")

    assert "--socket-overwrite-mode=leave" in dialog.arguments()
    dialog.close()


def test_forward_overwrite_blocks_local_directory_before_action_plan(window, tmp_path):
    directory = tmp_path / "keep-this-directory"
    directory.mkdir()
    dialog = app_module.SessionDialog("forward", window, ui_mode="advanced")
    dialog.a.setText(f"unix:{directory}")
    dialog.b.setText("tcp:localhost:8080")
    dialog.socket_overwrite_source.setCurrentIndex(1)

    error = dialog.forward_socket_error()

    assert error == app_module.translate_text(
        "A directory already exists at the local socket path; overwrite is blocked.",
        app_module.active_language(),
    )
    assert directory.is_dir()
    dialog.close()


def test_sync_dialog_inherits_global_vcs_and_can_override_it(window):
    dialog = app_module.SessionDialog("sync", window)

    assert dialog.ignore_vcs.checkState() == app_module.Qt.CheckState.PartiallyChecked
    assert "--ignore-vcs" not in dialog.arguments()
    assert "--no-ignore-vcs" not in dialog.arguments()

    dialog.ignore_vcs.setCheckState(app_module.Qt.CheckState.Unchecked)
    assert "--no-ignore-vcs" in dialog.arguments()
    dialog.ignore_vcs.setCheckState(app_module.Qt.CheckState.Checked)
    assert "--ignore-vcs" in dialog.arguments()
    assert "--no-ignore-vcs" not in dialog.arguments()
    dialog.close()


def test_effective_sync_preview_shows_global_values_and_appended_cli_ignores(
    window, tmp_path, monkeypatch
):
    (tmp_path / ".mutagen.yml").write_text(
        "sync:\n  defaults:\n    mode: one-way-safe\n    ignore:\n      paths:\n        - '*.log'\n      vcs: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module.Path, "home", lambda: tmp_path)
    seen = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: seen.append(args[2]),
    )
    dialog = app_module.SessionDialog("sync", window)
    dialog.ignore.setPlainText("*.tmp")

    dialog.preview_effective_session_configuration()

    assert any(
        line.startswith('mode = "two-way-safe"') and line.endswith("[command line]")
        for line in seen[0].splitlines()
    )
    assert any('ignore.paths = ["*.log", "*.tmp"]' in line for line in seen[0].splitlines())
    assert "[global config + command line (appended)]" in seen[0]
    assert any(
        line.startswith("ignore.vcs = true") and line.endswith("[global config]")
        for line in seen[0].splitlines()
    )
    assert "New standalone sync only" in seen[0]
    dialog.close()


def test_effective_forward_preview_shows_global_socket_defaults(window, tmp_path, monkeypatch):
    (tmp_path / ".mutagen.yml").write_text(
        "forward:\n  defaults:\n    socket:\n      overwriteMode: overwrite\n      owner: operator\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module.Path, "home", lambda: tmp_path)
    seen = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: seen.append(args[2]))
    dialog = app_module.SessionDialog("forward", window)

    dialog.preview_effective_session_configuration()

    assert 'socket.overwriteMode = "overwrite"' in seen[0]
    assert 'socket.owner = "operator"' in seen[0]
    assert "New standalone forward only" in seen[0]
    dialog.close()


def test_creation_wizard_mode_preview_and_ignore_presets(window):
    basic = app_module.SessionDialog("sync", window, ui_mode="basic", executable="mutagen.exe")
    assert [basic.mode.itemText(i) for i in range(basic.mode.count())] == [
        "two-way-safe",
        "one-way-safe",
    ]
    basic.a.setText("C:/source")
    basic.b.setText("user@host:/target")
    basic.name.setText("  sample  ")
    basic.profile.setCurrentIndex(basic.profile.findData("fast_poll"))
    basic.apply_ignore_preset(basic.ignore_preset.findText("Node.js"))
    preview = json.loads(basic.command_preview.toPlainText())
    assert preview[:4] == ["mutagen.exe", "sync", "create", "--name=sample"]
    assert "--watch-mode=force-poll" in preview
    assert "--ignore=node_modules/" in preview
    basic.close()

    advanced = app_module.SessionDialog("sync", window, ui_mode="advanced")
    assert "one-way-replica" in [advanced.mode.itemText(i) for i in range(advanced.mode.count())]
    advanced.close()


def test_quick_ignore_explains_when_no_local_sync_root_is_available(window, monkeypatch):
    session = {
        "identifier": "sync-remote-only",
        "name": "Remote only",
        "alpha": None,
        "beta": {"protocol": 1, "host": "remote.example", "path": "/srv/data"},
    }
    window.apply_snapshot(app_module.Snapshot(binary=window.client.binary, sync=[session]))
    row = window.sync_table.model().row_for_identifier(session["identifier"])
    window.sync_table.selectRow(row)
    window.sync_table.setCurrentIndex(window.sync_table.model().index(row, 0))
    dialogs = []
    messages = []
    monkeypatch.setattr(app_module.QDialog, "exec", lambda dialog: dialogs.append(dialog) or 0)
    monkeypatch.setattr(
        QMessageBox, "information", lambda *args: messages.append((args[1], args[2]))
    )

    window.open_session_preferences("sync")
    quick_ignore = next(
        button
        for button in dialogs[-1].findChildren(QPushButton)
        if "Quick Ignore" in button.text()
    )
    quick_ignore.click()

    assert messages[0][0] == "Quick Ignore unavailable"
    assert "No local sync endpoint" in messages[0][1]


@pytest.mark.parametrize("existing_rules", [[], ["nested/data file.txt"]])
def test_quick_ignore_drafts_root_relative_rule_without_writing_config(
    tmp_path, window, monkeypatch, existing_rules
):
    root = tmp_path / "sync-root"
    root.mkdir()
    target = root / "nested" / "data file.txt"
    target.parent.mkdir()
    target.write_text("private data", encoding="utf-8")
    session = {
        "identifier": "sync-local-source",
        "name": "Local source",
        "alpha": {"protocol": 0, "path": str(root)},
        "beta": {"protocol": 1, "host": "remote.example", "path": "/srv/data"},
        "ignore": {"paths": existing_rules},
    }
    window.apply_snapshot(app_module.Snapshot(binary=window.client.binary, sync=[session]))
    row = window.sync_table.model().row_for_identifier(session["identifier"])
    window.sync_table.selectRow(row)
    window.sync_table.setCurrentIndex(window.sync_table.model().index(row, 0))
    dialogs = []
    monkeypatch.setattr(app_module.QDialog, "exec", lambda dialog: dialogs.append(dialog) or 0)
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(target), "All files (*)"),
    )

    window.open_session_preferences("sync")
    dialog = dialogs[-1]
    quick_ignore = next(
        button for button in dialog.findChildren(QPushButton) if "Quick Ignore" in button.text()
    )
    quick_ignore.click()

    config_table = next(
        table
        for table in dialog.findChildren(QTableWidget)
        if any(
            table.item(row_index, 0) and "ignore" in table.item(row_index, 0).text().casefold()
            for row_index in range(table.rowCount())
        )
    )
    ignore_row = next(
        row_index
        for row_index in range(config_table.rowCount())
        if config_table.item(row_index, 0)
        and "ignore" in config_table.item(row_index, 0).text().casefold()
    )
    assert json.loads(config_table.item(ignore_row, 5).text()) == ["nested/data file.txt"]
    assert not (app_module.settings_path().with_name("mutagen.yml")).exists()


def test_creation_wizard_loads_custom_ignore_presets_and_discloses_store_warning(tmp_path, window):
    from ignore_presets import IgnorePresetStore

    preset_path = app_module.settings_path().with_name("ignore-presets.json")
    IgnorePresetStore(preset_path).create("Node.js", ("custom-build/",))
    dialog = app_module.SessionDialog("sync", window)
    assert dialog.ignore_presets["Node.js (custom)"] == ("custom-build/",)
    dialog.close()

    preset_path.write_text("{ invalid", encoding="utf-8")
    warning_dialog = app_module.SessionDialog("sync", window)
    assert warning_dialog.ignore_store_warning
    warning_dialog.close()


def test_apply_snapshot_updates_optional_diagnostics_and_missing_version(window, monkeypatch):
    observed = []
    window.diagnostics_view = object()
    monkeypatch.setattr(window, "update_diagnostics", lambda snapshot: observed.append(snapshot))
    snapshot = app_module.Snapshot(binary=window.client.binary)

    window.apply_snapshot(snapshot)

    assert observed == [snapshot]
    assert window._version_label_text == "Version: unavailable"


def test_creation_wizard_rejects_invalid_forward_endpoint_and_warns_on_public_bind(
    window, monkeypatch
):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[1]) or QMessageBox.StandardButton.No,
    )
    dialog = app_module.SessionDialog("forward", window, executable="mutagen.exe")
    dialog.a.setText("tcp:localhost:70000")
    dialog.b.setText("tcp:localhost:9000")
    dialog.validate()
    assert warnings == ["Invalid Endpoint"]
    assert dialog.result() == 0

    dialog.a.setText("tcp:0.0.0.0:8080")
    dialog.validate()
    assert warnings[-1] == "Public Forwarding Listener"
    assert dialog.result() == 0
    dialog.close()


@pytest.mark.parametrize(
    ("response", "expected_result"),
    [
        (QMessageBox.StandardButton.No, 0),
        (QMessageBox.StandardButton.Yes, QDialog.DialogCode.Accepted),
    ],
)
def test_public_forwarding_listener_requires_explicit_confirmation(
    window, monkeypatch, response, expected_result
):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[1]) or response,
    )
    dialog = app_module.SessionDialog("forward", window, executable="mutagen.exe")
    dialog.a.setText("tcp:0.0.0.0:8080")
    dialog.b.setText("tcp:localhost:9000")

    dialog.validate()

    assert warnings == ["Public Forwarding Listener"]
    assert dialog.result() == expected_result
    dialog.close()


def test_connection_profile_manager_filters_and_session_wizard_applies_profile(tmp_path, window):
    store = app_module.ConnectionProfileStore(tmp_path / "connection-profiles.json")
    work = store.create(
        "Python service",
        "C:/source",
        "dev@example:/srv/app",
        kind="sync",
        tags=("work", "python"),
        favorite=True,
        defaults={
            "watch.mode": "force-poll",
            "watch.pollingInterval": 20,
            "ignore.paths": ["__pycache__/"],
        },
    )
    store.create("Forward profile", "tcp:localhost:8000", "tcp:localhost:80", kind="forward")

    manager = app_module.ConnectionProfilesDialog(window, store)
    assert manager.table.rowCount() == 2
    manager.search_input.setText("python")
    assert manager.table.rowCount() == 1
    assert manager.table.item(0, 0).data(app_module.Qt.ItemDataRole.UserRole).id == work.id
    manager.close()

    wizard = app_module.SessionDialog("sync", window, saved_profiles=(work,))
    wizard.connection_profile.setCurrentIndex(1)
    assert wizard.name.text() == "Python service"
    assert wizard.a.text() == "C:/source"
    assert wizard.b.text() == "dev@example:/srv/app"
    assert wizard.ignore.toPlainText() == "__pycache__/"
    assert wizard.profile.currentData() == "balanced_poll"
    wizard.close()


@pytest.mark.parametrize(
    ("watch", "interval", "expected_profile"),
    [
        ("portable", None, "events"),
        ("force-poll", 5, "fast_poll"),
        ("force-poll", 60, "eco_poll"),
        ("no-watch", None, "manual"),
        ("unrecognized", 12, "default"),
    ],
)
def test_sync_connection_profile_maps_supported_watch_defaults(
    tmp_path, window, watch, interval, expected_profile
):
    defaults = {"watch.mode": watch}
    if interval is not None:
        defaults["watch.pollingInterval"] = interval
    profile = app_module.ConnectionProfile(
        id="profile-id",
        name="Profile",
        kind="sync",
        endpoint_a="./alpha",
        endpoint_b="./beta",
        defaults=defaults,
    )
    wizard = app_module.SessionDialog("sync", window, saved_profiles=(profile,))

    wizard.connection_profile.setCurrentIndex(1)

    assert wizard.profile.currentData() == expected_profile
    wizard.close()


def test_sync_connection_profile_ignores_malformed_optional_defaults(window):
    profile = app_module.ConnectionProfile(
        id="malformed-profile-id",
        name="Profile",
        kind="sync",
        endpoint_a="./alpha",
        endpoint_b="./beta",
        defaults={
            "mode": "unknown-mode",
            "ignore.paths": "not-a-list",
            "ignore.vcs": "true",
            "watch.mode": "force-poll",
            "watch.pollingInterval": 20,
        },
    )
    wizard = app_module.SessionDialog("sync", window, saved_profiles=(profile,))
    original_mode = wizard.mode.currentText()
    original_ignore = wizard.ignore.toPlainText()
    original_ignore_vcs = wizard.ignore_vcs.isChecked()

    wizard.connection_profile.setCurrentIndex(1)

    assert wizard.name.text() == "Profile"
    assert wizard.a.text() == "./alpha"
    assert wizard.b.text() == "./beta"
    assert wizard.mode.currentText() == original_mode
    assert wizard.ignore.toPlainText() == original_ignore
    assert wizard.ignore_vcs.isChecked() is original_ignore_vcs
    assert wizard.profile.currentData() == "balanced_poll"
    wizard.close()


def test_sync_connection_profile_applies_valid_defaults_and_skips_missing_profile_choice(
    window, monkeypatch
):
    profile = app_module.ConnectionProfile(
        id="valid-profile-id",
        name="Profile",
        kind="sync",
        endpoint_a="./alpha",
        endpoint_b="./beta",
        defaults={
            "mode": "two-way-safe",
            "ignore.paths": [".git", "build"],
            "ignore.vcs": True,
            "watch.mode": "force-poll",
            "watch.pollingInterval": 20,
        },
    )
    wizard = app_module.SessionDialog("sync", window, saved_profiles=(profile,))
    monkeypatch.setattr(wizard.profile, "findData", lambda _code: -1)

    wizard.connection_profile.setCurrentIndex(1)

    assert wizard.mode.currentText() == "two-way-safe"
    assert wizard.ignore.toPlainText() == ".git\nbuild"
    assert wizard.ignore_vcs.isChecked()
    wizard.close()


def test_session_wizard_browse_alpha_applies_selected_directory(window, monkeypatch, tmp_path):
    selected = str(tmp_path / "new-source")
    monkeypatch.setattr(app_module.QFileDialog, "getExistingDirectory", lambda *_args: selected)
    wizard = app_module.SessionDialog("sync", window)

    wizard.browse_alpha()

    expected = selected.replace("/", "\\") if os.name == "nt" else selected
    assert wizard.a.text() == expected
    wizard.close()


def test_forward_connection_profile_does_not_apply_sync_defaults(tmp_path, window):
    profile = app_module.ConnectionProfile(
        id="forward-profile-id",
        name="Forward",
        kind="forward",
        endpoint_a="tcp:localhost:8000",
        endpoint_b="tcp:localhost:80",
        defaults={},
    )
    wizard = app_module.SessionDialog("forward", window, saved_profiles=(profile,))

    wizard.connection_profile.setCurrentIndex(1)

    assert wizard.name.text() == "Forward"
    assert wizard.a.text() == "tcp:localhost:8000"
    assert wizard.b.text() == "tcp:localhost:80"
    wizard.close()


def test_session_wizard_ignores_missing_or_malformed_selected_profile(window):
    wizard = app_module.SessionDialog("sync", window)
    original = (wizard.name.text(), wizard.a.text(), wizard.b.text())

    wizard.connection_profile = None
    wizard.apply_connection_profile()
    wizard.connection_profile = app_module.QComboBox()
    wizard.connection_profile.addItem("Malformed", {"name": "not a profile"})
    wizard.connection_profile.setCurrentIndex(0)
    wizard.apply_connection_profile()

    assert (wizard.name.text(), wizard.a.text(), wizard.b.text()) == original
    wizard.close()


def test_connection_profile_manager_creates_and_selects_profile(window, monkeypatch, tmp_path):
    store = app_module.ConnectionProfileStore(tmp_path / "profiles.json")
    manager = app_module.ConnectionProfilesDialog(window, store)

    def accept(dialog):
        name, endpoint_a, endpoint_b, tags = dialog.findChildren(app_module.QLineEdit)
        name.setText("Created profile")
        endpoint_a.setText("./alpha")
        endpoint_b.setText("./beta")
        tags.setText("work, python")
        dialog.findChild(app_module.QPlainTextEdit).setPlainText('{"mode":"two-way-safe"}')
        dialog.findChild(app_module.QComboBox).setCurrentIndex(0)
        return app_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module.QDialog, "exec", accept)

    manager.new_profile()

    assert manager.table.rowCount() == 1
    created = manager.table.item(0, 0).data(app_module.Qt.ItemDataRole.UserRole)
    assert created.name == "Created profile"
    assert created.tags == ("work", "python")
    assert manager.table.selectionModel().hasSelection()
    manager.close()


@pytest.mark.parametrize("raw_defaults", ["not-json", "[]"])
def test_connection_profile_manager_rejects_invalid_defaults(
    window, monkeypatch, tmp_path, raw_defaults
):
    store = app_module.ConnectionProfileStore(tmp_path / "profiles.json")
    manager = app_module.ConnectionProfilesDialog(window, store)
    warnings = []

    def accept_invalid(dialog):
        name, endpoint_a, endpoint_b, _tags = dialog.findChildren(app_module.QLineEdit)
        name.setText("Invalid profile")
        endpoint_a.setText("./alpha")
        endpoint_b.setText("./beta")
        dialog.findChild(app_module.QPlainTextEdit).setPlainText(raw_defaults)
        return app_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr(app_module.QDialog, "exec", accept_invalid)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    manager.new_profile()

    assert len(warnings) == 1
    assert store.profiles == []
    manager.close()


@pytest.mark.parametrize("kind", ["sync", "forward"])
def test_open_group_session_selects_exact_session_and_resets_kind_filters(kind):
    events = []

    class Item:
        def __init__(self, identifier):
            self.identifier = identifier

        def data(self, _role):
            return self.identifier

    class Listing:
        def item(self, _row, _column):
            return Item("exact-group-id")

    class Table:
        rows = [None, Item("other-id"), Item("exact-group-id")]

        def rowCount(self):
            return len(self.rows)

        def item(self, row, _column):
            return self.rows[row]

        def selectRow(self, row):
            events.append(("select", row))

        def scrollToItem(self, item):
            events.append(("scroll", item.identifier))

    class Filter:
        def setCurrentIndex(self, index):
            events.append(("filter", index))

        def clear(self):
            events.append(("clear",))

        def setChecked(self, value):
            events.append(("checked", value))

    fake = SimpleNamespace(
        server_sync_table=Listing(),
        server_forward_table=Listing(),
        sync_table=Table(),
        forward_table=Table(),
        sync_server_filter=Filter(),
        sync_search=Filter(),
        sync_state_filter=Filter(),
        sync_favorites_only=Filter(),
        forward_search=Filter(),
        forward_state_filter=Filter(),
        forward_favorites_only=Filter(),
        set_page=lambda page: events.append(("page", page)),
    )

    app_module.MainWindow.open_group_session(fake, kind, 0)

    assert ("page", 1 if kind == "sync" else 2) in events
    assert ("select", 2) in events
    assert ("scroll", "exact-group-id") in events


def test_open_group_session_ignores_empty_group_row():
    events = []

    class Listing:
        def item(self, _row, _column):
            return None

    fake = SimpleNamespace(
        server_sync_table=Listing(),
        server_forward_table=Listing(),
        set_page=lambda page: events.append(page),
    )

    app_module.MainWindow.open_group_session(fake, "sync", 0)

    assert events == []


def test_session_dialog_sync_endpoint_validation_matrix(window):
    wizard = app_module.SessionDialog("sync", window, ui_mode="basic", executable="mutagen")
    invalid = {
        "  ": "Enter both endpoints",
        "-all": "option-like value",
        "bad\x00endpoint": "invalid NUL",
        "ssh://host/path": "native SSH form",
        "docker://": "container name or path",
        "user@example.org": "path after the host",
    }

    for endpoint, message in invalid.items():
        assert message in wizard.endpoint_error(endpoint)
    assert wizard.endpoint_error("./local") is None
    assert wizard.endpoint_error("user@example.org:/srv/app") is None
    assert wizard.endpoint_error("docker://container/app") is None
    wizard.close()


def test_session_dialog_forward_endpoint_validation_matrix(window, monkeypatch):
    wizard = app_module.SessionDialog("forward", window, executable="mutagen")
    monkeypatch.setattr(
        app_module.SessionDialog,
        "local_unix_socket_supported",
        staticmethod(lambda: False),
    )
    monkeypatch.setattr(app_module, "os", SimpleNamespace(name="posix"))

    invalid = {
        "tcp:localhost": "host and port",
        "tcp:localhost:nope": "host and a port",
        "tcp::80": "host and a port",
        "tcp:localhost:0": "host and a port",
        "unix:": "needs a path",
        "unix:/tmp/socket": "unavailable on this local platform",
        "npipe:////./pipe/name": "only on Windows endpoints",
        "docker://": "container and address",
    }
    for endpoint, message in invalid.items():
        assert message in wizard.endpoint_error(endpoint)

    assert wizard.endpoint_error("tcp:localhost:8080") is None
    assert wizard.endpoint_error("tcp6:::1:8080") is None
    wizard.close()


@pytest.mark.parametrize(
    ("os_name", "platform", "build", "expected"),
    [
        ("posix", "linux", None, True),
        ("nt", "win32", 17063, True),
        ("nt", "win32", 17062, False),
        ("nt", "win32", None, False),
        ("nt", "linux", None, False),
    ],
)
def test_session_dialog_local_unix_socket_capability_is_platform_gated(
    monkeypatch, os_name, platform, build, expected
):
    win = SimpleNamespace(build=build) if build is not None else None
    system = SimpleNamespace(platform=platform)
    if win is not None:
        system.getwindowsversion = lambda: win
    monkeypatch.setattr(app_module, "os", SimpleNamespace(name=os_name))
    monkeypatch.setattr(app_module, "sys", system)

    assert app_module.SessionDialog.local_unix_socket_supported() is expected


@pytest.mark.parametrize(
    ("demo", "pending", "session", "expected_questions"),
    [
        (True, False, {"identifier": "sync-1"}, 0),
        (False, True, {"identifier": "sync-1"}, 0),
        (False, False, None, 0),
        (False, False, {"identifier": ""}, 0),
    ],
)
def test_sync_startup_toggle_ignores_unavailable_targets(
    monkeypatch, demo, pending, session, expected_questions
):
    controller = SimpleNamespace(
        demo=demo,
        pending_action=pending,
        selected_session=lambda _kind: session,
        snapshot=SimpleNamespace(registration="registered"),
    )
    questions = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *args: questions.append(args) or app_module.QMessageBox.StandardButton.No,
    )

    app_module.MainWindow.toggle_sync_startup(controller)

    assert len(questions) == expected_questions


@pytest.mark.parametrize(
    ("paused", "registration", "answer", "expected_call"),
    [
        (False, "unregistered", "No", None),
        (False, "unregistered", "Yes", ("daemon", "register", {})),
        (False, "registered", "No", None),
        (False, "registered", "Yes", ("sync", "pause", {"target": "sync-1"})),
        (True, "unregistered", "No", None),
        (
            True,
            "unregistered",
            "Yes",
            ("sync", "resume", {"target": "sync-1", "register_before": True}),
        ),
        (
            True,
            "registered",
            None,
            ("sync", "resume", {"target": "sync-1", "register_before": False}),
        ),
    ],
)
def test_sync_startup_toggle_confirms_native_lifecycle_semantics(
    monkeypatch, paused, registration, answer, expected_call
):
    calls = []
    controller = SimpleNamespace(
        demo=False,
        pending_action=False,
        selected_session=lambda _kind: {"identifier": "sync-1", "paused": paused},
        snapshot=SimpleNamespace(registration=registration),
        run_command=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    response = {
        "Yes": app_module.QMessageBox.StandardButton.Yes,
        "No": app_module.QMessageBox.StandardButton.No,
        None: app_module.QMessageBox.StandardButton.No,
    }[answer]
    monkeypatch.setattr(app_module.QMessageBox, "question", lambda *_args: response)

    app_module.MainWindow.toggle_sync_startup(controller)

    if expected_call is None:
        assert calls == []
    else:
        action, subcommand, kwargs = expected_call
        assert calls == [((action, subcommand), kwargs)]


def test_ignore_import_is_cancel_safe_and_merges_previewed_rules(window, tmp_path, monkeypatch):
    path = tmp_path / ".dockerignore"
    path.write_bytes(b"ignored/\n")
    wizard = app_module.SessionDialog("sync", window, executable="mutagen")
    wizard.ignore.setPlainText("cache/\nexisting/")
    monkeypatch.setattr(app_module.QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    wizard.import_ignore_file()
    assert wizard.ignore.toPlainText() == "cache/\nexisting/"

    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(path), ""),
    )
    formats = []
    monkeypatch.setattr(
        app_module,
        "parse_ignore_file",
        lambda content, *, source_format: formats.append((content, source_format)) or object(),
    )

    class AcceptedPreview:
        def __init__(self, preview, _parent):
            self.preview = preview

        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

        def selected_patterns(self):
            return ["existing/", "new/", "!new/keep"]

    monkeypatch.setattr(app_module, "IgnoreConversionDialog", AcceptedPreview)
    wizard.import_ignore_file()

    assert formats == [(b"ignored/\n", "dockerignore")]
    assert wizard.ignore.toPlainText() == "cache/\nexisting/\nnew/\n!new/keep"
    wizard.close()


def test_ignore_import_reports_oversized_source_and_cancelled_conversion(
    window, tmp_path, monkeypatch
):
    path = tmp_path / ".gitignore"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    wizard = app_module.SessionDialog("sync", window, executable="mutagen")
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(path), ""),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda *_args: warnings.append(_args[2]),
    )
    wizard.import_ignore_file()
    assert "1 MiB size limit" in warnings[0]

    path.write_text("new/\n", encoding="utf-8")
    monkeypatch.setattr(
        app_module,
        "parse_ignore_file",
        lambda *_args, **_kwargs: object(),
    )

    class RejectedPreview:
        def __init__(self, _preview, _parent):
            pass

        def exec(self):
            return app_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "IgnoreConversionDialog", RejectedPreview)
    wizard.ignore.setPlainText("existing/")
    wizard.import_ignore_file()
    assert wizard.ignore.toPlainText() == "existing/"
    wizard.close()


def test_explain_ignore_dialog_cancel_does_not_read_configuration(window, monkeypatch):
    wizard = app_module.SessionDialog("sync", window, executable="mutagen")
    monkeypatch.setattr(app_module.QInputDialog, "getText", lambda *_args: ("", False))
    monkeypatch.setattr(
        app_module,
        "load_effective_sync_configuration",
        lambda *_args: pytest.fail("cancel must not read configuration"),
    )

    wizard.explain_ignore()

    wizard.close()


@pytest.mark.parametrize(
    ("vcs_origin", "vcs_active", "expect_global_vcs", "expect_session_vcs"),
    [
        ("global config", True, True, False),
        ("command line", True, False, True),
        ("built-in", True, False, False),
        ("global config", False, False, False),
    ],
)
def test_explain_ignore_respects_known_global_and_session_provenance(
    window,
    monkeypatch,
    vcs_origin,
    vcs_active,
    expect_global_vcs,
    expect_session_vcs,
):
    wizard = app_module.SessionDialog("sync", window, executable="mutagen")
    wizard.ignore.setPlainText("local/")
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getText",
        lambda *_args: ("build/cache", True),
    )

    class Preview:
        valid = True
        error = ""

        def __init__(self, values, origin=""):
            self.values = values
            self.origin = origin

        def as_mapping(self):
            return self.values

        def origin_for(self, _key):
            return self.origin

    previews = iter(
        [
            Preview({"ignore.paths": ("cache/",)}),
            Preview({"ignore.vcs": vcs_active}, vcs_origin),
        ]
    )
    monkeypatch.setattr(
        app_module,
        "load_effective_sync_configuration",
        lambda *_args: next(previews),
    )
    calls = []
    monkeypatch.setattr(
        app_module,
        "explain_ignore_path",
        lambda path, **layers: (
            calls.append((path, layers))
            or SimpleNamespace(ignored=True, matched_rule="cache/", scope="global", note="known")
        ),
    )
    monkeypatch.setattr(app_module, "format_ignore_layers", lambda **_layers: "layer preview")
    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda *args: messages.append(args[2]),
    )

    wizard.explain_ignore()

    assert len(calls) == 1
    assert calls[0][0] == "build/cache"
    global_rules = calls[0][1]["global_rules"]
    session_rules = calls[0][1]["session_rules"]
    assert (".git/" in global_rules) is expect_global_vcs
    assert (".git/" in session_rules) is expect_session_vcs
    assert "cache/" in global_rules
    assert "local/" in session_rules
    assert messages and "layer preview" in messages[0]
    wizard.close()


def test_explain_ignore_shows_warning_when_effective_configuration_is_invalid(window, monkeypatch):
    wizard = app_module.SessionDialog("sync", window, executable="mutagen")
    monkeypatch.setattr(app_module.QInputDialog, "getText", lambda *_args: ("build", True))
    invalid = SimpleNamespace(valid=False, error="invalid yaml")
    valid = SimpleNamespace(valid=True, error="", as_mapping=lambda: {}, origin_for=lambda _key: "")
    previews = iter([invalid, valid])
    monkeypatch.setattr(
        app_module,
        "load_effective_sync_configuration",
        lambda *_args: next(previews),
    )
    warnings = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )

    wizard.explain_ignore()

    assert warnings == ["invalid yaml"]
    wizard.close()


@pytest.mark.parametrize("kind", ["sync", "forward"])
def test_effective_session_preview_explains_empty_configuration(window, monkeypatch, kind):
    wizard = app_module.SessionDialog(kind, window, executable="mutagen")
    preview = SimpleNamespace(valid=True, source_path="C:/config/mutagen.yml", values=())
    calls = []

    def load(*args):
        calls.append(args)
        return preview

    loader = (
        "load_effective_sync_configuration"
        if kind == "sync"
        else "load_effective_forward_configuration"
    )
    monkeypatch.setattr(app_module, loader, load)
    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda *args: messages.append(args[2]),
    )

    wizard.preview_effective_session_configuration()

    assert len(calls) == 1
    assert calls[0][0].name == ".mutagen.yml"
    assert calls[0][1] == wizard.arguments()[:-2]
    assert "No explicit global or CLI configuration values." in messages[0]
    assert "C:/config/mutagen.yml" in messages[0]
    wizard.close()


def test_effective_session_preview_warns_when_native_configuration_is_invalid(window, monkeypatch):
    wizard = app_module.SessionDialog("sync", window, executable="mutagen")
    monkeypatch.setattr(
        app_module,
        "load_effective_sync_configuration",
        lambda *_args: SimpleNamespace(
            valid=False,
            source_path="C:/config/mutagen.yml",
            values=(),
            error="invalid source yaml",
        ),
    )
    warnings = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda *_args: pytest.fail("invalid preview must not show values"),
    )

    wizard.preview_effective_session_configuration()

    assert warnings == ["invalid source yaml"]
    wizard.close()


def test_settings_save_persists_and_refreshes(window, monkeypatch):
    window.set_page(5)
    saved = []
    refreshes = []
    monkeypatch.setattr(app_module, "write_settings", lambda value: saved.append(value.copy()))
    monkeypatch.setattr(window, "refresh", lambda **kwargs: refreshes.append(kwargs))
    window.interval_input.setValue(9)
    window.metric_interval_input.setCurrentIndex(window.metric_interval_input.findData(5))
    window.adaptive_input.setChecked(False)

    window.save_settings()

    assert saved[-1]["interval"] == 9
    assert saved[-1]["metric_interval"] == 5
    assert saved[-1]["adaptive_poll"] is False
    assert refreshes == [{"force": True}]


def test_invalid_binary_does_not_save_settings(window, monkeypatch):
    window.set_page(5)
    warnings = []
    writes = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1]))
    monkeypatch.setattr(app_module, "write_settings", lambda value: writes.append(value))
    window.binary_edit.setText("missing-mutagen.exe")

    window.save_settings()

    assert warnings == ["Invalid File"]
    assert writes == []


def test_failed_daemon_refresh_retains_last_successful_sessions(window):
    previous = window.snapshot
    previous.daemon = True
    window.demo = False

    window.apply_snapshot(app_module.Snapshot(binary=previous.binary, error="daemon stopped"))

    assert window.snapshot.sync == previous.sync
    assert window.snapshot.forward == previous.forward
    assert window.snapshot.sessions_stale is True
    assert "last successful sessions" in window.updated.text().lower()


def test_refresh_ignores_result_from_obsolete_generation(window, monkeypatch):
    callbacks = {}
    window.demo = False
    window.poll_backoff.can_retry = lambda _force: True
    monkeypatch.setattr(app_module, "MutagenClient", lambda binary: SimpleNamespace(binary=binary))
    monkeypatch.setattr(app_module, "read_registration", lambda _binary: ("registered", ""))

    def capture_submit(work, on_result, on_error=None, on_done=None):
        callbacks.update(work=work, result=on_result, error=on_error, done=on_done)

    monkeypatch.setattr(window, "submit", capture_submit)
    window.refresh(force=True)
    before = window.snapshot
    window._refresh_generation += 1

    callbacks["result"](app_module.Snapshot(binary=window.client.binary, daemon=True))

    assert window.snapshot is before


def test_apply_snapshot_ignores_explicit_stale_generation(window):
    before = window.snapshot
    window._refresh_generation = 4

    window.apply_snapshot(app_module.Snapshot(binary="new"), generation=3)

    assert window.snapshot is before


def test_apply_snapshot_marks_offline_and_partial_sessions_without_dropping_known_rows(
    window, monkeypatch
):
    window.demo = False
    monkeypatch.setattr(window.poll_backoff, "remaining", lambda: 4.0)
    previous = window.snapshot
    previous.daemon = True
    previous.sync = [{"identifier": "known-sync"}]
    previous.forward = [{"identifier": "known-forward"}]
    previous.sync_observed_at = datetime.now().astimezone()
    previous.forward_observed_at = datetime.now().astimezone()

    offline = app_module.Snapshot(binary=previous.binary)
    window.apply_snapshot(offline)
    assert window.snapshot.sync == previous.sync
    assert window.snapshot.forward == previous.forward
    assert window.snapshot.sessions_stale
    assert "showing last successful sessions" in window.updated.text().lower()

    partial = app_module.Snapshot(
        binary=previous.binary,
        daemon=True,
        sessions_stale=True,
        sync=[{"identifier": "fresh-sync"}],
        forward=[],
        error="forward list failed",
    )
    window.apply_snapshot(partial)
    assert window.snapshot.sync == [{"identifier": "fresh-sync"}]
    assert window.snapshot.forward == previous.forward
    assert window.snapshot.forward_observed_at == previous.forward_observed_at
    assert window.snapshot.sessions_stale
    assert "forward list failed" in window.updated.text()


def test_apply_snapshot_refreshes_version_cache_on_expiry(window, monkeypatch):
    window.demo = False
    now = iter((1000.0, 1000.0, 1000.0))
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(now))
    window._version_cache = ("0.17.0", 100.0, window.snapshot.binary)
    snapshot = app_module.Snapshot(
        binary=window.snapshot.binary,
        daemon=False,
        version="0.18.1",
        registration="unregistered",
    )

    window.apply_snapshot(snapshot)

    assert window._version_cache == ("0.18.1", 1000.0, snapshot.binary)


def test_apply_snapshot_fresh_daemon_updates_status_and_traffic(window, monkeypatch):
    window.demo = False
    alerts = []
    samples = []
    monkeypatch.setattr(window, "check_alerts", lambda snapshot: alerts.append(snapshot))
    monkeypatch.setattr(window.traffic_meter, "update", lambda rows: (12.0, 8.0))
    monkeypatch.setattr(window.poll_backoff, "observe", lambda alive: samples.append(alive))
    snapshot = app_module.Snapshot(
        binary=window.snapshot.binary,
        daemon=True,
        sessions_stale=False,
        version="0.18.1",
        registration="registered",
        sync=[{"identifier": "fresh-sync"}],
        forward=[{"identifier": "fresh-forward"}],
    )

    window.apply_snapshot(snapshot)

    assert window.snapshot is snapshot
    assert window.traffic_rates == (12.0, 8.0)
    assert window._traffic_sample_pending
    assert alerts == [snapshot]
    assert samples == [True]
    assert "Daemon online" in window.side_state.text()
    assert "Refreshed" in window.updated.text()


def test_apply_snapshot_offline_without_previous_sessions_shows_retry(window, monkeypatch):
    window.demo = False
    monkeypatch.setattr(window.poll_backoff, "remaining", lambda: 4.0)
    snapshot = app_module.Snapshot(binary="", daemon=False, sessions_stale=False)

    window.apply_snapshot(snapshot)

    assert "Daemon offline · retrying in 4 s" in window.updated.text()
    assert "Mutagen CLI not found" in window.side_state.text()


def test_history_does_not_repeat_old_forward_rates(window, monkeypatch):
    samples = []
    monkeypatch.setattr(window.history, "add", samples.append)
    window.demo = False
    window.recorder = None
    window.traffic_rates = (120.0, 75.0)
    window._traffic_sample_pending = True
    data = {
        "cpu": 1.0,
        "memory": 2048,
        "processes": 1,
        "read_rate": 0.0,
        "write_rate": 0.0,
        "gui_cpu": 0.0,
        "gui_memory": 4096,
    }

    window.apply_resource_metrics(data)
    window.apply_resource_metrics(data)

    assert (samples[0].forward_out_rate, samples[0].forward_in_rate) == (120.0, 75.0)
    assert samples[1].forward_out_rate is None
    assert samples[1].forward_in_rate is None


def test_demo_bulk_action_never_prompts_or_submits(window, monkeypatch):
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: calls.append("prompt"))
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: calls.append("submit"))

    window.bulk_action("sync", "pause")

    assert calls == []


def test_bulk_action_with_no_eligible_sessions_reports_empty_selection(window, monkeypatch):
    messages = []
    submissions = []
    window.demo = False
    window.snapshot.sync = [{"identifier": "paused-sync", "paused": True}]
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[1]))
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.bulk_action("sync", "flush", "all")

    assert messages == ["No Sessions"]
    assert submissions == []


def test_bulk_action_deduplicates_ids_and_honors_cancel(window, monkeypatch):
    prompts = []
    submissions = []
    window.demo = False
    window.snapshot.sync = [
        {"identifier": "sync-1", "paused": False},
        {"identifier": "sync-1", "paused": False},
        {"identifier": "", "paused": False},
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append(args[2]) or QMessageBox.StandardButton.No,
    )
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.bulk_action("sync", "pause", "all")

    assert "1 selected sessions" in prompts[0]
    assert submissions == []


def test_terminate_requires_typed_second_confirmation(window, monkeypatch):
    window.demo = False
    window.snapshot.sync = [{"identifier": "sync-1", "paused": False}]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(app_module.QInputDialog, "getText", lambda *args: ("terminate", True))
    submissions = []
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.bulk_action("sync", "terminate", "all")

    assert submissions == []
    assert window.pending_action is False


def test_bulk_pause_submits_only_explicit_unique_ids(window, monkeypatch):
    calls = []
    window.demo = False
    window.snapshot.sync = [
        {"identifier": "sync-1", "paused": False},
        {"identifier": "sync-1", "paused": False},
    ]
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)

    class FakeClient:
        def __init__(self, _binary, *, action_planner=None):
            pass

        def execute_many(self, kind, action, ids, **kwargs):
            calls.append((kind, action, ids, kwargs))
            return "accepted"

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(window, "refresh", lambda **kwargs: calls.append(("refresh", kwargs)))

    def run_worker(func, on_result, on_error=None, on_done=None):
        result = func()
        on_result(result)
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", run_worker)
    window.bulk_action("sync", "pause", "all")

    assert calls[0][:3] == ("sync", "pause", ["sync-1"])
    assert calls[0][3]["operator_consent"] is True
    assert calls[0][3]["expected_preflight_fingerprint"] == (
        app_module.session_preflight_fingerprint([window.snapshot.sync[0]])
    )
    assert calls[-1] == ("refresh", {"force": True})
    assert window.pending_action is False


def test_single_mutation_shows_exact_plan_before_execution(window, monkeypatch):
    window.demo = False
    native_row = {
        "identifier": "sync-exact-7",
        "configuration": {"mode": "two-way-safe"},
        "status": 6,
        "files": 17,
    }
    window.snapshot.sync = [native_row]
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append(args[2]) or QMessageBox.StandardButton.No,
    )
    submissions = []
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.run_command("sync", "pause", target="sync-exact-7")

    assert "Pause one synchronization session · R1" in prompts[0]
    assert "Exact session identifier: sync-exact-7" in prompts[0]
    assert "mutagen sync pause sync-exact-7" in prompts[0]
    assert submissions == []
    assert window.pending_action is False


def test_run_command_is_a_noop_in_demo(window, monkeypatch):
    prompts = []
    submissions = []
    window.demo = True
    monkeypatch.setattr(QMessageBox, "question", lambda *args: prompts.append(args))
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.run_command("sync", "pause", target="sync-exact")

    assert prompts == []
    assert submissions == []


def test_run_command_requires_exact_session_in_current_snapshot(window, monkeypatch):
    messages = []
    submissions = []
    window.demo = False
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[1]))
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.run_command("sync", "pause", target="missing-exact-id")

    assert messages == ["Refresh Required"]
    assert submissions == []


def test_run_command_rejects_actions_without_a_risk_policy(window, monkeypatch):
    errors = []
    window.demo = False
    window.snapshot.sync = [{"identifier": "sync-known"}]
    monkeypatch.setattr(window, "report_error", errors.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)

    window.run_command("sync", "unregistered-action", target="sync-known")

    assert errors == ["This session action has no registered risk policy."]


@pytest.mark.parametrize("scenario", ["prepare_error", "preview_cancel", "typed_cancel"])
def test_daemon_stop_requires_successful_preview_and_typed_confirmation(
    window, monkeypatch, scenario
):
    errors = []
    cancellations = []
    submissions = []
    window.demo = False
    plan = SimpleNamespace(
        plan_id="daemon-stop-plan",
        description="Stop the Mutagen daemon",
        risk="R2",
        argv=("daemon", "stop"),
        requires_typed_confirmation=scenario == "typed_cancel",
        typed_confirmation="STOP",
    )

    class FakeClient:
        def __init__(self, _binary, *, action_planner):
            self.action_planner = action_planner

        def prepare_daemon_plan(self, _action):
            if scenario == "prepare_error":
                raise ValueError("daemon plan unavailable")
            return plan

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(window.action_planner, "cancel", cancellations.append)
    monkeypatch.setattr(window, "report_error", errors.append)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: (
            QMessageBox.StandardButton.Yes
            if scenario == "typed_cancel"
            else QMessageBox.StandardButton.No
        ),
    )
    monkeypatch.setattr(app_module.QInputDialog, "getText", lambda *_args: ("STOP", False))
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.run_command("daemon", "stop")

    assert submissions == []
    if scenario == "prepare_error":
        assert errors == ["daemon plan unavailable"]
        assert cancellations == []
    else:
        assert errors == []
        assert cancellations == ["daemon-stop-plan"]


@pytest.mark.parametrize(
    "action,requires_typed_confirmation,typed_confirmation",
    [("start", False, None), ("stop", True, "STOP")],
)
def test_daemon_actions_use_preview_and_required_confirmation(
    window, monkeypatch, action, requires_typed_confirmation, typed_confirmation
):
    calls = []
    previews = []
    window.demo = False
    plan = SimpleNamespace(
        plan_id="daemon-start-plan",
        description=f"{action.title()} the Mutagen daemon",
        risk="R1" if action == "start" else "R2",
        argv=("daemon", action),
        requires_typed_confirmation=requires_typed_confirmation,
        typed_confirmation=typed_confirmation,
    )

    class FakeClient:
        last_created_session = None

        def __init__(self, _binary, *, action_planner):
            pass

        def prepare_daemon_plan(self, action):
            calls.append(("prepare", action))
            return plan

        def consent_action_plan(self, candidate, **kwargs):
            calls.append(("consent", kwargs))
            return candidate

        def execute(self, kind, action, target, options, **kwargs):
            calls.append(("execute", kind, action, target, options, kwargs))
            return "daemon started"

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: previews.append(_args[2]) or QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getText",
        lambda *_args: (
            ("STOP", True)
            if action == "stop"
            else pytest.fail("R1 daemon start must not request typed confirmation")
        ),
    )
    monkeypatch.setattr(window, "refresh", lambda **_kwargs: None)

    def submit(func, on_result, on_error=None, on_done=None):
        on_result(func())
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", submit)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window.run_command("daemon", action)

    assert f"mutagen daemon {action}" in previews[0]
    assert calls[0] == ("prepare", action)
    assert calls[1] == (
        "consent",
        {"consent": True, "typed_confirmation": typed_confirmation},
    )
    assert calls[2][1:3] == ("daemon", action)


@pytest.mark.parametrize("registration_approved", [False, True])
def test_create_obeys_daemon_registration_confirmation(window, monkeypatch, registration_approved):
    calls = []
    prompts = []
    cancellations = []
    answers = iter(
        [
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Yes
            if registration_approved
            else QMessageBox.StandardButton.No,
        ]
    )
    window.demo = False
    create_plan = SimpleNamespace(
        plan_id="sync-create-plan",
        description="Create one sync",
        risk="R1",
        argv=("sync", "create", "/alpha", "/beta"),
        backup_required=False,
        requires_typed_confirmation=False,
        typed_confirmation=None,
    )
    register_plan = SimpleNamespace(
        plan_id="daemon-register-plan",
        description="Register daemon",
        risk="R1",
        argv=("daemon", "register"),
    )

    class FakeClient:
        last_created_session = None

        def __init__(self, _binary, *, action_planner):
            pass

        def prepare_create_plan(self, _kind, _options, *, backup_choice=None):
            return create_plan

        def prepare_daemon_plan(self, action):
            assert action == "register"
            return register_plan

        def consent_action_plan(self, plan, **kwargs):
            calls.append(("consent", plan.plan_id, kwargs))
            return plan

        def execute(self, kind, action, *_args, **_kwargs):
            calls.append(("execute", kind, action))
            return f"{kind} {action} completed"

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: prompts.append(_args[2]) or next(answers),
    )
    monkeypatch.setattr(window.action_planner, "cancel", cancellations.append)

    def submit(func, on_result, _on_error=None, on_done=None):
        result = func()
        on_result(result)
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", submit)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)

    window.run_command("sync", "create", options=["/alpha", "/beta"], register_before=True)

    assert len(prompts) == 2
    assert "Registration affects every unpaused Mutagen session" in prompts[1]
    create_consent = (
        (
            "consent",
            "sync-create-plan",
            {"consent": True, "typed_confirmation": None, "backup_choice": None},
        ),
    )
    if registration_approved:
        assert calls[:1] == list(create_consent)
        assert calls[1] == (
            "consent",
            "daemon-register-plan",
            {"consent": True},
        )
        assert calls[2:] == [
            ("execute", "daemon", "register"),
            ("execute", "sync", "create"),
        ]
        assert cancellations == []
    else:
        assert calls == list(create_consent)
        assert cancellations == ["daemon-register-plan"]


def test_create_session_demo_mode_never_opens_the_wizard(window, monkeypatch):
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(
        app_module, "SessionDialog", lambda *_args, **_kwargs: pytest.fail("demo opened a wizard")
    )

    window.create_session("sync")

    assert messages == ["Actions are disabled in demo mode."]


def test_create_session_missing_cli_routes_to_settings(window, monkeypatch):
    window.demo = False
    window.client.binary = ""
    warnings = []
    pages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    monkeypatch.setattr(window, "set_page", pages.append)

    window.create_session("sync")

    assert warnings == ["First, configure mutagen.exe in Settings."]
    assert pages == [5]


def test_create_session_warns_and_ignores_invalid_saved_profiles(window, monkeypatch):
    window.demo = False
    window.client.binary = "mutagen"
    warnings = []
    captured = []
    monkeypatch.setattr(
        app_module,
        "load_profile_store",
        lambda _path: SimpleNamespace(valid=False, profiles=(), warnings=("invalid JSON",)),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    class Wizard:
        def __init__(self, _kind, _parent, **kwargs):
            captured.append(kwargs["saved_profiles"])

        def exec(self):
            return app_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module, "SessionDialog", Wizard)

    window.create_session("sync")

    assert "Local profiles were left unchanged" in warnings[0]
    assert captured == [()]


@pytest.mark.parametrize("accepted", [False, True])
def test_create_session_runs_only_an_accepted_validated_wizard(window, monkeypatch, accepted):
    window.demo = False
    window.client.binary = "mutagen"
    captured = {}
    calls = []
    monkeypatch.setattr(
        app_module,
        "load_profile_store",
        lambda _path: SimpleNamespace(valid=True, profiles=()),
    )

    class Wizard:
        backup_choice = "verified-backup"

        def __init__(self, kind, _parent, **kwargs):
            captured.update(kind=kind, **kwargs)

        def exec(self):
            return (
                app_module.QDialog.DialogCode.Accepted
                if accepted
                else app_module.QDialog.DialogCode.Rejected
            )

        def arguments(self):
            return ["--name=reviewed"]

    monkeypatch.setattr(app_module, "SessionDialog", Wizard)
    monkeypatch.setattr(window, "run_command", lambda *args, **kwargs: calls.append((args, kwargs)))

    window.create_session("sync")

    assert captured["kind"] == "sync"
    assert captured["saved_profiles"] == ()
    assert len(calls) == int(accepted)
    if accepted:
        assert calls == [
            (
                ("sync", "create"),
                {"options": ["--name=reviewed"], "backup_choice": "verified-backup"},
            )
        ]


def test_single_mutation_passes_confirmed_snapshot_to_planned_client(window, monkeypatch):
    window.demo = False
    native_row = {
        "identifier": "sync-exact-8",
        "configuration": {"mode": "two-way-safe"},
        "status": 6,
        "files": 17,
    }
    window.snapshot.sync = [native_row]
    calls = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)

    class FakeClient:
        def __init__(self, _binary, *, action_planner=None):
            assert action_planner is window.action_planner

        def execute(self, *args, **kwargs):
            calls.append((args, kwargs))
            return "accepted"

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)

    def run_worker(func, on_result, on_error=None, on_done=None):
        on_result(func())
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", run_worker)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)

    window.run_command("sync", "pause", target="sync-exact-8")

    assert calls[0][0] == ("sync", "pause", "sync-exact-8", None)
    assert calls[0][1]["operator_consent"] is True
    assert calls[0][1]["expected_preflight_fingerprint"] == (
        app_module.session_preflight_fingerprint([native_row])
    )
    assert window.pending_action is False


def test_create_action_uses_action_plan_and_explicit_preview(window, monkeypatch):
    from types import SimpleNamespace

    window.demo = False
    options = ["--name=reviewed", "--mode=two-way-safe", "/alpha", "/beta"]
    plan = SimpleNamespace(
        plan_id="create-plan",
        description="Create one synchronization session",
        risk="R2",
        argv=("sync", "create", *options),
        backup_required=False,
        requires_typed_confirmation=False,
        typed_confirmation=None,
    )
    prompts = []
    calls = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append(args[2]) or QMessageBox.StandardButton.Yes,
    )

    class FakeClient:
        def __init__(self, _binary, *, action_planner=None):
            assert action_planner is window.action_planner

        def prepare_create_plan(self, kind, actual_options, *, backup_choice):
            assert kind == "sync"
            assert actual_options == options
            assert backup_choice is None
            return plan

        def consent_action_plan(self, actual_plan, **kwargs):
            assert actual_plan is plan
            assert kwargs == {
                "consent": True,
                "typed_confirmation": None,
                "backup_choice": None,
            }
            return plan

        def execute(self, *args, **kwargs):
            calls.append((args, kwargs))
            return "created"

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)

    def run_worker(func, on_result, on_error=None, on_done=None):
        on_result(func())
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", run_worker)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)

    window.run_command("sync", "create", options=options)

    assert "Create one synchronization session · R2" in prompts[0]
    assert "mutagen sync create " + " ".join(options) in prompts[0]
    assert calls[0][0] == ("sync", "create", "", options)
    assert calls[0][1]["operator_consent"] is True
    assert calls[0][1]["action_plan"] is plan
    assert window.pending_action is False


def test_replica_create_requires_backup_choice_and_typed_plan_phrase(window, monkeypatch):
    from types import SimpleNamespace

    window.demo = False
    backup_choice = "operator-confirmed-recoverable-beta-backup"
    expected = "APPLY create:exact-hash"
    options = ["--mode=one-way-replica", "/alpha", "/beta"]
    plan = SimpleNamespace(
        plan_id="replica-plan",
        description="Create a potentially destructive replica session",
        risk="R3",
        argv=("sync", "create", *options),
        backup_required=True,
        requires_typed_confirmation=True,
        typed_confirmation=expected,
    )
    prompts = []
    typed_prompts = []
    consents = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: prompts.append(args[2]) or QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getText",
        lambda *args: typed_prompts.append(args[2]) or (expected, True),
    )

    class FakeClient:
        def __init__(self, _binary, *, action_planner=None):
            pass

        def prepare_create_plan(self, _kind, _options, *, backup_choice):
            assert backup_choice == backup_choice_value
            return plan

        def consent_action_plan(self, _plan, **kwargs):
            consents.append(kwargs)
            return plan

        def execute(self, *_args, **_kwargs):
            return "created"

    backup_choice_value = backup_choice
    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(
        window,
        "submit",
        lambda func, on_result, _on_error=None, on_done=None: (
            on_result(func()),
            on_done() if on_done else None,
        ),
    )
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)

    window.run_command("sync", "create", options=options, backup_choice=backup_choice)

    assert "R3" in prompts[0]
    assert expected in typed_prompts[0]
    assert consents == [
        {
            "consent": True,
            "typed_confirmation": expected,
            "backup_choice": backup_choice,
        }
    ]


@pytest.mark.parametrize(
    ("confirmation", "expect_typed_prompt"),
    [
        (QMessageBox.StandardButton.No, False),
        (QMessageBox.StandardButton.Yes, True),
    ],
)
def test_replica_create_cancellation_never_executes(
    window, monkeypatch, confirmation, expect_typed_prompt
):
    from types import SimpleNamespace

    window.demo = False
    options = ["--mode=one-way-replica", "/alpha", "/beta"]
    plan = SimpleNamespace(
        plan_id="replica-cancel-plan",
        description="Create a destructive replica session",
        risk="R3",
        argv=("sync", "create", *options),
        backup_required=True,
        requires_typed_confirmation=True,
        typed_confirmation="APPLY create:exact-hash",
    )
    executions = []
    cancelled_plans = []
    monkeypatch.setattr(window.action_planner, "cancel", cancelled_plans.append)

    class FakeClient:
        def __init__(self, _binary, *, action_planner=None):
            pass

        def prepare_create_plan(self, _kind, _options, *, backup_choice):
            assert backup_choice == "verified-backup"
            return plan

        def consent_action_plan(self, *_args, **_kwargs):
            raise AssertionError("cancelled replica plan must not be consented")

        def execute(self, *_args, **_kwargs):
            executions.append(True)

    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: confirmation)
    typed_prompts = []
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getText",
        lambda *_args: typed_prompts.append(True) or ("", False),
    )
    submissions = []
    monkeypatch.setattr(window, "submit", lambda *args, **kwargs: submissions.append(args))

    window.run_command("sync", "create", options=options, backup_choice="verified-backup")

    assert executions == []
    assert submissions == []
    assert cancelled_plans == [plan.plan_id]
    assert not window.pending_action
    assert typed_prompts == ([True] if expect_typed_prompt else [])


@pytest.mark.parametrize(
    ("paused", "registration", "answer", "expected_call"),
    [
        (False, "unregistered", QMessageBox.StandardButton.Yes, ("daemon", "register", {})),
        (
            False,
            "registered",
            QMessageBox.StandardButton.Yes,
            ("sync", "pause", {"target": "sync-1"}),
        ),
        (
            True,
            "unregistered",
            QMessageBox.StandardButton.Yes,
            ("sync", "resume", {"target": "sync-1", "register_before": True}),
        ),
        (
            True,
            "registered",
            None,
            ("sync", "resume", {"target": "sync-1", "register_before": False}),
        ),
    ],
)
def test_sync_startup_actions_respect_pause_and_registration(
    window, monkeypatch, paused, registration, answer, expected_call
):
    calls = []
    window.demo = False
    window.snapshot.registration = registration
    monkeypatch.setattr(
        window, "selected_session", lambda _kind: {"identifier": "sync-1", "paused": paused}
    )
    monkeypatch.setattr(
        window, "run_command", lambda *args, **kwargs: calls.append((args[0], args[1], kwargs))
    )
    if answer is not None:
        monkeypatch.setattr(QMessageBox, "question", lambda *args: answer)

    window.toggle_sync_startup()

    assert calls == [expected_call]


def test_logs_are_recorded_cleared_and_exported(window, monkeypatch, tmp_path):
    target = tmp_path / "history.txt"
    window.add_log("ERROR transfer failed\r\n")
    assert "ERROR transfer failed" in window.logs[-1]
    assert "\r" not in window.logs[-1]

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), "Text (*.txt)"))
    window.export_logs()
    assert "ERROR transfer failed" in target.read_text(encoding="utf-8")


def test_full_snapshot_export_requires_privacy_confirmation(window, monkeypatch, tmp_path):
    target = tmp_path / "snapshot.json"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args: (str(target), "JSON (*.json)")
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)

    window.export_snapshot()

    assert not target.exists()

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.export_snapshot()
    assert "sync" in target.read_text(encoding="utf-8")

    window.clear_logs()
    assert len(window.logs) == 1
    assert "UI history cleared" in window.logs[0]


@pytest.mark.parametrize(
    ("stage", "expected_error", "expected_version"),
    [
        ("missing_binary", "mutagen.exe is not configured. Open Settings.", ""),
        ("sync_error", "sync unavailable", ""),
        ("forward_error", "Forwarding: forward unavailable", "3.2.1"),
        ("cached_version", "", "cached 3.2.1"),
        ("version_error", "", "cached 3.2.1"),
    ],
)
def test_refresh_builds_snapshot_for_cli_failures_and_version_cache(
    window, monkeypatch, stage, expected_error, expected_version
):
    class FakeClient:
        def __init__(self, binary):
            self.binary = binary

        def list_sessions(self, kind):
            if stage == "sync_error" and kind == "sync":
                raise app_module.MutagenError("sync unavailable")
            if stage == "forward_error" and kind == "forward":
                raise app_module.MutagenError("forward unavailable")
            return [{"identifier": kind}]

        def get_version(self):
            if stage == "version_error":
                raise app_module.MutagenError("version unavailable")
            return "3.2.1\nextra"

    binary = "" if stage == "missing_binary" else "mutagen.exe"
    cache_time = app_module.time.monotonic()
    if stage == "version_error":
        cache_time -= 601
    cached_version = "cached 3.2.1" if stage in {"cached_version", "version_error"} else ""
    cache_binary = binary if cached_version else ""
    window.demo = False
    window.client = SimpleNamespace(binary=binary)
    window._version_cache = (cached_version, cache_time, cache_binary)
    monkeypatch.setattr(app_module, "MutagenClient", FakeClient)
    monkeypatch.setattr(app_module, "read_registration", lambda _binary: ("registered", "status"))
    captured = []

    def run_worker(func, on_result, on_error=None, on_done=None):
        captured.append(func())
        if on_done:
            on_done()

    monkeypatch.setattr(window, "submit", run_worker)
    window.refresh(force=True)

    snapshot = captured[0]
    assert snapshot.error == expected_error
    assert snapshot.version == expected_version
    assert window.pending_poll is False
    if stage == "forward_error":
        assert snapshot.daemon is True
        assert snapshot.sync == [{"identifier": "sync"}]


def test_settings_recovery_warning_does_not_claim_safe_defaults(window, monkeypatch):
    monkeypatch.setattr(app_module, "active_language", lambda: "en")

    recovered = app_module.settings_warning_message(
        ("Settings restored from the last valid settings backup.",)
    )
    invalid = app_module.settings_warning_message(
        ("Settings file is unreadable; safe defaults loaded.",)
    )

    assert recovered == "Settings were restored from the last valid backup. Review Settings."
    assert "Safe defaults are active" in invalid


def test_settings_recovery_warning_is_czech_when_czech_is_active(window, monkeypatch):
    monkeypatch.setattr(app_module, "active_language", lambda: "cs")

    warning = app_module.settings_warning_message(
        ("Settings restored from the last valid settings backup.",)
    )

    assert warning == "Nastavení byla obnovena z poslední platné zálohy. Zkontrolujte Nastavení."


def test_mainwindow_reports_recovered_settings_on_startup(tmp_path, monkeypatch, qapp):
    from settings import DEFAULT_SETTINGS, write_settings

    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    path = tmp_path / "settings.json"
    write_settings(path, {**DEFAULT_SETTINGS, "theme": "dark"})
    path.write_bytes(b"{")
    monkeypatch.setattr(app_module, "settings_path", lambda: path)

    recovered_window = app_module.MainWindow(demo=True)
    try:
        message = recovered_window.statusBar().currentMessage()
        assert "restored from the last valid backup" in message.lower()
        assert "safe defaults are active" not in message.lower()
    finally:
        recovered_window.timer.stop()
        recovered_window.metric_timer.stop()
        recovered_window.tail_timer.stop()
        recovered_window._allow_exit = True
        recovered_window.close()
        recovered_window.history.close()
        app_module.QThreadPool.globalInstance().waitForDone(5000)
        qapp.processEvents()
        recovered_window.deleteLater()
        qapp.processEvents()


def test_slow_refresh_coalesces_periodic_and_forced_requests(window, monkeypatch):
    submissions = []
    applied = []
    window.demo = False
    window.client = SimpleNamespace(binary="mutagen.exe")
    window.pending_action = False
    window.pending_poll = False
    window._refresh_again = False
    window._version_cache = ("3.2.1", app_module.time.monotonic(), "mutagen.exe")
    window.poll_backoff.can_retry = lambda force=False: True
    monkeypatch.setattr(
        window,
        "submit",
        lambda work, on_result, on_error=None, on_done=None: submissions.append(
            (work, on_result, on_error, on_done)
        ),
    )
    monkeypatch.setattr(
        window, "apply_snapshot", lambda snapshot, **_kwargs: applied.append(snapshot)
    )

    window.refresh()
    window.refresh()
    window.refresh(force=True)
    window.refresh(force=True)

    assert len(submissions) == 1
    assert window.pending_poll is True
    assert window._refresh_again is True

    stale_snapshot = object()
    submissions[0][1](stale_snapshot)
    assert applied == []

    submissions[0][3]()

    assert len(submissions) == 2
    assert window.pending_poll is True
    assert window._refresh_again is False

    current_snapshot = object()
    submissions[1][1](current_snapshot)
    assert applied == [current_snapshot]


def test_blocked_cli_refresh_never_overlaps_and_forces_one_retry(window, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls = []
    active_calls = 0
    peak_calls = 0

    class SlowClient:
        def __init__(self, binary):
            self.binary = binary

        def list_sessions(self, kind):
            nonlocal active_calls, peak_calls
            with lock:
                calls.append(kind)
                active_calls += 1
                peak_calls = max(peak_calls, active_calls)
                first_call = len(calls) == 1
            if first_call:
                started.set()
                release.wait(timeout=5)
            with lock:
                active_calls -= 1
            return []

        def get_version(self):
            return "3.2.1"

    window.demo = False
    window.client = SimpleNamespace(binary="mutagen.exe")
    window._version_cache = ("3.2.1", app_module.time.monotonic(), "mutagen.exe")
    window.poll_backoff.can_retry = lambda force=False: True
    monkeypatch.setattr(app_module, "MutagenClient", SlowClient)
    monkeypatch.setattr(app_module, "read_registration", lambda _binary: ("registered", "status"))

    window.refresh()
    assert started.wait(timeout=2)
    window.refresh()
    window.refresh(force=True)
    window.refresh(force=True)

    assert calls == ["sync"]
    assert peak_calls == 1

    release.set()
    deadline = app_module.time.monotonic() + 5
    while window.pending_poll and app_module.time.monotonic() < deadline:
        QApplication.processEvents()
        app_module.time.sleep(0.005)
    QApplication.processEvents()

    assert window.pending_poll is False
    assert calls == ["sync", "forward", "sync", "forward"]
    assert peak_calls == 1


def test_close_event_keeps_window_open_during_command(qapp, monkeypatch):
    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    event = SimpleNamespace(
        ignored=False, accepted=False, ignore=lambda: setattr(event, "ignored", True)
    )
    fake_window = SimpleNamespace(pending_action=True, _allow_exit=True)

    app_module.MainWindow.closeEvent(fake_window, event)

    assert event.ignored
    assert not event.accepted
    assert messages == ["Wait for the current command to finish first."]


def test_close_event_hides_to_tray_when_enabled(qapp, monkeypatch):
    hidden = []
    monkeypatch.setattr(app_module.QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    event = SimpleNamespace(ignored=False, ignore=lambda: setattr(event, "ignored", True))
    fake_window = SimpleNamespace(
        pending_action=False,
        conf={"tray": True},
        _allow_exit=False,
        hide=lambda: hidden.append(True),
    )

    app_module.MainWindow.closeEvent(fake_window, event)

    assert hidden == [True]
    assert event.ignored


def test_close_event_waits_for_workers_then_closes_history(qapp, monkeypatch):
    class Timer:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class Event:
        ignored = False
        accepted = False

        def ignore(self):
            self.ignored = True

        def accept(self):
            self.accepted = True

    tail, metric, timer = Timer(), Timer(), Timer()
    shown = []
    fake_window = SimpleNamespace(
        pending_action=False,
        conf={"tray": False},
        _allow_exit=False,
        tail_timer=tail,
        metric_timer=metric,
        timer=timer,
        workers={object()},
        statusBar=lambda: SimpleNamespace(showMessage=shown.append),
        _shutdown_pending=False,
    )
    waiting = Event()

    app_module.MainWindow.closeEvent(fake_window, waiting)

    assert waiting.ignored
    assert not waiting.accepted
    assert fake_window._shutdown_pending
    assert shown
    assert tail.stopped and metric.stopped and timer.stopped

    fake_window.workers.clear()
    recorder_calls = []
    fake_window.recorder = SimpleNamespace(close=lambda timeout: recorder_calls.append(timeout))
    fake_window.history = SimpleNamespace(
        close=lambda: (_ for _ in ()).throw(app_module.sqlite3.Error("closed"))
    )
    fake_window._shutdown_pending = True
    app_quit = []
    monkeypatch.setattr(
        app_module.QApplication,
        "instance",
        lambda: SimpleNamespace(quit=lambda: app_quit.append(True)),
    )
    done = Event()

    app_module.MainWindow.closeEvent(fake_window, done)

    assert done.accepted
    assert not fake_window._shutdown_pending
    assert recorder_calls == [8]
    assert app_quit == [True]


@pytest.mark.parametrize(("page", "expected_kind"), [(0, None), (1, "sync"), (2, "forward")])
def test_new_current_session_routes_only_sync_and_forward_pages(page, expected_kind):
    created = []
    fake_window = SimpleNamespace(
        pages=SimpleNamespace(currentIndex=lambda: page),
        create_session=created.append,
    )

    app_module.MainWindow.new_current_session(fake_window)

    assert created == ([expected_kind] if expected_kind else [])


@pytest.mark.parametrize("session", [None, {}])
def test_toggle_favorite_ignores_missing_selection_or_identifier(monkeypatch, session):
    writes = []
    monkeypatch.setattr(app_module, "write_settings", lambda conf: writes.append(conf))
    fake_window = SimpleNamespace(selected_session=lambda _kind: session)

    app_module.MainWindow.toggle_favorite(fake_window, "sync")

    assert writes == []


@pytest.mark.parametrize(("already_favorite", "expected_favorite"), [(False, True), (True, False)])
def test_toggle_favorite_adds_or_removes_exact_id_and_refreshes_views(
    monkeypatch, already_favorite, expected_favorite
):
    events = []
    favorites = {"sync": {"sync-1"} if already_favorite else set(), "forward": set()}
    sync_table = object()
    snapshot = SimpleNamespace(sync=("sync-row",), forward=("forward-row",))
    fake_window = SimpleNamespace(
        selected_session=lambda _kind: {"identifier": "sync-1"},
        favorites=favorites,
        conf={},
        _table_signatures={"sync": "old", "dashboard": "old"},
        sync_table=sync_table,
        forward_table=object(),
        snapshot=snapshot,
        fill_table=lambda *args: events.append(("fill", args)),
        filter_table=lambda kind: events.append(("filter", kind)),
        refresh_detail=lambda kind: events.append(("detail", kind)),
    )
    writes = []
    monkeypatch.setattr(app_module, "write_settings", lambda conf: writes.append(conf.copy()))

    app_module.MainWindow.toggle_favorite(fake_window, "sync")

    assert ("sync-1" in favorites["sync"]) is expected_favorite
    assert fake_window.conf["favorites"] == {
        "sync": ["sync-1"] if expected_favorite else [],
        "forward": [],
    }
    assert writes == [fake_window.conf]
    assert "sync" not in fake_window._table_signatures
    assert "dashboard" not in fake_window._table_signatures
    assert [event[0] for event in events] == ["fill", "filter", "detail"]
    assert events[0][1] == (sync_table, snapshot.sync, "sync")


def test_toggle_favorite_preserves_view_on_settings_write_failure(monkeypatch):
    errors = []
    fake_window = SimpleNamespace(
        selected_session=lambda _kind: {"identifier": "sync-1"},
        favorites={"sync": set(), "forward": set()},
        conf={},
        report_error=errors.append,
    )

    def fail_write(_conf):
        raise OSError("disk full")

    monkeypatch.setattr(app_module, "write_settings", fail_write)

    app_module.MainWindow.toggle_favorite(fake_window, "sync")

    assert errors == ["disk full"]
    assert fake_window.favorites["sync"] == {"sync-1"}
    assert fake_window.conf["favorites"]["sync"] == ["sync-1"]


def test_copy_session_id_copies_only_a_selected_session(monkeypatch):
    copied = []
    logs = []
    monkeypatch.setattr(
        app_module.QApplication,
        "clipboard",
        lambda: SimpleNamespace(setText=copied.append),
    )
    fake_window = SimpleNamespace(
        selected_session=lambda _kind: {"identifier": "exact-sync-id"}, add_log=logs.append
    )

    app_module.MainWindow.copy_session_id(fake_window, "sync")

    assert copied == ["exact-sync-id"]
    assert logs == ["Session identifier copied to clipboard"]

    copied.clear()
    fake_window.selected_session = lambda _kind: None
    app_module.MainWindow.copy_session_id(fake_window, "sync")
    assert copied == []


def test_export_session_json_handles_cancel_success_and_write_failure(monkeypatch, tmp_path):
    logs = []
    errors = []
    fake_window = SimpleNamespace(
        selected_session=lambda _kind: {"identifier": "sync-1", "secret_endpoint": "example"},
        add_log=logs.append,
        report_error=errors.append,
    )
    monkeypatch.setattr(app_module.QFileDialog, "getSaveFileName", lambda *_args: ("", ""))

    app_module.MainWindow.export_session_json(fake_window, "sync")
    assert logs == []

    destination = tmp_path / "session.json"
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    app_module.MainWindow.export_session_json(fake_window, "sync")
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "identifier": "sync-1",
        "secret_endpoint": "example",
    }
    assert logs == ["Session JSON export complete"]

    monkeypatch.setattr(
        app_module.Path,
        "write_text",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read-only")),
    )
    app_module.MainWindow.export_session_json(fake_window, "sync")
    assert errors == ["read-only"]


@pytest.mark.parametrize(
    ("kind", "demo", "paused", "favorite", "expected_labels"),
    [
        (
            "sync",
            True,
            False,
            True,
            ["★ Remove from Favorites", "Copy ID", "Exportovat JSON…"],
        ),
        (
            "sync",
            False,
            True,
            False,
            [
                "☆ Add to Favorites",
                "Copy ID",
                "Exportovat JSON…",
                "Resume",
                "Sync Now",
                "Enable Start at Sign-In",
            ],
        ),
        (
            "forward",
            False,
            False,
            False,
            ["☆ Add to Favorites", "Copy ID", "Exportovat JSON…", "Pause"],
        ),
    ],
)
def test_session_context_menu_lists_kind_and_state_actions(
    qapp, monkeypatch, kind, demo, paused, favorite, expected_labels
):
    class Action:
        def __init__(self, text, callback):
            self.text = text
            self.callback = callback

    class Menu:
        instance = None

        def __init__(self, _parent):
            self.actions = []
            Menu.instance = self

        def addAction(self, text, callback):
            action = Action(text, callback)
            self.actions.append(action)
            return action

        def addSeparator(self):
            self.actions.append(None)

        def exec(self, position):
            self.position = position

    events = []
    row = SimpleNamespace(row=lambda: 2)
    table = SimpleNamespace(
        itemAt=lambda _point: row,
        selectRow=lambda index: events.append(("select", index)),
        viewport=lambda: SimpleNamespace(mapToGlobal=lambda point: ("global", point)),
    )
    identifier = "session-1"
    session = {"identifier": identifier, "paused": paused}
    fake_window = SimpleNamespace(
        sync_table=table,
        forward_table=table,
        selected_session=lambda _kind: session,
        favorites={kind: {identifier} if favorite else set()},
        demo=demo,
        toggle_favorite=lambda selected_kind: events.append(("favorite", selected_kind)),
        copy_session_id=lambda selected_kind: events.append(("copy", selected_kind)),
        export_session_json=lambda selected_kind: events.append(("export", selected_kind)),
        session_action=lambda selected_kind, action: events.append(
            ("action", selected_kind, action)
        ),
        toggle_sync_startup=lambda: events.append(("startup",)),
    )
    monkeypatch.setattr(app_module, "QMenu", Menu)

    app_module.MainWindow.session_context_menu(fake_window, kind, "point")

    menu = Menu.instance
    assert [action.text for action in menu.actions if action is not None] == expected_labels
    assert menu.position == ("global", "point")
    assert events[0] == ("select", 2)
    for action in menu.actions:
        if action is not None:
            action.callback()
    expected_events = [("favorite", kind), ("copy", kind), ("export", kind)]
    if not demo:
        expected_events.append(("action", kind, "resume" if paused else "pause"))
        if kind == "sync":
            expected_events.extend([("action", kind, "flush"), ("startup",)])
    assert events[1:] == expected_events


def test_open_session_requires_one_exact_latest_snapshot_match(monkeypatch):
    messages = []
    events = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    selected = []

    class Table:
        def model(self):
            return SimpleNamespace(row_for_identifier=lambda _identifier: 2)

        def selectRow(self, row):
            selected.append(row)

    sync_table, forward_table = Table(), Table()
    fake_window = SimpleNamespace(
        showNormal=lambda: None,
        raise_=lambda: None,
        activateWindow=lambda: None,
        demo=False,
        _pending_launch_requests=[],
        pending_poll=False,
        _initial_refresh_pending=False,
        refresh=lambda **kwargs: None,
        _has_authoritative_session_lists=lambda: True,
        snapshot=SimpleNamespace(
            sync=({"identifier": "sync-1"},),
            forward=({"identifier": "forward-1"},),
            daemon=True,
            sessions_stale=False,
            sync_observed_at=datetime.now(app_module.UTC),
            forward_observed_at=datetime.now(app_module.UTC),
        ),
        set_page=lambda page: events.append(("page", page)),
        sync_table=sync_table,
        forward_table=forward_table,
        refresh_detail=lambda kind: events.append(("detail", kind)),
    )

    app_module.MainWindow.handle_launch_request(
        fake_window, {"command": "open_session", "session_id": "missing"}
    )
    assert messages == ["Exact session ID is unavailable or ambiguous in the latest snapshot."]
    assert events == []

    fake_window.snapshot.forward = ({"identifier": "sync-1"},)
    app_module.MainWindow.handle_launch_request(
        fake_window, {"command": "open_session", "session_id": "sync-1"}
    )
    assert messages[-1] == "Exact session ID is unavailable or ambiguous in the latest snapshot."
    assert events == []

    fake_window.snapshot.forward = ({"identifier": "forward-1"},)
    app_module.MainWindow.handle_launch_request(
        fake_window, {"command": "open_session", "session_id": "forward-1"}
    )
    assert fake_window.current_kind == "forward"
    assert fake_window.current_id == "forward-1"
    assert events == [("page", 2), ("detail", "forward")]
    assert selected == [2]


@pytest.mark.parametrize(
    "launch_message",
    [
        {"command": "open_session", "session_id": "exact-startup-id"},
        {"command": "open_folder", "path": "C:/sync"},
    ],
)
def test_session_launch_route_waits_for_first_authoritative_snapshot(monkeypatch, launch_message):
    from mutaui.services import path_lookup

    messages = []
    refreshes = []
    selected = []
    events = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    monkeypatch.setattr(
        path_lookup,
        "find_local_sessions_for_path",
        lambda _sessions, _path: ["exact-startup-id"],
    )
    monkeypatch.setattr(
        app_module,
        "from_legacy_session",
        lambda kind, raw, **_kwargs: (kind, raw["identifier"]),
    )

    class Table:
        def model(self):
            return SimpleNamespace(row_for_identifier=lambda _identifier: 0)

        def selectRow(self, row):
            selected.append(row)

    fake_window = SimpleNamespace(
        showNormal=lambda: None,
        raise_=lambda: None,
        activateWindow=lambda: None,
        demo=False,
        pending_poll=False,
        _initial_refresh_pending=False,
        _pending_launch_requests=[],
        refresh=lambda **kwargs: refreshes.append(kwargs),
        snapshot=SimpleNamespace(
            sync=(),
            forward=(),
            daemon=False,
            sessions_stale=True,
            sync_observed_at=None,
            forward_observed_at=None,
            error="",
        ),
        sync_table=Table(),
        forward_table=Table(),
        set_page=lambda page: events.append(("page", page)),
        refresh_detail=lambda kind: events.append(("detail", kind)),
    )
    request = launch_message
    fake_window._has_authoritative_session_lists = lambda: (
        app_module.MainWindow._has_authoritative_session_lists(fake_window)
    )
    fake_window._complete_pending_launch_requests = lambda: (
        app_module.MainWindow._complete_pending_launch_requests(fake_window)
    )
    fake_window.handle_launch_request = lambda message: app_module.MainWindow.handle_launch_request(
        fake_window, message
    )

    app_module.MainWindow.handle_launch_request(fake_window, request)

    assert messages == []
    assert fake_window._pending_launch_requests == [request]
    assert refreshes == [{"force": True}]

    fake_window.snapshot = SimpleNamespace(
        sync=({"identifier": "exact-startup-id"},),
        forward=(),
        daemon=True,
        sessions_stale=False,
        sync_observed_at=datetime.now(app_module.UTC),
        forward_observed_at=datetime.now(app_module.UTC),
        error="",
    )
    app_module.MainWindow._complete_pending_launch_requests(fake_window)

    assert messages == []
    assert fake_window._pending_launch_requests == []
    assert fake_window.current_kind == "sync"
    assert fake_window.current_id == "exact-startup-id"
    assert events == [("page", 1), ("detail", "sync")]
    assert selected == [0]


def test_pending_session_route_reports_refresh_failure_and_clears(monkeypatch):
    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    request = {"command": "open_session", "session_id": "exact-startup-id"}
    fake_window = SimpleNamespace(
        demo=False,
        _pending_launch_requests=[request],
        snapshot=SimpleNamespace(
            sync=(),
            forward=(),
            daemon=False,
            sessions_stale=True,
            sync_observed_at=None,
            forward_observed_at=None,
            error="Mutagen daemon is offline.",
        ),
    )
    fake_window._has_authoritative_session_lists = lambda: (
        app_module.MainWindow._has_authoritative_session_lists(fake_window)
    )

    app_module.MainWindow._complete_pending_launch_requests(fake_window)

    assert fake_window._pending_launch_requests == []
    assert messages == ["A current session list is unavailable. Refresh status and retry."]


@pytest.mark.parametrize(
    ("matches", "expected_message"),
    [
        ((), "No current local sync root contains this path."),
        (
            ("sync-1", "sync-2"),
            "Path belongs to multiple sync sessions; choose an exact session ID:\nsync-1\nsync-2",
        ),
    ],
)
def test_open_folder_rejects_missing_or_ambiguous_sync_root(monkeypatch, matches, expected_message):
    from mutaui.services import path_lookup

    messages = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    monkeypatch.setattr(
        path_lookup,
        "find_local_sessions_for_path",
        lambda snapshots, path: list(matches),
    )
    monkeypatch.setattr(
        app_module,
        "from_legacy_session",
        lambda kind, raw, **_kwargs: (kind, raw["identifier"]),
    )
    fake_window = SimpleNamespace(
        showNormal=lambda: None,
        raise_=lambda: None,
        activateWindow=lambda: None,
        demo=False,
        pending_poll=False,
        _initial_refresh_pending=False,
        _pending_launch_requests=[],
        refresh=lambda **_kwargs: None,
        snapshot=SimpleNamespace(
            sync=({"identifier": "sync-1"}, None, {"identifier": 5}),
            sync_observed_at=datetime.now(app_module.UTC),
            forward_observed_at=datetime.now(app_module.UTC),
            daemon=True,
            sessions_stale=False,
        ),
    )
    fake_window._has_authoritative_session_lists = lambda: True

    app_module.MainWindow.handle_launch_request(
        fake_window, {"command": "open_folder", "path": "C:/sync/subfolder"}
    )

    assert messages == [expected_message]


def test_update_diagnostics_handles_fresh_partial_and_stale_native_rows(window):
    snapshot = app_module.example_snapshot()
    observed_at = datetime.now().astimezone()
    snapshot.binary = "mutagen"
    snapshot.daemon = True
    snapshot.sync_observed_at = observed_at
    snapshot.forward_observed_at = observed_at
    snapshot.command_durations = {"sync list": 0.25, "forward list": 0.5}
    snapshot.sync.extend([None, {"identifier": 17}, {"name": "missing-id"}])

    window.update_diagnostics(snapshot)

    assert "Mutagen: mutagen" in window.diag_summary.text()
    assert "latest list command=0.25s" in window.diagnostics_view.toPlainText()

    stale = app_module.Snapshot(binary="mutagen", daemon=False, error="daemon offline")
    stale.sync = [{"identifier": "stale-session", "name": "Stale"}]
    window.update_diagnostics(stale)
    assert "CLI error: daemon offline" in window.diag_summary.text()
    assert "Trend: unavailable" in window.diagnostics_view.toPlainText()


def test_update_diagnostics_marks_authoritative_empty_snapshot_as_healthy(window, monkeypatch):
    observed_at = datetime.now().astimezone()
    report = SimpleNamespace(authoritative=True, session_count=0, issue_count=0, issues=())
    monkeypatch.setattr(app_module, "diagnose_sessions", lambda _context: report)
    snapshot = app_module.Snapshot(
        binary="mutagen",
        daemon=True,
        sync_observed_at=observed_at,
        forward_observed_at=observed_at,
    )

    window.update_diagnostics(snapshot)

    assert "Authoritative snapshot: yes" in window.diagnostics_view.toPlainText()
    assert "Trend: baseline" in window.diagnostics_view.toPlainText()
    assert "no findings in recent snapshot" in window.diag_problem_count.text()


def test_update_diagnostics_compares_successive_authoritative_issue_counts(window, monkeypatch):
    issue = SimpleNamespace(
        severity="warning",
        session_identifier="sync-one",
        observed_at=None,
        certainty="possible",
        code="test-warning",
        explanation="A test finding.",
        technical_detail="",
        suggested_actions=(),
        article_url="",
    )
    first = SimpleNamespace(authoritative=True, session_count=1, issue_count=1, issues=(issue,))
    second = SimpleNamespace(
        authoritative=True, session_count=2, issue_count=2, issues=(issue, issue)
    )
    reports = iter((first, second))
    monkeypatch.setattr(app_module, "diagnose_sessions", lambda _context: next(reports))
    window._doctor_observation_key = None
    window._doctor_previous_issue_count = None
    window._doctor_current_issue_count = 0
    observed_at = datetime.now().astimezone()

    window.update_diagnostics(
        app_module.Snapshot(
            binary="mutagen",
            daemon=True,
            sync_observed_at=observed_at,
            forward_observed_at=observed_at,
        )
    )
    next_observed_at = observed_at + timedelta(seconds=1)
    window.update_diagnostics(
        app_module.Snapshot(
            binary="mutagen",
            daemon=True,
            sync_observed_at=next_observed_at,
            forward_observed_at=next_observed_at,
        )
    )

    assert "Trend: increased (1 → 2 findings)" in window.diagnostics_view.toPlainText()
    assert "1 affected session(s)" in window.diag_problem_count.text()


def test_update_diagnostics_keeps_empty_stale_snapshot_unknown(window, monkeypatch):
    report = SimpleNamespace(authoritative=False, session_count=0, issue_count=0, issues=())
    monkeypatch.setattr(app_module, "diagnose_sessions", lambda _context: report)

    window.update_diagnostics(app_module.Snapshot(binary="mutagen", daemon=False))

    assert "Trend: unavailable" in window.diagnostics_view.toPlainText()
    assert "snapshot unknown or stale" in window.diag_problem_count.text()


def test_safe_diagnostics_export_redacts_machine_identifiers(tmp_path, window, monkeypatch):
    destination = tmp_path / "safe-report.json"
    window.snapshot = app_module.Snapshot(
        binary="C:/Users/private/mutagen.exe",
        daemon=True,
        sync=[
            {
                "identifier": "private-session-id",
                "name": "Secret project name",
                "alpha": {"protocol": 0, "path": "C:/Users/private/secret-project"},
                "beta": {"protocol": 1, "host": "alice@secret.example", "path": "/srv/private"},
            }
        ],
    )
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(window.history, "events", lambda **_kwargs: [])
    monkeypatch.setattr(window.history, "statistics", lambda **_kwargs: {})
    logs = []
    monkeypatch.setattr(window, "add_log", logs.append)

    window.export_safe_report()

    exported = destination.read_text(encoding="utf-8")
    assert "private-session-id" not in exported
    assert "Secret project name" not in exported
    assert "C:/Users/private" not in exported
    assert "secret.example" not in exported
    assert logs == ["Safe diagnostics report saved (no paths or addresses)"]


def test_support_bundle_dialog_previews_export_and_defaults_sensitive_logs_off(qapp):
    dialog = app_module.SupportBundleDialog(
        snapshot_preview='{"sync": [{"alpha": {"path": "C:/private"}}]}',
        event_count=4,
        monitored_line_count=2,
    )

    assert dialog.mode.currentData() == "safe"
    assert not dialog.include_event_messages.isChecked()
    assert not dialog.include_monitored_log_lines.isChecked()
    assert not dialog.include_event_messages.isEnabled()
    assert "C:/private" not in dialog.preview.toPlainText()

    dialog.mode.setCurrentIndex(dialog.mode.findData("full"))
    assert "C:/private" in dialog.preview.toPlainText()

    long_preview = app_module.SupportBundleDialog(
        snapshot_preview="x" * 2501,
        event_count=0,
        monitored_line_count=0,
    )
    long_preview.mode.setCurrentIndex(long_preview.mode.findData("full"))
    assert "Preview truncated" in long_preview.preview.toPlainText()

    dialog.mode.setCurrentIndex(dialog.mode.findData("logs"))
    assert dialog.include_event_messages.isEnabled()
    assert dialog.include_monitored_log_lines.isEnabled()
    assert "4" in dialog.preview.toPlainText()
    assert "2" in dialog.preview.toPlainText()
    assert "omits raw text" in dialog.preview.toPlainText()
    dialog.include_event_messages.setChecked(True)
    assert "includes event text" in dialog.preview.toPlainText()
    assert "monitored log lines" not in dialog.preview.toPlainText()
    dialog.include_monitored_log_lines.setChecked(True)
    assert "includes monitored log lines" in dialog.preview.toPlainText()


def test_support_bundle_dialog_localizes_czech_copy(qapp, monkeypatch):
    monkeypatch.setattr(app_module, "active_language", lambda: "cs")
    dialog = app_module.SupportBundleDialog(
        snapshot_preview="{}",
        event_count=0,
        monitored_line_count=0,
    )

    assert "Balíček podpory" in dialog.windowTitle()
    assert "Bezpečný diagnostický report" in dialog.mode.itemText(0)
    dialog.mode.setCurrentIndex(dialog.mode.findData("logs"))
    assert "Místní export" in dialog.preview.toPlainText()


def test_support_bundle_routes_full_snapshot_using_previewed_payload(window, monkeypatch):
    captured = {}

    class AcceptedFullSnapshot:
        mode = SimpleNamespace(currentData=lambda: "full")

        def __init__(self, **kwargs):
            captured["preview"] = kwargs["snapshot_preview"]

        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

    window.snapshot = app_module.Snapshot(binary="C:/private/mutagen.exe", sync=[])
    monkeypatch.setattr(window.history, "events", lambda **_kwargs: [])
    monkeypatch.setattr(app_module, "SupportBundleDialog", AcceptedFullSnapshot)
    monkeypatch.setattr(
        window,
        "export_snapshot",
        lambda **kwargs: captured.update(kwargs),
    )

    window.open_support_bundle()

    assert captured["snapshot_payload"]["binary"] == "C:/private/mutagen.exe"
    assert "C:/private/mutagen.exe" in captured["preview"]


def test_support_bundle_routes_local_self_check(window, monkeypatch):
    calls = []

    class AcceptedSelfCheck:
        mode = SimpleNamespace(currentData=lambda: "self_check")

        def __init__(self, **_kwargs):
            pass

        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

    monkeypatch.setattr(window.history, "events", lambda **_kwargs: [])
    monkeypatch.setattr(app_module, "SupportBundleDialog", AcceptedSelfCheck)
    monkeypatch.setattr(window, "run_local_self_check", lambda: calls.append("run"))

    window.open_support_bundle()

    assert calls == ["run"]


def test_advanced_sync_settings_exposes_optional_performance_assistant(
    window, tmp_path, monkeypatch
):
    session = {
        "identifier": "sync-exact-id",
        "name": "workspace",
        "watch": {"mode": "force-poll", "pollingInterval": 5},
        "alpha": {"protocol": 0, "path": str(tmp_path)},
        "beta": {"protocol": "ssh", "path": "/remote/workspace"},
    }
    captured = {}
    window.demo = False
    window.ui_mode = "advanced"
    window.snapshot.sessions_stale = False
    window.conf = {}
    monkeypatch.setattr(window, "selected_session", lambda _kind: session)
    monkeypatch.setattr(window, "refresh_detail", lambda _kind: None)
    monkeypatch.setattr(window, "add_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "write_settings", lambda _settings: None)
    monkeypatch.setattr(
        app_module.QDialog,
        "exec",
        lambda dialog: (
            captured.setdefault("dialog", dialog) and app_module.QDialog.DialogCode.Accepted
        ),
    )

    def run_assistant(*args, **kwargs):
        captured["assistant_args"] = args
        captured["assistant_kwargs"] = kwargs

    monkeypatch.setattr(app_module, "apply_performance_assistant", run_assistant)

    window.open_session_preferences("sync")
    dialog = captured["dialog"]
    button = dialog.findChild(QPushButton, "performanceTuningAssistant")
    assert button and button.isEnabled()
    button.click()

    assert captured["assistant_args"][0] is session
    assert captured["assistant_kwargs"]["stale"] is False
    assert captured["assistant_kwargs"]["parent"] is dialog
    dialog.close()


def test_full_snapshot_cancel_does_not_write_sensitive_data(tmp_path, window, monkeypatch):
    destination = tmp_path / "full-snapshot.json"
    window.snapshot = app_module.Snapshot(binary="C:/private/mutagen.exe", sync=[])
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    prompts = []

    def decline(*args):
        prompts.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(app_module.QMessageBox, "question", decline)

    window.export_snapshot()

    assert len(prompts) == 1
    assert "Sensitive Snapshot" in str(prompts[0][1])
    assert not destination.exists()


def test_session_log_snapshot_omits_raw_text_by_default(tmp_path, window, monkeypatch):
    destination = tmp_path / "session-logs.json"
    window.history.events = lambda **_kwargs: [(10.5, "warning", "private host /srv/private")]
    window.tail_lines.extend(["ssh private.example: token-secret"])
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    confirmations = []
    monkeypatch.setattr(
        app_module.QMessageBox, "question", lambda *args: confirmations.append(args)
    )

    window.export_session_log_snapshot()

    exported = json.loads(destination.read_text(encoding="utf-8"))
    payload = json.dumps(exported)
    assert exported["event_count"] == 1
    assert exported["monitored_line_count"] == 1
    assert "private host" not in payload
    assert "private.example" not in payload
    assert "token-secret" not in payload
    assert confirmations == []


def test_session_log_snapshot_requires_consent_for_selected_raw_text(tmp_path, window, monkeypatch):
    destination = tmp_path / "session-logs.json"
    window.history.events = lambda **_kwargs: [(10.5, "warning", "private host /srv/private")]
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    prompts = []

    def decline(*args):
        prompts.append(args)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(app_module.QMessageBox, "question", decline)

    window.export_session_log_snapshot(include_event_messages=True)

    assert len(prompts) == 1
    assert "Sensitive Log Details" in str(prompts[0][1])
    assert not destination.exists()


@pytest.mark.parametrize(
    ("notifications", "alerts", "visible", "quiet", "expected"),
    [
        (True, True, True, False, 1),
        (False, True, True, False, 0),
        (True, False, True, False, 0),
        (True, True, False, False, 0),
        (True, True, True, True, 0),
    ],
)
def test_check_alerts_requires_session_and_tray_preferences(
    monkeypatch, notifications, alerts, visible, quiet, expected
):
    import insights

    ticks = iter((100.0, 110.0))
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(app_module, "quiet_hours_active", lambda *_args, **_kwargs: quiet)
    messages = []
    logs = []

    class Tray:
        def isVisible(self):
            return visible

        def showMessage(self, *_args):
            messages.append("alert")

    fake = SimpleNamespace(
        previous_daemon=False,
        previous_states={("sync", "exact-id"): "watching"},
        conf={
            "alerts": alerts,
            "session_prefs": {"exact-id": {"notifications": notifications}},
        },
        tray=Tray(),
        add_log=logs.append,
    )
    snapshot = app_module.Snapshot(
        daemon=True,
        sync=[{"identifier": "exact-id", "name": "Exact session"}],
    )
    monkeypatch.setattr(app_module, "classify", lambda *_args: ("error", "Failed"))
    monkeypatch.setattr(
        insights,
        "state_transitions",
        lambda *_args: [("sync", "exact-id", "watching", "error")],
    )

    app_module.MainWindow.check_alerts(fake, snapshot)
    app_module.MainWindow.check_alerts(fake, snapshot)

    assert len(messages) == expected
    assert "Daemon is responding again" in logs[0]
    assert "needs attention" in logs[1]


@pytest.mark.parametrize(
    ("previous", "state", "expected"),
    [
        ("watching", "paused", "was paused"),
        ("paused", "watching", "resumed"),
        ("error", "watching", "recovered (watching)"),
        ("watching", "active", "watching → active"),
    ],
)
def test_check_alerts_logs_non_error_state_transitions(monkeypatch, previous, state, expected):
    import insights

    messages = []
    monkeypatch.setattr(app_module, "classify", lambda *_args: (state, "state"))
    monkeypatch.setattr(
        insights,
        "state_transitions",
        lambda *_args: [("sync", "state-id", previous, state)],
    )
    fake = SimpleNamespace(
        previous_daemon=True,
        previous_states={("sync", "state-id"): previous},
        conf={"alerts": False},
        tray=SimpleNamespace(isVisible=lambda: False),
        add_log=messages.append,
    )

    app_module.MainWindow.check_alerts(
        fake,
        app_module.Snapshot(daemon=True, sync=[{"identifier": "state-id", "name": "State"}]),
    )

    assert any(expected in message for message in messages)


def test_check_alerts_logs_daemon_outage_without_changing_session_states():
    messages = []
    previous_states = {("sync", "state-id"): "watching"}
    fake = SimpleNamespace(
        previous_daemon=True,
        previous_states=previous_states,
        conf={},
        tray=SimpleNamespace(isVisible=lambda: False),
        add_log=messages.append,
    )

    app_module.MainWindow.check_alerts(fake, app_module.Snapshot(daemon=False))

    assert messages == ["WARNING: Daemon is not responding"]
    assert fake.previous_states is previous_states


def test_clicked_session_notification_opens_its_exact_session():
    requests = []
    fake = SimpleNamespace(
        _last_notification_session_keys=(("sync", "native-exact-id"),),
        handle_launch_request=requests.append,
    )

    app_module.MainWindow.open_notified_issue(fake)

    assert requests == [{"command": "open_session", "session_id": "native-exact-id"}]


def test_clicked_grouped_notification_asks_for_exact_session(monkeypatch):
    requests = []
    fake = SimpleNamespace(
        _last_notification_session_keys=(("sync", "sync-id"), ("forward", "forward-id")),
        handle_launch_request=requests.append,
    )
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getItem",
        lambda *_args, **_kwargs: ("forward: forward-id", True),
    )

    app_module.MainWindow.open_notified_issue(fake)

    assert requests == [{"command": "open_session", "session_id": "forward-id"}]


def test_tray_status_updates_icon_and_localized_tooltip(monkeypatch):
    tooltip = []
    icons = []
    fake = SimpleNamespace(
        tray=SimpleNamespace(setIcon=icons.append),
        _tray_status_icon=lambda status: f"icon:{status}",
    )
    monkeypatch.setattr(
        app_module, "set_localized_tooltip", lambda _tray, text: tooltip.append(text)
    )

    app_module.MainWindow.update_tray_status(
        fake,
        SimpleNamespace(daemon=True, sessions_stale=False),
        {("sync", "healthy-id"): "watching", ("forward", "paused-id"): "paused"},
    )

    assert tooltip == ["Status: session paused"]
    assert icons == ["icon:paused"]


def test_session_preferences_invalid_proposal_is_rejected_then_valid_draft_saves(
    monkeypatch, window
):
    session = {
        "identifier": "prefs-exact-id",
        "name": "Preferences session",
        "alpha": {"protocol": 0, "path": "C:/missing-alpha"},
        "beta": {"protocol": 0, "path": "C:/missing-beta"},
    }
    monkeypatch.setattr(window, "selected_session", lambda _kind: session)
    warnings = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    window.conf["session_prefs"] = {"prefs-exact-id": {"configuration_proposal": "malformed"}}

    def invalid_draft(dialog):
        table = dialog.findChild(QTableWidget)
        row = next(
            i for i in range(table.rowCount()) if table.item(i, 0).text() == "Polling interval"
        )
        table.item(row, 5).setText("not-an-integer")
        dialog.findChild(QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(app_module.QDialog, "exec", invalid_draft)
    window.open_session_preferences("sync")
    assert warnings and "not-an-integer" in warnings[0]
    assert window.conf["session_prefs"]["prefs-exact-id"]["configuration_proposal"] == "malformed"

    def valid_draft(dialog):
        table = dialog.findChild(QTableWidget)
        rows = {table.item(i, 0).text(): i for i in range(table.rowCount())}
        table.item(rows["Polling interval"], 5).setText("10")
        table.item(rows["Ignore paths"], 5).setText('["*.log"]')
        table.item(rows["Ignore VCS metadata"], 5).setText("true")
        dialog.findChild(QDialogButtonBox).accepted.emit()
        return dialog.result()

    monkeypatch.setattr(app_module.QDialog, "exec", valid_draft)
    window.open_session_preferences("sync")

    saved = window.conf["session_prefs"]["prefs-exact-id"]["configuration_proposal"]
    assert saved["watch.pollingInterval"] == 10
    assert saved["ignore.paths"] == ["*.log"]
    assert saved["ignore.vcs"] is True


def test_session_quick_ignore_requires_local_root_and_adds_path_aware_draft(
    monkeypatch, tmp_path, window
):
    root = tmp_path / "sync"
    root.mkdir()
    selected = root / "nested" / "private file.txt"
    selected.parent.mkdir()
    selected.write_text("content", encoding="utf-8")
    session = {
        "identifier": "quick-ignore-id",
        "name": "Quick Ignore",
        "alpha": {"protocol": "local", "path": str(root)},
        "beta": {"protocol": "ssh", "path": "/remote"},
        "ignore": {"paths": ["existing/"]},
    }
    monkeypatch.setattr(window, "selected_session", lambda _kind: session)
    messages = []
    logs = []
    monkeypatch.setattr(window, "add_log", logs.append)
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )

    def click_quick_ignore(dialog):
        button = next(
            item
            for item in dialog.findChildren(QPushButton)
            if item.text() == "Quick Ignore a Local File…"
        )
        button.click()
        return app_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(app_module.QDialog, "exec", click_quick_ignore)
    monkeypatch.setattr(app_module.QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    window.open_session_preferences("sync")
    assert messages == []
    assert logs == []

    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(selected), ""),
    )
    window.open_session_preferences("sync")
    assert logs and "Quick Ignore drafted for ALPHA" in logs[0]

    session["beta"] = {"protocol": 0, "path": str(root)}
    choices = []
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getItem",
        lambda *_args: choices.append(True) or ("", False),
    )
    window.open_session_preferences("sync")
    assert choices == [True]

    session["alpha"] = {"protocol": "ssh", "path": "/remote-a"}
    session["beta"] = {"protocol": "ssh", "path": "/remote-b"}
    window.open_session_preferences("sync")
    assert any("No local sync endpoint" in message for message in messages)

    second_root = tmp_path / "second-sync"
    second_root.mkdir()
    second_file = second_root / "nested" / "other.txt"
    second_file.parent.mkdir()
    second_file.write_text("content", encoding="utf-8")
    session["alpha"] = {"protocol": "local", "path": str(root)}
    session["beta"] = {"protocol": "local", "path": str(second_root)}
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getItem",
        lambda _dialog, _title, _label, choices, *_args: (choices[1], True),
    )
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(second_file), ""),
    )
    window.open_session_preferences("sync")
    assert logs[-1].startswith("Quick Ignore drafted for BETA:")


def test_refresh_detail_renders_sync_transfer_issues_and_forwarding_totals(window, monkeypatch):
    sync = {
        "identifier": "detail-sync-id",
        "name": "Build tree",
        "status": 7,
        "paused": False,
        "alpha": {
            "protocol": 0,
            "path": "C:/alpha",
            "files": 3,
            "totalFileSize": 1024,
            "stagingProgress": {"expectedSize": 100, "receivedSize": 50, "path": "file.bin"},
            "scanProblems": [{"path": "alpha.txt", "error": "read failed"}],
        },
        "beta": {
            "protocol": 1,
            "host": "example",
            "path": "/beta",
            "files": 4,
            "stagingProgress": {"expectedSize": 0, "receivedSize": 0},
            "transitionProblems": [{"path": "beta.txt", "error": "write failed"}],
        },
        "successfulCycles": 2,
        "conflicts": [{"root": "conflict.txt"}],
        "lastError": "native detail",
    }
    forward = {
        "identifier": "detail-forward-id",
        "status": 3,
        "source": {"protocol": 0, "path": "C:/source.sock"},
        "destination": {"protocol": 1, "host": "example", "path": "/dest.sock"},
        "openConnections": 2,
        "totalConnections": 5,
        "totalOutboundData": 2048,
        "totalInboundData": 4096,
    }
    window.conf.setdefault("session_prefs", {})["detail-sync-id"] = {"note": "Reviewed"}
    window.favorites["sync"].add("detail-sync-id")
    monkeypatch.setattr(
        window, "selected_session", lambda kind: sync if kind == "sync" else forward
    )
    window.snapshot.registration = "registered"

    window.refresh_detail("sync")

    sync_document = QTextDocument()
    sync_document.setHtml(window.sync_details.text())
    sync_text = sync_document.toPlainText()
    assert "Transfer to ALPHA" in sync_text
    assert "RECENT CONFLICTS" in sync_text
    assert "RECENT ISSUES" in sync_text
    assert "native detail" in sync_text
    assert "Reviewed" in sync_text
    assert window.sync_progress.value() == 50
    assert window.sync_favorite_button.text().startswith("★")
    assert "Start at sign-in: on" in window.sync_autostart_button.text()

    window.refresh_detail("forward")

    forward_document = QTextDocument()
    forward_document.setHtml(window.forward_details.text())
    forward_text = forward_document.toPlainText()
    assert "CONNECTION OVERVIEW" in forward_text
    assert "Open connections: 2 · Total: 5" in forward_text
    assert "Data out:" in forward_text
    assert "Data in:" in forward_text


def test_main_version_prints_without_initializing_qt(monkeypatch, capsys):
    monkeypatch.setattr(app_module.sys, "argv", ["mutaui", "--version"])
    monkeypatch.setattr(
        app_module,
        "QApplication",
        lambda *_args: pytest.fail("version must exit before Qt initialization"),
    )

    assert app_module.main() == 0
    assert capsys.readouterr().out.strip() == app_module.APP_VERSION


@pytest.mark.parametrize(
    ("window_fails", "expected_code", "expected_log", "with_env"),
    [
        (False, 0, "OK: UI pages and server groups rendered.", False),
        (True, 1, "self-test window failed", False),
        (False, 0, "Settings recovery and file-backed history reopened.", True),
    ],
)
def test_main_self_test_writes_result_and_returns_explicit_status(
    tmp_path, monkeypatch, window_fails, expected_code, expected_log, with_env
):
    class SelfTestExit(Exception):
        def __init__(self, code):
            self.code = code

    class FakeApplication:
        def __init__(self, _args):
            pass

        def setApplicationName(self, _name):
            pass

        def setOrganizationName(self, _name):
            pass

        def setQuitOnLastWindowClosed(self, _value):
            pass

        def processEvents(self):
            pass

    class Rows:
        def rowCount(self):
            return 0

    class Selector:
        def count(self):
            return 1

        def setCurrentIndex(self, _index):
            pass

    class Pages:
        def count(self):
            return 2

    class FakeWindow:
        def __init__(self, *, demo, history_path=None):
            if window_fails:
                raise RuntimeError("self-test window failed")
            assert demo is True
            self.snapshot = object()
            self.pages = Pages()
            self.server_selector = Selector()
            self.server_sync_table = Rows()
            self.server_forward_table = Rows()
            self.cpu_chart = object()
            self.mem_chart = object()
            self.register_message = object()
            self.pending_action = True
            self._allow_exit = False
            self.settings_load = SimpleNamespace(
                warnings=["restored from the last valid settings backup"]
            )
            self.conf = {"theme": "dark"}
            self.history = SimpleNamespace(path=str(Path(history_path)) if history_path else "")

        def show(self):
            pass

        def apply_snapshot(self, _snapshot):
            pass

        def set_page(self, _index):
            pass

        def server_targets(self, _kind, _scope):
            return []

        def close(self):
            pass

    log_path = tmp_path / "self-test.log"
    if with_env:
        hist_path = tmp_path / "history.sqlite3"
        monkeypatch.setenv("MUTAUI_SELF_TEST_EXPECT_RECOVERED_THEME", "dark")
        monkeypatch.setenv("MUTAUI_SELF_TEST_HISTORY_PATH", str(hist_path))
    monkeypatch.setenv("MUTAUI_SELF_TEST_LOG", str(log_path))
    monkeypatch.setattr(app_module.sys, "argv", ["mutaui", "--self-test"])
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "MainWindow", FakeWindow)
    monkeypatch.setitem(
        app_module.sys.modules,
        "shiboken6",
        SimpleNamespace(isValid=lambda _widget: True),
    )
    monkeypatch.setattr(
        app_module.os, "_exit", lambda code: (_ for _ in ()).throw(SelfTestExit(code))
    )

    with pytest.raises(SelfTestExit) as exit_result:
        app_module.main()

    assert exit_result.value.code == expected_code
    assert expected_log in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("primary", [False, True])
def test_main_forwards_launch_request_or_opens_primary_window(monkeypatch, primary):
    events = []

    class FakeApplication:
        def __init__(self, _args):
            events.append("application")

        def setApplicationName(self, _name):
            pass

        def setOrganizationName(self, _name):
            pass

        def setQuitOnLastWindowClosed(self, _value):
            pass

        def exec(self):
            return 7

    class FakeSignal:
        def connect(self, callback):
            self.callback = callback

    class FakeBroker:
        def __init__(self):
            self.request_received = FakeSignal()

        def start_or_forward(self, message):
            events.append(("broker", message))
            return primary

    class FakeWindow:
        def __init__(self, demo):
            self.demo = demo
            events.append(("window", demo))

        def show(self):
            events.append("show")

        def handle_launch_request(self, message):
            events.append(("launch", message))

    monkeypatch.setattr(app_module.sys, "argv", ["mutaui", "--open-session", "exact-id"])
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(instance_lifecycle, "SingleInstanceBroker", FakeBroker)
    monkeypatch.setattr(app_module, "MainWindow", FakeWindow)
    monkeypatch.setattr(app_module.sys, "platform", "linux")

    assert app_module.main() == (7 if primary else 0)
    assert ("broker", {"command": "open_session", "session_id": "exact-id"}) in events
    assert (
        ("window", False) in events
        if primary
        else not any(isinstance(event, tuple) and event[0] == "window" for event in events)
    )
    if primary:
        assert "show" in events
        assert ("launch", {"command": "open_session", "session_id": "exact-id"}) in events


def test_main_focus_command_does_not_forward_launch_request_and_hooks_power_monitor(
    monkeypatch,
):
    events = []

    class FakeSignal:
        def connect(self, callback):
            events.append(("connected", callback))

    class FakeApplication:
        def __init__(self, _args):
            self.aboutToQuit = FakeSignal()

        def setApplicationName(self, _name):
            pass

        def setOrganizationName(self, _name):
            pass

        def setQuitOnLastWindowClosed(self, _value):
            pass

        def exec(self):
            return 0

    class FakeBroker:
        def __init__(self):
            self.request_received = FakeSignal()

        def start_or_forward(self, message):
            return True

    class FakeWindow:
        def __init__(self, demo):
            self.demo = demo
            self.health_tracker = SimpleNamespace(
                note_environment_event=lambda *_args, **_kwargs: None
            )
            self._power_event_monitor = SimpleNamespace(stop=lambda: events.append("stopped"))

        def show(self):
            events.append("show")

        def handle_launch_request(self, message):
            events.append(("launch", message))

    monkeypatch.setattr(app_module.sys, "argv", ["mutaui"])
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(instance_lifecycle, "SingleInstanceBroker", FakeBroker)
    monkeypatch.setattr(app_module, "MainWindow", FakeWindow)
    monkeypatch.setattr(
        "mutaui.services.power_events.install_platform_power_event_monitor",
        lambda app, cb: SimpleNamespace(stop=lambda: events.append("stopped")),
    )

    assert app_module.main() == 0
    assert "show" in events
    assert not any(event[0] == "launch" for event in events if isinstance(event, tuple))


def test_main_reports_single_instance_failure(monkeypatch, capsys):
    class FakeApplication:
        def __init__(self, _args):
            pass

        def setApplicationName(self, _name):
            pass

        def setOrganizationName(self, _name):
            pass

        def setQuitOnLastWindowClosed(self, _value):
            pass

    class FailedBroker:
        def start_or_forward(self, _message):
            raise instance_lifecycle.InstanceLifecycleError("another instance unavailable")

    monkeypatch.setattr(app_module.sys, "argv", ["mutaui"])
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(instance_lifecycle, "SingleInstanceBroker", FailedBroker)

    assert app_module.main() == 2
    assert "another instance unavailable" in capsys.readouterr().err


def test_portable_import_rejects_invalid_bundle_without_writing(tmp_path, window, monkeypatch):
    invalid_bundle = tmp_path / "invalid.json"
    invalid_bundle.write_text("not a bundle", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(invalid_bundle), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    window.import_portable_bundle()

    assert len(warnings) == 1
    assert "Bundle was not changed or imported" in warnings[0]


def test_portable_import_warns_on_oversized_bundle_without_crashing(tmp_path, window, monkeypatch):
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as stream:
        stream.truncate(5 * 1024 * 1024 + 1)
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(oversized), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    window.import_portable_bundle()

    assert len(warnings) == 1
    assert "Portable bundle exceeds the 5 MiB size limit." in warnings[0]


@pytest.mark.parametrize("invalid_file", ["connection-profiles.json", "ignore-presets.json"])
def test_portable_import_stops_when_existing_local_store_is_invalid(
    tmp_path, window, monkeypatch, invalid_file
):
    from portable_bundle import build_bundle

    bundle_path = tmp_path / "valid.json"
    bundle_path.write_text(build_bundle([], {}, app_version="8.2").text, encoding="utf-8")
    store_path = app_module.settings_path().with_name(invalid_file)
    store_path.write_text("{ invalid", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(bundle_path), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append((args[1], args[2])))

    window.import_portable_bundle()

    assert len(warnings) == 1
    assert warnings[0][0] == "Portable Import Unavailable"
    assert "was left unchanged" in warnings[0][1]


def test_portable_import_cancelled_preview_makes_no_changes(tmp_path, window, monkeypatch):
    from portable_bundle import build_bundle

    bundle_path = tmp_path / "valid.json"
    bundle_path.write_text(build_bundle([], {}, app_version="8.2").text, encoding="utf-8")
    messages = []

    class Preview:
        def exec(self):
            return app_module.QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(bundle_path), "JSON (*.json)"),
    )
    monkeypatch.setattr(app_module, "PortableImportPreviewDialog", lambda *_args: Preview())
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args))

    window.import_portable_bundle()

    assert messages == []


def test_portable_import_reports_empty_selection_without_writing(tmp_path, window, monkeypatch):
    from portable_bundle import build_bundle

    bundle_path = tmp_path / "valid.json"
    bundle_path.write_text(build_bundle([], {}, app_version="8.2").text, encoding="utf-8")
    messages = []

    class Preview:
        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

        def selected_preferences(self):
            return set()

        def ignore_choices(self):
            return {}

        def profile_choices(self):
            return {}

    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(bundle_path), "JSON (*.json)"),
    )
    monkeypatch.setattr(app_module, "PortableImportPreviewDialog", lambda *_args: Preview())
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))

    window.import_portable_bundle()

    assert messages == ["Nothing selected; no files changed."]


def test_portable_import_stops_if_profiles_change_after_preview(tmp_path, window, monkeypatch):
    from connection_profiles import ConnectionProfileStore
    from portable_bundle import build_bundle

    bundle_path = tmp_path / "valid.json"
    bundle_path.write_text(
        build_bundle([], {"theme": "dark"}, app_version="8.2").text,
        encoding="utf-8",
    )
    profile_path = app_module.settings_path().with_name("connection-profiles.json")
    warnings = []

    class Preview:
        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

        def selected_preferences(self):
            return {"theme"}

        def ignore_choices(self):
            return {}

        def profile_choices(self):
            return {}

    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (str(bundle_path), "JSON (*.json)"),
    )
    monkeypatch.setattr(app_module, "PortableImportPreviewDialog", lambda *_args: Preview())

    def change_profiles_then_confirm(*_args, **_kwargs):
        ConnectionProfileStore(profile_path).create(
            "Concurrent profile", "./source", "host:/destination", kind="sync"
        )
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", change_profiles_then_confirm)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    window.import_portable_bundle()

    assert len(warnings) == 1
    assert "profiles changed after preview" in warnings[0]


def test_portable_export_does_not_replace_existing_file_without_confirmation(
    tmp_path, window, monkeypatch
):
    destination = tmp_path / "existing.json"
    original = b"keep this bundle unchanged"
    destination.write_bytes(original)
    questions = []
    messages = []
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Cancel])
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: questions.append(True) or next(answers),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args))

    window.export_portable_bundle()

    assert questions == [True, True]
    assert destination.read_bytes() == original
    assert messages == []


def test_portable_import_preview_returns_choices_bound_to_profile_id(tmp_path, window):
    from connection_profiles import ConnectionProfileStore
    from portable_bundle import build_bundle, load_bundle

    profile = ConnectionProfileStore(tmp_path / "profiles.json").create(
        "Incoming profile", "./source", "host:/destination", kind="sync"
    )
    bundle = load_bundle(build_bundle([profile], {"theme": "dark"}, app_version="8.2").text)
    dialog = app_module.PortableImportPreviewDialog(
        window, bundle, existing_profiles=(), existing_ignores=()
    )
    selector = dialog.table.cellWidget(0, 3)
    selector.setCurrentIndex(selector.findData("skip"))

    assert dialog.profile_choices() == {profile.id: "skip"}
    dialog.close()


def test_portable_export_stops_when_save_dialog_is_cancelled(window, monkeypatch):
    questions = []
    monkeypatch.setattr(app_module.QFileDialog, "getSaveFileName", lambda *_args: ("", ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: questions.append(True))

    window.export_portable_bundle()

    assert questions == []


def test_portable_export_rejects_invalid_profile_store_before_file_dialog(window, monkeypatch):
    profile_path = app_module.settings_path().with_name("connection-profiles.json")
    profile_path.write_text("{ invalid", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: pytest.fail("invalid profile store must stop before file selection"),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    window.export_portable_bundle()

    assert len(warnings) == 1
    assert "left unchanged" in warnings[0]


def test_portable_export_privacy_cancel_keeps_destination_absent(tmp_path, window, monkeypatch):
    destination = tmp_path / "export.json"
    answers = iter([QMessageBox.StandardButton.Cancel])
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: next(answers))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)

    window.export_portable_bundle()

    assert not destination.exists()


def test_portable_export_reports_bundle_validation_failure(tmp_path, window, monkeypatch):
    destination = tmp_path / "export.json"
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    monkeypatch.setattr(
        app_module,
        "build_bundle",
        lambda *_args, **_kwargs: SimpleNamespace(valid=False, warnings=("invalid data",)),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    window.export_portable_bundle()

    assert warnings == ["invalid data"]
    assert not destination.exists()


def test_portable_export_reports_invalid_ignore_store_without_writing(
    tmp_path, window, monkeypatch
):
    ignore_path = app_module.settings_path().with_name("ignore-presets.json")
    ignore_path.write_text("{ invalid", encoding="utf-8")
    destination = tmp_path / "export.json"
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append((args[1], args[2])))

    window.export_portable_bundle()

    assert len(warnings) == 1
    assert warnings[0][0] == "Portable Export Unavailable"
    assert "left unchanged" in warnings[0][1]
    assert not destination.exists()


def test_portable_export_cleans_temporary_file_when_atomic_replace_fails(
    tmp_path, window, monkeypatch
):
    destination = tmp_path / "export.json"
    warnings = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    monkeypatch.setattr(
        app_module.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("disk full"))
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))

    window.export_portable_bundle()

    assert warnings == ["Could not save bundle: disk full"]
    assert not destination.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_portable_export_includes_paths_and_replaces_only_after_two_confirmations(
    tmp_path, window, monkeypatch
):
    from connection_profiles import ConnectionProfileStore
    from portable_bundle import load_bundle

    profile_path = app_module.settings_path().with_name("connection-profiles.json")
    ConnectionProfileStore(profile_path).create(
        "Local source", "C:/workspace/source", "host:/destination", kind="sync"
    )
    destination = tmp_path / "existing.json"
    destination.write_text("old bundle", encoding="utf-8")
    answers = iter([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Yes])
    messages = []
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "JSON (*.json)"),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: next(answers))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))

    window.export_portable_bundle()

    bundle = load_bundle(destination.read_bytes())
    assert bundle.valid
    assert bundle.data["items"]["connection_profiles"][0]["endpoint_a"] == "C:/workspace/source"
    assert any("Bundle saved:" in message for message in messages)


def test_diagnostics_escape_untrusted_finding_text_and_render_help_link(window, monkeypatch):
    issue = SimpleNamespace(
        code="unsafe <finding>",
        severity="warning",
        certainty="possible",
        session_identifier="session<1>",
        observed_at=datetime(2026, 11, 13, tzinfo=app_module.UTC),
        explanation="<img src=x onerror=alert(1)>",
        technical_detail="<script>alert(1)</script>",
        suggested_actions=("Review <mode>",),
        article_url="https://docs.example/help?a=1&b=2",
    )
    report = SimpleNamespace(
        authoritative=True,
        session_count=1,
        issue_count=1,
        issues=(issue,),
    )
    snapshot = SimpleNamespace(
        binary="mutagen",
        version="0.18.1",
        daemon=True,
        processes=1,
        cpu=0.0,
        memory=1024,
        sync=[],
        forward=[],
        registration="registered",
        error=None,
        sync_observed_at=None,
        forward_observed_at=None,
        sessions_stale=False,
        command_durations={},
        resource_observed_at=None,
    )
    monkeypatch.setattr(app_module, "diagnose_sessions", lambda _context: report)

    window.update_diagnostics(snapshot)

    rendered = window.diagnostics_view.toHtml()
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert 'href="https://docs.example/help?a=1&amp;b=2"' in rendered
    assert window.diag_problem_count.text().startswith("⚠  1 findings")
    assert window._doctor_current_issue_count == 1


def test_diagnostics_render_fresh_session_health_transitions(window, monkeypatch):
    observed_at = datetime.now().astimezone()
    session = SimpleNamespace(
        identity=SimpleNamespace(kind="sync", identifier="sync-1"),
        stale_reason=None,
        native_config={"status": 7, "paused": True},
        state="Paused",
        measured_at=observed_at,
    )
    transition = SimpleNamespace(
        from_state=None,
        to_state="healthy",
        observed_at=observed_at,
    )
    health = SimpleNamespace(
        session_identifier="sync-1",
        state="healthy",
        error_streak=0,
        reconnect_count=2,
        last_success_at=app_module.time.monotonic() - 60,
        last_command_duration_seconds=1.75,
        incident_id="incident-1",
        transitions=(transition,),
        environment_event="resume grace",
        recommend_manual_action=True,
    )
    report = SimpleNamespace(
        authoritative=True,
        session_count=1,
        issue_count=0,
        issues=(),
    )
    snapshot = SimpleNamespace(
        binary="mutagen",
        version="0.18.1",
        daemon=True,
        processes=1,
        cpu=0.0,
        memory=1024,
        sync=[{"identifier": "sync-1"}],
        forward=[],
        registration="registered",
        error=None,
        sync_observed_at=observed_at,
        forward_observed_at=None,
        sessions_stale=False,
        command_durations={"sync list": 1.75},
        resource_observed_at=observed_at,
    )
    observations = []
    monkeypatch.setattr(app_module, "from_legacy_session", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(app_module, "diagnose_sessions", lambda _context: report)
    monkeypatch.setattr(
        window.health_tracker,
        "observe",
        lambda observation, now: observations.append((observation, now)) or health,
    )

    window.update_diagnostics(snapshot)

    assert len(observations) == 1
    observation = observations[0][0]
    assert observation.confirmed_failure is False
    assert observation.intentional_pause is True
    assert observation.scan_in_progress is True
    rendered = window.diagnostics_view.toPlainText()
    assert "Incident: incident-1" in rendered
    assert "Transition: initial → healthy" in rendered
    assert "Environment grace: resume grace" in rendered
    assert "Assisted recommendation is ready" in rendered
    assert "✓" in window.diag_problem_count.text()


def test_portable_import_cancel_and_preview_rejection_leave_files_untouched(
    tmp_path, window, monkeypatch
):
    source = tmp_path / "bundle.json"
    source.write_text("unchanged", encoding="utf-8")
    warnings = []
    monkeypatch.setattr(app_module.QFileDialog, "getOpenFileName", lambda *_args: ("", "JSON"))
    window.import_portable_bundle()
    assert warnings == []

    monkeypatch.setattr(
        app_module.QFileDialog, "getOpenFileName", lambda *_args: (str(source), "JSON")
    )
    monkeypatch.setattr(
        app_module, "load_bundle", lambda _payload: SimpleNamespace(valid=True, data={"items": {}})
    )
    monkeypatch.setattr(
        app_module, "PortableImportPreviewDialog", lambda *_args: SimpleNamespace(exec=lambda: 0)
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append((args[1], args[2])))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: warnings.append(args[2]))

    window.import_portable_bundle()

    assert warnings == []
    assert source.read_text(encoding="utf-8") == "unchanged"
    assert not app_module.settings_path().with_name("connection-profiles.json").exists()


def test_portable_import_with_no_selections_does_not_write_any_files(tmp_path, window, monkeypatch):
    source = tmp_path / "bundle.json"
    source.write_text("bundle", encoding="utf-8")
    messages = []

    class Preview:
        def __init__(self, *_args):
            pass

        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

        def selected_preferences(self):
            return set()

        def profile_choices(self):
            return {}

        def ignore_choices(self):
            return {}

    monkeypatch.setattr(
        app_module.QFileDialog, "getOpenFileName", lambda *_args: (str(source), "JSON")
    )
    monkeypatch.setattr(
        app_module,
        "load_bundle",
        lambda _payload: SimpleNamespace(
            valid=True,
            data={"items": {"preferences": {}, "connection_profiles": [], "ignore_presets": []}},
        ),
    )
    monkeypatch.setattr(app_module, "PortableImportPreviewDialog", Preview)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(args[2]))

    window.import_portable_bundle()

    assert messages == ["Nothing selected; no files changed."]
    assert source.read_text(encoding="utf-8") == "bundle"
    assert not app_module.settings_path().with_name("connection-profiles.json").exists()
    assert not app_module.settings_path().with_name("ignore-presets.json").exists()


def test_portable_import_confirmation_cancel_keeps_preferences_unchanged(
    tmp_path, window, monkeypatch
):
    source = tmp_path / "bundle.json"
    source.write_text("bundle", encoding="utf-8")
    question_answers = []

    class Preview:
        def __init__(self, *_args):
            pass

        def exec(self):
            return app_module.QDialog.DialogCode.Accepted

        def selected_preferences(self):
            return {"theme"}

        def profile_choices(self):
            return {}

        def ignore_choices(self):
            return {}

    monkeypatch.setattr(
        app_module.QFileDialog, "getOpenFileName", lambda *_args: (str(source), "JSON")
    )
    monkeypatch.setattr(
        app_module,
        "load_bundle",
        lambda _payload: SimpleNamespace(
            valid=True,
            data={
                "items": {
                    "preferences": {"theme": "dark"},
                    "connection_profiles": [],
                    "ignore_presets": [],
                }
            },
        ),
    )
    monkeypatch.setattr(app_module, "PortableImportPreviewDialog", Preview)
    monkeypatch.setattr(app_module, "selected_preferences", lambda *_args: {"theme": "dark"})
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: question_answers.append(True) or QMessageBox.StandardButton.Cancel,
    )

    settings_file = app_module.settings_path()
    before = settings_file.read_bytes() if settings_file.exists() else None
    window.import_portable_bundle()

    after = settings_file.read_bytes() if settings_file.exists() else None
    assert question_answers == [True]
    assert after == before
    assert not app_module.settings_path().with_name("connection-profiles.json").exists()
    assert not app_module.settings_path().with_name("ignore-presets.json").exists()


@pytest.mark.parametrize(
    ("has_provenance", "proposal", "native_configuration"),
    [
        (False, {"watch_mode": "portable"}, {"watch_mode": "portable"}),
        (True, {}, {"watch_mode": "portable"}),
        (True, {"watch_mode": "portable"}, {}),
    ],
)
def test_sync_replacement_blocks_without_verified_change_inputs(
    window, monkeypatch, has_provenance, proposal, native_configuration
):
    session_id = "sync-exact-1"
    window.demo = False
    window.pending_action = False
    window.snapshot = SimpleNamespace(
        sessions_stale=False,
        sync_observed_at=datetime.now(app_module.UTC),
        sync=[{"identifier": session_id, "labels": {}}],
    )
    window.conf = {"session_prefs": {session_id: {"configuration_proposal": proposal}}}
    provenance = (
        SimpleNamespace(create_arguments=("sync", "create", "--watch-mode=portable"))
        if has_provenance
        else None
    )
    monkeypatch.setattr(window.session_provenance, "get", lambda _identifier: provenance)
    monkeypatch.setattr(
        app_module,
        "extract_sync_configuration",
        lambda _session: native_configuration,
    )
    errors = []
    monkeypatch.setattr(window, "report_error", errors.append)

    window.review_sync_replacement(session_id)

    assert len(errors) == 1
    assert window.pending_action is False


@pytest.mark.parametrize(
    ("preview_answer", "typed_confirmation", "accepted"),
    [
        (QMessageBox.StandardButton.No, False, False),
        (QMessageBox.StandardButton.Yes, True, False),
    ],
)
def test_daemon_stop_never_runs_without_both_confirmations(
    window, monkeypatch, preview_answer, typed_confirmation, accepted
):
    window.demo = False
    window.pending_action = False
    cancelled = []
    plan = SimpleNamespace(
        description="Stop the daemon",
        risk="high",
        argv=("daemon", "stop"),
        requires_typed_confirmation=typed_confirmation,
        typed_confirmation="STOP",
        plan_id="stop-plan",
    )
    planner = SimpleNamespace(cancel=cancelled.append)
    window.action_planner = planner

    class Client:
        binary = "mutagen"
        action_planner = planner

        @staticmethod
        def prepare_daemon_plan(_action):
            return plan

        @staticmethod
        def consent_action_plan(*_args, **_kwargs):
            pytest.fail("Rejected confirmation must not consent to the stop plan")

    preview_texts = []
    monkeypatch.setattr(app_module, "MutagenClient", lambda *_args, **_kwargs: Client())
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, text, *_args: preview_texts.append(text) or preview_answer,
    )
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getText",
        lambda *_args: ("STOP", accepted),
    )

    window.run_command("daemon", "stop")

    assert "interrupts all sync and forwarding sessions" in preview_texts[0]
    assert cancelled == ["stop-plan"]
    assert window.pending_action is False


def test_bulk_action_registration_prompt_scopes_impact_and_honors_cancel(window, monkeypatch):
    window.demo = False
    window.pending_action = False
    cancelled = []
    register_plan = SimpleNamespace(
        description="Register daemon",
        risk="high",
        argv=("daemon", "register"),
        plan_id="register-plan",
    )
    planner = SimpleNamespace(cancel=cancelled.append)
    window.action_planner = planner

    class Client:
        binary = "mutagen"
        action_planner = planner

        @staticmethod
        def prepare_daemon_plan(action):
            assert action == "register"
            return register_plan

        @staticmethod
        def consent_action_plan(*_args, **_kwargs):
            pytest.fail("Registration must not be consented after Cancel")

    questions = []
    monkeypatch.setattr(app_module, "MutagenClient", lambda *_args, **_kwargs: Client())
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, text, *_args: (
            questions.append(text) or QMessageBox.StandardButton.No
        ),
    )

    window.run_command("sync", "flush", register_before=True)

    assert "Registration affects every unpaused Mutagen session" in questions[0]
    assert cancelled == ["register-plan"]
    assert window.pending_action is False


@pytest.mark.parametrize(
    ("daemon_running", "expected_status"),
    [
        (False, "local Mutagen daemon is unavailable"),
        (True, "Mutagen daemon returned no sessions"),
    ],
)
def test_endpoint_details_explain_empty_snapshot(window, daemon_running, expected_status):
    window.endpoint_combo.setCurrentIndex(-1)
    window.snapshot = SimpleNamespace(daemon=daemon_running, sync=[], forward=[])

    window.update_endpoint_details()

    assert expected_status in window.endpoint_status.text()
    assert window.endpoint_session_info.text() == "—"


def test_endpoint_details_ignore_calls_before_endpoint_page_exists(window, monkeypatch):
    monkeypatch.delattr(window, "endpoint_combo")

    window.update_endpoint_details()


def test_endpoint_details_render_forwarding_capability_and_last_error(window, monkeypatch):
    session = {"identifier": "forward-exact-1"}
    left = SimpleNamespace(side="Source", address="127.0.0.1:5100", connected=True)
    right = SimpleNamespace(side="Destination", address="host.example:6100", connected=False)
    data = {
        "name": "Forward test",
        "state_text": "Forwarding",
        "left": left,
        "right": right,
        "open_connections": 2,
        "total_connections": 4,
        "total_outbound_data": 4096,
        "total_inbound_data": 2048,
        "last_error": "remote listener closed",
    }
    window.snapshot = SimpleNamespace(daemon=True, sync=[], forward=[session])
    window.endpoint_combo.addItem("Forward test", ("forward", "forward-exact-1"))
    window.endpoint_combo.setCurrentIndex(window.endpoint_combo.count() - 1)
    monkeypatch.setattr(app_module, "inspect_session", lambda *_args: data)

    window.update_endpoint_details()

    assert "Forward test · Forwarding" in window.endpoint_status.text()
    assert "Port forwarding" in window.endpoint_cards["left"]["stats"].text()
    assert window.endpoint_cards["left"]["conn"].text() == "● Connected"
    assert window.endpoint_cards["right"]["conn"].text() == "● Disconnected"
    assert "Open connections: 2" in window.endpoint_session_info.text()
    assert "Last error: remote listener closed" in window.endpoint_session_info.text()


def test_bulk_flush_preview_uses_exact_unpaused_ids_and_skip_wait(window, monkeypatch):
    window.demo = False
    window.pending_action = False
    candidates = [
        {"identifier": "sync-exact-1", "paused": False},
        {"identifier": "sync-exact-1", "paused": False},
        {"identifier": "sync-paused", "paused": True},
    ]
    monkeypatch.setattr(window, "server_targets", lambda kind, scope: candidates)
    prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, text, *_args: prompts.append(text) or QMessageBox.StandardButton.No,
    )

    window.bulk_action("sync", "flush")

    assert len(prompts) == 1
    assert "mutagen sync flush --skip-wait sync-exact-1" in prompts[0]
    assert "sync-paused" not in prompts[0]
    assert window.pending_action is False


@pytest.mark.parametrize("action", ["reset", "terminate"])
@pytest.mark.parametrize(
    ("typed_value", "accepted"),
    [("", False), ("wrong", True)],
)
def test_bulk_destructive_action_requires_exact_second_confirmation(
    window, monkeypatch, action, typed_value, accepted
):
    window.demo = False
    window.pending_action = False
    monkeypatch.setattr(
        window,
        "server_targets",
        lambda _kind, _scope: [{"identifier": "session-exact-1", "paused": False}],
    )
    prompts = []
    second_prompts = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda _parent, _title, text, *_args: (
            prompts.append(text) or QMessageBox.StandardButton.Yes
        ),
    )
    monkeypatch.setattr(
        app_module.QInputDialog,
        "getText",
        lambda _parent, _title, text: second_prompts.append(text) or (typed_value, accepted),
    )

    window.bulk_action("sync", action)

    expected = "RESET" if action == "reset" else "TERMINATE"
    assert len(prompts) == 1
    assert f"mutagen sync {action} session-exact-1" in prompts[0]
    assert len(second_prompts) == 1
    assert expected in second_prompts[0]
    assert window.pending_action is False


def test_graph_hover_handles_empty_outside_duplicate_and_both_series_modes(qapp, monkeypatch):
    tooltips = []
    monkeypatch.setattr(app_module.QToolTip, "hideText", lambda: None)
    monkeypatch.setattr(
        app_module.QToolTip,
        "showText",
        lambda _position, text, *_args: tooltips.append(text),
    )

    class MousePosition:
        def __init__(self, x, y):
            self._x = x
            self._y = y

        def x(self):
            return self._x

        def toPoint(self):
            return QPoint(round(self._x), round(self._y))

    def event_at(x, y):
        position = MousePosition(x, y)
        return SimpleNamespace(position=lambda: position, globalPosition=lambda: position)

    graph = app_module.Graph("#ffffff", unit="number", secondary="#00ff00")
    graph.resize(400, 200)
    updates = []
    monkeypatch.setattr(graph, "update", lambda: updates.append(True))
    graph.mouseMoveEvent(event_at(0, 0))
    assert graph.hover_index == -1
    assert updates == [True]

    graph.set_data([(1000, 1, 2), (1010, 3, 4)])
    area = graph._plot_rect()
    graph.mouseMoveEvent(event_at(0, 0))
    assert graph.hover_index == -1
    assert tooltips == []

    inside = event_at(area.center().x(), area.center().y())
    graph.mouseMoveEvent(inside)
    assert graph.hover_index >= 0
    assert " / " in tooltips[-1]
    tooltip_count = len(tooltips)
    update_count = len(updates)
    graph.mouseMoveEvent(inside)
    assert len(tooltips) == tooltip_count
    assert len(updates) == update_count

    single = app_module.Graph("#ffffff", unit="number")
    single.resize(400, 200)
    single.set_data([(2000, 7, None)])
    single_area = single._plot_rect()
    monkeypatch.setattr(single, "update", lambda: None)
    single.mouseMoveEvent(event_at(single_area.center().x(), single_area.center().y()))
    assert " / " not in tooltips[-1]


def test_apply_ui_language_updates_dynamic_widget_text_and_accessibility(window, monkeypatch):
    group = QGroupBox("Source group", window)
    group.setProperty("mutauiSourceTitle", "Source group")
    group.setProperty("mutauiCzechTitle", "Skupina")
    group.setProperty("mutauiTitleKind", "page")
    dialog = app_module.QWidget(window)
    dialog.setProperty("mutauiSourceTitle", "Source dialog")
    dialog.setProperty("mutauiCzechTitle", "Dialog")
    button = QPushButton("Source button", window)
    button.setProperty("mutauiSourceText", "Source button")
    button.setProperty("mutauiCzechText", "Tlačítko")
    button.setProperty("mutauiSourceAccessibleName", "Source action")
    button.setProperty("mutauiCzechAccessibleName", "Akce")
    field = QLineEdit(window)
    field.setProperty("mutauiSourcePlaceholder", "Source placeholder")
    field.setProperty("mutauiCzechPlaceholder", "Zástupný text")
    combo = app_module.QComboBox(window)
    combo.addItem("Original item")
    combo.setItemData(0, "Endpoints", app_module._LOCALIZED_ITEM_ROLE)
    table = QTableWidget(0, 1, window)
    header = QTableWidgetItem("Original header")
    header.setData(app_module._LOCALIZED_ITEM_ROLE, "Status")
    table.setHorizontalHeaderItem(0, header)
    missing_header = QTableWidget(0, 1, window)
    window.theme_input = app_module.QComboBox(window)
    window.theme_input.addItems(["System", "Light", "Dark"])
    window.language_input = app_module.QComboBox(window)
    window.language_input.addItems(["English", "Czech"])
    window.last_metrics = {"gui_cpu": 12.5, "gui_memory": 1024}
    if hasattr(window, "_last_monitor_stats"):
        del window._last_monitor_stats
    endpoint_updates = []
    monkeypatch.setattr(window, "update_endpoint_sessions", endpoint_updates.append)

    window.apply_ui_language("cs")

    assert group.title() == "Skupina"
    assert dialog.windowTitle() == "Dialog"
    assert button.text() == "Tlačítko"
    assert button.accessibleName() == "Akce"
    assert field.placeholderText() == "Zástupný text"
    assert combo.itemText(0) == app_module.translate_text("Endpoints", "cs")
    assert header.text() == app_module.translate_text("Status", "cs")
    assert missing_header.columnCount() == 1
    assert window.mode_selector.itemText(0) == app_module.translate("mode.basic", "cs")
    assert window.theme_input.itemText(2) == app_module.translate("appearance.dark", "cs")
    assert window.language_input.itemText(0) == app_module.translate("appearance.english", "cs")
    assert endpoint_updates == [window.snapshot]

    window.apply_ui_language("en")

    assert group.title() == "Source group"
    assert dialog.windowTitle() == "Source dialog"
    assert button.text() == "Source button"
    assert button.accessibleName() == "Source action"
    assert field.placeholderText() == "Source placeholder"
    assert endpoint_updates == [window.snapshot, window.snapshot]


def test_render_tail_rebuilds_filtered_lines_then_appends_without_losing_scroll(window):
    window.tail_lines.extend(["info ready", "error first"])
    window.tail_filter.setText("error")
    window.follow_tail.setChecked(False)
    scrollbar = window.tail_view.verticalScrollBar()
    scrollbar.setValue(0)

    window.render_tail()

    assert window.tail_view.toPlainText() == "error first"
    assert scrollbar.value() == 0
    assert window.tail_count_label.text() == "1 line"

    window.tail_lines.extend(["info skipped", "error second"])
    window.render_tail()

    assert window.tail_view.toPlainText().splitlines() == ["error first", "error second"]
    assert scrollbar.value() == 0

    window.follow_tail.setChecked(True)
    window.tail_lines.append("error third")
    window.render_tail()

    assert window.tail_view.toPlainText().splitlines()[-1] == "error third"
    assert scrollbar.value() == scrollbar.maximum()


def test_render_tail_returns_for_uninitialized_window():
    app_module.MainWindow.render_tail(SimpleNamespace())


def test_graph_paint_splits_series_at_missing_values_and_large_time_gaps(qapp):
    graph = app_module.Graph("#ffffff", unit="number", secondary="#00ff00")
    graph.resize(420, 220)
    graph.set_data(
        [
            (1_000, 1, 2),
            (1_010, None, 3),
            (1_020, 4, None),
            (2_000, 5, 6),
        ]
    )

    graph.show()
    qapp.processEvents()

    assert graph._geometry_cache is not None
    assert graph._geometry_cache[1]
    assert graph._geometry_cache[2]
    graph.close()


def test_graph_paint_handles_empty_single_point_hover_and_tiny_plot_area(qapp):
    empty = app_module.Graph("#ffffff", unit="number")
    empty.resize(420, 220)
    empty.show()
    qapp.processEvents()
    assert len(empty.points) == 0
    empty.close()

    single = app_module.Graph("#ffffff", unit="number")
    single.resize(420, 220)
    single.set_data([(1_000, 7, None)])
    single.hover_index = 0
    single.show()
    qapp.processEvents()
    assert single._geometry_cache is not None
    assert len(single._geometry_cache[2]) == 1
    single.close()

    tiny = app_module.Graph("#ffffff", unit="number")
    tiny.setMinimumSize(0, 0)
    tiny.resize(1, 1)
    tiny.show()
    qapp.processEvents()
    assert tiny.width() <= 1
    tiny.close()


def test_graph_paint_handles_secondary_series_without_primary_points(qapp):
    graph = app_module.Graph("#ffffff", unit="number", secondary="#00ff00")
    graph.resize(420, 220)
    graph.set_data([(1_000, None, 2), (1_010, None, 3)])
    graph.show()
    qapp.processEvents()

    assert graph._geometry_cache is not None
    assert graph._geometry_cache[2] == []
    assert graph._geometry_cache[3]
    graph.close()


def test_graph_add_amounts_and_health_ring_cover_empty_and_scaled_states(qapp):
    graph = app_module.Graph("#ffffff", unit="bytes_s", secondary="#00ff00")
    graph.add(12_000, ts=100)
    graph.add(0, second=None, ts=101)
    assert len(graph.points) == 2
    assert graph.amount(None) == "—"
    assert graph.amount(1_024) == "1.0 KB/s"
    graph.unit = "percent"
    assert graph.amount(12.5) == "12.5 %"
    graph.unit = "number"
    assert graph.amount(3.5) == "3.5"
    assert graph.amount(12.5) == "12"

    ring = app_module.HealthRing()
    ring.resize(120, 120)
    ring.show()
    qapp.processEvents()
    ring.set_health(10, 0)
    qapp.processEvents()
    ring.set_health(10, 3)
    qapp.processEvents()
    ring.close()


def test_worker_emits_result_error_and_finished(qapp):
    success = app_module.Worker(lambda: "ready")
    success_events = []
    success.signals.result.connect(lambda value: success_events.append(("result", value)))
    success.signals.finished.connect(lambda: success_events.append(("finished", None)))
    success.run()

    failure = app_module.Worker(lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    failure_events = []
    failure.signals.error.connect(lambda value: failure_events.append(("error", value)))
    failure.signals.finished.connect(lambda: failure_events.append(("finished", None)))
    failure.run()

    assert success_events == [("result", "ready"), ("finished", None)]
    assert failure_events == [("error", "offline"), ("finished", None)]


@pytest.mark.parametrize(
    ("valid", "identifier", "match", "expected_page", "expected_selection"),
    [
        (False, "", -1, [], []),
        (True, "sync-exact", 2, [1], [2]),
        (True, "sync-missing", -1, [1], []),
    ],
)
def test_dashboard_select_routes_only_valid_exact_session_rows(
    valid, identifier, match, expected_page, expected_selection
):
    selected = []
    pages = []
    dashboard_model = SimpleNamespace(
        index=lambda _row, _column: SimpleNamespace(
            isValid=lambda: valid,
            data=lambda _role: identifier,
        )
    )
    sync_model = SimpleNamespace(row_for_identifier=lambda exact_id: match)
    fake_window = SimpleNamespace(
        dashboard_table=SimpleNamespace(model=lambda: dashboard_model),
        sync_table=SimpleNamespace(
            model=lambda: sync_model,
            selectRow=selected.append,
        ),
        set_page=pages.append,
    )

    app_module.MainWindow.dashboard_select(fake_window, 0, 0)

    assert pages == expected_page
    assert selected == expected_selection
    assert getattr(fake_window, "current_id", "") == (identifier if valid else "")


@pytest.mark.parametrize(
    ("valid", "current_kind", "kind", "expected_id", "expected_kind"),
    [
        (False, "sync", "sync", "", "sync"),
        (False, "forward", "sync", "existing", "forward"),
        (True, "forward", "sync", "selected-exact", "sync"),
    ],
)
def test_on_select_preserves_or_updates_exact_selection_state(
    valid, current_kind, kind, expected_id, expected_kind
):
    index = SimpleNamespace(
        isValid=lambda: valid,
        siblingAtColumn=lambda _column: SimpleNamespace(data=lambda _role: "selected-exact"),
    )
    fake_window = SimpleNamespace(
        sync_table=SimpleNamespace(currentIndex=lambda: index),
        forward_table=SimpleNamespace(currentIndex=lambda: index),
        current_kind=current_kind,
        current_id="existing",
        refresh_detail=lambda _kind: None,
    )

    app_module.MainWindow.on_select(fake_window, kind)

    assert fake_window.current_id == expected_id
    assert fake_window.current_kind == expected_kind


def test_export_monitor_png_handles_cancel_failure_and_success(window, monkeypatch):
    events = []
    destinations = iter([("", ""), ("failed.png", ""), ("saved.png", "")])
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: next(destinations),
    )

    class Body:
        def size(self):
            return (640, 480)

        def render(self, _image):
            events.append("render")

    class Scroll:
        def widget(self):
            return Body()

    monkeypatch.setattr(window.pages, "widget", lambda _index: Scroll())
    save_results = iter([False, True])

    class Image:
        def __init__(self, _size):
            pass

        def fill(self, _color):
            events.append("fill")

        def save(self, _path, _format):
            return next(save_results)

    monkeypatch.setattr(app_module, "QPixmap", Image)
    errors = []
    logs = []
    monkeypatch.setattr(window, "report_error", errors.append)
    monkeypatch.setattr(window, "add_log", logs.append)

    window.export_monitor_png()
    assert events == []
    assert errors == [] and logs == []

    window.export_monitor_png()
    assert errors == ["Could not save PNG image."]
    assert events == ["fill", "render"]

    window.export_monitor_png()
    assert logs == ["Monitoring saved as PNG"]
    assert events == ["fill", "render", "fill", "render"]


def test_poll_tail_handles_missing_empty_new_data_and_read_error():
    events = []
    fake_window = SimpleNamespace(
        tail_file=None,
        stop_tail_file=lambda: events.append("stopped"),
        tail_info=SimpleNamespace(setText=lambda text: events.append(text)),
        tail_lines=SimpleNamespace(extend=lambda lines: events.append(tuple(lines))),
        schedule_tail_render=lambda: events.append("scheduled"),
    )

    app_module.MainWindow.poll_tail(fake_window)
    assert events == []

    fake_window.tail_file = SimpleNamespace(poll=lambda: [])
    app_module.MainWindow.poll_tail(fake_window)
    assert events == []

    fake_window.tail_file = SimpleNamespace(poll=lambda: ["line one", "line two"])
    app_module.MainWindow.poll_tail(fake_window)
    assert events == [("line one", "line two"), "scheduled"]

    def fail_read():
        raise OSError("permission denied" * 40)

    fake_window.tail_file = SimpleNamespace(poll=fail_read)
    app_module.MainWindow.poll_tail(fake_window)
    assert events[-2] == "stopped"
    assert events[-1].startswith("Could not read log: ")
    assert len(events[-1]) == len("Could not read log: ") + 200


@pytest.mark.parametrize(
    ("item", "selector_index", "expected_selection"),
    [
        (None, 1, []),
        (SimpleNamespace(data=lambda _role: "server-exact"), -1, []),
        (SimpleNamespace(data=lambda _role: "server-exact"), 2, [2]),
    ],
)
def test_pick_server_row_selects_only_an_existing_exact_group(
    item, selector_index, expected_selection
):
    selected = []
    fake_window = SimpleNamespace(
        server_overview=SimpleNamespace(item=lambda _row, _column: item),
        server_selector=SimpleNamespace(
            findData=lambda _identifier: selector_index,
            setCurrentIndex=selected.append,
        ),
    )

    app_module.MainWindow.pick_server_row(fake_window, 0, 0)

    assert selected == expected_selection


@pytest.mark.parametrize(
    "scenario",
    [
        "missing_type",
        "missing_backend",
        "backend_disabled",
        "missing_instance",
        "unsupported",
        "connected",
    ],
)
def test_health_network_monitor_handles_optional_backend_states(monkeypatch, scenario):
    import sys
    from types import ModuleType

    module = ModuleType("PySide6.QtNetwork")
    connects = []

    if scenario != "missing_type":

        class Information:
            Feature = SimpleNamespace(Reachability="reachability")

            @staticmethod
            def loadDefaultBackend():
                return scenario != "backend_disabled"

            @staticmethod
            def instance():
                if scenario == "missing_instance":
                    return None
                return Information()

            def supports(self, feature):
                return scenario == "connected" and feature == "reachability"

            def reachability(self):
                return "online"

            reachabilityChanged = SimpleNamespace(connect=connects.append)

        if scenario != "missing_backend":
            module.QNetworkInformation = Information
    monkeypatch.setitem(sys.modules, "PySide6.QtNetwork", module)
    fake_window = SimpleNamespace()
    fake_window._health_network_changed = lambda *_args: None

    app_module.MainWindow._attach_health_network_monitor(fake_window)

    if scenario == "connected":
        assert fake_window._health_network_information is not None
        assert fake_window._health_network_reachability == "online"
        assert connects == [fake_window._health_network_changed]
    else:
        assert not hasattr(fake_window, "_health_network_information")


@pytest.mark.parametrize("verified", [True, False])
def test_sync_replacement_migrates_verified_provenance_preferences_and_favorite(
    window, monkeypatch, verified
):
    identifier = "sync-exact-1"
    window.demo = False
    window.pending_action = False
    window.snapshot = SimpleNamespace(
        sessions_stale=False,
        sync_observed_at=datetime.now(app_module.UTC),
        sync=[{"identifier": identifier, "labels": {}}],
    )
    window.conf = {
        "session_prefs": {
            identifier: {"configuration_proposal": {"mode": "one-way-safe"}, "note": "retain"}
        }
    }
    window.favorites = {"sync": {identifier}, "forward": set()}
    provenance = []
    monkeypatch.setattr(
        window.session_provenance,
        "get",
        lambda _identifier: SimpleNamespace(
            create_arguments=("sync", "create", "--mode=two-way-safe", "source", "target")
        ),
    )
    monkeypatch.setattr(
        window.session_provenance, "record", lambda new_id, args: provenance.append((new_id, args))
    )
    monkeypatch.setattr(window.client, "command", lambda *_args, **_kwargs: "--mode string")
    finishes = []
    plan = SimpleNamespace(plan_id="plan-replace", target_ids=(identifier,))
    monkeypatch.setattr(window.client.action_planner, "prepare", lambda _request: plan)
    monkeypatch.setattr(window.client, "consent_action_plan", lambda _plan, *, consent: _plan)
    monkeypatch.setattr(
        window.client.action_planner,
        "finish",
        lambda *args, **kwargs: finishes.append((args, kwargs)),
    )
    monkeypatch.setattr(
        app_module,
        "extract_sync_configuration",
        lambda _session: {"mode": "two-way-safe"},
    )
    new_arguments = ("sync", "create", "--mode=one-way-safe", "source", "target")
    monkeypatch.setattr(
        app_module, "render_sync_replacement_arguments", lambda *_args: new_arguments
    )
    monkeypatch.setattr(app_module, "from_legacy_session", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        app_module,
        "validate_native_command_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(snapshot_inputs_complete=True),
    )
    monkeypatch.setattr(
        app_module,
        "build_reconfiguration_preview",
        lambda *_args, **_kwargs: SimpleNamespace(
            source_sha256="source-hash",
            changes=(
                SimpleNamespace(path="mode", current="two-way-safe", proposed="one-way-safe"),
            ),
        ),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda *_args: app_module.QMessageBox.StandardButton.Yes,
    )
    receipt = SimpleNamespace(
        verified=verified,
        new_session_identifier="sync-new" if verified else None,
        restored_session_identifier="sync-restored",
        recovery_uncertain=not verified,
    )
    monkeypatch.setattr(
        app_module,
        "replace_non_project_mutagen_session",
        lambda *_args, **_kwargs: receipt,
    )
    logs = []
    monkeypatch.setattr(window, "add_log", logs.append)
    monkeypatch.setattr(window, "report_error", lambda message: pytest.fail(message))
    errors = []
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *_args: errors.append(_args[-1]))
    refreshes = []
    monkeypatch.setattr(window, "refresh", lambda **kwargs: refreshes.append(kwargs))
    monkeypatch.setattr(
        window,
        "submit",
        lambda work, on_result, _on_error, on_done: (on_result(work()), on_done()),
    )

    window.review_sync_replacement(identifier)

    if verified:
        assert provenance == [("sync-new", new_arguments)]
        assert window.conf["session_prefs"] == {"sync-new": {"note": "retain"}}
        assert window.favorites["sync"] == {"sync-new"}
        assert finishes[0][1]["verified_target_ids"] == (identifier,)
        assert any("Replaced exact session" in message for message in logs)
    else:
        assert provenance == []
        assert window.conf["session_prefs"][identifier]["configuration_proposal"]
        assert window.favorites["sync"] == {identifier}
        assert finishes[0][1]["verified_target_ids"] == ()
        assert any("Restore session: sync-restored" in message for message in logs)
    assert refreshes == [{"force": True}]
    assert errors == []
    assert window.pending_action is False
