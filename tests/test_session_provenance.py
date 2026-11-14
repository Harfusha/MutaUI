import json

import pytest

from mutaui.services.session_provenance import (
    ProvenanceStoreError,
    SessionProvenanceStore,
)


def test_exact_creation_provenance_round_trips_by_native_identifier(tmp_path):
    path = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(path)
    argv = (
        "sync",
        "create",
        "--name=workspace",
        "--mode=two-way-safe",
        "C:/work",
        "user@example.test:/srv/work",
    )

    store.record("sync_native_123", argv)

    record = SessionProvenanceStore(path).get("sync_native_123")
    assert record is not None
    assert record.session_identifier == "sync_native_123"
    assert record.create_arguments == argv


@pytest.mark.parametrize(
    "argv",
    [
        ("sync", "pause", "sync_native_123"),
        ("sync", "create", "--all", "C:/work", "/srv/work"),
        ("sync", "create", "--password=secret", "C:/work", "/srv/work"),
        ("sync", "create", "--configuration-file=C:/private.yml", "C:/work", "/srv/work"),
    ],
)
def test_provenance_store_rejects_non_create_broad_or_sensitive_argv(tmp_path, argv):
    store = SessionProvenanceStore(tmp_path / "session-provenance.json")

    with pytest.raises(ProvenanceStoreError):
        store.record("sync_native_123", argv)


def test_provenance_store_fails_closed_on_malformed_file(tmp_path):
    path = tmp_path / "session-provenance.json"
    path.write_text(json.dumps({"schema_version": 99, "records": {}}), encoding="utf-8")

    with pytest.raises(ProvenanceStoreError, match="unsupported"):
        SessionProvenanceStore(path).get("sync_native_123")


def test_provenance_store_caps_record_count_and_preserves_existing_records(tmp_path):
    path = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(path)
    store.record("sync_native_1", ("sync", "create", "/alpha", "/beta"))
    store.record("sync_native_2", ("sync", "create", "/gamma", "/delta"))

    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    assert set(records) == {"sync_native_1", "sync_native_2"}
    assert store.get("sync_native_1") is not None
    assert store.get("sync_native_2") is not None


def test_missing_store_returns_no_provenance(tmp_path):
    assert SessionProvenanceStore(tmp_path / "missing.json").get("sync_native_123") is None


@pytest.mark.parametrize(
    "identifier",
    ["", "  ", "-sync_native_123", "sync native", "sync\x00native", "x" * 2049, None, 123],
)
def test_store_rejects_invalid_identifiers(tmp_path, identifier):
    with pytest.raises(ProvenanceStoreError):
        SessionProvenanceStore(tmp_path / "session-provenance.json").record(
            identifier, ("sync", "create", "/alpha", "/beta")
        )


def test_record_is_idempotent_but_refuses_different_arguments(tmp_path):
    store = SessionProvenanceStore(tmp_path / "session-provenance.json")
    args = ("sync", "create", "/alpha", "/beta")
    store.record("sync_native_123", args)
    store.record("sync_native_123", args)

    with pytest.raises(ProvenanceStoreError, match="already exists"):
        store.record("sync_native_123", ("sync", "create", "/other", "/beta"))


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        "sync create /alpha /beta",
        ("sync", "create", "/alpha"),
        ("sync", "create", "/alpha", "/beta", *(["x"] * 253)),
        ("sync", "create", "/alpha", 7),
        ("sync", "create", "/alpha", ""),
        ("sync", "create", "/alpha", "bad\x00path"),
        ("sync", "create", "/alpha", "x" * 16385),
        ("SYNC", "create", "/alpha", "/beta"),
        ("sync", "create", "--ALL=true", "/alpha", "/beta"),
        ("forward", "create", "--TOKEN=secret", "/alpha", "/beta"),
        ("sync", "create", "password =secret", "/alpha", "/beta"),
    ],
)
def test_store_rejects_invalid_or_unbounded_create_arguments(tmp_path, arguments):
    with pytest.raises(ProvenanceStoreError):
        SessionProvenanceStore(tmp_path / "session-provenance.json").record(
            "sync_native_123", arguments
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": 1},
        {"schema_version": 1, "records": []},
        {"schema_version": 1, "records": {"sync_native_123": None}},
        {
            "schema_version": 1,
            "records": {
                "sync_native_123": {
                    "create_arguments": ["sync", "create", "/a", "/b"],
                    "created_at": "now",
                    "integrity_sha256": "0" * 64,
                    "unexpected": True,
                }
            },
        },
    ],
)
def test_store_rejects_invalid_payload_and_record_shapes(tmp_path, payload):
    path = tmp_path / "session-provenance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceStoreError):
        SessionProvenanceStore(path).get("sync_native_123")


