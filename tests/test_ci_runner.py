"""Tests and negative probes for CI test runner and JUnit validator (QA-001 / P0-01)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci.run_tests import run_tests, validate_branch_coverage
from scripts.ci.validate_junit import parse_and_validate_junit


def test_validate_junit_success(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="10" failures="0" errors="0" skipped="0">
    <testcase classname="test_foo" name="test_one" time="0.01"/>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    summary = parse_and_validate_junit(xml_file)
    assert summary["tests"] == 10
    assert summary["failures"] == 0
    assert summary["errors"] == 0
    assert summary["skipped"] == 0


def test_validate_junit_fails_on_failure(tmp_path: Path) -> None:
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="10" failures="1" errors="0" skipped="0">
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
  <testsuite name="pytest" tests="5" failures="0" errors="1" skipped="0">
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
  <testsuite name="pytest" tests="5" failures="0" errors="0" skipped="2">
    <testcase classname="test_foo" name="test_skip"><skipped/></testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "junit.xml"
    xml_file.write_text(xml_content, encoding="utf-8")

    with pytest.raises(ValueError, match="2 skipped test"):
        parse_and_validate_junit(xml_file)

    # When explicitly allowed:
    summary = parse_and_validate_junit(xml_file, allow_skipped=True)
    assert summary["skipped"] == 2


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
        """<testsuites><testsuite name="p" tests="1" failures="1" errors="0" skipped="0"/></testsuites>""",
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


def test_run_tests_cli_invocation_negative_probe(tmp_path: Path) -> None:
    """Invoking run_tests.py as subprocess with an invalid test flag exits with code 1."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "ci" / "run_tests.py"
    res = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--skip-coverage",
            "-k",
            "non_existent_test_filter_xyz_123456",
        ],
        capture_output=True,
        text=True,
    )
    # Pytest returns exit code 5 when no tests match the filter, which runner must preserve as non-zero failure
    assert res.returncode != 0
