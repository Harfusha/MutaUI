"""Verify pip compatibility exports against the universal uv lock."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = {
    "requirements.txt": [],
    "requirements-build.txt": ["build", "test", "quality"],
    "requirements-quality.txt": ["test", "quality"],
}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mutaui-requirements-") as temporary:
        temporary_path = Path(temporary)
        for filename, groups in EXPORTS.items():
            output = temporary_path / filename
            command = [
                "uv",
                "export",
                "--locked",
                "--no-default-groups",
                "--no-emit-project",
                "--no-hashes",
            ]
            for group in groups:
                command.extend(["--only-group", group])
            command.extend(["--output-file", str(output)])
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)

            expected = (ROOT / filename).read_text(encoding="utf-8").splitlines()[2:]
            actual = output.read_text(encoding="utf-8").splitlines()[2:]
            if expected != actual:
                raise SystemExit(
                    f"{filename} is stale; regenerate it from pyproject.toml and uv.lock"
                )

    print("Pinned requirements exports match pyproject.toml and uv.lock.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
