# Phase 4 progress — platform, performance, and release quality

Date: 2026-11-14. Baseline: repository `master`, commit `9b5718a5f4dec6fe8f3a93d3f5f2426941e56c25` (v8.2). Environment: Python 3.12.10, PySide6 6.8.3, pytest 9.2.0, Coverage.py 7.17.3, checksum-verified Mutagen CLI 0.18.1.

## Scope delivered

- **PR-033 (Single-instance lifecycle, notifications, tray fallback):** Implemented in `src/mutaui/services/instance_lifecycle.py`, `src/mutaui/services/power_events.py`, `src/mutaui/services/tray_status.py`, `src/mutaui/services/quiet_hours.py`, and `src/mutaui/services/session_notification_gate.py`. Single-instance broker uses local named pipes/sockets with JSON framing to forward commands (`--open-session`, `--open-folder`, `--open-project`, `--doctor`, `--demo`). Notifications feature quiet hours (start/end HH:MM), 10s error debounce, 60s per-session throttle, incident grouping, and worst-state tray icon/tooltip. Power monitors subscribe to Windows broadcasts, Linux logind `PrepareForSleep`, and macOS NSWorkspace sleep/wake events.
- **PR-034 (Path integration and command palette):** Implemented in `src/mutaui/services/path_lookup.py`, `src/mutaui/services/linux_file_manager_integration.py`, and Windows Explorer Send To integration. Case-insensitive path containment, directory symlink resolution, and exact-ID session mapping. Linux file manager integration supports per-user Nautilus scripts and Dolphin service menus with ownership-checked manifest rollback.
- **PR-035 (Lazy dashboards, model/view performance, missing-value correctness):** Implemented in `monitoring.py`, `async_recorder.py`, `insights.py`, and `performance.py`. `SessionTableModel` virtualizes high session counts. SQLite history uses WAL and bounded queries. Missing metric samples remain `None` and are labeled "Not measured", never fabricated as zero.
- **PR-036 (Localization and accessibility):** Full bilingual EN/CS catalog in `src/mutaui/ui/preferences.py` and `src/mutaui/ui/settings_registry.py`. Localizes labels, buttons, tooltips, placeholders, dialog titles, table headers, statuses, and session plurals without string concatenation. Tables provide accessible names, keyboard navigation, and visible focus rings. Capture matrix validates 100%, 125%, 150%, 200%, and 320% scaling without text clipping.
- **PR-037 (Packaged performance benchmarks):** Implemented in `benchmarks/session_table_benchmark.py`. Measures 0, 1, 10, 100, 500, 1,000, and 5,000 rows. On Windows 11 (AMD64 8C/16T, 32GB RAM), 1,000-row model update P95 is 71.754 ms; offscreen Qt view filter/render P95 is 30.612 ms. Packaged startup: onedir P95 is 1,035 ms (budget: 3 s); onefile P95 is 2,188.671 ms (budget: 6 s).
- **PR-038 (Multiplatform packaging and release workflows):** Unified `.github/workflows/ci.yml` and `.github/workflows/release.yml` for Windows (installer and portable), macOS (Intel and Apple Silicon DMG), and Linux (AppImage and deb). Enforces checksum-verified Mutagen CLI 0.18.1 download, zero-skip policy, 95% branch coverage gate, CycloneDX SBOM generation, and artifact provenance.
- **PR-039 (Documentation site and actual UI screenshots):** MkDocs Material site built in strict mode. Includes 12 actual UI screenshots in `docs/assets/images/actual-ui/` captured from the running application (both themes, both modes, 100–320% DPI). Complete user guides, settings reference, architecture, threat model, and troubleshooting guides.
- **PR-040 (Acceptance traceability and audit matrix):** Maintained in `docs/acceptance-traceability.md` and `docs/implementation-inventory.md`. Maps every requirement across E01–E22, AC-001–AC-040, and PR-001–PR-041 to concrete source paths, tests, documentation, and platform status.
- **PR-041 (Packaged self-test and crash recovery):** Rebuilt both onedir (`dist-fast/MutagenControl/MutagenControl.exe`) and onefile (`dist/MutagenControl.exe`) with Python 3.12.10 and PyInstaller 6.22.3. Both packages pass `scripts/run_self_test.py` and `scripts/run_crash_recovery_self_test.py` (verifying settings rollback and WAL database integrity after an simulated crash).
- **E22 (Performance Tuning Assistant):** Implemented in `src/mutaui/services/performance_advisor.py` and `src/mutaui/ui/performance_tuning.py`. Qualitative advisor grounds recommendations in official Mutagen documentation. Reports unknown entry counts instead of guessing; warns on high-frequency forced polling, large roots, cross-device staging, and local permission issues. Suggestions remain optional proposals and never mutate live sessions.

## Verification evidence

- **Full test suite (Python 3.12.10):** **1,372 passed, 0 skipped, 0 failed** in 102.85 s (exit code 0).
- **Aggregate branch coverage:** **95.93%** (3,520 branches, 132 missed/partial), meeting the plan's 95% gate.
- **Pure domain, services, and adapters coverage:** **100% branch coverage** across critical components.
- **Static checks:**
  - `ruff check .`: 235 files checked, zero issues.
  - `ruff format --check .`: 235 files formatted.
  - `mypy --strict src/mutaui`: 46 source files checked, zero issues.
  - `python scripts/generate_settings_reference.py --check`: current.
  - `python -m pymarkdown -d MD013,MD029 scan README.md docs`: zero violations.
  - `python -m mkdocs build --strict`: clean build.
  - `python verify_source.py`: OK (37 Python modules, 12 files, Qt layout checks).
  - `python scripts/check_dependency_exports.py`: matches `pyproject.toml` and `uv.lock`.
  - `python -m pip_audit`: zero known vulnerabilities.
  - `python -m yamllint -s .github/workflows .yamllint`: zero errors.
  - `detect-secrets-hook`: clean, exit 0.
  - Local AI Hub security audit: 156 files scanned, zero findings.
  - `git diff --check`: zero whitespace/corruption errors.
- **Live Mutagen integration:** 12 tests passed against official Mutagen 0.18.1 daemon in isolated data directories.
- **Packaged self-tests:**
  - `scripts/run_self_test.py dist-fast/MutagenControl/MutagenControl.exe`: PASS
  - `scripts/run_self_test.py dist/MutagenControl.exe`: PASS
  - `scripts/run_crash_recovery_self_test.py --executable dist-fast/MutagenControl/MutagenControl.exe`: PASS
  - `scripts/run_crash_recovery_self_test.py --executable dist/MutagenControl.exe`: PASS
- **Checksums:** Generated in `dist/SHA256SUMS.txt` and `dist-fast/MutagenControl/SHA256SUMS.txt`.

## Gate G4 disposition

- Status: **Verified locally on Windows x64; external hosted CI run, macOS notarization, and Linux distribution packaging remain open for remote execution.**
- All 40 acceptance criteria (AC-001–AC-040) mapped to concrete implementations and local proof in `docs/acceptance-traceability.md`.
- No required tests skipped in the verified local suite.
- Rebuilt packages verified for both startup self-test and crash recovery.
