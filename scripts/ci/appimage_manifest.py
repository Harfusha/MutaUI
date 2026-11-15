"""Fail-closed manifest parsing for the exact AppImage build utility."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def load_pinned_tool(path: Path) -> tuple[str, str, str]:
    """Return version, SHA-256, URL only for the approved fixed architecture."""
    metadata = json.loads(path.read_text(encoding="utf-8"))
    tool = metadata["appimagetool"]
    version = tool["version"]
    architecture = tool["architecture"]
    checksum = tool["sha256"]
    url = tool["url"]
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError("Invalid appimagetool version")
    if architecture != "x86_64":
        raise ValueError("Unsupported appimagetool architecture")
    if not isinstance(checksum, str) or re.fullmatch(r"[a-f0-9]{64}", checksum) is None:
        raise ValueError("Invalid appimagetool SHA-256")
    expected = (
        "https://github.com/AppImage/appimagetool/releases/download/"
        f"{version}/appimagetool-x86_64.AppImage"
    )
    if url != expected:
        raise ValueError("AppImage utility URL does not match the pinned release")
    return version, checksum, expected


def main() -> int:
    if len(sys.argv) != 2:
        print("Expected one path to pinned manifest", file=sys.stderr)
        return 2
    try:
        version, checksum, url = load_pinned_tool(Path(sys.argv[1]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"AppImage utility manifest rejected: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(version, checksum, url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
