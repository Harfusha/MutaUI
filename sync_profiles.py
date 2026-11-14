"""Native Mutagen creation profiles, and low-cost GUI polling policy.

Existing Mutagen sessions cannot be reconfigured in place using the standard
Mutagen sync CLI. Profiles here are ONLY applied at session creation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

PROFILES = {
    "default": ("Default Mutagen configuration", ()),
    "events": (
        "File change events (portable watch)",
        ("--watch-mode=portable", "--scan-mode=accelerated"),
    ),
    "fast_poll": (
        "Poll every 5 s (higher load)",
        ("--watch-mode=force-poll", "--watch-polling-interval=5"),
    ),
    "balanced_poll": (
        "Poll every 20 s",
        ("--watch-mode=force-poll", "--watch-polling-interval=20"),
    ),
    "eco_poll": ("Eco poll every 60 s", ("--watch-mode=force-poll", "--watch-polling-interval=60")),
    "manual": ("No file watching (Sync now manually)", ("--watch-mode=no-watch",)),
}


def profile_flags(profile: str) -> list[str]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    return list(PROFILES[profile][1])


def native_config_text(session: dict) -> str:
    watch = session.get("watch") or {}
    config = {
        "Watch mode": watch.get("mode", "default"),
        "Polling interval": watch.get("pollingInterval", "default"),
        "Scan mode": session.get("scanMode", "default"),
        "Compression algorithm": (session.get("compression") or {}).get("algorithm", "default"),
    }
    return "\n".join(f"{key}: {val}" for key, val in config.items())


@dataclass
class AdaptivePolling:
    """Throttle GUI's local CLI reads, never alter Mutagen daemon's sync timing."""

    fast: int = 2
    idle: int = 20
    quiet_after: int = 90
    clock: object = time.monotonic
    last_activity: float | None = None
    previous_signature: tuple | None = None
    busy: bool = False

    def observe(self, snapshot) -> None:
        now = self.clock()
        signature_items = []
        self.busy = False
        for kind, group in (("sync", snapshot.sync), ("forward", snapshot.forward)):
            busy_statuses = (
                {"4", "5", "7", "9", "10", "11", "12", "13"} if kind == "sync" else {"1", "2"}
            )
            for s in group:
                signature_items.append(
                    (
                        kind,
                        str(s.get("identifier") or ""),
                        bool(s.get("paused")),
                        str(s.get("status")),
                        int(s.get("successfulCycles") or 0),
                        len(s.get("conflicts") or []),
                        str(s.get("lastError") or ""),
                        int(s.get("totalConnections") or 0),
                    )
                )
                if not s.get("paused") and str(s.get("status")) in busy_statuses:
                    self.busy = True
        signature = tuple(sorted(signature_items))
        if self.previous_signature != signature or self.busy:
            self.last_activity = now
        self.previous_signature = signature

    def interval(self, *, enabled: bool, normal: int, eco: bool = False) -> int:
        normal = max(2, min(30, int(normal)))
        if enabled:
            now = self.clock()
            recent = self.last_activity is not None and now - self.last_activity < self.quiet_after
            value = self.fast if self.busy or recent else self.idle
        else:
            value = normal
        return max(15, value) if eco else max(2, value)
