from types import SimpleNamespace

import pytest

import sync_configuration as sync_configuration_module
from sync_configuration import (
    SYNC_CONFIG_FIELDS,
    SyncConfigurationDraft,
    build_effective_forward_configuration,
    build_effective_sync_configuration,
    load_effective_forward_configuration,
    load_effective_sync_configuration,
    render_sync_reference,
    session_configuration_rows,
    validate_sync_proposal,
)


def test_registry_has_complete_help_and_no_invented_support_claims():
    assert SYNC_CONFIG_FIELDS
    assert all(field.label and field.help_short and field.help_full for field in SYNC_CONFIG_FIELDS)
    assert all(
        field.support_status == "requires capability verification" for field in SYNC_CONFIG_FIELDS
    )
    reference = render_sync_reference()
    assert all(f"`{field.key}`" in reference for field in SYNC_CONFIG_FIELDS)


def test_rows_show_current_native_value_origin_and_creation_time_lock():
    session = {
        "identifier": "exact-id",
        "name": "Example",
        "watch": {"mode": 1, "pollingInterval": 20},
        "scanMode": 2,
        "futureField": {"keep": True},
    }

    rows = {row.key: row for row in session_configuration_rows(session)}

    assert rows["watch.mode"].current_value == 1
    assert rows["watch.mode"].origin == "Mutagen session export; inheritance origin unknown"
    assert rows["watch.mode"].editable_via_replacement
    assert rows["watch.mode"].proposed_value is None
    assert rows["scanMode"].current_value == 2
    assert not rows["mode"].present


def test_endpoint_specific_overrides_are_separate_from_common_values():
    rows = {
        row.key: row
        for row in session_configuration_rows(
            {"watch": {"mode": 1}, "alpha": {"watch": {"mode": 2}}, "beta": {}}
        )
    }

    assert rows["watch.mode"].current_value == 1
    assert rows["alpha.watch.mode"].current_value == 2
    assert not rows["beta.watch.mode"].present
    assert rows["alpha.watch.mode"].endpoint == "ALPHA"
    assert "alpha.permissions.defaultFileMode" in rows
    assert "beta.compression.algorithm" in rows


def test_draft_validates_and_stages_proposals_without_mutating_session():
    session = {"identifier": "exact-id", "watch": {"mode": 1, "pollingInterval": 20}}
    original = {"identifier": "exact-id", "watch": {"mode": 1, "pollingInterval": 20}}
    draft = SyncConfigurationDraft(session)

    draft.propose("watch.mode", "force-poll")
    draft.propose("watch.pollingInterval", 30)

    assert draft.proposals == {"watch.mode": "force-poll", "watch.pollingInterval": 30}
    assert session == original


def test_invalid_proposal_is_rejected_and_does_not_touch_existing_proposal():
    draft = SyncConfigurationDraft({"identifier": "exact-id"})
    draft.propose("watch.mode", "portable")

    try:
        draft.propose("watch.pollingInterval", 0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("zero polling interval must be rejected")

    assert draft.proposals == {"watch.mode": "portable"}


def test_effective_sync_configuration_merges_cli_overrides_and_ignore_paths():
    result = build_effective_sync_configuration(
        b"sync:\n  defaults:\n    watch:\n      mode: portable\n    ignore:\n      paths: [vendor]\n",
        ["--mode=two-way-safe", "--watch-polling-interval=12", "--ignore=build", "--ignore-vcs"],
        source_path="config.yml",
    )

    assert result.valid
    assert result.source_path == "config.yml"
    assert result.as_mapping() == {
        "watch.mode": "portable",
        "ignore.paths": ["vendor", "build"],
        "mode": "two-way-safe",
        "watch.pollingInterval": 12,
        "ignore.vcs": True,
    }
    assert result.origin_for("ignore.paths") == "global config + command line (appended)"

    without_inherited = build_effective_sync_configuration(None, ["--ignore=build"])
    assert without_inherited.origin_for("ignore.paths") == "command line"

    empty_mapping = build_effective_sync_configuration(b"sync:\n  defaults:\n    watch: {}\n", [])
    assert empty_mapping.as_mapping() == {"watch": {}}


@pytest.mark.parametrize(
    ("source", "arguments", "error"),
    [
        (b"invalid: [", [], ""),
        (b"sync: []", [], "mapping"),
        (b"sync:\n  defaults: []\n", [], "mapping"),
        (b"sync:\n  defaults:\n    ignore: []\n", [], "ignore"),
        (b"sync:\n  defaults:\n    ignore:\n      paths: [2]\n", [], "list of strings"),
        (b"sync:\n  defaults:\n    1: value\n", [], "keys must be strings"),
        (None, ["--watch-polling-interval=x"], "integer"),
        (
            b"sync:\n  defaults:\n    ignore:\n      paths: bad\n",
            ["--ignore=build"],
            "list of strings",
        ),
    ],
)
def test_effective_sync_configuration_rejects_malformed_sources_and_overrides(
    source, arguments, error
):
    result = build_effective_sync_configuration(source, arguments)

    assert not result.valid
    assert error in result.error


def test_empty_global_sync_defaults_and_numeric_nested_keys():
    empty = build_effective_sync_configuration(b"sync:\n  defaults: {}\n", [])
    assert empty.valid and empty.values == ()

    malformed = build_effective_sync_configuration(b"sync:\n  defaults:\n    1: invalid\n", [])
    assert not malformed.valid and "keys must be strings" in malformed.error


def test_command_ignore_refuses_invalid_inherited_paths_even_after_yaml_parse(monkeypatch):
    class DivergentPaths(dict):
        def get(self, key, default=None):
            return [] if key == "paths" else super().get(key, default)

    monkeypatch.setattr(
        sync_configuration_module,
        "parse_yaml_bytes",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            document={"sync": {"defaults": {"ignore": DivergentPaths(paths="invalid")}}},
            error="",
        ),
    )

    result = build_effective_sync_configuration(b"valid yaml", ["--ignore=build"])

    assert not result.valid and "Inherited `ignore.paths`" in result.error


