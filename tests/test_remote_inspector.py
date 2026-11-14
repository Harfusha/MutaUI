import json
import stat
from io import BytesIO
from types import SimpleNamespace

import pytest

from mutaui.services.remote_inspector import (
    ParamikoRemoteInspector,
    RemoteInspectionError,
    RemoteInspectionRequest,
)


class FakeSFTP:
    def __init__(self, payload=b"remote contents", *, link_path=None, grow=False):
        self.payload = payload
        self.link_path = link_path
        self.grow = grow
        self.opened = []
        self.stat_count = 0

    def normalize(self, path):
        import posixpath

        return posixpath.normpath(path)

    def lstat(self, path):
        if path == self.link_path:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_size=0, st_mtime=10)
        is_dir = path in {"/srv", "/srv/sub"}
        size = len(self.payload)
        self.stat_count += 1
        if self.grow and self.stat_count >= 4:
            size += 1
        return SimpleNamespace(
            st_mode=stat.S_IFDIR if is_dir else stat.S_IFREG | 0o600,
            st_size=0 if is_dir else size,
            st_mtime=10,
        )

    def open(self, path, mode):
        self.opened.append((path, mode))
        return BytesIO(self.payload)

    def get_channel(self):
        return SimpleNamespace(settimeout=lambda _value: None)

    def close(self):
        pass


class FakeClient:
    def __init__(self, sftp=None):
        self.sftp = sftp or FakeSFTP()
        self.calls = []
        self.policy = None

    def load_host_keys(self, filename):
        self.calls.append(("known_hosts", filename))

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, hostname, **kwargs):
        self.calls.append(("connect", hostname, kwargs))

    def get_transport(self):
        return SimpleNamespace(
            is_active=lambda: True,
            get_remote_server_key=lambda: SimpleNamespace(asbytes=lambda: b"host-key"),
        )

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.calls.append(("closed",))


def _request(tmp_path, **changes):
    known_hosts = tmp_path / "known_hosts"
    private_key = tmp_path / "id_key"
    known_hosts.write_text("trusted host key", encoding="utf-8")
    private_key.write_text("private key placeholder", encoding="utf-8")
    values = {
        "hostname": "sync-host",
        "username": "tester",
        "endpoint_root": "/srv",
        "relative_path": "sub/file.txt",
        "known_hosts_path": known_hosts,
        "private_key_path": private_key,
        "audit_path": tmp_path / "remote-inspection.jsonl",
    }
    values.update(changes)
    return RemoteInspectionRequest(**values)


def test_remote_read_requires_explicit_opt_in_and_audit_before_network(tmp_path):
    client = FakeClient()
    inspector = ParamikoRemoteInspector(lambda: client)
    request = _request(tmp_path)

    with pytest.raises(RemoteInspectionError, match="Explicit consent"):
        inspector.inspect(request, consent=False)
    assert not client.calls
    assert not request.audit_path.exists()


def test_remote_read_uses_verified_host_key_bounded_read_and_private_temp_copy(tmp_path):
    client = FakeClient()
    request = _request(tmp_path)

    with ParamikoRemoteInspector(lambda: client).inspect(request, consent=True) as artifact:
        assert artifact.local_path.read_bytes() == b"remote contents"
        assert artifact.size_bytes == len(b"remote contents")
        assert artifact.remote_path == "/srv/sub/file.txt"
        assert artifact.host_key_sha256
        assert artifact.temporary_root == artifact.local_path.parent
        assert client.sftp.opened == [("/srv/sub/file.txt", "rb")]
        connect = next(call for call in client.calls if call[0] == "connect")
        assert connect[2]["allow_agent"] is False
        assert connect[2]["look_for_keys"] is False
        assert len(request.audit_path.read_text(encoding="utf-8").splitlines()) == 2
        assert "sub/file.txt" not in request.audit_path.read_text(encoding="utf-8")
        temp_path = artifact.local_path

    assert not temp_path.exists()
    events = [json.loads(line) for line in request.audit_path.read_text().splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "completed"]


