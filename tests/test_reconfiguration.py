from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mutaui.domain.models import SessionIdentity, SessionSnapshot
from mutaui.services.reconfiguration import (
    build_reconfiguration_preview,
    validate_native_command_snapshot,
)


def _snapshot(configuration: object, *, stale_reason: str | None = None) -> SessionSnapshot:
    return SessionSnapshot(
        identity=SessionIdentity("sync", "sync-exact-123", "source name"),
        native_config={
            "identifier": "sync-exact-123",
            "name": "source name",
            "labels": {"owner": "editor"},
            "configuration": configuration,
            "alpha": {"protocol": 0, "path": "C:/alpha"},
            "beta": {"protocol": 0, "path": "C:/beta"},
        },
        alpha_or_source=None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
        stale_reason=stale_reason,
    )


def _forward_snapshot(
    native_config: dict[str, object], *, identifier: str = "forward-exact-9"
) -> SessionSnapshot:
    return SessionSnapshot(
        identity=SessionIdentity("forward", identifier, "forward name"),
        native_config=native_config,
        alpha_or_source=None,
        beta_or_destination=None,
        state="forwarding",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )


def test_complete_command_snapshot_round_trips_losslessly_for_exact_id():
    snapshot = _snapshot({"mode": "two-way-safe", "watch": {"mode": "portable"}})

    result = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "--sync-mode=two-way-safe", "C:/alpha", "C:/beta"),
        command_target_identifier="sync-exact-123",
    )

    assert result.round_trip_valid
    assert result.command_snapshot_available
    assert result.command_snapshot_matches_target
    assert not result.unknown_configuration_paths
    assert result.snapshot_inputs_complete
    assert len(result.source_sha256) == 64


def test_missing_original_arguments_or_unknown_fields_fail_closed():
    snapshot = _snapshot({"mode": "two-way-safe", "experimentalMode": "future"})

    no_argv = validate_native_command_snapshot(
        snapshot, command_arguments=None, command_target_identifier="sync-exact-123"
    )
    unknown = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )

    assert not no_argv.snapshot_inputs_complete
    assert any("Original native create arguments" in item for item in no_argv.issues)
    assert unknown.unknown_configuration_paths == ("configuration.experimentalMode",)
    assert not unknown.snapshot_inputs_complete


def test_unknown_empty_configuration_group_fails_closed():
    snapshot = _snapshot({"mode": "two-way-safe", "experimental": {}})

    result = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )

    assert result.unknown_configuration_paths == ("configuration.experimental",)
    assert not result.snapshot_inputs_complete


def test_known_empty_endpoint_groups_remain_round_trippable():
    snapshot = SessionSnapshot(
        identity=SessionIdentity("sync", "flat-endpoint-001", "flat endpoint"),
        native_config={
            "identifier": "flat-endpoint-001",
            "name": "flat endpoint",
            "mode": "two-way-safe",
            "alpha": {
                "protocol": "local",
                "path": "/alpha",
                "ignore": {},
                "symlink": {},
            },
            "beta": {
                "protocol": "local",
                "path": "/beta",
                "ignore": {},
                "symlink": {},
            },
        },
        alpha_or_source=None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )

    result = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "/alpha", "/beta"),
        command_target_identifier="flat-endpoint-001",
    )

    assert result.unknown_configuration_paths == ()
    assert result.snapshot_inputs_complete


def test_command_snapshot_requires_exact_target_and_rejects_broad_args():
    snapshot = _snapshot({"mode": "two-way-safe"})

    mismatch = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="same-name-other-session",
    )
    broad = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "--all"),
        command_target_identifier="sync-exact-123",
    )

    assert not mismatch.command_snapshot_matches_target
    assert not mismatch.snapshot_inputs_complete
    assert any("broad targeting" in issue for issue in broad.issues)


def test_reconfiguration_preview_has_exact_structured_diff_and_never_executes():
    snapshot = _snapshot({"mode": "two-way-safe", "watch": {"mode": "portable"}})
    proposal = {"mode": "one-way-safe", "watch": {"mode": "portable"}}

    preview = build_reconfiguration_preview(
        snapshot,
        proposal,
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )

    assert preview.session_identifier == "sync-exact-123"
    assert [(item.path, item.current, item.proposed) for item in preview.changes] == [
        ("mode", "two-way-safe", "one-way-safe")
    ]
    assert preview.clears_sync_history
    assert preview.triggers_rescan
    assert not preview.execution_enabled
    assert snapshot.native_config["configuration"]["mode"] == "two-way-safe"


