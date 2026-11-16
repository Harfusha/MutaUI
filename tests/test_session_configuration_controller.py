import pytest

from forward_configuration import FORWARD_CONFIG_FIELDS
from mutaui.services.session_configuration import build_session_configuration_proposal
from sync_configuration import SYNC_CONFIG_FIELDS


def test_sync_proposal_controller_parses_and_validates_typed_values():
    fields = {field.key: field for field in SYNC_CONFIG_FIELDS}
    session = {"identifier": "exact-id"}

    proposal = build_session_configuration_proposal(
        "sync",
        session,
        fields,
        {
            "watch.pollingInterval": "30",
            "ignore.vcs": "TRUE",
            "ignore.paths": '["build/", "!build/keep.txt"]',
            "mode": "two-way-safe",
            "scanMode": "",
        },
    )

    assert proposal == {
        "watch.pollingInterval": 30,
        "ignore.vcs": True,
        "ignore.paths": ["build/", "!build/keep.txt"],
        "mode": "two-way-safe",
    }
    assert session == {"identifier": "exact-id"}


def test_forward_proposal_controller_keeps_validated_native_values():
    fields = {field.key: field for field in FORWARD_CONFIG_FIELDS}

    proposal = build_session_configuration_proposal(
        "forward",
        {"identifier": "exact-forward-id"},
        fields,
        {
            "source.socket.overwriteMode": "overwrite",
            "destination.socket.permissionMode": "0750",
        },
    )

    assert proposal == {
        "source.socket.overwriteMode": "overwrite",
        "destination.socket.permissionMode": "0750",
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ignore.vcs", "sometimes"),
        ("watch.pollingInterval", "not-an-integer"),
        ("ignore.paths", "not-json"),
    ],
)
def test_sync_proposal_controller_rejects_invalid_user_text(key, value):
    fields = {field.key: field for field in SYNC_CONFIG_FIELDS}

    with pytest.raises((ValueError, TypeError)):
        build_session_configuration_proposal("sync", {}, fields, {key: value})
