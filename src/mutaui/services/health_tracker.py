"""Monotonic, in-memory session health tracking and recovery gating."""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

HealthMode = Literal["monitor_only", "assisted", "auto_safe"]
EnvironmentEvent = Literal["sleep", "wake", "network_change"]
SafeRecoveryAction = Literal["refresh_status"]
SAFE_RECOVERY_ACTIONS: frozenset[str] = frozenset({"refresh_status"})


@dataclass(frozen=True, slots=True)
class HealthPolicy:
    mode: HealthMode = "monitor_only"
    failure_count_threshold: int = 3
    failure_elapsed_seconds: int = 120
    cooldown_seconds: int = 60
    max_attempts: int = 2
    attempt_window_seconds: int = 1800
    environment_grace_seconds: int = 120

    def __post_init__(self) -> None:
        if self.mode not in ("monitor_only", "assisted", "auto_safe"):
            raise ValueError("Unsupported health mode")
        if self.failure_count_threshold < 3:
            raise ValueError("At least three confirmed failures are required")
        if self.failure_elapsed_seconds < 0:
            raise ValueError("Failure duration cannot be negative")
        if self.cooldown_seconds < 60:
            raise ValueError("Recovery cooldown must be at least 60 seconds")
        if not 1 <= self.max_attempts <= 2:
            raise ValueError("At most two recovery attempts are allowed")
        if self.attempt_window_seconds < 1800:
            raise ValueError("Recovery attempt window must be at least 30 minutes")
        if self.environment_grace_seconds < 0:
            raise ValueError("Environment grace cannot be negative")


@dataclass(frozen=True, slots=True)
class HealthObservation:
    session_identifier: str
    observation_key: str
    observed_at: datetime
    state: str
    confirmed_failure: bool
    intentional_pause: bool = False
    scan_in_progress: bool = False
    command_duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class HealthTransition:
    from_state: str | None
    to_state: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class SessionHealth:
    session_identifier: str
    state: str
    transitions: tuple[HealthTransition, ...]
    error_streak: int
    error_elapsed_seconds: float
    reconnect_count: int
    last_success_at: float | None
    last_command_duration_seconds: float | None
    incident_id: str | None
    intentional_pause: bool
    environment_event: EnvironmentEvent | None
    recommend_manual_action: bool
    automated_action: bool = False


@dataclass(frozen=True, slots=True)
class RecoveryGate:
    allowed: bool
    reason: str
    session_identifier: str
    action: str
    attempts_in_window: int
    incident_id: str | None


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    session_identifier: str
    action: str
    allowed: bool
    reason: str
    decided_at: float
    incident_id: str | None
    attempts_in_window: int


@dataclass(slots=True)
class _SessionState:
    last_observation_key: str | None = None
    state: str = "unknown"
    transitions: list[HealthTransition] = field(default_factory=list)
    error_streak: int = 0
    failure_started_at: float | None = None
    reconnect_count: int = 0
    last_success_at: float | None = None
    last_command_duration_seconds: float | None = None
    incident_id: str | None = None
    intentional_pause: bool = False
    attempts: list[tuple[float, bool]] = field(default_factory=list)
    recovery_audit: list[RecoveryDecision] = field(default_factory=list)


