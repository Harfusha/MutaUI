"""Apply fresh session snapshots to the in-memory health tracker."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from mutaui.domain.models import SessionSnapshot
from mutaui.services.health_tracker import HealthObservation, HealthTracker, SessionHealth
from mutaui.services.session_doctor import FRESHNESS_SECONDS


def observe_session_health(
    tracker: HealthTracker,
    sessions: Sequence[SessionSnapshot],
    *,
    failed_sessions: set[str],
    sync_observed_at: datetime | None,
    forward_observed_at: datetime | None,
    command_durations: Mapping[str, float | None],
    now: float,
) -> list[SessionHealth]:
    tracker.prune({session.identity.identifier for session in sessions})
    results = []
    for session in sessions:
        session_kind = session.identity.kind
        source_timestamp = sync_observed_at if session_kind == "sync" else forward_observed_at
        timestamp_age = (
            (datetime.now().astimezone() - source_timestamp).total_seconds()
            if source_timestamp is not None
            else None
        )
        if (
            session.stale_reason is not None
            or timestamp_age is None
            or not 0 <= timestamp_age <= FRESHNESS_SECONDS
        ):
            continue
        observation_key = (
            f"{session_kind}:{source_timestamp.isoformat()}"
            if source_timestamp is not None
            else f"{session_kind}:stale"
        )
        raw_status = session.native_config.get("status")
        results.append(
            tracker.observe(
                HealthObservation(
                    session_identifier=session.identity.identifier,
                    observation_key=observation_key,
                    observed_at=session.measured_at,
                    state=session.state,
                    confirmed_failure=session.identity.identifier in failed_sessions,
                    intentional_pause=session.native_config.get("paused") is True,
                    scan_in_progress=raw_status in (7, "7") or "scan" in session.state.casefold(),
                    command_duration_seconds=command_durations.get(f"{session_kind} list"),
                ),
                now=now,
            )
        )
    return results
