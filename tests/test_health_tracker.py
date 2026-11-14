from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from mutaui.services.action_planner import ACTION_SPECS
from mutaui.services.health_tracker import (
    HealthObservation,
    HealthPolicy,
    HealthTracker,
)

BASE = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


def _observation(
    key: str,
    *,
    failed: bool = False,
    state: str = "watching",
    paused: bool = False,
    scanning: bool = False,
    duration: float | None = 0.2,
) -> HealthObservation:
    return HealthObservation(
        session_identifier="session-exact-id",
        observation_key=key,
        observed_at=BASE + timedelta(seconds=int(key)),
        state=state,
        confirmed_failure=failed,
        intentional_pause=paused,
        scan_in_progress=scanning,
        command_duration_seconds=duration,
    )


def test_monitor_only_is_default_and_never_recommends_recovery():
    tracker = HealthTracker()

    result = tracker.observe(_observation("0", failed=True), now=0.0)

    assert tracker.policy.mode == "monitor_only"
    assert not result.recommend_manual_action
    assert not result.automated_action


def test_assisted_waits_for_three_confirmed_failures_and_elapsed_threshold():
    tracker = HealthTracker(HealthPolicy(mode="assisted", failure_elapsed_seconds=120))

    tracker.observe(_observation("0", failed=True), now=0.0)
    tracker.observe(_observation("60", failed=True), now=60.0)
    early = tracker.observe(_observation("121", failed=True), now=121.0)

    assert early.error_streak == 3
    assert early.recommend_manual_action
    assert early.incident_id
    assert not early.automated_action


def test_long_scan_suppresses_errors_and_does_not_accumulate_a_failure_streak():
    tracker = HealthTracker(HealthPolicy(mode="assisted"))

    tracker.observe(_observation("0", failed=True), now=0.0)
    result = tracker.observe(
        _observation("1800", failed=True, state="scanning", scanning=True), now=1800.0
    )

    assert result.error_streak == 0
    assert not result.recommend_manual_action


def test_ssh_flapping_resets_consecutive_failures_and_tracks_reconnects():
    tracker = HealthTracker(HealthPolicy(mode="assisted", failure_elapsed_seconds=0))

    tracker.observe(_observation("0", failed=True, state="disconnected"), now=0.0)
    recovered = tracker.observe(_observation("10", state="watching"), now=10.0)
    failed_again = tracker.observe(_observation("20", failed=True, state="disconnected"), now=20.0)

    assert recovered.error_streak == 0
    assert recovered.reconnect_count == 1
    assert failed_again.error_streak == 1
    assert not failed_again.recommend_manual_action


@pytest.mark.parametrize("event", ["sleep", "wake", "network_change"])
def test_environment_change_grace_suppresses_transient_failures(event: str):
    tracker = HealthTracker(HealthPolicy(mode="assisted", environment_grace_seconds=120))
    tracker.note_environment_event(event, now=100.0)

    result = tracker.observe(_observation("110", failed=True), now=110.0)

    assert result.error_streak == 0
    assert result.environment_event == event
    assert not result.recommend_manual_action


def test_external_manual_pause_clears_streak_and_is_never_resumed():
    tracker = HealthTracker(HealthPolicy(mode="assisted", failure_elapsed_seconds=0))
    tracker.observe(_observation("0", failed=True), now=0.0)

    paused = tracker.observe(_observation("10", failed=True, state="paused", paused=True), now=10.0)

    assert paused.error_streak == 0
    assert paused.intentional_pause
    assert not paused.recommend_manual_action
    assert not paused.automated_action


def test_duplicate_snapshot_is_idempotent_and_command_durations_are_measured():
    tracker = HealthTracker()
    observation = _observation("0", failed=True, duration=1.25)

    first = tracker.observe(observation, now=0.0)
    duplicate = tracker.observe(observation, now=10.0)

    assert first.error_streak == duplicate.error_streak == 1
    assert duplicate.last_command_duration_seconds == 1.25


def test_recovery_gate_uses_exact_scope_cooldown_attempt_limit_and_circuit_breaker():
    tracker = HealthTracker(
        HealthPolicy(
            mode="auto_safe",
            failure_elapsed_seconds=0,
            cooldown_seconds=60,
            max_attempts=2,
        )
    )
    for second in (0, 10, 20):
        tracker.observe(_observation(str(second), failed=True), now=float(second))

    assert not tracker.recovery_gate(
        "", action="refresh_status", now=30, preconditions_stable=True
    ).allowed
    assert not tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=30, preconditions_stable=False
    ).allowed
    assert not tracker.recovery_gate(
        "session-exact-id", action="sync_flush", now=30, preconditions_stable=True
    ).allowed
    assert tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=30, preconditions_stable=True
    ).allowed

    tracker.record_recovery_attempt(
        "session-exact-id", action="refresh_status", now=30, succeeded=False
    )
    assert not tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=89, preconditions_stable=True
    ).allowed
    tracker.record_recovery_attempt(
        "session-exact-id", action="refresh_status", now=90, succeeded=True
    )
    assert not tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=200, preconditions_stable=True
    ).allowed
    audit = tracker.recovery_audit("session-exact-id")
    assert audit[-1].action == "refresh_status"
    assert audit[-1].reason == "circuit breaker: attempt limit reached"


def test_recovery_gate_blocks_two_recent_failed_attempts_before_limit():
    tracker = HealthTracker(
        HealthPolicy(
            mode="auto_safe",
            failure_elapsed_seconds=0,
            cooldown_seconds=60,
            max_attempts=2,
            attempt_window_seconds=1800,
        )
    )
    for second in (0, 10, 20):
        tracker.observe(_observation(str(second), failed=True), now=float(second))
    for second in (20, 81):
        tracker.record_recovery_attempt(
            "session-exact-id", action="refresh_status", now=float(second), succeeded=False
        )

    decision = tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=142, preconditions_stable=True
    )

    assert not decision.allowed
    assert decision.reason == "circuit breaker: repeated recovery failures"
    assert decision.incident_id


