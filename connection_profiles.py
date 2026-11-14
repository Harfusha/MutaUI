"""Versioned local storage for reusable connection profiles."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from uuid import uuid4

from forward_configuration import validate_forward_proposal
from sync_configuration import validate_sync_proposal

CURRENT_SCHEMA_VERSION = 1
ProfileKind = Literal["sync", "forward"]
_PROFILE_FIELDS = {
    "id",
    "name",
    "kind",
    "endpoint_a",
    "endpoint_b",
    "tags",
    "favorite",
    "defaults",
    "created_at",
    "updated_at",
}


class ProfileStoreError(ValueError):
    """The profile store is malformed or cannot be safely changed."""


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    id: str
    name: str
    kind: ProfileKind
    endpoint_a: str
    endpoint_b: str
    tags: tuple[str, ...] = ()
    favorite: bool = False
    defaults: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "defaults", MappingProxyType(copy.deepcopy(dict(self.defaults))))


@dataclass(frozen=True, slots=True)
class ProfileStoreLoad:
    profiles: tuple[ConnectionProfile, ...]
    valid: bool
    schema_version: int | None
    warnings: tuple[str, ...] = ()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _clean_tags(tags: Any) -> tuple[str, ...]:
    if not isinstance(tags, (list, tuple)) or len(tags) > 64:
        raise ProfileStoreError("Profile tags must be a list of at most 64 strings.")
    result = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip() or len(tag) > 32:
            raise ProfileStoreError("Each profile tag must be 1–32 characters.")
        clean = tag.strip()
        if clean not in result:
            result.append(clean)
    return tuple(result)


def _clean_defaults(kind: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or len(raw) > 64:
        raise ProfileStoreError("Profile defaults must be a mapping with at most 64 fields.")
    clean = {}
    validator = validate_sync_proposal if kind == "sync" else validate_forward_proposal
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ProfileStoreError("Profile default field names must be strings.")
        try:
            clean[key] = validator(key, value)
        except (ValueError, TypeError) as exc:
            raise ProfileStoreError(f"Invalid profile default '{key}': {exc}") from exc
    return clean


def _parse_profile(raw: Any) -> ConnectionProfile:
    if not isinstance(raw, dict) or set(raw) - _PROFILE_FIELDS:
        raise ProfileStoreError("Profile entry must be an object with only supported fields.")
    identifier = raw.get("id")
    name = raw.get("name")
    kind = raw.get("kind")
    endpoint_a, endpoint_b = raw.get("endpoint_a"), raw.get("endpoint_b")
    favorite = raw.get("favorite", False)
    if not isinstance(identifier, str) or not identifier or len(identifier) > 80:
        raise ProfileStoreError("Profile ID is invalid.")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ProfileStoreError("Profile name must be 1–120 characters.")
    if kind not in ("sync", "forward"):
        raise ProfileStoreError("Profile kind must be sync or forward.")
    for endpoint in (endpoint_a, endpoint_b):
        if not isinstance(endpoint, str) or not endpoint.strip() or len(endpoint) > 4096:
            raise ProfileStoreError(
                "Profile endpoints must be non-empty strings of at most 4096 characters."
            )
        if "\x00" in endpoint:
            raise ProfileStoreError("Profile endpoints cannot contain NUL characters.")
    if type(favorite) is not bool:
        raise ProfileStoreError("Profile favorite must be a boolean.")
    tags = _clean_tags(raw.get("tags", []))
    defaults = _clean_defaults(kind, raw.get("defaults", {}))
    created_at = raw.get("created_at", "")
    updated_at = raw.get("updated_at", "")
    if not isinstance(created_at, str) or not isinstance(updated_at, str):
        raise ProfileStoreError("Profile timestamps must be strings.")
    return ConnectionProfile(
        identifier,
        name.strip(),
        kind,
        endpoint_a,
        endpoint_b,
        tags,
        favorite,
        defaults,
        created_at or _timestamp(),
        updated_at or _timestamp(),
    )


def load_profile_store(path: str | Path) -> ProfileStoreLoad:
    target = Path(path)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ProfileStoreLoad((), True, CURRENT_SCHEMA_VERSION)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ProfileStoreLoad(
            (), False, None, (f"Profile file could not be read: {type(exc).__name__}.",)
        )
    try:
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "profiles"}:
            raise ProfileStoreError("Profile store must contain only schema_version and profiles.")
        version = raw.get("schema_version")
        if type(version) is not int or version != CURRENT_SCHEMA_VERSION:
            raise ProfileStoreError(f"Unsupported connection profile schema version: {version!r}.")
        entries = raw.get("profiles")
        if not isinstance(entries, list) or len(entries) > 10000:
            raise ProfileStoreError("Profile list must contain at most 10000 entries.")
        profiles = tuple(_parse_profile(entry) for entry in entries)
        ids = [profile.id for profile in profiles]
        if len(ids) != len(set(ids)):
            raise ProfileStoreError("Profile IDs must be unique.")
        return ProfileStoreLoad(profiles, True, version)
    except ProfileStoreError as exc:
        version = raw.get("schema_version") if isinstance(raw, dict) else None
        return ProfileStoreLoad((), False, version, (str(exc),))


def _profile_json(profile: ConnectionProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "kind": profile.kind,
        "endpoint_a": profile.endpoint_a,
        "endpoint_b": profile.endpoint_b,
        "tags": list(profile.tags),
        "favorite": profile.favorite,
        "defaults": dict(profile.defaults),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


class ConnectionProfileStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        loaded = load_profile_store(self.path)
        if not loaded.valid:
            raise ProfileStoreError(
                "Cannot change an invalid profile store: " + "; ".join(loaded.warnings)
            )
        self.profiles = list(loaded.profiles)

    def create(
        self,
        name: str,
        endpoint_a: str,
        endpoint_b: str,
        *,
        kind: ProfileKind,
        tags: tuple[str, ...] = (),
        favorite: bool = False,
        defaults: Mapping[str, Any] | None = None,
    ) -> ConnectionProfile:
        now = _timestamp()
        profile = _parse_profile(
            {
                "id": uuid4().hex,
                "name": name,
                "kind": kind,
                "endpoint_a": endpoint_a,
                "endpoint_b": endpoint_b,
                "tags": tags,
                "favorite": favorite,
                "defaults": dict(defaults or {}),
                "created_at": now,
                "updated_at": now,
            }
        )
        self.add(profile)
        return profile

    def add(self, profile: ConnectionProfile) -> None:
        if any(existing.id == profile.id for existing in self.profiles):
            raise ProfileStoreError("Profile ID already exists.")
        self._save([*self.profiles, profile])

    def update(self, profile: ConnectionProfile) -> None:
        if not any(existing.id == profile.id for existing in self.profiles):
            raise KeyError(profile.id)
        updated = replace(profile, updated_at=_timestamp())
        self._save([updated if item.id == profile.id else item for item in self.profiles])

    def delete(self, identifier: str) -> None:
        filtered = [profile for profile in self.profiles if profile.id != identifier]
        if len(filtered) == len(self.profiles):
            raise KeyError(identifier)
        self._save(filtered)

    def search(
        self, query: str = "", *, kind: ProfileKind | None = None, favorites_only: bool = False
    ) -> tuple[ConnectionProfile, ...]:
        needle = query.casefold().strip()
        return tuple(
            profile
            for profile in self.profiles
            if (kind is None or profile.kind == kind)
            and (not favorites_only or profile.favorite)
            and (
                not needle
                or needle in profile.name.casefold()
                or any(needle in tag.casefold() for tag in profile.tags)
            )
        )

    def _save(self, profiles: list[ConnectionProfile]) -> None:
        checked = tuple(_parse_profile(_profile_json(profile)) for profile in profiles)
        payload = json.dumps(
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "profiles": [_profile_json(p) for p in checked],
            },
            ensure_ascii=False,
            indent=2,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".profiles-", suffix=".tmp", dir=self.path.parent)
        temporary = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                backup = self.path.with_suffix(self.path.suffix + ".bak")
                if backup.exists():
                    backup = self.path.with_name(
                        f"{self.path.name}.{_timestamp().replace(':', '-')}.bak"
                    )
                original = self.path.read_bytes()
                with backup.open("xb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != "nt":
                directory_fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
        self.profiles = list(checked)


def duplicate_profile(profile: ConnectionProfile, *, name: str | None = None) -> ConnectionProfile:
    now = _timestamp()
    return replace(
        profile,
        id=uuid4().hex,
        name=name.strip() if isinstance(name, str) and name.strip() else f"{profile.name} copy",
        favorite=False,
        created_at=now,
        updated_at=now,
    )
