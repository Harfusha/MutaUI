# MutaUI — F3 agent continuation and acceptance contract

**Date:** 2026-11-15  
**Repository:** https://github.com/Harfusha/MutaUI  
**Working branch:** `audit/f3-hardening-2026-11-15`  
**Review:** https://github.com/Harfusha/MutaUI/pull/1 (draft)  
**Baseline audit:** `101796a28971a40fbc5cb45e154abb5016e6d192`  
**Canonical specification:** `docs/audits/F3_AGENT_REMAINING.md`

## Critical instructions

This is a continuation of the 2026-11-15 F3 audit, **not a claim that the audit is finished**. Before working, fetch the latest branch head, compare against `master`, and inspect GitHub Actions for the exact head SHA. Do not repeat the fixes listed as implemented below unless a failing check demonstrates a regression.

MutaUI is a control GUI for the **native Mutagen CLI**. Preserve exact session IDs, native lossless settings, fail-closed SSH host keys, per-action consent, no unintended daemon autostart, never execute `--all` for an individual session, and keep `MANUAL_RESOLUTION_ENABLED=False` until destructive conflict-resolution acceptance is independently proven. No production release from a failed matrix.

## Implemented in PR #1 — must still be verified

| Area | Changes in the PR | Required verification |
| --- | --- | --- |
| F3-001 security | Individually classified non-secret hashes; normalized POSIX baseline paths and shifted line numbers; synthetic high-entropy negative probe uses a temporary baseline | Security job PASS with `detect-secrets-hook` unchanged and no new undisclosed fingerprints |
| F3-002/F3-003 daemon | Per-client immutable copy of subprocess environment; short isolated data directories; deterministic lifecycle probes and no global HOME changes | Real Mutagen CLI 0.18.1 start/list/stop loops on Windows, Linux, macOS Intel and ARM |
| F3-002 diagnostics | Failure artifacts contain non-identifying categories, never raw native logs or private paths | Redaction regression tests and failure-path CI artifacts |
| F3-004 socket test | Test socket path shortened; native `leave` and consented `overwrite` assertions retained | Windows native AF_UNIX overwrite behavior and no unintended removal |
| F3-005 format | Ruff-isort and Ruff-format corrections made after initial failing jobs | `ruff check .`, `ruff format --check .` on final SHA |
| F3-006 skips | POSIX tests assert Windows path semantics instead of skipping Windows-only assertions | JUnit zero skipped on four OS platforms |
| F3-007 supply chain | Bounded actionlint download, SHA-256 before extracting, regular tar member only; AppImage digest, version and URL from one validated manifest | Negative archive symlink, mutated digest/URL and positive native packages |
| F3-019 UI refresh | `SessionTableModel` updates only changed rows when identifiers and ordering remain stable; retains persistent view index | Qt selection, sorted rows, scroll position; 1k/5k benchmark |
| F3-024 privacy | Redacted Windows local build and checkout paths in committed benchmark and reports | Public file scan and generated diagnostics |
| QA evidence | JUnit nested suite counts are not double counted; impossible test/coverage counters rejected; generated report cannot claim signed release | Unit tests and current SHA-hosted CI evidence |
| CI permissions | Routine PR CI `contents: read`, no release attestation privileges | Workflow audit; release-only signing privileges |

**Status rule:** "Implemented" means code exists in the review branch; it does not imply hosted CI, visual QA, or release verification.

## Blocker P0 — finish before merging

1. Open current PR check suite and identify the **latest** head SHA, not a superseded queued run.
2. Get all five jobs green: Windows, Ubuntu, macOS Intel, macOS Apple Silicon, and security. If any job fails, read that job's actual log and apply the smallest justified fix. Do not dismiss failures with `xfail`, `skip`, `continue-on-error`, or lowered coverage.
3. For macOS daemon failures: inspect short path, Mutagen environment, exit status, socket readiness, stale locks, stop acknowledgement and redacted diagnostics. Test 10 repeated cycles. Do not solve a genuine failure by just increasing timeouts.
4. For Windows socket overwrite: verify exact native `lastError`, endpoint capability and listener readiness. Assert `leave` preserves existing content and `overwrite` only affects the explicitly consented path. Keep safe failure on unsupported native behavior.
5. For security: compare the hashed `.secrets.baseline` on disk with `mutaui-secret-baseline-review` artifact if scanner requests a rewrite. Approve only verified public revision/checksum false positives. Keep the negative fake-token probe; never blanket-ignore a detector.
6. For JUnit/coverage: validate no failures, errors, mandatory skips, missing branch information, or inaccurate source inventories. Preserve the fail-fast runner and make reports reference the tested SHA.

