"""Cross-platform test runner and gatekeeper for MutaUI CI and release workflows.

Guarantees fail-fast semantics across Windows (cmd/pwsh), macOS, and Linux:
1. Executes pytest subprocess and captures exit code.
2. Validates JUnit XML report (0 failures, 0 errors, 0 skipped).
3. Validates branch coverage (>= 95%).
4. Exits with non-zero exit code if any gate fails.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from pathlib import Path

# Allow importing sibling modules in scripts/ci
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from validate_junit import parse_and_validate_junit
except ImportError:
    from scripts.ci.validate_junit import parse_and_validate_junit


def validate_branch_coverage(coverage_xml_path: str | Path, min_rate: float = 0.95) -> float:
    path = Path(coverage_xml_path)
    if not path.is_file():
        raise FileNotFoundError(f"Coverage XML report not found at {path}")

    try:
        root = ET.parse(path).getroot()
        covered = int(root.get("branches-covered", "0"))
        total = int(root.get("branches-valid", "0"))
    except Exception as exc:
        raise ValueError(f"Failed to parse coverage XML at {path}: {exc}") from exc

    if total == 0:
        raise ValueError(f"No branch information found in coverage report at {path}")

    rate = covered / total
    print(f"Branch coverage: {covered}/{total} = {rate:.2%}")
    if rate < min_rate:
        raise ValueError(
            f"Branch coverage {rate:.2%} is below the required threshold of {min_rate:.2%}"
        )
    return rate


def run_tests(
    pytest_args: list[str] | None = None,
    junit_xml: Path = Path("test-results/pytest.xml"),
    coverage_xml: Path = Path("coverage.xml"),
    min_branch_coverage: float = 0.95,
    skip_coverage_check: bool = False,
    allow_skipped_tests: bool = False,
) -> int:
    junit_xml.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "-rs",
        f"--junitxml={junit_xml}",
    ]

    has_explicit_path = bool(pytest_args and any(not a.startswith("-") for a in pytest_args))
    if not has_explicit_path:
        cmd.append("tests")

    if not skip_coverage_check:
        cmd.extend(
            [
                "--cov",
                "--cov-branch",
                "--cov-report=term-missing:skip-covered",
                f"--cov-report=xml:{coverage_xml}",
            ]
        )

    # Mutagen's Unix-domain daemon socket has a strict path-length limit.
    # macOS CI's default pytest temporary tree exceeds this on long test names.
    # Scope each run to a unique short path; never touch the user's daemon.
    with ExitStack() as cleanup:
        custom_basetemp = any(
            arg == "--basetemp" or arg.startswith("--basetemp=") for arg in (pytest_args or [])
        )
        if sys.platform in {"darwin", "linux"} and not custom_basetemp:
            temp_base = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="mu-", dir="/tmp"))
            cmd.append(f"--basetemp={temp_base}")

        if pytest_args:
            cmd.extend(pytest_args)

        print(f"[run_tests] Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd)

    if result.returncode != 0:
        print(f"[run_tests] Pytest failed with exit code {result.returncode}", file=sys.stderr)
        # Even on failure, inspect junit if generated to print exact counts
        if junit_xml.is_file():
            try:
                parse_and_validate_junit(junit_xml, allow_skipped=allow_skipped_tests)
            except Exception as parse_err:
                print(f"[run_tests] JUnit verification detail: {parse_err}", file=sys.stderr)
        return result.returncode or 1

    # Pytest reported 0 exit code - now enforce strict gate assertions:
    try:
        parse_and_validate_junit(junit_xml, allow_skipped=allow_skipped_tests)
    except Exception as exc:
        print(f"[run_tests] Gate failure: {exc}", file=sys.stderr)
        return 1

    if not skip_coverage_check:
        try:
            validate_branch_coverage(coverage_xml, min_rate=min_branch_coverage)
        except Exception as exc:
            print(f"[run_tests] Coverage gate failure: {exc}", file=sys.stderr)
            return 1

    print("[run_tests] All CI quality gates PASSED.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MutaUI CI Test Runner and Gatekeeper.")
    parser.add_argument(
        "--junit-xml",
        type=Path,
        default=Path("test-results/pytest.xml"),
        help="Path for JUnit XML output",
    )
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        default=Path("coverage.xml"),
        help="Path for coverage XML output",
    )
    parser.add_argument(
        "--min-branch-coverage",
        type=float,
        default=0.95,
        help="Minimum required branch coverage (default 0.95)",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Skip coverage check",
    )
    parser.add_argument(
        "--allow-skipped",
        action="store_true",
        help="Allow skipped tests in JUnit report",
    )
    parser.add_argument(
        "pytest_extra_args",
        nargs="*",
        help="Extra arguments passed directly to pytest",
    )
    args, extra_args = parser.parse_known_args(argv)
    forwarded_args = list(args.pytest_extra_args)
    if extra_args:
        if extra_args[0] == "--":
            extra_args = extra_args[1:]
        forwarded_args.extend(extra_args)

    return run_tests(
        pytest_args=forwarded_args if forwarded_args else None,
        junit_xml=args.junit_xml,
        coverage_xml=args.coverage_xml,
        min_branch_coverage=args.min_branch_coverage,
        skip_coverage_check=args.skip_coverage,
        allow_skipped_tests=args.allow_skipped,
    )


if __name__ == "__main__":
    sys.exit(main())
