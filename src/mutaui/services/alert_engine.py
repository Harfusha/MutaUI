"""Sustained resource alerts with one notification per incident."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any


def _number(value: Any) -> float:
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else 0.0
    except (ValueError, TypeError, OverflowError):
        return 0.0


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

    def __init__(self) -> None:
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
