"""Debounce, group, and throttle per-session desktop issue notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class SessionNotification:
    kind: Literal["issue", "recovery"]
    session_keys: tuple[SessionKey, ...]
    titles: tuple[str, ...]


class SessionNotificationGate:
    """Emit one grouped incident after sustained failure; retain recovery state."""

    def __init__(self, *, debounce_seconds: float = 10, throttle_seconds: float = 60):
        if debounce_seconds < 0 or throttle_seconds < 0:
            raise ValueError("Notification intervals must not be negative.")
        self.debounce_seconds = debounce_seconds
        self.throttle_seconds = throttle_seconds
        self._pending: dict[SessionKey, tuple[float, str]] = {}
        self._notified: dict[SessionKey, str] = {}
        self._last_notified: dict[SessionKey, float] = {}

    def update(
        self,
        errors: dict[SessionKey, str],
        *,
        now: float,
        notifications_allowed: bool = True,
    ) -> tuple[SessionNotification, ...]:
        current_keys = set(errors)
        recovered = tuple(key for key in self._notified if key not in current_keys)
        recovery_titles = tuple(self._notified[key] for key in recovered)
        if recovered and notifications_allowed:
            for key in recovered:
                del self._notified[key]
        for key in tuple(self._pending):
            if key not in current_keys:
                del self._pending[key]

        for key, title in errors.items():
            if key in self._notified:
                self._notified[key] = title
            elif key in self._pending:
                started, _previous_title = self._pending[key]
                self._pending[key] = (started, title)
            else:
                self._pending[key] = (now, title)

        notifications: list[SessionNotification] = []
        if recovered and notifications_allowed:
            notifications.append(SessionNotification("recovery", recovered, recovery_titles))

        ready = tuple(
            key
            for key, (started, _title) in self._pending.items()
            if now - started >= self.debounce_seconds
            and (
                key not in self._last_notified
                or now - self._last_notified[key] >= self.throttle_seconds
            )
        )
        if ready and notifications_allowed:
            titles = tuple(self._pending[key][1] for key in ready)
            for key in ready:
                self._notified[key] = self._pending.pop(key)[1]
                self._last_notified[key] = now
            notifications.append(SessionNotification("issue", ready, titles))
        return tuple(notifications)
