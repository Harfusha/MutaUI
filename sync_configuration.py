"""Metadata and proposal-only model for native sync configuration."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutaui.adapters.yaml_config import parse_yaml_bytes


@dataclass(frozen=True, slots=True)
class SyncConfigField:
    key: str
    path: tuple[str, ...]
    label: str
    help_short: str
    help_full: str
    recommended: str
    impact: str
    options: tuple[str, ...] = ()
    endpoint: str | None = None
    validation: str = "yaml"
    support_status: str = "requires capability verification"


@dataclass(frozen=True, slots=True)
class SyncConfigRow:
    key: str
    label: str
    present: bool
    current_value: Any
    origin: str
    editable_via_replacement: bool
    impact: str
    support_status: str
    proposed_value: Any = None
    endpoint: str | None = None


@dataclass(frozen=True, slots=True)
class EffectiveSessionConfiguration:
    valid: bool
    values: tuple[tuple[str, Any, str], ...] = ()
    source_path: str | None = None
    error: str = ""

    def as_mapping(self) -> dict[str, Any]:
        return {key: value for key, value, _origin in self.values}

    def origin_for(self, key: str) -> str | None:
        return next((origin for field, _value, origin in self.values if field == key), None)


def build_effective_sync_configuration(
    global_yaml: bytes | None,
    command_arguments: Sequence[str],
    *,
    source_path: str | None = None,
) -> EffectiveSessionConfiguration:
    """Merge known global sync defaults and wizard CLI overrides for a new session."""
    defaults: dict[str, Any] = {}
    use_global_configuration = "--no-global-configuration" not in command_arguments
    if global_yaml is not None and use_global_configuration:
        parsed = parse_yaml_bytes(global_yaml, source_path=source_path)
        if not parsed.valid:
            return EffectiveSessionConfiguration(False, source_path=source_path, error=parsed.error)
        document = parsed.document or {}
        sync = document.get("sync", {})
        if not isinstance(sync, Mapping):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Global `sync` configuration must be a mapping.",
            )
        raw_defaults = sync.get("defaults", {})
        if not isinstance(raw_defaults, Mapping):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Global `sync.defaults` configuration must be a mapping.",
            )
        raw_ignore = raw_defaults.get("ignore", {})
        if not isinstance(raw_ignore, Mapping):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Global `sync.defaults.ignore` configuration must be a mapping.",
            )
        raw_paths = raw_ignore.get("paths", [])
        if not isinstance(raw_paths, list) or any(not isinstance(item, str) for item in raw_paths):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Global `sync.defaults.ignore.paths` must be a list of strings.",
            )

        def flatten(prefix: str, value: Any) -> None:
            if isinstance(value, Mapping):
                if not value and prefix:
                    defaults[prefix] = {}
                    return
                if not value:
                    return
                for nested_key, nested_value in value.items():
                    if not isinstance(nested_key, str):
                        raise ValueError("Global sync configuration keys must be strings.")
                    flatten(f"{prefix}.{nested_key}" if prefix else nested_key, nested_value)
            else:
                defaults[prefix] = value

        try:
            flatten("", raw_defaults)
        except ValueError as exc:
            return EffectiveSessionConfiguration(False, source_path=source_path, error=str(exc))

    overrides: dict[str, Any] = {}
    command_ignore_paths: list[str] = []
    for argument in command_arguments:
        if argument.startswith("--mode="):
            overrides["mode"] = argument.partition("=")[2]
        elif argument.startswith("--watch-mode="):
            overrides["watch.mode"] = argument.partition("=")[2]
        elif argument.startswith("--watch-polling-interval="):
            value = argument.partition("=")[2]
            try:
                overrides["watch.pollingInterval"] = int(value)
            except ValueError:
                return EffectiveSessionConfiguration(
                    False, source_path=source_path, error="CLI polling interval must be an integer."
                )
        elif argument.startswith("--scan-mode="):
            overrides["scanMode"] = argument.partition("=")[2]
        elif argument.startswith("--ignore="):
            command_ignore_paths.append(argument.partition("=")[2])
        elif argument == "--ignore-vcs":
            overrides["ignore.vcs"] = True
        elif argument == "--no-ignore-vcs":
            overrides["ignore.vcs"] = False

    values = dict(defaults)
    origins = {key: "global config" for key in defaults}
    values.update(overrides)
    origins.update({key: "command line" for key in overrides})
    if command_ignore_paths:
        inherited_paths = values.get("ignore.paths", [])
        if not isinstance(inherited_paths, list) or any(
            not isinstance(item, str) for item in inherited_paths
        ):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Inherited `ignore.paths` must be a list of strings.",
            )
        values["ignore.paths"] = [*inherited_paths, *command_ignore_paths]
        origins["ignore.paths"] = (
            "global config + command line (appended)" if inherited_paths else "command line"
        )

    rows = tuple((key, value, origins[key]) for key, value in values.items())
    return EffectiveSessionConfiguration(True, rows, source_path)


def load_effective_sync_configuration(
    global_config_path: str | Path,
    command_arguments: Sequence[str],
) -> EffectiveSessionConfiguration:
    path = Path(global_config_path).expanduser()
    try:
        source = path.read_bytes()
    except FileNotFoundError:
        source = None
    except OSError as exc:
        return EffectiveSessionConfiguration(
            False,
            source_path=str(path),
            error=f"Could not read global Mutagen configuration: {exc.strerror or type(exc).__name__}.",
        )
    return build_effective_sync_configuration(source, command_arguments, source_path=str(path))


def build_effective_forward_configuration(
    global_yaml: bytes | None,
    command_arguments: Sequence[str],
    *,
    source_path: str | None = None,
) -> EffectiveSessionConfiguration:
    """Show global forward defaults for a new forwarding session."""
    defaults: dict[str, Any] = {}
    if global_yaml is not None and "--no-global-configuration" not in command_arguments:
        parsed = parse_yaml_bytes(global_yaml, source_path=source_path)
        if not parsed.valid:
            return EffectiveSessionConfiguration(False, source_path=source_path, error=parsed.error)
        document = parsed.document or {}
        forward = document.get("forward", {})
        if not isinstance(forward, Mapping):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Global `forward` configuration must be a mapping.",
            )
        raw_defaults = forward.get("defaults", {})
        if not isinstance(raw_defaults, Mapping):
            return EffectiveSessionConfiguration(
                False,
                source_path=source_path,
                error="Global `forward.defaults` configuration must be a mapping.",
            )

        def flatten(prefix: str, value: Any) -> None:
            if isinstance(value, Mapping):
                for nested_key, nested_value in value.items():
                    if not isinstance(nested_key, str):
                        raise ValueError("Global forward configuration keys must be strings.")
                    flatten(f"{prefix}.{nested_key}" if prefix else nested_key, nested_value)
            else:
                defaults[prefix] = value

        try:
            flatten("", raw_defaults)
        except ValueError as exc:
            return EffectiveSessionConfiguration(False, source_path=source_path, error=str(exc))

    values = tuple((key, value, "global config") for key, value in defaults.items())
    return EffectiveSessionConfiguration(True, values, source_path)


def load_effective_forward_configuration(
    global_config_path: str | Path,
    command_arguments: Sequence[str],
) -> EffectiveSessionConfiguration:
    path = Path(global_config_path).expanduser()
    try:
        source = path.read_bytes()
    except FileNotFoundError:
        source = None
    except OSError as exc:
        return EffectiveSessionConfiguration(
            False,
            source_path=str(path),
            error=f"Could not read global Mutagen configuration: {exc.strerror or type(exc).__name__}.",
        )
    return build_effective_forward_configuration(source, command_arguments, source_path=str(path))


def _field(
    key: str,
    path: tuple[str, ...],
    label: str,
    help_short: str,
    help_full: str,
    recommended: str,
    impact: str,
    *,
    options: tuple[str, ...] = (),
    endpoint: str | None = None,
    validation: str = "yaml",
) -> SyncConfigField:
    return SyncConfigField(
        key, path, label, help_short, help_full, recommended, impact, options, endpoint, validation
    )


_COMMON_FIELDS = (
    _field(
        "mode",
        ("mode",),
        "Sync mode",
        "How changes propagate.",
        "One-way replica may overwrite destination data. Existing sessions require replacement.",
        "two-way-safe",
        "Changes can overwrite data.",
        options=("two-way-safe", "two-way-resolved", "one-way-safe", "one-way-replica"),
    ),
    _field(
        "watch.mode",
        ("watch", "mode"),
        "Watch mode",
        "How Mutagen detects file changes.",
        "Polling can raise CPU and I/O use. Existing sessions require replacement.",
        "portable",
        "Frequent polling raises resource use.",
        options=("portable", "force-poll", "no-watch"),
    ),
    _field(
        "watch.pollingInterval",
        ("watch", "pollingInterval"),
        "Polling interval",
        "Seconds between polling scans.",
        "Must be positive; smaller values can raise CPU and I/O use.",
        "Mutagen default",
        "Low values raise resource use.",
        validation="positive-int",
    ),
    _field(
        "scanMode",
        ("scanMode",),
        "Scan mode",
        "How file trees are scanned.",
        "Full scans can cost more time and I/O than accelerated scans.",
        "accelerated",
        "Full scans can add substantial I/O.",
        options=("accelerated", "full"),
    ),
    _field(
        "probeMode",
        ("probeMode",),
        "Probe mode",
        "Whether endpoint capabilities are probed.",
        "Assuming capabilities can skip checks and may be incompatible with an endpoint.",
        "probe",
        "Assume mode can skip safety checks.",
        options=("probe", "assume"),
    ),
    _field(
        "stageMode",
        ("stageMode",),
        "Staging mode",
        "Where file contents are staged.",
        "Filesystem choice affects temporary storage and available space.",
        "mutagen",
        "Staging uses disk space.",
        options=("mutagen", "neighboring", "internal"),
    ),
    _field(
        "symbolicLink.mode",
        ("symlink", "mode"),
        "Symbolic link mode",
        "How symbolic links are represented.",
        "Available behavior depends on operating system and endpoint.",
        "portable",
        "Native link behavior varies by platform.",
        options=("ignore", "portable", "posix-raw"),
    ),
    _field(
        "ignore.paths",
        ("ignore", "paths"),
        "Ignore paths",
        "Ordered patterns excluded from sync.",
        "Pattern order, negation and syntax affect which files Mutagen considers.",
        "No custom paths",
        "Incorrect rules can omit data.",
        validation="string-list",
    ),
    _field(
        "ignore.vcs",
        ("ignore", "vcs"),
        "Ignore VCS metadata",
        "Ignore common version control data.",
        "This can exclude repository metadata such as `.git`.",
        "Mutagen default",
        "Ignored metadata is not synchronized.",
        validation="bool",
    ),
    _field(
        "ignore.syntax",
        ("ignore", "syntax"),
        "Ignore syntax",
        "Pattern language for ignore paths.",
        "Mutagen and Docker syntax are version-dependent; verify the installed CLI first.",
        "Detected by Mutagen",
        "Different syntax can change exclusions.",
        options=("mutagen", "docker"),
    ),
    _field(
        "permissions.defaultFileMode",
        ("permissions", "defaultFileMode"),
        "Default file mode",
        "POSIX mode for new files.",
        "POSIX permissions may not map directly to Windows or remote filesystems.",
        "Mutagen default",
        "May broaden or restrict access.",
        validation="octal-mode",
    ),
    _field(
        "permissions.defaultDirectoryMode",
        ("permissions", "defaultDirectoryMode"),
        "Default directory mode",
        "POSIX mode for new directories.",
        "POSIX permissions may not map directly to Windows or remote filesystems.",
        "Mutagen default",
        "May broaden or restrict access.",
        validation="octal-mode",
    ),
    _field(
        "permissions.defaultOwner",
        ("permissions", "defaultOwner"),
        "Default owner",
        "Owner applied to new entries where supported.",
        "Owner names depend on endpoint and platform.",
        "Mutagen default",
        "Can change ownership access.",
        validation="nonempty-string",
    ),
    _field(
        "permissions.defaultGroup",
        ("permissions", "defaultGroup"),
        "Default group",
        "Group applied to new entries where supported.",
        "Group names depend on endpoint and platform.",
        "Mutagen default",
        "Can change group access.",
        validation="nonempty-string",
    ),
    _field(
        "maxEntryCount",
        ("maxEntryCount",),
        "Maximum entries",
        "Upper bound on scanned entries.",
        "Zero means unlimited; large repositories may require substantial scan work.",
        "Mutagen default",
        "A low limit can prevent complete synchronization.",
        validation="nonnegative-int",
    ),
    _field(
        "maxStagingFileSize",
        ("maxStagingFileSize",),
        "Maximum staging file size",
        "Upper bound for a staged file in bytes.",
        "Zero means unlimited.",
        "Mutagen default",
        "A low limit can prevent large files from synchronizing.",
        validation="nonnegative-int",
    ),
    _field(
        "compression.algorithm",
        ("compression", "algorithm"),
        "Compression algorithm",
        "Compression applied to transferred data.",
        "Choices vary by Mutagen version and endpoint.",
        "Mutagen default",
        "Compression trades CPU for network use.",
    ),
    _field(
        "hash.algorithm",
        ("hash", "algorithm"),
        "Hash algorithm",
        "Algorithm used to identify content.",
        "Choices vary by Mutagen version and endpoint.",
        "Mutagen default",
        "Hash choice affects CPU cost and compatibility.",
    ),
)

_ENDPOINT_FIELDS = tuple(
    _field(
        f"{side.lower()}.{name}",
        (side.lower(), *path),
        f"{side} {label}",
        short,
        f"{full} Endpoint-specific overrides must be supported by the installed Mutagen version.",
        "Inherited or Mutagen default",
        impact,
        options=options,
        endpoint=side,
        validation=validation,
    )
    for side in ("ALPHA", "BETA")
    for name, path, label, short, full, impact, options, validation in (
        (
            "watch.mode",
            ("watch", "mode"),
            "watch mode",
            "Endpoint file-change detection.",
            "Polling can raise CPU and I/O use.",
            "Frequent polling raises resource use.",
            ("portable", "force-poll", "no-watch"),
            "yaml",
        ),
        (
            "watch.pollingInterval",
            ("watch", "pollingInterval"),
            "polling interval",
            "Endpoint polling interval in seconds.",
            "Smaller values increase polling work.",
            "Low values raise resource use.",
            (),
            "positive-int",
        ),
        (
            "scanMode",
            ("scanMode",),
            "scan mode",
            "Endpoint tree-scan mode.",
            "Full scans can cost more time and I/O.",
            "Full scans can add substantial I/O.",
            ("accelerated", "full"),
            "yaml",
        ),
        (
            "probeMode",
            ("probeMode",),
            "probe mode",
            "Endpoint capability-probe behavior.",
            "Assume mode can skip checks.",
            "Assume mode can skip safety checks.",
            ("probe", "assume"),
            "yaml",
        ),
        (
            "stageMode",
            ("stageMode",),
            "staging mode",
            "Endpoint staging location.",
            "Filesystem choice affects staging space.",
            "Staging uses disk space.",
            ("mutagen", "neighboring", "internal"),
            "yaml",
        ),
        (
            "permissions.defaultFileMode",
            ("permissions", "defaultFileMode"),
            "default file mode",
            "POSIX mode for files at this endpoint.",
            "Platform and endpoint may limit permission handling.",
            "Can broaden or restrict access.",
            (),
            "octal-mode",
        ),
        (
            "permissions.defaultDirectoryMode",
            ("permissions", "defaultDirectoryMode"),
            "default directory mode",
            "POSIX mode for directories at this endpoint.",
            "Platform and endpoint may limit permission handling.",
            "Can broaden or restrict access.",
            (),
            "octal-mode",
        ),
        (
            "permissions.defaultOwner",
            ("permissions", "defaultOwner"),
            "default owner",
            "Owner applied at this endpoint where supported.",
            "Owner names depend on endpoint platform.",
            "Can change access ownership.",
            (),
            "nonempty-string",
        ),
        (
            "permissions.defaultGroup",
            ("permissions", "defaultGroup"),
            "default group",
            "Group applied at this endpoint where supported.",
            "Group names depend on endpoint platform.",
            "Can change access ownership.",
            (),
            "nonempty-string",
        ),
        (
            "compression.algorithm",
            ("compression", "algorithm"),
            "compression algorithm",
            "Compression choice for this endpoint.",
            "Choices vary by Mutagen version and endpoint.",
            "Trades CPU for network use.",
            (),
            "yaml",
        ),
        (
            "hash.algorithm",
            ("hash", "algorithm"),
            "hash algorithm",
            "Content hash choice for this endpoint.",
            "Choices vary by Mutagen version and endpoint.",
            "Affects CPU cost and compatibility.",
            (),
            "yaml",
        ),
    )
)

SYNC_CONFIG_FIELDS = _COMMON_FIELDS + _ENDPOINT_FIELDS
_FIELDS_BY_KEY = {field.key: field for field in SYNC_CONFIG_FIELDS}
_MISSING = object()


def render_sync_reference() -> str:
    lines = [
        "## Native sync configuration proposals",
        "",
        "Current values are read-only session exports. Proposed values stay in MutaUI settings;",
        "they do not modify running Mutagen sessions. Verify each field against the installed CLI before replacement.",
        "",
        "| Field | Path | Recommended | Support | Impact | Help |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for field in SYNC_CONFIG_FIELDS:
        help_text = field.help_short.replace("|", "\\|")
        impact = field.impact.replace("|", "\\|")
        path = ".".join(field.path).replace("|", "\\|")
        lines.append(
            f"| `{field.key}` | `{path}` | {field.recommended} | {field.support_status} | {impact} | {help_text} |"
        )
    return "\n".join(lines) + "\n"


def _lookup(source: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = source
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def session_configuration_rows(
    session: Mapping[str, Any], proposals: Mapping[str, Any] | None = None
) -> tuple[SyncConfigRow, ...]:
    proposed = proposals or {}
    rows = []
    for field in SYNC_CONFIG_FIELDS:
        value = _lookup(session, field.path)
        has_proposal = field.key in proposed
        rows.append(
            SyncConfigRow(
                key=field.key,
                label=field.label,
                present=value is not _MISSING,
                current_value=None if value is _MISSING else copy.deepcopy(value),
                origin=(
                    "Mutagen session export; inheritance origin unknown"
                    if value is not _MISSING
                    else "Not reported by Mutagen export"
                ),
                editable_via_replacement=True,
                impact=field.impact,
                support_status=field.support_status,
                proposed_value=copy.deepcopy(proposed[field.key]) if has_proposal else None,
                endpoint=field.endpoint,
            )
        )
    return tuple(rows)


class SyncConfigurationDraft:
    """A local proposal only; it never mutates or reconfigures a Mutagen session."""

    def __init__(self, session: Mapping[str, Any]) -> None:
        self.session = copy.deepcopy(dict(session))
        self.proposals: dict[str, Any] = {}

    def propose(self, key: str, value: Any) -> None:
        field = _FIELDS_BY_KEY.get(key)
        if field is None:
            raise ValueError(f"Unsupported sync configuration field: {key}")
        _validate(field, value)
        self.proposals[key] = copy.deepcopy(value)

    def rows(self) -> tuple[SyncConfigRow, ...]:
        return session_configuration_rows(self.session, self.proposals)


def validate_sync_proposal(key: str, value: Any) -> Any:
    field = _FIELDS_BY_KEY.get(key)
    if field is None:
        raise ValueError(f"Unsupported sync configuration field: {key}")
    _validate(field, value)
    return copy.deepcopy(value)


def _validate(field: SyncConfigField, value: Any) -> None:
    if field.options and value not in field.options:
        raise ValueError(f"{field.label} must be one of: {', '.join(field.options)}")
    if field.validation == "positive-int" and (
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
    ):
        raise ValueError(f"{field.label} must be a positive integer")
    if field.validation == "nonnegative-int" and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise ValueError(f"{field.label} must be a non-negative integer")
    if field.validation == "bool" and not isinstance(value, bool):
        raise ValueError(f"{field.label} must be true or false")
    if field.validation == "string-list" and (
        not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value)
    ):
        raise ValueError(f"{field.label} must be a list of strings")
    if field.validation == "octal-mode" and (
        not isinstance(value, str) or not re.fullmatch(r"0?[0-7]{3,4}", value)
    ):
        raise ValueError(f"{field.label} must be a three- or four-digit octal string")
    if field.validation == "nonempty-string" and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field.label} must be a non-empty string")
