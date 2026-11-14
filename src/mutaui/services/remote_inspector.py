"""Opt-in, bounded, read-only SSH/SFTP conflict-file inspection."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import importlib
import json
import math
import os
import posixpath
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from uuid import uuid4


class RemoteInspectionError(ValueError):
    """Raised when remote conflict inspection cannot stay within its trust scope."""


class SFTPFile(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def close(self) -> None: ...


class SFTPClient(Protocol):
    def normalize(self, path: str) -> str: ...

    def lstat(self, path: str) -> Any: ...

    def open(self, path: str, mode: str) -> SFTPFile: ...

    def get_channel(self) -> Any: ...

    def close(self) -> None: ...


class SSHClient(Protocol):
    def load_host_keys(self, filename: str) -> None: ...

    def set_missing_host_key_policy(self, policy: object) -> None: ...

    def connect(self, hostname: str, **kwargs: object) -> None: ...

    def open_sftp(self) -> SFTPClient: ...

    def get_transport(self) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RemoteInspectionRequest:
    hostname: str
    username: str
    endpoint_root: str
    relative_path: str
    known_hosts_path: Path
    private_key_path: Path
    port: int = 22
    max_bytes: int = 2 * 1024 * 1024
    timeout_seconds: float = 10.0
    audit_path: Path | None = None


@dataclass(slots=True)
class RemoteInspectionArtifact:
    local_path: Path
    remote_path: str
    size_bytes: int
    sha256: str
    is_text: bool
    modified_time: int | None
    host_key_sha256: str
    _temporary_directory: tempfile.TemporaryDirectory[str]

    @property
    def temporary_root(self) -> Path:
        return Path(self._temporary_directory.name)

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def __enter__(self) -> RemoteInspectionArtifact:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _append_audit(path: Path, record: dict[str, object]) -> None:
    payload = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
    try:
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise RemoteInspectionError("Remote inspection audit could not be persisted.") from exc


def _checked_path(endpoint_root: str, relative_path: str) -> tuple[str, tuple[str, ...]]:
    if (
        not endpoint_root.startswith("/")
        or "\x00" in endpoint_root
        or "\\" in endpoint_root
        or not relative_path
        or "\x00" in relative_path
        or "\\" in relative_path
    ):
        raise RemoteInspectionError(
            "A POSIX endpoint root and conflict-relative path are required."
        )
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
        raise RemoteInspectionError("Remote conflict path must stay under its endpoint root.")
    if ".." in PurePosixPath(endpoint_root).parts:
        raise RemoteInspectionError("Remote endpoint root is invalid.")
    root = posixpath.normpath(endpoint_root)
    return root, relative.parts


class ParamikoRemoteInspector:
    """Read one regular conflict file using an explicit SSH key and known_hosts."""

    def __init__(self, client_factory: Callable[[], SSHClient] | None = None) -> None:
        self._client_factory = client_factory

    def inspect(
        self, request: RemoteInspectionRequest, *, consent: bool
    ) -> RemoteInspectionArtifact:
        if not consent:
            raise RemoteInspectionError("Explicit consent is required before remote file access.")
        if type(request.port) is not int or not (1 <= request.port <= 65535):
            raise RemoteInspectionError("SSH port is outside the valid range.")
        if type(request.max_bytes) is not int or not (1 <= request.max_bytes <= 16 * 1024 * 1024):
            raise RemoteInspectionError("Remote file size limit must be between 1 byte and 16 MiB.")
        if (
            isinstance(request.timeout_seconds, bool)
            or not isinstance(request.timeout_seconds, (int, float))
            or not math.isfinite(request.timeout_seconds)
            or not (1 <= request.timeout_seconds <= 30)
        ):
            raise RemoteInspectionError(
                "Remote inspection timeout must be between 1 and 30 seconds."
            )
        if not request.hostname or request.hostname.startswith("-") or not request.username:
            raise RemoteInspectionError("An explicit SSH host and username are required.")
        if request.audit_path is None:
            raise RemoteInspectionError("A local audit path is required before remote inspection.")
        audit_path = request.audit_path.expanduser().absolute()
        if audit_path.is_symlink() or (audit_path.exists() and not audit_path.is_file()):
            raise RemoteInspectionError(
                "Remote inspection audit path must be a regular local file."
            )
        if not audit_path.parent.is_dir():
            raise RemoteInspectionError("Remote inspection audit directory must already exist.")
        known_hosts = request.known_hosts_path.expanduser().absolute()
        private_key = request.private_key_path.expanduser().absolute()
        for path, label in ((known_hosts, "known_hosts"), (private_key, "private key")):
            if path.is_symlink() or not path.is_file():
                raise RemoteInspectionError(f"A regular local {label} file is required.")
        root, parts = _checked_path(request.endpoint_root, request.relative_path)
        target_hash = hashlib.sha256(
            f"{request.hostname}\0{root}\0{'/'.join(parts)}".encode()
        ).hexdigest()
        event_id = uuid4().hex
        audit_common = {
            "event_id": event_id,
            "host_sha256": hashlib.sha256(request.hostname.encode("utf-8")).hexdigest(),
            "remote_target_sha256": target_hash,
        }
        _append_audit(
            audit_path,
            {**audit_common, "phase": "prepared", "timestamp": datetime.now(UTC).isoformat()},
        )
        if self._client_factory is None:
            try:
                paramiko = importlib.import_module("paramiko")
            except ImportError as exc:
                _append_audit(
                    audit_path,
                    {
                        **audit_common,
                        "phase": "failed",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error_type": type(exc).__name__,
                    },
                )
                raise RemoteInspectionError(
                    "Remote inspection requires the optional Paramiko runtime dependency."
                ) from exc
            factory: Callable[[], SSHClient] = paramiko.SSHClient
            reject_policy: object = paramiko.RejectPolicy()
        else:
            factory = self._client_factory
            reject_policy = _RejectUnknownHostKey()

        client = factory()
        temporary_directory = tempfile.TemporaryDirectory(prefix="mutaui-remote-inspect-")
        artifact: RemoteInspectionArtifact | None = None
        sftp: SFTPClient | None = None
        try:
            client.load_host_keys(str(known_hosts))
            client.set_missing_host_key_policy(reject_policy)
            client.connect(
                request.hostname,
                port=request.port,
                username=request.username,
                key_filename=str(private_key),
                allow_agent=False,
                look_for_keys=False,
                timeout=request.timeout_seconds,
                banner_timeout=request.timeout_seconds,
                auth_timeout=request.timeout_seconds,
                channel_timeout=request.timeout_seconds,
            )
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                raise RemoteInspectionError("SSH transport is not active.")
            host_key = transport.get_remote_server_key()
            host_key_fingerprint = (
                base64.b64encode(hashlib.sha256(host_key.asbytes()).digest())
                .decode("ascii")
                .rstrip("=")
            )
            sftp = client.open_sftp()
            sftp.get_channel().settimeout(request.timeout_seconds)
            root_stat = sftp.lstat(root)
            if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
                raise RemoteInspectionError("Remote endpoint root must be a real directory.")
            canonical_root = posixpath.normpath(sftp.normalize(root))
            current = canonical_root
            for index, part in enumerate(parts):
                current = posixpath.join(current, part)
                metadata = sftp.lstat(current)
                if stat.S_ISLNK(metadata.st_mode):
                    raise RemoteInspectionError("Remote conflict path crosses a symbolic link.")
                if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                    raise RemoteInspectionError("Remote conflict path has a non-directory parent.")
            normalized = posixpath.normpath(sftp.normalize(current))
            if posixpath.commonpath((canonical_root, normalized)) != canonical_root:
                raise RemoteInspectionError("Resolved remote path escaped the endpoint root.")
            metadata = sftp.lstat(normalized)
            if not stat.S_ISREG(metadata.st_mode):
                raise RemoteInspectionError("Only a regular remote conflict file can be inspected.")
            if metadata.st_size < 0 or metadata.st_size > request.max_bytes:
                raise RemoteInspectionError(
                    "Remote conflict file exceeds the configured size limit."
                )

            local_path = Path(temporary_directory.name) / "remote-conflict-copy"
            digest = hashlib.sha256()
            total = 0
            remote_file = sftp.open(normalized, "rb")
            try:
                with local_path.open("xb") as output:
                    while True:
                        chunk = remote_file.read(min(65536, request.max_bytes - total + 1))
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > request.max_bytes:
                            raise RemoteInspectionError(
                                "Remote conflict changed or exceeded the size limit during read."
                            )
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            finally:
                remote_file.close()
            local_path.chmod(stat.S_IREAD)
            if total != metadata.st_size:
                raise RemoteInspectionError("Remote conflict changed during inspection.")
            current_metadata = sftp.lstat(normalized)
            if (
                current_metadata.st_size != metadata.st_size
                or getattr(current_metadata, "st_mtime", None)
                != getattr(metadata, "st_mtime", None)
                or current_metadata.st_mode != metadata.st_mode
            ):
                raise RemoteInspectionError("Remote conflict metadata changed during inspection.")
            payload = local_path.read_bytes()
            try:
                payload.decode("utf-8")
                is_text = b"\x00" not in payload
            except UnicodeDecodeError:
                is_text = False
            artifact = RemoteInspectionArtifact(
                local_path,
                normalized,
                total,
                digest.hexdigest(),
                is_text,
                getattr(metadata, "st_mtime", None),
                host_key_fingerprint,
                temporary_directory,
            )
            _append_audit(
                audit_path,
                {
                    **audit_common,
                    "phase": "completed",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "size_bytes": total,
                    "content_sha256": artifact.sha256,
                    "host_key_sha256": host_key_fingerprint,
                },
            )
            return artifact
        except RemoteInspectionError as exc:
            temporary_directory.cleanup()
            _append_audit(
                audit_path,
                {
                    **audit_common,
                    "phase": "failed",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error_type": type(exc).__name__,
                },
            )
            raise
        except Exception as exc:
            temporary_directory.cleanup()
            _append_audit(
                audit_path,
                {
                    **audit_common,
                    "phase": "failed",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error_type": type(exc).__name__,
                },
            )
            raise RemoteInspectionError(
                f"Remote inspection failed safely: {type(exc).__name__}."
            ) from exc
        finally:
            if sftp is not None:
                with contextlib.suppress(Exception):
                    sftp.close()
            with contextlib.suppress(Exception):
                client.close()


class _RejectUnknownHostKey:
    def missing_host_key(self, _client: object, hostname: str, _key: object) -> None:
        raise RemoteInspectionError(f"SSH host key for {hostname} is not trusted.")
