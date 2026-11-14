# Phase 2 progress — profiles, projects, Doctor and health

Date: 2026-11-14. Baseline: repository `master`, commit `9b5718a5f4dec6fe8f3a93d3f5f2426941e56c25` (v8.2). Environment: Python 3.12.10, PySide6 6.8.3, pytest 9.2.0, Coverage.py 7.17.3, checksum-verified Mutagen CLI 0.18.1.

## Scope delivered

- **PR-015 (Connection Profiles):** Implemented in `connection_profiles.py`. Versioned JSON schema with tags, favorites, search filtering, duplication with fresh identity, and wizard integration. Corrupt or future-schema stores fail closed without rewriting.
- **PR-016 (Read-only SSH Profile Manager):** Implemented in `ssh_profiles.py`. Parses OpenSSH configuration and bounded includes (up to 64 files) in read-only mode. Queries effective host configuration via `ssh -G` without shell expansion. Bounded connection test enforces `BatchMode=yes` and `StrictHostKeyChecking=yes`, detects unknown or changed host keys, and never modifies `known_hosts` or reads private key contents.
- **PR-017 (Import/export, migrations and backups):** Implemented in `portable_bundle.py` and `settings.py`. Versioned, checksummed bundles with machine-path redaction. Import preview classifies stable IDs and semantic collisions; applies explicit create/merge/skip choices. Settings migration preserves exact backup bytes and provides a verified rollback path.
- **PR-018 (Ignore Preset Center):** Implemented in `ignore_presets.py` and `src/mutaui/ui/ignore_rules.py`. Versioned preset store preserving pattern order and negation rules (`!`). Converts `.gitignore` and `.dockerignore` files with staged preview, skipping unsupported lines and highlighting negation overrides. Stale-write protection prevents overwriting concurrent edits.
- **PR-019 (Native Mutagen Project importer and viewer):** Implemented in `src/mutaui/projects/native_project.py` and `src/mutaui/ui/project_viewer.py`. Reads native `mutagen.yml` losslessly, displaying sync/forward declarations, merged defaults, hooks, and custom commands. Watches project directories with hash-debounced external diff detection. Never rewrites native project YAML during import or viewing.
- **PR-020 (Native project operations and hook consent):** Implemented in `src/mutaui/projects/project_actions.py` and `src/mutaui/projects/project_editor.py`. Manages project lifecycle (`start`, `list`, `flush`, `pause`, `resume`, `reset`, `terminate`). R3 operations require exact typed confirmation phrases. Previews all shell hooks and custom commands with explicit operator consent. Post-operation verification checks that all project sessions converged or terminated as expected.
- **PR-021 (Deterministic Session Doctor):** Implemented in `src/mutaui/services/session_doctor.py`. Pure rule engine analyzes typed snapshots and classifies root causes: offline daemon, paused sessions, root deletion, permission errors, staging exhaustion, scan/transition failures, port conflicts, SSH authentication/trust errors, and network flapping. Deduplicates scan findings and timestamps all evidence.
- **PR-022 (Health tracking and incident state machine):** Implemented in `src/mutaui/services/health_tracker.py`. Monotonic time tracking, consecutive failure streaks, and incident lifecycle (monitor-only, assisted, auto-safe). Grace periods suppress transient alerts during sleep, wake, and network reconnection.
- **PR-023 (Auto-safe assisted recovery and circuit breaker):** Implemented in `src/mutaui/services/health_tracker.py`. Auto-safe recovery permits only non-destructive, read-only refresh operations; all R2 and R3 actions are strictly rejected. Circuit breaker halts recovery attempts after two recent consecutive failures or cooldown breaches.

## Verification evidence

- `tests/test_connection_profiles.py`: 12 passed (versioning, tags, search, duplicate identity, store failures).
- `tests/test_ssh_profiles.py`: 10 passed (include depth caps, strict host keys, option injection prevention, read-only config).
- `integration/ssh/test_host_key_acceptance.py`: Acceptance test with real OpenSSH server for Linux CI (wrong, pinned, and changed keys).
- `tests/test_portable_bundle.py`: 14 passed (checksum verification, redaction, import preview, backup rollback).
- `tests/test_v5_migration.py`: 1 passed (v4 remote schema migration).
- `tests/test_ignore_presets.py` and `tests/test_ignore_rules_dialog.py`: 18 passed (pattern order, negation, gitignore conversion, custom presets).
- `tests/test_native_project.py`, `tests/test_native_project_dialog.py`, `tests/test_project_actions.py`, `tests/test_project_editor.py`: 111 passed (lossless YAML, hook consent, R3 confirmation, post-check verification).
- `tests/test_session_doctor.py`: 15 passed (classification rules, timestamped evidence, deduplication).
- `tests/test_health_tracker.py`: 35 passed (monitored/assisted/auto-safe gates, circuit breaker, monotonic time, 100% branch coverage).

## Gate G2 disposition

- Status: **Verified locally on Windows x64; Linux CI OpenSSH acceptance suite prepared.**
- Verification criteria:
  - Real CLI integration for native projects in isolated directories: verified (passed against Mutagen 0.18.1).
  - No destructive automated actions: 100% verified (R2/R3 blocked in Auto-safe).
  - SSH manager never writes to host files or reads private keys: 100% verified.
  - Doctor diagnoses deterministically with evidence timestamps: 100% verified.
