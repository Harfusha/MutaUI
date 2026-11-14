from __future__ import annotations

import hashlib

import pytest

from scripts.write_checksums import write_checksums


def test_write_checksums_are_stable_sorted_and_exclude_themselves(tmp_path):
    (tmp_path / "zeta.bin").write_bytes(b"zeta")
    (tmp_path / "Alpha.bin").write_bytes(b"alpha")

    output = write_checksums(tmp_path)

    assert output.name == "SHA256SUMS.txt"
    assert output.read_text(encoding="ascii").splitlines() == [
        f"{hashlib.sha256(b'alpha').hexdigest()}  Alpha.bin",
        f"{hashlib.sha256(b'zeta').hexdigest()}  zeta.bin",
    ]


def test_write_checksums_requires_at_least_one_asset(tmp_path):
    with pytest.raises(ValueError, match="No release assets"):
        write_checksums(tmp_path)
