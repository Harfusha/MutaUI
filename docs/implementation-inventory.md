# MutaUI implementation inventory

Baseline: repository `master`, commit `9b5718a5f4dec6fe8f3a93d3f5f2426941e56c25` (v8.2). Environment: Python 3.12.10, PySide6 6.8.3, pytest 9.2.0, Coverage.py 7.17.3, checksum-verified Mutagen CLI 0.18.1.

Status definition:

- `verified`: Code is fully implemented, passes automated tests locally under Python 3.12, static checks are green, and documentation is complete.
- `partial`: Implementation is present and passes focused tests, but certain end-to-end integration or cross-platform tests require external hosted infrastructure.
- `blocked by external dependency`: Requires third-party credentials, remote signing keys, or external hardware/runners.

## 1. Functional Epics (E01–E22)

| Epic | Source Code | Test / Manual Evidence | Documentation | OS / Version | Status |
|---|---|---|---|---|---|
| **E01 Onboarding & installation** | `src/mutaui/ui/onboarding.py`, `app.py::OnboardingWizard` | `tests/test_onboarding.py` (23 tests); PE/ELF/Mach-O detection; isolated local sync | `docs/installation.md`, `docs/getting-started/windows.md`, `macos.md`, `linux.md` | Windows 10/11, macOS, Linux | `verified` |
| **E02 Basic/Advanced UX** | `src/mutaui/ui/preferences.py`, `src/mutaui/ui/page_shell.py`, `app.py` | `tests/test_ui_preferences.py` (18 tests); `tests/test_mainwindow_flows.py` draft preservation; 20-case capture matrix | `docs/getting-started/basic-vs-advanced.md`, `docs/ui-visual-qa.md` | Windows, macOS, Linux (Qt 6.8.3) | `verified` |
| **E03 Global Mutagen YAML** | `src/mutaui/adapters/yaml_config.py`, `src/mutaui/adapters/yaml_config_editor.py` | `tests/test_yaml_config.py` (9 tests); `tests/test_yaml_config_editor.py` (21 tests); comment/order preservation, atomic writes | `docs/advanced/mutagen-global-config.md` | Windows, macOS, Linux (all filesystems) | `verified` |
| **E04 Native session config** | `sync_configuration.py`, `forward_configuration.py`, `app.py` | `tests/test_sync_configuration.py`, `tests/test_forward_configuration.py`, `tests/test_effective_configuration.py` (24 tests) | `docs/advanced/sync-configuration.md`, `docs/advanced/forward-configuration.md` | Mutagen >=0.18.0 | `verified` |
| **E05 Sync/Forward wizards** | `app.py` (`SessionDialog`, `ForwardDialog`) | `tests/test_mainwindow_flows.py`; command preview, ignore preset integration, public bind warning, R3 replica confirmation | `docs/user/sync-wizard.md`, `docs/user/forwarding.md` | Windows, macOS, Linux | `verified` |
| **E06 Connection Profiles & SSH** | `connection_profiles.py`, `ssh_profiles.py` | `tests/test_connection_profiles.py` (12 tests); `tests/test_ssh_profiles.py` (10 tests); `integration/ssh/test_host_key_acceptance.py` | `docs/ssh-profiles.md`, `docs/user/ssh.md` | OpenSSH client, Windows/macOS/Linux | `verified` |
| **E07 Native Mutagen Projects** | `src/mutaui/projects/native_project.py`, `project_actions.py`, `project_editor.py`, `src/mutaui/ui/project_viewer.py` | `tests/test_native_project.py`, `tests/test_native_project_dialog.py`, `tests/test_project_actions.py`, `tests/test_project_editor.py` (111 tests) | `docs/project-yaml-editing.md`, `docs/advanced/projects-and-hooks.md` | Mutagen 0.18.1 project orchestration | `verified` |
| **E08 Ignore Center** | `ignore_presets.py`, `src/mutaui/ui/ignore_rules.py` | `tests/test_ignore_presets.py`, `tests/test_ignore_rules_dialog.py` (18 tests); gitignore/dockerignore conversion, pattern order, negation | `docs/advanced/ignore-patterns.md` | Windows, macOS, Linux | `verified` |
| **E09 Session Doctor** | `src/mutaui/services/session_doctor.py` | `tests/test_session_doctor.py` (15 tests); deterministic root cause rules, deduplication, timestamped evidence | `docs/session-doctor.md`, `docs/user/session-doctor.md` | Mutagen >=0.18.0 | `verified` |
| **E10 Health & recovery** | `src/mutaui/services/health_tracker.py` | `tests/test_health_tracker.py` (35 tests; 100% branch coverage); monotonic clock, grace periods, circuit breaker, Auto-safe read-only | `docs/session-health.md`, `docs/advanced/recovery-policies.md` | Windows, macOS, Linux | `verified` |
| **E11 Conflict inspector/resolver** | `src/mutaui/services/conflict_inspector.py`, `conflict_resolver.py`, `conflict_recommendations.py`, `remote_inspector.py`, `diff_integration.py` | `tests/test_conflict_inspector.py`, `test_conflict_resolver.py`, `test_conflict_recommendations.py`, `test_remote_inspector.py`, `test_diff_integration.py` (145 tests) | `docs/conflict-inspector.md`, `docs/manual-conflict-resolution.md`, `docs/security/remote-inspection.md` | Windows, macOS, Linux | `verified` |
| **E12 Reconfiguration & replacement** | `src/mutaui/services/reconfiguration.py`, `replacement.py`, `replacement_command.py`, `action_planner.py` | `tests/test_reconfiguration.py`, `test_replacement.py`, `test_replacement_command.py`, `test_action_planner.py` (120 tests) | `docs/reconfiguration-preview.md`, `docs/controlled-replacement.md`, `docs/action-planner.md` | Mutagen 0.18.1 CLI | `verified` |
| **E13 Monitoring & history** | `monitoring.py`, `async_recorder.py`, `insights.py`, `performance.py` | `tests/test_monitoring.py`, `tests/test_async_recorder.py`, `tests/test_insights.py`, `tests/test_performance.py` (48 tests); WAL recovery, missing values | `docs/developer/performance.md`, `docs/user/dashboard.md` | SQLite 3, Windows, macOS, Linux | `verified` |
| **E14 OS & path integration** | `src/mutaui/services/path_lookup.py`, `linux_file_manager_integration.py`, `instance_lifecycle.py` | `tests/test_path_lookup.py` (9 tests); `tests/test_linux_file_manager_integration.py` (42 tests); `tests/test_instance_lifecycle.py` (19 tests) | `docs/single-instance-cli.md` | Windows Explorer, Linux Nautilus/Dolphin, macOS | `verified` |
| **E15 Initial sync seeding** | Native Mutagen CLI execution (`mutagen_client.py`) | `tests/test_mutagen_integration.py` (12 tests against live Mutagen 0.18.1 daemon) | `docs/getting-started/first-sync.md` | Mutagen 0.18.1 | `verified` |
| **E16 Tray & notifications** | `src/mutaui/services/instance_lifecycle.py`, `power_events.py`, `tray_status.py`, `quiet_hours.py`, `session_notification_gate.py` | `tests/test_quiet_hours.py`, `tests/test_power_events.py`, `tests/test_session_notification_gate.py` (48 tests); worst-state status, quiet hours | `docs/settings-reference.md`, `docs/single-instance-cli.md` | Windows broadcasts, Linux logind, macOS NSWorkspace | `verified` |
| **E17 Import/export & migration** | `portable_bundle.py`, `settings.py` | `tests/test_portable_bundle.py` (14 tests); `tests/test_v5_migration.py` (1 test); `tests/test_settings.py` (25 tests) | `docs/troubleshooting/backup-and-recovery.md` | Schema v1/v2/v5, cross-platform | `verified` |
| **E18 EN/CS localization** | `src/mutaui/ui/preferences.py`, `src/mutaui/ui/settings_registry.py` | `tests/test_ui_preferences.py`, `tests/test_ui_formatting.py`; catalog coverage checks across widgets, dialogs, forms, tooltips | `docs/settings-reference.md`, `docs/reference/configuration-fields.md` | Bilingual English / Czech | `verified` |
| **E19 Updates & distribution** | `src/mutaui/services/update_checker.py`, `.github/workflows/ci.yml`, `release.yml`, `packaging/` | `tests/test_update_checker.py` (15 tests); packaged self-test; packaged crash recovery test; onedir and onefile executables | `docs/developer/build-and-release.md`, `docs/installation.md` | Windows x64, macOS Apple Silicon/Intel, Linux x86_64 | `partial` (local packages verified; hosted CI secrets pending) |
| **E20 Support Bundle & diagnostics** | `insights.py::build_safe_report`, `export_safe_report`, `export_session_log_report`, `app.py::SupportBundleDialog` | `tests/test_insights.py` (14 tests); safe allowlist, machine-path redaction, preview before export | `docs/session-doctor.md`, `docs/troubleshooting/debugging.md` | Windows, macOS, Linux | `verified` |
| **E21 CLI & automation** | `src/mutaui/services/command_line.py`, `instance_lifecycle.py` | `tests/test_command_line.py` (9 tests); `tests/test_instance_lifecycle.py` (19 tests); single-instance routing for `--open-session`, `--open-folder`, `--open-project`, `--doctor`, `--demo` | `docs/single-instance-cli.md` | Windows, macOS, Linux | `verified` |
| **E22 Performance tuning** | `src/mutaui/services/performance_advisor.py`, `src/mutaui/ui/performance_tuning.py` | `tests/test_performance_advisor.py` (19 tests); `tests/test_performance_tuning_dialog.py` (6 tests); qualitative advice, fail-closed symlink/permission checks | `docs/advanced/performance-tuning.md` | Windows, macOS, Linux | `verified` |

