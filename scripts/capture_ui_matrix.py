"""Capture a pairwise EN/CS, theme, mode, and DPI screenshot matrix."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

CAPTURE_CASES = (
    ("dark", "en", "basic", "1"),
    ("dark", "cs", "advanced", "1"),
    ("light", "en", "advanced", "1"),
    ("light", "cs", "basic", "1"),
    ("dark", "en", "basic", "1.25"),
    ("dark", "cs", "advanced", "1.25"),
    ("light", "en", "advanced", "1.25"),
    ("light", "cs", "basic", "1.25"),
    ("dark", "en", "basic", "1.5"),
    ("dark", "cs", "advanced", "1.5"),
    ("light", "en", "advanced", "1.5"),
    ("light", "cs", "basic", "1.5"),
    ("dark", "en", "basic", "2"),
    ("dark", "cs", "advanced", "2"),
    ("light", "en", "advanced", "2"),
    ("light", "cs", "basic", "2"),
    ("dark", "en", "basic", "3.2"),
    ("dark", "cs", "advanced", "3.2"),
    ("light", "en", "advanced", "3.2"),
    ("light", "cs", "basic", "3.2"),
)


def capture_matrix(output: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    capture = repository / "gui_capture.py"
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    output.mkdir(parents=True, exist_ok=True)

    for theme, language, mode, scale in CAPTURE_CASES:
        case = f"{theme}-{language}-{mode}-{scale.replace('.', '_')}x"
        target = output / case
        command = [
            sys.executable,
            str(capture),
            str(target),
            "--theme",
            theme,
            "--language",
            language,
            "--mode",
            mode,
            "--scale",
            scale,
        ]
        if scale == "3.2":
            # 3840x2160 physical pixels at 320% maps to a 1200x675 logical viewport.
            command.extend(("--window-width", "1200", "--window-height", "675"))
        # The executable and all options come from this script's fixed case matrix.
        subprocess.run(command, check=True, env=environment, cwd=repository)  # noqa: S603


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Directory for the screenshot matrix")
    args = parser.parse_args()
    capture_matrix(args.output)


if __name__ == "__main__":
    main()
