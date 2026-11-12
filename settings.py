"""Validated, versioned settings storage for Mutagen Control."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sync_profiles import PROFILES

CURRENT_SCHEMA_VERSION = 1
DEFAULT_SETTINGS: dict[str, Any] = {
    "schema_version": CURRENT_SCHEMA_VERSION,
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
    "cpu_alert_on": False,
    "cpu_alert_limit": 90,
    "ram_alert_on": False,
    "ram_alert_limit": 1024,
    "alert_hold": 20,
    "favorites": {"sync": [], "forward": []},
    "session_prefs": {},
}


@dataclass(frozen=True)
class SettingsLoad:
    values: dict[str, Any]
    warnings: tuple[str, ...] = ()


class SettingsValidationError(OSError):
    """Raised when a settings write would persist invalid or future data."""


def _is_int(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def validate_settings(raw: Any) -> SettingsLoad:
    if not isinstance(raw, dict):
        return SettingsLoad(copy.deepcopy(DEFAULT_SETTINGS), ("Settings root must be a JSON object.",))

    values = copy.deepcopy(DEFAULT_SETTINGS)
    values.update(copy.deepcopy(raw))
    warnings: list[str] = []

    version = raw.get("schema_version", 0)
    if type(version) is not int or version < 0:
        warnings.append("Settings schema version is invalid; defaults were used for it.")
        values["schema_version"] = CURRENT_SCHEMA_VERSION
    elif version > CURRENT_SCHEMA_VERSION:
        warnings.append("Settings were written by a newer application; saving is blocked to preserve them.")
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

    integer_ranges = {
        "interval": (2, 30),
        "metric_interval": (1, 10),
        "adaptive_fast": (2, 15),
        "adaptive_idle": (5, 180),
        "adaptive_quiet": (15, 900),
        "cpu_alert_limit": (1, 1600),
        "ram_alert_limit": (64, 131072),
        "alert_hold": (5, 600),
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
        "adaptive_poll", "eco_tray", "tray", "alerts", "cpu_alert_on", "ram_alert_on",
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

    favorites = raw.get("favorites", DEFAULT_SETTINGS["favorites"])
    if not isinstance(favorites, dict):
        values["favorites"] = copy.deepcopy(DEFAULT_SETTINGS["favorites"])
        warnings.append("Invalid setting 'favorites'; defaults used.")
    else:
        clean_favorites: dict[str, list[str]] = {}
        for kind in ("sync", "forward"):
            entries = favorites.get(kind, [])
            if (not isinstance(entries, list)
                    or len(entries) > 10000
                    or any(not isinstance(item, str) or len(item) > 2048 for item in entries)):
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
            if not isinstance(identifier, str) or len(identifier) > 2048 or not isinstance(prefs, dict):
                warnings.append("Invalid session preference entry; entry ignored.")
                continue
            note = prefs.get("note", "")
            notifications = prefs.get("notifications", True)
            if not isinstance(note, str) or len(note) > 10000 or type(notifications) is not bool:
                warnings.append("Invalid session preference values; entry ignored.")
                continue
            clean_prefs[identifier] = {"note": note, "notifications": notifications}
    values["session_prefs"] = clean_prefs

    return SettingsLoad(values, tuple(dict.fromkeys(warnings)))


def load_settings(path: str | Path) -> SettingsLoad:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return SettingsLoad(copy.deepcopy(DEFAULT_SETTINGS))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return SettingsLoad(copy.deepcopy(DEFAULT_SETTINGS), ("Settings file is unreadable; safe defaults loaded.",))
    return validate_settings(raw)


def write_settings(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    if not isinstance(data, dict):
        raise SettingsValidationError("Settings must be a JSON object.")
    if type(data.get("schema_version", CURRENT_SCHEMA_VERSION)) is int and data.get("schema_version", CURRENT_SCHEMA_VERSION) > CURRENT_SCHEMA_VERSION:
        raise SettingsValidationError("Settings were written by a newer application; refusing to overwrite them.")

    validated = validate_settings(data)
    if validated.warnings:
        raise SettingsValidationError("Refusing to save invalid settings: " + "; ".join(validated.warnings))

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = load_settings(path)
        if existing.warnings:
            backup = path.with_name(path.name + ".invalid.bak")
            if not backup.exists():
                shutil.copy2(path, backup)

    temp_path: Path | None = None
    try:
        # Atomic replacement avoids a corrupted settings file after a crash/power loss.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".settings-", suffix=".tmp", delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(validated.values, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
