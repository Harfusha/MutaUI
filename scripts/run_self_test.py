"""Run a packaged demo self-test and wait for its explicit success marker."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SUCCESS_MARKER = "OK: UI pages and server groups rendered."


def _log_path() -> Path:
    configured = os.environ.get("MUTAUI_SELF_TEST_LOG")
    if configured:
        return Path(configured)
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        return Path(runner_temp) / "mutagen-control-self-test.log"
    return Path(tempfile.mkdtemp(prefix="mutagen-control-self-test-")) / "self-test.log"


def run_self_test(executable: Path, *, timeout_seconds: float = 120.0) -> int:
    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.unlink(missing_ok=True)

    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    environment["MUTAUI_SELF_TEST_LOG"] = str(log_path)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        process = subprocess.Popen(
            [str(executable), "--self-test"],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            shell=False,
        )
    except OSError as exc:
        print(f"Could not start packaged app: {exc}", file=sys.stderr)
        return 1

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            log_text = log_path.read_text(encoding="utf-8").strip()
        except OSError:
            log_text = ""
        if log_text == SUCCESS_MARKER:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            print(f"Packaged self-test passed: {executable}")
            return 0

        exit_code = process.poll()
        if exit_code is not None:
            break
        time.sleep(0.25)
    else:
        process.kill()
        process.wait()
        exit_code = 124

    print(f"Packaged self-test failed (exit code {exit_code}).", file=sys.stderr)
    if log_path.exists():
        print(log_path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
    else:
        print(f"Self-test log not created: {log_path}", file=sys.stderr)
    return exit_code or 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--timeout", type=float, default=120.0)
    arguments = parser.parse_args()
    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    return run_self_test(arguments.executable, timeout_seconds=arguments.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
