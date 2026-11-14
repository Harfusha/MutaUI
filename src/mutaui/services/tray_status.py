"""Worst confirmed Mutagen state represented by the desktop tray."""

from __future__ import annotations

from collections.abc import Iterable


def worst_tray_status(*, daemon_online: bool, sessions_stale: bool, states: Iterable[str]) -> str:
    if not daemon_online:
        return "offline"
    if sessions_stale:
        return "unknown"
    confirmed = tuple(states)
    if not confirmed:
        return "idle"
    if any(state in {"error", "conflicted"} for state in confirmed):
        return "issue"
    if "paused" in confirmed:
        return "paused"
    if any(state in {"connecting", "scanning", "transitioning", "staging"} for state in confirmed):
        return "busy"
    if all(state in {"watching", "active", "idle", "healthy"} for state in confirmed):
        return "healthy"
    return "unknown"
