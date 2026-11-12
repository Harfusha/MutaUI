# MutaUI Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Resolve all actionable findings in the supplied MutaUI v8.2 review with safe, testable changes and no broad rewrite.

**Architecture:** Keep the Mutagen CLI as the engine. Isolate settings validation and table data from the 3,200-line GUI module where practical; keep runtime state transitions explicit and generation-aware. Separate normal CI checks from manually dispatched packaging and clearly distinguish synthetic, local integration, and live SSH evidence.

**Tech Stack:** Python 3.12, PySide6, pytest, Ruff, PyInstaller, GitHub Actions, Mutagen CLI.

**Spec:** `docs/superpowers/specs/2026-11-12-mutaui-review-remediation.md`

## Global Constraints

- Preserve existing user data and local changes.
- Do not mutate the user's real sessions in tests.
- No real SSH credentials in the standard test suite.
- Retain the native Mutagen CLI as the sync engine.
- No wholesale GUI rewrite.
- Never label synthetic benchmarks or optional integration tests as live validation.

## Review Focus

- Settings file contains valid JSON with the wrong root type; loader must recover without overwriting it.
- Risky mode confirmation is cancelled; no Mutagen create command may run.
- A refresh fails after prior success; the UI must retain data and mark it stale/offline.
- Older async refresh completes after a newer one; it must be discarded.
- UI refresh occurs between traffic measurements; no duplicate measurement may be recorded.

---

### Task 1: Safe settings and session creation

**Files:** `app.py`, new `settings.py`, settings and GUI tests.

- [ ] Add typed settings schema/defaults and migration with safe preservation of invalid input.
- [ ] Route settings reads and writes through the schema boundary.
- [ ] Add explicit informed confirmation for `two-way-resolved` and `one-way-replica`.
- [ ] Prove rejection/cancel leaves settings intact and calls no Mutagen create command.
- [ ] Run targeted settings and session-creation tests.

### Task 2: Refresh consistency and measurement timing

**Files:** `app.py`, `mutagen_client.py`, `monitoring.py`, `performance.py`, focused tests.

- [ ] Preserve the last valid session snapshot after a failed refresh and expose stale/offline status.
- [ ] Add refresh generations and ignore results older than the current generation.
- [ ] Timestamp forwarding measurements at the source poll and separate sample timing from UI refresh timing.
- [ ] Add deterministic failure-order and sample-timing tests.
- [ ] Run focused tests and GUI smoke where PySide6 is available.

### Task 3: Scalable session tables and benchmark

**Files:** new `session_table_model.py`, `app.py`, new or updated benchmark module, GUI and performance tests.

- [ ] Identify the highest-volume tables and replace per-cell item storage with a shared `QAbstractTableModel`/`QTableView` path.
- [ ] Preserve sorting, selection, empty states, and identifier-bound row actions.
- [ ] Add a synthetic benchmark for 10, 100, 500, and 1,000 sessions with timing and memory output.
- [ ] Run GUI/model tests and benchmark smoke.

### Task 4: CI, integration coverage, and quality gates

**Files:** `.github/workflows/windows-build.yml`, `tests`, `requirements-build.txt`, `pyproject.toml` or Ruff config.

- [ ] Keep self-test tracebacks visible and upload the log as a diagnostic artifact even after job failure.
- [ ] Run lightweight test/lint jobs on push and pull request; keep PyInstaller builds dispatch-only.
- [ ] Add opt-in isolated local Mutagen integration tests and document SSH recovery prerequisites.
- [ ] Expand Ruff to `E9,F,B,I,UP,SIM` and fix findings.
- [ ] Evaluate `PySide6-Essentials`; retain full PySide6 if tests or packaging show it is needed.
- [ ] Run the full portable test and packaging checks supported by the host.

### Task 5: Export warning and documentation cleanup

**Files:** `app.py`, `README.md`, `ARCHITECTURE.md`, `docs/TESTING.md`, tests.

- [ ] Require explicit confirmation before full snapshot export and describe sensitive fields.
- [ ] Remove fixed test counts and document current commands and validation boundaries.
- [ ] Record dependency and integration-test decisions accurately.
- [ ] Run targeted UI and documentation/source checks.

### Task 6: Final integration and evidence

**Files:** all changed paths.

- [ ] Review complete diff for regressions and preserved unrelated work.
- [ ] Run Ruff, `verify_source.py`, unit tests, GUI smoke, coverage, and available integration tests.
- [ ] Run packaged EXE self-test on Windows; otherwise leave it explicitly pending for CI.
- [ ] Record actual results, skipped environment checks, and remaining external validation.
