"""Exercise crash recovery through a packaged Windows application build."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from monitoring import METRIC_COLUMNS, HistoryStore, Sample  # noqa: E402
from settings import DEFAULT_SETTINGS, write_settings  # noqa: E402

CRASH_EXIT_CODE = 23


def _settings_path(appdata: Path) -> Path:
    return appdata / "MutagenControl" / "settings.json"


def _crash_fixture(appdata: Path) -> None:
    settings_path = _settings_path(appdata)
    write_settings(settings_path, {**DEFAULT_SETTINGS, "theme": "dark"})

    history_path = settings_path.parent / "metrics.sqlite3"
    committed_ts = time.time()
    uncommitted_ts = committed_ts + 0.125
    store = HistoryStore(history_path)
    store.add(Sample(ts=committed_ts, cpu=42.0, active_sessions=1))
    store.db.execute("BEGIN IMMEDIATE")
    uncommitted_values = (uncommitted_ts,) + tuple(
        getattr(Sample(ts=uncommitted_ts, cpu=99.0), column) for column in METRIC_COLUMNS
    )
    store.db.execute(
        "INSERT INTO metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", uncommitted_values
    )
    settings_path.write_bytes(b"{")
    marker = appdata / "crash-fixture.json"
    marker.write_text(
        json.dumps({"committed_ts": committed_ts, "uncommitted_ts": uncommitted_ts}),
        encoding="utf-8",
    )
    os._exit(CRASH_EXIT_CODE)


def _run_packaged_restart(executable: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mutaui-crash-recovery-") as temp_name:
        root = Path(temp_name)
        appdata = root / "roaming"
        marker = appdata / "crash-fixture.json"
        child = subprocess.run(  # noqa: S603 - fixed Python executable and literal fixture arguments
            [sys.executable, str(Path(__file__).resolve()), "--crash-fixture", str(appdata)],
            cwd=REPOSITORY_ROOT,
            check=False,
            timeout=30,
            shell=False,
        )
        if child.returncode != CRASH_EXIT_CODE:
            raise RuntimeError(f"Crash fixture exited with {child.returncode}, expected 23.")

        fixture = json.loads(marker.read_text(encoding="utf-8"))
        settings_path = _settings_path(appdata)
        history_path = settings_path.parent / "metrics.sqlite3"
        log_path = root / "packaged-self-test.log"
        env = os.environ.copy()
        env.update(
            {
                "APPDATA": str(appdata),
                "MUTAUI_SELF_TEST_LOG": str(log_path),
                "MUTAUI_SELF_TEST_HISTORY_PATH": str(history_path),
                "MUTAUI_SELF_TEST_EXPECT_RECOVERED_THEME": "dark",
                "QT_QPA_PLATFORM": "offscreen",
            }
        )
        result = subprocess.run(  # noqa: S603 - exact packaged executable and fixed self-test flag
            [str(executable), "--self-test"],
            cwd=executable.parent,
            env=env,
            check=False,
            timeout=120,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        if (
            result.returncode != 0
            or "Settings recovery and file-backed history reopened." not in log_text
        ):
            raise RuntimeError(
                f"Packaged recovery self-test failed (exit={result.returncode}): {log_text}"
            )

        persisted_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if persisted_settings.get("theme") != "dark":
            raise RuntimeError("Recovered theme was not persisted by the packaged restart.")
        corrupt_backups = tuple(settings_path.parent.glob("settings.json.corrupt.*.bak"))
        if not any(path.read_bytes() == b"{" for path in corrupt_backups):
            raise RuntimeError(
                "Corrupt settings bytes were not preserved beside the recovered file."
            )

        store = HistoryStore(history_path)
        try:
            integrity = store.db.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"Recovered history database integrity check: {integrity}")
            committed = store.db.execute(
                "SELECT cpu FROM metrics WHERE ts=?", (fixture["committed_ts"],)
            ).fetchone()
            uncommitted = store.db.execute(
                "SELECT 1 FROM metrics WHERE ts=?", (fixture["uncommitted_ts"],)
            ).fetchone()
            if committed != (42.0,) or uncommitted is not None:
                raise RuntimeError(
                    "Crash recovery did not preserve committed history and roll back WAL data."
                )
        finally:
            store.close()

        print("PASS: packaged restart recovered settings and reopened populated SQLite history.")


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--crash-fixture":
        _crash_fixture(Path(sys.argv[2]))
    if len(sys.argv) != 3 or sys.argv[1] != "--executable":
        print(f"Usage: {Path(sys.argv[0]).name} --executable <MutagenControl.exe>", file=sys.stderr)
        return 2
    executable = Path(sys.argv[2]).resolve()
    if not executable.is_file():
        print(f"Packaged executable not found: {executable}", file=sys.stderr)
        return 2
    try:
        _run_packaged_restart(executable)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
