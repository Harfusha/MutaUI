from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

import mutaui.ui.project_viewer as project_viewer_module
from mutaui.projects.native_project import (
    ProjectReferenceStore,
    ProjectSession,
    load_native_project,
)
from mutaui.services.action_planner import ActionPlanner
from mutaui.ui.project_viewer import (
    NativeProjectActionDialog,
    NativeProjectCreationDialog,
    NativeProjectManagerDialog,
    NativeProjectViewerDialog,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_project_viewer_shows_hooks_without_running_or_rewriting(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    source = "sync: {}\nbeforeCreate:\n  - touch sentinel\n"
    project.write_text(source, encoding="utf-8")

    dialog = NativeProjectViewerDialog(project)
    dialog._watch_current_project()

    assert "touch sentinel" in dialog.summary.toPlainText()
    assert "never executed" in dialog.summary.toPlainText()
    assert dialog.yaml.toPlainText() == source
    assert project.read_text(encoding="utf-8") == source


def test_project_viewer_explains_action_availability_requirements(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")

    no_executor = NativeProjectViewerDialog(project)
    assert not no_executor.actions_button.isEnabled()
    assert "Select a Mutagen CLI" in no_executor.actions_button.toolTip()

    no_audit = NativeProjectViewerDialog(project, executor=object())
    assert not no_audit.actions_button.isEnabled()
    assert "audit path is required" in no_audit.actions_button.toolTip()

    ready = NativeProjectViewerDialog(
        project, executor=object(), audit_path=tmp_path / "audit.jsonl"
    )
    assert ready.actions_button.isEnabled()


def test_project_viewer_does_not_readd_already_watched_project_paths(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    dialog = NativeProjectViewerDialog(project)
    watched_file = str(dialog.current.path)
    watched_directory = str(dialog.current.path.parent)

    class ExistingWatcher:
        def files(self):
            return [watched_file]

        def directories(self):
            return [watched_directory]

        def addPath(self, _path):
            raise AssertionError("Existing paths must not be registered twice")

        def removePath(self, _path):
            raise AssertionError("The active project paths must remain watched")

    dialog._watcher = ExistingWatcher()
    dialog._watch_current_project()


def test_project_viewer_removes_stale_watch_paths_and_skips_unchanged_refresh(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    dialog = NativeProjectViewerDialog(project)
    removed = []

    class StaleWatcher:
        def files(self):
            return ["stale-file.yml"]

        def directories(self):
            return ["stale-directory"]

        def removePath(self, path):
            removed.append(path)

        def addPath(self, _path):
            pass

    dialog._watcher = StaleWatcher()
    dialog._watch_current_project()
    assert removed == ["stale-file.yml", "stale-directory"]

    dialog.refresh_project = lambda: (_ for _ in ()).throw(
        AssertionError("Unchanged YAML must not trigger a full refresh")
    )
    dialog._refresh_external_change()


def test_project_viewer_renders_effective_settings_commands_and_retained_keys(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    dialog = NativeProjectViewerDialog(project)
    snapshot = replace(
        dialog.current,
        sessions=(
            ProjectSession("build", "sync", False, "./source", "dev@example:/srv"),
            ProjectSession(
                "web",
                "forward",
                None,
                "tcp:localhost:8080",
                "tcp:localhost:80",
                (("watch.mode", "portable"),),
            ),
        ),
        sync_default_settings=(("ignore.vcs", "true"),),
        commands=(("logs", "echo logs"),),
        unknown_root_keys=("x-local-note",),
        warnings=("unknown extension is retained",),
    )

    dialog._render(snapshot)
    text = dialog.summary.toPlainText()

    assert "Sync sessions: 1" in text
    assert "Forward sessions: 1" in text
    assert "flushOnCreate disabled" in text
    assert "Effective watch.mode: portable" in text
    assert "Sync default values:" in text
    assert "logs: echo logs" in text
    assert "Other root keys retained in source:" in text
    assert "Validation notes:" in text


def test_project_manager_selection_uses_reference_id(tmp_path):
    _app()
    project = tmp_path / "project" / "mutagen.yml"
    store_path = tmp_path / "mutagen-projects.json"
    reference = ProjectReferenceStore(store_path).add(project)

    dialog = NativeProjectManagerDialog(store_path)
    dialog.table.selectRow(0)

    assert dialog.selected_reference() == reference


def test_project_viewer_debounces_external_file_changes(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    dialog = NativeProjectViewerDialog(project)

    project.write_text("sync:\n  app:\n    alpha: ./src\n", encoding="utf-8")
    dialog._schedule_external_refresh()
    dialog._schedule_external_refresh()
    assert dialog._refresh_timer.isSingleShot()
    assert dialog._refresh_timer.interval() == 300
    assert dialog._refresh_timer.isActive()
    dialog._refresh_timer.timeout.emit()

    assert "alpha: ./src" in dialog.diff.toPlainText()
    assert dialog.current.sha256 != dialog.baseline.sha256


def test_project_action_preview_lists_hooks_and_resets_consent_on_change(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\nbeforeCreate:\n  - docker compose up -d\n", encoding="utf-8")

    class Executor:
        def run(self, argv, *, timeout_seconds, readonly=False):
            raise AssertionError("Preview must not execute commands.")

    dialog = NativeProjectActionDialog(
        load_native_project(project), Executor(), tmp_path / "project-actions.jsonl"
    )
    dialog.action.setCurrentText("start")

    assert "docker compose up -d" in dialog.preview.toPlainText()
    assert "--project-file" in dialog.preview.toPlainText()
    assert "Risk: R3" in dialog.preview.toPlainText()
    assert "Typed confirmation required: APPLY project:" in dialog.preview.toPlainText()
    dialog.consent.setChecked(True)
    dialog.shell_consent.setChecked(True)
    dialog.action.setCurrentText("list")
    assert not dialog.consent.isChecked()
    assert not dialog.shell_consent.isChecked()


def test_replica_project_start_typed_confirmation_cancel_never_runs(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text(
        "sync:\n  app:\n    alpha: ./src\n    beta: ./replica\n    mode: one-way-replica\n",
        encoding="utf-8",
    )

    class Executor:
        def __init__(self):
            self.calls = []

        def run(self, argv, *, timeout_seconds, readonly=False):
            self.calls.append((argv, timeout_seconds, readonly))
            raise AssertionError("A cancelled R3 project start must not execute.")

    executor = Executor()
    planner = ActionPlanner(now=lambda: 1.0)
    dialog = NativeProjectActionDialog(
        load_native_project(project), executor, tmp_path / "project-actions.jsonl", planner
    )
    dialog.action.setCurrentText("start")
    dialog.consent.setChecked(True)
    typed_prompts = []
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args: typed_prompts.append(True) or ("", False),
    )

    dialog.execute()

    assert "Risk: R3" in dialog.preview.toPlainText()
    assert typed_prompts == [True]
    assert executor.calls == []
    assert planner.audit[-1].decision == "cancelled"


def test_project_creation_preview_requires_valid_new_file_path(tmp_path):
    _app()
    dialog = NativeProjectCreationDialog(tmp_path / "audit.jsonl")

    dialog.preview()
    assert not dialog.create_button.isEnabled()
    assert "Choose the new project file path." in dialog.status.text()

    dialog.path.setText(str(tmp_path / "wrong-name.yml"))
    dialog.preview()
    assert "must be named mutagen.yml" in dialog.status.text()

    dialog.path.setText(str(tmp_path / "missing" / "mutagen.yml"))
    dialog.preview()
    assert "directory must already exist" in dialog.status.text()

    dialog.path.setText(str(tmp_path / "mutagen.yml"))
    dialog.preview()
    assert dialog.create_button.isEnabled()
    assert "Preview valid" in dialog.status.text()

    (tmp_path / "mutagen.yml").write_text("sync: {}\n", encoding="utf-8")
    dialog.preview()
    assert not dialog.create_button.isEnabled()
    assert "never overwrites" in dialog.status.text()


def test_project_creation_chooser_cancel_and_create_success(tmp_path, monkeypatch):
    _app()
    dialog = NativeProjectCreationDialog(tmp_path / "audit.jsonl")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: ("", ""))
    dialog.choose_path()
    assert dialog.path.text() == ""

    project = tmp_path / "mutagen.yml"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_args: (str(project), ""))
    dialog.choose_path()
    dialog.preview()
    dialog.create_file()

    assert dialog.created_path == project
    assert project.is_file()


def test_project_viewer_controls_follow_validity_and_audit_requirements(tmp_path):
    _app()
    invalid = tmp_path / "invalid.yml"
    invalid.write_text("sync: [", encoding="utf-8")

    invalid_viewer = NativeProjectViewerDialog(invalid, audit_path=tmp_path / "audit.jsonl")
    assert not invalid_viewer.edit_button.isEnabled()
    assert not invalid_viewer.reference_button.isEnabled()
    assert "Invalid native project" in invalid_viewer.summary.toPlainText()

    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    no_audit = NativeProjectViewerDialog(project)
    assert not no_audit.edit_button.isEnabled()
    assert "audit path" in no_audit.edit_button.toolTip()
    assert "Select a Mutagen CLI" in no_audit.actions_button.toolTip()

    no_executor = NativeProjectViewerDialog(project, audit_path=tmp_path / "audit.jsonl")
    assert no_executor.edit_button.isEnabled()
    assert not no_executor.actions_button.isEnabled()
    assert "Select a Mutagen CLI" in no_executor.actions_button.toolTip()


def test_project_viewer_open_another_cancel_and_refresh_updates_snapshot(tmp_path, monkeypatch):
    _app()
    original = tmp_path / "mutagen.yml"
    original.write_text("sync: {}\n", encoding="utf-8")
    other = tmp_path / "other.yml"
    other.write_text("forward: {}\n", encoding="utf-8")
    viewer = NativeProjectViewerDialog(original)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    viewer.open_another()
    assert viewer.current.path == original

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(other), ""))
    viewer.open_another()
    assert viewer.current.path == other
    assert viewer.tabs.currentWidget() is viewer.summary
    assert viewer.diff.toPlainText() == "No external changes detected."

    other.write_text("forward:\n  defaults:\n    watch: true\n", encoding="utf-8")
    viewer.refresh_project()
    assert "watch: true" in viewer.yaml.toPlainText()
    assert viewer.tabs.currentWidget() is viewer.diff
    assert viewer.reference_button.isEnabled() is False


def test_project_viewer_add_reference_handles_error_and_success(tmp_path, monkeypatch):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")

    class Store:
        def __init__(self, fail=False):
            self.fail = fail
            self.added = []

        def add(self, path):
            if self.fail:
                raise OSError("reference write failed")
            self.added.append(path)
            return type("Reference", (), {"name": "mutagen.yml"})()

    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("warning"))
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append("info"))

    viewer_without_store = NativeProjectViewerDialog(project)
    viewer_without_store.add_reference()
    assert messages == []

    failing_store = Store(fail=True)
    NativeProjectViewerDialog(project, failing_store).add_reference()
    assert messages == ["warning"]

    store = Store()
    NativeProjectViewerDialog(project, store).add_reference()
    assert store.added == [project]
    assert messages == ["warning", "info"]


def test_project_viewer_baseline_edit_and_action_dialog_gates(tmp_path, monkeypatch):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    audit = tmp_path / "audit.jsonl"
    viewer = NativeProjectViewerDialog(project)

    viewer.accept_current_baseline()
    assert viewer.baseline == viewer.current
    assert "new in-memory comparison baseline" in viewer.diff.toPlainText()

    viewer.edit_yaml()
    assert viewer.current.path == project
    assert not audit.exists()
    viewer.open_actions()
    assert viewer.tabs.currentWidget() is viewer.diff

    class Editor:
        def __init__(self, *_args):
            self.receipt = object()

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(project_viewer_module, "ProjectYamlEditorDialog", Editor)
    editor_viewer = NativeProjectViewerDialog(project, audit_path=audit)
    editor_viewer.edit_yaml()
    assert editor_viewer.current.path == project

    class Executor:
        pass

    calls = []

    class ActionDialog:
        def __init__(self, *_args):
            pass

        def exec(self):
            calls.append("exec")
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(project_viewer_module, "NativeProjectActionDialog", ActionDialog)
    action_viewer = NativeProjectViewerDialog(project, executor=Executor(), audit_path=audit)
    action_viewer.open_actions()
    assert calls == ["exec"]


def test_project_manager_import_open_and_remove_decisions(tmp_path, monkeypatch):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    store_path = tmp_path / "references.json"
    store = ProjectReferenceStore(store_path)
    reference = store.add(project)
    manager = NativeProjectManagerDialog(store_path)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: ("", ""))
    manager.import_project()
    assert manager.table.rowCount() == 1

    invalid = tmp_path / "invalid.yml"
    invalid.write_text("sync: [", encoding="utf-8")
    messages = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(invalid), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("warning"))
    manager.import_project()
    assert messages == ["warning"]

    dialogs = []

    class Viewer:
        def __init__(self, *args, **kwargs):
            dialogs.append("viewer")

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(project_viewer_module, "NativeProjectViewerDialog", Viewer)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(project), ""))
    manager.import_project()
    manager.table.selectRow(0)
    manager.open_selected()
    assert dialogs == ["viewer", "viewer"]

    manager.table.setCurrentCell(-1, -1)
    manager.open_selected()
    manager.remove_selected()
    assert manager.reference_store.references == [reference]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Cancel,
    )
    manager.table.selectRow(0)
    manager.remove_selected()
    assert manager.reference_store.references == [reference]

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: QMessageBox.StandardButton.Yes,
    )
    manager.remove_selected()
    assert manager.reference_store.references == []


