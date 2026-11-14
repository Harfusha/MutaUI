"""Loss-preserving adapter from existing Mutagen JSON dictionaries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from mutagen_client import classify, endpoint_text
from mutaui.domain.models import Endpoint, SessionIdentity, SessionSnapshot


def _endpoint(raw: object, *, kind: Literal["sync", "forward"]) -> Endpoint | None:
    if not isinstance(raw, dict):
        return None
    protocol = raw.get("protocol")
    protocol_text = str(protocol) if protocol is not None else None
    protocol_kinds = {0: "local", 1: "ssh", 11: "docker"}
    endpoint_kind = (
        protocol_kinds.get(protocol, "unknown") if isinstance(protocol, int) else "unknown"
    )
    host = raw.get("host") if isinstance(raw.get("host"), str) else None
    user = raw.get("user") if isinstance(raw.get("user"), str) else None
    port = (
        raw.get("port")
        if isinstance(raw.get("port"), int) and not isinstance(raw.get("port"), bool)
        else None
    )
    path_key = "path" if kind == "sync" else "endpoint"
    path = raw.get(path_key) if isinstance(raw.get(path_key), str) else None
    return Endpoint(
        endpoint_kind, endpoint_text(raw, kind), host, port, user, path, protocol_text, raw
    )


def from_legacy_session(
    kind: Literal["sync", "forward"],
    raw: dict[str, object],
    *,
    measured_at: datetime,
    stale_reason: str | None = None,
) -> SessionSnapshot:
    identifier = raw.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("Native session identifier is required")
    name = raw.get("name")
    labels = raw.get("labels", {})
    if not isinstance(labels, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in labels.items()
    ):
        raise ValueError("Native session labels must be string pairs")
    identity = SessionIdentity(kind, identifier, name if isinstance(name, str) else "", labels)
    if kind == "sync":
        first, second = raw.get("alpha"), raw.get("beta")
    else:
        first, second = raw.get("source"), raw.get("destination")
    counters = {
        key: value
        for key, value in raw.items()
        if key in {"files", "directories", "symbolicLinks", "totalFileSize"}
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    }
    conflicts = raw.get("conflicts")
    conflict_items = tuple(conflicts) if isinstance(conflicts, list) else ()
    problems: list[object] = []
    for endpoint in (first, second):
        if not isinstance(endpoint, dict):
            continue
        for field in ("scanProblems", "transitionProblems"):
            items = endpoint.get(field)
            if isinstance(items, list):
                problems.extend(items)
    return SessionSnapshot(
        identity=identity,
        native_config=raw,
        alpha_or_source=_endpoint(first, kind=kind),
        beta_or_destination=_endpoint(second, kind=kind),
        state=classify(raw, kind)[0],
        conflicts=conflict_items,
        problems=tuple(problems),
        counters=counters,
        measured_at=measured_at,
        stale_reason=stale_reason,
    )
