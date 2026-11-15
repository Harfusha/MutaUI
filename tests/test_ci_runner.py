"""Tests and negative probes for CI test runner and JUnit validator (QA-001 / P0-01 / F2-001 / F2-003)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci.install_actionlint import (
    ACTIONLINT_SHA256,
    ACTIONLINT_VERSION,
    extract_verified_actionlint,
    verify_sha256,
)
from scripts.ci.run_tests import run_tests, validate_branch_coverage
from scripts.ci.validate_junit import parse_and_validate_junit


def test_validate_junit_success(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="0" errors="0" skipped="0">
    <testcase classname="test_foo" name="test_one" time="0.01"/>
    <testcase classname="test_foo" name="test_two" time="0.02"/>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    summary = parse_and_validate_junit(xml_file)
    assert summary["tests"] == 2
    assert summary["failures"] == 0
    assert summary["errors"] == 0
    assert summary["skipped"] == 0


def test_validate_junit_fails_on_inconsistent_summary(tmp_path: Path) -> None:
    # Suite claims 10 tests, but only contains 1 testcase
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="10" failures="0" errors="0" skipped="0">
    <testcase classname="test_foo" name="test_one" time="0.01"/>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "inconsistent.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="inconsistent summary"):
        parse_and_validate_junit(xml_file)


def test_validate_junit_fails_on_inconsistent_failures_count(tmp_path: Path) -> None:
    # Suite claims 0 failures, but contains a failed testcase
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1" failures="0" errors="0" skipped="0">
    <testcase classname="test_foo" name="test_one"><failure message="boom">err</failure></testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "inconsistent_fail.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="inconsistent summary"):
        parse_and_validate_junit(xml_file)


def test_validate_junit_fails_on_malformed_xml(tmp_path: Path) -> None:
    malformed_file = tmp_path / "malformed.xml"
    malformed_file.write_text("<testsuites><unclosed>", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to parse JUnit XML report"):
        parse_and_validate_junit(malformed_file)


def test_validate_junit_fails_on_failure(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1" failures="1" errors="0" skipped="0">
    <testcase classname="test_foo" name="test_one"><failure message="failed">assert False</failure></testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="1 test failure"):
        parse_and_validate_junit(xml_file)


def test_validate_junit_fails_on_error(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1" failures="0" errors="1" skipped="0">
    <testcase classname="test_foo" name="test_err"><error message="collection error"/></testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="1 test error"):
        parse_and_validate_junit(xml_file)


def test_validate_junit_fails_on_skipped_by_default(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="1" failures="0" errors="0" skipped="1">
    <testcase classname="test_foo" name="test_skip"><skipped/></testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="1 skipped test"):
        parse_and_validate_junit(xml_file)

    # When explicitly allowed:
    summary = parse_and_validate_junit(xml_file, allow_skipped=True)
    assert summary["skipped"] == 1


def test_validate_junit_fails_on_zero_tests(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="0" failures="0" errors="0" skipped="0"/>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="0 executed tests"):
        parse_and_validate_junit(xml_file)


def test_validate_branch_coverage_threshold(tmp_path: Path) -> None:
    # 96% branch coverage: covered=96, valid=100
    xml_passing = """<?xml version="1.0" ?>
<coverage branches-covered="96" branches-valid="100" line-rate="0.99" branch-rate="0.96"/>
"""
    pass_file = tmp_path / "cov_pass.xml"
    pass_file.write_text(xml_passing, encoding="utf-8")

    rate = validate_branch_coverage(pass_file, min_rate=0.95)
    assert rate == 0.96

    # 90% branch coverage: covered=90, valid=100
    xml_fail = """<?xml version="1.0" ?>
<coverage branches-covered="90" branches-valid="100" line-rate="0.95" branch-rate="0.90"/>
"""
    fail_file = tmp_path / "cov_fail.xml"
    fail_file.write_text(xml_fail, encoding="utf-8")

    with pytest.raises(ValueError, match="below the required threshold"):
        validate_branch_coverage(fail_file, min_rate=0.95)


def test_actionlint_checksum_verification_success_and_tampered_fail(tmp_path: Path) -> None:
    # 1. Verification of real pinned constants
    assert ACTIONLINT_VERSION == "1.7.12"
    assert ACTIONLINT_SHA256 == "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"

    # 2. Positive probe with matching file and hash
    probe_file = tmp_path / "sample.tar.gz"
    probe_file.write_bytes(b"trusted actionlint archive content")
    import hashlib

    real_hash = hashlib.sha256(b"trusted actionlint archive content").hexdigest()
    assert verify_sha256(probe_file, real_hash) is True

    # 3. Negative probe with tampered file
    tampered_file = tmp_path / "tampered.tar.gz"
    tampered_file.write_bytes(b"tampered content")
    with pytest.raises(ValueError, match="SHA-256 verification failed"):
        verify_sha256(tampered_file, real_hash)


def test_run_tests_negative_probe_fails_on_pytest_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC-N01: when pytest returns 1, run_tests MUST exit with non-zero exit code."""
    junit_file = tmp_path / "junit.xml"
    cov_file = tmp_path / "cov.xml"

    class FakeCompletedProcess:
        returncode = 1

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeCompletedProcess())

    exit_code = run_tests(
        junit_xml=junit_file,
        coverage_xml=cov_file,
        skip_coverage_check=True,
    )
    assert exit_code != 0, "run_tests must return non-zero when pytest exits non-zero"


