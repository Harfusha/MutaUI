import json

from settings import DEFAULT_SETTINGS, load_settings, write_settings


def test_non_object_settings_use_defaults_without_replacing_source(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")

    loaded = load_settings(path)

    assert loaded.values["interval"] == DEFAULT_SETTINGS["interval"]
    assert loaded.warnings
    assert path.read_text(encoding="utf-8") == "[]"


def test_invalid_values_fall_back_and_unknown_keys_survive(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"interval": [], "tray": "yes", "future_option": 42}), encoding="utf-8")

    loaded = load_settings(path)

    assert loaded.values["interval"] == DEFAULT_SETTINGS["interval"]
    assert loaded.values["tray"] == DEFAULT_SETTINGS["tray"]
    assert loaded.values["future_option"] == 42
    assert loaded.warnings


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
