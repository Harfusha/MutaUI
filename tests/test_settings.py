import json

import pytest

import settings as settings_module
from settings import (
    DEFAULT_SETTINGS,
    SettingsValidationError,
    load_settings,
    migrate_settings_file,
    rollback_settings_migration,
    validate_settings,
    write_settings,
)


def test_non_object_settings_use_defaults_without_replacing_source(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")

    loaded = load_settings(path)

    assert loaded.values["interval"] == DEFAULT_SETTINGS["interval"]
    assert loaded.warnings
    assert path.read_text(encoding="utf-8") == "[]"


def test_invalid_values_fall_back_and_unknown_keys_survive(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"interval": [], "tray": "yes", "future_option": 42}), encoding="utf-8"
    )

    loaded = load_settings(path)

    assert loaded.values["interval"] == DEFAULT_SETTINGS["interval"]
    assert loaded.values["tray"] == DEFAULT_SETTINGS["tray"]
    assert loaded.values["future_option"] == 42
    assert loaded.warnings


def test_quiet_hours_defaults_and_invalid_values_are_safe():
    valid = validate_settings({})
    invalid = validate_settings(
        {"quiet_hours_enabled": "yes", "quiet_hours_start": "25:30", "quiet_hours_end": "7:00"}
    )

    assert valid.values["quiet_hours_enabled"] is False
    assert valid.values["quiet_hours_start"] == "22:00"
    assert valid.values["quiet_hours_end"] == "07:00"
    assert invalid.values["quiet_hours_enabled"] is False
    assert invalid.values["quiet_hours_start"] == "22:00"
    assert invalid.values["quiet_hours_end"] == "07:00"
    assert len(invalid.warnings) == 3


def test_legacy_settings_migrate_defaults_and_version(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"interval": 8}), encoding="utf-8")

    loaded = load_settings(path)

    assert loaded.values["interval"] == 8
    assert loaded.values["adaptive_poll"] is True
    assert loaded.values["schema_version"] == 1
    assert loaded.warnings == ()


