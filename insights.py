"""Privacy-conscious diagnostics, trend summaries and alert state machine.

No Qt dependency: this module can be tested without opening a UI.
"""

from __future__ import annotations

import math
import os
import platform
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from mutagen_client import classify, conflict_count, problem_count


def local_self_check(*, app_path, settings_path, history, qt_version, mutagen_version):
    """Check local app paths and runtime health without changing local or remote state."""
    app_file = os.fspath(app_path)
    settings_file = os.fspath(settings_path)
    app_exists = os.path.isfile(app_file)
    settings_parent_exists = os.path.isdir(os.path.dirname(settings_file))
    settings_parent_writable = settings_parent_exists and os.access(
        os.path.dirname(settings_file), os.W_OK
    )
    try:
        integrity = history.db.execute("PRAGMA integrity_check").fetchone()[0]
        database_ok = integrity == "ok"
    except (AttributeError, sqlite3.Error, TypeError) as exc:
        integrity = type(exc).__name__
        database_ok = False
    return {
        "schema": "mutagen-control-self-check-v1",
        "checks": {
            "application_path": {
                "status": "ok" if app_exists else "warning",
                "detail": "found" if app_exists else "missing",
            },
            "settings_path": {
                "status": "ok" if settings_parent_writable else "warning",
                "detail": "directory writable"
                if settings_parent_writable
                else "directory unavailable or read-only",
            },
            "history_database": {
                "status": "ok" if database_ok else "error",
                "detail": str(integrity),
            },
            "python": {"status": "ok", "detail": platform.python_version()},
            "qt": {
                "status": "ok" if qt_version else "warning",
                "detail": qt_version or "unavailable",
            },
            "mutagen_cli": {
                "status": "ok" if mutagen_version else "warning",
                "detail": mutagen_version or "unavailable",
            },
        },
        "remote_writes": False,
    }


def _number(value: Any) -> float:
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else 0.0
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _measured_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    except (ValueError, TypeError, OverflowError):
        return None


