"""Capability checked rendering of reviewed sync creation arguments."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from sync_configuration import SYNC_CONFIG_FIELDS, validate_sync_proposal

_FIELD_FLAGS = {
    "mode": "--mode",
    "watch.mode": "--watch-mode",
    "watch.pollingInterval": "--watch-polling-interval",
    "scanMode": "--scan-mode",
    "probeMode": "--probe-mode",
    "stageMode": "--stage-mode",
    "symbolicLink.mode": "--symlink-mode",
    "ignore.syntax": "--ignore-syntax",
    "ignore.paths": "--ignore",
    "maxEntryCount": "--max-entry-count",
    "maxStagingFileSize": "--max-staging-file-size",
    "permissions.defaultFileMode": "--default-file-mode",
    "permissions.defaultDirectoryMode": "--default-directory-mode",
    "permissions.defaultOwner": "--default-owner",
    "permissions.defaultGroup": "--default-group",
    "compression.algorithm": "--compression",
    "hash.algorithm": "--hash",
}
_BOOL_FLAGS = {
    "ignore.vcs": ("--ignore-vcs", "--no-ignore-vcs"),
}
_VERSIONED_ENUM_FIELDS = {"compression.algorithm", "hash.algorithm"}


def render_sync_replacement_arguments(
    original: Sequence[str], proposals: Mapping[str, object], help_text: str
) -> tuple[str, ...]:
    """Overlay supported proposals onto exact original argv, failing closed."""
    if len(original) < 4 or tuple(original[:2]) != ("sync", "create"):
        raise ValueError("Exact original sync create arguments are required.")
    if any(not isinstance(arg, str) or not arg or "\x00" in arg for arg in original):
        raise ValueError("Original create arguments are malformed.")
    if any(arg.casefold() in {"--all", "--all=true"} for arg in original):
        raise ValueError("Broad session targeting cannot be replayed.")
    known = {field.key: field for field in SYNC_CONFIG_FIELDS}
    unknown = set(proposals) - known.keys()
    if unknown:
        raise ValueError("Unknown proposed configuration fields: " + ", ".join(sorted(unknown)))
    available = set(re.findall(r"--[a-zA-Z][a-zA-Z0-9-]*", help_text))
    normalized_help = re.sub(r"\s+", " ", help_text)
    result = list(original)
    for key, value in proposals.items():
        value = validate_sync_proposal(key, value)
        field = known[key]
        if key in _BOOL_FLAGS:
            positive, negative = _BOOL_FLAGS[key]
            if positive not in available or negative not in available:
                raise ValueError(
                    f"Installed Mutagen does not document both {positive} and {negative}."
                )
            result = [arg for arg in result if arg.split("=", 1)[0] not in (positive, negative)]
            if not isinstance(value, bool):
                raise ValueError(f"{key} proposal must be boolean.")
            result.append(positive if value else negative)
            continue

        endpoint = None
        base_key = key
        if key.startswith(("alpha.", "beta.")):
            endpoint, base_key = key.split(".", 1)
        flag = _FIELD_FLAGS[base_key]
        if endpoint is not None:
            flag += "-" + endpoint
        if flag not in available:
            raise ValueError(f"Installed Mutagen help does not document {flag}.")
        if isinstance(value, str):
            choices = _documented_choices(normalized_help, flag)
            if (field.options or base_key in _VERSIONED_ENUM_FIELDS) and not choices:
                raise ValueError(
                    f"Installed Mutagen help does not document supported values for {flag}."
                )
            if choices and value not in choices:
                raise ValueError(f"Installed Mutagen help does not support {value!r} for {flag}.")
        result = [arg for arg in result if arg.split("=", 1)[0] != flag]
        if key == "ignore.paths":
            if not isinstance(value, (list, tuple)) or any(
                not isinstance(item, str) or not item or "\x00" in item for item in value
            ):
                raise ValueError("Ignore path proposal must be a list of nonempty strings.")
            result.extend(f"{flag}={item}" for item in value)
        elif isinstance(value, (str, int)) and not isinstance(value, bool):
            result.append(f"{flag}={value}")
        else:
            raise ValueError(f"{key} proposal has an unsupported value type.")
    return tuple(result)


def _documented_choices(help_text: str, flag: str) -> frozenset[str]:
    """Read an optional pipe-delimited choice list from the selected help entry."""
    option = re.search(rf"(?<![A-Za-z0-9-]){re.escape(flag)}(?![A-Za-z0-9-])", help_text)
    if option is None:
        return frozenset()
    remainder = help_text[option.end() :]
    next_flag = re.search(r"\s--[a-zA-Z][a-zA-Z0-9-]*\b", remainder)
    section = remainder[: next_flag.start()] if next_flag else remainder
    for match in re.finditer(r"\(([^()]*)\)", section):
        values = match.group(1).split("|")
        if len(values) > 1 and all(value.strip() for value in values):
            return frozenset(value.strip() for value in values)
    return frozenset()
