"""Proposal-only metadata for native forwarding session configuration."""

from __future__ import annotations

import copy
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ForwardConfigField:
    key: str
    path: tuple[str, ...]
    label: str
    help_short: str
    help_full: str
    recommended: str
    impact: str
    validation: str = "string"
    options: tuple[str, ...] = ()
    endpoint: str | None = None
    support_status: str = "requires CLI and platform capability verification"


@dataclass(frozen=True, slots=True)
class ForwardConfigRow:
    key: str
    label: str
    present: bool
    current_value: Any
    origin: str
    impact: str
    support_status: str
    proposed_value: Any = None
    endpoint: str | None = None


_SOCKET_FIELDS = (
    (
        "overwriteMode",
        "Socket overwrite mode",
        "How an existing socket path is handled.",
        "Overwrite can replace an existing filesystem entry; never deletes it silently.",
        "leave",
        "Overwrite may affect existing paths.",
        "choice",
        ("leave", "overwrite"),
    ),
    (
        "owner",
        "Socket owner",
        "Owner assigned to a Unix socket where supported.",
        "Owner names and support depend on Mutagen version, endpoint and operating system.",
        "Mutagen default",
        "Can change access ownership.",
        "string",
        (),
    ),
    (
        "group",
        "Socket group",
        "Group assigned to a Unix socket where supported.",
        "Group names and support depend on Mutagen version, endpoint and operating system.",
        "Mutagen default",
        "Can change access ownership.",
        "string",
        (),
    ),
    (
        "permissionMode",
        "Socket permission mode",
        "POSIX mode for a Unix socket.",
        "Permission modes may be unsupported on Windows and some endpoints.",
        "Mutagen default",
        "May broaden or restrict access.",
        "octal-mode",
        (),
    ),
)

FORWARD_CONFIG_FIELDS = tuple(
    ForwardConfigField(
        key=f"{side.lower()}.socket.{native_key}",
        path=(f"configuration{side.title()}", "socket", native_key),
        label=f"{side.title()} {label.removeprefix('Socket ')}",
        help_short=short,
        help_full=full,
        recommended=recommended,
        impact=impact,
        validation=validation,
        options=options,
        endpoint=side.upper(),
    )
    for side in ("source", "destination")
    for native_key, label, short, full, recommended, impact, validation, options in _SOCKET_FIELDS
)
_FIELDS_BY_KEY = {field.key: field for field in FORWARD_CONFIG_FIELDS}
_MISSING = object()


def is_unix_forward_endpoint(endpoint: str) -> bool:
    """Recognize Mutagen Unix socket endpoint addresses, including remote transports."""
    return bool(re.search(r"(?:^|:)unix:", endpoint.strip(), flags=re.IGNORECASE))


def local_unix_socket_entry_type(endpoint: str) -> str | None:
    """Inspect a local Unix socket path without following or modifying its final entry."""
    value = endpoint.strip()
    if not value.lower().startswith("unix:"):
        return None
    path = Path(value[5:]).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unavailable"
    if stat.S_ISLNK(mode):
        return "symbolic link"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "special filesystem entry"


def render_forward_reference() -> str:
    lines = [
        "## Native forwarding configuration proposals",
        "",
        "Socket controls are proposal-only until installed CLI, endpoint and platform support is verified.",
        "Existing forwarding sessions are not changed by MutaUI settings.",
        "",
        "| Field | Native path | Recommended | Support | Impact | Help |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for field in FORWARD_CONFIG_FIELDS:
        path = ".".join(field.path)
        lines.append(
            f"| `{field.key}` | `{path}` | {field.recommended} | {field.support_status} | "
            f"{field.impact.replace('|', r'\\|')} | {field.help_short.replace('|', r'\\|')} |"
        )
    return "\n".join(lines) + "\n"


def _lookup(session: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = session
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def forward_configuration_rows(
    session: Mapping[str, Any], proposals: Mapping[str, Any] | None = None
) -> tuple[ForwardConfigRow, ...]:
    proposals = proposals or {}
    result = []
    for field in FORWARD_CONFIG_FIELDS:
        value = _lookup(session, field.path)
        origin = "Mutagen session export; inheritance origin unknown"
        if value is _MISSING:
            shared_value = _lookup(session, ("socket", field.path[-1]))
            if shared_value is not _MISSING:
                value = shared_value
                origin = "Mutagen shared socket value; endpoint inheritance origin unknown"
        if value is _MISSING:
            origin = "Not reported by Mutagen export"
        result.append(
            ForwardConfigRow(
                key=field.key,
                label=field.label,
                present=value is not _MISSING,
                current_value=None if value is _MISSING else copy.deepcopy(value),
                origin=origin,
                impact=field.impact,
                support_status=field.support_status,
                proposed_value=copy.deepcopy(proposals[field.key])
                if field.key in proposals
                else None,
                endpoint=field.endpoint,
            )
        )
    return tuple(result)


class ForwardConfigurationDraft:
    """Local draft only; mutation requires a separate replacement workflow."""

    def __init__(self, session: Mapping[str, Any]) -> None:
        self.session = copy.deepcopy(dict(session))
        self.proposals: dict[str, Any] = {}

    def propose(self, key: str, value: Any) -> None:
        field = _FIELDS_BY_KEY.get(key)
        if field is None:
            raise ValueError(f"Unsupported forwarding configuration field: {key}")
        _validate(field, value)
        self.proposals[key] = copy.deepcopy(value)


def validate_forward_proposal(key: str, value: Any) -> Any:
    field = _FIELDS_BY_KEY.get(key)
    if field is None:
        raise ValueError(f"Unsupported forwarding configuration field: {key}")
    _validate(field, value)
    return copy.deepcopy(value)


def _validate(field: ForwardConfigField, value: Any) -> None:
    if field.validation == "choice" and value not in field.options:
        raise ValueError(f"{field.label} must be one of: {', '.join(field.options)}")
    if field.validation == "octal-mode" and (
        not isinstance(value, str) or not re.fullmatch(r"0?[0-7]{3,4}", value)
    ):
        raise ValueError(f"{field.label} must be a three- or four-digit octal string")
    if field.validation == "string" and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field.label} must be a non-empty string")
