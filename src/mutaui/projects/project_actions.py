"""Previewed native Mutagen project commands with hook-consent gates."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from mutagen_client import parse_sessions
from mutaui.adapters.cli_executor import CommandExecutor, CommandResult
from mutaui.services.action_planner import ActionPlan, ActionPlanner, ActionRequest

from .native_project import NativeProjectSnapshot, load_native_project

PROJECT_ACTION_HOOKS = {
    "start": ("beforeCreate", "afterCreate"),
    "terminate": ("beforeTerminate", "afterTerminate"),
    "pause": ("beforePause", "afterPause"),
    "resume": ("beforeResume", "afterResume"),
}
PROJECT_ACTIONS = ("list", "start", "pause", "resume", "flush", "reset", "terminate", "run")


class ProjectActionError(ValueError):
    """Raised when a native project action lacks a safe, current precondition."""


@dataclass(frozen=True, slots=True)
class ProjectActionPlan:
    action: str
    path: Path
    project_sha256: str
    argv: tuple[str, ...]
    session_names: tuple[str, ...]
    hooks: tuple[tuple[str, tuple[str, ...]], ...]
    command_name: str | None = None
    command_text: str | None = None

    @property
    def read_only(self) -> bool:
        return self.action == "list"

    @property
    def shell_consent_required(self) -> bool:
        return bool(self.hooks) or self.action == "run"


@dataclass(frozen=True, slots=True)
class ProjectActionReceipt:
    plan: ProjectActionPlan
    action_result: CommandResult
    postcheck_result: CommandResult | None
    postcheck_error: str = ""

    @property
    def verified(self) -> bool:
        return self.plan.read_only or (
            self.postcheck_result is not None and not self.postcheck_error
        )


def plan_project_action(
    snapshot: NativeProjectSnapshot,
    action: str,
    command_name: str | None = None,
) -> ProjectActionPlan:
    if not snapshot.valid:
        raise ProjectActionError("Invalid native project cannot be operated.")
    if action not in PROJECT_ACTIONS:
        raise ProjectActionError("Unsupported native project action.")
    if action != "list" and (snapshot.unknown_root_keys or snapshot.warnings):
        details = (*snapshot.unknown_root_keys, *snapshot.warnings)
        raise ProjectActionError(
            "Project contains unrecognized or invalid configuration; operation is blocked: "
            + "; ".join(details)
        )
    path = snapshot.path.expanduser().absolute()
    if not path.is_file():
        raise ProjectActionError("Native project file is missing; reload before operating.")

    command_text = None
    if action == "run":
        if not command_name:
            raise ProjectActionError("Select a named project command.")
        command_text = next(
            (value for name, value in snapshot.commands if name == command_name), None
        )
        if command_text is None:
            raise ProjectActionError("Selected project command is not declared in this file.")

    hooks_by_name = dict(snapshot.hooks)
    hook_names = PROJECT_ACTION_HOOKS.get(action, ())
    hooks = tuple((name, hooks_by_name[name]) for name in hook_names if name in hooks_by_name)
    arguments = ["project", action]
    if command_name is not None and action == "run":
        arguments.append(command_name)
    arguments.extend(("--project-file", str(path)))
    return ProjectActionPlan(
        action,
        path,
        snapshot.sha256,
        tuple(arguments),
        tuple(item.name for item in snapshot.sessions),
        hooks,
        command_name,
        command_text,
    )


def prepare_action_plan(plan: ProjectActionPlan, action_planner: ActionPlanner) -> ActionPlan:
    action_key = f"project_{plan.action}"
    return action_planner.prepare(
        ActionRequest(
            action=action_key,
            target_ids=(project_target_id(plan.path),),
            argv=plan.argv,
            preflight_fingerprint=plan.project_sha256,
            affected_paths=(str(plan.path),),
            capabilities=(action_key,),
        )
    )


def project_target_id(path: str | Path) -> str:
    target = os.path.normcase(os.path.realpath(path))
    digest = hashlib.sha256(target.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"project:{digest}"


def execute_project_action(
    plan: ProjectActionPlan,
    executor: CommandExecutor,
    *,
    consent: bool = False,
    shell_consent: bool = False,
    audit_path: str | Path | None = None,
    action_planner: ActionPlanner | None = None,
    action_plan: ActionPlan | None = None,
) -> ProjectActionReceipt:
    if not plan.read_only and not consent:
        raise ProjectActionError("Explicit consent is required for this project action.")
    if plan.shell_consent_required and not shell_consent:
        raise ProjectActionError(
            "Explicit consent is required for project hooks or shell commands."
        )
    if not plan.read_only and action_planner is not None:
        expected_action = f"project_{plan.action}"
        if (
            action_plan is None
            or action_plan.state != "consented"
            or action_plan.action != expected_action
            or action_plan.target_ids != (project_target_id(plan.path),)
            or action_plan.argv != plan.argv
            or action_plan.preflight_fingerprint != plan.project_sha256
        ):
            raise ProjectActionError("A consented matching ActionPlanner plan is required.")

    def close_planner(outcome: str, *, verified: bool = False) -> None:
        if action_planner is None or action_plan is None or plan.read_only:
            return
        action_planner.finish(
            action_plan.plan_id,
            verified_target_ids=action_plan.target_ids if verified else (),
            outcome=outcome,
        )

    audit_target = Path(audit_path) if audit_path is not None else None
    if not plan.read_only and audit_target is None:
        close_planner("local audit path is unavailable")
        raise ProjectActionError("A local audit path is required before a project mutation.")
    current = load_native_project(plan.path)
    if not current.valid or current.sha256 != plan.project_sha256:
        close_planner("project file changed before execution")
        raise ProjectActionError(
            "Native project changed after preview; reload and review it again."
        )

    try:
        executor.run(("project", plan.action, "--help"), timeout_seconds=15, readonly=True)
        current = load_native_project(plan.path)
    except Exception as exc:
        close_planner("native project preflight failed")
        raise ProjectActionError(f"Native project preflight failed: {exc}") from exc
    if not current.valid or current.sha256 != plan.project_sha256:
        close_planner("project file changed during preflight")
        raise ProjectActionError("Native project changed during preflight; no action was run.")

    event_id = uuid4().hex
    if not plan.read_only:
        assert audit_target is not None
        try:
            _append_audit(
                audit_target,
                {
                    "event_id": event_id,
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "phase": "prepared",
                    "action": plan.action,
                    "project_path": str(plan.path),
                    "project_sha256": plan.project_sha256,
                    "command_name": plan.command_name,
                    "hook_names": [name for name, _ in plan.hooks],
                    "consent": consent,
                    "shell_consent": shell_consent,
                },
            )
        except OSError as exc:
            close_planner("project audit could not be recorded before execution")
            raise ProjectActionError(f"Project audit could not be recorded: {exc}") from exc
    try:
        action_result = executor.run(plan.argv, timeout_seconds=120, readonly=plan.read_only)
    except Exception as exc:
        close_planner("native project action failed; refresh before retrying")
        if not plan.read_only:
            assert audit_target is not None
            _append_audit(
                audit_target,
                {
                    "event_id": event_id,
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                    "phase": "failed",
                    "error": str(exc),
                },
            )
        raise
    if plan.read_only:
        return ProjectActionReceipt(plan, action_result, None)
    postcheck: CommandResult | None = None
    postcheck_error = ""
    try:
        if plan.action == "terminate":
            remaining_sessions: list[str] = []
            for kind in ("sync", "forward"):
                postcheck = executor.run(
                    (kind, "list", "--template", "{{ json . }}"),
                    timeout_seconds=30,
                    readonly=True,
                )
                sessions = parse_sessions(postcheck.stdout)
                remaining_sessions.extend(
                    name
                    for name in plan.session_names
                    if any(session.get("name") == name for session in sessions)
                )
            if remaining_sessions:
                postcheck_error = (
                    "Terminated project sessions remain in native status: "
                    + ", ".join(dict.fromkeys(remaining_sessions))
                )
        else:
            postcheck = executor.run(
                ("project", "list", "--project-file", str(plan.path)),
                timeout_seconds=30,
                readonly=True,
            )
    except Exception as exc:  # The action ran; preserve that fact when verification fails.
        postcheck_error = str(exc)
    if postcheck is not None and plan.action != "terminate":
        missing_sessions = [name for name in plan.session_names if name not in postcheck.stdout]
        if missing_sessions:
            postcheck_error = (
                "Project status output did not include expected sessions: "
                + ", ".join(missing_sessions)
            )
    try:
        assert audit_target is not None
        _append_audit(
            audit_target,
            {
                "event_id": event_id,
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "phase": "completed",
                "postcheck_verified": postcheck is not None and not postcheck_error,
                "postcheck_error": postcheck_error,
            },
        )
    except OSError as exc:
        postcheck_error = "; ".join(
            filter(None, (postcheck_error, f"audit completion write failed: {exc}"))
        )
    close_planner(
        "native project post-check passed"
        if not postcheck_error
        else "native project outcome is uncertain",
        verified=not postcheck_error and postcheck is not None,
    )
    return ProjectActionReceipt(plan, action_result, postcheck, postcheck_error)


def _append_audit(path: Path, event: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
