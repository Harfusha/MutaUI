"""Ambiguity-preserving lookup of sync sessions containing a local path."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from mutaui.domain.models import SessionSnapshot


def _is_within_path(
    root: str,
    candidate: str,
    *,
    commonpath: Callable[[Sequence[str]], str] = os.path.commonpath,
    normcase: Callable[[str], str] = os.path.normcase,
) -> bool:
    """Check containment with the host path rules; cross-volume paths do not match."""
    try:
        return normcase(commonpath((root, candidate))) == normcase(root)
    except ValueError:
        return False


def find_local_sessions_for_path(
    snapshots: Sequence[SessionSnapshot], selected_path: str | Path
) -> tuple[str, ...]:
    """Return all exact sync IDs whose resolved local root contains the path."""
    try:
        query = Path(selected_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return ()
    matches: list[str] = []
    for snapshot in snapshots:
        if snapshot.identity.kind != "sync" or snapshot.stale_reason:
            continue
        for endpoint in (snapshot.alpha_or_source, snapshot.beta_or_destination):
            if endpoint is None or endpoint.kind != "local" or not endpoint.path:
                continue
            try:
                root = Path(endpoint.path).expanduser().resolve(strict=True)
                if root.is_dir() and _is_within_path(str(root), str(query)):
                    matches.append(snapshot.identity.identifier)
                    break
            except (OSError, RuntimeError, ValueError):
                continue
    return tuple(sorted(set(matches)))
