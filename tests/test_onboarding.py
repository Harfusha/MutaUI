import json
import shutil
import struct
from pathlib import Path

import pytest

from mutagen_client import MutagenError
from mutaui.ui.onboarding import (
    detect_binary_architectures,
    host_architecture,
    inspect_cli,
    run_isolated_local_sync_test,
)


class FakeClient:
    binary = "C:\\fake\\mutagen.exe"

    def __init__(self):
        self.calls = []
        self.data_dir = ""
        self.name = ""

    def command(self, args, *, timeout=35, readonly=False, env_overrides=None):
        self.calls.append((args, timeout, readonly, env_overrides))
        if args == ["version"]:
            return "Mutagen version 0.18.1"
        if args in (["sync", "create", "--help"], ["forward", "create", "--help"]):
            return "Usage: mutagen\n--name\n--no-global-configuration"
        if args[0:2] == ["sync", "create"]:
            self.data_dir = env_overrides["MUTAGEN_DATA_DIRECTORY"]
            self.name = next(
                value.split("=", 1)[1] for value in args if value.startswith("--name=")
            )
            alpha, beta = Path(args[-2]), Path(args[-1])
            shutil.copy2(alpha / "onboarding-check.txt", beta / "onboarding-check.txt")
            return "created"
        if args == ["sync", "list", "--template", "{{ json . }}"]:
            return json.dumps([{"identifier": "sync_exact_id", "name": self.name}])
        return ""


def test_inspect_cli_uses_only_readonly_version_and_help_commands():
    client = FakeClient()

    result = inspect_cli(client)

    assert result.version == "Mutagen version 0.18.1"
    assert result.available
    assert "sync" in result.capabilities
    assert all(call[2] for call in client.calls)


def test_inspect_cli_returns_binary_architecture(monkeypatch):
    monkeypatch.setattr(
        "mutaui.ui.onboarding.detect_binary_architectures", lambda _path: ("x86_64",)
    )

    result = inspect_cli(FakeClient())

    assert result.architectures == ("x86_64",)


def test_host_architecture_uses_common_canonical_names(monkeypatch):
    monkeypatch.setattr("mutaui.ui.onboarding.platform.machine", lambda: "AMD64")

    assert host_architecture() == "x86_64"


def test_local_sync_smoke_uses_isolated_data_and_exact_id_cleanup():
    client = FakeClient()

    result = run_isolated_local_sync_test(client)

    assert "passed" in result.lower()
    assert client.data_dir
    create_call = next(call for call in client.calls if call[0][0:2] == ["sync", "create"])
    assert create_call[3]["MUTAGEN_DATA_DIRECTORY"] == client.data_dir
    assert any(call[0] == ["sync", "terminate", "sync_exact_id"] for call in client.calls)
    assert any(call[0] == ["daemon", "stop"] for call in client.calls)


def test_missing_cli_reports_install_help_without_running_commands():
    client = FakeClient()
    client.binary = ""

    result = inspect_cli(client)

    assert not result.available
    assert result.capabilities == ()
    assert client.calls == []


def test_detect_pe_architecture(tmp_path):
    raw = bytearray(0x80)
    raw[:2] = b"MZ"
    raw[0x3C:0x40] = struct.pack("<I", 0x80)
    raw.extend(b"PE\0\0" + struct.pack("<H", 0x8664))
    path = tmp_path / "mutagen.exe"
    path.write_bytes(raw)

    assert detect_binary_architectures(path) == ("x86_64",)


def test_detect_elf_architecture(tmp_path):
    raw = bytearray(20)
    raw[:4] = b"\x7fELF"
    raw[4:6] = b"\x02\x01"
    raw[18:20] = struct.pack("<H", 0xB7)
    path = tmp_path / "mutagen"
    path.write_bytes(raw)

    assert detect_binary_architectures(path) == ("arm64",)


def test_detect_fat_macho_architectures(tmp_path):
    raw = bytearray(b"\xca\xfe\xba\xbe" + struct.pack(">I", 2))
    raw.extend(struct.pack(">iiIII", 0x01000007, 0, 64, 32, 0))
    raw.extend(struct.pack(">iiIII", 0x0100000C, 0, 96, 32, 0))
    path = tmp_path / "mutagen"
    path.write_bytes(raw)

    assert detect_binary_architectures(path) == ("arm64", "x86_64")


def test_detect_thin_macho_architecture(tmp_path):
    raw = b"\xfe\xed\xfa\xcf" + struct.pack(">I", 0x01000007) + bytes(24)
    path = tmp_path / "mutagen"
    path.write_bytes(raw)

    assert detect_binary_architectures(path) == ("x86_64",)


