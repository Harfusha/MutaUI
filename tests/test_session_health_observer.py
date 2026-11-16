"""Tests for filtering current snapshots before health observation."""

from datetime import datetime, timedelta

from mutaui.domain.models import SessionIdentity, SessionSnapshot
from mutaui.services.health_tracker import HealthObservation, HealthTracker
from mutaui.services.session_doctor import FRESHNESS_SECONDS
from mutaui.services.session_health_observer import observe_session_health


def make_session(
    identifier: str,
    observed_at: datetime,
    *,
    kind: str = "sync",
    stale_reason: str | None = None,
    native_config: dict[str, object] | None = None,
    state: str = "watching",
) -> SessionSnapshot:
    return SessionSnapshot(
        identity=SessionIdentity(kind=kind, identifier=identifier, name=identifier),
        native_config=native_config or {},
        alpha_or_source=None,
        beta_or_destination=None,
        state=state,
        conflicts=(),
        problems=(),
        counters={},
        measured_at=observed_at,
        stale_reason=stale_reason,
    )


def test_only_fresh_sessions_are_observed():
    now = datetime.now().astimezone()
    sessions = [
        make_session("fresh", now),
        make_session("stale", now, stale_reason="stale snapshot"),
        make_session(
            "old-forward",
            now - timedelta(seconds=FRESHNESS_SECONDS + 1),
            kind="forward",
        ),
    ]

    results = observe_session_health(
        HealthTracker(),
        sessions,
        failed_sessions=set(),
        sync_observed_at=now,
        forward_observed_at=now - timedelta(seconds=FRESHNESS_SECONDS + 1),
        command_durations={"sync list": 0.25},
        now=10.0,
    )

    assert [result.session_identifier for result in results] == ["fresh"]
    assert results[0].last_command_duration_seconds == 0.25


def test_missing_and_future_timestamps_are_not_observed():
    now = datetime.now().astimezone()
    session = make_session("forward", now, kind="forward")

    assert (
        observe_session_health(
            HealthTracker(),
            [session],
            failed_sessions=set(),
            sync_observed_at=None,
            forward_observed_at=None,
            command_durations={},
            now=10.0,
        )
        == []
    )
    assert (
        observe_session_health(
            HealthTracker(),
            [session],
            failed_sessions=set(),
            sync_observed_at=None,
            forward_observed_at=now + timedelta(seconds=1),
            command_durations={},
            now=10.0,
        )
        == []
    )


def test_health_observation_preserves_failure_pause_and_scan_signals():
    class RecordingTracker(HealthTracker):
        def __init__(self):
            super().__init__()
            self.observations: list[tuple[HealthObservation, float]] = []

        def observe(self, observation: HealthObservation, *, now: float):
            self.observations.append((observation, now))
            return super().observe(observation, now=now)

    observed_at = datetime.now().astimezone()
    tracker = RecordingTracker()
    session = make_session(
        "sync",
        observed_at,
        native_config={"paused": True, "status": 7},
        state="scanning",
    )

    observe_session_health(
        tracker,
        [session],
        failed_sessions={"sync"},
        sync_observed_at=observed_at,
        forward_observed_at=None,
        command_durations={},
        now=123.0,
    )

    observation, monotonic_now = tracker.observations[0]
    assert observation.confirmed_failure is True
    assert observation.intentional_pause is True
    assert observation.scan_in_progress is True
    assert monotonic_now == 123.0
