"""Generate the checked-in Settings reference from the typed help registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from forward_configuration import render_forward_reference  # noqa: E402
from mutaui.ui.settings_registry import render_reference  # noqa: E402
from sync_configuration import render_sync_reference  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the reference is stale.")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "settings-reference.md")
    args = parser.parse_args()
    expected = (
        render_reference() + "\n" + render_sync_reference() + "\n" + render_forward_reference()
    )
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != expected:
            print(f"Settings reference is stale: {args.output}", file=sys.stderr)
            return 1
        print(f"Settings reference is current: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(expected, encoding="utf-8")
    print(f"Generated settings reference: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