@pytest.mark.parametrize(
    ("fail_postcheck", "expected"),
    [
        (False, "Mutagen returned no project status output."),
        (True, "list verification failed"),
    ],
)
def test_project_action_execute_reports_success_and_postcheck_failure(
    tmp_path, monkeypatch, fail_postcheck, expected
):
    from types import SimpleNamespace

    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    calls = []

    class Executor:
        def run(self, argv, *, timeout_seconds, readonly=False):
            calls.append((argv, timeout_seconds, readonly))
            if fail_postcheck and argv[1:2] == ("list",) and argv[0] == "project":
                raise OSError("list verification failed")
            return SimpleNamespace(stdout="", stderr="", returncode=0)

    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, message: messages.append(message),
    )
    dialog = NativeProjectActionDialog(
        load_native_project(project), Executor(), tmp_path / "audit.jsonl"
    )
    dialog.action.setCurrentText("start")
    dialog.consent.setChecked(True)

    dialog.execute()

    assert len(calls) == 3
    assert expected in messages[0]


def test_project_action_preview_renders_risk_session_and_named_command_paths(tmp_path):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text(
        "sync:\n  app:\n    alpha: ./src\n    beta: ./replica\n    mode: one-way-replica\n"
        "beforeCreate:\n  - echo prepare\ncommands:\n  logs: echo logs\n",
        encoding="utf-8",
    )

    class Executor:
        pass

    dialog = NativeProjectActionDialog(
        load_native_project(project), Executor(), tmp_path / "audit.jsonl"
    )
    assert "Sync app" in dialog.preview.toPlainText()
    assert "None declared" not in dialog.preview.toPlainText()

    dialog.action.setCurrentText("start")
    assert "Risk: R3" in dialog.preview.toPlainText()
    assert "Typed confirmation required" in dialog.preview.toPlainText()
    assert "Start creates all declared sessions" in dialog.preview.toPlainText()
    for action, description in (
        ("flush", "Flush triggers synchronization"),
        ("reset", "Reset clears synchronization history"),
        ("terminate", "Terminate ends project sessions"),
    ):
        dialog.action.setCurrentText(action)
        assert description in dialog.preview.toPlainText()

    dialog.action.setCurrentText("run")
    dialog.command.setCurrentText("logs")
    assert "Custom shell command:" in dialog.preview.toPlainText()
    assert "echo logs" in dialog.preview.toPlainText()
    assert not dialog.shell_consent.isHidden()


