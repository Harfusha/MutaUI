"""Per-user single-instance request forwarding over a bounded local socket."""

from __future__ import annotations

import getpass
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MAX_MESSAGE_BYTES = 4096
_COMMAND_FIELDS = {
    "open_session": "session_id",
    "open_folder": "path",
    "open_project": "path",
    "doctor": None,
    "focus": None,
}


class InstanceLifecycleError(RuntimeError):
    """Raised when a request cannot be safely forwarded to the running app."""


def instance_socket_name(*, user_identity: str | None = None) -> str:
    """Use a non-identifying stable per-user namespace for local IPC."""
    identity = user_identity or (str(os.getuid()) if hasattr(os, "getuid") else getpass.getuser())
    suffix = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:20]
    return f"mutaui-v8-{suffix}"


def validate_instance_message(value: object) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        raise InstanceLifecycleError("Instance message must be a JSON object.")
    command = value.get("command")
    if not isinstance(command, str) or command not in _COMMAND_FIELDS:
        raise InstanceLifecycleError("Unsupported instance command.")
    field = _COMMAND_FIELDS[command]
    argument = value.get(field) if field else None
    if field and (
        not isinstance(argument, str)
        or not argument.strip()
        or len(argument.encode("utf-8")) > 2048
        or "\x00" in argument
        or argument.startswith("-")
        or (field == "path" and not Path(argument).is_absolute())
    ):
        raise InstanceLifecycleError("Instance command has an invalid exact argument.")
    if any(key not in {"command", field} for key in value):
        raise InstanceLifecycleError("Instance message contains unsupported fields.")
    return {"command": command, field: argument} if field else {"command": command}


class SingleInstanceBroker(QObject):
    """Hold the primary socket or forward one validated command to its owner."""

    request_received = Signal(object)

    def __init__(self, socket_name: str | None = None) -> None:
        super().__init__()
        self.socket_name = socket_name or instance_socket_name()
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.primary = False
        self._buffers: dict[int, bytearray] = {}

    def start_or_forward(self, message: Mapping[str, object], *, timeout_ms: int = 1500) -> bool:
        normalized = validate_instance_message(message)
        if self.server.listen(self.socket_name):
            self.primary = True
            self.server.newConnection.connect(self._accept_connections)
            return True
        socket = QLocalSocket(self)
        socket.connectToServer(self.socket_name)
        if not socket.waitForConnected(max(100, min(timeout_ms, 3000))):
            raise InstanceLifecycleError(
                "Could not reach the existing instance; its socket was retained for safety."
            )
        payload = (
            json.dumps(
                {**normalized, "request_id": uuid4().hex},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if len(payload) > MAX_MESSAGE_BYTES:
            socket.disconnectFromServer()
            raise InstanceLifecycleError("Instance message exceeds the byte limit.")
        if socket.write(payload) != len(payload) or not socket.waitForBytesWritten(timeout_ms):
            socket.abort()
            raise InstanceLifecycleError("Could not send request to the running instance.")
        if not socket.waitForReadyRead(timeout_ms):
            socket.abort()
            raise InstanceLifecycleError("Running instance did not acknowledge the request.")
        try:
            response = json.loads(bytes(socket.readAll()).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise InstanceLifecycleError(
                "Running instance returned an invalid acknowledgement."
            ) from exc
        if not isinstance(response, dict) or response.get("accepted") is not True:
            raise InstanceLifecycleError("Running instance refused the request.")
        return False

    def _accept_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            self._buffers[id(socket)] = bytearray()
            socket.readyRead.connect(lambda current=socket: self._read_request(current))
            socket.disconnected.connect(lambda current=socket: self._buffers.pop(id(current), None))

    def _read_request(self, socket: QLocalSocket) -> None:
        buffer = self._buffers.setdefault(id(socket), bytearray())
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > MAX_MESSAGE_BYTES:
            socket.write(b'{"accepted":false}\n')
            socket.disconnectFromServer()
            return
        if not buffer.endswith(b"\n"):
            return
        payload = bytes(buffer)
        if payload.count(b"\n") != 1:
            socket.write(b'{"accepted":false}\n')
            socket.disconnectFromServer()
            return
        try:
            raw = json.loads(payload.decode("utf-8"))
            request_id = raw.get("request_id") if isinstance(raw, dict) else None
            if not isinstance(request_id, str) or len(request_id) != 32:
                raise InstanceLifecycleError("Invalid request ID.")
            message = validate_instance_message(
                {key: value for key, value in raw.items() if key != "request_id"}
            )
            self.request_received.emit(message)
        except (UnicodeError, json.JSONDecodeError, InstanceLifecycleError):
            socket.write(b'{"accepted":false}\n')
            socket.disconnectFromServer()
            return
        socket.write(b'{"accepted":true}\n')
        socket.flush()
        socket.disconnectFromServer()

    def close(self) -> None:
        for socket in self.server.findChildren(QLocalSocket):
            socket.abort()
        self._buffers.clear()
        self.server.close()
        self.primary = False
