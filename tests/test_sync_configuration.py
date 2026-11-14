from sync_configuration import (
    SYNC_CONFIG_FIELDS,
    SyncConfigurationDraft,
    render_sync_reference,
    session_configuration_rows,
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
