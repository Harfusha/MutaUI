"""Small deterministic render/polling primitives independent of Qt.

Separating these from the UI makes performance constraints testable. None of
these helpers generate or interpolate fake measurements.
"""

from __future__ import annotations

import bisect
import math
import time
from collections.abc import Iterable


def envelope_downsample(rows: Iterable[tuple], max_points: int = 600) -> list[tuple]:
    """Return time-ordered rows while preserving peaks and troughs.

    For each bucket retain max/min of each *present* numeric metric, plus the
    first and last measurement. This prevents the average-only artefact where
    a short CPU spike disappears when the history is zoomed out.

    Data are never interpolated across gaps. The caller handles missing periods.
    """
    points = list(rows)
    max_points = max(8, int(max_points))
    if len(points) <= max_points:
        return points
    columns = min(2, max(0, len(points[0]) - 1))
    # Reserve two boundary points. Keep up to 4 selected points per bucket.
    bucket_count = max(1, (max_points - 2) // max(2, columns * 2))
    usable = points[1:-1]
    output = [points[0]]
    for b in range(bucket_count):
        start = b * len(usable) // bucket_count
        stop = (b + 1) * len(usable) // bucket_count
        chunk = usable[start:stop]
        if not chunk:
            continue
        selected = {0, len(chunk) - 1}
        for j in range(1, columns + 1):
            valid = [
                (idx, row[j])
                for idx, row in enumerate(chunk)
                if isinstance(row[j], (int, float)) and math.isfinite(row[j])
            ]
            if valid:
                selected.add(min(valid, key=lambda pair: pair[1])[0])
                selected.add(max(valid, key=lambda pair: pair[1])[0])
        output.extend(chunk[i] for i in sorted(selected))
    output.append(points[-1])
    # Rare bucket-size rounding can exceed the requested bound by up to two.
    # Recurse once if necessary, keeping temporal extrema from stage one.
    if len(output) > max_points:
        return envelope_downsample(output, max_points)
    return output


def nearest_time_index(timestamps: list[float], target: float) -> int:
    """Binary-search the nearest sample in O(log n) (for graph tooltips)."""
    if not timestamps:
        return -1
    idx = bisect.bisect_left(timestamps, target)
    if idx <= 0:
        return 0
    if idx >= len(timestamps):
        return len(timestamps) - 1
    return idx if abs(timestamps[idx] - target) < abs(timestamps[idx - 1] - target) else idx - 1


class RefreshGate:
    """Coalesce UI refreshes; forcing bypasses limit, but updates the clock."""

    def __init__(self, min_seconds: float, clock=time.monotonic):
        if min_seconds < 0:
            raise ValueError("Interval must be non-negative")
        self.min_seconds = float(min_seconds)
        self.clock = clock
        self.last = float("-inf")

    def ready(self, force: bool = False) -> bool:
        now = self.clock()
        if force or now < self.last or now - self.last >= self.min_seconds:
            self.last = now
            return True
        return False

    def reset(self):
        self.last = float("-inf")


class PollBackoff:
    """Limit repeated failing CLI polls; manual refresh always bypasses it.

    A healthy poll returns immediately to the configured timer interval. Failed
    daemon/CLI queries back off exponentially to `maximum` seconds. The clock
    is injected so retry logic can be tested without sleeping.
    """

    def __init__(self, base: float = 4.0, maximum: float = 60.0, clock=time.monotonic):
        if base <= 0 or maximum < base:
            raise ValueError("Invalid polling backoff interval")
        self.base = base
        self.maximum = maximum
        self.clock = clock
        self.failures = 0
        self.retry_at = 0.0

    def observe(self, success: bool) -> None:
        if success:
            self.failures = 0
            self.retry_at = 0.0
        else:
            self.failures += 1
            self.retry_at = self.clock() + min(
                self.maximum, self.base * (2 ** min(20, self.failures - 1))
            )

    def can_retry(self, force: bool = False) -> bool:
        return force or self.clock() >= self.retry_at

    def remaining(self) -> float:
        return max(0.0, self.retry_at - self.clock())