def test_remote_inspector_rejects_size_limit_traversal_symlink_and_untrusted_host(tmp_path):
    request = _request(tmp_path, max_bytes=4)
    client = FakeClient()
    with pytest.raises(RemoteInspectionError, match="size limit"):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)
    assert not client.sftp.opened

    with pytest.raises(RemoteInspectionError, match="stay under"):
        ParamikoRemoteInspector(lambda: FakeClient()).inspect(
            _request(tmp_path, relative_path="../secret"), consent=True
        )

    symlinked = FakeClient(FakeSFTP(link_path="/srv/sub"))
    with pytest.raises(RemoteInspectionError, match="symbolic link"):
        ParamikoRemoteInspector(lambda: symlinked).inspect(_request(tmp_path), consent=True)

    # The injected policy mirrors Paramiko RejectPolicy's fail-closed contract.
    from mutaui.services.remote_inspector import _RejectUnknownHostKey

    with pytest.raises(RemoteInspectionError, match="not trusted"):
        _RejectUnknownHostKey().missing_host_key(None, "unknown", None)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"port": True}, "port is outside"),
        ({"port": 65536}, "port is outside"),
        ({"max_bytes": 0}, "size limit must be"),
        ({"max_bytes": 16 * 1024 * 1024 + 1}, "size limit must be"),
        ({"timeout_seconds": True}, "timeout must be"),
        ({"timeout_seconds": float("nan")}, "timeout must be"),
        ({"timeout_seconds": 31}, "timeout must be"),
        ({"hostname": "-option"}, "explicit SSH host"),
        ({"username": ""}, "explicit SSH host"),
        ({"audit_path": None}, "local audit path"),
        ({"endpoint_root": "relative"}, "POSIX endpoint root"),
        ({"relative_path": "/absolute/file"}, "stay under"),
        ({"relative_path": "sub/../secret"}, "stay under"),
    ],
)
def test_remote_inspection_rejects_invalid_request_before_connect(tmp_path, changes, message):
    client = FakeClient()

    with pytest.raises(RemoteInspectionError, match=message):
        ParamikoRemoteInspector(lambda: client).inspect(_request(tmp_path, **changes), consent=True)

    assert not any(call[0] == "connect" for call in client.calls)


@pytest.mark.parametrize("endpoint_root", ["/srv/..", "/srv/../other", "/../etc"])
def test_remote_endpoint_root_rejects_parent_components(endpoint_root):
    from mutaui.services.remote_inspector import _checked_path

    with pytest.raises(RemoteInspectionError, match="endpoint root is invalid"):
        _checked_path(endpoint_root, "sub/file.txt")


def test_remote_inspector_rejects_inactive_transport_and_closes_client(tmp_path):
    class InactiveClient(FakeClient):
        def get_transport(self):
            return SimpleNamespace(is_active=lambda: False)

    client = InactiveClient()
    request = _request(tmp_path)

    with pytest.raises(RemoteInspectionError, match="transport is not active"):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)

    assert ("closed",) in client.calls
    events = [json.loads(line) for line in request.audit_path.read_text().splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "failed"]


@pytest.mark.parametrize("field", ["known_hosts_path", "private_key_path"])
def test_remote_inspector_requires_existing_local_trust_files(tmp_path, field):
    client = FakeClient()
    request = _request(tmp_path, **{field: tmp_path / "missing-file"})

    with pytest.raises(RemoteInspectionError, match="regular local"):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)

    assert not client.calls


@pytest.mark.parametrize("audit_kind", ["directory", "missing_parent"])
def test_remote_inspector_requires_safe_existing_audit_parent(tmp_path, audit_kind):
    client = FakeClient()
    audit_path = (
        tmp_path / "audit-dir"
        if audit_kind == "directory"
        else tmp_path / "missing" / "audit.jsonl"
    )
    if audit_kind == "directory":
        audit_path.mkdir()
    request = _request(tmp_path, audit_path=audit_path)

    with pytest.raises(RemoteInspectionError, match="audit"):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)

    assert not client.calls


def test_remote_inspector_audit_write_failure_blocks_remote_access(tmp_path, monkeypatch):
    import mutaui.services.remote_inspector as remote_module

    client = FakeClient()
    request = _request(tmp_path)

    def fail_fsync(_fd):
        raise OSError("disk full")

    monkeypatch.setattr(remote_module.os, "fsync", fail_fsync)
    with pytest.raises(RemoteInspectionError, match="audit could not be persisted"):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)

    assert not client.calls


def test_remote_inspector_reports_missing_optional_paramiko_dependency(tmp_path, monkeypatch):
    import mutaui.services.remote_inspector as remote_module

    def missing_dependency(_name):
        raise ImportError("not installed")

    monkeypatch.setattr(remote_module.importlib, "import_module", missing_dependency)
    request = _request(tmp_path)

    with pytest.raises(RemoteInspectionError, match="optional Paramiko"):
        ParamikoRemoteInspector().inspect(request, consent=True)

    events = [json.loads(line) for line in request.audit_path.read_text().splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "failed"]


