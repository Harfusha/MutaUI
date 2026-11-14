import os
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

import mutaui.services.instance_lifecycle as lifecycle_module
from mutaui.services.instance_lifecycle import (
    MAX_MESSAGE_BYTES,
    InstanceLifecycleError,
    SingleInstanceBroker,
    instance_socket_name,
    validate_instance_message,
)

_APP: QApplication | None = None


def _application() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def test_single_instance_socket_name_is_stable_and_does_not_expose_user_identity():
    first = instance_socket_name(user_identity="user@example.test")
    second = instance_socket_name(user_identity="user@example.test")
    assert first == second
    assert "user@example.test" not in first


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"command": "focus"}, {"command": "focus"}),
        (
            {"command": "open_session", "session_id": "exact-id-1"},
            {"command": "open_session", "session_id": "exact-id-1"},
        ),
        (
            {"command": "open_folder", "path": "C:/Users/test/Sync"},
            {"command": "open_folder", "path": "C:/Users/test/Sync"},
        ),
    ],
)
def test_single_instance_messages_allow_only_named_routes(message, expected):
    assert validate_instance_message(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        {"command": "shell", "argv": ["cmd.exe"]},
        {"command": "open_session", "session_id": "--all"},
        {"command": "open_project", "path": "\x00"},
        {"command": "focus", "unexpected": "value"},
        [],
    ],
)
def test_single_instance_messages_reject_unknown_or_injected_arguments(message):
    with pytest.raises(InstanceLifecycleError):
        validate_instance_message(message)


def test_primary_server_acknowledges_and_emits_one_validated_request():
    app = _application()
    name = instance_socket_name(user_identity="test-" + uuid4().hex)
    primary = SingleInstanceBroker(name)
    received = []
    assert primary.start_or_forward({"command": "focus"})
    primary.request_received.connect(received.append)
    client = QLocalSocket()
    client.connectToServer(name)
    assert client.waitForConnected(1000)
    client.write(b'{"command":"doctor","request_id":"0123456789abcdef0123456789abcdef"}\n')
    client.flush()
    loop = QEventLoop()
    client.readyRead.connect(loop.quit)
    QTimer.singleShot(1500, loop.quit)
    loop.exec()

    assert b'"accepted":true' in bytes(client.readAll())
    assert received == [{"command": "doctor"}]
    client.abort()
    primary.close()
    QLocalServer.removeServer(name)
    assert app is not None


class _Signal:
    def connect(self, _callback):
        pass


class _Server:
    SocketOption = QLocalServer.SocketOption

    def __init__(self, *_args):
        self.newConnection = _Signal()

    def setSocketOptions(self, _options):
        pass

    def listen(self, _name):
        return False

    def close(self):
        pass

    def findChildren(self, _kind):
        return []


class _ForwardSocket:
    def __init__(
        self,
        *,
        connected=True,
        write_result=None,
        written=True,
        readable=True,
        response=b'{"accepted":true}',
    ):
        self.connected = connected
        self.write_result = write_result
        self.written = written
        self.readable = readable
        self.response = response
        self.payload = b""
        self.aborted = False
        self.disconnected = False

    def connectToServer(self, _name):
        pass

    def waitForConnected(self, _timeout):
        return self.connected

    def write(self, payload):
        self.payload = bytes(payload)
        return len(payload) if self.write_result is None else self.write_result

    def waitForBytesWritten(self, _timeout):
        return self.written

    def waitForReadyRead(self, _timeout):
        return self.readable

    def readAll(self):
        return self.response

    def disconnectFromServer(self):
        self.disconnected = True

    def abort(self):
        self.aborted = True


@pytest.mark.parametrize(
    ("socket", "error"),
    [
        (_ForwardSocket(connected=False), "Could not reach"),
        (_ForwardSocket(write_result=0), "Could not send"),
        (_ForwardSocket(written=False), "Could not send"),
        (_ForwardSocket(readable=False), "did not acknowledge"),
        (_ForwardSocket(response=b"not-json"), "invalid acknowledgement"),
        (_ForwardSocket(response=b"\xff"), "invalid acknowledgement"),
        (_ForwardSocket(response=b"{}"), "refused"),
        (_ForwardSocket(response=b"[]"), "refused"),
    ],
)
def test_forwarder_fails_closed_on_socket_and_acknowledgement_errors(monkeypatch, socket, error):
    _application()
    monkeypatch.setattr(lifecycle_module, "QLocalServer", _Server)
    monkeypatch.setattr(lifecycle_module, "QLocalSocket", lambda *_args: socket)
    broker = SingleInstanceBroker("fake-socket")

    with pytest.raises(InstanceLifecycleError, match=error):
        broker.start_or_forward({"command": "focus"})
    if not socket.connected:
        assert socket.payload == b""
    if not socket.written or socket.write_result == 0 or not socket.readable:
        assert socket.aborted