def test_project_action_cancels_r3_plan_when_second_confirmation_is_declined(tmp_path, monkeypatch):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    cancelled = []
    planner = type("Planner", (), {"cancel": lambda _self, plan_id: cancelled.append(plan_id)})()
    monkeypatch.setattr(
        project_viewer_module,
        "prepare_action_plan",
        lambda *_args: type(
            "Plan",
            (),
            {
                "requires_typed_confirmation": True,
                "typed_confirmation": "APPLY sync-project",
                "plan_id": "plan-exact",
                "preflight_fingerprint": "fingerprint",
            },
        )(),
    )
    prompts = []
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args: (prompts.append("typed confirmation") or "", False),
    )
    dialog = NativeProjectActionDialog(
        load_native_project(project),
        object(),
        tmp_path / "audit.jsonl",
        action_planner=planner,
    )
    dialog.action.setCurrentText("reset")

    dialog.execute()

    assert prompts == ["typed confirmation"]
    assert cancelled == ["plan-exact"]


@pytest.mark.parametrize(
    (
        "requires_confirmation",
        "accepted",
        "confirmation",
        "postcheck_error",
        "postcheck_stdout",
        "expected_suffix",
    ),
    [
        (False, False, None, None, None, ""),
        (
            True,
            True,
            "APPLY project:exact-id",
            "audit write failed",
            None,
            "Action ran; verification or audit issue: audit write failed",
        ),
        (
            False,
            False,
            None,
            None,
            "validated project",
            "Post-check:\nvalidated project",
        ),
        (
            False,
            False,
            None,
            None,
            "",
            "Mutagen returned no project status output.",
        ),
    ],
)
def test_project_action_forwards_optional_exact_confirmation_to_planner(
    tmp_path,
    monkeypatch,
    requires_confirmation,
    accepted,
    confirmation,
    postcheck_error,
    postcheck_stdout,
    expected_suffix,
):
    from types import SimpleNamespace

    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    plan = SimpleNamespace(read_only=False)
    action_plan = SimpleNamespace(
        requires_typed_confirmation=requires_confirmation,
        typed_confirmation="APPLY project:exact-id",
        plan_id="plan-exact",
        preflight_fingerprint="preflight-exact",
    )
    consent_calls = []

    class Planner:
        def consent(self, plan_id, **kwargs):
            consent_calls.append((plan_id, kwargs))
            return "consented-plan"

    monkeypatch.setattr(project_viewer_module, "prepare_action_plan", lambda *_args: action_plan)
    prompts = []
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args: (
            prompts.append(True) or ("APPLY project:exact-id" if accepted else "", accepted)
        ),
    )
    receipt = SimpleNamespace(
        action_result=SimpleNamespace(stdout="completed"),
        postcheck_error=postcheck_error,
        postcheck_result=(
            SimpleNamespace(stdout=postcheck_stdout) if postcheck_stdout is not None else None
        ),
    )
    execute_calls = []
    messages = []
    monkeypatch.setattr(
        project_viewer_module,
        "execute_project_action",
        lambda *args, **kwargs: execute_calls.append((args, kwargs)) or receipt,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: messages.append(_args[-1]))

    dialog = NativeProjectActionDialog(
        load_native_project(project), object(), tmp_path / "audit.jsonl", Planner()
    )
    dialog.current_plan = lambda: plan
    dialog.execute()

    assert prompts == ([True] if requires_confirmation else [])
    assert len(consent_calls) == 1
    assert consent_calls[0][0] == "plan-exact"
    assert consent_calls[0][1]["typed_confirmation"] == confirmation
    assert consent_calls[0][1]["current_preflight_fingerprint"] == "preflight-exact"
    assert len(execute_calls) == 1
    assert len(messages) == 1
    assert messages[0].startswith("completed")
    if expected_suffix:
        assert expected_suffix in messages[0]


