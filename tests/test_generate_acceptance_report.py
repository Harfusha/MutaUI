"""Tests for generate_acceptance_report.py (QA-009 / P1-01)."""

from __future__ import annotations

from pathlib import Path

from scripts.ci.generate_acceptance_report import generate_report, parse_coverage, parse_junit


def test_parse_junit_sample(tmp_path: Path):
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="10" failures="0" errors="0" skipped="0">
    <testcase classname="test_foo" name="test_one"/>
  </testsuite>
</testsuites>
"""
    junit_file = tmp_path / "junit.xml"
    junit_file.write_text(xml_content, encoding="utf-8")

    stats = parse_junit(junit_file)
    assert stats["tests"] == 10
    assert stats["failures"] == 0
    assert stats["passed"] == 10


def test_parse_coverage_sample(tmp_path: Path):
    cov_content = """<?xml version="1.0" ?>
<coverage branches-covered="95" branches-valid="100" line-rate="0.98"/>
"""
    cov_file = tmp_path / "cov.xml"
    cov_file.write_text(cov_content, encoding="utf-8")

    stats = parse_coverage(cov_file)
    assert stats["branches_covered"] == 95
    assert stats["branches_valid"] == 100
    assert stats["branch_coverage"] == 0.95


def test_generate_report_produces_valid_markdown(tmp_path: Path, monkeypatch):
    """A clean local sample should be reported as locally passing, not release certified."""
    from scripts.ci import generate_acceptance_report as report_module

    monkeypatch.setattr(
        report_module,
        "get_git_info",
        lambda: {"commit": "stable", "short_commit": "stable", "branch": "main", "dirty": "false"},
    )
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    junit_file = tmp_path / "junit.xml"
    junit_file.write_text(
        """<testsuites><testsuite name="pytest" tests="5" failures="0" errors="0" skipped="0"/></testsuites>""",
        encoding="utf-8",
    )
    cov_file = tmp_path / "cov.xml"
    cov_file.write_text(
        """<coverage branches-covered="96" branches-valid="100" line-rate="0.99"/>""",
        encoding="utf-8",
    )
    out_file = tmp_path / "acceptance.md"

    text = generate_report(junit_file, cov_file, out_file)
    assert out_file.is_file()
    assert "Acceptance and Verification Evidence Report" in text
    assert "PASSED" in text


def test_dirty_tree_does_not_claim_release_pass(tmp_path: Path, monkeypatch):
    """Even passing XML cannot certify a dirty checkout."""
    from scripts.ci import generate_acceptance_report as report_module

    monkeypatch.setattr(
        report_module,
        "get_git_info",
        lambda: {
            "commit": "abc",
            "short_commit": "abc",
            "branch": "audit",
            "dirty": "true",
        },
    )
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="x"/></testsuite>',
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.xml"
    coverage.write_text('<coverage branches-covered="96" branches-valid="100" line-rate="0.97"/>')
    result = generate_report(junit, coverage, tmp_path / "report.md")
    assert "**Status:** **FAILED / GATES UNMET**" in result
    assert "Runner Host | `redacted`" in result


def test_ci_sha_mismatch_does_not_claim_pass(tmp_path: Path, monkeypatch):
    from scripts.ci import generate_acceptance_report as report_module

    monkeypatch.setattr(
        report_module,
        "get_git_info",
        lambda: {
            "commit": "old",
            "short_commit": "old",
            "branch": "master",
            "dirty": "false",
        },
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "new")
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="x"/></testsuite>',
        encoding="utf-8",
    )
    coverage = tmp_path / "coverage.xml"
    coverage.write_text('<coverage branches-covered="96" branches-valid="100" line-rate="0.97"/>')
    result = generate_report(junit, coverage, tmp_path / "report.md")
    assert "**Status:** **FAILED / GATES UNMET**" in result


def test_unknown_git_provenance_cannot_pass_qa_gate(tmp_path: Path, monkeypatch):
    from scripts.ci import generate_acceptance_report as report_module

    monkeypatch.setattr(
        report_module,
        "get_git_info",
        lambda: {
            "commit": "unknown",
            "short_commit": "unknown",
            "branch": "unknown",
            "dirty": "true",
        },
    )
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="x"/></testsuite>'
    )
    coverage = tmp_path / "c.xml"
    coverage.write_text('<coverage branches-covered="100" branches-valid="100" line-rate="1"/>')
    report = generate_report(junit, coverage, tmp_path / "out.md")
    assert "**Status:** **FAILED / GATES UNMET**" in report
