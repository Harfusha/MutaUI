"""Generates verified acceptance and traceability report from test artifacts.

P1-01 / QA-009: Ingests JUnit XML, Coverage XML, Git provenance, and environment
metadata to produce an honest, machine-generated evidence report.
"""

from __future__ import annotations

import argparse
import datetime
import os
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def get_git_info() -> dict[str, str]:
    git_bin = shutil.which("git") or "git"
    try:
        commit = subprocess.check_output(
            [git_bin, "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        short_commit = subprocess.check_output(
            [git_bin, "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        branch = subprocess.check_output(
            [git_bin, "rev-parse", "--abbrev-ref", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        is_dirty = bool(
            subprocess.check_output(
                [git_bin, "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except Exception:
        commit = os.environ.get("GITHUB_SHA", "unknown")
        short_commit = commit[:7] if commit != "unknown" else "unknown"
        branch = os.environ.get("GITHUB_REF_NAME", "unknown")
        is_dirty = True  # Unknown Git provenance must never produce release PASS.

    return {
        "commit": commit,
        "short_commit": short_commit,
        "branch": branch,
        "dirty": str(is_dirty).lower(),
    }


def parse_junit(junit_path: Path) -> dict[str, int]:
    """Count leaf suites exactly once, including nested JUnit hierarchies.

    Aggregate parent testsuite metadata already includes nested child suites.
    Summing both levels double-counts tests and can falsely certify a report.
    """
    empty = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "passed": 0}
    if not junit_path.is_file():
        return empty

    root = ET.parse(junit_path).getroot()
    leaf_suites = [
        suite
        for suite in root.iter("testsuite")
        if not any(child.tag == "testsuite" for child in suite)
    ]
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}

    if leaf_suites:
        for suite in leaf_suites:
            cases = list(suite.findall("testcase"))
            fallback = {
                "tests": len(cases),
                "failures": sum(c.find("failure") is not None for c in cases),
                "errors": sum(c.find("error") is not None for c in cases),
                "skipped": sum(c.find("skipped") is not None for c in cases),
            }
            for key in totals:
                totals[key] += int(suite.get(key, fallback[key]))
    else:
        cases = list(root.iter("testcase"))
        totals.update(
            tests=len(cases),
            failures=sum(c.find("failure") is not None for c in cases),
            errors=sum(c.find("error") is not None for c in cases),
            skipped=sum(c.find("skipped") is not None for c in cases),
        )

    if any(value < 0 for value in totals.values()):
        raise ValueError("JUnit counters may not be negative")
    if totals["failures"] + totals["errors"] + totals["skipped"] > totals["tests"]:
        raise ValueError("JUnit failures, errors and skips exceed test count")
    return {
        **totals,
        "passed": (
            totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
        ),
    }


def parse_coverage(coverage_path: Path) -> dict[str, float | int]:
    if not coverage_path.is_file():
        return {
            "branch_coverage": 0.0,
            "branches_covered": 0,
            "branches_valid": 0,
            "line_coverage": 0.0,
        }

    tree = ET.parse(coverage_path)
    root = tree.getroot()

    covered = int(root.get("branches-covered", "0"))
    total = int(root.get("branches-valid", "0"))
    rate = (covered / total) if total > 0 else 0.0
    line_rate = float(root.get("line-rate", "0.0"))
    if covered < 0 or total < 0 or covered > total or not 0.0 <= line_rate <= 1.0:
        raise ValueError("Coverage report contains invalid counters or rates")

    return {
        "branch_coverage": rate,
        "branches_covered": covered,
        "branches_valid": total,
        "line_coverage": line_rate,
    }


def get_mutagen_version() -> str:
    binary = os.environ.get("MUTAGEN_BINARY") or "mutagen"
    resolved_bin = shutil.which(binary) or binary
    try:
        out = subprocess.check_output(
            [resolved_bin, "version"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        return out.splitlines()[0] if out else "not detected"
    except Exception:
        return "not detected / isolated CLI"


def generate_report(
    junit_path: Path,
    coverage_path: Path,
    output_path: Path,
) -> str:
    git_info = get_git_info()
    junit_stats = parse_junit(junit_path)
    cov_stats = parse_coverage(coverage_path)
    mutagen_ver = get_mutagen_version()
    clean = git_info["dirty"] == "false"
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    expected_sha = os.environ.get("GITHUB_SHA")
    matches_ci_commit = bool(expected_sha and expected_sha == git_info["commit"])
    now_utc = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    exit_status = (
        "PASSED"
        if (
            junit_stats["tests"] > 0
            and junit_stats["failures"] == 0
            and junit_stats["errors"] == 0
            and junit_stats["skipped"] == 0
            and cov_stats["branch_coverage"] >= 0.95
            and clean
            and (not in_ci or matches_ci_commit)
        )
        else "FAILED / GATES UNMET"
    )

    if exit_status == "PASSED":
        exit_status = (
            "LOCAL TESTS PASSED (NOT RELEASE CERTIFIED)"
            if not in_ci
            else "CI TESTS PASSED (NOT RELEASE CERTIFIED)"
        )

    content = f"""# Acceptance and Verification Evidence Report

**Generated:** {now_utc}  
**Commit:** `{git_info["commit"]}` ({git_info["branch"]})  
**Working tree dirty:** {git_info["dirty"]}  
**CI SHA matches checkout:** {"yes" if matches_ci_commit else "not verified" if in_ci else "local only"}  
**Status:** **{exit_status}**

## Environment Evidence

| Component | Detected Value |
|---|---|
| Platform / OS | `{platform.platform()}` (`{platform.machine()}`) |
| Python Runtime | `{sys.version.split()[0]}` |
| Mutagen CLI | `{mutagen_ver}` |
| Runner Host | `redacted` |
| CI Run ID | `{os.environ.get("GITHUB_RUN_ID", "local-run")}` |

## Test Suite Execution Summary

| Metric | Measured Value | Required Gate | Status |
|---|---|---|---|
| Total Executed Tests | **{junit_stats["tests"]}** | > 0 | {"PASS" if junit_stats["tests"] > 0 else "FAIL"} |
| Passed Tests | **{junit_stats["passed"]}** | All non-skipped | {"PASS" if junit_stats["passed"] == junit_stats["tests"] else "WARN"} |
| Test Failures | **{junit_stats["failures"]}** | 0 | {"PASS" if junit_stats["failures"] == 0 else "FAIL"} |
| Test Errors | **{junit_stats["errors"]}** | 0 | {"PASS" if junit_stats["errors"] == 0 else "FAIL"} |
| Skipped Tests | **{junit_stats["skipped"]}** | 0 (no CI skips allowed) | {"PASS" if junit_stats["skipped"] == 0 else "FAIL"} |
| Branch Coverage | **{cov_stats["branch_coverage"]:.2%}** ({cov_stats["branches_covered"]}/{cov_stats["branches_valid"]}) | >= 95.00% | {"PASS" if cov_stats["branch_coverage"] >= 0.95 else "FAIL"} |
| Line Coverage | **{cov_stats["line_coverage"]:.2%}** | Reference | INFO |

## Criteria Traceability Summary

- **P0 gates:** Only local suite counters and coverage are represented in this report. Hosted CI security, daemon and integration results require separate evidence.
- **P1 gates:** Packaging, supply chain, native OS behavior and license require separate verified evidence from the same commit.
- **P2 gates:** Visual QA, accessibility and measured resource budgets are not established by JUnit XML.

> This report describes **only** the test artifacts provided. It does not prove package signing, native GUI accessibility, all-platform acceptance or a release. Generated by `scripts/ci/generate_acceptance_report.py`.
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Report generated: {output_path}")
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate verified acceptance report.")
    parser.add_argument(
        "--junit-xml",
        type=Path,
        default=Path("test-results/pytest.xml"),
        help="Path to pytest.xml",
    )
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        default=Path("coverage.xml"),
        help="Path to coverage.xml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/reports/acceptance-latest.md"),
        help="Output markdown report path",
    )
    args = parser.parse_args(argv)

    generate_report(args.junit_xml, args.coverage_xml, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
