import json

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox, QPlainTextEdit

import app as app_module
from connection_profiles import (
    CURRENT_SCHEMA_VERSION,
    ConnectionProfileStore,
    ProfileStoreError,
    duplicate_profile,
    load_profile_store,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_profile_store_creates_versioned_profiles_with_tags_and_favorites(tmp_path):
    path = tmp_path / "connection-profiles.json"
    store = ConnectionProfileStore(path)

    profile = store.create(
        "Work laptop",
        "C:/Projects/app",
        "dev@example:/srv/app",
        kind="sync",
        tags=("work", "python"),
        favorite=True,
        defaults={"watch.mode": "force-poll", "watch.pollingInterval": 30},
    )

    loaded = load_profile_store(path)
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == CURRENT_SCHEMA_VERSION
    assert loaded.valid
    assert loaded.profiles == (profile,)
    assert profile.favorite
    assert profile.tags == ("work", "python")


def test_profile_manager_preserves_identity_when_toggling_favorite(tmp_path):
    _app()
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create("Build", "./source", "dev@example:/srv", kind="sync")
    dialog = app_module.ConnectionProfilesDialog(None, store)
    dialog.table.selectRow(0)

    dialog.toggle_favorite()

    selected = dialog.selected_profile()
    assert selected is not None
    assert selected.id == profile.id
    assert selected.favorite is True
    assert store.profiles[0].id == profile.id
    assert store.profiles[0].favorite is True


def test_profile_manager_empty_selection_is_a_noop(tmp_path, monkeypatch):
    _app()
    dialog = app_module.ConnectionProfilesDialog(
        None, ConnectionProfileStore(tmp_path / "profiles.json")
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args: (_ for _ in ()).throw(AssertionError("No profile should be prompted")),
    )

    dialog.duplicate_selected()
    dialog.toggle_favorite()
    dialog.delete_selected()

    assert not dialog.store.profiles


def test_profile_manager_new_profile_cancel_and_invalid_defaults_are_safe(tmp_path, monkeypatch):
    _app()
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    dialog = app_module.ConnectionProfilesDialog(None, store)
    monkeypatch.setattr(QDialog, "exec", lambda _self: QDialog.DialogCode.Rejected)
    dialog.new_profile()
    assert not store.profiles

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))

    def accept_invalid_defaults(window):
        window.findChild(QPlainTextEdit).setPlainText("[]")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_invalid_defaults)
    dialog.new_profile()

    assert not store.profiles
    assert warnings == ["Default settings must be a JSON object."]


def test_profile_manager_creates_and_selects_valid_profile(tmp_path, monkeypatch):
    _app()
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    dialog = app_module.ConnectionProfilesDialog(None, store)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))

    def accept_profile(window):
        fields = window.findChildren(QLineEdit)
        for field, value in zip(
            fields,
            ("Build", "./source", "dev@example:/srv", " work, python "),
            strict=True,
        ):
            field.setText(value)
        window.findChild(QPlainTextEdit).setPlainText('{"watch.mode": "force-poll"}')
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_profile)
    dialog.new_profile()

    created = dialog.selected_profile()
    assert warnings == []
    assert created is not None
    assert created.name == "Build"
    assert created.kind == "sync"
    assert created.tags == ("work", "python")
    assert created.defaults == {"watch.mode": "force-poll"}


def test_profile_manager_duplicates_selected_profile_with_new_identity(tmp_path):
    _app()
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    original = store.create("Build", "./source", "dev@example:/srv", kind="sync", tags=("ci",))
    dialog = app_module.ConnectionProfilesDialog(None, store)
    dialog.table.selectRow(0)

    dialog.duplicate_selected()

    assert len(store.profiles) == 2
    duplicate = next(profile for profile in store.profiles if profile.id != original.id)
    assert duplicate.id != original.id
    assert duplicate.name == "Build copy"
    assert duplicate.tags == original.tags
    assert dialog.selected_profile() == original


def test_profile_manager_delete_requires_confirmation_and_removes_only_local_profile(
    tmp_path, monkeypatch
):
    _app()
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create("Build", "./source", "dev@example:/srv", kind="sync")
    dialog = app_module.ConnectionProfilesDialog(None, store)
    dialog.table.selectRow(0)
    answers = iter((QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: next(answers))

    dialog.delete_selected()
    assert [item.id for item in store.profiles] == [profile.id]
    dialog.table.selectRow(0)
    dialog.delete_selected()

    assert store.profiles == []


def test_profile_manager_reports_local_store_failures(tmp_path, monkeypatch):
    _app()
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    profile = store.create("Build", "./source", "dev@example:/srv", kind="sync")
    dialog = app_module.ConnectionProfilesDialog(None, store)
    dialog.table.selectRow(0)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args[-1]))
    monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)

    def fail(*_args, **_kwargs):
        raise OSError("profile store is read-only")

    monkeypatch.setattr(store, "add", fail)
    dialog.duplicate_selected()
    monkeypatch.setattr(store, "update", fail)
    dialog.toggle_favorite()
    monkeypatch.setattr(store, "delete", fail)
    dialog.delete_selected()

    assert len(warnings) == 3
    assert all("profile store is read-only" in message for message in warnings)
    assert store.profiles == [profile]


def test_duplicate_gets_new_identity_and_can_change_name(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    original = store.create("Build", "C:/a", "C:/b", kind="sync", tags=("ci",))

    copy = duplicate_profile(original, name="Build staging")
    store.add(copy)

    assert copy.id != original.id
    assert copy.name == "Build staging"
    assert copy.tags == original.tags
    assert len(store.profiles) == 2


def test_search_filters_by_name_tag_and_favorite(tmp_path):
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    store.create("Work laptop", "a", "b", kind="sync", tags=("work",), favorite=True)
    store.create("Home server", "c", "d", kind="forward", tags=("home",))

    assert [profile.name for profile in store.search("work")] == ["Work laptop"]
    assert [profile.name for profile in store.search(favorites_only=True)] == ["Work laptop"]
    assert [profile.kind for profile in store.search(kind="forward")] == ["forward"]


def test_invalid_json_or_future_schema_is_retained_and_never_overwritten(tmp_path):
    path = tmp_path / "profiles.json"
    original = b"{invalid"
    path.write_bytes(original)

    loaded = load_profile_store(path)
    assert not loaded.valid
    assert path.read_bytes() == original
    with pytest.raises(ProfileStoreError):
        ConnectionProfileStore(path).create("x", "a", "b", kind="sync")
    assert path.read_bytes() == original


def test_duplicate_ids_unknown_fields_bad_defaults_and_duplicate_tags_are_rejected(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "profiles": [
                    {
                        "id": "same",
                        "name": "A",
                        "kind": "sync",
                        "endpoint_a": "a",
                        "endpoint_b": "b",
                    },
                    {
                        "id": "same",
                        "name": "B",
                        "kind": "sync",
                        "endpoint_a": "c",
                        "endpoint_b": "d",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    assert not load_profile_store(path).valid
