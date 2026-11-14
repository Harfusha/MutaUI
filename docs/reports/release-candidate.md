# Release candidate audit — 2026-11-14

**Decision: CANDIDATE VERIFIED LOCALLY. NOT RELEASED TO PRODUCTION PENDING EXTERNAL HOSTED SECRETS AND SIGNING.**

This report records all local verification evidence, rebuilt distribution artifacts, and remaining external gates. It does not authorize public distribution without explicit user credentials and license selection.

## Candidate identity

- Repository: `C:\Ostatní\MutagenApp`, branch `master`.
- Base commit: `9b5718a5f4dec6fe8f3a93d3f5f2426941e56c25` (v8.2).
- Local environment: Windows 11 x64, Python 3.12.10, pytest 9.2.0, Coverage.py 7.17.3, PySide6 6.8.3, Paramiko 5.1.0, Ruff 0.17.5, and checksum-verified Mutagen CLI 0.18.1 in isolated data directories.

## Verified local evidence

1. **Full test suite (Python 3.12.10):**
   - **1,372 passed, 0 skipped, 0 failed in 102.85 s (exit code 0)**.
   - Aggregate branch coverage: **3,520 branches, 95.93% coverage** (exceeds the 95.0% gate).
   - Line coverage: **11,849 statements, 96.25% coverage**.
   - Pure domain, services, and adapters maintain **100% branch coverage** across 39 modules.
2. **Static and security checks:**
   - `ruff check .`: 235 files checked, clean (exit code 0).
   - `ruff format --check .`: 235 files formatted (exit code 0).
   - `mypy --strict src/mutaui`: 46 source files checked, clean (exit code 0).
   - `python scripts/generate_settings_reference.py --check`: current (exit code 0).
   - `python -m pymarkdown -d MD013,MD029 scan README.md docs`: clean (exit code 0).
   - `python -m mkdocs build --strict`: documentation site builds cleanly (exit code 0).
   - `python verify_source.py`: clean (exit code 0).
   - `python scripts/check_dependency_exports.py`: pinned exports match `pyproject.toml` and `uv.lock`.
   - `pip-audit`: no known vulnerabilities across locked dependencies (exit code 0).
   - `yamllint -s .github/workflows .yamllint`: zero errors (exit code 0).
   - `detect-secrets-hook`: clean baseline, exit code 0.
   - Local AI Hub security audit: 156 files scanned, zero findings, `is_clean=true`, `triage_complete=true`.
   - `git diff --check`: clean, zero whitespace/binary corruption errors (exit code 0).
3. **Live Mutagen CLI integration:**
   - 12 integration tests in `tests/test_mutagen_integration.py` pass against official Mutagen 0.18.1 daemon in an isolated `MUTAGEN_DATA_DIRECTORY`.
   - Covers local two-way sync, sync replacement, restore on failed create, ignore pattern negation, global defaults inheritance, forwarding socket defaults, and native project lifecycle (`start` and `terminate`).
4. **Packaged Windows distribution artifacts:**
   - Rebuilt onedir package `dist-fast/MutagenControl/MutagenControl.exe` under Python 3.12.10 with PyInstaller 6.22.3.
     - `scripts/run_self_test.py`: PASS
     - `scripts/run_crash_recovery_self_test.py`: PASS (verifies settings rollback and WAL database integrity).
     - Checksums: `dist-fast/MutagenControl/SHA256SUMS.txt`.
   - Rebuilt single-file executable `dist/MutagenControl.exe` under Python 3.12.10 with PyInstaller 6.22.3.
     - `scripts/run_self_test.py`: PASS
     - `scripts/run_crash_recovery_self_test.py`: PASS.
     - Checksums: `dist/SHA256SUMS.txt` (`08c24dc85efb11f68e8b37a67bf860db2ef143a96ecd2c445693f4b53cb75cf9`).
5. **Performance benchmarks:**
   - Local Windows 11 machine (AMD64 8C/16T, 32GB RAM):
     - 1,000-row model update P95: 71.754 ms (budget: 150 ms).
     - Offscreen Qt view filter/render P95: 30.612 ms.
     - Packaged onedir startup P95: 1,035 ms (budget: 3 s).
     - Packaged onefile startup P95: 2,188.671 ms (budget: 6 s).

## Gate disposition

| Gate | Status | Verified local proof | Remaining external evidence |
|---|---|---|---|
| **G0 — Baseline and CI foundations** | Verified locally | Python 3.12 locked environment, ADRs 0001–0005, roadmap, capability matrix, unit and integration baselines, packaged smoke. | Hosted GitHub Actions runner receipt for Windows, macOS, and Linux. Reference-hardware SSD audit. |
| **G1 — UX and configuration** | Verified locally | Basic/Advanced shell, theming, settings registry, lossless YAML round-trip with comment preservation, global config editor, sync and forward configuration editors, exact command preview wizards. | Interactive accessibility testing with external assistive tools; multi-user usability trials. |
| **G2 — Profiles, projects, Doctor** | Verified locally | Versioned connection profiles, read-only SSH manager (`ssh -G`), safe import/export with redaction, ignore preset center, native project lifecycle and hook consent, deterministic Session Doctor rules, health tracker and Auto-safe circuit breaker. | Hosted Linux CI OpenSSH server acceptance; live remote SSH network flapping. |
| **G3 — Conflicts and reconfiguration** | Verified locally | Read-only Conflict Inspector, ActionPlanner R0–R3 risk tiers, exact target locking, reconfiguration planner, controlled replacement, read-only remote inspection, temporary diff integration, manual per-file resolver with backup/restore rollback. | Remote SFTP multi-endpoint latency trials; destructive live tests remain disabled by default. |
| **G4 — Production quality** | Ready for release | 1,372 tests passing with zero skips, 95.93% branch coverage, clean security/dependency/secret audits, rebuilt onedir and onefile binaries passing self-test and crash recovery, 12 actual UI screenshots, complete documentation site. | Hosted tag release pipeline trigger; Apple Developer ID notarization and Windows authenticode signing secrets; final product license selection by owner. |

## Outstanding external gates

- **Hosted CI execution:** GitHub Actions workflows (`.github/workflows/ci.yml` and `release.yml`) are configured with strict multiplatform matrices and checksum validation, but require pushing to a remote repository with hosted runners.
- **Signing and notarization:** Code signing certificates (Windows EV/OV authenticode and Apple Developer ID) and notarization credentials must be provided as GitHub Actions repository secrets (`WINDOWS_SIGNING_CERT`, `APPLE_CERTIFICATE`, `APPLE_NOTARIZATION_API_KEY`).
- **Product license:** A formal software license grant has not been designated by the project owner. The repository preserves existing copyright and attribution without assuming third-party distribution terms.
