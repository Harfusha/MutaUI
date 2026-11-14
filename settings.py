"""Validated, versioned settings storage for Mutagen Control."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forward_configuration import validate_forward_proposal
from sync_configuration import validate_sync_proposal
from sync_profiles import PROFILES

CURRENT_SCHEMA_VERSION = 1
DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": CURRENT_SCHEMA_VERSION,
    "theme": "system",
    "language": "en",
    "onboarding_completed": False,
    "check_updates_on_startup": False,
    "binary": "",
    "interval": 4,
    "metric_interval": 2,
    "adaptive_poll": True,
    "adaptive_fast": 2,
    "adaptive_idle": 30,
    "adaptive_quiet": 90,
    "new_sync_profile": "default",
    "eco_tray": True,
    "tray": True,
    "alerts": True,
    "quiet_hours_enabled": False,
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "cpu_alert_on": False,
    "cpu_alert_limit": 90,
    "ram_alert_on": False,
    "ram_alert_limit": 1024,
    "alert_hold": 20,
    "health_mode": "monitor_only",
    "health_failure_count": 3,
    "health_failure_elapsed": 120,
    "health_cooldown": 60,
    "health_max_attempts": 2,
    "health_attempt_window": 1800,
    "health_environment_grace": 120,
    "favorites": {"sync": [], "forward": []},
    "session_prefs": {},
}


@dataclass(frozen=True)
class SettingsLoad:
    values: dict[str, Any]
    warnings: tuple[str, ...] = ()


class SettingsValidationError(OSError):
    """Raised when a settings write would persist invalid or future data."""


@dataclass(frozen=True)
class SettingsMigrationResult:
    migrated: bool
    backup_path: Path | None = None
    message: str = ""


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=".settings-restore-", suffix=".tmp", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _exclusive_backup(path: Path, label: str, data: bytes) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.name}.{label}.{stamp}.bak")
    with backup.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return backup


def migrate_settings_file(path: str | Path) -> SettingsMigrationResult:
    """Normalize a legacy supported settings file, preserving exact rollback bytes."""
    target = Path(path)
    try:
        original = target.read_bytes()
        raw = json.loads(original.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsValidationError(f"Settings cannot be migrated safely: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsValidationError("Settings root is not an object; source was left unchanged.")
    version = raw.get("schema_version", 0)
    if type(version) is not int or version < 0 or version > CURRENT_SCHEMA_VERSION:
        raise SettingsValidationError("Settings schema is unsupported; source was left unchanged.")
    validated = validate_settings(raw)
    if validated.warnings:
        raise SettingsValidationError(
            "Settings validation failed; source was left unchanged: "
            + "; ".join(validated.warnings)
        )
    if version == CURRENT_SCHEMA_VERSION:
        return SettingsMigrationResult(False, None, "Settings are already current.")
    migrated_values = copy.deepcopy(validated.values)
    migrated_values["schema_version"] = CURRENT_SCHEMA_VERSION
    backup = _exclusive_backup(target, "pre-migration", original)
    try:
        write_settings(target, migrated_values)
        checked = load_settings(target)
        if checked.warnings or checked.values != migrated_values:
            raise SettingsValidationError("Migrated settings did not pass read-back validation.")
    except Exception:
        _atomic_write_bytes(target, original)
        raise
    return SettingsMigrationResult(
        True, backup, "Legacy settings migrated; exact source backup created."
    )


def rollback_settings_migration(path: str | Path, backup_path: str | Path) -> Path:
    """Restore an exact migration backup after validating both current and backup data."""
    target = Path(path)
    backup = Path(backup_path)
    prefix = target.name + ".pre-migration."
    if (
        backup.parent.resolve() != target.parent.resolve()
        or not backup.name.startswith(prefix)
        or not backup.name.endswith(".bak")
    ):
        raise SettingsValidationError("Rollback backup must be a sibling pre-migration backup.")
    current = load_settings(target)
    if current.warnings:
        raise SettingsValidationError("Current settings are invalid; refusing rollback overwrite.")
    try:
        original = backup.read_bytes()
        raw = json.loads(original.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsValidationError(f"Migration backup is unreadable: {exc}") from exc
    previous = validate_settings(raw)
    if previous.warnings:
        raise SettingsValidationError("Migration backup is invalid; rollback refused.")
    _exclusive_backup(target, "pre-rollback", target.read_bytes())
    _atomic_write_bytes(target, original)
    return target


def _is_int(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def validate_settings(raw: Any) -> SettingsLoad:
    if not isinstance(raw, dict):
        return SettingsLoad(
            copy.deepcopy(DEFAULT_SETTINGS), ("Settings root must be a JSON object.",)
        )

    values = copy.deepcopy(DEFAULT_SETTINGS)
    values.update(copy.deepcopy(raw))
    warnings: list[str] = []

    version = raw.get("schema_version", 0)
    if type(version) is not int or version < 0:
        warnings.append("Settings schema version is invalid; defaults were used for it.")
        values["schema_version"] = CURRENT_SCHEMA_VERSION
    elif version > CURRENT_SCHEMA_VERSION:
        warnings.append(
            "Settings were written by a newer application; saving is blocked to preserve them."
        )
        values["schema_version"] = version
    else:
        # Version 0 is the legacy unversioned format used by existing releases.
        values["schema_version"] = CURRENT_SCHEMA_VERSION

    string_keys = {"binary": 4096}
    for key, max_length in string_keys.items():
        value = raw.get(key, DEFAULT_SETTINGS[key])
        if not isinstance(value, str) or len(value) > max_length or "\x00" in value:
            values[key] = DEFAULT_SETTINGS[key]
            warnings.append(f"Invalid setting '{key}'; default used.")

    for key in ("quiet_hours_start", "quiet_hours_end"):
        value = raw.get(key, DEFAULT_SETTINGS[key])
        if (
            not isinstance(value, str)
            or len(value) != 5
            or value[2] != ":"
            or not value[:2].isdigit()
            or not value[3:].isdigit()
            or int(value[:2]) > 23
            or int(value[3:]) > 59
        ):
            values[key] = DEFAULT_SETTINGS[key]
            warnings.append(f"Invalid setting '{key}'; default used.")

    integer_ranges = {
        "interval": (2, 30),
        "metric_interval": (1, 10),
        "adaptive_fast": (2, 15),
        "adaptive_idle": (5, 180),
        "adaptive_quiet": (15, 900),
        "cpu_alert_limit": (1, 1600),
        "ram_alert_limit": (64, 131072),
        "alert_hold": (5, 600),
        "health_failure_count": (3, 10),
        "health_failure_elapsed": (30, 900),
        "health_cooldown": (60, 3600),
        "health_max_attempts": (1, 2),
        "health_attempt_window": (1800, 86400),
        "health_environment_grace": (30, 900),
    }
    for key, (minimum, maximum) in integer_ranges.items():
        value = raw.get(key, DEFAULT_SETTINGS[key])
        valid = _is_int(value, minimum, maximum)
        if key == "metric_interval":
            valid = valid and value in {1, 2, 3, 5, 10}
        if not valid:
            values[key] = DEFAULT_SETTINGS[key]
            warnings.append(f"Invalid setting '{key}'; default used.")

    boolean_keys = {
        "adaptive_poll",
        "eco_tray",
        "tray",
        "alerts",
        "quiet_hours_enabled",
        "cpu_alert_on",
        "ram_alert_on",
        "onboarding_completed",
        "check_updates_on_startup",
    }
    for key in boolean_keys:
        value = raw.get(key, DEFAULT_SETTINGS[key])
        if type(value) is not bool:
            values[key] = DEFAULT_SETTINGS[key]
            warnings.append(f"Invalid setting '{key}'; default used.")

    profile = raw.get("new_sync_profile", DEFAULT_SETTINGS["new_sync_profile"])
    if not isinstance(profile, str) or profile not in PROFILES:
        values["new_sync_profile"] = DEFAULT_SETTINGS["new_sync_profile"]
        warnings.append("Invalid setting 'new_sync_profile'; default used.")

    health_mode = raw.get("health_mode", DEFAULT_SETTINGS["health_mode"])
    if not isinstance(health_mode, str) or health_mode not in {
        "monitor_only",
        "assisted",
        "auto_safe",
    }:
        values["health_mode"] = DEFAULT_SETTINGS["health_mode"]
        warnings.append("Invalid setting 'health_mode'; monitor-only mode used.")

    for key, choices in (("theme", {"system", "light", "dark"}), ("language", {"en", "cs"})):
        value = raw.get(key, DEFAULT_SETTINGS[key])
        if not isinstance(value, str) or value not in choices:
            values[key] = DEFAULT_SETTINGS[key]
            warnings.append(f"Invalid setting '{key}'; default used.")

    favorites = raw.get("favorites", DEFAULT_SETTINGS["favorites"])
    if not isinstance(favorites, dict):
        values["favorites"] = copy.deepcopy(DEFAULT_SETTINGS["favorites"])
        warnings.append("Invalid setting 'favorites'; defaults used.")
    else:
        clean_favorites: dict[str, list[str]] = {}
        for kind in ("sync", "forward"):
            entries = favorites.get(kind, [])
            if (
                not isinstance(entries, list)
                or len(entries) > 10000
                or any(not isinstance(item, str) or len(item) > 2048 for item in entries)
            ):
                clean_favorites[kind] = []
                warnings.append(f"Invalid favorites for '{kind}'; defaults used.")
            else:
                clean_favorites[kind] = list(dict.fromkeys(entries))
        values["favorites"] = clean_favorites

    session_prefs = raw.get("session_prefs", {})
    clean_prefs: dict[str, dict[str, Any]] = {}
    if not isinstance(session_prefs, dict) or len(session_prefs) > 10000:
        warnings.append("Invalid setting 'session_prefs'; defaults used.")
    else:
        for identifier, prefs in session_prefs.items():
            if (
                not isinstance(identifier, str)
                or len(identifier) > 2048
                or not isinstance(prefs, dict)
            ):
                warnings.append("Invalid session preference entry; entry ignored.")
                continue
            note = prefs.get("note", "")
            notifications = prefs.get("notifications", True)
            if not isinstance(note, str) or len(note) > 10000 or type(notifications) is not bool:
                warnings.append("Invalid session preference values; entry ignored.")
                continue
            proposed = prefs.get("configuration_proposal", {})
            clean_proposed: dict[str, Any] = {}
            if not isinstance(proposed, dict) or len(proposed) > 64:
                warnings.append("Invalid session configuration proposal; proposals discarded.")
            else:
                for field, value in proposed.items():
                    if not isinstance(field, str):
                        warnings.append("Invalid proposed configuration field; proposal ignored.")
                        continue
                    try:
                        clean_proposed[field] = validate_sync_proposal(field, value)
                    except (ValueError, TypeError):
                        warnings.append(
                            f"Invalid proposed configuration '{field}'; proposal ignored."
                        )
            forward_proposed = prefs.get("forward_configuration_proposal", {})
            clean_forward_proposed: dict[str, Any] = {}
            if not isinstance(forward_proposed, dict) or len(forward_proposed) > 64:
                warnings.append("Invalid forwarding configuration proposal; proposals discarded.")
            else:
                for field, value in forward_proposed.items():
                    if not isinstance(field, str):
                        warnings.append("Invalid proposed forwarding field; proposal ignored.")
                        continue
                    try:
                        clean_forward_proposed[field] = validate_forward_proposal(field, value)
                    except (ValueError, TypeError):
                        warnings.append(
                            f"Invalid proposed forwarding configuration '{field}'; proposal ignored."
                        )
            clean_prefs[identifier] = {
                "note": note,
                "notifications": notifications,
                "configuration_proposal": clean_proposed,
                "forward_configuration_proposal": clean_forward_proposed,
            }
    values["session_prefs"] = clean_prefs

    return SettingsLoad(values, tuple(dict.fromkeys(warnings)))


def load_settings(path: str | Path) -> SettingsLoad:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        backup = _load_last_valid_settings(path)
        if backup is not None:
            _atomic_write_bytes(path, backup[0])
            return SettingsLoad(
                backup[1].values, ("Settings restored from the last valid settings backup.",)
            )
        return SettingsLoad(copy.deepcopy(DEFAULT_SETTINGS))
    except (UnicodeError, json.JSONDecodeError):
        try:
            corrupt_source = path.read_bytes()
        except OSError:
            corrupt_source = None
        backup = _load_last_valid_settings(path)
        if backup is not None:
            if corrupt_source is not None:
                _exclusive_backup(path, "corrupt", corrupt_source)
            _atomic_write_bytes(path, backup[0])
            return SettingsLoad(
                backup[1].values, ("Settings restored from the last valid settings backup.",)
            )
        return SettingsLoad(
            copy.deepcopy(DEFAULT_SETTINGS), ("Settings file is unreadable; safe defaults loaded.",)
        )
    except OSError:
        return SettingsLoad(
            copy.deepcopy(DEFAULT_SETTINGS), ("Settings file is unreadable; safe defaults loaded.",)
        )
    return validate_settings(raw)


def _load_last_valid_settings(path: Path) -> tuple[bytes, SettingsLoad] | None:
    backup_path = path.with_name(path.name + ".last-valid.bak")
    try:
        payload = backup_path.read_bytes()
        loaded = validate_settings(json.loads(payload.decode("utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        return None
    if loaded.warnings:
        return None
    return payload, loaded


def write_settings(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    if not isinstance(data, dict):
        raise SettingsValidationError("Settings must be a JSON object.")
    if (
        type(data.get("schema_version", CURRENT_SCHEMA_VERSION)) is int
        and data.get("schema_version", CURRENT_SCHEMA_VERSION) > CURRENT_SCHEMA_VERSION
    ):
        raise SettingsValidationError(
            "Settings were written by a newer application; refusing to overwrite them."
        )

    validated = validate_settings(data)
    if validated.warnings:
        raise SettingsValidationError(
            "Refusing to save invalid settings: " + "; ".join(validated.warnings)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    previous_bytes: bytes | None = None
    if path.exists():
        try:
            previous_bytes = path.read_bytes()
        except OSError:
            previous_bytes = None
        existing = load_settings(path)
        if existing.warnings:
            backup = path.with_name(path.name + ".invalid.bak")
            if not backup.exists() and previous_bytes is not None:
                with backup.open("xb") as stream:
                    stream.write(previous_bytes)

    # Persist the validated candidate first. After a successful main-file
    # replace, the sidecar is therefore the newest known-good settings state.
    payload = json.dumps(validated.values, indent=2, ensure_ascii=False).encode("utf-8")
    _atomic_write_bytes(path.with_name(path.name + ".last-valid.bak"), payload)
    _atomic_write_bytes(path, payload)