@pytest.mark.parametrize(
    "action",
    ["pause", "resume", "flush", "reset", "terminate", "daemon_stop", "arbitrary"],
)
def test_auto_safe_rejects_every_mutating_or_unknown_action(action: str):
    tracker = HealthTracker(HealthPolicy(mode="auto_safe", failure_elapsed_seconds=0))
    for second in (0, 10, 20):
        tracker.observe(_observation(str(second), failed=True), now=float(second))

    decision = tracker.recovery_gate(
        "session-exact-id", action=action, now=30, preconditions_stable=True
    )

    assert not decision.allowed
    assert decision.reason == "action is not in the auto-safe allowlist"


def test_auto_safe_rejects_every_catalogued_r2_and_r3_action():
    tracker = HealthTracker(HealthPolicy(mode="auto_safe", failure_elapsed_seconds=0))
    for second in (0, 10, 20):
        tracker.observe(_observation(str(second), failed=True), now=float(second))

    for action, spec in ACTION_SPECS.items():
        if spec.risk not in {"R2", "R3"}:
            continue
        decision = tracker.recovery_gate(
            "session-exact-id", action=action, now=30, preconditions_stable=True
        )

        assert not decision.allowed, action
        assert decision.action == action
        assert decision.reason == "action is not in the auto-safe allowlist"
    assert tracker.recovery_audit("session-exact-id")[-1].session_identifier == "session-exact-id"


@pytest.mark.parametrize(
    "values",
    [
        {"mode": "unknown"},
        {"failure_count_threshold": 2},
        {"failure_elapsed_seconds": -1},
        {"cooldown_seconds": 59},
        {"max_attempts": 0},
        {"max_attempts": 3},
        {"attempt_window_seconds": 1799},
        {"environment_grace_seconds": -1},
    ],
)
def test_health_policy_rejects_unsafe_thresholds(values):
    with pytest.raises(ValueError):
        HealthPolicy(**values)


@pytest.mark.parametrize("now", [float("nan"), float("inf"), float("-inf")])
def test_health_tracker_rejects_non_finite_monotonic_time(now):
    tracker = HealthTracker()
    with pytest.raises(ValueError, match="finite"):
        tracker.observe(_observation("0"), now=now)


def test_health_tracker_rejects_invalid_observation_identity_duration_and_event():
    tracker = HealthTracker()
    original = _observation("0")
    for observation in (
        replace(original, session_identifier=""),
        replace(original, observation_key=""),
        replace(original, command_duration_seconds=float("nan")),
        replace(original, command_duration_seconds=-0.1),
    ):
        with pytest.raises(ValueError):
            tracker.observe(observation, now=0.0)
    with pytest.raises(ValueError, match="Unsupported environment event"):
        tracker.note_environment_event("unknown", now=0.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        tracker.note_environment_event("sleep", now=float("nan"))


def test_health_environment_event_clears_existing_incident_and_empty_audit_is_empty():
    tracker = HealthTracker(HealthPolicy(mode="assisted", failure_elapsed_seconds=0))
    tracker.observe(_observation("0", failed=True), now=0.0)
    tracker.note_environment_event("wake", now=1.0)
    result = tracker.observe(_observation("2", failed=True), now=2.0)

    assert result.error_streak == 0
    assert result.incident_id is None
    assert tracker.recovery_audit("missing") == ()


def test_healthy_first_observation_and_disabled_recovery_mode_are_recorded():
    tracker = HealthTracker()
    healthy = tracker.observe(_observation("0", state="watching"), now=0.0)
    assert healthy.error_streak == 0
    assert healthy.last_success_at == 0.0

    tracker.observe(_observation("10", failed=True), now=10.0)
    gate = tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=11, preconditions_stable=True
    )
    assert gate.reason == "automatic recovery mode is disabled"


def test_recovery_gate_requires_failure_duration_before_allowing_attempt():
    tracker = HealthTracker(HealthPolicy(mode="auto_safe", failure_elapsed_seconds=120))
    for second in (0, 10, 20):
        tracker.observe(_observation(str(second), failed=True), now=float(second))

    gate = tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=30, preconditions_stable=True
    )
    assert gate.reason == "failure duration threshold is not met"


def test_recovery_gate_records_denials_for_pause_grace_and_missing_failure_threshold():
    tracker = HealthTracker(HealthPolicy(mode="auto_safe", failure_elapsed_seconds=0))
    empty = tracker.recovery_gate(
        "missing", action="refresh_status", now=0, preconditions_stable=True
    )
    assert empty.reason == "exact session target is required"

    tracker.observe(_observation("0", failed=True), now=0.0)
    below_threshold = tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=1, preconditions_stable=True
    )
    assert below_threshold.reason == "confirmed failure threshold is not met"

    tracker.observe(_observation("2", failed=True, paused=True, state="paused"), now=2.0)
    paused = tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=3, preconditions_stable=True
    )
    assert paused.reason == "session is intentionally paused"

    tracker.note_environment_event("sleep", now=4)
    tracker.observe(_observation("5", state="watching"), now=5.0)
    grace = tracker.recovery_gate(
        "session-exact-id", action="refresh_status", now=6, preconditions_stable=True
    )
    assert grace.reason == "sleep/wake/network recovery grace is active"

    with pytest.raises(ValueError, match="grace is active"):
        tracker.record_recovery_attempt(
            "session-exact-id", action="refresh_status", now=7, succeeded=True
        )
