"""Prove the active secret scanner still catches fresh credentials after triage."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    scanner = shutil.which("detect-secrets-hook")
    if scanner is None:
        print("detect-secrets-hook is not installed", file=sys.stderr)
        return 1
    # The test token is random, disposable and never checked in or printed.
    # The file lives in a temporary folder inside the checkout for scanning.
    with tempfile.TemporaryDirectory(prefix=".secret-negative-probe-", dir=Path.cwd()) as folder:
        candidate = Path(folder) / "credentials.py"
        # Detect-secrets may rewrite the selected baseline. Use an isolated copy:
        # the negative probe must never mutate the tracked security baseline.
        isolated_baseline = Path(folder) / "baseline.json"
        shutil.copyfile(".secrets.baseline", isolated_baseline)
        candidate.write_text(
            "API_TOKEN = " + repr(os.urandom(32).hex()) + "\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [scanner, "--baseline", str(isolated_baseline), str(candidate)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 1:
            print(
                "Secret detector negative probe failed: expected a high-entropy token "
                f"to be rejected with exit 1; got exit {result.returncode}",
                file=sys.stderr,
            )
            return 1
    print("Synthetic high-entropy credential was rejected as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
