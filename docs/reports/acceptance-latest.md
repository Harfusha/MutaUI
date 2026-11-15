# Acceptance and Verification Evidence Report

**Generated:** 2026-11-15 07:48:09 UTC  
**Commit:** `592cf7d5fbd3f015ef5354b9e8300da020d58b22` (master)  
**Working tree dirty:** true  
**Status:** **PASSED**

## Environment Evidence

| Component | Detected Value |
|---|---|
| Platform / OS | `Windows-11-10.0.26300-SP0` (`AMD64`) |
| Python Runtime | `3.12.10` |
| Mutagen CLI | `0.18.1` |
| Runner Host | `AdamPC` |
| CI Run ID | `local-run` |

## Test Suite Execution Summary

| Metric | Measured Value | Required Gate | Status |
|---|---|---|---|
| Total Executed Tests | **1423** | > 0 | PASS |
| Passed Tests | **1423** | All non-skipped | PASS |
| Test Failures | **0** | 0 | PASS |
| Test Errors | **0** | 0 | PASS |
| Skipped Tests | **0** | 0 (no CI skips allowed) | PASS |
| Branch Coverage | **95.00%** (3061/3222) | >= 95.00% | PASS |
| Line Coverage | **96.62%** | Reference | INFO |

## Criteria Traceability Summary

- **P0 Gates (QA-001 - QA-006):** Verified against strict exit code runner, isolated daemon harness, and deterministic advisor.
- **P1 Gates (QA-007 - QA-014, QA-023):** Verified against 95%+ branch coverage, supply chain digests, modular Qt architecture, and honest third-party notices.
- **P2 Polish (QA-015 - QA-020):** Validated on synthetic performance baselines and platform compatibility matrix.

> Report generated automatically by `scripts/ci/generate_acceptance_report.py`.
