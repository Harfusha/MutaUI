"""Privacy-conscious diagnostics, trend summaries and alert state machine.

No Qt dependency: this module can be tested without opening a UI.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from mutagen_client import classify, conflict_count, problem_count


def _number(value: Any) -> float:
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else 0.0
    except (ValueError, TypeError, OverflowError):
        return 0.0


def measurement_summary(rows: list[dict]) -> dict:
    """Calculate human-useful statistics from actual samples, not interpolated graph lines."""
    fields = ("cpu", "memory", "read_rate", "write_rate", "forward_out_rate", "forward_in_rate")
    result: dict = {"samples": len(rows), "fields": {}}
    for field in fields:
        values = sorted(_number(row.get(field)) for row in rows)
        if not values:
            result["fields"][field] = {"min": 0, "avg": 0, "p95": 0, "max": 0, "latest": 0}
            continue
        result["fields"][field] = {
            "min": values[0],
            "avg": sum(values) / len(values),
            "p95": values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)],
            "max": values[-1],
            "latest": _number(rows[-1].get(field)),
        }
    return result


@dataclass(frozen=True)
class ResourceAlert:
    key: str
    message: str
    value: float


class AlertEngine:
    """Sustained threshold alerts with one alert per incident and rearm after recovery.

    Intermittent threshold violations reset the hold timer. The notification only
    fires when the metric stays above the limit for the configured duration.
    """

    def __init__(self):
        self.started: dict[str, float] = {}
        self.fired: set[str] = set()

    def evaluate(self, cpu: float, ram_bytes: float, *, cpu_limit: float = 90.0,
                 ram_limit_mb: float = 1024, hold_seconds: float = 20,
                 enabled_cpu: bool = False, enabled_ram: bool = False,
                 now: float | None = None) -> list[ResourceAlert]:
        now = time.monotonic() if now is None else now
        limits = (
            ("cpu", enabled_cpu, _number(cpu), max(1, _number(cpu_limit)), "CPU", "%"),
            ("ram", enabled_ram, _number(ram_bytes) / 1024**2,
             max(1, _number(ram_limit_mb)), "RAM", "MB"),
        )
        alerts = []
        for key, enabled, value, threshold, name, unit in limits:
            if not enabled or value < threshold:
                self.started.pop(key, None)
                self.fired.discard(key)
                continue
            self.started.setdefault(key, now)
            if key not in self.fired and now - self.started[key] >= max(0, hold_seconds):
                self.fired.add(key)
                alerts.append(ResourceAlert(key, f"Mutagen {name}: {value:.1f} {unit} (limit {threshold:.1f} {unit})", value))
        return alerts


def state_transitions(previous: dict, current: dict) -> list[tuple[str, str, str, str]]:
    """Report meaningful transitions, not brief normal busy/active oscillations."""
    events = []
    for identity, state in current.items():
        old = previous.get(identity)
        if old is None or old == state:
            continue
        old_group = "working" if old in ("active", "busy") else old
        new_group = "working" if state in ("active", "busy") else state
        if old_group != new_group:
            events.append((*identity, old, state))
    return events


def safe_diagnostic_report(snapshot: Any, *, now: float | None = None) -> dict:
    """Strict allow-list: excludes identifiers, names, paths, hosts, auth and errors.

    Unlike redaction of a raw snapshot, new upstream fields are excluded by
    default so future Mutagen versions won't accidentally leak secrets.
    """
    now = time.time() if now is None else now
    report = {
        "schema": "mutagen-control-safe-diagnostics-v1",
        "timestamp_unix": round(now),
        "daemon_running": bool(snapshot.daemon),
        "mutagen_version": str(snapshot.version or "")[:120],
        "registration": snapshot.registration if snapshot.registration in
                        ("registered", "unregistered", "other", "unknown", "unsupported") else "unknown",
        "local_processes": int(snapshot.processes or 0),
        "cpu_percent_total": _number(snapshot.cpu),
        "memory_bytes_total": int(snapshot.memory or 0),
        "sessions": [],
    }
    for kind, sessions in (("sync", snapshot.sync), ("forward", snapshot.forward)):
        for item in sessions:
            state, _ = classify(item, kind)
            session = {"kind": kind, "state": state, "paused": bool(item.get("paused")),
                       "has_error": bool(item.get("lastError"))}
            if kind == "sync":
                session.update(conflict_count=conflict_count(item), problem_count=problem_count(item),
                               successful_cycles=int(item.get("successfulCycles") or 0),
                               alpha_connected=bool((item.get("alpha") or {}).get("connected")),
                               beta_connected=bool((item.get("beta") or {}).get("connected")))
            else:
                session.update(open_connections=int(item.get("openConnections") or 0),
                               total_connections=int(item.get("totalConnections") or 0))
            report["sessions"].append(session)
    return report
