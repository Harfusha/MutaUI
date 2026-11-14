import pytest

from forward_configuration import (
    FORWARD_CONFIG_FIELDS,
    ForwardConfigurationDraft,
    forward_configuration_rows,
    is_unix_forward_endpoint,
    local_unix_socket_entry_type,
    render_forward_reference,
)


def test_forward_registry_has_help_and_gates_socket_capabilities():
    assert FORWARD_CONFIG_FIELDS
    assert all(
        field.help_short and field.help_full and field.impact for field in FORWARD_CONFIG_FIELDS
    )
    assert all("capability" in field.support_status for field in FORWARD_CONFIG_FIELDS)
    reference = render_forward_reference()
    assert all(f"`{field.key}`" in reference for field in FORWARD_CONFIG_FIELDS)


@pytest.mark.parametrize(
    "endpoint",
    [
        "unix:/tmp/source.sock",
        "operator@server:unix:/run/source.sock",
        "docker://web:unix:/run/source.sock",
    ],
)
def test_forward_endpoint_parser_recognizes_local_and_remote_unix_sockets(endpoint):
    assert is_unix_forward_endpoint(endpoint)


@pytest.mark.parametrize("endpoint", ["tcp:localhost:8080", "npipe:\\\\.\\pipe\\service"])
def test_forward_endpoint_parser_rejects_non_unix_transports(endpoint):
    assert not is_unix_forward_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "operator@server:unix:/run/source.sock",
        "docker://web:unix:/run/source.sock",
    ],
)
def test_local_unix_socket_inspector_does_not_probe_remote_endpoint_paths(endpoint):
    assert local_unix_socket_entry_type(endpoint) is None


def test_local_unix_socket_entry_inspector_reports_existing_entry_without_mutating(tmp_path):
    socket_path = tmp_path / "existing.sock"
    socket_path.write_text("keep me", encoding="utf-8")

    assert local_unix_socket_entry_type(f"unix:{socket_path}") == "file"
    assert socket_path.read_text(encoding="utf-8") == "keep me"
    assert local_unix_socket_entry_type(f"unix:{tmp_path / 'missing.sock'}") == "absent"


def test_local_unix_socket_entry_inspector_identifies_directory(tmp_path):
    directory = tmp_path / "existing-dir"
    directory.mkdir()

    assert local_unix_socket_entry_type(f"unix:{directory}") == "directory"


def test_rows_keep_native_values_read_only_and_proposal_separate():
    session = {
        "identifier": "forward-id",
        "configurationDestination": {
            "socket": {"overwriteMode": "leave", "permissionMode": "0600"}
        },
    }

    rows = {row.key: row for row in forward_configuration_rows(session)}

    assert rows["destination.socket.overwriteMode"].current_value == "leave"
    assert rows["destination.socket.permissionMode"].current_value == "0600"
    assert rows["source.socket.overwriteMode"].present is False
    assert rows["destination.socket.overwriteMode"].proposed_value is None


def test_rows_read_mutagens_flat_shared_socket_values_for_both_endpoints():
    session = {
        "identifier": "forward-id",
        "socket": {"overwriteMode": "overwrite", "owner": "operator"},
    }

    rows = {row.key: row for row in forward_configuration_rows(session)}

    assert rows["source.socket.overwriteMode"].current_value == "overwrite"
    assert rows["destination.socket.overwriteMode"].current_value == "overwrite"
    assert rows["source.socket.owner"].current_value == "operator"
    assert rows["destination.socket.owner"].current_value == "operator"
    assert "shared socket" in rows["source.socket.owner"].origin
    assert session["socket"] == {"overwriteMode": "overwrite", "owner": "operator"}


def test_forward_proposal_validation_does_not_mutate_native_session():
    session = {
        "identifier": "forward-id",
        "configurationDestination": {"socket": {"overwriteMode": "leave"}},
    }
    draft = ForwardConfigurationDraft(session)

    draft.propose("destination.socket.overwriteMode", "overwrite")
    draft.propose("destination.socket.permissionMode", "0660")

    assert draft.proposals == {
        "destination.socket.overwriteMode": "overwrite",
        "destination.socket.permissionMode": "0660",
    }
    assert session["configurationDestination"]["socket"]["overwriteMode"] == "leave"
