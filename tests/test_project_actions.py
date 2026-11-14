import json

import pytest

from mutaui.adapters.cli_executor import CommandResult
from mutaui.projects.native_project import (
    ProjectStoreError,
    create_native_project_file,
    load_native_project,
    validate_native_project_text,
)
from mutaui.projects.project_actions import (
    ProjectActionError,
    execute_project_action,
    plan_project_action,
    prepare_action_plan,
)
from mutaui.services.action_planner import ActionPlanner

PROJECT_TEXT = """sync:
  defaults: {}
  app:
    alpha: ./src
    beta: user@example.org:/srv/app
beforeCreate:
  - docker compose up -d
commands:
  logs: docker compose logs
"""


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def run(self, argv, *, timeout_seconds, readonly=False):
        call = (tuple(argv), timeout_seconds, readonly)
        self.calls.append(call)
        return CommandResult(tuple(argv), 0, "sessions: app", "", 0.01)


def test_native_project_creation_validates_and_never_overwrites(tmp_path):
    path = tmp_path / "mutagen.yml"
    audit = tmp_path / "project-actions.jsonl"
    created = create_native_project_file(path, PROJECT_TEXT, audit_path=audit)
    assert created.valid
    assert path.read_text(encoding="utf-8") == PROJECT_TEXT
    with pytest.raises(ProjectStoreError, match="never overwritten"):
        create_native_project_file(path, PROJECT_TEXT.replace("./src", "./other"), audit_path=audit)
    assert "alpha: ./src" in path.read_text(encoding="utf-8")
    assert '"phase":"created"' in audit.read_text(encoding="utf-8")


def test_native_project_creation_rejects_invalid_or_unsafe_shape(tmp_path):
    assert not validate_native_project_text("sync: [not, mapping]\n")[0]
    assert not validate_native_project_text("sync:\n  app:\n    alpha: ./src\n")[0]
    with pytest.raises(ProjectStoreError, match="invalid native project"):
        create_native_project_file(
            tmp_path / "mutagen.yml", "sync: [bad]\n", audit_path=tmp_path / "audit.jsonl"
        )
    with pytest.raises(ProjectStoreError, match="named mutagen.yml"):
        create_native_project_file(
            tmp_path / "project.yml", PROJECT_TEXT, audit_path=tmp_path / "audit.jsonl"
        )