def test_run_tests_negative_probe_fails_when_pytest_zero_but_junit_has_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """AC-N02: when pytest returns 0 but JUnit reports failures, run_tests MUST fail."""
    junit_file = tmp_path / "junit.xml"
    junit_file.write_text(
        """<testsuites><testsuite name="p" tests="1" failures="1" errors="0" skipped="0">
  <testcase classname="test_p" name="test_one"><failure message="fail">err</failure></testcase>
</testsuite></testsuites>""",
        encoding="utf-8",
    )
    cov_file = tmp_path / "cov.xml"

    class FakeCompletedProcess:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeCompletedProcess())

    exit_code = run_tests(
        junit_xml=junit_file,
        coverage_xml=cov_file,
        skip_coverage_check=True,
    )
    assert exit_code != 0, "run_tests must fail if JUnit reports failures despite pytest exitcode 0"


def test_run_tests_e2e_failing_test_fails_runner(tmp_path: Path) -> None:
    """AC-N03: real pytest execution on an injected failing test must fail run_tests."""
    failing_test = tmp_path / "test_injected_fail.py"
    failing_test.write_text("def test_injected(): assert False\n", encoding="utf-8")

    junit_file = tmp_path / "junit_fail.xml"
    cov_file = tmp_path / "cov_fail.xml"

    exit_code = run_tests(
        pytest_args=[str(failing_test)],
        junit_xml=junit_file,
        coverage_xml=cov_file,
        skip_coverage_check=True,
    )
    assert exit_code != 0, "run_tests must return non-zero when a test actually fails in pytest"


def test_run_tests_cli_invocation_negative_probe(tmp_path: Path) -> None:
    """Invoking run_tests.py as subprocess with an invalid test filter exits non-zero."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "ci" / "run_tests.py"
    res = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--skip-coverage",
            "tests/test_app_import.py",
            "-k",
            "non_existent_test_filter_xyz_123456",
        ],
        capture_output=True,
        text=True,
    )
    # Pytest returns exit code 5 when no tests match the filter, which runner must preserve as non-zero failure
    assert res.returncode != 0


def test_actionlint_tar_rejects_symlink_member(tmp_path: Path) -> None:
    import tarfile

    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("actionlint")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        tar.addfile(member)

    with pytest.raises(ValueError, match="regular binary"):
        extract_verified_actionlint(archive, tmp_path / "extract")
    assert not (tmp_path / "outside").exists()


def test_actionlint_tar_extracts_only_pinned_regular_member(tmp_path: Path) -> None:
    import io
    import tarfile

    archive = tmp_path / "safe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("actionlint")
        payload = b"synthetic test ELF content"
        member.size = len(payload)
        tar.addfile(member, io.BytesIO(payload))

        irrelevant = tarfile.TarInfo("../unrelated")
        irrelevant.size = 6
        tar.addfile(irrelevant, io.BytesIO(b"ignore"))

    destination = extract_verified_actionlint(archive, tmp_path / "extract")
    assert destination.read_bytes() == b"synthetic test ELF content"
    assert not (tmp_path / "unrelated").exists()


def test_actionlint_download_rejects_oversize_without_replacing_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from scripts.ci import install_actionlint as installer

    archive = tmp_path / "actionlint.tar.gz"
    archive.write_bytes(b"already-verified-payload")
    monkeypatch.setattr(installer, "MAX_ACTIONLINT_ARCHIVE_BYTES", 8)
    monkeypatch.setattr(
        installer.urllib.request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(b"too many bytes for this archive"),
    )

    with pytest.raises(ValueError, match="exceeds size limit"):
        installer.download_actionlint_archive(archive)

    assert archive.read_bytes() == b"already-verified-payload"
    assert not list(tmp_path.glob(".actionlint-download-*"))


def test_actionlint_download_stages_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from scripts.ci import install_actionlint as installer

    archive = tmp_path / "actionlint.tar.gz"
    monkeypatch.setattr(
        installer.urllib.request,
        "urlopen",
        lambda _url, timeout: io.BytesIO(b"test-archive"),
    )
    installer.download_actionlint_archive(archive)
    assert archive.read_bytes() == b"test-archive"
    assert not list(tmp_path.glob(".actionlint-download-*"))
