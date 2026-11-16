import pytest

from forward_configuration import FORWARD_CONFIG_FIELDS
from mutaui.services.session_configuration import (
    build_session_arguments,
    build_session_configuration_proposal,
)
from sync_configuration import SYNC_CONFIG_FIELDS


def test_sync_proposal_parses_typed_values_and_ignores_empty_values():
    fields = {field.key: field for field in SYNC_CONFIG_FIELDS}
    sync_fields = {field.validation: field for field in SYNC_CONFIG_FIELDS}
    values = {
        sync_fields["positive-int"].key: " 12 ",
        sync_fields["bool"].key: " TRUE ",
        sync_fields["string-list"].key: '["*.tmp"]',
        sync_fields["yaml"].key: " value ",
    }
    values[next(field.key for field in SYNC_CONFIG_FIELDS if field.key not in values)] = "   "

    session = {"untouched": {"value": True}}
    proposal = build_session_configuration_proposal("sync", session, fields, values)

    assert proposal == {
        sync_fields["positive-int"].key: 12,
        sync_fields["bool"].key: True,
        sync_fields["string-list"].key: ["*.tmp"],
        sync_fields["yaml"].key: "value",
    }
    assert session == {"untouched": {"value": True}}


def test_forward_proposal_preserves_octal_mode_as_text():
    fields = {field.key: field for field in FORWARD_CONFIG_FIELDS}
    mode = next(field for field in FORWARD_CONFIG_FIELDS if field.validation == "octal-mode")

    proposal = build_session_configuration_proposal("forward", {}, fields, {mode.key: "0750"})

    assert proposal == {mode.key: "0750"}


@pytest.mark.parametrize(
    ("validation", "value"),
    [("bool", "yes"), ("positive-int", "0"), ("string-list", "not json")],
)
def test_sync_proposal_rejects_invalid_typed_values(validation, value):
    fields = {field.key: field for field in SYNC_CONFIG_FIELDS}
    field = next(field for field in SYNC_CONFIG_FIELDS if field.validation == validation)

    with pytest.raises((ValueError, TypeError)):
        build_session_configuration_proposal("sync", {}, fields, {field.key: value})


def test_sync_arguments_preserve_profile_ignore_and_endpoint_order():
    assert build_session_arguments(
        "sync",
        name=" demo ",
        paused=True,
        mode="two-way-safe",
        profile="events",
        ignore_vcs=False,
        ignore_patterns=[" *.tmp ", "", " logs/ "],
        alpha=" local/path ",
        beta=" remote/path ",
        socket_options={"source": (None, "", "", ""), "destination": (None, "", "", "")},
    ) == [
        "--name=demo",
        "--paused",
        "--mode=two-way-safe",
        "--watch-mode=portable",
        "--scan-mode=accelerated",
        "--no-ignore-vcs",
        "--ignore=*.tmp",
        "--ignore=logs/",
        "local/path",
        "remote/path",
    ]


def test_forward_unix_socket_arguments_keep_leave_default_and_explicit_options():
    assert build_session_arguments(
        "forward",
        name="",
        paused=False,
        mode="",
        profile="default",
        ignore_vcs=None,
        ignore_patterns=[],
        alpha="UNIX:/tmp/source",
        beta="remote/path",
        socket_options={
            "source": ("overwrite", " alice ", " staff ", " 0750 "),
            "destination": (None, "", "", ""),
        },
    ) == [
        "--socket-overwrite-mode=leave",
        "--socket-overwrite-mode-source=overwrite",
        "--socket-owner-source=alice",
        "--socket-group-source=staff",
        "--socket-permission-mode-source=0750",
        "UNIX:/tmp/source",
        "remote/path",
    ]
