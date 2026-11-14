"""Repeatable *local* microbenchmarks; no Qt, server, network, or daemon needed.

Run: python benchmark.py
This is NOT a Windows GUI benchmark nor a claim about runtime CPU/RAM.
"""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from endpoint_inspector import summary
from monitoring import HistoryStore, Sample
from mutagen_client import example_snapshot


def timed(func, repetitions=3):
    durations = []
    for _ in range(repetitions):
        start = time.perf_counter()
        func()
        durations.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(durations), 3)


def run_benchmark():
    session = example_snapshot().sync[0]
    decode_ms = timed(lambda: [summary(session, "sync") for _ in range(10_000)])
    with tempfile.TemporaryDirectory() as directory:
        db = HistoryStore(Path(directory) / "metrics.sqlite3")
        try:
            now = time.time()

            def fill():
                for i in range(2000):
                    db.add(Sample(ts=now - 4000 + i * 2, cpu=i % 50, memory=100_000_000 + i))

            fill_ms = timed(fill, 1)
            read_ms = timed(lambda: db.query(hours=2, max_points=320))
        finally:
            db.close()
    return {
        "endpoint_decoding_10k_ms": decode_ms,
        "sqlite_write_2k_ms": fill_ms,
        "sqlite_aggregate_2k_ms": read_ms,
        "note": "Isolated microbenchmarks; not a Windows GUI or SSH test",
    }


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), ensure_ascii=False, indent=2))