def test_stale_snapshot_and_non_json_proposal_are_refused():
    with pytest.raises(ValueError, match="stale"):
        build_reconfiguration_preview(_snapshot({}, stale_reason="stale"), {})
    with pytest.raises(ValueError, match="finite JSON"):
        build_reconfiguration_preview(_snapshot({}), {"invalid": float("nan")})


def test_flat_mutagen_list_export_is_read_for_config_and_unknown_roots_block():
    snapshot = SessionSnapshot(
        identity=SessionIdentity("sync", "flat-exact-001", "flat"),
        native_config={
            "identifier": "flat-exact-001",
            "name": "flat",
            "mode": "two-way-safe",
            "watch": {},
            "alpha": {"protocol": "local", "path": "/alpha", "watch": {}},
            "beta": {"protocol": "local", "path": "/beta", "watch": {}},
        },
        alpha_or_source=None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    preview = build_reconfiguration_preview(
        snapshot,
        {"mode": "one-way-safe"},
        command_arguments=("sync", "create", "/alpha", "/beta"),
        command_target_identifier="flat-exact-001",
    )
    assert [(change.path, change.current, change.proposed) for change in preview.changes] == [
        ("mode", "two-way-safe", "one-way-safe")
    ]

    unknown_snapshot = SessionSnapshot(
        identity=snapshot.identity,
        native_config={**dict(snapshot.native_config), "futureMode": "unknown"},
        alpha_or_source=None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    unknown_preview = build_reconfiguration_preview(
        unknown_snapshot,
        {"mode": "one-way-safe"},
        command_arguments=("sync", "create", "/alpha", "/beta"),
        command_target_identifier="flat-exact-001",
    )
    assert unknown_preview.validation.unknown_configuration_paths == ("futureMode",)
    assert not unknown_preview.validation.snapshot_inputs_complete


def test_forward_snapshot_validates_source_and_destination_independently():
    snapshot = _forward_snapshot(
        {
            "configurationSource": {"futureOption": True},
            "configurationDestination": "invalid-shape",
        }
    )

    result = validate_native_command_snapshot(
        snapshot,
        command_arguments=("forward", "create", "localhost:8000", "localhost:9000"),
        command_target_identifier="forward-exact-9",
    )

    assert result.round_trip_valid
    assert result.command_snapshot_matches_target
    assert result.unknown_configuration_paths == (
        "configurationDestination",
        "configurationSource.futureOption",
    )
    assert not result.snapshot_inputs_complete


def test_forward_preview_uses_forward_configuration_and_records_exact_differences():
    snapshot = _forward_snapshot(
        {
            "configuration": {"socket": {"overwriteMode": "leave"}},
            "configurationSource": {"socket": {"overwriteMode": "leave"}},
            "configurationDestination": None,
        }
    )

    preview = build_reconfiguration_preview(
        snapshot,
        {"socket": {"overwriteMode": "overwrite"}},
        command_arguments=("forward", "create", "source", "destination"),
        command_target_identifier="forward-exact-9",
    )

    assert preview.session_kind == "forward"
    assert not preview.clears_sync_history
    assert [(change.path, change.current, change.proposed) for change in preview.changes] == [
        ("socket.overwriteMode", "leave", "overwrite")
    ]
    assert preview.validation.unknown_configuration_paths == ()
    assert not preview.execution_enabled


def test_invalid_native_snapshot_and_empty_identifier_fail_closed():
    malformed = _snapshot({"mode": float("nan")})
    validation = validate_native_command_snapshot(
        malformed,
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )
    assert not validation.round_trip_valid
    assert not validation.source_sha256
    assert validation.issues

    without_id = SimpleNamespace(
        stale_reason=None,
        identity=SimpleNamespace(kind="sync", identifier=""),
    )
    with pytest.raises(ValueError, match="exact session identifier"):
        build_reconfiguration_preview(without_id, {})


def test_forward_preview_handles_unavailable_configuration_shape():
    snapshot = _forward_snapshot(
        {
            "configuration": "unavailable",
            "configurationSource": 42,
            "configurationDestination": None,
        }
    )

    preview = build_reconfiguration_preview(
        snapshot,
        {},
        command_arguments=("forward", "create", "source", "destination"),
        command_target_identifier="forward-exact-9",
    )

    assert preview.changes == ()
    assert preview.validation.unknown_configuration_paths == ("configurationSource",)
    assert not preview.validation.snapshot_inputs_complete


def test_sync_flat_export_reports_unknown_roots_and_endpoint_leaves():
    snapshot = replace(
        _snapshot({"mode": "two-way-safe"}),
        native_config={
            "identifier": "sync-exact-123",
            "name": "source name",
            "mode": "two-way-safe",
            "watch": {
                "mode": "portable",
                "pollingInterval": 1,
                "futureWatchOption": True,
            },
            "futureRoot": "unknown",
            "alpha": {
                "protocol": 0,
                "path": "C:/alpha",
                "watch": {"mode": "portable"},
                "futureEndpointOption": True,
            },
            "beta": "unavailable",
        },
    )

    result = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "C:/alpha", "C:/beta"),
        command_target_identifier="sync-exact-123",
    )

    assert result.unknown_configuration_paths == (
        "alpha.futureEndpointOption",
        "futureRoot",
        "watch.futureWatchOption",
    )
    assert not result.snapshot_inputs_complete

    preview = build_reconfiguration_preview(
        snapshot,
        {
            "mode": "one-way-safe",
            "watch": {"mode": "no-watch", "pollingInterval": 2},
        },
        command_arguments=("sync", "create", "C:/alpha", "C:/beta"),
        command_target_identifier="sync-exact-123",
    )
    changes = {change.path: (change.current, change.proposed) for change in preview.changes}
    assert changes["watch.mode"] == ("portable", "no-watch")
    assert changes["watch.pollingInterval"] == (1, 2)


