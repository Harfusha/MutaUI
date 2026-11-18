# Release candidate audit — 2026-11-15 (Follow-up 592cf7d)

> **Historical snapshot — superseded for current release status.** This decision applies only to commit `592cf7d` and its 2026-11-15 evidence. It is not the current candidate decision. Use [the 2026-11-17 remaining-work handoff](../audits/F3_REMAINING_WORK_2026-11-17.md) and active Hub plan `plan_3633c4195d5e`. Keep this report as historical evidence.

**Decision: LOCAL EVIDENCE ONLY. HOSTED G0–G4 QUALITY GATES FAIL; RELEASE BLOCKED.**

This report documents local verification evidence and gate disposition following the completion of audit follow-up plan `MutaUI_AUDIT_FOLLOWUP_2026-11-14_592cf7d.md`.

## Candidate identity

- **Repository:** `Harfusha/MutaUI` (GitHub checkout), branch `master`.
- **Audited Commit:** `592cf7d5fbd3f015ef5354b9e8300da020d58b22` with follow-up changes.
- **Environment:** Windows 11 x64, Python 3.12.10, pytest 9.2.0, Coverage.py 7.1.0, PySide6 6.8.3, Mutagen CLI 0.18.1.

## Verified local evidence

1. **Full test suite (Python 3.12.10):**
   - **1,410 passed, 0 skipped, 0 failed in 98.17 s (exit code 0)**.
   - Aggregate branch coverage: **95.01%** (3,352 covered / 3,528 valid branches), exceeding the mandatory 95.0% threshold.
   - Statement coverage: **96.16%** (11,952 statements, 11,533 executed).
   - Strict JUnit validation: passed (valid XML, consistent testcase counts, 0 failures, 0 skips).

2. **Static and documentation checks:**
   - `ruff check .`: clean across all files (exit code 0).
   - `ruff format --check .`: 258 files checked and formatted (exit code 0).
   - `mypy --strict src/mutaui`: 55 source files checked, clean (exit code 0).
   - `scripts/generate_settings_reference.py --check`: current (exit code 0).
   - `pymarkdown scan README.md docs`: clean (exit code 0).
   - `mkdocs build --strict`: documentation site builds cleanly (exit code 0).
   - `verify_source.py`: clean (37 Python modules, 12 files, and static Qt layout checks, exit code 0).

3. **Follow-up audit gates (G0–G4):**
   - **G0 (F2-001–F2-006):** Actionlint pin & SHA-256 (`8aca8db9...`), macOS notarytool variable fix (`$notary_file`), CI runner and JUnit integrity hardening, isolated Mutagen daemon harness (`IsolatedMutagenDaemon`), and platform conditional regressions resolved.
   - **G1 (F2-007–F2-012):** Linux AppImage supply chain verification (`packaging/linux/supply-chain.json` with pinned appimagetool SHA-256 `ed4ce84f...`), honest previous-release upgrade validation in CI, and third-party notices documented in `NOTICE.md`.
   - **G2 (F2-013–F2-018):** Graph hover `None` sample crash resolved with Qt regression tests, atomic YAML writes with Win32 `ReplaceFileW` and POSIX directory fsync, conservative replacement and ActionPlanner leases, and remote SSH/SFTP fault matrix verified.
   - **G3 (F2-019–F2-028):** Monolithic `app.py` modularization into `src/mutaui/ui/localization.py`, `src/mutaui/ui/widgets/graph.py`, `src/mutaui/ui/widgets/health_ring.py`, and `src/mutaui/ui/widgets/session_table.py`; presentation caching in `SessionRowPresentation` with $O(1)$ ID index (1,000-row view update P95: 30.0 ms).
   - **G4 (F2-029–F2-032):** Truthful acceptance traceability in `docs/acceptance-traceability.md` with explicit evidence IDs for all F2-AC-001 through F2-AC-038 criteria.

## Gate disposition

| Gate | Status | Local evidence | Remaining external prerequisites |
|---|---|---|---|
| **G0 — Baseline & CI foundations** | Verified locally | Python 3.12, 1,410 tests passing (0 skip, 0 fail), isolated daemon harness. | Hosted GitHub Actions runner receipt for Windows, macOS, and Linux. |
| **G1 — UX & Configuration** | Verified locally | Basic/Advanced shell, lossless YAML, honest upgrade CI check, supply-chain pin. | Production code signing certificates (Windows Authenticode, Apple Developer ID). |
| **G2 — Profiles, Projects, Doctor** | Verified locally | Read-only SSH manager, native projects, atomic YAML replacement, remote fault matrix. | Hosted Linux CI OpenSSH server acceptance. |
| **G3 — Conflicts & Reconfiguration** | Verified locally | Graph None crash fix, session table caching, extracted widgets, ActionPlanner leases. | Remote SFTP multi-endpoint latency trials. |
| **G4 — Production Quality** | Verified locally | 95.01% branch coverage, 96.16% total coverage, strict static checks, complete traceability. | Hosted tag release pipeline trigger with credentials; owner license decision. |

## Host CI result as of 2026-11-15

[Run #43710608113](https://github.com/Harfusha/MutaUI/actions/runs/43710608113): Windows 1 fail; Linux 1 fail/1 skip; macOS ARM and Intel 13 fail/1 skip each; security 14 high-entropy matches. This supersedes any earlier local claim of production readiness. A clean final-commit hosted CI run, signing certificates, real package smoke and owner license selection are still mandatory. No release is authorized by this local report.
