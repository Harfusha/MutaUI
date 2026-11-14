"""CLI execution contract with an adapter for the existing MutagenClient."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    elapsed_seconds: float


class CommandExecutor(Protocol):
    def run(
        self, argv: Sequence[str], *, timeout_seconds: int, readonly: bool = False
    ) -> CommandResult: ...


class LegacyMutagenClient(Protocol):
    def command(self, args: list[str], *, timeout: int = 35, readonly: bool = False) -> str: ...


class LegacyMutagenExecutor:
    """Wrap the legacy CLI adapter without changing command or error behavior."""

    def __init__(
        self, client: LegacyMutagenClient, clock: Callable[[], float] = perf_counter
    ) -> None:
        self._client = client
        self._clock = clock

    def run(
        self, argv: Sequence[str], *, timeout_seconds: int, readonly: bool = False
    ) -> CommandResult:
        arguments = tuple(argv)
        if not arguments or any(not isinstance(arg, str) or "\x00" in arg for arg in arguments):
            raise ValueError("CLI arguments must be a non-empty sequence of strings")
        started = self._clock()
        stdout = self._client.command(list(arguments), timeout=timeout_seconds, readonly=readonly)
        elapsed = max(0.0, self._clock() - started)
        return CommandResult(arguments, 0, stdout, "", elapsed)
