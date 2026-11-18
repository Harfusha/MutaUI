"""Real OpenSSH host-key checks, run by the Linux CI integration step."""

from __future__ import annotations

import getpass
import hashlib
import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

import ssh_profiles
from mutaui.services.remote_inspector import (
    ParamikoRemoteInspector,
    RemoteInspectionError,
    RemoteInspectionRequest,
)
from ssh_profiles import test_ssh_connection as check_ssh_connection


@dataclass
class OpenSSHFixture:
    sshd: str
    port: int
    work_dir: Path
    config_path: Path
    known_hosts_path: Path
    host_key_a: Path
    host_key_b: Path
    wrong_host_key: Path
    client_alias: str
    process: subprocess.Popen[bytes] | None = None

    # Executables come from shutil.which; every argument is fixture-owned.

    @property
    def known_hosts_name(self) -> str:
        return f"[127.0.0.1]:{self.port}"

    def start(self, host_key: Path) -> None:
        self.config_path.write_text(
            "\n".join(
                (
                    f"Port {self.port}",
                    "ListenAddress 127.0.0.1",
                    f"HostKey {host_key}",
                    f"PidFile {self.work_dir / 'sshd.pid'}",
                    f"AuthorizedKeysFile {self.work_dir / 'authorized_keys'}",
                    f"AllowUsers {getpass.getuser()}",
                    "PubkeyAuthentication yes",
                    "PasswordAuthentication no",
                    "KbdInteractiveAuthentication no",
                    "PermitRootLogin no",
                    "PermitTTY no",
                    "AllowTcpForwarding no",
                    "AllowAgentForwarding no",
                    "X11Forwarding no",
                    "Subsystem sftp internal-sftp",
                    "UsePAM no",
                    "UseDNS no",
                    "StrictModes no",
                    "LogLevel ERROR",
                    "",
                )
            ),
            encoding="utf-8",
        )
        subprocess.run(  # noqa: S603
            [self.sshd, "-t", "-f", str(self.config_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        self.process = subprocess.Popen(  # noqa: S603
            [self.sshd, "-D", "-e", "-f", str(self.config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.wait_until_ready()

    def wait_until_ready(self) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process is None or self.process.poll() is not None:
                raise AssertionError("OpenSSH test server exited before becoming ready")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise AssertionError("OpenSSH test server did not become ready")

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        self.process.wait(timeout=10)
        self.process = None

    def pin(self, key_path: Path) -> None:
        key_data = key_path.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.known_hosts_path.write_text(
            f"{self.known_hosts_name} {key_data[0]} {key_data[1]}\n",
            encoding="utf-8",
        )


@pytest.fixture
def openssh_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OpenSSHFixture:
    sshd = shutil.which("sshd")
    ssh = shutil.which("ssh")
    ssh_keygen = shutil.which("ssh-keygen")
    if not sshd or not ssh or not ssh_keygen:
        pytest.fail("OpenSSH server, client, and ssh-keygen are required for this CI test")

    ssh_dir = tmp_path / "home" / ".ssh"
    ssh_dir.mkdir(parents=True)
    ssh_dir.chmod(0o700)
    key_paths = {name: tmp_path / name for name in ("client", "host-a", "host-b", "wrong-host")}
    for key_path in key_paths.values():
        subprocess.run(  # noqa: S603
            [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key_path)],
            check=True,
            capture_output=True,
            text=True,
        )

    authorized_keys = tmp_path / "authorized_keys"
    authorized_keys.write_text(
        key_paths["client"].with_suffix(".pub").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    fixture = OpenSSHFixture(
        sshd=sshd,
        port=_available_port(),
        work_dir=tmp_path,
        config_path=tmp_path / "sshd_config",
        known_hosts_path=ssh_dir / "known_hosts",
        host_key_a=key_paths["host-a"],
        host_key_b=key_paths["host-b"],
        wrong_host_key=key_paths["wrong-host"],
        client_alias="mutaui-ssh-test",
    )

    config = ssh_dir / "config"
    config.write_text(
        "\n".join(
            (
                "Host mutaui-ssh-test",
                "  HostName 127.0.0.1",
                f"  Port {fixture.port}",
                f"  User {getpass.getuser()}",
                f"  IdentityFile {key_paths['client']}",
                "  IdentitiesOnly yes",
                f"  UserKnownHostsFile {fixture.known_hosts_path}",
                "  GlobalKnownHostsFile none",
                "",
            )
        ),
        encoding="utf-8",
    )
    config.chmod(0o600)
    run_ssh = ssh_profiles._run_ssh

    def run_ssh_with_fixture_config(
        argv: list[str], *, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return run_ssh([argv[0], "-F", str(config), *argv[1:]], timeout=timeout)

    monkeypatch.setattr(ssh_profiles, "_run_ssh", run_ssh_with_fixture_config)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SSH_AUTH_SOCK", "")
    try:
        fixture.start(fixture.host_key_a)
        yield fixture
    finally:
        fixture.stop()


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_real_ssh_rejects_wrong_key_and_accepts_pinned_key(
    openssh_server: OpenSSHFixture,
) -> None:
    server = openssh_server
    server.pin(server.wrong_host_key)

    wrong_key_result = check_ssh_connection(server.client_alias)

    assert not wrong_key_result.success
    assert wrong_key_result.host_key_error

    server.pin(server.host_key_a)
    verified_key_result = check_ssh_connection(server.client_alias)

    assert verified_key_result.success
    assert not verified_key_result.host_key_error


def test_real_ssh_rejects_changed_host_key(openssh_server: OpenSSHFixture) -> None:
    server = openssh_server
    server.pin(server.host_key_a)
    assert check_ssh_connection(server.client_alias).success

    server.stop()
    server.start(server.host_key_b)
    changed_key_result = check_ssh_connection(server.client_alias)

    assert not changed_key_result.success
    assert changed_key_result.host_key_error


def test_real_ssh_recovers_after_server_network_flap(openssh_server: OpenSSHFixture) -> None:
    server = openssh_server
    server.pin(server.host_key_a)
    assert check_ssh_connection(server.client_alias).success

    server.stop()
    disconnected = check_ssh_connection(server.client_alias)
    assert not disconnected.success
    assert not disconnected.host_key_error

    server.start(server.host_key_a)
    reconnected = check_ssh_connection(server.client_alias)
    assert reconnected.success
    assert not reconnected.host_key_error


@pytest.mark.parametrize(
    ("pinned_key", "expected_phase"),
    (("host_key_a", "completed"), ("wrong_host_key", "failed")),
)
def test_real_sftp_inspection_enforces_host_key_and_audits_read(
    openssh_server: OpenSSHFixture,
    tmp_path: Path,
    pinned_key: str,
    expected_phase: str,
) -> None:
    server = openssh_server
    server.pin(getattr(server, pinned_key))
    remote_root = tmp_path / "remote-endpoint"
    remote_root.mkdir()
    payload = b"conflict copy owned by this test\n"
    (remote_root / "conflict.txt").write_bytes(payload)
    audit_path = tmp_path / "remote-inspection.jsonl"
    request = RemoteInspectionRequest(
        hostname="127.0.0.1",
        username=getpass.getuser(),
        endpoint_root=remote_root.as_posix(),
        relative_path="conflict.txt",
        known_hosts_path=server.known_hosts_path,
        private_key_path=tmp_path / "client",
        port=server.port,
        max_bytes=1024,
        audit_path=audit_path,
    )

    inspector = ParamikoRemoteInspector()
    if expected_phase == "completed":
        with inspector.inspect(request, consent=True) as artifact:
            assert artifact.remote_path == f"{remote_root.as_posix()}/conflict.txt"
            assert artifact.local_path.read_bytes() == payload
            assert artifact.size_bytes == len(payload)
            assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
    else:
        with pytest.raises(RemoteInspectionError):
            inspector.inspect(request, consent=True)

    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["phase"] for record in records] == ["prepared", expected_phase]
    assert "username" not in records[-1]
    assert "remote_path" not in records[-1]
