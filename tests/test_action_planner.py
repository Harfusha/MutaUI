import math
from dataclasses import replace

import pytest

from mutaui.services.action_planner import (
    ACTION_SPECS,
    ActionPlanner,
    ActionPlanningError,
    ActionRequest,
)


class FakeClock:
    value = 0.0

    def __call__(self) -> float:
        return self.value


def _request(
    action: str = "sync_pause",
    *,
    targets: tuple[str, ...] = ("sync_exact_001",),
    argv: tuple[str, ...] = ("sync", "pause", "sync_exact_001"),
    fingerprint: str = "source-hash-1",
    backup_choice: str | None = None,
) -> ActionRequest:
    return ActionRequest(
        action=action,
        target_ids=targets,
        argv=argv,
        preflight_fingerprint=fingerprint,
        affected_paths=("/workspace/project",),
        capabilities=(action,),
        backup_choice=backup_choice,
    )


def test_action_catalog_assigns_explicit_risk_tiers_and_blocks_unknown_actions():
    assert ACTION_SPECS["refresh_status"].risk == "R0"
    assert ACTION_SPECS["sync_flush"].risk == "R1"
    assert ACTION_SPECS["sync_reset"].risk == "R2"
    assert ACTION_SPECS["sync_replica"].risk == "R3"
    planner = ActionPlanner(now=FakeClock())

    with pytest.raises(ActionPlanningError, match="Unsupported action"):
        planner.prepare(_request("shell_command"))

    with pytest.raises(ActionPlanningError, match="capability is unavailable"):
        planner.prepare(replace(_request(), capabilities=()))


@pytest.mark.parametrize(
    ("action_request", "message"),
    [
        (_request(targets=()), "exact session identifiers"),
        (_request(argv=("sync", "pause", "--all")), "--all"),
        (_request(fingerprint="  "), "fingerprint"),
        (replace(_request(), preconditions_stable=False), "Preconditions"),
    ],
)
def test_preflight_rejects_ambiguous_or_unstable_mutations(action_request, message):
    planner = ActionPlanner(now=FakeClock())

    with pytest.raises(ActionPlanningError, match=message):
        planner.prepare(action_request)


def test_exact_target_lock_blocks_overlap_until_plan_is_closed():
    clock = FakeClock()
    planner = ActionPlanner(now=clock)
    first = planner.prepare(_request())

    with pytest.raises(ActionPlanningError, match="already locked"):
        planner.prepare(_request(action="sync_resume", argv=("sync", "resume", "sync_exact_001")))

    planner.cancel(first.plan_id)
    next_plan = planner.prepare(
        _request(action="sync_resume", argv=("sync", "resume", "sync_exact_001"))
    )
    assert next_plan.target_ids == ("sync_exact_001",)


def test_preflight_fingerprint_change_expires_plan_without_consent():
    clock = FakeClock()
    planner = ActionPlanner(now=clock)
    plan = planner.prepare(_request())

    stale = planner.consent(
        plan.plan_id,
        consent=True,
        current_preflight_fingerprint="new-source-hash",
    )

    assert stale.state == "stale"
    assert planner.audit[-1].reason == "preflight changed; create a new preview"


def test_r3_requires_matching_backup_and_typed_exact_target_confirmation():
    planner = ActionPlanner(now=FakeClock())
    plan = planner.prepare(
        _request(
            "sync_replica",
            argv=("sync", "create", "--sync-mode=one-way-replica"),
            backup_choice="backup",
        )
    )
    assert plan.risk == "R3"
    assert plan.typed_confirmation == "APPLY sync_exact_001"

    with pytest.raises(ActionPlanningError, match="backup choice"):
        planner.consent(
            plan.plan_id,
            consent=True,
            current_preflight_fingerprint="source-hash-1",
            typed_confirmation=plan.typed_confirmation,
            backup_choice="skip",
        )
    with pytest.raises(ActionPlanningError, match="Typed confirmation"):
        planner.consent(
            plan.plan_id,
            consent=True,
            current_preflight_fingerprint="source-hash-1",
            typed_confirmation="APPLY other-session",
            backup_choice="backup",
        )
    accepted = planner.consent(
        plan.plan_id,
        consent=True,
        current_preflight_fingerprint="source-hash-1",
        typed_confirmation=plan.typed_confirmation,
        backup_choice="backup",
    )
    assert accepted.state == "consented"


def test_r2_consent_records_plan_and_postcheck_must_match_exact_targets():
    planner = ActionPlanner(now=FakeClock())
    plan = planner.prepare(_request("sync_reset", argv=("sync", "reset", "sync_exact_001")))
    assert plan.risk == "R2"

    accepted = planner.consent(
        plan.plan_id, consent=True, current_preflight_fingerprint="source-hash-1"
    )
    assert accepted.state == "consented"
    stale = planner.finish(
        plan.plan_id, verified_target_ids=("sync_other_002",), outcome="unexpected target"
    )
    assert stale.state == "stale"
    assert planner.audit[-1].reason == "post-check target mismatch"


