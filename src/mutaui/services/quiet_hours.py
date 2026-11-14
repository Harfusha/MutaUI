"""Local-time quiet-hours policy for desktop notifications."""

from __future__ import annotations

from datetime import datetime, time


def _parse_clock(value: str) -> time:
    if len(value) != 5 or value[2] != ":" or not value[:2].isdigit() or not value[3:].isdigit():
        raise ValueError("Quiet-hours times must use HH:MM.")
    hour, minute = int(value[:2]), int(value[3:])
    if hour > 23 or minute > 59:
        raise ValueError("Quiet-hours times must use HH:MM.")
    return time(hour, minute)


def quiet_hours_active(
    now: datetime,
    *,
    enabled: bool,
    start: str = "22:00",
    end: str = "07:00",
) -> bool:
    """Return whether ``now`` falls in the configured local quiet interval.

    Equal start/end times mean no interval. Start is inclusive; end is exclusive.
    """
    if not enabled:
        return False
    start_time, end_time = _parse_clock(start), _parse_clock(end)
    current = now.time().replace(tzinfo=None)
    if start_time == end_time:
        return False
    if start_time < end_time:
        return start_time <= current < end_time
    return current >= start_time or current < end_time
