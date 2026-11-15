"""Isolated Mutagen daemon fixture and test harness (CI-05 / F2-004).

Manages an isolated Mutagen daemon process instance with guaranteed cleanup,
readiness polling, lifecycle tracking, and diagnostic capture upon failure.
Never modifies or interacts with the user's default daemon.
"""

from __future__ import annotations

import json
import os
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
        self.data_dir = self.base_dir / "daemon-data"
        self.home_dir = self.base_dir / "isolated-home"
        self.readiness_timeout = readiness_timeout
        self.stop_timeout = stop_timeout
        self.env_overrides = env_overrides or {}

        self.phase = "unstarted"
        self.diagnostics = DaemonDiagnostics()
        self.client = MutagenClient(self.binary)
        self._prev_env: dict[str, str | None] = {}
        self._started = False

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

        env_keys = ["MUTAGEN_DATA_DIRECTORY", "MUTAGEN_DISABLE_AUTOSTART", "HOME", "USERPROFILE"]
        for key in env_keys:
            self._prev_env[key] = os.environ.get(key)

        os.environ["MUTAGEN_DATA_DIRECTORY"] = str(self.data_dir)
        os.environ["MUTAGEN_DISABLE_AUTOSTART"] = "0"
        os.environ["HOME"] = str(self.home_dir)
        os.environ["USERPROFILE"] = str(self.home_dir)
        for k, v in self.env_overrides.items():
            self._prev_env[k] = os.environ.get(k)
            os.environ[k] = v

        try:
            # Launch daemon start
            self.client.command(["daemon", "start"], timeout=self.stop_timeout)
            self._started = True
            self.wait_until_ready()
            self.phase = "ready"
            self.diagnostics.phase = "ready"
            self.diagnostics.ready_time = time.monotonic()
        except Exception as exc:
            self.phase = "failed"
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
        """Cleanly stop the daemon and reap any orphan processes."""
        was_failed = self.phase == "failed"
        if not was_failed:
            self.phase = "stopping"
            self.diagnostics.phase = "stopping"
        self.diagnostics.stop_time = time.monotonic()

        if self._started:
            with suppress(Exception):
                self.client.command(["daemon", "stop"], timeout=self.stop_timeout)

        # Restore environment
        for key, val in self._prev_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

        if not was_failed:
            self.phase = "stopped"
            self.diagnostics.phase = "stopped"

    def _capture_failure_diagnostics(self, error_msg: str) -> None:
        """Capture redacted diagnostics into artifact when an error occurs."""
        self.diagnostics.error = error_msg
        log_file = self.data_dir / "daemon.log"
        if log_file.is_file():
            with suppress(Exception):
                self.diagnostics.daemon_logs = log_file.read_text(
                    encoding="utf-8", errors="replace"
                )[-4000:]

        diag_dir = Path("test-results") / "daemon-diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        diag_path = diag_dir / f"daemon_fail_{int(time.time() * 1000)}.json"
        with suppress(Exception):
            diag_path.write_text(
                json.dumps(
                    {
                        "phase": self.diagnostics.phase,
                        "error": self.diagnostics.error,
                        "data_dir": str(self.data_dir),
                        "start_duration": self.diagnostics.ready_time - self.diagnostics.start_time
                        if self.diagnostics.ready_time > 0
                        else None,
                        "daemon_logs_tail": self.diagnostics.daemon_logs,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