class HealthTracker:
    """Tracks typed observations; all elapsed-time decisions use injected monotonic seconds."""

    def __init__(
        self,
        policy: HealthPolicy | None = None,
        *,
        incident_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.policy = policy or HealthPolicy()
        self._states: dict[str, _SessionState] = {}
        self._incident_id_factory = incident_id_factory or (lambda: str(uuid.uuid4()))
        self._environment_event: EnvironmentEvent | None = None
        self._environment_until = 0.0

    def update_policy(self, policy: HealthPolicy) -> None:
        self.policy = policy

    @staticmethod
    def _check_now(now: float) -> None:
        if not math.isfinite(now):
            raise ValueError("Monotonic time must be finite")

    def note_environment_event(self, event: EnvironmentEvent, *, now: float) -> None:
        self._check_now(now)
        if event not in ("sleep", "wake", "network_change"):
            raise ValueError("Unsupported environment event")
        self._environment_event = event
        self._environment_until = max(
            self._environment_until, now + self.policy.environment_grace_seconds
        )
        for state in self._states.values():
            state.error_streak = 0
            state.failure_started_at = None
            state.incident_id = None

    def observe(self, observation: HealthObservation, *, now: float) -> SessionHealth:
        self._check_now(now)
        if not observation.session_identifier or not observation.observation_key:
            raise ValueError("Session identifier and observation key are required")
        if observation.command_duration_seconds is not None and (
            not math.isfinite(observation.command_duration_seconds)
            or observation.command_duration_seconds < 0
        ):
            raise ValueError("Command duration must be finite and non-negative")

        state = self._states.setdefault(observation.session_identifier, _SessionState())
        if observation.observation_key == state.last_observation_key:
            return self._snapshot(observation.session_identifier, state, now)

        previous_state = state.state
        previous_failure_streak = state.error_streak
        state.last_observation_key = observation.observation_key
        if observation.state != previous_state:
            state.transitions.append(
                HealthTransition(
                    previous_state if previous_state != "unknown" else None,
                    observation.state,
                    observation.observed_at,
                )
            )
            del state.transitions[:-100]
        state.state = observation.state
        state.last_command_duration_seconds = observation.command_duration_seconds
        state.intentional_pause = observation.intentional_pause

        if observation.intentional_pause:
            self._clear_incident(state)
            return self._snapshot(observation.session_identifier, state, now)
        if observation.scan_in_progress:
            self._clear_incident(state)
            return self._snapshot(observation.session_identifier, state, now)
        if now < self._environment_until:
            self._clear_incident(state)
            return self._snapshot(observation.session_identifier, state, now)

        if observation.confirmed_failure:
            if state.error_streak == 0:
                state.failure_started_at = now
                state.incident_id = self._incident_id_factory()
            state.error_streak += 1
        else:
            if previous_failure_streak:
                state.reconnect_count += 1
            state.last_success_at = now
            self._clear_incident(state)

        return self._snapshot(observation.session_identifier, state, now)

    def recovery_gate(
        self,
        session_identifier: str,
        *,
        action: str,
        now: float,
        preconditions_stable: bool,
    ) -> RecoveryGate:
        self._check_now(now)
        state = self._states.get(session_identifier)
        attempts = (
            [at for at, _ in state.attempts if now - at < self.policy.attempt_window_seconds]
            if state is not None
            else []
        )
        reason = "eligible"
        allowed = True
        if action not in SAFE_RECOVERY_ACTIONS:
            allowed, reason = False, "action is not in the auto-safe allowlist"
        elif not session_identifier or state is None:
            allowed, reason = False, "exact session target is required"
        elif self.policy.mode != "auto_safe":
            allowed, reason = False, "automatic recovery mode is disabled"
        elif state.intentional_pause:
            allowed, reason = False, "session is intentionally paused"
        elif now < self._environment_until:
            allowed, reason = False, "sleep/wake/network recovery grace is active"
        elif not preconditions_stable:
            allowed, reason = False, "recovery preconditions are not stable"
        elif state.error_streak < self.policy.failure_count_threshold:
            allowed, reason = False, "confirmed failure threshold is not met"
        elif (
            state.failure_started_at is None
            or now - state.failure_started_at < self.policy.failure_elapsed_seconds
        ):
            allowed, reason = False, "failure duration threshold is not met"
        elif attempts and now - max(attempts) < self.policy.cooldown_seconds:
            allowed, reason = False, "recovery cooldown is active"
        elif (
            state.attempts
            and all(
                not succeeded
                for at, succeeded in state.attempts
                if now - at < self.policy.attempt_window_seconds
            )
            and len(attempts) >= 2
        ):
            allowed, reason = False, "circuit breaker: repeated recovery failures"
        elif len(attempts) >= self.policy.max_attempts:
            allowed, reason = False, "circuit breaker: attempt limit reached"
        decision = RecoveryDecision(
            session_identifier=session_identifier,
            action=action,
            allowed=allowed,
            reason=reason,
            decided_at=now,
            incident_id=state.incident_id if state is not None else None,
            attempts_in_window=len(attempts),
        )
        if state is not None:
            state.recovery_audit.append(decision)
            del state.recovery_audit[:-100]
        return RecoveryGate(
            allowed,
            reason,
            session_identifier,
            action,
            len(attempts),
            state.incident_id if state is not None else None,
        )

    def record_recovery_attempt(
        self,
        session_identifier: str,
        *,
        action: SafeRecoveryAction,
        now: float,
        succeeded: bool,
    ) -> RecoveryGate:
        gate = self.recovery_gate(
            session_identifier,
            action=action,
            now=now,
            preconditions_stable=True,
        )
        if not gate.allowed:
            raise ValueError(gate.reason)
        state = self._states[session_identifier]
        state.attempts.append((now, succeeded))
        return self.recovery_gate(
            session_identifier,
            action=action,
            now=now,
            preconditions_stable=True,
        )

    def recovery_audit(self, session_identifier: str) -> tuple[RecoveryDecision, ...]:
        """Return the bounded in-memory decisions for one exact session."""
        state = self._states.get(session_identifier)
        if state is None:
            return ()
        return tuple(state.recovery_audit)

    def _clear_incident(self, state: _SessionState) -> None:
        state.error_streak = 0
        state.failure_started_at = None
        state.incident_id = None

    def _snapshot(self, identifier: str, state: _SessionState, now: float) -> SessionHealth:
        elapsed = (
            max(0.0, now - state.failure_started_at)
            if state.failure_started_at is not None
            else 0.0
        )
        threshold_met = (
            state.error_streak >= self.policy.failure_count_threshold
            and elapsed >= self.policy.failure_elapsed_seconds
            and not state.intentional_pause
        )
        return SessionHealth(
            session_identifier=identifier,
            state=state.state,
            transitions=tuple(state.transitions),
            error_streak=state.error_streak,
            error_elapsed_seconds=elapsed,
            reconnect_count=state.reconnect_count,
            last_success_at=state.last_success_at,
            last_command_duration_seconds=state.last_command_duration_seconds,
            incident_id=state.incident_id,
            intentional_pause=state.intentional_pause,
            environment_event=(self._environment_event if now < self._environment_until else None),
            recommend_manual_action=(threshold_met and self.policy.mode == "assisted"),
        )