def test_project_action_preview_contains_exact_file_and_shell_hooks(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    snapshot = load_native_project(path)

    start = plan_project_action(snapshot, "start")
    run = plan_project_action(snapshot, "run", "logs")

    assert start.argv == ("project", "start", "--project-file", str(path.absolute()))
    assert start.hooks == (("beforeCreate", ("docker compose up -d",)),)
    assert start.shell_consent_required
    assert run.command_text == "docker compose logs"
    assert run.shell_consent_required


def test_project_action_requires_consent_and_verifies_after_operation(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "start")
    executor = FakeExecutor()
    audit = tmp_path / "project-actions.jsonl"

    with pytest.raises(ProjectActionError, match="Explicit consent"):
        execute_project_action(plan, executor, consent=False, shell_consent=False, audit_path=audit)
    with pytest.raises(ProjectActionError, match="hooks or shell commands"):
        execute_project_action(plan, executor, consent=True, shell_consent=False, audit_path=audit)
    assert executor.calls == []

    receipt = execute_project_action(
        plan, executor, consent=True, shell_consent=True, audit_path=audit
    )

    assert receipt.verified
    assert [call[0] for call in executor.calls] == [
        ("project", "start", "--help"),
        plan.argv,
        ("project", "list", "--project-file", str(path.absolute())),
    ]
    assert executor.calls[0][2] is True
    assert executor.calls[1][2] is False
    assert executor.calls[2][2] is True
    events = audit.read_text(encoding="utf-8").splitlines()
    assert '"phase":"prepared"' in events[0]
    assert '"phase":"completed"' in events[1]
    assert "docker compose up -d" not in audit.read_text(encoding="utf-8")


def test_project_action_rejects_stale_file_before_cli(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "run", "logs")
    path.write_text(PROJECT_TEXT.replace("./src", "./new"), encoding="utf-8")
    executor = FakeExecutor()

    with pytest.raises(ProjectActionError, match="changed after preview"):
        execute_project_action(
            plan,
            executor,
            consent=True,
            shell_consent=True,
            audit_path=tmp_path / "project-actions.jsonl",
        )
    assert executor.calls == []


def test_project_action_uses_shared_planner_and_exact_typed_scope(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    project_plan = plan_project_action(load_native_project(path), "start")
    planner = ActionPlanner(now=lambda: 1.0)
    action_plan = prepare_action_plan(project_plan, planner)

    assert action_plan.risk == "R3"
    assert action_plan.argv == project_plan.argv
    assert action_plan.target_ids[0].startswith("project:")
    action_plan = planner.consent(
        action_plan.plan_id,
        consent=True,
        current_preflight_fingerprint=project_plan.project_sha256,
        typed_confirmation=action_plan.typed_confirmation,
    )
    receipt = execute_project_action(
        project_plan,
        FakeExecutor(),
        consent=True,
        shell_consent=True,
        audit_path=tmp_path / "actions.jsonl",
        action_planner=planner,
        action_plan=action_plan,
    )

    assert receipt.verified
    assert planner.audit[-1].decision == "finished"


def test_project_terminate_is_planned_as_r3_and_checks_sessions_absent(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    project_plan = plan_project_action(load_native_project(path), "terminate")
    planner = ActionPlanner(now=lambda: 1.0)
    action_plan = prepare_action_plan(project_plan, planner)
    action_plan = planner.consent(
        action_plan.plan_id,
        consent=True,
        current_preflight_fingerprint=project_plan.project_sha256,
        typed_confirmation=action_plan.typed_confirmation,
    )

    class TerminateExecutor(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            self.calls.append((tuple(argv), timeout_seconds, readonly))
            output = "sessions terminated" if tuple(argv[:2]) == ("project", "terminate") else "[]"
            return CommandResult(tuple(argv), 0, output, "", 0.01)

    executor = TerminateExecutor()
    receipt = execute_project_action(
        project_plan,
        executor,
        consent=True,
        shell_consent=True,
        audit_path=tmp_path / "actions.jsonl",
        action_planner=planner,
        action_plan=action_plan,
    )

    assert receipt.verified
    assert project_plan.hooks == ()
    assert planner.audit[-1].decision == "finished"


def test_project_terminate_verifies_absence_when_native_project_is_no_longer_running(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    project_plan = plan_project_action(load_native_project(path), "terminate")

    class TerminateExecutor(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            self.calls.append((tuple(argv), timeout_seconds, readonly))
            if tuple(argv[:2]) == ("project", "terminate"):
                return CommandResult(tuple(argv), 0, "terminated", "", 0.01)
            if tuple(argv[:2]) == ("sync", "list"):
                return CommandResult(tuple(argv), 0, "[]", "", 0.01)
            if tuple(argv[:2]) == ("forward", "list"):
                return CommandResult(tuple(argv), 0, "[]", "", 0.01)
            raise AssertionError(f"Unexpected command: {argv}")

    executor = TerminateExecutor()
    receipt = execute_project_action(
        project_plan,
        executor,
        consent=True,
        shell_consent=True,
        audit_path=tmp_path / "actions.jsonl",
    )

    assert receipt.verified
    assert receipt.postcheck_result is not None
    assert any(call[0][:2] == ("sync", "list") for call in executor.calls)
    assert any(call[0][:2] == ("forward", "list") for call in executor.calls)


def test_project_action_blocks_unknown_config_but_keeps_readonly_list(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT + "futureRoot: retained\n", encoding="utf-8")
    snapshot = load_native_project(path)

    with pytest.raises(ProjectActionError, match="unrecognized or invalid configuration"):
        plan_project_action(snapshot, "start")
    assert plan_project_action(snapshot, "list").read_only


def test_project_action_planning_rejects_invalid_unsupported_missing_and_bad_run(tmp_path):
    invalid_path = tmp_path / "invalid.yml"
    invalid_path.write_text("sync: [\n", encoding="utf-8")
    with pytest.raises(ProjectActionError, match="Invalid native project"):
        plan_project_action(load_native_project(invalid_path), "list")

    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    snapshot = load_native_project(path)
    with pytest.raises(ProjectActionError, match="Unsupported"):
        plan_project_action(snapshot, "unrecognized")
    with pytest.raises(ProjectActionError, match="Select a named"):
        plan_project_action(snapshot, "run")
    with pytest.raises(ProjectActionError, match="not declared"):
        plan_project_action(snapshot, "run", "missing")

    path.unlink()
    with pytest.raises(ProjectActionError, match="file is missing"):
        plan_project_action(snapshot, "list")


def test_project_list_is_read_only_and_needs_no_audit_or_consent(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "list")
    executor = FakeExecutor()

    receipt = execute_project_action(plan, executor)

    assert receipt.verified
    assert receipt.postcheck_result is None
    assert [call[0] for call in executor.calls] == [
        ("project", "list", "--help"),
        plan.argv,
    ]
    assert all(call[2] for call in executor.calls)


def test_project_action_rechecks_file_after_preflight_before_mutation(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "start")

    class EditingExecutor(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            call = super().run(argv, timeout_seconds=timeout_seconds, readonly=readonly)
            if tuple(argv) == ("project", "start", "--help"):
                path.write_text(PROJECT_TEXT.replace("./src", "./changed"), encoding="utf-8")
            return call

    executor = EditingExecutor()
    with pytest.raises(ProjectActionError, match="changed during preflight"):
        execute_project_action(
            plan,
            executor,
            consent=True,
            shell_consent=True,
            audit_path=tmp_path / "audit.jsonl",
        )

    assert len(executor.calls) == 1


def test_project_action_wraps_preflight_errors_without_running_mutation(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "pause")

    class BrokenPreflight(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            if tuple(argv) == ("project", "pause", "--help"):
                raise OSError("help unavailable")
            return super().run(argv, timeout_seconds=timeout_seconds, readonly=readonly)

    executor = BrokenPreflight()
    with pytest.raises(ProjectActionError, match="preflight failed: help unavailable"):
        execute_project_action(
            plan,
            executor,
            consent=True,
            audit_path=tmp_path / "audit.jsonl",
        )

    assert executor.calls == []


def test_project_action_rejects_missing_audit_and_mismatched_shared_plan(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "pause")
    executor = FakeExecutor()

    with pytest.raises(ProjectActionError, match="audit path is required"):
        execute_project_action(plan, executor, consent=True)
    assert executor.calls == []

    planner = ActionPlanner(now=lambda: 1.0)
    with pytest.raises(ProjectActionError, match="consented matching ActionPlanner"):
        execute_project_action(
            plan,
            executor,
            consent=True,
            audit_path=tmp_path / "audit.jsonl",
            action_planner=planner,
        )
    assert executor.calls == []


def test_project_action_postcheck_failure_is_reported_as_unverified(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "start")

    class MissingProject(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            if tuple(argv) == ("project", "list", "--project-file", str(path.absolute())):
                raise OSError("list unavailable")
            return super().run(argv, timeout_seconds=timeout_seconds, readonly=readonly)

    receipt = execute_project_action(
        plan,
        MissingProject(),
        consent=True,
        shell_consent=True,
        audit_path=tmp_path / "audit.jsonl",
    )

    assert not receipt.verified
    assert receipt.postcheck_error == "list unavailable"


def test_project_action_postcheck_requires_every_project_session(tmp_path):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "start")

    class EmptyProject(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            if tuple(argv) == ("project", "list", "--project-file", str(path.absolute())):
                return CommandResult(tuple(argv), 0, "no sessions", "", 0.01)
            return super().run(argv, timeout_seconds=timeout_seconds, readonly=readonly)

    receipt = execute_project_action(
        plan,
        EmptyProject(),
        consent=True,
        shell_consent=True,
        audit_path=tmp_path / "audit.jsonl",
    )

    assert not receipt.verified
    assert "app" in receipt.postcheck_error


@pytest.mark.parametrize("action", ["start", "list"])
def test_project_action_records_mutation_failure_but_keeps_list_read_only(tmp_path, action):
    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), action)

    class FailedAction(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            if tuple(argv) == plan.argv:
                raise OSError("native action failed")
            return super().run(argv, timeout_seconds=timeout_seconds, readonly=readonly)

    audit = tmp_path / "audit.jsonl"
    executor = FailedAction()
    kwargs = {} if action == "list" else {"consent": True, "shell_consent": True}
    with pytest.raises(OSError, match="native action failed"):
        execute_project_action(plan, executor, audit_path=audit, **kwargs)

    if action == "list":
        assert not audit.exists()
    else:
        events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
        assert [event["phase"] for event in events] == ["prepared", "failed"]


def test_project_terminate_reports_sessions_that_remain(tmp_path, monkeypatch):
    import mutaui.projects.project_actions as project_actions

    path = tmp_path / "mutagen.yml"
    path.write_text(PROJECT_TEXT, encoding="utf-8")
    plan = plan_project_action(load_native_project(path), "terminate")
    monkeypatch.setattr(
        project_actions,
        "parse_sessions",
        lambda output: [{"name": "app"}] if output == "sync" else [],
    )

    class RemainingSession(FakeExecutor):
        def run(self, argv, *, timeout_seconds, readonly=False):
            self.calls.append((tuple(argv), timeout_seconds, readonly))
            if tuple(argv[:2]) == ("sync", "list"):
                return CommandResult(tuple(argv), 0, "sync", "", 0.01)
            if tuple(argv[:2]) == ("forward", "list"):
                return CommandResult(tuple(argv), 0, "forward", "", 0.01)
            return CommandResult(tuple(argv), 0, "terminated", "", 0.01)

    receipt = execute_project_action(
        plan,
        RemainingSession(),
        consent=True,
        audit_path=tmp_path / "audit.jsonl",
    )

    assert not receipt.verified
    assert "app" in receipt.postcheck_error