@pytest.mark.parametrize("has_planner", [False, True])
def test_project_action_execution_failure_warns_and_cancels_created_plan(
    tmp_path, monkeypatch, has_planner
):
    from types import SimpleNamespace

    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    plan = SimpleNamespace(read_only=False)
    action_plan = SimpleNamespace(
        requires_typed_confirmation=False,
        plan_id="plan-failed",
        preflight_fingerprint="fingerprint",
    )
    cancelled = []

    class Planner:
        def consent(self, *_args, **_kwargs):
            return action_plan

        def cancel(self, plan_id):
            cancelled.append(plan_id)
            raise ValueError("already cancelled")

    planner = Planner() if has_planner else None
    if has_planner:
        monkeypatch.setattr(
            project_viewer_module, "prepare_action_plan", lambda *_args: action_plan
        )
    monkeypatch.setattr(
        project_viewer_module,
        "execute_project_action",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("execution failed")),
    )
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))
    dialog = NativeProjectActionDialog(
        load_native_project(project), object(), tmp_path / "audit.jsonl", planner
    )
    dialog.current_plan = lambda: plan

    dialog.execute()

    assert warnings == ["execution failed"]
    assert cancelled == (["plan-failed"] if has_planner else [])


@pytest.mark.parametrize(
    ("accepted", "has_receipt", "writes_change"),
    [(False, False, False), (True, False, False), (True, True, True)],
)
def test_project_viewer_yaml_edit_requires_acceptance_and_receipt(
    tmp_path, monkeypatch, accepted, has_receipt, writes_change
):
    _app()
    project = tmp_path / "mutagen.yml"
    original = "sync: {}\n"
    changed = "sync: {}\ncommands:\n  logs: echo logs\n"
    project.write_text(original, encoding="utf-8")
    dialog = NativeProjectViewerDialog(project, audit_path=tmp_path / "audit.jsonl")

    class Editor:
        receipt = object() if has_receipt else None

        def __init__(self, *_args):
            pass

        def exec(self):
            if writes_change:
                project.write_text(changed, encoding="utf-8")
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(project_viewer_module, "ProjectYamlEditorDialog", Editor)
    dialog.edit_yaml()

    if writes_change:
        assert dialog.current.raw_text.replace("\r\n", "\n") == changed
        assert "saved with a backup" in dialog.diff.toPlainText()
    else:
        assert project.read_text(encoding="utf-8").replace("\r\n", "\n") == original
        assert dialog.current.raw_text.replace("\r\n", "\n") == original


