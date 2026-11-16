"""Isolated GUI controller branch regressions without native Mutagen side effects.

Exercise skipped/cancelled/invalid states using method unbinding rather than
launching real dialogs, touching the user's default daemon or opening SSH.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import app as app_module


class TextRecorder:
    def __init__(self) -> None:
        self.value = ""
        self.calls: list[str] = []

    def setText(self, text: str) -> None:
        self.value = text
        self.calls.append(text)

    def showMessage(self, text: str, *_args: object) -> None:
        self.setText(text)

    def clear(self) -> None:
        self.calls.clear()


def test_onboarding_cli_picker_cancel_invalid_and_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    selected = [""]
    status = TextRecorder()
    dialog = SimpleNamespace(onboarding_cli_status=status, _onboarding_pending_client=None)
    monkeypatch.setattr(
        app_module.QFileDialog,
        "getOpenFileName",
        lambda *_args: (selected[0], ""),
    )
    monkeypatch.setattr(
        app_module,
        "MutagenClient",
        lambda path: SimpleNamespace(binary="" if path == "invalid" else path),
    )
    monkeypatch.setattr(app_module, "set_localized_text", lambda target, text: target.setText(text))

    app_module.MainWindow.choose_onboarding_cli(dialog)
    assert dialog._onboarding_pending_client is None

    selected[0] = "invalid"
    app_module.MainWindow.choose_onboarding_cli(dialog)
    assert "not an available Mutagen" in status.value
    assert dialog._onboarding_pending_client is None

    selected[0] = "verified-mutagen"
    app_module.MainWindow.choose_onboarding_cli(dialog)
    assert dialog._onboarding_pending_client.binary == "verified-mutagen"
    assert "Selected CLI:" in status.value


def test_onboarding_cli_and_local_smoke_refuse_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = TextRecorder()
    test_status = TextRecorder()
    queued: list[object] = []
    dialog = SimpleNamespace(
        _onboarding_pending_client=None,
        client=SimpleNamespace(binary=""),
        onboarding_cli_status=status,
        onboarding_test_status=test_status,
        submit=lambda func, callback, **kwargs: queued.append((func, callback, kwargs)),
        show_onboarding_cli_result=lambda _result: None,
    )
    monkeypatch.setattr(app_module, "set_localized_text", lambda target, text: target.setText(text))

    app_module.MainWindow.check_onboarding_cli(dialog)
    app_module.MainWindow.run_onboarding_local_test(dialog)
    assert not queued
    assert "not found" in status.value
    assert "Select or install" in test_status.value

    dialog.client = SimpleNamespace(binary="verified-mutagen")
    app_module.MainWindow.check_onboarding_cli(dialog)
    app_module.MainWindow.run_onboarding_local_test(dialog)
    assert len(queued) == 2
    assert "Checking CLI" in status.value
    assert "disposable" in test_status.value


def test_onboarding_cli_result_distinguishes_partial_help_failure() -> None:
    status = TextRecorder()
    dialog = SimpleNamespace(onboarding_cli_status=status)
    result = SimpleNamespace(
        capabilities=("sync",),
        architectures=("x86_64",),
        version="Mutagen version 0.18.1",
        error="forward help unavailable",
        binary="selected-mutagen",
    )
    app_module.MainWindow.show_onboarding_cli_result(dialog, result)
    assert "Some help checks failed:" in status.value

    result.error = ""
    app_module.MainWindow.show_onboarding_cli_result(dialog, result)
    assert "Some help checks failed:" not in status.value


def test_onboarding_completion_updates_and_rolls_back_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[dict[str, object]] = []
    monkeypatch.setattr(
        app_module,
        "write_settings",
        lambda conf: written.append(dict(conf)),
    )
    edit = TextRecorder()
    messages = TextRecorder()
    dialog = SimpleNamespace(
        conf={"check_updates_on_startup": False},
        _onboarding_pending_client=SimpleNamespace(binary="selected-mutagen"),
        binary_edit=edit,
        onboarding_update_check=SimpleNamespace(isChecked=lambda: True),
        statusBar=lambda: messages,
    )
    app_module.MainWindow.complete_onboarding(dialog)
    assert dialog.conf["onboarding_completed"] is True
    assert dialog.conf["binary"] == "selected-mutagen"
    assert dialog.conf["check_updates_on_startup"] is True
    assert edit.value == "selected-mutagen"
    assert written[-1]["onboarding_completed"] is True

    # No binary edit widget, no optional update checkbox: both are safe.
    other = SimpleNamespace(
        conf={"check_updates_on_startup": False},
        _onboarding_pending_client=SimpleNamespace(binary="headless-mutagen"),
        statusBar=lambda: messages,
    )
    app_module.MainWindow.complete_onboarding(other)
    assert other.conf["binary"] == "headless-mutagen"
    assert other.conf["onboarding_completed"] is True

    missing = SimpleNamespace(
        conf={"check_updates_on_startup": False},
        _onboarding_pending_client=None,
        statusBar=lambda: messages,
    )
    app_module.MainWindow.complete_onboarding(missing)
    assert missing.conf["onboarding_completed"] is True
    assert "binary" not in missing.conf

    def fail_save(_conf: object) -> None:
        raise OSError("read-only profile")

    monkeypatch.setattr(app_module, "write_settings", fail_save)
    failed_dialog = SimpleNamespace(
        conf={"onboarding_completed": False, "check_updates_on_startup": False},
        _onboarding_pending_client=None,
        onboarding_update_check=SimpleNamespace(isChecked=lambda: True),
        statusBar=lambda: messages,
    )
    app_module.MainWindow.complete_onboarding(failed_dialog)
    assert failed_dialog.conf["onboarding_completed"] is False
    assert failed_dialog.conf["check_updates_on_startup"] is False
    assert "Could not save onboarding" in messages.value


def test_log_tail_picker_cancel_selection_and_render_coalescing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = [""]
    started: list[int] = []
    requests: list[str] = []
    messages = TextRecorder()
    lines = TextRecorder()
    dialog = SimpleNamespace(
        tail_file=None,
        tail_timer=SimpleNamespace(start=lambda value: started.append(value)),
        tail_lines=lines,
        tail_info=messages,
        poll_tail=lambda: requests.append("poll"),
        _tail_render_pending=False,
        _render_pending_tail=lambda: None,
    )
    monkeypatch.setattr(app_module.QFileDialog, "getOpenFileName", lambda *_args: (selected[0], ""))
    monkeypatch.setattr(app_module, "FileTail", lambda path: SimpleNamespace(path=path))
    app_module.MainWindow.choose_tail_file(dialog)
    assert dialog.tail_file is None

    selected[0] = str(tmp_path / "tail.log")
    app_module.MainWindow.choose_tail_file(dialog)
    assert dialog.tail_file.path == selected[0]
    assert started == [900]
    assert requests == ["poll"]

    repaint: list[int] = []
    monkeypatch.setattr(
        app_module.QTimer,
        "singleShot",
        lambda delay, callback: repaint.append(delay),
    )
    app_module.MainWindow.schedule_tail_render(dialog)
    app_module.MainWindow.schedule_tail_render(dialog)
    assert repaint == [160]
    assert dialog._tail_render_pending is True


def test_log_tail_export_cancel_success_and_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = [""]
    errors: list[str] = []
    dialog = SimpleNamespace(
        tail_view=SimpleNamespace(toPlainText=lambda: "local diagnostic data"),
        report_error=lambda error: errors.append(error),
    )
    monkeypatch.setattr(
        app_module.QFileDialog, "getSaveFileName", lambda *_args: (destination[0], "")
    )
    app_module.MainWindow.export_tail_file(dialog)
    assert not list(tmp_path.iterdir())

    path = tmp_path / "tail.txt"
    destination[0] = str(path)
    app_module.MainWindow.export_tail_file(dialog)
    assert path.read_text(encoding="utf-8") == "local diagnostic data\n"

    destination[0] = str(tmp_path)
    app_module.MainWindow.export_tail_file(dialog)
    assert errors


def test_portable_import_preview_excludes_missing_controls() -> None:
    profile = SimpleNamespace(profile=SimpleNamespace(id="profile"))
    preset = SimpleNamespace(preset=SimpleNamespace(id="preset"))
    dialog = SimpleNamespace(
        preview=[profile],
        ignore_preview=[preset],
        table=SimpleNamespace(cellWidget=lambda _row, _column: None),
        ignore_table=SimpleNamespace(cellWidget=lambda _row, _column: None),
    )
    assert app_module.PortableImportPreviewDialog.profile_choices(dialog) == {}
    assert app_module.PortableImportPreviewDialog.ignore_choices(dialog) == {}


def test_session_dialog_directory_picker_preserves_cancel_and_platform_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = [""]
    control = TextRecorder()
    dialog = SimpleNamespace(a=control)
    monkeypatch.setattr(app_module.QFileDialog, "getExistingDirectory", lambda *_args: selected[0])
    app_module.SessionDialog.browse_alpha(dialog)
    assert control.calls == []

    selected[0] = "/alpha/beta"
    app_module.SessionDialog.browse_alpha(dialog)
    expected = os.path.normpath(selected[0]) if os.name == "nt" else selected[0]
    assert control.value == expected


def test_history_clear_respects_optional_recorder() -> None:
    history_clears: list[str] = []
    recorder_clears: list[str] = []
    messages: list[str] = []
    dialog = SimpleNamespace(
        logs=["old"],
        log_view=TextRecorder(),
        history=SimpleNamespace(clear_events=lambda: history_clears.append("history")),
        recorder=None,
        add_log=lambda message: messages.append(message),
    )
    app_module.MainWindow.clear_logs(dialog)
    assert history_clears == ["history"]
    assert messages == ["UI history cleared"]

    dialog.recorder = SimpleNamespace(clear_events=lambda: recorder_clears.append("recorder"))
    app_module.MainWindow.clear_logs(dialog)
    assert recorder_clears == ["recorder"]