def test_no_global_configuration_ignores_broken_yaml_and_load_reports_file_errors(
    tmp_path, monkeypatch
):
    ignored = build_effective_sync_configuration(b"sync: [", ["--no-global-configuration"])
    assert ignored.valid and ignored.values == ()

    missing = load_effective_sync_configuration(tmp_path / "missing.yml", [])
    assert missing.valid

    def denied(_self):
        raise PermissionError("denied")

    monkeypatch.setattr(type(tmp_path / "denied.yml"), "read_bytes", denied)
    denied_result = load_effective_sync_configuration(tmp_path / "denied.yml", [])
    assert not denied_result.valid and "Could not read" in denied_result.error


def test_effective_forward_configuration_reports_global_validation_and_nested_defaults():
    absent = build_effective_forward_configuration(None, [])
    assert absent.valid and absent.values == ()

    merged = build_effective_forward_configuration(
        b"forward:\n  defaults:\n    socket:\n      owner: adam\n",
        [],
        source_path="global.yml",
    )
    assert merged.valid and merged.as_mapping() == {"socket.owner": "adam"}

    invalid = build_effective_forward_configuration(b"forward: []", [])
    assert not invalid.valid and "mapping" in invalid.error

    skipped = build_effective_forward_configuration(b"forward: [", ["--no-global-configuration"])
    assert skipped.valid and skipped.values == ()

    invalid_defaults = build_effective_forward_configuration(b"forward:\n  defaults: []\n", [])
    assert not invalid_defaults.valid and "defaults" in invalid_defaults.error

    invalid_key = build_effective_forward_configuration(
        b"forward:\n  defaults:\n    1: invalid\n", []
    )
    assert not invalid_key.valid and "keys must be strings" in invalid_key.error


def test_forward_configuration_load_reports_unreadable_file(tmp_path, monkeypatch):
    def denied(_self):
        raise PermissionError("denied")

    monkeypatch.setattr(type(tmp_path / "denied.yml"), "read_bytes", denied)
    result = load_effective_forward_configuration(tmp_path / "denied.yml", [])
    assert not result.valid and "Could not read" in result.error

    def no_error_detail(_self):
        raise OSError()

    monkeypatch.setattr(type(tmp_path / "denied.yml"), "read_bytes", no_error_detail)
    fallback = load_effective_forward_configuration(tmp_path / "denied.yml", [])
    assert not fallback.valid and "OSError" in fallback.error


@pytest.mark.parametrize(
    ("validation", "invalid"),
    [
        ("positive-int", True),
        ("nonnegative-int", -1),
        ("bool", "yes"),
        ("string-list", ["ok", 1]),
        ("octal-mode", "888"),
        ("nonempty-string", "  "),
        ("options", "unsupported-choice"),
    ],
)
def test_sync_proposal_validators_reject_wrong_types_and_ranges(validation, invalid):
    field = next(
        field
        for field in SYNC_CONFIG_FIELDS
        if (field.validation == validation if validation != "options" else field.options)
    )

    with pytest.raises(ValueError):
        validate_sync_proposal(field.key, invalid)


def test_sync_proposal_rejects_unknown_fields():
    with pytest.raises(ValueError, match="Unsupported"):
        validate_sync_proposal("future.option", "value")
    with pytest.raises(ValueError, match="Unsupported"):
        SyncConfigurationDraft({}).propose("future.option", "value")
