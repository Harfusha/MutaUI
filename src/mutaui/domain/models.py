"""Typed domain objects shared by UI, native adapters, and persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Literal, cast

SessionKind = Literal["sync", "forward"]
RiskTier = Literal["R0", "R1", "R2", "R3"]


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return cast(Mapping[str, object], _freeze(value))


@dataclass(frozen=True, slots=True)
class MutagenInstall:
    binary_path: str
    version: str | None
    source: str
    fingerprint: str | None
    capability_set: frozenset[str]
    last_checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class Endpoint:
    kind: str
    spec: str
    host: str | None = None
    port: int | None = None
    user: str | None = None
    path: str | None = None
    protocol: str | None = None
    native_fields: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "native_fields", _freeze_mapping(self.native_fields))


@dataclass(frozen=True, slots=True)
class SessionIdentity:
    kind: SessionKind
    identifier: str
    name: str
    labels: Mapping[str, str] = field(default_factory=dict)
    project_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("Session identifier is required")
        object.__setattr__(self, "labels", MappingProxyType(dict(self.labels)))


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    identity: SessionIdentity
    native_config: Mapping[str, object]
    alpha_or_source: Endpoint | None
    beta_or_destination: Endpoint | None
    state: str
    conflicts: tuple[object, ...]
    problems: tuple[object, ...]
    counters: Mapping[str, int | float | None]
    measured_at: datetime
    stale_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "native_config", _freeze_mapping(self.native_config))
        object.__setattr__(self, "conflicts", _freeze(self.conflicts))
        object.__setattr__(self, "problems", _freeze(self.problems))
        object.__setattr__(self, "counters", _freeze_mapping(self.counters))


@dataclass(frozen=True, slots=True)
class GlobalConfig:
    raw_yaml: str
    parsed_known: Mapping[str, object]
    unknown_tree: Mapping[str, object]
    file_hash: str | None
    effective_defaults: Mapping[str, object]
    read_only: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "parsed_known", _freeze_mapping(self.parsed_known))
        object.__setattr__(self, "unknown_tree", _freeze_mapping(self.unknown_tree))
        object.__setattr__(self, "effective_defaults", _freeze_mapping(self.effective_defaults))


@dataclass(frozen=True, slots=True)
class SessionConfiguration:
    common: Mapping[str, object]
    endpoint_overrides: Mapping[str, object]
    provenance_map: Mapping[str, str]
    unknown_fields: Mapping[str, object]

    def __post_init__(self) -> None:
        for key in ("common", "endpoint_overrides", "provenance_map", "unknown_fields"):
            object.__setattr__(self, key, _freeze_mapping(getattr(self, key)))


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    id: str
    display_name: str
    endpoint_specs: tuple[str, ...]
    default_settings: Mapping[str, object]
    ssh_profile_ref: str | None
    tags: tuple[str, ...]
    created: datetime
    last_used: datetime | None
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "default_settings", _freeze_mapping(self.default_settings))


@dataclass(frozen=True, slots=True)
class ProjectDefinition:
    path: str
    source_hash: str
    native_project_id: str | None
    parsed_known: Mapping[str, object]
    unknown_tree: Mapping[str, object]
    hooks: tuple[object, ...]
    commands: tuple[object, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parsed_known", _freeze_mapping(self.parsed_known))
        object.__setattr__(self, "unknown_tree", _freeze_mapping(self.unknown_tree))
        object.__setattr__(self, "hooks", _freeze(self.hooks))
        object.__setattr__(self, "commands", _freeze(self.commands))


@dataclass(frozen=True, slots=True)
class DiagnosticIssue:
    code: str
    severity: str
    confidence: float
    evidence: tuple[object, ...]
    cause: str
    suggested_actions: tuple[str, ...]
    can_auto_fix: bool
    source_version: str | None
    certainty: Literal["confirmed", "suspected"] = "suspected"
    explanation: str = ""
    technical_detail: str = ""
    article_url: str | None = None
    session_identifier: str | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))


@dataclass(frozen=True, slots=True)
class ActionPlan:
    id: str
    kind: str
    exact_targets: tuple[str, ...]
    before_state: Mapping[str, object]
    commands: tuple[tuple[str, ...], ...]
    preconditions: tuple[str, ...]
    risk_tier: RiskTier
    affected_scope: str
    backup_plan: str | None
    rollback_ability: bool
    confirmation_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "before_state", _freeze_mapping(self.before_state))


@dataclass(frozen=True, slots=True)
class ActionAuditEvent:
    id: str
    plan_id: str
    requested_at: datetime
    completed_at: datetime | None
    requested_by: str
    result: str
    error: str | None
    redacted_details: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "redacted_details", _freeze_mapping(self.redacted_details))


@dataclass(frozen=True, slots=True)
class Capability:
    value: str
    supported: bool
    reason: str | None = None
    minimum_version: str | None = None
    platform: str | None = None


@dataclass(frozen=True, slots=True)
class MetricPoint:
    timestamp: datetime
    value: float | None
    source: str
    sampled_at: datetime
    freshness: Literal["fresh", "stale", "unknown"]
