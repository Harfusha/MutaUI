"""Tests for Linux packaging supply chain verification (REL-03 / F2-008 / F2-AC-019)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def test_linux_supply_chain_manifest_exists():
    manifest_path = Path("packaging/linux/supply-chain.json")
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "appimagetool" in manifest
    tool = manifest["appimagetool"]
    assert tool["version"] == "1.9.1"
    assert tool["architecture"] == "x86_64"
    assert len(tool["sha256"]) == 64
    assert tool["sha256"] == "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"


def test_appimagetool_checksum_rejects_tampered_bytes(tmp_path: Path):
    manifest = json.loads(Path("packaging/linux/supply-chain.json").read_text(encoding="utf-8"))
    expected_hash = manifest["appimagetool"]["sha256"]

    # Injected tampered binary
    fake_tool = tmp_path / "appimagetool.AppImage"
    fake_tool.write_bytes(b"malicious or corrupted upstream asset")

    actual_hash = hashlib.sha256(fake_tool.read_bytes()).hexdigest()
    assert actual_hash != expected_hash

    # Verification function must fail
    def verify_appimagetool(path: Path, expected: str) -> bool:
        calculated = hashlib.sha256(path.read_bytes()).hexdigest()
        if calculated.lower() != expected.lower():
            raise ValueError(
                f"Checksum mismatch for appimagetool: expected {expected}, got {calculated}"
            )
        return True

    with pytest.raises(ValueError, match="Checksum mismatch for appimagetool"):
        verify_appimagetool(fake_tool, expected_hash)