@pytest.mark.parametrize(
    "raw",
    [
        b"not a binary",
        b"MZ" + bytes(62) + struct.pack("<I", 17 * 1024 * 1024),
        b"\x7fELF" + bytes([2, 0]) + bytes(14),
        b"\x7fELF" + bytes([2, 1]) + bytes(12) + struct.pack("<H", 999),
        b"\xca\xfe\xba\xbe" + struct.pack(">I", 0),
        b"\xca\xfe\xba\xbe" + struct.pack(">I", 1) + b"short",
    ],
)
def test_detect_binary_architecture_fails_closed_for_unknown_or_truncated_headers(tmp_path, raw):
    path = tmp_path / "unknown"
    path.write_bytes(raw)

    assert detect_binary_architectures(path) == ()


def test_detect_short_pe_header_fails_closed(tmp_path):
    path = tmp_path / "truncated.exe"
    path.write_bytes(b"MZ")

    assert detect_binary_architectures(path) == ()


def test_local_sync_smoke_rejects_missing_cli_and_cleans_only_temp_daemon():
    class FailedClient(FakeClient):
        binary = ""

    with pytest.raises(MutagenError, match="CLI was not found"):
        run_isolated_local_sync_test(FailedClient())

    class CreateFailure(FakeClient):
        def command(self, args, **kwargs):
            self.calls.append(
                (args, kwargs.get("timeout"), kwargs.get("readonly"), kwargs.get("env_overrides"))
            )
            if args[0:2] == ["sync", "create"]:
                raise MutagenError("create denied")
            return ""

    client = CreateFailure()
    with pytest.raises(MutagenError, match="create denied"):
        run_isolated_local_sync_test(client)
    assert client.calls[-1][0] == ["daemon", "stop"]
    assert not any(call[0][0:2] == ["sync", "terminate"] for call in client.calls)


def test_architecture_detection_treats_missing_binary_as_unknown(tmp_path):
    assert detect_binary_architectures(tmp_path / "missing-mutagen") == ()


def test_inspect_cli_keeps_available_capability_when_other_help_fails():
    class PartialHelp(FakeClient):
        def command(self, args, **kwargs):
            if args == ["sync", "create", "--help"]:
                raise MutagenError("sync help unavailable")
            return super().command(args, **kwargs)

    result = inspect_cli(PartialHelp())

    assert result.available
    assert result.capabilities == ("forward",)
    assert "sync: sync help unavailable" in result.error


def test_local_sync_smoke_refuses_ambiguous_created_session_id():
    class NoIdentifier(FakeClient):
        def command(self, args, **kwargs):
            if args == ["sync", "list", "--template", "{{ json . }}"]:
                self.calls.append(
                    (
                        args,
                        kwargs.get("timeout"),
                        kwargs.get("readonly"),
                        kwargs.get("env_overrides"),
                    )
                )
                return "[]"
            return super().command(args, **kwargs)

    client = NoIdentifier()
    with pytest.raises(MutagenError, match="Could not identify the isolated test session"):
        run_isolated_local_sync_test(client)

    assert client.calls[-1][0] == ["daemon", "stop"]
    assert not any(call[0][0:2] == ["sync", "terminate"] for call in client.calls)


def test_local_sync_smoke_waits_for_delayed_transfer_marker(tmp_path, monkeypatch):
    client = FakeClient()
    path_type = type(tmp_path)
    original_is_file = path_type.is_file
    delayed_once = [False]

    def delay_marker(candidate):
        if candidate.name == "onboarding-check.txt" and not delayed_once[0]:
            delayed_once[0] = True
            return False
        return original_is_file(candidate)

    monkeypatch.setattr(path_type, "is_file", delay_marker)

    result = run_isolated_local_sync_test(client)

    assert "passed" in result.lower()
    assert delayed_once[0]


def test_local_sync_smoke_times_out_and_cleans_isolated_session(monkeypatch):
    client = FakeClient()
    times = iter((100.0, 111.0))
    monkeypatch.setattr("mutaui.ui.onboarding.time.monotonic", lambda: next(times))
    monkeypatch.setattr("mutaui.ui.onboarding.time.sleep", lambda _seconds: None)
    original_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda candidate: (
            False if candidate.name == "onboarding-check.txt" else original_is_file(candidate)
        ),
    )

    with pytest.raises(MutagenError, match="did not transfer its test file"):
        run_isolated_local_sync_test(client)

    assert client.calls[-2][0] == ["sync", "terminate", "sync_exact_id"]
    assert client.calls[-1][0] == ["daemon", "stop"]


def test_detect_pe_with_out_of_bounds_header_fails_closed(tmp_path):
    path = tmp_path / "oversized.exe"
    raw = bytearray(64)
    raw[:2] = b"MZ"
    struct.pack_into("<I", raw, 0x3C, 16 * 1024 * 1024 + 1)
    path.write_bytes(raw)
    assert detect_binary_architectures(path) == ()