def test_forwarder_sends_one_bounded_request_and_accepts_exact_ack(monkeypatch):
    _application()
    monkeypatch.setattr(lifecycle_module, "QLocalServer", _Server)
    socket = _ForwardSocket()
    monkeypatch.setattr(lifecycle_module, "QLocalSocket", lambda *_args: socket)
    broker = SingleInstanceBroker("fake-socket")

    assert broker.start_or_forward({"command": "open_session", "session_id": "exact-id"}) is False
    assert socket.payload.endswith(b"\n")
    assert b'"session_id":"exact-id"' in socket.payload


def test_forwarder_disconnects_if_serialized_request_exceeds_wire_limit(monkeypatch):
    _application()
    monkeypatch.setattr(lifecycle_module, "QLocalServer", _Server)
    socket = _ForwardSocket()
    monkeypatch.setattr(lifecycle_module, "QLocalSocket", lambda *_args: socket)
    monkeypatch.setattr(lifecycle_module, "MAX_MESSAGE_BYTES", 20)
    broker = SingleInstanceBroker("fake-socket")

    with pytest.raises(InstanceLifecycleError, match="byte limit"):
        broker.start_or_forward({"command": "focus"})
    assert socket.disconnected
    assert not socket.aborted


def test_accept_connections_ignores_socket_created_without_pending_connection():
    broker = SingleInstanceBroker("reader-socket")

    class EmptyServer:
        pending = True

        def hasPendingConnections(self):
            return self.pending

        def nextPendingConnection(self):
            self.pending = False
            return None

    broker.server = EmptyServer()
    broker._accept_connections()
    assert broker._buffers == {}


class _ReadSocket:
    def __init__(self, *chunks):
        self.chunks = list(chunks)
        self.writes = []
        self.disconnected = False

    def readAll(self):
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, payload):
        self.writes.append(bytes(payload))
        return len(payload)

    def disconnectFromServer(self):
        self.disconnected = True

    def flush(self):
        pass


@pytest.mark.parametrize(
    "payload",
    [
        b"{" + b" " * MAX_MESSAGE_BYTES + b"}\n",
        b'{"request_id":"0123456789abcdef0123456789abcdef"}\n\n',
        b"not-json\n",
        b'{"command":"focus","request_id":"short"}\n',
        b'{"command":"unknown","request_id":"0123456789abcdef0123456789abcdef"}\n',
    ],
)
def test_primary_rejects_oversized_malformed_or_unapproved_requests(payload):
    broker = SingleInstanceBroker("reader-socket")
    socket = _ReadSocket(payload)

    broker._read_request(socket)

    assert socket.writes == [b'{"accepted":false}\n']
    assert socket.disconnected


def test_primary_waits_for_newline_before_accepting_a_split_request():
    _application()
    broker = SingleInstanceBroker("reader-socket")
    received = []
    broker.request_received.connect(received.append)
    request = b'{"command":"focus","request_id":"0123456789abcdef0123456789abcdef"}\n'
    socket = _ReadSocket(request[:20], request[20:])

    broker._read_request(socket)
    assert socket.writes == []
    broker._read_request(socket)

    assert received == [{"command": "focus"}]
    assert socket.writes == [b'{"accepted":true}\n']


def test_primary_server_close_disconnects_pending_local_clients():
    app = _application()
    name = instance_socket_name(user_identity="pending-" + uuid4().hex)
    primary = SingleInstanceBroker(name)
    client = QLocalSocket()
    assert primary.start_or_forward({"command": "focus"})
    client.connectToServer(name)
    assert client.waitForConnected(1000)
    assert primary.server.waitForNewConnection(1000)
    app.processEvents()
    assert primary.server.findChildren(QLocalSocket)

    primary.close()

    assert client.waitForDisconnected(1000)
    client.abort()
    primary.deleteLater()
    app.processEvents()
    QLocalServer.removeServer(name)
