import hashlib
import json

import pytest

from connection_profiles import ConnectionProfileStore
from ignore_presets import IgnorePresetStore, preset_to_record
from portable_bundle import (
    _canonical,
    apply_profile_import,
    build_bundle,
    load_bundle,
    preview_profile_import,
    selected_preferences,
)
from settings import migrate_settings_file, rollback_settings_migration


def test_bundle_is_versioned_checksummed_and_redacts_machine_paths(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create(
        "Laptop",
        r"C:\Users\adam\work",
        "deploy@build.example:/srv/project",
        kind="sync",
        tags=("work",),
    )

    result = build_bundle(
        [profile],
        {"theme": "dark", "language": "cs", "binary": r"C:\secret\mutagen.exe"},
        app_version="8.2",
    )
    loaded = load_bundle(result.text)

    assert result.valid
    assert loaded.valid
    assert loaded.data["schema_version"] == 1
    assert loaded.data["items"]["connection_profiles"][0]["endpoint_a"] == "[redacted-local-path]"
    assert (
        loaded.data["items"]["connection_profiles"][0]["endpoint_b"]
        == "deploy@build.example:/srv/project"
    )
    assert "mutagen.exe" not in result.text
    assert loaded.data["checksum"]


def test_opt_in_paths_still_never_export_binary_or_secret_fields(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create("Local", "/home/adam/work", "/tmp/dest", kind="sync")

    result = build_bundle(
        [profile], {"binary": "/secret/mutagen"}, app_version="8.2", include_local_paths=True
    )

    assert result.valid
    assert "/home/adam/work" in result.text
    assert "mutagen" not in result.text
    assert "private_key" not in result.text.lower()


def test_optional_records_are_redacted_before_they_enter_the_bundle():
    result = build_bundle(
        [],
        {},
        app_version="8.2",
        project_references=[{"id": "proj1", "url": "https://alice:secret@example.test/repo"}],
    )

    assert result.valid
    assert "alice:secret@" not in result.text
    assert "[redacted]" in result.text


def test_ignore_preset_export_is_strict_and_preserves_root_anchored_patterns(tmp_path):
    preset = IgnorePresetStore(tmp_path / "ignore-presets.json").create(
        "Root rules", ("/build/", "!build/keep.txt")
    )
    result = build_bundle([], {}, app_version="8.2", ignore_presets=[preset_to_record(preset)])
    assert result.valid
    assert load_bundle(result.text).valid
    assert "/build/" in result.text

    rejected = build_bundle(
        [], {}, app_version="8.2", ignore_presets=[{"id": "p1", "password": "secret"}]
    )
    assert not rejected.valid
    assert "password" not in rejected.text


def test_import_rejects_unredacted_paths_and_embedded_credentials(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create(
        "Remote", "https://alice:secret@example.test/repo", "host:/dest", kind="sync"
    )
    exported = build_bundle([profile], {}, app_version="8.2")
    payload = json.loads(exported.text)
    profile_data = payload["items"]["connection_profiles"][0]
    profile_data["endpoint_a"] = "https://alice:secret@example.test/repo"
    unsigned = {key: value for key, value in payload.items() if key != "checksum"}
    payload["checksum"] = hashlib.sha256(_canonical(unsigned)).hexdigest()

    assert not load_bundle(json.dumps(payload)).valid

    path_profile = store.create("Local", "/home/user/project", "host:/dest", kind="sync")
    path_bundle = json.loads(build_bundle([path_profile], {}, app_version="8.2").text)
    local = path_bundle["items"]["connection_profiles"][0]
    local["endpoint_a"] = "/home/user/project"
    unsigned = {key: value for key, value in path_bundle.items() if key != "checksum"}
    path_bundle["checksum"] = hashlib.sha256(_canonical(unsigned)).hexdigest()
    assert not load_bundle(json.dumps(path_bundle)).valid


def test_bundle_checksum_future_schema_and_malformed_profiles_fail_closed():
    store = ConnectionProfileStore("missing-profiles.json")
    text = build_bundle([], {}, app_version="8.2").text
    payload = json.loads(text)
    payload["items"]["preferences"]["theme"] = "light"
    assert not load_bundle(json.dumps(payload)).valid

    payload["schema_version"] = 999
    assert not load_bundle(json.dumps(payload)).valid
    assert store.profiles == []


def test_portable_bundle_validates_and_roundtrips_ordered_ignore_presets(tmp_path):
    presets = IgnorePresetStore(tmp_path / "ignores.json")
    preset = presets.create("Project", ("build/", "!build/release/"))
    bundle = build_bundle([], {}, app_version="8.2", ignore_presets=[preset_to_record(preset)])
    loaded = load_bundle(bundle.text)
    assert bundle.valid and loaded.valid
    assert loaded.data["items"]["ignore_presets"][0]["patterns"] == [
        "build/",
        "!build/release/",
    ]

    payload = json.loads(bundle.text)
    payload["items"]["ignore_presets"][0]["patterns"] = [r"C:\\private"]
    unsigned = {key: value for key, value in payload.items() if key != "checksum"}
    payload["checksum"] = hashlib.sha256(_canonical(unsigned)).hexdigest()
    rejected = load_bundle(json.dumps(payload))
    assert not rejected.valid
    assert "ignore preset" in rejected.warnings[0].lower()


def test_import_preview_classifies_stable_id_and_semantic_fingerprint(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    current = store.create("Alpha", "./a", "host:/b", kind="sync")
    same = build_bundle([current], {}, app_version="8.2")
    preview = preview_profile_import(load_bundle(same.text), store.profiles)
    assert preview[0].action == "skip"

    changed = current.__class__(
        current.id,
        "Renamed",
        current.kind,
        current.endpoint_a,
        current.endpoint_b,
        current.tags,
        current.favorite,
        current.defaults,
        current.created_at,
        current.updated_at,
    )
    conflict = preview_profile_import(
        load_bundle(build_bundle([changed], {}, app_version="8.2").text), store.profiles
    )
    assert conflict[0].action == "conflict"


def test_import_apply_is_explicit_and_backs_up_existing_profile_store(tmp_path):
    path = tmp_path / "profiles.json"
    store = ConnectionProfileStore(path)
    seed = store.create("Existing", "./old", "host:/old", kind="sync")
    incoming_store = ConnectionProfileStore(tmp_path / "incoming.json")
    incoming = incoming_store.create("Beta", "./src", "host:/dest", kind="sync")
    bundle = load_bundle(build_bundle([incoming], {}, app_version="8.2").text)
    preview = preview_profile_import(bundle, store.profiles)
    assert len(store.profiles) == 1

    apply_profile_import(store, bundle, {incoming.id: "create"})

    assert {profile.id for profile in store.profiles} == {incoming.id, seed.id}
    assert path.with_suffix(".json.bak").exists()
    assert preview[0].action == "create"


def test_import_stops_if_profile_file_changed_after_preview(tmp_path):
    path = tmp_path / "profiles.json"
    store = ConnectionProfileStore(path)
    other = ConnectionProfileStore(tmp_path / "incoming.json")
    external = ConnectionProfileStore(path)
    incoming = other.create("New", "./src", "host:/dest", kind="sync")
    bundle = load_bundle(build_bundle([incoming], {}, app_version="8.2").text)
    external.create("Local", "./one", "host:/one", kind="sync")

    with pytest.raises(ValueError, match="changed after preview"):
        apply_profile_import(store, bundle, {incoming.id: "create"})


def test_selected_preferences_preserve_local_ids_notes_and_machine_binary():
    current = {
        "theme": "system",
        "language": "en",
        "binary": r"C:\local\mutagen.exe",
        "favorites": {"sync": ["local-id"], "forward": []},
        "session_prefs": {"local-id": {"note": "keep me", "notifications": False}},
    }
    imported = {"theme": "dark", "language": "cs", "binary": "/other/mutagen"}

    merged = selected_preferences(current, imported, {"theme", "language"})

    assert merged["theme"] == "dark"
    assert merged["language"] == "cs"
    assert merged["binary"] == current["binary"]
    assert merged["favorites"] == current["favorites"]
    assert merged["session_prefs"]["local-id"]["note"] == "keep me"
    assert merged["session_prefs"]["local-id"]["notifications"] is False


def test_legacy_settings_migration_has_exact_backup_and_rollback(tmp_path):
    path = tmp_path / "settings.json"
    original = b'{"theme":"dark","language":"cs","favorites":{"sync":["s1"],"forward":[]},"session_prefs":{"s1":{"note":"keep","notifications":false}}}\n'
    path.write_bytes(original)

    result = migrate_settings_file(path)

    assert result.migrated
    assert result.backup_path is not None
    assert result.backup_path.read_bytes() == original
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["theme"] == "dark"
    assert migrated["favorites"]["sync"] == ["s1"]
    assert migrated["session_prefs"]["s1"]["note"] == "keep"

    rollback_settings_migration(path, result.backup_path)
    assert path.read_bytes() == original


def test_invalid_or_future_settings_are_not_migrated(tmp_path):
    path = tmp_path / "settings.json"
    original = b'{"schema_version":999,"unknown":{"keep":true}}'
    path.write_bytes(original)

    with pytest.raises(OSError):
        migrate_settings_file(path)
    assert path.read_bytes() == original


def test_failed_settings_migration_restores_exact_original(tmp_path, monkeypatch):
    import settings as settings_module

    path = tmp_path / "settings.json"
    original = b'{"theme":"dark","unknown":{"preserve":true}}\n'
    path.write_bytes(original)

    def fail_after_write(target, _values):
        target.write_bytes(b"partial")
        raise OSError("simulated failed migration")

    monkeypatch.setattr(settings_module, "write_settings", fail_after_write)
    with pytest.raises(OSError, match="simulated failed migration"):
        migrate_settings_file(path)
    assert path.read_bytes() == original
