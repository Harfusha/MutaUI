"""Group Mutagen sessions by remote endpoint using only the local daemon's API data.

Host matching is deliberately conservative: DNS aliases and different hostnames
may point at the same machine, but we never guess or make network requests.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


def _remote_key(endpoint: dict) -> tuple[str, str] | None:
    if not isinstance(endpoint, dict):
        return None
    protocol = endpoint.get("protocol", 0)
    try:
        number = int(protocol)
    except (TypeError, ValueError):
        number = {"ssh": 1, "docker": 11}.get(str(protocol).lower(), 0)
    host = str(endpoint.get("host") or "").strip().lower()
    if not host or number not in (1, 11):
        return None
    if number == 1:
        port = endpoint.get("port") or 22
        try:
            port = int(port)
        except (ValueError, TypeError):
            port = 22
        # Group by server, not by SSH user, session path or display name.
        return (f"ssh:{host}:{port}", f"{host}:{port}" if port != 22 else host)
    return (f"docker:{host}", f"Docker · {host}")


def session_servers(session: dict, kind: str) -> set[str]:
    names = ("alpha", "beta") if kind == "sync" else ("source", "destination")
    return {key for item in names if (ident := _remote_key(session.get(item) or {}))
            for key in (ident[0],)}


@dataclass
class ServerGroup:
    key: str
    name: str
    sync_ids: list[str] = field(default_factory=list)
    forward_ids: list[str] = field(default_factory=list)
    errors: int = 0
    paused: int = 0

    @property
    def count(self) -> int:
        return len(self.sync_ids) + len(self.forward_ids)


def group_servers(sync: Iterable[dict], forward: Iterable[dict]) -> list[ServerGroup]:
    """Each session can be listed under two servers, but never twice under one."""
    from mutagen_client import classify
    groups: dict[str, ServerGroup] = {}
    for kind, sessions in (("sync", sync), ("forward", forward)):
        for sess in sessions:
            identifier = str(sess.get("identifier") or "")
            if not identifier:
                continue
            endpoint_names = ("alpha", "beta") if kind == "sync" else ("source", "destination")
            seen = set()
            for end in endpoint_names:
                pair = _remote_key(sess.get(end) or {})
                if not pair or pair[0] in seen:
                    continue
                seen.add(pair[0])
                key, name = pair
                group = groups.setdefault(key, ServerGroup(key, name))
                (group.sync_ids if kind == "sync" else group.forward_ids).append(identifier)
                state = classify(sess, kind)[0]
                group.errors += int(state == "error")
                group.paused += int(state == "paused")
    return sorted(groups.values(), key=lambda group: group.name.casefold())
