"""Typed domain adapter preserves native identifiers and unknown fields."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mutaui.adapters.cli_executor import LegacyMutagenExecutor
from mutaui.adapters.mutagen_snapshot import from_legacy_session
from mutaui.domain.models import SessionConfiguration, SessionIdentity, _freeze

FIXTURE = Path(__file__).parent / "fixtures" / "mutagen_sync.json"
FORWARD_FIXTURE = Path(__file__).parent / "fixtures" / "mutagen_forward.json"


def test_golden_sync_snapshot_preserves_orientation_and_unknown_fields():
    native = json.loads(FIXTURE.read_text(encoding="utf-8"))
    measured_at = datetime(2026, 11, 12, tzinfo=UTC)

    snapshot = from_legacy_session("sync", native, measured_at=measured_at)

    assert snapshot.identity.identifier == "sync-golden-001"
    assert snapshot.identity.name == "duplicate names are allowed"
    assert snapshot.alpha_or_source.spec == r"C:\workspace\app"
    assert snapshot.beta_or_destination.spec == "dev@example.test:2202:/srv/app"
    assert snapshot.counters["files"] == 42
    assert snapshot.native_config["alphaFutureField"] == {"preserve": True}
    assert snapshot.measured_at == measured_at


def test_snapshot_ids_must_exist_but_names_need_not_be_unique():
    native = json.loads(FIXTURE.read_text(encoding="utf-8"))
    native.pop("identifier")

    with pytest.raises(ValueError, match="identifier"):
        from_legacy_session("sync", native, measured_at=datetime.now(UTC))


def test_snapshot_is_frozen_and_native_mapping_is_read_only():
    native = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshot = from_legacy_session("sync", native, measured_at=datetime.now(UTC))

    with pytest.raises((AttributeError, TypeError)):
        snapshot.identity.identifier = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        snapshot.native_config["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        snapshot.native_config["alphaFutureField"]["preserve"] = False  # type: ignore[index]


def test_forward_adapter_keeps_source_destination_orientation():
    native = json.loads(FORWARD_FIXTURE.read_text(encoding="utf-8"))

    snapshot = from_legacy_session("forward", native, measured_at=datetime.now(UTC))

    assert snapshot.identity.identifier == "forward-exact-id"
    assert snapshot.alpha_or_source.spec == "/local"
    assert snapshot.beta_or_destination.spec == "host.test:tcp:9000"


def test_adapter_rejects_invalid_label_shapes():
    native = json.loads(FIXTURE.read_text(encoding="utf-8"))
    native["labels"] = {"bad": 3}

    with pytest.raises(ValueError, match="labels"):
        from_legacy_session("sync", native, measured_at=datetime.now(UTC))


def test_recursive_freezer_handles_mappings_sequences_sets_and_scalars():
    frozen = _freeze({"items": [1, {"nested": {"keep"}}], "tuple": ("x",)})

    assert tuple(frozen["items"]) == (1, {"nested": frozenset({"keep"})})
    assert frozen["tuple"] == ("x",)
    assert _freeze(None) is None
    assert _freeze(3) == 3


def test_identity_requires_id_and_configuration_freezes_each_mapping():
    with pytest.raises(ValueError, match="identifier"):
        SessionIdentity("sync", "", "name")

    configuration = SessionConfiguration(
        common={"nested": [1]},
        endpoint_overrides={},
        provenance_map={},
        unknown_fields={},
    )

    assert configuration.common["nested"] == (1,)


def test_legacy_cli_adapter_keeps_argument_boundaries_and_options():
    class FakeClient:
        def __init__(self):
            self.calls = []

        def command(self, args, *, timeout, readonly):
            self.calls.append((args, timeout, readonly))
            return "native output"

    client = FakeClient()
    executor = LegacyMutagenExecutor(client, clock=lambda: 10.0)

    result = executor.run(["sync", "pause", "session id"], timeout_seconds=7, readonly=False)

    assert client.calls == [(["sync", "pause", "session id"], 7, False)]
    assert result.argv == ("sync", "pause", "session id")
    assert result.stdout == "native output"
    assert result.returncode == 0
    assert result.elapsed_seconds == 0

    with pytest.raises(ValueError, match="non-empty"):
        executor.run([], timeout_seconds=1)
    with pytest.raises(ValueError, match="non-empty"):
        executor.run(["sync", "\x00pause"], timeout_seconds=1)
