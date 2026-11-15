"""Isolated Mutagen daemon fixture and test harness (CI-05 / F2-004).

Manages an isolated Mutagen daemon process instance with guaranteed cleanup,
readiness polling, lifecycle tracking, and diagnostic capture upon failure.
Never modifies or interacts with the user's default daemon.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen_client import MutagenClient, MutagenError


@dataclass
class DaemonDiagnostics:
    phase: str = "unstarted"
    start_time: float = 0.0
    ready_time: float = 0.0
    stop_time: float = 0.0
    pid: int | None = None
    exit_code: int | None = None
    stderr_tail: str = ""
    stdout_tail: str = ""
    daemon_logs: str = ""
    error: str | None = None


class IsolatedMutagenDaemon:
    """Robust context manager managing an isolated Mutagen test daemon."""

    def __init__(
        self,
        binary: str | Path,
        base_dir: Path,
        *,
        readiness_timeout: float = 20.0,
        stop_timeout: float = 20.0,
        env_overrides: dict[str, str] | None = None,
    ) -> None:
        self.binary = str(binary)
        self.base_dir = Path(base_dir)
        self.readiness_timeout = readiness_timeout
        self.stop_timeout = stop_timeout
        self.env_overrides = env_overrides or {}
        if any(k in self.env_overrides for k in ("MUTAGEN_DATA_DIRECTORY", "HOME", "USERPROFILE")):
            raise ValueError("Disposable daemon data and home cannot be overridden")
        # Validate before allocating a temp directory; invalid overrides must not leak one.
        # The native Unix socket has a tight path limit on macOS/Linux.
        short_root = "/tmp" if os.name != "nt" else tempfile.gettempdir()
        self._owned_root = Path(tempfile.mkdtemp(prefix="mu-", dir=short_root))
        self.data_dir = self._owned_root / "data"
        self.home_dir = self._owned_root / "home"
        environment = os.environ.copy()
        environment.update(
            {
                "MUTAGEN_DATA_DIRECTORY": str(self.data_dir),
                "MUTAGEN_DISABLE_AUTOSTART": "0",
                "HOME": str(self.home_dir),
                "USERPROFILE": str(self.home_dir),
            }
        )
        environment.update(self.env_overrides)
        self.phase = "unstarted"
        self.diagnostics = DaemonDiagnostics()
        self.client = MutagenClient(self.binary, process_environment=environment)
        self._started = False
        self._start_attempted = False

    def __enter__(self) -> IsolatedMutagenDaemon:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_val is not None:
            self._capture_failure_diagnostics(str(exc_val))
        self.stop()

    def start(self) -> None:
        """Start the isolated daemon and poll until it is fully ready to accept commands."""
        self.phase = "starting"
        self.diagnostics.phase = "starting"
        self.diagnostics.start_time = time.monotonic()

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.home_dir.mkdir(parents=True, exist_ok=True)

        try:
            # A failing launch can still leave a child daemon running.
            self._start_attempted = True
            self.client.command(["daemon", "start"], timeout=self.stop_timeout)
            self._started = True
            self.wait_until_ready()
            self.phase = "ready"
            self.diagnostics.phase = "ready"
            self.diagnostics.ready_time = time.monotonic()
        except Exception as exc:
            self.phase = "failed"
            self.diagnostics.phase = "failed"
            self._capture_failure_diagnostics(str(exc))
            self.stop()
            raise

    def wait_until_ready(self) -> None:
        """Actively verify readiness using sync list and forward list probes."""
        deadline = time.monotonic() + self.readiness_timeout
        last_error = ""

        while time.monotonic() < deadline:
            try:
                # Both sync and forward must accept queries without connection errors
                self.client.command(
                    ["sync", "list", "--template", "{{ json . }}"], timeout=5, readonly=True
                )
                self.client.command(
                    ["forward", "list", "--template", "{{ json . }}"], timeout=5, readonly=True
                )
                return
            except MutagenError as exc:
                last_error = str(exc)
                err_lower = last_error.casefold()
                if "unable to connect to daemon" not in err_lower and "timed out" not in err_lower:
                    raise
                time.sleep(0.2)
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.2)

        raise TimeoutError(
            f"Isolated Mutagen daemon failed to become ready within {self.readiness_timeout}s. "
            f"Last error: {last_error}"
        )

    def stop(self) -> None:
        """Stop only this disposable daemon; never delete data on an uncertain stop."""
        was_failed = self.phase == "failed"
        if not was_failed:
            self.phase = "stopping"
            self.diagnostics.phase = "stopping"
        self.diagnostics.stop_time = time.monotonic()

        stop_acknowledged = not self._start_attempted
        if self._start_attempted:
            try:
                self.client.command(["daemon", "stop"], timeout=self.stop_timeout)
                stop_acknowledged = True
            except MutagenError as exc:
                self._capture_failure_diagnostics("Stop not acknowledged: " + str(exc))

        # A failed readiness probe alone is not proof that a daemon exited.
        # Require explicit CLI stop acknowledgement before removing test-owned data.
        daemon_stopped = stop_acknowledged and not self.client._daemon_state()
        if daemon_stopped and self._owned_root.is_dir():
            shutil.rmtree(self._owned_root)
        self._started = False
        self._start_attempted = not daemon_stopped

        if not was_failed:
            self.phase = "stopped" if daemon_stopped else "stop_failed"
            self.diagnostics.phase = self.phase

    def _capture_failure_diagnostics(self, error_msg: str) -> None:
        """Write only non-identifying lifecycle metadata to a CI artifact.

        Native daemon logs and error messages can contain local paths, remote hostnames
        and credentials. Retain those only in process memory, never in uploaded files.
        """
        self.diagnostics.error = error_msg
        logs_available = any(
            path.is_file()
            for path in (self.data_dir / "daemon.log", self.data_dir / "daemon" / "daemon.log")
        )
        lowered = error_msg.casefold()
        category = (
            "timeout"
            if "timed out" in lowered or "timeout" in lowered
            else "connection"
            if "connect" in lowered
            else "other"
        )
        diag_dir = Path("test-results") / "daemon-diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        diag_path = diag_dir / f"daemon_fail_{time.time_ns()}.json"
        with suppress(OSError):
            diag_path.write_text(
                json.dumps(
                    {
                        "phase": self.phase,
                        "error_category": category,
                        "daemon_log_present": logs_available,
                        "start_duration_seconds": (
                            max(0.0, time.monotonic() - self.diagnostics.start_time)
                            if self.diagnostics.start_time > 0
                            else None
                        ),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
