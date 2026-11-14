"""Shared exact-target risk planner; planning and consent never execute commands."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Literal

RiskTier = Literal["R0", "R1", "R2", "R3"]
PlanState = Literal["planned", "consented", "rejected", "stale", "cancelled", "finished"]


@dataclass(frozen=True, slots=True)
class ActionSpec:
    risk: RiskTier
    mutates: bool
    description: str
    backup_required: bool = False
    required_capability: str | None = None


ACTION_SPECS: dict[str, ActionSpec] = {
    "refresh_status": ActionSpec("R0", False, "Refresh native session status"),
    "inspect_conflict": ActionSpec("R0", False, "Inspect reported conflict metadata"),
    "open_local_path": ActionSpec("R0", False, "Open one contained local path"),
    "sync_pause": ActionSpec(
        "R1", True, "Pause one synchronization session", required_capability="sync_pause"
    ),
    "sync_resume": ActionSpec(
        "R1", True, "Resume one synchronization session", required_capability="sync_resume"
    ),
    "sync_flush": ActionSpec(
        "R1", True, "Request one synchronization cycle", required_capability="sync_flush"
    ),
    "forward_pause": ActionSpec(
        "R1", True, "Pause one forwarding session", required_capability="forward_pause"
    ),
    "forward_resume": ActionSpec(
        "R1", True, "Resume one forwarding session", required_capability="forward_resume"
    ),
    "sync_create": ActionSpec(
        "R2", True, "Create one synchronization session", required_capability="sync_create"
    ),
    "forward_create": ActionSpec(
        "R2", True, "Create one forwarding session", required_capability="forward_create"
    ),
    "forward_socket_overwrite": ActionSpec(
        "R3",
        True,
        "Create a forwarding session that may replace a socket path entry",
        required_capability="forward_create",
    ),
    "sync_reset": ActionSpec(
        "R2", True, "Reset one synchronization history", required_capability="sync_reset"
    ),
    "sync_reconfigure": ActionSpec(
        "R2", True, "Replace one synchronization session", required_capability="sync_reconfigure"
    ),
    "forward_reconfigure": ActionSpec(
        "R2", True, "Replace one forwarding session", required_capability="forward_reconfigure"
    ),
    "sync_terminate": ActionSpec(
        "R2", True, "Terminate one synchronization session", required_capability="sync_terminate"
    ),
    "forward_terminate": ActionSpec(
        "R2", True, "Terminate one forwarding session", required_capability="forward_terminate"
    ),
    "sync_replica": ActionSpec(
        "R3", True, "Create a potentially destructive replica session", True, "sync_replica"
    ),
    "resolve_conflict": ActionSpec("R3", True, "Resolve a file conflict", True, "resolve_conflict"),
    "delete_files": ActionSpec("R3", True, "Delete scoped files", True, "delete_files"),
    "project_hook": ActionSpec(
        "R3", True, "Run a native project hook", required_capability="project_hook"
    ),
    "daemon_stop": ActionSpec(
        "R3", True, "Stop the Mutagen daemon", required_capability="daemon_stop"
    ),
    "daemon_start": ActionSpec(
        "R1", True, "Start the Mutagen daemon", required_capability="daemon_start"
    ),
    "daemon_register": ActionSpec(
        "R2", True, "Register the Mutagen daemon at login", required_capability="daemon_register"
    ),
    "daemon_unregister": ActionSpec(
        "R2",
        True,
        "Remove Mutagen daemon login registration",
        required_capability="daemon_unregister",
    ),
    "project_pause": ActionSpec(
        "R1", True, "Pause sessions in one native project", required_capability="project_pause"
    ),
    "project_resume": ActionSpec(
        "R1", True, "Resume sessions in one native project", required_capability="project_resume"
    ),
    "project_flush": ActionSpec(
        "R1", True, "Flush sessions in one native project", required_capability="project_flush"
    ),
    "project_reset": ActionSpec(
        "R2", True, "Reset sessions in one native project", required_capability="project_reset"
    ),
    "project_start": ActionSpec(
        "R3",
        True,
        "Start sessions and hooks in one native project",
        required_capability="project_start",
    ),
    "project_terminate": ActionSpec(
        "R3",
        True,
        "Terminate sessions and run hooks in one native project",
        required_capability="project_terminate",
    ),
    "project_run": ActionSpec(
        "R3", True, "Run one native project shell command", required_capability="project_run"
    ),
}


class ActionPlanningError(ValueError):
    """Raised when a plan cannot be safely prepared or confirmed."""


@dataclass(frozen=True, slots=True)
class ActionRequest:
    action: str
    target_ids: tuple[str, ...]
    argv: tuple[str, ...]
    preflight_fingerprint: str
    affected_paths: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    preconditions_stable: bool = True
    backup_choice: str | None = None


@dataclass(frozen=True, slots=True)
class ActionPlan:
    plan_id: str
    action: str
    risk: RiskTier
    description: str
    target_ids: tuple[str, ...]
    argv: tuple[str, ...]
    affected_paths: tuple[str, ...]
    preflight_fingerprint: str
    created_at: float
    expires_at: float
    backup_required: bool
    backup_choice: str | None
    requires_typed_confirmation: bool
    typed_confirmation: str | None
    state: PlanState = "planned"


@dataclass(frozen=True, slots=True)
class ActionAuditEvent:
    plan_id: str
    action: str
    risk: RiskTier
    target_ids: tuple[str, ...]
    affected_paths: tuple[str, ...]
    decision: str
    reason: str
    at: float
    preflight_fingerprint: str


class ActionPlanner:
    """Build and consent exact-target plans under a bounded lease."""

    def __init__(
        self,
        *,
        now: Callable[[], float],
        plan_ttl_seconds: float = 120.0,
        plan_id_factory: Callable[[], str] | None = None,
        audit_limit: int = 500,
    ) -> None:
        if not math.isfinite(plan_ttl_seconds) or plan_ttl_seconds <= 0:
            raise ValueError("Plan expiry must be finite and positive")
        if audit_limit < 1:
            raise ValueError("Audit limit must be positive")
        self._now = now
        self._ttl = plan_ttl_seconds
        self._plan_id_factory = plan_id_factory or (lambda: str(uuid.uuid4()))
        self._audit_limit = audit_limit
        self._plans: dict[str, ActionPlan] = {}
        self._target_locks: dict[str, str] = {}
        self._audit: list[ActionAuditEvent] = []

    @property
    def audit(self) -> tuple[ActionAuditEvent, ...]:
        return tuple(self._audit)

    def prepare(self, request: ActionRequest) -> ActionPlan:
        now = self._checked_now()
        spec = ACTION_SPECS.get(request.action)
        if spec is None:
            raise ActionPlanningError("Unsupported action; no command was planned.")
        if not request.preflight_fingerprint.strip():
            raise ActionPlanningError("A current preflight fingerprint is required.")
        if not request.preconditions_stable:
            raise ActionPlanningError("Preconditions are not stable; refresh and review first.")
        if spec.required_capability and spec.required_capability not in request.capabilities:
            raise ActionPlanningError("Required action capability is unavailable.")
        if spec.mutates and not request.target_ids:
            raise ActionPlanningError("Mutating actions require exact session identifiers.")
        if any(not target.strip() for target in request.target_ids):
            raise ActionPlanningError("Target identifiers cannot be empty.")
        if len(set(request.target_ids)) != len(request.target_ids):
            raise ActionPlanningError("Duplicate target identifiers are not allowed.")
        if any(argument.casefold() in {"--all", "--all=true"} for argument in request.argv):
            raise ActionPlanningError("Broad --all targeting is forbidden.")
        if spec.mutates and not request.argv:
            raise ActionPlanningError("A reviewed exact command preview is required.")
        if spec.backup_required and not request.backup_choice:
            raise ActionPlanningError("Choose a backup strategy before planning this action.")

        self._expire(now)
        for target in request.target_ids:
            locked_by = self._target_locks.get(target)
            if locked_by is not None:
                raise ActionPlanningError(f"Exact target is already locked by plan {locked_by}.")

        plan_id = self._plan_id_factory()
        if not plan_id or plan_id in self._plans:
            raise ActionPlanningError("Plan identifier is invalid or already in use.")
        typed = f"APPLY {' '.join(request.target_ids)}" if spec.risk == "R3" else None
        plan = ActionPlan(
            plan_id=plan_id,
            action=request.action,
            risk=spec.risk,
            description=spec.description,
            target_ids=request.target_ids,
            argv=request.argv,
            affected_paths=request.affected_paths,
            preflight_fingerprint=request.preflight_fingerprint,
            created_at=now,
            expires_at=now + self._ttl,
            backup_required=spec.backup_required,
            backup_choice=request.backup_choice,
            requires_typed_confirmation=typed is not None,
            typed_confirmation=typed,
        )
        self._plans[plan_id] = plan
        for target in plan.target_ids:
            self._target_locks[target] = plan_id
        self._record(plan, "planned", "preview created", now)
        return plan

    def consent(
        self,
        plan_id: str,
        *,
        consent: bool,
        current_preflight_fingerprint: str,
        typed_confirmation: str | None = None,
        backup_choice: str | None = None,
    ) -> ActionPlan:
        now = self._checked_now()
        plan = self._require_plan(plan_id)
        if plan.state != "planned":
            raise ActionPlanningError("Plan is no longer awaiting consent.")
        if now >= plan.expires_at:
            return self._close(plan, "stale", "plan expired before consent", now)
        if current_preflight_fingerprint != plan.preflight_fingerprint:
            return self._close(plan, "stale", "preflight changed; create a new preview", now)
        if not consent:
            return self._close(plan, "rejected", "operator declined the preview", now)
        if plan.backup_required and backup_choice != plan.backup_choice:
            raise ActionPlanningError("A backup choice is required for this R3 action.")
        if plan.requires_typed_confirmation and typed_confirmation != plan.typed_confirmation:
            raise ActionPlanningError("Typed confirmation must match the exact target phrase.")
        consented = replace(plan, state="consented")
        self._plans[plan_id] = consented
        self._record(consented, "consented", "preview and exact target confirmed", now)
        return consented

    def cancel(self, plan_id: str) -> ActionPlan:
        now = self._checked_now()
        plan = self._require_plan(plan_id)
        if plan.state not in ("planned", "consented"):
            raise ActionPlanningError("Plan is already closed.")
        return self._close(plan, "cancelled", "plan cancelled", now)

    def finish(
        self, plan_id: str, *, verified_target_ids: Sequence[str], outcome: str
    ) -> ActionPlan:
        now = self._checked_now()
        plan = self._require_plan(plan_id)
        if plan.state != "consented":
            raise ActionPlanningError("Only a consented plan can be completed.")
        if tuple(verified_target_ids) != plan.target_ids:
            return self._close(plan, "stale", "post-check target mismatch", now)
        finished = replace(plan, state="finished")
        self._plans[plan_id] = finished
        self._record(finished, "finished", outcome, now)
        self._release(finished)
        return finished

    def _checked_now(self) -> float:
        now = self._now()
        if not math.isfinite(now):
            raise ValueError("Planner clock must be finite")
        return now

    def _require_plan(self, plan_id: str) -> ActionPlan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ActionPlanningError("Unknown action plan.")
        return plan

    def _expire(self, now: float) -> None:
        for plan in tuple(self._plans.values()):
            if plan.state in ("planned", "consented") and now >= plan.expires_at:
                self._close(plan, "stale", "plan expired", now)

    def _close(self, plan: ActionPlan, state: PlanState, reason: str, now: float) -> ActionPlan:
        closed = replace(plan, state=state)
        self._plans[plan.plan_id] = closed
        self._record(closed, state, reason, now)
        self._release(closed)
        return closed

    def _release(self, plan: ActionPlan) -> None:
        for target in plan.target_ids:
            if self._target_locks.get(target) == plan.plan_id:
                del self._target_locks[target]

    def _record(self, plan: ActionPlan, decision: str, reason: str, now: float) -> None:
        self._audit.append(
            ActionAuditEvent(
                plan.plan_id,
                plan.action,
                plan.risk,
                plan.target_ids,
                plan.affected_paths,
                decision,
                reason,
                now,
                plan.preflight_fingerprint,
            )
        )
        del self._audit[: -self._audit_limit]