**Acceptance:** all five jobs green on exactly one SHA; full JUnit tests 0 fail/0 skip; branch coverage at least 95% over the declared inventory; no orphan test daemons; reproducible CLI setup. A successful earlier or local dirty-tree report is not evidence.

## Remaining F3 tasks (implement after P0)

| ID | Priority | Required implementation and tests |
| --- | --- | --- |
| F3-008 | P1 | Real Windows upgrade from a **released old installer**; current v8.2.0 may lack one. Log `UNVERIFIED`, never simulate a genuine historical upgrade using an installer built from the same source |
| F3-009 | P1 | macOS signed app + DMG notarization and Gatekeeper launch, Intel and ARM; test on real runner with owner-supplied certificates |
| F3-010 | P1 | Clean Linux AppImage/deb GUI install, run, uninstall, retained user files, file-manager integration; include supported Ubuntu and target Fedora |
| F3-011 | P1 | Windows Authenticode installer, verified signature, fresh install and upgrade profile retention with owner-supplied certificate |
| F3-012 | P1 | Release tag/version checks, checksums, SBOM, provenance, signatures, post-install smoke and all required matrix checks as mandatory publish gates |
| F3-013 | P1 | Audit production module inventory. Incrementally extend strict mypy and coverage beyond `src/mutaui` to root modules without hiding error classes |
| F3-014 | P1 | Split sync/forward creation dialogs and session settings controllers out of the remaining large `app.py` into testable typed UI/services |
| F3-015 | P1 | Split YAML/global preferences, native projects, profiles and SSH controllers from GUI while retaining lossless precedence and read-only SSH inspections |
| F3-016 | P1 | Split monitoring, health, alerts, doctor, tray and background status into focused controllers; verify no cross-thread QObject mutations |
| F3-017 | P1 | Fault-inject action planner/replacement/backup/YAML/conflict paths: stale IDs, fsync/rename errors, disk full, cancelled prompts, daemon crash, SSH flap, rollback failure. Preserve fail-closed behavior |
| F3-018 | P1 | Native SSH acceptance with isolated host-key fixtures, rotation rejection, IPv6, Unicode, symlinks, latency and native project hook consent |
| F3-019 | P1 | Extend Qt table incremental mutation to inserts/removes/reorders where justified and add measured p95 render/scroll/selection performance at 1k and 5k rows |
| F3-020 | P2 | Beginner Basic wizard: initial setup, safe local sync, understandable defaults/errors, help text, no accidental destructive action |
| F3-021 | P2 | Critical-path Czech/English translation audit, dynamic message interpolation, live language switching and correct keyboard mnemonics |
| F3-022 | P2 | Real visual/a11y QA on each OS across DPI 100/125/150/200, themes, language modes, screen readers and keyboard-only navigation |
| F3-023 | P2 | Clean reproducible CPU/RSS, startup p50/p95/p99, CLI spawn-count, tray idle and 8-hour soak measurements, explicitly separated from the Mutagen daemon |
| F3-024 | P2 | Platform-specific documentation, clean-install screenshots, privacy inventory, redacted support bundle and honest capability matrix |
| F3-025 | Owner | Decide and authorize the MutaUI project license and redistributable dependency compliance, especially Qt LGPL; do not invent a license |
| F3-026 | P1 | Final single-SHA signed release acceptance with current security evidence, all platform test matrices, installer acceptance and maintained version/tag |

## Release prerequisites that an agent cannot legitimately invent

The owner must decide the license; provide Apple Developer ID, notary API credentials, Windows code-signing certificate through approved GitHub Actions secrets; and accept target platform GUI/a11y behavior. No credentials belong in commits, support bundles or logs.

## Commands and verification

```bash
git fetch origin
git switch audit/f3-hardening-2026-11-15
git pull --ff-only
uv sync --locked --group build --group test --group quality
python scripts/ci/run_static_checks.py
python scripts/ci/run_tests.py
python scripts/ci/verify_secret_detection.py
python -m pytest -q tests/test_ci_runner.py tests/test_generate_acceptance_report.py
```

Run on Python 3.12 and inspect the **hosted** workflow run for the exact resulting commit. Local tests are supplemental, never a substitute for clean Windows/macOS/Linux acceptance. Do not merge the draft PR or tag a release until all mandatory gates pass.

## Next action for the agent

Continue on PR #1; verify the latest Actions logs first, fix confirmed P0 regressions without masking checks, then proceed through F3-008 to F3-026. Update this file with new SHA, evidence URL, actual pass/fail state and any owner blockers; never mark a task done solely because source code or a synthetic test exists.
