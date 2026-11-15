"""JUnit XML validator for MutaUI CI gates.

Validates that all required test suites ran without failures, errors, or skips,
and enforces structural integrity between suite metadata and testcase elements.
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
    if root is None or (root.tag != "testsuites" and root.tag != "testsuite"):
        raise ValueError(
            f"Invalid JUnit XML structure at {path}: root tag must be <testsuites> or <testsuite>, got <{getattr(root, 'tag', None)}>"
        )

    # Derive actual counts solely from leaf testcase elements. Nested testsuite
    # summary attributes are aggregate metadata and must not be double-counted.
    cases = list(root.iter("testcase"))
    total_tests = len(cases)
    failures = sum(case.find("failure") is not None for case in cases)
    errors = sum(case.find("error") is not None for case in cases)
    skipped = sum(case.find("skipped") is not None for case in cases)

    # Verify all available suite metadata *against all descendant cases*. This
    # also rejects forged "10 passed" XML containing only one real test case.
    for suite in root.iter("testsuite"):
        descendants = list(suite.iter("testcase"))
        actual = {
            "tests": len(descendants),
            "failures": sum(case.find("failure") is not None for case in descendants),
            "errors": sum(case.find("error") is not None for case in descendants),
            "skipped": sum(case.find("skipped") is not None for case in descendants),
        }
        for field, observed in actual.items():
            declared = suite.get(field)
            if declared is None:
                continue
            try:
                reported = int(declared)
            except ValueError as exc:
                raise ValueError(f"Invalid JUnit {field} counter") from exc
            if reported != observed:
                raise ValueError(
                    f"JUnit XML inconsistent summary in suite '{suite.get('name', 'default')}': "
                    f"declared {field}={reported} but found {observed} actual test entries."
                )

    # Some generators also place aggregate counters on the testsuites root.
    if root.tag == "testsuites":
        actual = {
            "tests": total_tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        }
        for field, observed in actual.items():
            declared = root.get(field)
            if declared is not None and int(declared) != observed:
                raise ValueError("JUnit XML inconsistent summary at root testsuites")

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
    parser = argparse.ArgumentParser(description="Validate JUnit XML reports for CI gatekeeping.")
    parser.add_argument("xml_path", type=Path, help="Path to JUnit XML file")
    parser.add_argument(
        "--allow-skipped",
        action="store_true",
        help="Allow skipped tests (default: disallow)",
    )
    args = parser.parse_args(argv)

    try:
        summary = parse_and_validate_junit(args.xml_path, allow_skipped=args.allow_skipped)
        print(
            f"JUnit validation passed: {summary['tests']} tests executed, "
            f"0 failures, 0 errors, {summary['skipped']} skipped."
        )
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
