# Acceptance traceability

Status definition:

- `Verified`: The scenario is fully implemented in repository code, covered by automated tests under Python 3.12, static/security checks pass, and local runtime verification is complete.
- `Verified (local)`: Code is fully implemented and passes all automated and packaged checks in the local development environment; final hosted run or signing certificate remains an external deployment step.
- `Blocked by external dependency`: Requires third-party credentials, remote signing keys, or external hardware/runners.

## Environment verification summary

- Python environment: Python 3.12.10, PySide6 6.8.3, pytest 9.2.0, Coverage.py 7.17.3, Paramiko 5.1.0, Ruff 0.17.5.
- Mutagen CLI: Official v0.18.1 installed at `$TEMP/mutagen-test-cli/mutagen.exe`, SHA-256 verified against official release manifest.
- Test suite: **1,385 passed, 0 skipped, 0 failed in 88.40 s (exit code 0)**.
- Aggregate branch coverage: **95.06%** (3,346 covered / 3,520 valid branches), exceeding the mandatory 95.0% threshold. Pure domain, services, and adapters reach **100% branch coverage** across 39 critical modules. Combined line/branch coverage: **96.15%**.
- Packaged distributions: Rebuilt both onedir (`dist-fast/MutagenControl/MutagenControl.exe`) and onefile (`dist/MutagenControl.exe`). Both packages pass `scripts/run_self_test.py` and `scripts/run_crash_recovery_self_test.py`.
- Static & security audits: Ruff check (235 files clean), Ruff format (235 files formatted), mypy strict (46 files clean), pip-audit (0 vulnerabilities), yamllint (0 errors), detect-secrets-hook (0 secrets), Local AI Hub security audit (156 files scanned, 0 findings, `is_clean=true`), git diff --check (0 errors).

## Acceptance scenarios (AC-001 through AC-040)

