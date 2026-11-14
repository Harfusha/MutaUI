"""Validated portable import/export for local MutaUI preferences and profiles."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from connection_profiles import (
    ConnectionProfile,
    ConnectionProfileStore,
    ProfileStoreError,
    _parse_profile,
    _profile_json,
    load_profile_store,
)
from ignore_presets import IgnorePresetError, parse_preset_record, preset_to_record
from settings import validate_settings

PORTABLE_SCHEMA_VERSION = 1
MAX_BUNDLE_BYTES = 5 * 1024 * 1024
PREFERENCE_KEYS = frozenset(
    {
        "theme",
        "language",
        "new_sync_profile",
        "favorites",
        "alerts",
        "cpu_alert_on",
        "cpu_alert_limit",
        "ram_alert_on",
        "ram_alert_limit",
        "alert_hold",
        "tray",
        "eco_tray",
    }
)
_LOCAL_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|/|~[/\\])")


@dataclass(frozen=True, slots=True)
class BundleBuild:
    text: str
    valid: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BundleLoad:
    data: dict[str, Any]
    valid: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileImportPreview:
    profile: ConnectionProfile
    action: Literal["create", "merge", "skip", "conflict"]
    reason: str


class PortableBundleError(ValueError):
    """Portable bundle is invalid, unsupported, or unsafe to apply."""


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sanitize_records(
    records: list[dict[str, Any]], warnings: list[str], *, include_local_paths: bool
) -> list[dict[str, Any]]:
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError("Portable records must be a bounded list.")
    blocked = re.compile(
        r"secret|password|token|credential|authorization|private.?key|key.?contents?", re.I
    )

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for name, item in value.items():
                if blocked.search(str(name)):
                    warnings.append(f"Sensitive field '{name}' was excluded from export.")
                else:
                    result[str(name)] = clean(item)
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):
            value = re.sub(r"(://[^:/@\s]+):[^@/\s]+@", r"\1:[redacted]@", value)
            if _LOCAL_PATH.match(value) and not include_local_paths:
                warnings.append("An absolute local path in portable metadata was redacted.")
                return "[redacted-local-path]"
            return value
        if value is None or type(value) in {bool, int, float}:
            return value
        raise ValueError("Portable metadata contains an unsupported value.")

    if any(not isinstance(record, dict) for record in records):
        raise ValueError("Portable metadata records must be objects.")
    return [clean(record) for record in records]


def _redact_endpoint(value: str, *, include_local_paths: bool, warnings: list[str]) -> str:
    if not include_local_paths and _LOCAL_PATH.match(value):
        warnings.append("An absolute local endpoint was replaced with [redacted-local-path].")
        return "[redacted-local-path]"
    # A URL-shaped endpoint can carry a password in userinfo. Strip only the password.
    value = re.sub(r"(://[^:/@\s]+):[^@/\s]+@", r"\1:[redacted]@", value)
    return value


def _safe_profile(
    profile: ConnectionProfile, *, include_local_paths: bool, warnings: list[str]
) -> dict[str, Any]:
    item = _profile_json(profile)
    item["endpoint_a"] = _redact_endpoint(
        item["endpoint_a"], include_local_paths=include_local_paths, warnings=warnings
    )
    item["endpoint_b"] = _redact_endpoint(
        item["endpoint_b"], include_local_paths=include_local_paths, warnings=warnings
    )
    return item


def build_bundle(
    profiles: list[ConnectionProfile] | tuple[ConnectionProfile, ...],
    settings: dict[str, Any],
    *,
    app_version: str,
    include_local_paths: bool = False,
    ignore_presets: list[dict[str, Any]] | None = None,
    project_references: list[dict[str, Any]] | None = None,
) -> BundleBuild:
    warnings: list[str] = []
    if include_local_paths:
        warnings.append("Machine-specific endpoint paths were included by explicit request.")
    safe_settings = {
        key: copy.deepcopy(settings[key]) for key in PREFERENCE_KEYS if key in settings
    }
    validated = validate_settings({"schema_version": 1, **safe_settings})
    if validated.warnings:
        return BundleBuild("", False, validated.warnings)
    safe_settings = {key: validated.values[key] for key in safe_settings}
    try:
        incoming_ignores = ignore_presets or []
        if not isinstance(incoming_ignores, list) or len(incoming_ignores) > 10000:
            raise ValueError("Portable ignore presets must be a bounded list.")
        safe_ignores = [preset_to_record(parse_preset_record(value)) for value in incoming_ignores]
        safe_projects = _sanitize_records(
            project_references or [], warnings, include_local_paths=include_local_paths
        )
    except (TypeError, ValueError) as exc:
        return BundleBuild("", False, (str(exc),))
    payload: dict[str, Any] = {
        "schema_version": PORTABLE_SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "created_with": "MutaUI",
        "app_version": app_version[:64],
        "platform": sys.platform,
        "machine_paths_included": include_local_paths,
        "items": {
            "connection_profiles": [
                _safe_profile(profile, include_local_paths=include_local_paths, warnings=warnings)
                for profile in profiles
            ],
            "preferences": safe_settings,
            "ignore_presets": safe_ignores,
            "project_references": safe_projects,
        },
    }
    payload["checksum"] = hashlib.sha256(_canonical(payload)).hexdigest()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > MAX_BUNDLE_BYTES:
        return BundleBuild("", False, ("Portable bundle exceeds the size limit.",))
    return BundleBuild(text, True, tuple(dict.fromkeys(warnings)))


def load_bundle(source: str | bytes) -> BundleLoad:
    try:
        raw_bytes = source if isinstance(source, bytes) else source.encode("utf-8")
        if len(raw_bytes) > MAX_BUNDLE_BYTES:
            raise PortableBundleError("Portable bundle exceeds the size limit.")
        payload = json.loads(raw_bytes.decode("utf-8"))
        expected = {
            "schema_version",
            "created_at",
            "created_with",
            "app_version",
            "platform",
            "machine_paths_included",
            "items",
            "checksum",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise PortableBundleError("Portable bundle has an unsupported structure.")
        version = payload["schema_version"]
        if type(version) is not int or version != PORTABLE_SCHEMA_VERSION:
            raise PortableBundleError(f"Unsupported portable schema version: {version!r}.")
        if type(payload["machine_paths_included"]) is not bool:
            raise PortableBundleError("Portable path disclosure flag is invalid.")
        checksum = payload["checksum"]
        if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise PortableBundleError("Portable bundle checksum is missing or malformed.")
        unsigned = {key: value for key, value in payload.items() if key != "checksum"}
        actual = hashlib.sha256(_canonical(unsigned)).hexdigest()
        if actual != checksum:
            raise PortableBundleError("Portable bundle checksum does not match its contents.")
        items = payload["items"]
        if not isinstance(items, dict) or set(items) != {
            "connection_profiles",
            "preferences",
            "ignore_presets",
            "project_references",
        }:
            raise PortableBundleError("Portable bundle items are invalid.")
        raw_profiles = items["connection_profiles"]
        if not isinstance(raw_profiles, list) or len(raw_profiles) > 10000:
            raise PortableBundleError("Portable profile list is invalid or too large.")
        profiles = [_parse_profile(profile) for profile in raw_profiles]
        credential_url = re.compile(r"://[^:/@\s]+:[^@/\s]+@")
        if any(
            credential_url.search(p.endpoint_a) or credential_url.search(p.endpoint_b)
            for p in profiles
        ):
            raise PortableBundleError(
                "Portable profile contains embedded credentials; redact them before import."
            )
        if not payload["machine_paths_included"] and any(
            _LOCAL_PATH.match(endpoint)
            for profile in profiles
            for endpoint in (profile.endpoint_a, profile.endpoint_b)
        ):
            raise PortableBundleError("Bundle contains an unredacted absolute local path.")
        if len({profile.id for profile in profiles}) != len(profiles):
            raise PortableBundleError("Portable profile IDs must be unique.")
        prefs = items["preferences"]
        if not isinstance(prefs, dict) or set(prefs) - PREFERENCE_KEYS:
            raise PortableBundleError("Portable preferences contain unsupported fields.")
        checked = validate_settings({"schema_version": 1, **prefs})
        if checked.warnings:
            raise PortableBundleError(
                "Portable preferences failed validation: " + "; ".join(checked.warnings)
            )
        for list_key in ("ignore_presets", "project_references"):
            value = items[list_key]
            if (
                not isinstance(value, list)
                or len(value) > 10000
                or any(not isinstance(item, dict) for item in value)
            ):
                raise PortableBundleError(f"Portable {list_key} must be a bounded list of objects.")
        if items["ignore_presets"]:
            try:
                checked_presets = [parse_preset_record(value) for value in items["ignore_presets"]]
            except IgnorePresetError as exc:
                raise PortableBundleError(f"Portable ignore preset is invalid: {exc}") from exc
            if len({preset.id for preset in checked_presets}) != len(checked_presets):
                raise PortableBundleError("Portable ignore preset IDs must be unique.")
        warnings = (
            (
                "This bundle declares absolute machine-specific paths; review profiles before importing.",
            )
            if payload["machine_paths_included"]
            else ()
        )
        return BundleLoad(payload, True, warnings)
    except (
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        KeyError,
        ProfileStoreError,
        PortableBundleError,
    ) as exc:
        return BundleLoad({}, False, (str(exc),))


def _profile_fingerprint(profile: ConnectionProfile) -> str:
    data = _profile_json(profile)
    for key in ("id", "created_at", "updated_at"):
        data.pop(key, None)
    return hashlib.sha256(_canonical(data)).hexdigest()


def preview_profile_import(
    bundle: BundleLoad, existing: list[ConnectionProfile] | tuple[ConnectionProfile, ...]
) -> tuple[ProfileImportPreview, ...]:
    if not bundle.valid:
        raise PortableBundleError("Cannot preview an invalid bundle.")
    incoming = [_parse_profile(item) for item in bundle.data["items"]["connection_profiles"]]
    by_id = {profile.id: profile for profile in existing}
    fingerprints = {_profile_fingerprint(profile) for profile in existing}
    preview: list[ProfileImportPreview] = []
    for profile in incoming:
        local = by_id.get(profile.id)
        if local and _profile_fingerprint(local) == _profile_fingerprint(profile):
            preview.append(
                ProfileImportPreview(profile, "skip", "Same profile ID and content already exist.")
            )
        elif local:
            preview.append(
                ProfileImportPreview(
                    profile, "conflict", "Same stable ID has different profile content."
                )
            )
        elif _profile_fingerprint(profile) in fingerprints:
            preview.append(
                ProfileImportPreview(
                    profile, "skip", "Equivalent profile already exists under another ID."
                )
            )
        else:
            preview.append(ProfileImportPreview(profile, "create", "New stable profile ID."))
    return tuple(preview)


def apply_profile_import(
    store: ConnectionProfileStore,
    bundle: BundleLoad,
    choices: dict[str, str],
) -> tuple[str, ...]:
    fresh_store = load_profile_store(store.path)
    if not fresh_store.valid:
        raise PortableBundleError("Local profile store became invalid; import stopped.")
    if list(fresh_store.profiles) != store.profiles:
        raise PortableBundleError(
            "Local profiles changed after preview; reload and review the import again."
        )
    preview = preview_profile_import(bundle, store.profiles)
    next_profiles = list(store.profiles)
    outcomes: list[str] = []
    by_id = {profile.id: index for index, profile in enumerate(next_profiles)}
    for item in preview:
        choice = choices.get(item.profile.id, "skip")
        if choice not in {"create", "merge", "skip"}:
            raise PortableBundleError(f"Invalid import choice for profile {item.profile.id}.")
        if choice == "merge" and item.action != "conflict":
            raise PortableBundleError("Merge is available only when a stable profile ID conflicts.")
        index = by_id.get(item.profile.id)
        if item.action == "conflict" and choice == "merge":
            assert index is not None
            next_profiles[index] = item.profile
            outcomes.append("merge")
        elif choice == "create":
            new_profile = item.profile
            if index is not None:
                new_profile = ConnectionProfile(
                    uuid4().hex,
                    item.profile.name,
                    item.profile.kind,
                    item.profile.endpoint_a,
                    item.profile.endpoint_b,
                    item.profile.tags,
                    item.profile.favorite,
                    item.profile.defaults,
                    item.profile.created_at,
                    item.profile.updated_at,
                )
            next_profiles.append(new_profile)
            by_id[new_profile.id] = len(next_profiles) - 1
            outcomes.append("create")
        else:
            outcomes.append("skip")
    if next_profiles != store.profiles:
        store._save(next_profiles)
    return tuple(outcomes)


def selected_preferences(
    current: dict[str, Any], incoming: dict[str, Any], selected: set[str]
) -> dict[str, Any]:
    if selected - PREFERENCE_KEYS:
        raise PortableBundleError("Only listed portable preferences can be imported.")
    merged = copy.deepcopy(current)
    for key in selected:
        if key not in incoming:
            continue
        merged[key] = copy.deepcopy(incoming[key])
    validated = validate_settings(merged)
    if validated.warnings:
        raise PortableBundleError(
            "Imported preference validation failed: " + "; ".join(validated.warnings)
        )
    return validated.values