@pytest.mark.parametrize("created_at", [None, 7, "x" * 65])
def test_store_rejects_invalid_timestamps(tmp_path, created_at):
    path = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(path)
    store.record("sync_native_123", ("sync", "create", "/a", "/b"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"]["sync_native_123"]["created_at"] = created_at
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceStoreError, match="timestamp"):
        store.get("sync_native_123")


@pytest.mark.parametrize("digest", [None, 7, "Z" * 64, "short"])
def test_store_rejects_invalid_integrity_digest_shape(tmp_path, digest):
    path = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(path)
    store.record("sync_native_123", ("sync", "create", "/a", "/b"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"]["sync_native_123"]["integrity_sha256"] = digest
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceStoreError, match="digest"):
        store.get("sync_native_123")


def test_store_rejects_integrity_mismatch(tmp_path):
    path = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(path)
    store.record("sync_native_123", ("sync", "create", "/a", "/b"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"]["sync_native_123"]["created_at"] = "changed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceStoreError, match="integrity check"):
        store.get("sync_native_123")


def test_store_rejects_write_when_record_limit_is_reached(tmp_path, monkeypatch):
    import mutaui.services.session_provenance as provenance

    monkeypatch.setattr(provenance, "MAX_RECORDS", 0)
    with pytest.raises(ProvenanceStoreError, match="full"):
        SessionProvenanceStore(tmp_path / "session-provenance.json").record(
            "sync_native_123", ("sync", "create", "/alpha", "/beta")
        )


def test_store_rejects_oversized_file(tmp_path, monkeypatch):
    import mutaui.services.session_provenance as provenance

    path = tmp_path / "session-provenance.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(provenance, "MAX_STORE_BYTES", 1)

    with pytest.raises(ProvenanceStoreError, match="size limit"):
        SessionProvenanceStore(path).get("sync_native_123")


def test_write_rechecks_symlink_before_replacing_store(tmp_path, monkeypatch):
    from pathlib import Path

    store = SessionProvenanceStore(tmp_path / "session-provenance.json")
    original = Path.is_symlink
    calls = 0

    def symlink_on_write(path):
        nonlocal calls
        calls += 1
        return calls == 2 or original(path)

    monkeypatch.setattr(Path, "is_symlink", symlink_on_write)
    with pytest.raises(ProvenanceStoreError, match="symbolic link"):
        store.record("sync_native_123", ("sync", "create", "/alpha", "/beta"))


def test_write_failure_before_temp_file_creation_is_wrapped(tmp_path, monkeypatch):
    import mutaui.services.session_provenance as provenance

    def fail_create(**kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr(provenance.tempfile, "NamedTemporaryFile", fail_create)
    with pytest.raises(ProvenanceStoreError, match="Could not save"):
        SessionProvenanceStore(tmp_path / "session-provenance.json").record(
            "sync_native_123", ("sync", "create", "/alpha", "/beta")
        )


def test_read_rejects_symlink_path(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_symlink", lambda _path: True)
    with pytest.raises(ProvenanceStoreError, match="symbolic link"):
        SessionProvenanceStore(tmp_path / "session-provenance.json").get("sync_native_123")


def test_read_wraps_invalid_utf8_and_malformed_json(tmp_path):
    path = tmp_path / "session-provenance.json"
    store = SessionProvenanceStore(path)
    for content in (b"\xff", b"{"):
        path.write_bytes(content)
        with pytest.raises(ProvenanceStoreError, match="unreadable or malformed"):
            store.get("sync_native_123")


def test_write_sets_private_permissions_on_posix(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import mutaui.services.session_provenance as provenance

    chmod_calls = []
    original_os = provenance.os
    monkeypatch.setattr(
        provenance,
        "os",
        SimpleNamespace(
            name="posix",
            chmod=lambda path, mode: chmod_calls.append((path, mode)),
            fsync=original_os.fsync,
            replace=original_os.replace,
        ),
    )
    SessionProvenanceStore(tmp_path / "session-provenance.json").record(
        "sync_native_123", ("sync", "create", "/alpha", "/beta")
    )

    assert len(chmod_calls) == 1
    assert chmod_calls[0][1] == provenance.stat.S_IRUSR | provenance.stat.S_IWUSR
