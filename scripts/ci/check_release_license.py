"""Preflight policy: never auto-select legal terms on behalf of the owner.

This gate verifies that a human-supplied LICENSE and notices exist before a
distribution tag is published. Passing this test does not constitute legal advice.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def verify_release_legal_files(root: Path) -> None:
    license_file = root / "LICENSE"
    notices_file = root / "NOTICE.md"

    if not license_file.is_file():
        raise ValueError(
            "Owner must choose and commit a LICENSE before a public binary release. "
            "Do not auto-generate or assume MIT/GPL/Apache terms."
        )
    content = license_file.read_text(encoding="utf-8").strip()
    if len(content) < 100:
        raise ValueError("LICENSE is missing substantive terms")
    if any(token in content.casefold() for token in ("choose a license", "license goes here")):
        raise ValueError("LICENSE still contains placeholder instructions")
    if not notices_file.is_file():
        raise ValueError("NOTICE.md is missing substantive third-party attribution")
    notices = notices_file.read_text(encoding="utf-8").strip()
    if len(notices) < 100:
        raise ValueError("NOTICE.md is missing substantive third-party attribution")
    if "lgpl distribution review: approved" not in notices.casefold():
        raise ValueError(
            "LGPL distribution review must be marked APPROVED in NOTICE.md before release"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        verify_release_legal_files(args.root)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"Release legal preflight blocked: {exc}", file=sys.stderr)
        return 1
    print("LICENSE and NOTICE files present; LGPL distribution review is approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
