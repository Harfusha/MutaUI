"""Audit bundled native libraries (.dll, .so, .dylib) against inventory and version baseline."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeLibraryRecord:
    name: str
    path: str
    category: str
    component: str
    declared_version: str | None
    license: str
    bundled_purpose: str
    max_glibc_symbol: str | None = None


# Known baseline metadata for components bundled in MutaUI desktop distributions
COMPONENT_REGISTRY = {
    "qt": {
        "pattern": re.compile(r"(?:Qt6|libQt6|libqcocoa|libqxcb|libqwindows)", re.IGNORECASE),
        "component": "Qt6",
        "category": "GUI Framework",
        "declared_version": "6.8.3",
        "license": "LGPL-3.0-only",
        "purpose": "Application user interface and event loop",
    },
    "python": {
        "pattern": re.compile(r"(?:python3\d*|libpython3\.\d+|Python\.framework)", re.IGNORECASE),
        "component": "Python Runtime",
        "category": "Interpreter",
        "declared_version": "3.12",
        "license": "PSF-2.0",
        "purpose": "Application execution runtime",
    },
    "openssl": {
        "pattern": re.compile(r"(?:libcrypto|libssl|crypto|ssl)", re.IGNORECASE),
        "component": "OpenSSL",
        "category": "Cryptography",
        "declared_version": "3.0+",
        "license": "Apache-2.0",
        "purpose": "Secure networking and TLS/SSH cryptographic primitives",
    },
    "sqlite": {
        "pattern": re.compile(r"(?:sqlite3|libsqlite3)", re.IGNORECASE),
        "component": "SQLite",
        "category": "Database",
        "declared_version": "3.45+",
        "license": "Public Domain",
        "purpose": "Local event log and history persistence",
    },
}


def scan_glibc_symbols(binary_path: Path) -> str | None:
    """Extract highest GLIBC symbol version referenced by an ELF binary if readable."""
    try:
        content = binary_path.read_bytes()
    except (OSError, PermissionError):
        return None
    matches = re.findall(rb"GLIBC_(\d+\.\d+)", content)
    if not matches:
        return None
    versions: list[tuple[int, int]] = []
    for m in matches:
        parts = m.decode("ascii", errors="ignore").split(".")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            versions.append((int(parts[0]), int(parts[1])))
    if not versions:
        return None
    max_ver = max(versions)
    return f"GLIBC_{max_ver[0]}.{max_ver[1]}"


def classify_library(file_path: Path) -> NativeLibraryRecord:
    name = file_path.name
    matched_component = "Other"
    matched_category = "Native Dependency"
    matched_version = None
    matched_license = "Proprietary / System / Other"
    matched_purpose = "Bundled runtime dependency"

    for _, meta in COMPONENT_REGISTRY.items():
        if meta["pattern"].search(name):
            matched_component = str(meta["component"])
            matched_category = str(meta["category"])
            matched_version = str(meta["declared_version"])
            matched_license = str(meta["license"])
            matched_purpose = str(meta["purpose"])
            break

    glibc_ver = scan_glibc_symbols(file_path) if file_path.suffix in (".so", "") else None

    return NativeLibraryRecord(
        name=name,
        path=str(file_path),
        category=matched_category,
        component=matched_component,
        declared_version=matched_version,
        license=matched_license,
        bundled_purpose=matched_purpose,
        max_glibc_symbol=glibc_ver,
    )


def audit_directory(root_dir: Path) -> list[NativeLibraryRecord]:
    records: list[NativeLibraryRecord] = []
    if not root_dir.exists():
        return records

    extensions = {".dll", ".so", ".dylib"}
    for root, _, files in os.walk(root_dir):
        for f in files:
            path = Path(root) / f
            if path.suffix.lower() in extensions or ".so." in f:
                records.append(classify_library(path))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit bundled native libraries.")
    parser.add_argument("directory", nargs="?", default=".", help="Root directory to scan")
    parser.add_argument("--json", action="store_true", help="Output audit as JSON")
    parser.add_argument("--output", help="Write audit report to file")
    args = parser.parse_args(argv)

    root = Path(args.directory).resolve()
    records = audit_directory(root)

    report_data = {
        "scanned_directory": str(root),
        "total_libraries": len(records),
        "components": {
            comp: len([r for r in records if r.component == comp])
            for comp in {"Qt6", "Python Runtime", "OpenSSL", "SQLite", "Other"}
        },
        "records": [asdict(r) for r in records],
    }

    output_text = json.dumps(report_data, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Audit report written to: {args.output}")
    elif args.json:
        print(output_text)
    else:
        print(f"Audit completed: {len(records)} native libraries found in {root}.")
        for comp, count in report_data["components"].items():
            print(f"  - {comp}: {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
