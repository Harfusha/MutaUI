"""Platform-neutral runner for static checks in CI and release workflows.

Executes each static analysis tool in sequence, terminating immediately on the
first failure so that no step can mask a previous error.
"""

from __future__ import annotations

import subprocess
import sys


def run_command(cmd: list[str]) -> None:
    print(f"[run_static_checks] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(
            f"[run_static_checks] Command failed with exit code {result.returncode}: {' '.join(cmd)}",
            file=sys.stderr,
        )
        sys.exit(result.returncode or 1)


def main() -> int:
    commands = [
        [sys.executable, "-m", "ruff", "check", "."],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "src/mutaui",
            "tests/test_app_import.py",
            "tests/test_domain_models.py",
            "tests/test_write_checksums.py",
            "scripts/run_self_test.py",
            "scripts/write_checksums.py",
            "tests/test_run_self_test.py",
            "gui_capture.py",
            "scripts/capture_ui_matrix.py",
            "tests/test_gui_capture.py",
            "tests/test_capture_ui_matrix.py",
            "benchmarks/session_table_benchmark.py",
            "tests/test_session_table_benchmark.py",
            "tests/test_ui_preferences.py",
            "tests/test_mainwindow_flows.py",
            "tests/test_update_checker.py",
        ],
        [sys.executable, "-m", "mypy", "src/mutaui"],
        [sys.executable, "scripts/generate_settings_reference.py", "--check"],
        [
            sys.executable,
            "scripts/generate_settings_reference.py",
            "--check",
            "--output",
            "docs/reference/configuration-fields.md",
        ],
        [sys.executable, "-m", "pymarkdown", "-d", "MD013,MD029", "scan", "README.md", "docs"],
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        [sys.executable, "verify_source.py"],
    ]

    for cmd in commands:
        run_command(cmd)

    print("[run_static_checks] All static checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
