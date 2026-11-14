"""Read-only interpretation of endpoint state exported by *local* Mutagen daemon.

No sockets, SSH connections, remote commands, or helper services are created here.
The Mutagen CLI obtains this information through its existing daemon API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mutagen_client import classify, endpoint_text


@dataclass(frozen=True)
class EndpointView:
    side: str
    address: str
    connected: bool
    scanned: bool | None
    files: int | None
    directories: int | None
    symlinks: int | None
    total_file_size: int | None
    scan_problems: int
    transition_problems: int
    staging_path: str
    staging_bytes: int
    staging_expected_bytes: int
    staging_files: int
    staging_expected_files: int
    staging_percent: float | None


def _nonnegative(value: Any) -> int | None:
    try:
        return max(0, int(value)) if value is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def _problems(endpoint: dict, name: str) -> int:
    return len(endpoint.get(name) or []) + int(
        _nonnegative(endpoint.get("excluded" + name[0].upper() + name[1:])) or 0
    )


def endpoint_view(endpoint: dict | None, side: str, kind: str = "sync") -> EndpointView:
    endpoint = endpoint if isinstance(endpoint, dict) else {}
    staging = endpoint.get("stagingProgress") or {}
    if not isinstance(staging, dict):
        staging = {}
    received = _nonnegative(staging.get("receivedSize")) or 0
    expected = _nonnegative(staging.get("expectedSize")) or 0
    received_files = _nonnegative(staging.get("receivedFiles")) or 0
    expected_files = _nonnegative(staging.get("expectedFiles")) or 0
    # An absent staging progress is *not* zero percent, it is unknown/N/A.
    progress = None
    if staging:
        if expected:
            progress = max(0.0, min(100.0, 100.0 * received / expected))
        elif expected_files:
            progress = max(0.0, min(100.0, 100.0 * received_files / expected_files))
    is_sync = kind == "sync"
    return EndpointView(
        side=side,
        address=endpoint_text(endpoint, kind),
        connected=bool(endpoint.get("connected")),
        scanned=(bool(endpoint["scanned"]) if "scanned" in endpoint and is_sync else None),
        files=_nonnegative(endpoint.get("files")) if is_sync else None,
        directories=_nonnegative(endpoint.get("directories")) if is_sync else None,
        symlinks=_nonnegative(endpoint.get("symbolicLinks")) if is_sync else None,
        total_file_size=_nonnegative(endpoint.get("totalFileSize")) if is_sync else None,
        scan_problems=_problems(endpoint, "scanProblems") if is_sync else 0,
        transition_problems=_problems(endpoint, "transitionProblems") if is_sync else 0,
        staging_path=str(staging.get("path") or ""),
        staging_bytes=received,
        staging_expected_bytes=expected,
        staging_files=received_files,
        staging_expected_files=expected_files,
        staging_percent=progress,
    )


def session_views(session: dict, kind: str) -> tuple[EndpointView, EndpointView]:
    if kind == "sync":
        return endpoint_view(session.get("alpha"), "ALPHA", kind), endpoint_view(
            session.get("beta"), "BETA", kind
        )
    if kind == "forward":
        return endpoint_view(session.get("source"), "SOURCE", kind), endpoint_view(
            session.get("destination"), "DESTINATION", kind
        )
    raise ValueError("Unknown session type")


def summary(session: dict, kind: str) -> dict:
    left, right = session_views(session, kind)
    state, text = classify(session, kind)
    base = {
        "name": str(session.get("name") or session.get("identifier") or "Session"),
        "identifier": str(session.get("identifier") or ""),
        "state": state,
        "state_text": text,
        "paused": bool(session.get("paused")),
        "last_error": str(session.get("lastError") or ""),
        "left": left,
        "right": right,
        "kind": kind,
    }
    if kind == "sync":
        base.update(
            successful_cycles=_nonnegative(session.get("successfulCycles")) or 0,
            conflicts=len(session.get("conflicts") or [])
            + (_nonnegative(session.get("excludedConflicts")) or 0),
        )
    else:
        base.update(
            open_connections=_nonnegative(session.get("openConnections")) or 0,
            total_connections=_nonnegative(session.get("totalConnections")) or 0,
            total_inbound_data=_nonnegative(session.get("totalInboundData")) or 0,
            total_outbound_data=_nonnegative(session.get("totalOutboundData")) or 0,
        )
    return base
