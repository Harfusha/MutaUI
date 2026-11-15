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

    # Prevent double-counting by avoiding recursive iter("testsuite") on nested containers
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
        if not suites:
            # Fallback if testsuites has no direct child testsuite but has testcases
            suites = [root]
    else:
        suites = [root]

    total_tests = 0
    failures = 0
    errors = 0
    skipped = 0

    for suite in suites:
        cases = suite.findall("testcase")
        has_cases = len(cases) > 0

        suite_tests_attr = suite.get("tests")
        suite_failures_attr = suite.get("failures")
        suite_errors_attr = suite.get("errors")
        suite_skipped_attr = suite.get("skipped")

        suite_tests = int(suite_tests_attr) if suite_tests_attr is not None else len(cases)
        suite_failures = int(suite_failures_attr) if suite_failures_attr is not None else 0
        suite_errors = int(suite_errors_attr) if suite_errors_attr is not None else 0
        suite_skipped = int(suite_skipped_attr) if suite_skipped_attr is not None else 0

        if has_cases:
            # Verify consistency between declared metadata and actual testcase elements
            actual_cases = len(cases)
            if suite_tests_attr is not None and suite_tests != actual_cases:
                raise ValueError(
                    f"JUnit XML inconsistent summary in suite '{suite.get('name', 'default')}': "
                    f"declared tests={suite_tests} but found {actual_cases} <testcase> elements in {path}."
                )

            actual_failures = sum(1 for c in cases if c.find("failure") is not None)
            if suite_failures_attr is not None and suite_failures != actual_failures:
                raise ValueError(
                    f"JUnit XML inconsistent summary in suite '{suite.get('name', 'default')}': "
                    f"declared failures={suite_failures} but found {actual_failures} <failure> elements in {path}."
                )

            actual_errors = sum(1 for c in cases if c.find("error") is not None)
            if suite_errors_attr is not None and suite_errors != actual_errors:
                raise ValueError(
                    f"JUnit XML inconsistent summary in suite '{suite.get('name', 'default')}': "
                    f"declared errors={suite_errors} but found {actual_errors} <error> elements in {path}."
                )

            actual_skipped = sum(1 for c in cases if c.find("skipped") is not None)
            if suite_skipped_attr is not None and suite_skipped != actual_skipped:
                raise ValueError(
                    f"JUnit XML inconsistent summary in suite '{suite.get('name', 'default')}': "
                    f"declared skipped={suite_skipped} but found {actual_skipped} <skipped> elements in {path}."
                )

        total_tests += suite_tests
        failures += suite_failures
        errors += suite_errors
        skipped += suite_skipped

    # If suite attributes were completely absent and total_tests is 0, check root cases
    if total_tests == 0:
        all_cases = list(root.iter("testcase"))
        total_tests = len(all_cases)
        for case in all_cases:
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
