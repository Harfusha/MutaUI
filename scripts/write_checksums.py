"""Write deterministic SHA-256 sums for flat release assets."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def write_checksums(directory: Path) -> Path:
    root = directory.resolve(strict=True)
    output = root / "SHA256SUMS.txt"
    assets = sorted(
        (path for path in root.iterdir() if path.is_file() and path != output),
        key=lambda path: path.name.casefold(),
    )
    if not assets:
        raise ValueError(f"No release assets found in {root}")
    lines = []
    for asset in assets:
        with asset.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {asset.name}")
    output.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return output


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    print(write_checksums(target))