def test_invalid_original_is_backed_up_before_valid_replacement(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")

    write_settings(path, DEFAULT_SETTINGS)

    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert path.with_name("settings.json.invalid.bak").read_text(encoding="utf-8") == "[]"


def test_sync_configuration_proposals_are_validated_and_kept_local(tmp_path):
    path = tmp_path / "settings.json"
    proposal = {
        "watch.mode": "force-poll",
        "watch.pollingInterval": 30,
        "not-a-native-field": "unsafe",
    }
    path.write_text(
        json.dumps(
            {"session_prefs": {"exact-id": {"note": "draft", "configuration_proposal": proposal}}}
        ),
        encoding="utf-8",
    )

    loaded = load_settings(path)

    prefs = loaded.values["session_prefs"]["exact-id"]
    assert prefs["configuration_proposal"] == {
        "watch.mode": "force-poll",
        "watch.pollingInterval": 30,
    }
    assert loaded.warnings


def test_invalid_sync_configuration_proposal_is_discarded():
    loaded = validate_settings(
        {"session_prefs": {"exact-id": {"configuration_proposal": {"watch.pollingInterval": 0}}}}
    )

    assert loaded.values["session_prefs"]["exact-id"]["configuration_proposal"] == {}
    assert loaded.warnings


def test_forwarding_proposals_are_validated_separately():
    loaded = validate_settings(
        {
            "session_prefs": {
                "forward-id": {
                    "forward_configuration_proposal": {
                        "destination.socket.overwriteMode": "overwrite",
                        "destination.socket.permissionMode": "0600",
                        "destination.socket.group": "",
                    }
                }
            }
        }
    )

    assert loaded.values["session_prefs"]["forward-id"]["forward_configuration_proposal"] == {
        "destination.socket.overwriteMode": "overwrite",
        "destination.socket.permissionMode": "0600",
    }
    assert loaded.warnings


def test_invalid_schema_and_scalar_values_fall_back_and_future_schema_blocks_save(tmp_path):
    loaded = validate_settings(
        {
            "schema_version": -1,
            "binary": "bad\x00binary",
            "new_sync_profile": "not-supported",
            "health_mode": "automatic",
            "theme": "neon",
            "language": "xx",
            "favorites": [],
        }
    )
    assert loaded.values["schema_version"] == DEFAULT_SETTINGS["schema_version"]
    for key in ("binary", "new_sync_profile", "health_mode", "theme", "language", "favorites"):
        assert loaded.values[key] == DEFAULT_SETTINGS[key]
    assert len(loaded.warnings) >= 6

    future = {"schema_version": DEFAULT_SETTINGS["schema_version"] + 1, "future": {"keep": True}}
    path = tmp_path / "future.json"
    original = json.dumps(future).encode("utf-8")
    path.write_bytes(original)
    assert validate_settings(future).values["schema_version"] == future["schema_version"]
    with pytest.raises(SettingsValidationError, match="newer application"):
        write_settings(path, future)
    assert path.read_bytes() == original


def test_favorites_and_session_preferences_reject_invalid_shapes_and_deduplicate():
    loaded = validate_settings(
        {
            "favorites": {
                "sync": ["same", "same"],
                "forward": "not-a-list",
            },
            "session_prefs": {
                "not-a-dict": "bad",
                7: {"note": "bad identifier type"},
                "bad-note": {"note": [], "notifications": True},
                "bad-notifications": {"note": "ok", "notifications": 1},
                "valid": {"note": "ok", "notifications": False},
            },
        }
    )
    assert loaded.values["favorites"] == {"sync": ["same"], "forward": []}
    assert set(loaded.values["session_prefs"]) == {"valid"}
    assert loaded.values["session_prefs"]["valid"]["notifications"] is False
    assert loaded.warnings

    malformed_prefs = validate_settings({"session_prefs": "not-an-object"})
    oversized_prefs = validate_settings(
        {"session_prefs": {f"session-{n}": {} for n in range(10001)}}
    )
    assert malformed_prefs.values["session_prefs"] == {}
    assert oversized_prefs.values["session_prefs"] == {}
    assert malformed_prefs.warnings and oversized_prefs.warnings


def test_session_preference_proposals_discard_invalid_keys_values_and_oversized_maps():
    loaded = validate_settings(
        {
            "session_prefs": {
                "proposal": {
                    "configuration_proposal": {
                        7: "non-string key",
                        "watch.pollingInterval": 0,
                    },
                    "forward_configuration_proposal": {
                        7: "non-string key",
                        "destination.socket.permissionMode": "not-octal",
                    },
                },
                "too-many-sync": {"configuration_proposal": {f"unknown-{n}": n for n in range(65)}},
                "too-many-forward": {
                    "forward_configuration_proposal": {f"unknown-{n}": n for n in range(65)}
                },
            }
        }
    )
    values = loaded.values["session_prefs"]
    assert values["proposal"]["configuration_proposal"] == {}
    assert values["proposal"]["forward_configuration_proposal"] == {}
    assert values["too-many-sync"]["configuration_proposal"] == {}
    assert values["too-many-forward"]["forward_configuration_proposal"] == {}
    assert loaded.warnings


def test_load_missing_malformed_and_non_utf8_settings(tmp_path):
    missing = load_settings(tmp_path / "missing.json")
    assert missing.values == DEFAULT_SETTINGS
    assert not missing.warnings

    path = tmp_path / "bad.json"
    for source in (b"{", b"\xff"):
        path.write_bytes(source)
        loaded = load_settings(path)
        assert loaded.values == DEFAULT_SETTINGS
        assert loaded.warnings


def test_load_recovers_last_valid_settings_after_crash_corruption(tmp_path):
    path = tmp_path / "settings.json"
    first = {**DEFAULT_SETTINGS, "theme": "dark"}
    latest = {**DEFAULT_SETTINGS, "theme": "light"}
    write_settings(path, first)
    write_settings(path, latest)

    path.write_bytes(b'{"theme":')
    loaded = load_settings(path)

    assert loaded.values == latest
    assert any("last valid settings" in warning.lower() for warning in loaded.warnings)
    assert json.loads(path.read_text(encoding="utf-8")) == latest
    corrupt_backups = list(tmp_path.glob("settings.json.corrupt.*.bak"))
    assert len(corrupt_backups) == 1
    assert corrupt_backups[0].read_bytes() == b'{"theme":'


def test_write_requires_valid_object_and_preserves_first_invalid_backup(tmp_path):
    path = tmp_path / "settings.json"
    with pytest.raises(SettingsValidationError, match="JSON object"):
        write_settings(path, [])
    with pytest.raises(SettingsValidationError, match="invalid settings"):
        write_settings(path, {"interval": 1})
    assert not path.exists()

    invalid = b"not-json"
    path.write_bytes(invalid)
    write_settings(path, DEFAULT_SETTINGS)
    backup = path.with_name(path.name + ".invalid.bak")
    assert backup.read_bytes() == invalid

    path.write_bytes(b"still-not-json")
    write_settings(path, DEFAULT_SETTINGS)
    assert backup.read_bytes() == invalid


def test_write_creates_new_settings_file(tmp_path):
    path = tmp_path / "new" / "settings.json"

    write_settings(path, DEFAULT_SETTINGS)

    assert json.loads(path.read_text(encoding="utf-8")) == DEFAULT_SETTINGS


def test_migrate_settings_creates_exact_backup_and_is_idempotent(tmp_path):
    path = tmp_path / "settings.json"
    original = b'{  "interval": 8, "legacy": "kept?" }\r\n'
    path.write_bytes(original)

    result = migrate_settings_file(path)

    assert result.migrated
    assert result.backup_path is not None
    assert result.backup_path.read_bytes() == original
    assert load_settings(path).values["schema_version"] == DEFAULT_SETTINGS["schema_version"]
    assert not migrate_settings_file(path).migrated


@pytest.mark.parametrize(
    "source",
    [
        b"[]",
        b"not-json",
        b"\xff",
        b'{"schema_version": 999}',
        b'{"interval": 1}',
    ],
)
def test_migration_rejects_unsafe_source_without_changing_original(tmp_path, source):
    path = tmp_path / "settings.json"
    path.write_bytes(source)

    with pytest.raises(SettingsValidationError):
        migrate_settings_file(path)

    assert path.read_bytes() == source


def test_migration_write_failure_restores_exact_source(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    original = b'{"interval": 8}\n'
    path.write_bytes(original)

    def fail_write(*_args, **_kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(settings_module, "write_settings", fail_write)
    with pytest.raises(OSError, match="simulated write failure"):
        migrate_settings_file(path)
    assert path.read_bytes() == original


def test_migration_readback_mismatch_restores_exact_source(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    original = b'{"interval": 8}\n'
    path.write_bytes(original)
    real_load = settings_module.load_settings
    calls = 0

    def mismatched_readback(target):
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_load(target)
        return settings_module.SettingsLoad({"schema_version": 0})

    monkeypatch.setattr(settings_module, "load_settings", mismatched_readback)
    with pytest.raises(SettingsValidationError, match="read-back validation"):
        migrate_settings_file(path)
    assert path.read_bytes() == original


def test_rollback_restores_exact_bytes_and_rejects_non_sibling_backup(tmp_path):
    path = tmp_path / "settings.json"
    original = b'{ "interval": 8 }\r\n'
    path.write_bytes(original)
    migrated = migrate_settings_file(path)
    assert migrated.backup_path is not None

    write_settings(path, DEFAULT_SETTINGS)
    restored = rollback_settings_migration(path, migrated.backup_path)
    assert restored == path
    assert path.read_bytes() == original
    assert list(tmp_path.glob("settings.json.pre-rollback.*.bak"))

    outside = tmp_path.parent / (path.name + ".pre-migration.fake.bak")
    outside.write_bytes(original)
    with pytest.raises(SettingsValidationError, match="sibling"):
        rollback_settings_migration(path, outside)


def test_rollback_refuses_invalid_current_or_backup_data(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(DEFAULT_SETTINGS), encoding="utf-8")
    backup = path.with_name(path.name + ".pre-migration.invalid.bak")
    backup.write_bytes(b"not-json")

    path.write_bytes(b"invalid-current")
    with pytest.raises(SettingsValidationError, match="Current settings are invalid"):
        rollback_settings_migration(path, backup)

    write_settings(path, DEFAULT_SETTINGS)
    with pytest.raises(SettingsValidationError, match="unreadable"):
        rollback_settings_migration(path, backup)

    backup.write_text("[]", encoding="utf-8")
    with pytest.raises(SettingsValidationError, match="backup is invalid"):
        rollback_settings_migration(path, backup)


def test_atomic_rollback_write_cleans_up_when_temp_creation_fails(tmp_path, monkeypatch):
    path = tmp_path / "restore.json"

    def fail_temp(*_args, **_kwargs):
        raise OSError("temporary storage unavailable")

    monkeypatch.setattr(settings_module.tempfile, "NamedTemporaryFile", fail_temp)
    with pytest.raises(OSError, match="temporary storage unavailable"):
        settings_module._atomic_write_bytes(path, b"content")
    assert not path.exists()
    assert not list(tmp_path.glob(".settings-restore-*.tmp"))


def test_settings_write_cleans_up_when_temp_creation_fails(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"

    def fail_temp(*_args, **_kwargs):
        raise OSError("temporary storage unavailable")

    monkeypatch.setattr(settings_module.tempfile, "NamedTemporaryFile", fail_temp)
    with pytest.raises(OSError, match="temporary storage unavailable"):
        write_settings(path, DEFAULT_SETTINGS)
    assert not path.exists()
    assert not list(tmp_path.glob(".settings-*.tmp"))


def test_load_settings_restores_from_last_valid_when_file_is_missing(tmp_path):
    path = tmp_path / "settings.json"
    backup = path.with_name(path.name + ".last-valid.bak")
    valid_data = dict(DEFAULT_SETTINGS, theme="dark")
    backup.write_text(json.dumps(valid_data), encoding="utf-8")

    loaded = load_settings(path)

    assert loaded.values["theme"] == "dark"
    assert any("restored from the last valid settings backup" in w for w in loaded.warnings)
    assert path.exists()


def test_load_settings_handles_corrupt_read_oserror_with_valid_backup(tmp_path, monkeypatch):
    from pathlib import Path

    path = tmp_path / "settings.json"
    backup = path.with_name(path.name + ".last-valid.bak")
    backup.write_text(json.dumps(DEFAULT_SETTINGS), encoding="utf-8")
    path.write_text("invalid json", encoding="utf-8")

    real_read_bytes = Path.read_bytes

    def fake_read_bytes(self, *args, **kwargs):
        if self == path:
            raise OSError("permission denied reading corrupt file")
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)
    loaded = load_settings(path)

    assert loaded.values == DEFAULT_SETTINGS
    assert any("restored from the last valid settings backup" in w for w in loaded.warnings)


def test_load_last_valid_settings_ignores_backup_with_warnings(tmp_path):
    path = tmp_path / "settings.json"
    backup = path.with_name(path.name + ".last-valid.bak")
    # Setting with invalid interval triggers warnings
    backup.write_text(json.dumps({"interval": -5}), encoding="utf-8")

    assert settings_module._load_last_valid_settings(path) is None