def test_expired_plan_releases_lock_and_audit_is_bounded():
    clock = FakeClock()
    planner = ActionPlanner(now=clock, plan_ttl_seconds=10, audit_limit=2)
    plan = planner.prepare(_request())
    clock.value = 11
    fresh = planner.prepare(_request())

    assert fresh.plan_id != plan.plan_id
    assert [event.decision for event in planner.audit] == ["stale", "planned"]


@pytest.mark.parametrize("ttl", [0, -1, math.inf, math.nan])
def test_planner_rejects_invalid_expiry(ttl):
    with pytest.raises(ValueError, match="finite and positive"):
        ActionPlanner(now=FakeClock(), plan_ttl_seconds=ttl)


def test_planner_rejects_nonpositive_audit_limit_and_nonfinite_clock():
    with pytest.raises(ValueError, match="Audit limit must be positive"):
        ActionPlanner(now=FakeClock(), audit_limit=0)

    clock = FakeClock()
    clock.value = math.inf
    with pytest.raises(ValueError, match="Planner clock must be finite"):
        ActionPlanner(now=clock).prepare(_request())


def test_prepare_rejects_empty_duplicate_targets_and_missing_command_or_backup():
    planner = ActionPlanner(now=FakeClock())
    invalid_requests = [
        replace(_request(), target_ids=(" ",)),
        replace(_request(), target_ids=("same", "same")),
        replace(_request(), argv=("sync", "pause", "--all=true")),
        replace(_request(), argv=()),
        _request("sync_replica", backup_choice=None),
    ]
    messages = [
        "cannot be empty",
        "Duplicate target",
        "--all",
        "command preview",
        "backup strategy",
    ]

    for action_request, message in zip(invalid_requests, messages, strict=True):
        with pytest.raises(ActionPlanningError, match=message):
            planner.prepare(action_request)


def test_plan_factory_rejects_empty_and_reused_identifiers():
    empty = ActionPlanner(now=FakeClock(), plan_id_factory=lambda: "")
    with pytest.raises(ActionPlanningError, match="identifier is invalid"):
        empty.prepare(_request())

    identifiers = iter(("reused-id", "reused-id"))
    reused = ActionPlanner(now=FakeClock(), plan_id_factory=lambda: next(identifiers))
    reused.prepare(_request())
    with pytest.raises(ActionPlanningError, match="identifier is invalid"):
        reused.prepare(
            _request(targets=("sync_exact_002",), argv=("sync", "pause", "sync_exact_002"))
        )


def test_consent_expiry_and_decline_close_plan_and_release_target():
    clock = FakeClock()
    planner = ActionPlanner(now=clock, plan_ttl_seconds=5)
    expiring = planner.prepare(_request())
    clock.value = expiring.expires_at
    stale = planner.consent(
        expiring.plan_id,
        consent=True,
        current_preflight_fingerprint="source-hash-1",
    )
    assert stale.state == "stale"

    declined = planner.prepare(_request())
    rejected = planner.consent(
        declined.plan_id,
        consent=False,
        current_preflight_fingerprint="source-hash-1",
    )
    assert rejected.state == "rejected"
    assert [event.decision for event in planner.audit[-2:]] == ["planned", "rejected"]


def test_plan_transitions_reject_wrong_state_and_unknown_plan():
    planner = ActionPlanner(now=FakeClock())
    with pytest.raises(ActionPlanningError, match="Unknown action plan"):
        planner.cancel("missing-plan")

    plan = planner.prepare(_request())
    with pytest.raises(ActionPlanningError, match="Only a consented plan"):
        planner.finish(plan.plan_id, verified_target_ids=plan.target_ids, outcome="not yet")

    consented = planner.consent(
        plan.plan_id,
        consent=True,
        current_preflight_fingerprint="source-hash-1",
    )
    with pytest.raises(ActionPlanningError, match="no longer awaiting consent"):
        planner.consent(
            consented.plan_id,
            consent=True,
            current_preflight_fingerprint="source-hash-1",
        )

    cancelled = planner.cancel(consented.plan_id)
    assert cancelled.state == "cancelled"
    with pytest.raises(ActionPlanningError, match="already closed"):
        planner.cancel(cancelled.plan_id)


def test_successful_finish_releases_exact_target_lock():
    planner = ActionPlanner(now=FakeClock())
    plan = planner.prepare(_request())
    planner.consent(
        plan.plan_id,
        consent=True,
        current_preflight_fingerprint="source-hash-1",
    )
    finished = planner.finish(
        plan.plan_id,
        verified_target_ids=plan.target_ids,
        outcome="verified",
    )
    assert finished.state == "finished"
    next_plan = planner.prepare(
        _request(action="sync_resume", argv=("sync", "resume", "sync_exact_001"))
    )
    assert next_plan.target_ids == plan.target_ids


def test_close_does_not_release_target_lock_owned_by_another_plan():
    planner = ActionPlanner(now=FakeClock())
    plan = planner.prepare(_request())
    planner._target_locks[plan.target_ids[0]] = "different-plan"

    planner.cancel(plan.plan_id)

    assert planner._target_locks[plan.target_ids[0]] == "different-plan"
