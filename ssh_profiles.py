"""Read-only OpenSSH profile inspection and host-key-safe connection checks."""

from __future__ import annotations

import glob
import hashlib
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_ALIAS_RE = re.compile(r"^[A-Za-z0-9_.@:-]{1,255}$")
_MAX_CONFIG_BYTES = 1024 * 1024
_MAX_CONFIG_FILES = 64
_MAX_INCLUDE_DEPTH = 8
_SSH_TIMEOUT = 10


@dataclass(frozen=True, slots=True)
class SSHHostProfile:
    alias: str
    directives: dict[str, tuple[str, ...]] = field(default_factory=dict)
    unsupported: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SSHConfigRead:
    profiles: tuple[SSHHostProfile, ...]
    valid: bool
    sha256: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SSHCommandResult:
    success: bool
    message: str
    options: dict[str, tuple[str, ...]] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    host_key_error: bool = False


def _safe_alias(alias: str) -> bool:
    return bool(alias and _ALIAS_RE.fullmatch(alias) and not alias.startswith("-"))


def parse_ssh_config(path: str | Path, *, max_bytes: int = _MAX_CONFIG_BYTES) -> SSHConfigRead:
    """Read aliases and simple directives, following bounded Include patterns."""
    config_path = Path(path).expanduser()
    profiles: dict[str, dict[str, list[str]]] = {}
    unsupported: dict[str, set[str]] = {}
    warnings: list[str] = []
    hashes: list[bytes] = []
    seen: set[Path] = set()
    invalid = False
    file_count = 0
    file_limit_reported = False

    def process(current: Path, active: list[str], depth: int) -> list[str]:
        nonlocal invalid, file_count, file_limit_reported
        if depth > _MAX_INCLUDE_DEPTH:
            warnings.append(f"Include depth limit reached at {current}")
            return active
        if file_count >= _MAX_CONFIG_FILES:
            if not file_limit_reported:
                warnings.append("SSH config include file limit reached")
                file_limit_reported = True
            return active
        try:
            resolved = current.expanduser().resolve(strict=True)
        except OSError:
            warnings.append(f"Missing or unreadable SSH config include: {current}")
            return active
        if resolved in seen:
            warnings.append(f"Repeated or recursive SSH config include skipped: {resolved}")
            return active
        seen.add(resolved)
        file_count += 1
        try:
            raw = resolved.read_bytes()
            if len(raw) > max_bytes:
                invalid = True
                warnings.append(f"SSH config exceeds {max_bytes} bytes: {resolved}")
                return active
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            invalid = True
            warnings.append(f"Cannot safely read SSH config {resolved}: {exc}")
            return active
        hashes.append(str(resolved).encode("utf-8", errors="replace") + b"\0" + raw)

        for line_number, line in enumerate(text.splitlines(), start=1):
            try:
                parts = shlex.split(line, comments=True, posix=True)
            except ValueError as exc:
                warnings.append(f"Malformed SSH config line {resolved}:{line_number}: {exc}")
                continue
            if not parts:
                continue
            key, values = parts[0].lower(), parts[1:]
            if not values:
                warnings.append(f"SSH config directive has no value at {resolved}:{line_number}")
                continue
            if key == "include":
                for value in values:
                    pattern = os.path.expandvars(os.path.expanduser(value))
                    if not os.path.isabs(pattern):
                        pattern = str(resolved.parent / pattern)
                    matches = sorted(glob.glob(pattern))
                    if not matches:
                        warnings.append(
                            f"Unresolved SSH Include at {resolved}:{line_number}: {value}"
                        )
                    for match in matches:
                        active = process(Path(match), active, depth + 1)
                continue
            if key == "host":
                active = []
                for candidate in values:
                    if any(char in candidate for char in "*!?") or candidate.startswith("!"):
                        warnings.append(
                            f"Wildcard/negated SSH Host pattern not listed as an alias: {candidate}"
                        )
                        continue
                    if _safe_alias(candidate):
                        active.append(candidate)
                        profiles.setdefault(candidate, {})
                        unsupported.setdefault(candidate, set())
                continue
            if key == "match":
                warnings.append(
                    f"Match blocks are not expanded by the read-only alias listing ({resolved}:{line_number})"
                )
                active = []
                continue
            for alias in active:
                bucket = profiles.setdefault(alias, {})
                bucket.setdefault(key, []).append(" ".join(values))
                if key not in {
                    "hostname",
                    "user",
                    "port",
                    "identityfile",
                    "identitiesonly",
                    "proxyjump",
                    "proxycommand",
                    "userknownhostsfile",
                    "stricthostkeychecking",
                    "preferredauthentications",
                    "connecttimeout",
                    "addressfamily",
                    "canonicalizehostname",
                    "serveraliveinterval",
                    "serveralivecountmax",
                    "compression",
                    "forwardagent",
                    "forwardx11",
                    "requesttty",
                }:
                    unsupported.setdefault(alias, set()).add(key)
        return active

    if config_path.exists():
        process(config_path, [], 0)
    else:
        warnings.append(f"SSH config not found: {config_path}")
    ordered = tuple(
        SSHHostProfile(
            alias,
            {key: tuple(values) for key, values in directives.items()},
            tuple(sorted(unsupported.get(alias, ()))),
        )
        for alias, directives in profiles.items()
    )
    digest = hashlib.sha256(b"\n\0".join(hashes)).hexdigest() if hashes else None
    return SSHConfigRead(ordered, not invalid, digest, tuple(warnings))