@pytest.mark.parametrize("accepted", [False, True])
def test_project_viewer_action_refreshes_after_accepted_action_only(
    tmp_path, monkeypatch, accepted
):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    dialog = NativeProjectViewerDialog(
        project, executor=object(), audit_path=tmp_path / "audit.jsonl"
    )
    refreshes = []
    dialog.refresh_project = lambda: refreshes.append(True)

    class ActionDialog:
        def __init__(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(project_viewer_module, "NativeProjectActionDialog", ActionDialog)
    dialog.open_actions()

    assert len(refreshes) == (2 if accepted else 1)


@pytest.mark.parametrize("invalidate_after_refresh", [True, False])
def test_project_viewer_action_stops_if_project_becomes_invalid_or_audit_is_missing(
    tmp_path, monkeypatch, invalidate_after_refresh
):
    _app()
    project = tmp_path / "mutagen.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    audit_path = None if not invalidate_after_refresh else tmp_path / "audit.jsonl"
    dialog = NativeProjectViewerDialog(project, executor=object(), audit_path=audit_path)
    refreshes = []

    def refresh():
        refreshes.append(True)
        if invalidate_after_refresh:
            dialog.current = replace(dialog.current, valid=False)

    monkeypatch.setattr(dialog, "refresh_project", refresh)
    monkeypatch.setattr(
        project_viewer_module,
        "NativeProjectActionDialog",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Actions must not open without a valid audited project")
        ),
    )

    dialog.open_actions()

    assert refreshes == [True]


