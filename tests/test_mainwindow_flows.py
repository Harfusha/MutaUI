"""Offline tests for GUI interactions and asynchronous refresh decisions."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

import app as app_module


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path, monkeypatch, qapp):
    monkeypatch.setattr(app_module, "settings_path", lambda: tmp_path / "settings.json")
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


def test_session_dialog_validation_blocks_missing_and_risky_inputs(window, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[1]) or QMessageBox.StandardButton.No,
    )
    dialog = app_module.SessionDialog("sync", window)
    dialog.validate()
    assert warnings == ["Missing Information"]
    assert dialog.result() == 0

    dialog.a.setText("C:/source")
    dialog.b.setText("user@host:/target")
    dialog.mode.setCurrentText("one-way-replica")
    dialog.validate()
    assert warnings[-1] == "Risky Mode"
    assert dialog.result() == 0

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: QMessageBox.StandardButton.Yes,
    )
    dialog.validate()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()


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


def test_settings_save_persists_and_refreshes(window, monkeypatch):
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
    warnings = []
    writes = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[1]))
    monkeypatch.setattr(app_module, "write_settings", lambda value: writes.append(value))
    window.binary_edit.setText("missing-mutagen.exe")

    window.save_settings()

    assert warnings == ["Invalid File"]
    assert writes == []


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
        def __init__(self, _binary):
            pass

        def execute_many(self, kind, action, ids):
            calls.append((kind, action, ids))
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

    assert calls[0] == ("sync", "pause", ["sync-1"])
    assert calls[-1] == ("refresh", {"force": True})
    assert window.pending_action is False


@pytest.mark.parametrize(
    ("paused", "registration", "answer", "expected_call"),
    [
        (False, "unregistered", QMessageBox.StandardButton.Yes, ("daemon", "register", {})),
        (False, "registered", QMessageBox.StandardButton.Yes, ("sync", "pause", {"target": "sync-1"})),
        (True, "unregistered", QMessageBox.StandardButton.Yes,
         ("sync", "resume", {"target": "sync-1", "register_before": True})),
        (True, "registered", None,
         ("sync", "resume", {"target": "sync-1", "register_before": False})),
    ],
)
def test_sync_startup_actions_respect_pause_and_registration(
    window, monkeypatch, paused, registration, answer, expected_call
):
    calls = []
    window.demo = False
    window.snapshot.registration = registration
    monkeypatch.setattr(window, "selected_session", lambda _kind: {"identifier": "sync-1", "paused": paused})
    monkeypatch.setattr(window, "run_command", lambda *args, **kwargs: calls.append((args[0], args[1], kwargs)))
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