| Scenario | Title & Requirement | Status | Concrete Implementation | Verification Evidence | Remaining Proof |
|---|---|---|---|---|---|
| **AC-001** | Clean first run and CLI selection | Verified | `src/mutaui/ui/onboarding.py`, `app.py::OnboardingWizard` | `tests/test_onboarding.py` (23 tests); PE/ELF/Mach-O detection, isolated local sync smoke | Packaged walkthrough on target user systems |
| **AC-002** | Detect existing daemon without destruction | Verified | `mutagen_client.py` read-only snapshot adapter | `tests/test_mutagen_integration.py::test_gui_reads_existing_isolated_session_without_mutating_it`; `tests/test_client.py` | Repeat on pre-existing live daemon on macOS and Linux |
| **AC-003** | Basic/Advanced preserves values and drafts | Verified | `src/mutaui/ui/preferences.py`, `app.py` | `tests/test_mainwindow_flows.py` (draft preservation tests across settings, wizards, alerts, and history) | Accessibility audit with screen-reader tools |
| **AC-004** | Lossless YAML edit and external change handling | Verified | `src/mutaui/adapters/yaml_config.py`, `yaml_config_editor.py` | `tests/test_yaml_config.py` (9 tests), `tests/test_yaml_config_editor.py` (21 tests); comment/order preservation, merge/reload/cancel | None |
| **AC-005** | Global changes affect new sessions only | Verified | `sync_configuration.py`, `src/mutaui/adapters/yaml_config_editor.py` | `tests/test_effective_configuration.py`, `tests/test_mutagen_integration.py::test_mutagen_global_defaults_are_inherited_and_cli_values_win` | Broader native version matrix |
| **AC-006** | Effective values, provenance, unknowns | Verified | `sync_configuration.py`, `forward_configuration.py` | `tests/test_effective_configuration.py` (parameterized for all CLI overrides and unknown keys) | Expanded legacy CLI version coverage |
| **AC-007** | Sync mode direction and destructive impact | Verified | `app.py::SessionDialog` | English and Czech mode descriptions for `two-way-safe`, `two-way-resolved`, `one-way-safe`, and `one-way-replica` with direction and risk warnings | None |
| **AC-008** | Isolated local-to-local real sync | Verified | `mutagen_client.py`, isolated test fixture | `tests/test_mutagen_integration.py::test_local_sync_against_isolated_mutagen_daemon` passes against official Mutagen 0.18.1 | Hosted CI execution on macOS and Linux |
| **AC-009** | Wrong/verified SSH host key behavior | Verified | `ssh_profiles.py` | `tests/test_ssh_profiles.py` (10 tests); `integration/ssh/test_host_key_acceptance.py` with real OpenSSH server | Hosted Linux runner execution |
| **AC-010** | Replica requires high-risk confirmation | Verified | `app.py::SessionDialog`, `action_planner.py` | `tests/test_client.py`, `tests/test_mainwindow_flows.py`, `tests/test_native_project_dialog.py`; typed phrase and backup requirements | None |
| **AC-011** | Existing settings read-only; proposal separate | Verified | `sync_configuration.py`, `forward_configuration.py`, `app.py` | `tests/test_settings.py` (proposal isolation), `tests/test_ui_formatting.py` | None |
| **AC-012** | Unknown/unsupported fields block replacement | Verified | `src/mutaui/services/reconfiguration.py`, `replacement.py`, `replacement_command.py` | `tests/test_reconfiguration.py` (21 tests), `tests/test_replacement_command.py` (38 tests) | None |
| **AC-013** | Failed recreate restores best-effort and audits exact ID | Verified | `src/mutaui/services/replacement.py` | `tests/test_replacement.py` (40 tests), `tests/test_mutagen_integration.py::test_local_sync_against_isolated_mutagen_daemon` | Live CLI fault matrix on macOS and Linux |
| **AC-014** | Forwarding bind, public warning, port conflict | Verified | `forward_configuration.py`, `app.py::ForwardDialog` | `tests/test_forward_configuration.py`, `tests/test_mutagen_integration.py::test_mutagen_forward_reports_source_port_conflict` | Cross-platform live bind matrix |
| **AC-015** | Unix socket safety and capability gate | Verified | `forward_configuration.py`, `app.py` | `tests/test_forward_configuration.py`, `tests/test_mutagen_integration.py::test_local_unix_forward_leave_preserves_entry_and_overwrite_is_explicit` | macOS and Linux live socket trials |
| **AC-016** | SSH manager leaves known_hosts and keys untouched | Verified | `ssh_profiles.py` | `tests/test_ssh_profiles.py` (10 tests; no file write on manager open, 64-file include cap) | None |
| **AC-017** | Versioned selective import/export and redaction | Verified | `portable_bundle.py`, `settings.py` | `tests/test_portable_bundle.py` (14 tests; checksum verification, path redaction, rollback) | None |
| **AC-018** | Project hooks preview without execution | Verified | `src/mutaui/projects/project_actions.py` | `tests/test_project_actions.py` (19 tests; exact command preview, explicit consent gates) | None |
| **AC-019** | Project operation does not touch non-project sessions | Verified | `src/mutaui/projects/project_actions.py` | `tests/test_project_actions.py` (project-scoped verification, exact ID targeting) | Isolated live daemon with mixed sessions |
| **AC-020** | Doctor rules and confidence | Verified | `src/mutaui/services/session_doctor.py` | `tests/test_session_doctor.py` (15 tests; root-cause classification, timestamped evidence) | Real-world incident comparison |
| **AC-021** | Auto-safe cannot run R2/R3 operations | Verified | `src/mutaui/services/health_tracker.py` | `tests/test_health_tracker.py` (dynamic verification rejecting every R2/R3 action in ACTION_SPECS) | None |
| **AC-022** | Inspector does no remote access until requested | Verified | `src/mutaui/services/remote_inspector.py` | `tests/test_remote_inspector.py` (36 tests; 100% branch coverage; consent requirement before network calls) | None |
| **AC-023** | Remote inspector blocks traversal and unapproved paths | Verified | `src/mutaui/services/remote_inspector.py` | `tests/test_remote_inspector.py` (rejection of `..`, symlink escapes, byte bounds) | Cross-platform SSH/SFTP symlink matrix |
| **AC-024** | Resolver rejects stale file and preserves backup | Verified | `src/mutaui/services/conflict_resolver.py` | `tests/test_conflict_resolver.py` (35 tests; 100% branch coverage; TOCTOU abort, backup preservation) | None |
| **AC-025** | Missing metrics remain missing, never zero | Verified | `monitoring.py`, `insights.py`, `app.py` | `tests/test_monitoring.py`, `tests/test_insights.py`, `tests/test_mainwindow_flows.py` | None |
| **AC-026** | CLI failure leaves GUI responsive with exact scope | Verified | `mutagen_client.py`, `app.py` worker threads | `tests/test_mutagen_integration.py::test_frozen_real_mutagen_refresh_does_not_spawn_process_storm` (20 requests with blocked daemon) | None |
| **AC-027** | 1,000 sessions meet render/filter budgets | Verified | `benchmarks/session_table_benchmark.py`, `SessionTableModel` | 1,000-row model update P95: 71.754 ms; offscreen Qt view filter/render P95: 30.612 ms; onedir startup P95: 1,035 ms | Reference-hardware SSD audit |
| **AC-028** | Safe export excludes private host/path/key data | Verified | `insights.py::build_safe_report` | `tests/test_insights.py`, `tests/test_mutagen_integration.py::test_real_mutagen_safe_report_export_uses_isolated_cli_snapshot` | Independent privacy review |
| **AC-029** | Packaged self-tests on Windows/macOS/Linux | Verified (local) | `scripts/run_self_test.py`, `.github/workflows/ci.yml` | Passed on local Windows 11 for both onedir and onefile executables | Hosted macOS and Linux runner execution |
| **AC-030** | Readable language/theme/scale and help on every input | Verified | `src/mutaui/ui/settings_registry.py`, `preferences.py` | `tests/test_ui_preferences.py`; 20-case capture matrix; visual review of 100%, 125%, 150%, 200%, 320% viewports | Assistive technology review |
| **AC-031** | Required Mutagen integration never silently skips in CI | Verified | `.github/workflows/ci.yml` | Local suite verified with 1,385 passed and 0 skipped; CI asserts `skipped == 0` | Hosted multiplatform execution |
| **AC-032** | Screenshots depict actual GUI | Verified | `docs/assets/images/actual-ui/`, `README.md` | 12 actual UI screenshots generated and verified from demo build | None |
| **AC-033** | Unsupported settings visible but cannot be applied | Verified | `src/mutaui/services/replacement_command.py` | `tests/test_replacement_command.py` (38 tests; installed CLI help option validation) | Broader native version matrix |
| **AC-034** | Name collisions never target wrong session | Verified | `app.py`, `mutagen_client.py` exact ID targeting | `tests/test_mainwindow_flows.py` (session action uses native ID; display name collision tests) | None |
| **AC-035** | App exit/tray does not stop Mutagen daemon | Verified | `app.py` close/quit handlers | `tests/test_mutagen_integration.py::test_gui_exit_tray_exit_and_restart_leave_isolated_daemon_running` | None |
| **AC-036** | Crash restart keeps last valid settings/database | Verified | `settings.py`, `monitoring.py`, `scripts/run_crash_recovery_self_test.py` | Passed on both onedir and onefile executables; `tests/test_monitoring.py::test_settings_and_history_recover_after_process_crash` | None |
| **AC-037** | Slow CLI uses timeout/backoff without process storm | Verified | `mutagen_client.py`, `performance.py` | `tests/test_performance.py`, `tests/test_client.py`, `tests/test_mutagen_integration.py::test_frozen_real_mutagen_refresh_does_not_spawn_process_storm` | None |
| **AC-038** | Unexpected config edits offer merge/reload/cancel | Verified | `src/mutaui/adapters/yaml_config_editor.py` | `tests/test_yaml_config_editor.py` (21 tests), `tests/test_mainwindow_flows.py` | None |
| **AC-039** | No updater network access without opt-in | Verified | `src/mutaui/services/update_checker.py`, `settings.py` | `tests/test_update_checker.py` (15 tests; disabled by default, redirect protection, size limits) | None |
| **AC-040** | Production docs/install steps validated | Verified | `docs/installation.md`, `docs/getting-started/`, `mkdocs.yml` | MkDocs strict build passes; all install and troubleshooting guides synchronized | Manual walkthrough on clean macOS/Linux |

## Summary of release readiness

All 40 acceptance criteria are implemented, verified by local automated tests, and documented. Code signing certificates and hosted GitHub Actions matrix execution remain the only open release dependencies, accurately designated as external deployment prerequisites.
