"""Safe Mutagen CLI discovery and an explicitly initiated local-only smoke test."""

from __future__ import annotations

import contextlib
import platform
import struct
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from mutagen_client import MutagenClient, MutagenError, parse_sessions


@dataclass(frozen=True, slots=True)
class CLIDiscovery:
    binary: str
    version: str
    capabilities: tuple[str, ...]
    error: str = ""
    architectures: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.binary and self.version)


def inspect_cli(client: MutagenClient) -> CLIDiscovery:
    """Read version and command help only; never start or contact a daemon."""
    if not client.binary:
        return CLIDiscovery("", "", (), "Mutagen CLI was not found.")
    architectures = detect_binary_architectures(client.binary)
    try:
        version = client.command(["version"], timeout=5, readonly=True)
    except MutagenError as exc:
        return CLIDiscovery(client.binary, "", (), str(exc), architectures)

    capabilities: list[str] = []
    errors: list[str] = []
    for kind in ("sync", "forward"):
        try:
            client.command([kind, "create", "--help"], timeout=5, readonly=True)
        except MutagenError as exc:
            errors.append(f"{kind}: {exc}")
        else:
            capabilities.append(kind)
    return CLIDiscovery(
        client.binary, version, tuple(capabilities), "; ".join(errors), architectures
    )


def detect_binary_architectures(path: str | Path) -> tuple[str, ...]:
    """Read PE, ELF, or Mach-O headers; return empty when format is unknown."""
    pe_architectures = {
        0x014C: "x86",
        0x01C0: "arm",
        0x01C4: "armv7",
        0x0200: "ia64",
        0x8664: "x86_64",
        0xAA64: "arm64",
    }
    elf_architectures = {
        3: "x86",
        8: "mips",
        20: "ppc",
        21: "ppc64",
        40: "arm",
        62: "x86_64",
        183: "arm64",
        243: "riscv64",
    }
    macho_architectures = {
        7: "x86",
        12: "arm",
        18: "ppc",
        0x01000007: "x86_64",
        0x0100000C: "arm64",
        0x01000012: "ppc64",
    }
    try:
        with Path(path).open("rb") as stream:
            prefix = stream.read(64)
            if prefix.startswith(b"MZ") and len(prefix) >= 64:
                pe_offset = struct.unpack_from("<I", prefix, 0x3C)[0]
                if pe_offset > 16 * 1024 * 1024:
                    return ()
                stream.seek(pe_offset)
                header = stream.read(6)
                if header[:4] == b"PE\0\0" and len(header) == 6:
                    architecture = pe_architectures.get(struct.unpack_from("<H", header, 4)[0])
                    return (architecture,) if architecture else ()
                return ()
            if prefix.startswith(b"\x7fELF") and len(prefix) >= 20:
                byte_order = {1: "<", 2: ">"}.get(prefix[5])
                if byte_order is None:
                    return ()
                architecture = elf_architectures.get(
                    struct.unpack_from(f"{byte_order}H", prefix, 18)[0]
                )
                return (architecture,) if architecture else ()

            macho_order = {
                b"\xfe\xed\xfa\xce": ">",
                b"\xfe\xed\xfa\xcf": ">",
                b"\xce\xfa\xed\xfe": "<",
                b"\xcf\xfa\xed\xfe": "<",
            }.get(prefix[:4])
            if macho_order is not None and len(prefix) >= 8:
                architecture = macho_architectures.get(
                    struct.unpack_from(f"{macho_order}I", prefix, 4)[0]
                )
                return (architecture,) if architecture else ()

            fat_formats = {
                b"\xca\xfe\xba\xbe": (">", 20),
                b"\xbe\xba\xfe\xca": ("<", 20),
                b"\xca\xfe\xba\xbf": (">", 32),
                b"\xbf\xba\xfe\xca": ("<", 32),
            }
            fat_format = fat_formats.get(prefix[:4])
            if fat_format is not None and len(prefix) >= 8:
                byte_order, entry_size = fat_format
                count = struct.unpack_from(f"{byte_order}I", prefix, 4)[0]
                if count == 0 or count > 64:
                    return ()
                table_size = count * entry_size
                stream.seek(8)
                entries = stream.read(table_size)
                if len(entries) != table_size:
                    return ()
                architectures = {
                    macho_architectures[cpu_type]
                    for index in range(count)
                    if (
                        cpu_type := struct.unpack_from(
                            f"{byte_order}I", entries, index * entry_size
                        )[0]
                    )
                    in macho_architectures
                }
                return tuple(sorted(architectures))
    except (OSError, struct.error, ValueError):
        return ()
    return ()


def host_architecture() -> str:
    """Return a normalized host architecture label for side-by-side review."""
    value = platform.machine().casefold()
    return {
        "amd64": "x86_64",
        "x64": "x86_64",
        "i386": "x86",
        "i486": "x86",
        "i586": "x86",
        "i686": "x86",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(value, value or "unknown")


def run_isolated_local_sync_test(client: MutagenClient) -> str:
    """Create and remove a uniquely named sync under a disposable daemon/data root."""
    if not client.binary:
        raise MutagenError("Mutagen CLI was not found.")

    name = f"mutaui-onboarding-{uuid4().hex[:12]}"
    identifier = ""
    result = "Local sync test failed."
    with tempfile.TemporaryDirectory(prefix="mutaui-onboarding-") as temporary:
        root = Path(temporary).resolve()
        data_directory = root / "mutagen-data"
        alpha = root / "alpha"
        beta = root / "beta"
        alpha.mkdir()
        beta.mkdir()
        marker = alpha / "onboarding-check.txt"
        marker.write_text("local Mutagen onboarding check\n", encoding="utf-8")
        environment = {"MUTAGEN_DATA_DIRECTORY": str(data_directory)}
        try:
            client.command(
                [
                    "sync",
                    "create",
                    f"--name={name}",
                    "--no-global-configuration",
                    str(alpha),
                    str(beta),
                ],
                timeout=30,
                env_overrides=environment,
            )
            sessions = parse_sessions(
                client.command(
                    ["sync", "list", "--template", "{{ json . }}"],
                    timeout=10,
                    readonly=True,
                    env_overrides=environment,
                )
            )
            matches = [item for item in sessions if item.get("name") == name]
            if len(matches) != 1 or not isinstance(matches[0].get("identifier"), str):
                raise MutagenError("Could not identify the isolated test session for cleanup.")
            identifier = matches[0]["identifier"]
            deadline = time.monotonic() + 10
            while not (beta / marker.name).is_file() and time.monotonic() < deadline:
                time.sleep(0.1)
            if not (beta / marker.name).is_file():
                raise MutagenError("Local sync did not transfer its test file within 10 seconds.")
            result = "Local sync test passed; isolated session and data will be removed."
        finally:
            try:
                if identifier:
                    client.command(
                        ["sync", "terminate", identifier],
                        timeout=20,
                        env_overrides=environment,
                    )
            finally:
                # Stop only the daemon addressed by this temporary data directory.
                with contextlib.suppress(MutagenError):
                    client.command(["daemon", "stop"], timeout=10, env_overrides=environment)
    return result
