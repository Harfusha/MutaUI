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
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "mypy"],
        [
            sys.executable,
            "-m",
            "mypy",
            "src/mutaui",
            "app.py",
            "connection_profiles.py",
            "endpoint_inspector.py",
            "server_groups.py",
            "settings.py",
            "performance.py",
            "forward_configuration.py",
            "portable_bundle.py",
            "ignore_presets.py",
            "sync_configuration.py",
            "ssh_profiles.py",
            "monitoring.py",
            "insights.py",
            "async_recorder.py",
            "benchmark.py",
            "log_stream.py",
            "sync_profiles.py",
            "verify_source.py",
            "mutagen_client.py",
            "gui_capture.py",
        ],
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