@pytest.mark.parametrize(
    "failure", ["root_link", "root_file", "parent_file", "file_link", "file_dir"]
)
def test_remote_inspector_rejects_unsafe_remote_file_types(tmp_path, failure):
    class UnsafeSFTP(FakeSFTP):
        def lstat(self, path):
            if failure == "root_link" and path == "/srv":
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_size=0, st_mtime=10)
            if failure == "root_file" and path == "/srv":
                return SimpleNamespace(st_mode=stat.S_IFREG, st_size=0, st_mtime=10)
            if failure == "parent_file" and path == "/srv/sub":
                return SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_mtime=10)
            if failure == "file_link" and path == "/srv/sub/file.txt":
                return SimpleNamespace(st_mode=stat.S_IFLNK, st_size=0, st_mtime=10)
            if failure == "file_dir" and path == "/srv/sub/file.txt":
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_size=0, st_mtime=10)
            return super().lstat(path)

    client = FakeClient(UnsafeSFTP())
    request = _request(tmp_path)

    with pytest.raises(RemoteInspectionError):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)

    assert not client.sftp.opened
    assert ("closed",) in client.calls


def test_remote_inspector_rejects_server_normalization_outside_endpoint_root(tmp_path):
    class EscapingSFTP(FakeSFTP):
        def normalize(self, path):
            if path == "/srv":
                return "/srv"
            return "/outside/file.txt"

    client = FakeClient(EscapingSFTP())

    with pytest.raises(RemoteInspectionError, match="escaped the endpoint root"):
        ParamikoRemoteInspector(lambda: client).inspect(_request(tmp_path), consent=True)

    assert not client.sftp.opened


def test_remote_inspector_rejects_file_growth_during_bounded_read(tmp_path):
    class UnderreportingSFTP(FakeSFTP):
        def lstat(self, path):
            result = super().lstat(path)
            if path == "/srv/sub/file.txt":
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_size=4,
                    st_mtime=result.st_mtime,
                )
            return result

    client = FakeClient(UnderreportingSFTP(payload=b"12345"))
    request = _request(tmp_path, max_bytes=4)

    with pytest.raises(RemoteInspectionError, match="during read"):
        ParamikoRemoteInspector(lambda: client).inspect(request, consent=True)

    assert client.sftp.opened
    assert ("closed",) in client.calls


def test_remote_inspector_rejects_size_and_metadata_changes_after_read(tmp_path):
    growing = FakeClient(FakeSFTP(payload=b"short", grow=True))
    with pytest.raises(RemoteInspectionError, match="changed during inspection"):
        ParamikoRemoteInspector(lambda: growing).inspect(_request(tmp_path), consent=True)

    class ChangingMetadata(FakeSFTP):
        def lstat(self, path):
            result = super().lstat(path)
            if path == "/srv/sub/file.txt" and self.stat_count >= 5:
                return SimpleNamespace(
                    st_mode=result.st_mode,
                    st_size=result.st_size,
                    st_mtime=result.st_mtime + 1,
                )
            return result

    changed = FakeClient(ChangingMetadata())
    request = _request(tmp_path, audit_path=tmp_path / "changed-audit.jsonl")
    with pytest.raises(RemoteInspectionError, match="metadata changed"):
        ParamikoRemoteInspector(lambda: changed).inspect(request, consent=True)


def test_remote_inspector_marks_binary_payload_and_cleans_up_on_connect_error(tmp_path):
    binary = FakeClient(FakeSFTP(payload=b"\xff\x00binary"))
    with ParamikoRemoteInspector(lambda: binary).inspect(
        _request(tmp_path), consent=True
    ) as artifact:
        assert not artifact.is_text

    class FailingClient(FakeClient):
        def connect(self, _hostname, **_kwargs):
            raise OSError("network unavailable")

    failing = FailingClient()
    request = _request(tmp_path, audit_path=tmp_path / "failed-audit.jsonl")
    with pytest.raises(RemoteInspectionError, match="failed safely: OSError"):
        ParamikoRemoteInspector(lambda: failing).inspect(request, consent=True)

    assert ("closed",) in failing.calls
    events = [json.loads(line) for line in request.audit_path.read_text().splitlines()]
    assert [event["phase"] for event in events] == ["prepared", "failed"]


def test_remote_inspector_uses_optional_paramiko_factory_when_injected_absent(
    tmp_path, monkeypatch
):
    import mutaui.services.remote_inspector as remote_module

    client = FakeClient()
    paramiko = SimpleNamespace(SSHClient=lambda: client, RejectPolicy=lambda: object())
    monkeypatch.setattr(remote_module.importlib, "import_module", lambda _name: paramiko)

    with ParamikoRemoteInspector().inspect(_request(tmp_path), consent=True) as artifact:
        assert artifact.size_bytes == len(b"remote contents")

    assert client.policy is not None
