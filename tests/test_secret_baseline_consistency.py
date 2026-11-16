"""Guard the reviewed secret baseline against stale file and hash locations.

A matching source line is not evidence a credential is safe: only the recorded
per-finding review may classify public digests as non-credentials.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def test_reviewed_hash_entries_still_point_to_hashes() -> None:
    baseline = json.loads(Path(".secrets.baseline").read_text(encoding="utf-8"))
    count = 0
    for filename, entries in baseline["results"].items():
        for entry in entries:
            assert filename == entry["filename"], "Baseline contains inconsistent source paths"
            if entry["type"] != "Hex High Entropy String":
                continue
            count += 1
            path = Path(filename.replace("\\", "/"))
            assert path.is_file(), f"Reviewed hash file no longer exists: {filename}"
            lines = path.read_text(encoding="utf-8").splitlines()
            position = int(entry["line_number"])
            assert 1 <= position <= len(lines), filename
            assert re.search(r"\b[a-fA-F0-9]{40}(?:[a-fA-F0-9]{24})?\b", lines[position - 1]), (
                f"Reviewed checksum/commit moved: {filename}:{position}"
            )
    assert count >= 10, "Reviewed checksum/commit records were unexpectedly removed"