@pytest.mark.parametrize(
    ("accepted", "created_path"),
    [(False, None), (True, None)],
)
def test_project_manager_create_stops_on_cancel_or_missing_created_path(
    tmp_path, monkeypatch, accepted, created_path
):
    _app()
    manager = NativeProjectManagerDialog(tmp_path / "references.json")

    class CreationDialog:
        def __init__(self, *_args):
            self.created_path = created_path

        def exec(self):
            return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected

    monkeypatch.setattr(project_viewer_module, "NativeProjectCreationDialog", CreationDialog)
    monkeypatch.setattr(
        project_viewer_module,
        "NativeProjectViewerDialog",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("No viewer should open without a created path")
        ),
    )

    manager.create_project()


def test_project_manager_opens_viewer_after_successful_project_creation(tmp_path, monkeypatch):
    _app()
    project = tmp_path / "created.yml"
    project.write_text("sync: {}\n", encoding="utf-8")
    manager = NativeProjectManagerDialog(tmp_path / "references.json")
    opened = []

    class CreationDialog:
        created_path = project

        def __init__(self, *_args):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    class Viewer:
        def __init__(self, path, *_args, **_kwargs):
            opened.append(path)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(project_viewer_module, "NativeProjectCreationDialog", CreationDialog)
    monkeypatch.setattr(project_viewer_module, "NativeProjectViewerDialog", Viewer)
    refreshes = []
    monkeypatch.setattr(manager, "refresh", lambda: refreshes.append(True))

    manager.create_project()

    assert opened == [project]
    assert refreshes == [True]