def measurement_summary(rows: list[dict]) -> dict:
    """Calculate human-useful statistics from actual samples, not interpolated graph lines."""
    fields = ("cpu", "memory", "read_rate", "write_rate", "forward_out_rate", "forward_in_rate")
    result: dict = {"samples": len(rows), "fields": {}}
    for field in fields:
        values = sorted(
            value for row in rows if (value := _measured_number(row.get(field))) is not None
        )
        if not values:
            result["fields"][field] = {
                "min": None,
                "avg": None,
                "p95": None,
                "max": None,
                "latest": None,
                "measured_samples": 0,
            }
            continue
        result["fields"][field] = {
            "min": values[0],
            "avg": sum(values) / len(values),
            "p95": values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)],
            "max": values[-1],
            "latest": _measured_number(rows[-1].get(field)),
            "measured_samples": len(values),
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

    def evaluate(
        self,
        cpu: float,
        ram_bytes: float,
        *,
        cpu_limit: float = 90.0,
        ram_limit_mb: float = 1024,
        hold_seconds: float = 20,
        enabled_cpu: bool = False,
        enabled_ram: bool = False,
        now: float | None = None,
    ) -> list[ResourceAlert]:
        now = time.monotonic() if now is None else now
        limits = (
            ("cpu", enabled_cpu, _number(cpu), max(1, _number(cpu_limit)), "CPU", "%"),
            (
                "ram",
                enabled_ram,
                _number(ram_bytes) / 1024**2,
                max(1, _number(ram_limit_mb)),
                "RAM",
                "MB",
            ),
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
                alerts.append(
                    ResourceAlert(
                        key,
                        f"Mutagen {name}: {value:.1f} {unit} (limit {threshold:.1f} {unit})",
                        value,
                    )
                )
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


def _safe_age_seconds(value: Any, now: float) -> int | None:
    if not isinstance(value, datetime):
        return None
    try:
        return max(0, round(now - value.timestamp()))
    except (OverflowError, OSError, ValueError):
        return None


def _safe_version(value: Any) -> str:
    text = str(value or "")
    return text[:64] if re.fullmatch(r"[A-Za-z0-9._+ -]{1,64}", text) else "unknown"


def safe_diagnostic_report(
    snapshot: Any,
    *,
    now: float | None = None,
    application_version: str = "unknown",
    qt_version: str = "unknown",
    problem_codes: tuple[str, ...] | list[str] = (),
    build_id: str | None = None,
    recent_event_count: int = 0,
    event_count_capped: bool = False,
) -> dict:
    """Strict allow-list: excludes identifiers, names, paths, hosts, auth and errors.

    Unlike redaction of a raw snapshot, new upstream fields are excluded by
    default so future Mutagen versions won't accidentally leak secrets.
    """
    now = time.time() if now is None else now
    codes = sorted(
        {
            code
            for code in problem_codes
            if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,64}", code)
        }
    )
    if build_id is not None and not re.fullmatch(r"[0-9]{1,20}", build_id):
        build_id = None
    version = str(snapshot.version or "")
    version_match = re.search(r"(?:Mutagen version )?([0-9]+(?:\.[0-9A-Za-z-]+){1,4})", version)
    resource_observed = getattr(snapshot, "resource_observed_at", None) is not None
    cpu_percent = _measured_number(getattr(snapshot, "cpu", None)) if resource_observed else None
    memory_bytes = (
        _measured_number(getattr(snapshot, "memory", None)) if resource_observed else None
    )
    process_count = (
        _measured_number(getattr(snapshot, "processes", None)) if resource_observed else None
    )
    report = {
        "schema": "mutagen-control-safe-diagnostics-v1",
        "timestamp_unix": round(now),
        "application_version": _safe_version(application_version),
        "runtime": {
            "os": _safe_version(platform.system()),
            "os_release": _safe_version(platform.release()),
            "python_version": _safe_version(platform.python_version()),
            "qt_version": _safe_version(qt_version),
        },
        "ci_build_id": build_id,
        "freshness": {
            "sessions_stale": bool(getattr(snapshot, "sessions_stale", True)),
            "sync_age_seconds": _safe_age_seconds(getattr(snapshot, "sync_observed_at", None), now),
            "forward_age_seconds": _safe_age_seconds(
                getattr(snapshot, "forward_observed_at", None), now
            ),
            "resource_age_seconds": _safe_age_seconds(
                getattr(snapshot, "resource_observed_at", None), now
            ),
        },
        "observed_capabilities": {
            "mutagen_version_reported": bool(version_match),
            "sync_snapshot_available": getattr(snapshot, "sync_observed_at", None) is not None,
            "forward_snapshot_available": getattr(snapshot, "forward_observed_at", None)
            is not None,
        },
        "problem_codes": codes,
        "event_counts": {
            "recent_events": max(0, min(int(recent_event_count), 500)),
            "capped": bool(event_count_capped),
        },
        "daemon_running": bool(snapshot.daemon),
        "mutagen_version": version_match.group(1) if version_match else "unknown",
        "registration": snapshot.registration
        if snapshot.registration
        in ("registered", "unregistered", "other", "unknown", "unsupported")
        else "unknown",
        "local_processes": int(process_count) if process_count is not None else None,
        "cpu_percent_total": cpu_percent,
        "memory_bytes_total": int(memory_bytes) if memory_bytes is not None else None,
        "sessions": [],
    }
    for kind, sessions in (("sync", snapshot.sync), ("forward", snapshot.forward)):
        for item in sessions:
            state, _ = classify(item, kind)
            session = {
                "kind": kind,
                "state": state,
                "paused": bool(item.get("paused")),
                "has_error": bool(item.get("lastError")),
            }
            if kind == "sync":
                session.update(
                    conflict_count=conflict_count(item),
                    problem_count=problem_count(item),
                    successful_cycles=int(item.get("successfulCycles") or 0),
                    alpha_connected=bool((item.get("alpha") or {}).get("connected")),
                    beta_connected=bool((item.get("beta") or {}).get("connected")),
                )
            else:
                session.update(
                    open_connections=int(item.get("openConnections") or 0),
                    total_connections=int(item.get("totalConnections") or 0),
                )
            report["sessions"].append(session)
    return report


def session_log_report(
    events: list[tuple[float, str, str]],
    monitored_log_lines: list[str],
    *,
    now: float | None = None,
    include_event_messages: bool = False,
    include_monitored_log_lines: bool = False,
) -> dict[str, Any]:
    """Build a bounded local log snapshot; raw text is omitted unless selected."""
    now = time.time() if now is None else now
    bounded_events = events[-500:]
    bounded_lines = monitored_log_lines[-1200:]
    report: dict[str, Any] = {
        "schema": "mutagen-control-session-logs-v1",
        "timestamp_unix": round(now),
        "event_count": len(events),
        "event_count_capped": len(events) > 500,
        "monitored_line_count": len(monitored_log_lines),
        "monitored_line_count_capped": len(monitored_log_lines) > 1200,
        "events": [],
        "monitored_log_lines": list(bounded_lines) if include_monitored_log_lines else [],
    }
    for timestamp, severity, message in bounded_events:
        event = {
            "timestamp_unix": _measured_number(timestamp),
            "severity": severity if severity in ("info", "warning", "error") else "unknown",
        }
        if include_event_messages:
            event["message"] = str(message)
        report["events"].append(event)
    return report
