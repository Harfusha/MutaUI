"""JUnit XML validator for MutaUI CI gates.

Validates that all required test suites ran without failures, errors, or skips.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TypedDict


class JUnitSummary(TypedDict):
    tests: int
    failures: int
    errors: int
    skipped: int


def parse_and_validate_junit(xml_path: str | Path, allow_skipped: bool = False) -> JUnitSummary:
    path = Path(xml_path)
    if not path.is_file():
        raise FileNotFoundError(f"JUnit XML report not found at {path}")

    try:
        tree = ET.parse(path)
    except Exception as exc:
        raise ValueError(f"Failed to parse JUnit XML report at {path}: {exc}") from exc

    root = tree.getroot()
    total_tests = 0
    failures = 0
    errors = 0
    skipped = 0

    # Handles both <testsuites> container and root <testsuite>
    suites = list(root.iter("testsuite"))
    if not suites and root.tag == "testsuite":
        suites = [root]

    for suite in suites:
        total_tests += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))

    # Also double check testcase elements directly in case suite attributes are missing
    if total_tests == 0:
        cases = list(root.iter("testcase"))
        total_tests = len(cases)
        for case in cases:
            if case.find("failure") is not None:
                failures += 1
            if case.find("error") is not None:
                errors += 1
            if case.find("skipped") is not None:
                skipped += 1

    summary: JUnitSummary = {
        "tests": total_tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
    }

    if total_tests == 0:
        raise ValueError(f"JUnit XML report at {path} contains 0 executed tests.")
    if failures > 0:
        raise ValueError(f"JUnit validation failed: {failures} test failure(s) recorded in {path}.")
    if errors > 0:
        raise ValueError(f"JUnit validation failed: {errors} test error(s) recorded in {path}.")
    if skipped > 0 and not allow_skipped:
        raise ValueError(
            f"JUnit validation failed: {skipped} skipped test(s) recorded in {path}. "
            "CI quality gates require 0 skipped tests."
        )

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate JUnit XML test results.")
    parser.add_argument("junit_xml", type=Path, help="Path to junit XML file")
    parser.add_argument(
        "--allow-skipped",
        action="store_true",
        help="Allow skipped tests instead of failing",
    )
    args = parser.parse_args(argv)

    try:
        summary = parse_and_validate_junit(args.junit_xml, allow_skipped=args.allow_skipped)
        print(
            f"JUnit XML valid: {summary['tests']} tests passed, "
            f"0 failures, 0 errors, {summary['skipped']} skipped."
        )
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
