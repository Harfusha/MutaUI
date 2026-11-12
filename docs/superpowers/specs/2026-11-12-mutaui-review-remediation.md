# MutaUI v8.2 Review Remediation Specification

## Purpose

Address every actionable recommendation in the supplied repository review. Prioritize packaged-app reliability, settings safety, and protection against destructive session creation. Improve runtime consistency and large-session performance without a broad rewrite. Preserve existing user data and unrelated working-tree changes.

## Accepted Review Findings

### P1: Reliability and operation safety

1. Settings loading must accept only a JSON object, validate supported values and types, apply documented defaults and migrations, and recover safely from malformed or incompatible data. Recovery must preserve the original file until the user saves a valid replacement.
2. Creating `two-way-resolved` must require a clear confirmation that ALPHA wins conflict resolution. Creating `one-way-replica` must require a clear confirmation that extra BETA files can be deleted. Cancel must prevent the corresponding Mutagen command.
3. Add opt-in integration coverage using the real Mutagen CLI and isolated temporary local endpoints when the CLI is installed. Keep SSH/recovery validation opt-in and document its environment requirements; never report it as run unless it was.
4. CI must print and upload packaged self-test diagnostics on failure. Push and pull-request events must run lightweight static and test checks; expensive PyInstaller packaging remains manually dispatchable.

### P2: Runtime correctness, scale, and maintainability

5. A failed refresh must preserve the most recent valid session snapshot and show an explicit stale/offline state rather than replacing useful data with an empty snapshot.
6. Refresh work must carry a monotonically increasing generation or equivalent request identity. Results older than the newest applicable request must not overwrite current state.
7. Forwarding-rate samples must use the time of an actual measurement. UI metric rendering must not manufacture repeated measurements; traffic sampling and display refresh must be independent.
8. Replace the highest-volume `QTableWidget` usage with a `QTableView` and model where it reduces per-row widget/item overhead while preserving selection, sorting, filtering, and actions.
9. Extend the benchmark to synthetic session counts of 10, 100, 500, and 1,000 and report repeatable timing and memory data without presenting synthetic values as live measurements.
10. Reduce `app.py` coupling incrementally by extracting the safety-critical settings/refresh or table logic touched by this work. Do not perform a wholesale GUI rewrite.

### P3: Documentation, dependencies, and privacy

11. Remove hard-coded historical test totals from README; document commands and test categories instead.
12. Expand Ruff rules to `E9`, `F`, `B`, `I`, `UP`, and selected `SIM` rules, fixing findings without unrelated behavior changes.
13. Use `PySide6-Essentials` instead of the full PySide6 meta-package only if every required import, GUI test, and PyInstaller build remains supported. Otherwise document why the full package is required.
14. Before exporting a full snapshot, clearly warn that endpoint addresses, paths, session names, identifiers, and state may be sensitive. The user must explicitly confirm before the file is written.

## Constraints

- Do not reset, terminate, replace, or otherwise mutate a user's real Mutagen session during tests.
- No real SSH host or credentials are required for the normal test suite.
- Preserve the last valid settings and session data during recovery.
- Keep the native Mutagen CLI as the sync engine.
- Keep existing user-facing behavior unless a review finding calls for a safety or correctness change.
- Keep the existing CI diagnostic change and unrelated working-tree state.
- Distinguish deterministic unit/GUI tests from live-daemon, SSH, Windows EXE, and visual/runtime evidence.

## Acceptance Criteria

- Settings shape and supported value validation have isolated regression tests, including JSON list/scalar input and malformed values.
- Destructive-mode confirmations are tested for accept and cancel, and cancel is proven to issue no create command.
- Failed refresh and out-of-order completion tests prove last-known-good and newest-generation behavior.
- Traffic tests prove timestamped measurements are emitted only when sampled.
- The table model is exercised with generated large datasets and keeps existing per-row commands tied to the correct identifier.
- Benchmarks cover exactly 10, 100, 500, and 1,000 synthetic sessions.
- CI has lightweight push/PR checks, dispatch-only packaging, and a diagnostic artifact step that tolerates a missing log.
- Optional real Mutagen tests isolate daemon state and local endpoints; skipped/unavailable external validations are reported honestly.
- Ruff, docs, dependency declarations, and export warning agree with actual source behavior.
- Full targeted test suite, source checks, GUI smoke, and packaged EXE self-test are run where the host supports them; unavailable platform/runtime checks remain explicit.
