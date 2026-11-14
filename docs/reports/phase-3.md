# Phase 3 progress — conflicts and reconfiguration

Date: 2026-11-14. Baseline: repository `master`, commit `9b5718a5f4dec6fe8f3a93d3f5f2426941e56c25` (v8.2). Environment: Python 3.12.10, PySide6 6.8.3, pytest 9.2.0, Coverage.py 7.17.3, checksum-verified Mutagen CLI 0.18.1.

## Scope delivered

- **PR-024 (Conflict Inspector read-only view):** Implemented in `src/mutaui/services/conflict_inspector.py` and `src/mutaui/ui/conflict_inspector_dialog.py`. Displays structured conflict lists from native snapshots without fetching remote file contents. Normalizes conflict types (creation, modification, deletion) across ALPHA and BETA. Safe local file opening enforces root containment, directory existence, and symlink/junction escape rejection.
- **PR-025 (ActionPlanner and risk tier policy):** Implemented in `src/mutaui/services/action_planner.py`. Central execution gate enforcing risk tiers: R0 (read-only), R1 (reversible UI operations), R2 (reset/recreate), and R3 (destructive filesystem mutation, replicas, and hook execution). Requires explicit typed consent phrases for R3 operations. Generates immutable audit logs with execution receipts and post-operation verification.
- **PR-026 (Reconfiguration planner and command snapshot validator):** Implemented in `src/mutaui/services/reconfiguration.py`. Compares current session native configuration against proposed edits. Rejects reconfiguration when unknown native configuration groups or unsupported flags exist. Validates that all fields can round-trip losslessly to CLI arguments before planning.
- **PR-027 (Controlled session replacement):** Implemented in `src/mutaui/services/replacement.py` and `src/mutaui/services/replacement_command.py`. Bounded replacement workflow for non-project sync sessions: preflight check, creation of replacement with new parameters, termination of old session by exact ID, and best-effort restore if creation fails. Checks installed CLI help options to ensure all flags and enum values are natively supported.
- **PR-028 (Project-owned configuration edits):** Implemented in `src/mutaui/projects/project_editor.py` and `src/mutaui/ui/project_yaml_editor_dialog.py`. Enforces that project-managed sessions are reconfigured exclusively through `mutagen.yml` edits with staged previews, source-hash pinning, and atomic writes. Rejects detached recreation of project sessions.
- **PR-029 (Opt-in remote inspection and trust boundary):** Implemented in `src/mutaui/services/remote_inspector.py`. User-authorized, read-only SSH/SFTP inspection of remote conflicting files. Validates remote path containment, refuses directory traversal (`..`), checks symlink targets, enforces byte limits, and verifies host key against pinned identities. Documented in `docs/security/remote-inspection.md`.
- **PR-030 (Diff integration and artifact lifecycle):** Implemented in `src/mutaui/services/diff_integration.py`. Generates temporary side-by-side or unified diffs from inspected remote copies. Tracks artifact lifecycle, cleans temporary files on dialog close, and handles background process exit safely.
- **PR-031 (Manual per-file conflict resolution):** Implemented in `src/mutaui/services/conflict_resolver.py`. Feature-gated, per-file manual resolution (ALPHA wins or BETA wins). Mandatory preflight rechecks hashes on both endpoints; creates full backups outside the sync root; applies atomic replacement; flushes and verifies convergence; and rolls back to backup if convergence fails. Disallows mass replica conversion.
- **PR-032 (Scoped conflict recommendations):** Implemented in `src/mutaui/services/conflict_recommendations.py` and `src/mutaui/ui/conflict_recommendations_dialog.py`. Rule-based advisory suggestions based on file patterns (e.g. build artifacts, lockfiles). Explicit opt-in required; recommendations remain purely advisory and never trigger automatic resolution.

## Verification evidence

- `tests/test_conflict_inspector.py` and `tests/test_conflict_inspector_dialog.py`: 37 passed (read-only view, containment, symlink/junction escape rejection, deferred dialog close).
- `tests/test_action_planner.py`: 21 passed (R0-R3 risk tiers, exact phrase confirmation, state machine, audit log).
- `tests/test_reconfiguration.py`: 21 passed (snapshot validation, unknown group rejection, diff generation, round-trip contract).
- `tests/test_replacement.py` and `tests/test_replacement_command.py`: 78 passed (exact-ID cleanup, restore on error, installed CLI help matching, prefix collision avoidance).
- `tests/test_remote_inspector.py`: 36 passed (100% branch coverage; traversal rejection, symlink checks, size bounds, SSH option safety).
- `tests/test_diff_integration.py`: 12 passed (temporary file lifecycle, process tracking, cleanup).
- `tests/test_conflict_resolver.py`: 35 passed (100% branch coverage; preflight recheck, backup creation, TOCTOU abort, restore rollback).
- `tests/test_conflict_recommendations.py` and `tests/test_conflict_recommendations_dialog.py`: 22 passed (opt-in gating, advice authoring, rule evaluation).

## Gate G3 disposition

- Status: **Verified locally on Windows x64; complete fault-injection and rollback tests pass.**
- Verification criteria:
  - Complete injected fault matrix for file mutation: verified (all TOCTOU, backup, and replace failures restore or retain backups safely).
  - No mass replica conflict resolution: verified (conflict resolver operates only on individual files with explicit per-file confirmation).
  - Project sessions reconfigured only via `mutagen.yml`: verified.
  - Remote inspection strictly read-only and user-authorized: verified.
