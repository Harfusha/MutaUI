"""Release legal preflight cannot silently pick an open-source license."""

from pathlib import Path

import pytest

from scripts.ci.check_release_license import verify_release_legal_files


def test_release_license_gate_fails_without_owner_license(tmp_path: Path) -> None:
    (tmp_path / "NOTICE.md").write_text("Third-party notices " * 10, encoding="utf-8")
    with pytest.raises(ValueError, match="choose and commit a LICENSE"):
        verify_release_legal_files(tmp_path)


def test_release_license_gate_rejects_placeholder(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Choose a license " * 15, encoding="utf-8")
    (tmp_path / "NOTICE.md").write_text("Third-party notices " * 10, encoding="utf-8")
    with pytest.raises(ValueError, match="placeholder"):
        verify_release_legal_files(tmp_path)


def test_release_license_gate_accepts_owner_supplied_terms_and_notices(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text(
        "Custom legal text supplied by the project owner, for automated shape testing only. " * 4,
        encoding="utf-8",
    )
    (tmp_path / "NOTICE.md").write_text("Third-party notices " * 10, encoding="utf-8")
    verify_release_legal_files(tmp_path)
