# E22 Performance Tuning Assistant Implementation Plan

> **For agentic workers:** Implement this plan task by task. Keep native session state read-only.

**Goal:** Add an optional Advanced assistant that offers documented, qualitative Mutagen tuning advice as a local replacement proposal.

**Architecture:** A pure service analyzes the selected sync snapshot and bounded local endpoint metadata. A focused Qt dialog presents warnings and optional suggestions. The existing Session Settings proposal table remains the sole draft/apply path; no live command runs from the assistant.

**Tech Stack:** Python, pathlib/os metadata, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-e22-performance-tuning-assistant.md`

## Global Constraints

- Mutagen session export is the source of truth; missing values stay unknown.
- No filesystem recursion or remote probing.
- Do not report invented speed, CPU, I/O, or entry counts.
- Existing-session changes require the existing reviewed replacement flow.
- EN/CS user-facing copy; no new runtime dependency.

## Review Focus

- Unknown/malformed native data never becomes a confident recommendation.
- Root symlinks, inaccessible roots, and remote endpoints are handled without traversal or remote access.
- A staging mismatch only suggests endpoint-local neighboring staging for the affected local root.
- Cancelling or viewing guidance cannot mutate session state or invoke Mutagen.
- Assistant suggestions only populate the current local proposal draft.

---

## Tasks

- [x] Add failing service tests for documented thresholds, unknown entry counts, path safety, permissions, and staging devices.
- [x] Implement a pure qualitative advisor and bounded local-root checks.
- [x] Add localized Advanced dialog and proposal-table integration; never call replacement from the assistant.
- [x] Add Qt flow tests for cancel, optional application, and no live command.
- [x] Document official sources, run focused tests and source/lint checks, then update E22 traceability.

Verification (2026-11-14): 19 advisor tests passed with 100% branch coverage for `performance_advisor.py`; 6 dialog tests and 7 focused MainWindow performance tests passed. The offline test set reported 1,350 passed, 12 skipped, 95.81% total coverage; pytest printed a passing summary but the Python 3.13.2 process exited abnormally with status 1 (the project requires Python 3.12). Ruff, format check (235 files), `verify_source.py`, strict mypy for the pure advisor, and `git diff --check` passed. Hub security audit scanned 156 files with zero findings. The dialog module's strict mypy check could not be repeated because PySide6 stubs are unavailable in this Python 3.13 environment; its earlier check passed before the final advisor-only changes.