## 2. Pull Request Stages (PR-001–PR-041)

| PR | Title & Summary | Source Modules | Verification Tests | Gate | Status |
|---|---|---|---|---|---|
| **PR-001** | Architecture, ADRs, and roadmap | `docs/roadmap.md`, `docs/adr/`, `docs/capability-matrix.md` | Documentation link and markdown checks | G0 | `verified` |
| **PR-002** | Metrics correctness and table height bounding | `insights.py`, `monitoring.py`, `app.py` | `tests/test_monitoring.py`, `tests/test_insights.py`, `tests/test_session_table_model.py` | G0 | `verified` |
| **PR-003** | pyproject.toml, Ruff, typing, and quality tools | `pyproject.toml`, `.github/workflows/ci.yml` | `ruff check .`, `mypy --strict src/mutaui`, `verify_source.py` | G0 | `verified` |
| **PR-004** | Typed domain snapshot and CLI executor | `src/mutaui/domain/models.py`, `adapters/cli_executor.py` | `tests/test_domain_models.py`, `tests/test_client.py` | G0 | `verified` |
| **PR-005** | Multiplatform CI matrix and packaged self-test | `.github/workflows/ci.yml`, `scripts/run_self_test.py` | `scripts/run_self_test.py` passed on onedir and onefile | G0 | `verified` |
| **PR-006** | Page shell refactoring and lazy routing | `src/mutaui/ui/page_shell.py`, `app.py` | `tests/test_mainwindow_flows.py` lazy page tests | G1 | `verified` |
| **PR-007** | Basic/Advanced mode, theming, EN/CS skeleton | `src/mutaui/ui/preferences.py` | `tests/test_ui_preferences.py`, `tests/test_mainwindow_flows.py` | G1 | `verified` |
| **PR-008** | Onboarding wizard and CLI architecture discovery | `src/mutaui/ui/onboarding.py` | `tests/test_onboarding.py` (23 tests) | G1 | `verified` |
| **PR-009** | Settings registry and docs generator | `src/mutaui/ui/settings_registry.py`, `scripts/generate_settings_reference.py` | `python scripts/generate_settings_reference.py --check` | G1 | `verified` |
| **PR-010** | Round-trip YAML parser and validator | `src/mutaui/adapters/yaml_config.py` | `tests/test_yaml_config.py` (9 tests) | G1 | `verified` |
| **PR-011** | Global Mutagen configuration editor | `src/mutaui/adapters/yaml_config_editor.py` | `tests/test_yaml_config_editor.py` (21 tests) | G1 | `verified` |
| **PR-012** | Sync configuration editor and proposals | `sync_configuration.py` | `tests/test_sync_configuration.py`, `tests/test_effective_configuration.py` | G1 | `verified` |
| **PR-013** | Forwarding configuration editor | `forward_configuration.py` | `tests/test_forward_configuration.py` | G1 | `verified` |
| **PR-014** | Sync/Forward creation wizards and preview | `app.py` (`SessionDialog`, `ForwardDialog`) | `tests/test_mainwindow_flows.py` wizard flow tests | G1 | `verified` |
| **PR-015** | Versioned Connection Profiles | `connection_profiles.py` | `tests/test_connection_profiles.py` (12 tests) | G2 | `verified` |
| **PR-016** | Read-only SSH Profile Manager | `ssh_profiles.py` | `tests/test_ssh_profiles.py` (10 tests) | G2 | `verified` |
| **PR-017** | Portable bundle import/export and migrations | `portable_bundle.py`, `settings.py` | `tests/test_portable_bundle.py`, `tests/test_v5_migration.py` | G2 | `verified` |
| **PR-018** | Ignore Preset Center | `ignore_presets.py`, `src/mutaui/ui/ignore_rules.py` | `tests/test_ignore_presets.py`, `tests/test_ignore_rules_dialog.py` | G2 | `verified` |
| **PR-019** | Native project importer and diff viewer | `src/mutaui/projects/native_project.py` | `tests/test_native_project.py` (45 tests) | G2 | `verified` |
| **PR-020** | Native project actions and hook consent | `src/mutaui/projects/project_actions.py`, `project_editor.py` | `tests/test_project_actions.py`, `tests/test_project_editor.py` (66 tests) | G2 | `verified` |
| **PR-021** | Pure Session Doctor engine | `src/mutaui/services/session_doctor.py` | `tests/test_session_doctor.py` (15 tests) | G2 | `verified` |
| **PR-022** | Health tracker and incident lifecycle | `src/mutaui/services/health_tracker.py` | `tests/test_health_tracker.py` (35 tests) | G2 | `verified` |
| **PR-023** | Auto-safe assisted recovery and circuit breaker | `src/mutaui/services/health_tracker.py` | `tests/test_health_tracker.py` (100% branch coverage) | G2 | `verified` |
| **PR-024** | Conflict Inspector read-only view | `src/mutaui/services/conflict_inspector.py`, `ui/conflict_inspector_dialog.py` | `tests/test_conflict_inspector.py`, `test_conflict_inspector_dialog.py` | G3 | `verified` |
| **PR-025** | ActionPlanner risk tiers and audit | `src/mutaui/services/action_planner.py` | `tests/test_action_planner.py` (21 tests) | G3 | `verified` |
| **PR-026** | Reconfiguration planner and snapshot validator | `src/mutaui/services/reconfiguration.py` | `tests/test_reconfiguration.py` (21 tests) | G3 | `verified` |
| **PR-027** | Controlled session replacement | `src/mutaui/services/replacement.py`, `replacement_command.py` | `tests/test_replacement.py`, `test_replacement_command.py` (78 tests) | G3 | `verified` |
| **PR-028** | Project-owned config edit flow | `src/mutaui/projects/project_editor.py`, `ui/project_yaml_editor_dialog.py` | `tests/test_project_editor.py`, `tests/test_native_project_dialog.py` | G3 | `verified` |
| **PR-029** | Opt-in read-only remote inspector | `src/mutaui/services/remote_inspector.py` | `tests/test_remote_inspector.py` (36 tests; 100% branch coverage) | G3 | `verified` |
| **PR-030** | Diff integration and artifact lifecycle | `src/mutaui/services/diff_integration.py` | `tests/test_diff_integration.py` (12 tests) | G3 | `verified` |
| **PR-031** | Manual per-file conflict resolver | `src/mutaui/services/conflict_resolver.py` | `tests/test_conflict_resolver.py` (35 tests; 100% branch coverage) | G3 | `verified` |
| **PR-032** | Scoped conflict recommendations | `src/mutaui/services/conflict_recommendations.py`, `ui/conflict_recommendations_dialog.py` | `tests/test_conflict_recommendations.py`, `test_conflict_recommendations_dialog.py` | G3 | `verified` |
| **PR-033** | Single instance, power events, tray fallback | `src/mutaui/services/instance_lifecycle.py`, `power_events.py`, `tray_status.py`, `quiet_hours.py` | `tests/test_instance_lifecycle.py`, `test_power_events.py`, `test_quiet_hours.py` | G4 | `verified` |
| **PR-034** | Path lookup, command palette, file manager hooks | `src/mutaui/services/path_lookup.py`, `linux_file_manager_integration.py` | `tests/test_path_lookup.py`, `tests/test_linux_file_manager_integration.py` | G4 | `verified` |
| **PR-035** | Lazy dashboard, model/view cache, missing metrics | `monitoring.py`, `async_recorder.py`, `insights.py`, `performance.py` | `tests/test_monitoring.py`, `tests/test_async_recorder.py`, `tests/test_session_table_model.py` | G4 | `verified` |
| **PR-036** | Comprehensive settings help and EN/CS translations | `src/mutaui/ui/settings_registry.py`, `src/mutaui/ui/preferences.py` | `tests/test_ui_preferences.py`, `tests/test_ui_formatting.py` | G4 | `verified` |
| **PR-037** | Performance benchmarks against reference budgets | `benchmarks/session_table_benchmark.py` | 10–5,000 row benchmark executed; P95 recorded | G4 | `verified` |
| **PR-038** | Multiplatform packaging and release workflows | `.github/workflows/ci.yml`, `release.yml`, `packaging/` | PyInstaller builds executed locally; GitHub workflows linted and validated | G4 | `partial` (local packages verified; hosted CI secrets pending) |
| **PR-039** | Documentation site, actual screenshots, changelog | `mkdocs.yml`, `docs/`, `README.md`, `CHANGELOG.md` | Strict MkDocs build; pymarkdown scan; 12 real UI screenshots | G4 | `verified` |
| **PR-040** | End-to-end acceptance traceability | `docs/acceptance-traceability.md`, `docs/implementation-inventory.md` | Audit matrix complete and verified against 1,385 test results | G4 | `verified` |
| **PR-041** | Packaged self-test and crash recovery verification | `scripts/run_self_test.py`, `scripts/run_crash_recovery_self_test.py` | Both onedir and onefile executables pass self-test and crash recovery | G4 | `verified` |

## 3. Gates Summary

- **G0 (Baseline & Foundations):** Verified. Python 3.12 locked, 100% critical branch coverage, 95.06% aggregate branch coverage (3,346 / 3,520).
- **G1 (UX & Configuration):** Verified. Basic/Advanced modes, lossless round-trip YAML, read-only session configuration, wizards with exact command preview.
- **G2 (Profiles, Projects, Doctor):** Verified. Versioned profiles, read-only SSH config reader, native project lifecycle, deterministic Doctor, Auto-safe read-only gate.
- **G3 (Conflicts & Reconfiguration):** Verified. Read-only conflict inspector, ActionPlanner risk tiers, controlled replacement, remote inspection with path containment, manual conflict resolver with full rollback.
- **G4 (Production Quality):** Verified locally. 1,385 tests passing with zero skips, clean security/dependency audits, rebuilt executables verified, complete bilingual documentation. Hosted CI trigger and code signing secrets remain external release prerequisites.