def parse_ssh_options(output: str) -> dict[str, str | tuple[str, ...]]:
    """Parse OpenSSH ``-G`` key/value output, retaining repeated options."""
    parsed: dict[str, list[str]] = {}
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        key, value = parts[0].lower(), parts[1].strip()
        if key and value:
            parsed.setdefault(key, []).append(value)
    list_options = {
        "identityfile",
        "userknownhostsfile",
        "globalknownhostsfile",
        "stricthostkeychecking",
    }
    return {
        key: tuple(values) if len(values) > 1 or key in list_options else values[0]
        for key, values in parsed.items()
    }


def _find_ssh(executable: str | None = None) -> str | None:
    return executable or shutil.which("ssh")


def _run_ssh(argv: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv; alias and executable are validated
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def resolve_ssh_options(
    alias: str, *, executable: str | None = None, timeout: int = _SSH_TIMEOUT
) -> SSHCommandResult:
    if not _safe_alias(alias):
        return SSHCommandResult(False, "Invalid SSH alias.")
    binary = _find_ssh(executable)
    if not binary:
        return SSHCommandResult(False, "OpenSSH client was not found.")
    try:
        completed = _run_ssh([binary, "-G", alias], timeout=max(1, min(timeout, _SSH_TIMEOUT)))
    except subprocess.TimeoutExpired:
        return SSHCommandResult(False, "OpenSSH option resolution timed out.")
    except OSError as exc:
        return SSHCommandResult(False, f"Could not run OpenSSH: {exc}")
    if completed.returncode:
        return SSHCommandResult(
            False,
            "OpenSSH could not resolve this alias.",
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    options = parse_ssh_options(completed.stdout)
    normalized = {
        key: value if isinstance(value, tuple) else (value,) for key, value in options.items()
    }
    return SSHCommandResult(
        True,
        "Effective OpenSSH options resolved locally.",
        normalized,
        completed.stdout,
        completed.stderr,
    )


def test_ssh_connection(
    alias: str, *, executable: str | None = None, timeout: int = 12
) -> SSHCommandResult:
    """Run a user-requested non-interactive test without bypassing host-key checks."""
    if not _safe_alias(alias):
        return SSHCommandResult(False, "Invalid SSH alias.")
    binary = _find_ssh(executable)
    if not binary:
        return SSHCommandResult(False, "OpenSSH client was not found.")
    argv = [
        binary,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=5",
        "-T",
        alias,
        "true",
    ]
    try:
        completed = _run_ssh(argv, timeout=max(1, min(timeout, 15)))
    except subprocess.TimeoutExpired:
        return SSHCommandResult(
            False, "SSH connection test timed out; no host-key setting was changed."
        )
    except OSError as exc:
        return SSHCommandResult(False, f"Could not run OpenSSH: {exc}")
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    host_key_error = bool(
        re.search(r"\bno\s+(?:[a-z0-9_-]+\s+)?host key is known\b", output)
    ) or any(
        marker in output
        for marker in (
            "host key verification failed",
            "host key is not known",
            "remote host identification has changed",
            "offending ",
        )
    )
    if completed.returncode == 0:
        return SSHCommandResult(
            True,
            "SSH connection test succeeded with strict host-key checking.",
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    message = (
        "Host key is missing or does not match known_hosts; verify it through your normal trusted process."
        if host_key_error
        else "SSH connection test failed."
    )
    return SSHCommandResult(
        False,
        message,
        stdout=completed.stdout,
        stderr=completed.stderr,
        host_key_error=host_key_error,
    )


# pytest otherwise mistakes this imported public operation for a test in consumers.
test_ssh_connection.__test__ = False