def test_nested_non_json_configuration_is_reported_as_unknown():
    result = validate_native_command_snapshot(
        _snapshot("unsupported-shape"),
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )

    assert result.unknown_configuration_paths == ("configuration",)
    assert not result.snapshot_inputs_complete


def test_sync_unknown_leaf_marks_non_string_keys():
    snapshot = _snapshot({1: "unsupported-key"})

    result = validate_native_command_snapshot(
        snapshot,
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )

    assert result.unknown_configuration_paths == ("configuration.<non-string-key>",)


@pytest.mark.parametrize(
    "arguments", [(), ("sync", "create", "", "beta"), ("sync", "create", "alpha\x00", "beta")]
)
def test_command_snapshot_rejects_invalid_argument_lists(arguments):
    result = validate_native_command_snapshot(
        _snapshot({"mode": "two-way-safe"}),
        command_arguments=arguments,
        command_target_identifier="sync-exact-123",
    )

    assert not result.command_snapshot_available
    assert any("invalid argument list" in issue for issue in result.issues)


def test_preview_marks_added_removed_and_equal_configuration_fields():
    snapshot = _snapshot({"mode": "two-way-safe", "watch": {"mode": "portable"}})

    preview = build_reconfiguration_preview(snapshot, {"mode": "two-way-safe", "new": True})

    assert [(change.path, change.current, change.proposed) for change in preview.changes] == [
        ("new", "(Mutagen default or not reported)", True),
        ("watch.mode", "portable", "(removed in proposal)"),
    ]


def test_preview_canonicalizes_tuple_values_as_json_arrays():
    preview = build_reconfiguration_preview(
        _snapshot({"mode": "two-way-safe"}),
        {"extensions": ("md", "txt")},
    )

    assert preview.changes[0].proposed == ["md", "txt"]


def test_round_trip_comparison_mismatch_is_reported(monkeypatch):
    import mutaui.services.reconfiguration as reconfiguration

    original_canonical_json = reconfiguration._canonical_json
    calls = 0

    def mismatch_once(value):
        nonlocal calls
        calls += 1
        result = original_canonical_json(value)
        return f"{result} " if calls == 2 else result

    monkeypatch.setattr(reconfiguration, "_canonical_json", mismatch_once)
    result = validate_native_command_snapshot(
        _snapshot({"mode": "two-way-safe"}),
        command_arguments=("sync", "create", "alpha", "beta"),
        command_target_identifier="sync-exact-123",
    )

    assert not result.round_trip_valid
    assert any("changed during round-trip" in issue for issue in result.issues)
