"""Inject accurate version and system compatibility metadata into macOS Info.plist."""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path


def resolve_version() -> str:
    root = Path(__file__).resolve().parents[2]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            with pyproject.open("rb") as fp:
                data = tomllib.load(fp)
                ver = data.get("project", {}).get("version")
                if ver:
                    return str(ver).strip()
        except Exception:
            pass
    init_py = root / "src" / "mutaui" / "__init__.py"
    if init_py.is_file():
        for line in init_py.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "9.2.0"


def patch_plist(plist_path: Path, version: str) -> None:
    if not plist_path.is_file():
        raise FileNotFoundError(f"Info.plist not found at: {plist_path}")

    with plist_path.open("rb") as fp:
        plist_data = plistlib.load(fp)

    plist_data["CFBundleShortVersionString"] = version
    plist_data["CFBundleVersion"] = version
    if plist_data.get("CFBundleIdentifier") in (None, "", "MutagenControl"):
        plist_data["CFBundleIdentifier"] = "io.mutagen.control"
    # Qt6 Cocoa framework requires minimum macOS 12.0
    plist_data.setdefault("LSMinimumSystemVersion", "12.0")
    plist_data.setdefault(
        "NSHumanReadableCopyright",
        "Copyright © 2026 Mutagen Control contributors",
    )

    with plist_path.open("wb") as fp:
        plistlib.dump(plist_data, fp, fmt=plistlib.FMT_XML)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python patch_macos_plist.py <path_to_Info.plist> [version]", file=sys.stderr)
        return 1

    plist_path = Path(args[0]).resolve()
    version = args[1] if len(args) > 1 else resolve_version()
    version = version.lstrip("v")
    patch_plist(plist_path, version)
    print(f"Patched {plist_path} with version {version} and minimum macOS 12.0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
