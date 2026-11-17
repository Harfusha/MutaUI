# MutaUI — F3 agent continuation and acceptance contract

- **Audit started:** 2026-11-15
- **Repository:** [Harfusha/MutaUI](https://github.com/Harfusha/MutaUI)
- **Current working branch:** `master` (the PR branch is already integrated)
- **Review:** [PR #1](https://github.com/Harfusha/MutaUI/pull/1) (merged and closed as `de5b9b1`)
- **Baseline audit:** `101796a28971a40fbc5cb45e154abb5016e6d192`
- **Canonical specification:** `docs/audits/F3_AGENT_REMAINING.md`

## Current continuation checkpoint — 2026-11-17

- At checkpoint start on 2026-11-17, `origin/master` was `ae4b1b3b41965e3a4e0a28092de00126ff497add`. Run #87 passed all five jobs on that SHA. Follow-up commit `4648a2e80f9fb4dab18b08bc960b7b185bf816e7` updated the Node 24 action refs; Checks run #88 passed all five jobs on that exact commit with no Node.js 20 deprecation warnings. Documentation commit `6ce5324f436dd045fdecb2e2df55332a717df004` refreshed this checkpoint; run #89 passed all five jobs on that exact SHA. Commit `7965d752f38cf752c0d0615e56a9f4bcfe7e059f` added the owner-selected MIT license, third-party LGPL notices, and a release gate that blocks while LGPL review is pending; run #90 passed all five jobs on that exact SHA. Checkpoint commit `664cdbd8f36eeaaf9977c9237f71ec537b9270d5` passed all five jobs in run #91.
- Hosted [Checks run #81](https://github.com/Harfusha/MutaUI/actions/runs/43974893399) completed successfully on exactly `eda6078`: Ubuntu, Windows, macOS ARM, macOS Intel and dependency/workflow/YAML/secret checks all passed.
- Hosted [Checks run #82](https://github.com/Harfusha/MutaUI/actions/runs/43978069349) completed successfully on exactly `ecbeef5`: Ubuntu, Windows, macOS ARM, macOS Intel and dependency/workflow/YAML/secret checks all passed.
- Hosted [Checks run #83](https://github.com/Harfusha/MutaUI/actions/runs/43979743248) completed successfully on exactly `3e29dcf` across all four OS jobs and security checks; the new Linux OpenSSH disconnect/reconnect integration test passed.
- Hosted [Checks run #84](https://github.com/Harfusha/MutaUI/actions/runs/43981197608) completed successfully on exactly `40585436b527b583a437d252f40d9b0ffb720326`; Windows, Ubuntu, macOS ARM, macOS Intel and dependency/workflow/YAML/secret jobs all passed.
- Hosted [Checks run #85](https://github.com/Harfusha/MutaUI/actions/runs/43986151501) completed successfully on exactly `ca5137b706f24dcbbecbe85f5305f9b8751900f4`; all five jobs passed.
- Hosted [Checks run #86](https://github.com/Harfusha/MutaUI/actions/runs/44016838155) completed successfully on exactly `72cf4782d09020ed669ed76a2ac7bfa807a25a2a` on attempt 2; all five jobs passed. Attempt 1 failed only the macOS Intel disk-image step with `hdiutil: create failed - Resource busy`; rerunning that job succeeded without source changes, so this is recorded as a transient runner failure, not a product-code fix.
- Historical local verification on the then-dirty candidate based at `72cf4782d09020ed669ed76a2ac7bfa807a25a2a`: `uv run python scripts/ci/run_tests.py` passed 1,615 tests with 0 failures/skips, 95.32% branch coverage, and 96.65% total coverage. Static checks and the synthetic-secret rejection also passed then. Its `working_tree_dirty: true` manifest is historical local evidence; run #87 above covers the committed candidate.
- Isolated-daemon tests cover graceful stop/restart and abrupt process-crash recovery; the new crash-recovery case passes locally. The existing 10-cycle lifecycle test passed in #83 on all hosted OSes. IPv6/Unicode SSH parsing, remote symlink escape, Linux OpenSSH and disconnect/reconnect acceptance passed in #83. Windows host has no `sshd`; this integration case runs on Ubuntu CI.
- **Still open:** signed Windows upgrade/install, macOS notarization/Gatekeeper, Linux target-distribution GUI, physical DPI/accessibility, live network fault/latency matrix, tray-idle and CLI-spawn measurements, reference-hardware metrics, 8-hour soak, Qt LGPL legal review and signing-secret verification, and final release/tag acceptance.

The older continuation entries below are historical snapshots and their reported dirty roots, commits, counts and CI runs do not describe the current checkout.

## Critical instructions

This is a continuation of the 2026-11-15 F3 audit, **not a claim that the audit is finished**. Before working, fetch the latest branch head, compare against `master`, and inspect GitHub Actions for the exact head SHA. Do not repeat the fixes listed as implemented below unless a failing check demonstrates a regression.

MutaUI is a control GUI for the **native Mutagen CLI**. Preserve exact session IDs, native lossless settings, fail-closed SSH host keys, per-action consent, no unintended daemon autostart, never execute `--all` for an individual session, and keep `MANUAL_RESOLUTION_ENABLED=False` until destructive conflict-resolution acceptance is independently proven. No production release from a failed matrix.

## F3 implementation and baseline verification criteria

The table preserves the original handoff checklist; current hosted results are in the continuation checkpoint above.

| Area | Changes in the PR | Baseline verification criteria |
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

**Status rule:** "Implemented" means code exists in the review branch. The baseline table is not a current pass/fail report; use the continuation checkpoint above for hosted CI and owner-controlled gates.

## Further remediation applied after the initial F3 handoff

The following changes are committed. Current repository CI is recorded above; this table preserves the original evidence targets and still-open owner gates.

| Area | Implementation | Original evidence target / remaining gate |
| --- | --- | --- |
| Windows upgrade | `scripts/ci/select_upgrade_baseline.py` now chooses a genuine prior stable GitHub Release installer by semantic version. The release workflow checks download origin, declared SHA-256, Windows Authenticode and the publisher identity before running an in-place upgrade. It fails instead of silently using a clean-install test for later versions | Unit tests and a native signed prior-to-current upgrade with preserved user settings |
| Windows upgrade API | Full authenticated, bounded-pagination GitHub Release query with explicit failure on API error, missing historical asset, downgrade, untrusted URL and malformed hash | Actual history and signed artifacts required |
| Qt sorting | `SessionTableModel.sort()` remaps persistent QModelIndex objects by original row position, including non-first columns and duplicate IDs, while reusing presentation cache | Qt regression tests and resource profiling |
| CI history | PR workflow cancels its own superseded runs instead of accumulating unbounded runner jobs; release workflow is independent | Final-sha five-job matrix, not earlier canceled runs |
| Security baseline | Public SHA/commit false positives point to actual source lines; orphaned build-script digest entry dropped; an automated check detects future stale hash positions | `detect-secrets-hook` must succeed and synthetic credential must still be rejected |
| Evidence | JUnit parser handles leaf suites, mixed nested suites and parent-direct cases exactly once; rejects impossible counters | Full suite/coverage evidence from tested commit |
| Release policy | `scripts/ci/check_release_license.py` halts release if owner has not selected a license and retained third-party notice | **Owner decision is still outstanding**; passing this file check is not legal certification |
| Daemon cleanup | Polls for acknowledged, completed shutdown before removing disposable test data; retains diagnostic state if stop is ambiguous | Real CLI repeat-cycle tests on four OS targets |

### CI and release gates

The older handoff snapshot recorded an incomplete matrix. Checks run #88 passed all five repository CI jobs on exact commit `4648a2e80f9fb4dab18b08bc960b7b185bf816e7` after the Node 24 action updates. This proves repository CI only. Signed installs, notarization, physical GUI/accessibility, soak, owner licensing and release approval remain open; do not claim them from CI.

The remaining F3 task table below is an acceptance worklist. Several tasks now have code written; they still require real-OS/signing verification and therefore remain open.

### Status after local verification — 2026-11-15

Fetched `origin` without changing the working tree. The PR ref `origin/audit/f3-hardening-2026-11-15` is at `7715f64f7fafc14d8d8707229f58e0a2798011b9`; the local working copy is on `master` at `f94e63c39b21abcd589b45709466a9c4670dfa21`, six commits ahead with no remote-only commits. The latest hosted run inspected (`43738015537`, SHA `7715f64`) failed its `Run static checks` step on `macos-15-intel`; the run showed 1/4 jobs completed and no test artifacts. Remaining jobs are not a PASS.

On the local dirty tree after the dialog extractions, `run_static_checks.py` passed; `run_tests.py` passed 1,492 tests, zero skips, 96.80% total coverage and 3,089/3,226 = 95.75% branch coverage. The secret probe rejected its synthetic credential, and the targeted release/security/model test files passed 41 tests. These local results do not certify the hosted PR SHA.

## Implementation continuation — CI evidence and performance (2026-11-15)

Since the preceding handoff, **six additional implementation commits** were added to this draft PR. They have not been certified by a full hosted matrix.

| Commit | What changed | Tests and outstanding evidence |
| --- | --- | --- |
| `7108eb4c` | Fixed Ruff SIM117 and made pinned actionlint archive downloads atomic, with bounded size and cleanup | Static checks; negative oversized/partial-download tests |
| `8302401f` | Added `measure_refresh_cases` to session benchmark: no-op snapshot, single-row change, structural insert/remove at 1k/5k rows | Offscreen latency p50/p95/max and Qt model reset/dataChanged signal counts; hardware budgets remain unverified |
| `0fa2a9d1` | Added `scripts/ci/evidence_manifest.py`; test runner removes stale outputs and writes SHA-256 artifacts bound to `git HEAD`, `GITHUB_SHA`, and `GITHUB_RUN_ID` | CI SHA/run tampering tests and real full-suite evidence |
| `b58779f7` | Acceptance report supports direct script invocation and returns nonzero for failed gates | CLI negative tests and CI artifact |
| `6e9a945b` | Release workflow now uploads per-OS JUnit, coverage and their bound evidence manifest | Signed release execution and owner certificates |
| `673d2406` | Reworked strict JUnit validation to count real testcase elements and verify all nested/aggregate counters | Nested suite, metadata-only forgery and parent/child consistency regression tests |

**Important:** The prior hosted run `43733189106` exposed a Ruff SIM117 error in `scripts/ci/install_actionlint.py`. The fix was committed, but later runs were queued/cancelled under the PR concurrency policy. Do not infer that Ruff or pytest now passes: use the newest SHA-specific run for actual PASS/FAIL.

### Mandatory acceptance evidence

- Five-job GitHub Actions matrix (security + Windows, Ubuntu, macOS Intel, macOS ARM) at **one exact latest commit**.
- All static analysis, docs, security scanner, synthetic negative secret probe and test suite pass; **zero skips/failures**; branch coverage at least 95% within explicitly declared inventory.
- Artifact `test-results/evidence.json` SHA-256 values equal the attached JUnit and coverage files; manifest `commit` and `ci_run_id` equal the current run.
- Measured `benchmark-results/session-table.json` includes `refresh_cases` entries for 1000 and 5000 rows, and no-op refresh produces zero Qt model resets.
- Actual previous-version Windows installer / macOS notarized packages / Linux installed GUI / Qt a11y remain separately **UNVERIFIED** pending native builds and owner credentials.

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
| F3-008 | P1 | **Code added.** Release workflow selects a genuine prior stable Windows release and verifies provenance, SHA-256 and Authenticode. Still validate signed old-to-new upgrade, retained user data, migrations and rollback on a real Windows runner |
| F3-009 | P1 | **Pipeline added.** Release workflow signs the macOS app and DMG and submits them for notarization. Still verify Gatekeeper launch on Intel and ARM with owner credentials |
| F3-010 | P1 | **Package smoke added.** Release workflow launches the AppImage and installs the deb. Still validate clean GUI install/run/uninstall, retained user files and file-manager integration on Ubuntu and target Fedora |
| F3-011 | P1 | **Pipeline added.** Release workflow signs and verifies Windows binaries/installer and checks publisher identity during upgrade. Still validate fresh install and upgrade retention with owner certificate on native Windows |
| F3-012 | P1 | **Release gates added.** Tag/version check, source/security gates, per-OS tests, checksums, CycloneDX SBOMs, attestations, signing/notarization, package smoke and publish dependency are in `release.yml`. Test evidence binds commit, run ID, and XML hashes; CI now rejects dirty checkouts. Still require a successful exact-tag pipeline and verify published assets |
| F3-013 | P1 | **Implemented and verified.** `app.py` is included in configured strict mypy; all 96 configured source files pass without disabling strict checks. Run #88 passed all five jobs on exact commit `4648a2e`. |
| F3-014 | P1 | **Implemented locally.** `SessionDialog` and shared helpers are outside `app.py`; proposal parsing is in `mutaui.services.session_configuration`, while sync/forward native configuration and validation are separate. Compatibility alias, settings-path injection, and shared dialog form/save/cancel behavior remain tested. |
| F3-015 | P1 | **Implemented locally.** SSH inspection, connection profiles, portable import preview, global YAML editing, preferences, and native-project operations have dedicated UI/service/project modules with `app.py` compatibility paths. Preferences mode/theme/language application is now in `mutaui.ui.preferences_controller`; compatibility wrappers and GUI behavior have regression tests. |
| F3-016 | P1 | **Implemented locally.** Health policy, alert engine, network monitoring, session doctor/observer, notification gate and tray status each have dedicated service/UI modules; `MainWindow` compatibility paths remain. Hosted run #82 and local tests pass. Physical Qt thread-safety/a11y acceptance remains under F3-022 |
| F3-017 | P1 | **Repository tests implemented.** Tests cover stale snapshots, fsync/disk-full, canceled plans, replacement failures, conflict restore, rollback uncertainty, and abrupt isolated-daemon process-crash recovery. The new crash-recovery test passes locally; hosted cross-platform lifecycle evidence remains tied to the next exact-SHA run. |
| F3-018 | P1 | **Code gates implemented; platform acceptance partial.** Strict host-key and changed-key checks, IPv6/Unicode SSH parsing, remote symlink escape rejection, Windows `leave`/`overwrite` forward behavior, project-hook shell-consent enforcement, and GUI consent-reset behavior have tests. Hosted Linux OpenSSH and Ubuntu disconnect/reconnect acceptance passed in #83. Cross-platform live latency and installed-user hook confirmation remain open. |
| F3-019 | P1 | **Implemented locally.** Qt tests cover persistent indexes, duplicate IDs, insert/remove selection, and viewport scroll retention during incremental refresh. Offscreen 1k/5k benchmark and CI #82 pass. Physical GUI/a11y acceptance remains open |
| F3-020 | P2 | **Implemented locally.** Basic onboarding covers CLI discovery, safe local sync, default choices, help/errors, and keeps destructive actions behind later explicit flows; `tests/test_onboarding.py` has 23 cases. Clean installed-user walkthrough remains open |
| F3-021 | P2 | **Implemented locally.** EN/CS catalogs and interpolation checks exist; live settings switching now has a GUI regression test. Physical keyboard-mnemonic/accessibility audit remains open |
| F3-022 | P2 | **External acceptance open.** Real visual/a11y QA is still required on each OS across DPI 100/125/150/200, themes, languages, screen readers and keyboard-only navigation |
| F3-023 | P2 | **Runtime CPU/RSS, tray-idle, and CLI-launch instrumentation implemented locally.** Per-sample tray-idle seconds and Mutagen CLI launches are stored in SQLite and CSV; legacy rows remain unknown. Reference-hardware measurements and an 8-hour soak require real runtime evidence. |
| F3-024 | P2 | **Implemented locally, platform proof open.** Platform setup docs, actual UI screenshots, privacy-safe support exports and capability matrix exist. Clean installed-user screenshots and target-distribution walkthroughs remain open |
| F3-025 | Owner | **MIT selected and LICENSE added.** Verify Qt/PySide LGPL source delivery, relinking/replacement, installation information, and notices for each package before release; frozen-package legal review remains open |
| F3-026 | P1 | Final single-SHA signed release acceptance with current security evidence, all platform test matrices, installer acceptance and maintained version/tag |

## Release prerequisites that an agent cannot legitimately invent

The owner must decide the license; provide Apple Developer ID, notary API credentials, Windows code-signing certificate through approved GitHub Actions secrets; and accept target platform GUI/a11y behavior. No credentials belong in commits, support bundles or logs.

## Commands and verification

```bash
git fetch origin
git switch master
git pull --ff-only
uv sync --locked --group build --group test --group quality
python scripts/ci/run_static_checks.py
python scripts/ci/run_tests.py
python scripts/ci/verify_secret_detection.py
python -m pytest -q tests/test_ci_runner.py tests/test_generate_acceptance_report.py
```

Run on Python 3.12 and inspect the **hosted** workflow run for the exact resulting commit. Local tests are supplemental, never a substitute for clean Windows/macOS/Linux acceptance. Do not merge the draft PR or tag a release until all mandatory gates pass.

## Next action for the agent

Continue directly on `master`. Review the remaining F3-014—016 architecture items against current modules; close only verified repository-level work, and keep signed-install, physical GUI/accessibility, long-soak and owner-credential/license acceptance open until their real evidence exists. Keep the draft PR for reference; do not tag or publish a release while those gates remain open.

## Local continuation evidence — 2026-11-15

**Remote HEAD checked:** `7715f64f7fafc14d8d8707229f58e0a2798011b9`; branch fetched and fast-forwarded. The following edits are local and uncommitted, so they have no hosted CI run yet.

- GitHub run [43738015537](https://github.com/Harfusha/MutaUI/actions/runs/43738015537) is for this SHA. Public annotations show `checks (macos-15-intel)` failed in **Run static checks** and no test artifacts were produced; other matrix jobs are not shown complete. `gh run view --log-failed` could not retrieve logs because this environment is not authenticated to GitHub. Do not infer the hidden log's exact failure.
- `uv sync --locked --python 3.12 --group build --group test --group quality`: PASS; Python 3.12.10.
- `uv run python scripts/ci/run_static_checks.py`: PASS after applying Ruff's exact formatting to `tests/test_gui_branch_coverage.py`; Ruff, formatter, mypy, generated settings docs, Markdown, MkDocs strict build and source audit passed. MkDocs reports the audit and secret-triage pages are outside `nav`, but exits successfully.
- `uv run python scripts/ci/verify_secret_detection.py`: PASS; synthetic high-entropy credential rejected.
- `uv run pytest -x -q --tb=short tests`: PASS, 1,489 passed, 0 failed. Targeted CI, acceptance-report, session-table, Mutagen integration/daemon and GUI branch tests: PASS, 76 passed.
- `uv run python scripts/ci/run_tests.py`: FAIL locally twice on Windows/Python 3.12.10. Pytest terminates with access violation `3221225477` in `tests/test_page_shell.py::test_lazy_page_is_created_on_first_navigation_and_reused`; runner reports JUnit has 0 executed tests. The affected test passes alone and the full suite passes without coverage. Coverage acceptance remains **UNVERIFIED**; no skip or threshold change was made.
- Fixed two assertions in the new GUI branch tests: rollback now starts from an independent original settings state; Windows path expectation now uses `os.path.normpath`. Both targeted tests pass.
- No current five-job hosted matrix, native four-OS Mutagen loops, signed installers, notarization, physical GUI/a11y evidence, or owner license/certificates were obtained. F3-008—026 remain open as applicable; no merge, tag or release.

## Local continuation after branch integration — 2026-11-15

The active checkout is now the local integration commit `f94e63c39b21abcd589b45709466a9c4670dfa21` on `master`, 52 commits ahead of `origin/master`; `origin/audit/f3-hardening-2026-11-15` remains at `7715f64f7fafc14d8d8707229f58e0a2798011b9`. The working tree is dirty. No hosted run exists for the integrated commit or these uncommitted edits; the older hosted run above does not validate this state.

- Removed release signing/notarization secrets and the duplicated release-only signing step from `.github/workflows/ci.yml`; release signing remains in the tag workflow.
- Corrected `.secrets.baseline`: removed the stale build-script finding and updated actionlint checksum locations after source lines moved. Updated the triage to distinguish the stale finding from real public digests.
- Updated the compact daemon-path test to assert the actual isolated `mu-*` root, private `data`/`home` paths and compact path lengths. The production daemon path behavior is unchanged.
- Targeted release-separation, daemon-harness and secret-baseline tests: **13 passed**. `scripts/ci/run_static_checks.py`: **PASS**, including Ruff, format, mypy (59 files, now including `performance.py` and `async_recorder.py`), generated settings docs, Markdown, strict MkDocs and source audit. MkDocs still warns that three audit/security pages are outside `nav`.
- `scripts/ci/verify_secret_detection.py`: **PASS**; synthetic high-entropy credential rejected. Final `scripts/ci/run_tests.py`: **PASS**, 1,492 passed, 0 failed/skipped; branch coverage 3,111/3,252 (**95.66%**) and total coverage **96.75%**. `test-results/evidence.json` binds JUnit/coverage hashes to commit `f94e63c...`, with `ci_run_id=local`; this is local evidence only.
- `benchmarks/session_table_benchmark.py --output benchmark-results/session-table.json`: **PASS**, 30 repetitions at 1k/5k rows; unchanged refresh had 0 model resets. Offscreen unchanged p95: 4.173 ms (1k), 25.344 ms (5k). Structural-change p95: 9.419 ms (1k), 49.174 ms (5k). This is synthetic Windows 11/offscreen evidence, not installed-GUI or hosted/reference-hardware acceptance.
- Focused F3-017/018 unit coverage across action planning, replacement, conflicts, remote inspection, Mutagen client/daemon, SSH profiles and project consent: **286 passed**. The real OpenSSH acceptance integration was not run locally because this Windows host has no `sshd`.
- `git diff --check`: **PASS**. Incremental strict mypy coverage includes `sync_configuration.py`, `forward_configuration.py`, `performance.py` and `async_recorder.py`; strict typing of the large root modules remains open under F3-013.
- No hosted five-job matrix for this final state, native four-OS Mutagen lifecycle runs, signed Windows upgrade/installers, macOS notarization, Linux GUI install, physical visual/a11y/performance evidence, or owner license/certificate decisions. Keep F3-008—026 open where those gates apply. Do not merge, tag or release from this local result.

## Local continuation after typing expansion — 2026-11-15

The current checkout is still `f94e63c39b21abcd589b45709466a9c4670dfa21` on `master`. `git fetch origin` showed no remote-only commit on `origin/audit/f3-hardening-2026-11-15` (local/remote divergence: 6/0); no pull, merge, or push was performed. The working tree has local uncommitted changes.

- Expanded strict mypy to 76 source files and fixed the discovered annotations; `app.py` remains excluded and its prior strict run reported substantial typing debt. Static checks and synthetic secret detection pass for the current working tree. Focused changed-area tests passed (72 tests, plus 6 watch-default cases); `git diff --check` passes.
- Current `uv run python scripts/ci/run_tests.py`: **FAIL**, exit `3221225477`, Windows access violation at `tests/test_page_shell.py:42` while calling `app.processEvents()` in `test_lazy_page_is_created_on_first_navigation_and_reused`; runner reports zero completed tests in JUnit. That test passed alone (1 passed). Do not treat the earlier 1,492-test report as validation of this dirty tree; full-suite/coverage acceptance is unverified.
- No current hosted matrix validates this checkout. Keep F3-013 partial and F3-008—026 open where applicable; no merge, tag, or release.

## Local continuation after Qt event-pump hardening — 2026-11-15

The following evidence supersedes the previous local test failure, but covers only the dirty Windows checkout at `f94e63c39b21abcd589b45709466a9c4670dfa21` on `master`.

- `uv run python scripts/ci/run_static_checks.py`: **PASS**; Ruff, formatting, configured mypy (76 files), generated settings docs, Markdown, strict MkDocs and source audit. MkDocs still notes three audit/security pages outside navigation.
- `uv run python scripts/ci/verify_secret_detection.py`: **PASS**; disposable high-entropy credential rejected.
- `uv run python scripts/ci/run_tests.py` with isolated temporary report paths: **PASS**, 1,493 passed, 0 failed, 0 skipped; branch coverage 3,091/3,228 (**95.76%**), total coverage **96.81%**. Local manifest reports commit `f94e63c39b21abcd589b45709466a9c4670dfa21`, `ci_run_id=local`, JUnit SHA-256 `1f68c7dc44fcbfb8578b01014f5e8b20a6724feafda61cb2148e02f3e98dbf7e`, coverage SHA-256 `bf9a8c9901a3fb2a5f2e85c42d20ff516fba261ec3fb4b2b159681e64d0fde06`. These hashes cover local artifacts; they do not attest to the uncommitted diff or a hosted run.
- Removed suite-wide Qt event pumping from lazy-page tests, session-table benchmarks and SSH-dialog teardown; deferred deletion now targets the owned widget. The full suite passed after these changes. The benchmark still synchronously grabs the view/window to measure rendering.
- `benchmarks/session_table_benchmark.py` (30 repetitions): refresh canary had 0 model resets and expected insert/remove/data-change signals. At 1,000 rows, unchanged p95 was 6.625 ms and structural-change p95 14.009 ms. At 5,000 rows, unchanged p95 was 39.342 ms and structural-change p95 86.065 ms. Synthetic Windows/offscreen evidence only.
- Strict mypy configured inventory remains clean; `uv run mypy --strict app.py` still reports 385 errors. Keep F3-013 partial.
- Hosted PR run [43738015537](https://github.com/Harfusha/MutaUI/actions/runs/43738015537) is for PR HEAD `7715f64f7fafc14d8d8707229f58e0a2798011b9`; public annotations show `checks (macos-15-intel)` failed at **Run static checks**, no test artifacts, and the remaining platform jobs are not proven green. Exact failure logs require GitHub sign-in. No local result validates that PR SHA.
- No four-OS native Mutagen lifecycle runs, signed installs/upgrades, macOS notarization, Linux installed-GUI run, visual/a11y acceptance, owner license/certificate decisions, or five-job hosted PASS. F3-008—026 remain open where applicable; do not merge, tag or release.

## Local continuation after benchmark render adjustment — 2026-11-15

This section supersedes the earlier local full-suite counts and covers the current dirty Windows checkout at `f94e63c39b21abcd589b45709466a9c4670dfa21`. Reports were written under `%TEMP%\mutaui-f3-20261115211156` to preserve repository reports.

- `uv run python scripts/ci/run_tests.py`: **PASS**, 1,493 passed, 0 failed, 0 skipped; branch coverage 3,091/3,228 (**95.76%**), total coverage **96.81%**. Evidence manifest records `ci_run_id=local`, JUnit SHA-256 `73f35f6a1cfdb9f9a0b150d6df33ec49ff02ca520f54eaee7e9d15534326ed04`, coverage SHA-256 `f6954652bb8f4143078f4ffcf87dcf81e337af77523dfae89c96f8234b50a49d`. These are local artifacts, not hosted attestations.
- `uv run python scripts/ci/run_static_checks.py`: **PASS** on the current tree, including Ruff, formatting, configured mypy (76 files), docs and source audit. MkDocs warns three audit/security pages are outside navigation.
- `uv run python scripts/ci/verify_secret_detection.py`: **PASS**; synthetic high-entropy credential rejected. `git diff --check`: **PASS**; Git only reports existing LF-to-CRLF normalization warnings.
- After the final synchronous `grab()` benchmark change, the 30-repetition offscreen benchmark passed: unchanged refresh p95 6.625 ms (1k rows) and 39.342 ms (5k); structural refresh p95 14.009 ms (1k) and 86.065 ms (5k). This is synthetic Windows/offscreen evidence only.
- `uv run mypy --strict app.py` remains at 385 errors; F3-013 stays partial. Configured mypy for 76 source files passes.
- No pull, merge, push, hosted workflow rerun, four-OS native Mutagen run, signing/notarization, Linux installed-GUI, visual/a11y acceptance, or owner license/certificate decision was performed in this continuation. Keep hosted/platform/owner gates open; do not merge, tag or release.

## Local continuation after strict root typing — 2026-11-15

The active checkout remains `f94e63c39b21abcd589b45709466a9c4670dfa21` on `master`. This continuation did not fetch, pull, merge, or push. Local edits remain uncommitted; no merge or release is authorized by these local checks.

- Added `app.py` to the existing strict mypy file inventory. `uv run mypy` now passes all **78 source files** without disabling strict checks. Annotated the remaining root GUI callbacks and typed the endpoint card mapping and session notification paths.
- Fixed the verified-session replacement success path to call the existing settings persistence wrapper with the settings data. No session replacement itself was executed; this was code-path validation only.
- Extended the existing verified-replacement test to assert that settings are persisted only on verified success. The focused replacement set passed (**17 passed** before this assertion; the updated persistence test passed **2/2**).
- Extracted the sustained `AlertEngine`/`ResourceAlert` and metric coercion into `src/mutaui/services/alert_engine.py`; `app.py` imports the service directly. Existing alert tests and GUI smoke pass (16 total).
- `uv run python scripts/ci/run_static_checks.py`: **PASS**, including Ruff, formatting, strict mypy for 78 files, generated docs, Markdown, strict MkDocs build, and source audit. MkDocs still reports three audit/security pages outside the configured navigation.
- The project gate is `uv run mypy` with `strict = true` and `app.py` among its 78 explicit source roots. Diagnostic single-file `uv run mypy --strict app.py` is not equivalent under `follow_imports = "skip"`: it reports five imported-`Any` errors; forcing normal import traversal reports 41 errors across six files. No strictness setting was changed.
- `uv run python scripts/ci/run_tests.py`: **PASS**, 1,494 passed, 0 failed, 0 skipped; branch coverage 3,101/3,244 (**95.59%**) and total coverage **96.76%**. Latest local `test-results/evidence.json` (`2026-11-15T21:38:19.427003+00:00`, schema 1) binds commit `f94e63c39b21abcd589b45709466a9c4670dfa21`, `ci_run_id=local`, JUnit SHA-256 `cd37606c20a7469323fcc43e64e6db6013bd0eff9418be8051fb72696847cf8e`, and coverage SHA-256 `a714c494b7c7ad1b6368ae72af812234d8df96fbd93149f47c0105b5438be548`. These are local results, not hosted attestations.
- `uv run python scripts/ci/verify_secret_detection.py`: **PASS**; synthetic high-entropy credential rejected. `git diff --check`: **PASS**; Git reports LF-to-CRLF normalization warnings for existing modified files.
- Opened the failed [hosted run #66](https://github.com/Harfusha/MutaUI/actions/runs/43738015537) log for `macos-15-intel`: `ruff format --check .` failed because `tests/test_gui_branch_coverage.py` would be reformatted. The local dirty-tree diff contains that formatting correction and the local static-check run above passes, but neither is present in the hosted PR SHA `7715f64f7fafc14d8d8707229f58e0a2798011b9`; a new exact-SHA hosted run is still required.
- No hosted five-job PASS exists for this same final source state. The known public PR run remains failed on macOS Intel at static checks and is for PR head `7715f64f7fafc14d8d8707229f58e0a2798011b9`. Four-OS native Mutagen lifecycle runs, signed Windows upgrade/installers, macOS notarization, Linux installed-GUI, physical visual/accessibility acceptance, and owner license/certificate decisions remain unverified. Keep F3-008—026 open where applicable; do not merge, tag, or release.

## Local continuation after health network monitor extraction — 2026-11-15

The active checkout remains dirty `master` at `f94e63c39b21abcd589b45709466a9c4670dfa21`. This continuation did not fetch, pull, merge, or push.

- Read-only check of [PR #1 checks](https://github.com/Harfusha/MutaUI/pull/1/checks) still shows hosted head `7715f64`; run #66 has an Intel macOS error annotation and only 1/4 matrix jobs completed on the run page. No hosted run validates dirty `f94e63c`.

- Extracted optional `QNetworkInformation` backend setup into `src/mutaui/services/health_network_monitor.py`. `MainWindow` retains its QObject-bound signal callback and only retains the information object when the backend is supported; missing Qt/backend and `ImportError`/`RuntimeError` remain safe fallbacks.
- Added service tests for callback wiring, backend unavailability, and missing `QtNetwork`. `uv run pytest -q tests/test_health_network_monitor.py tests/test_mainwindow_flows.py -k health_network`: **9 passed**, 344 deselected. An initial run found that unsupported backends must not create MainWindow attributes; the conditional assignment now preserves that contract.
- `uv run python scripts/ci/run_static_checks.py`: **PASS**; Ruff, formatting, strict mypy for **79 source files**, generated settings docs, Markdown, strict MkDocs, and source audit. MkDocs still warns three audit/security pages are outside `nav`.
- `uv run python scripts/ci/run_tests.py`: **PASS**, **1,497 passed**, 0 failed/skipped; branch coverage **3,103/3,246 (95.59%)**, total coverage **96.76%**. Local manifest is not a hosted attestation and does not make the dirty diff a committed SHA.
- `uv run pytest -q tests/test_mutagen_integration.py tests/test_mutagen_daemon_harness.py`: **PASS**, 21 passed on local Windows/Python 3.12. This does not establish the required macOS ARM/Intel or Linux daemon cycles.
- `uv run pytest -q tests -k test_local_unix_forward_leave_preserves_entry_and_overwrite_is_explicit`: **PASS**, 1 passed on local Windows/Python 3.12. Native Mutagen 0.18.1 capability and other-OS behavior still need hosted/native evidence.
- `uv run pytest -q tests/test_ci_runner.py tests/test_generate_acceptance_report.py tests/test_session_table_benchmark.py`: **PASS**, 42 passed locally. Hosted evidence-manifest SHA/run binding remains unverified.
- GitHub run #66 remains failed on older PR SHA `7715f64f7fafc14d8d8707229f58e0a2798011b9`. No exact-SHA hosted rerun, four-OS Mutagen lifecycle, signed install, notarization, Linux installed-GUI, physical visual/accessibility acceptance, or owner license/certificate decision. P0 and F3-008—026 remain open where applicable; do not merge, tag, or release.

## Local continuation after session health observer extraction — 2026-11-15

This remains a dirty Windows checkout on `master` at `f94e63c39b21abcd589b45709466a9c4670dfa21`; no fetch, pull, merge, or push was performed.

- Extracted the fresh-session health observation loop from `MainWindow.update_diagnostics` into `src/mutaui/services/session_health_observer.py`. It retains the 60-second freshness check, stale/missing/future timestamp rejection, confirmed-failure and pause flags, scan detection, command duration, and the shared monotonic observation time.
- Added `tests/test_session_health_observer.py`; focused check: **3 passed**. The full suite also exercised these tests and the existing MainWindow flows.
- `uv run python scripts/ci/run_tests.py`: **PASS**, **1,500 passed**, 0 failed/skipped; branch coverage **3,131/3,246 (96.46%)**, total coverage **96.76%**.
- `uv run python scripts/ci/run_static_checks.py`: **PASS**; Ruff, formatting, strict mypy for **80 source files**, generated docs, Markdown, strict MkDocs, and source audit. MkDocs continues to note three audit/security pages outside `nav`.
- `git diff --check`: **PASS** after the final test and audit updates; Git reports only its normal LF-to-CRLF warnings for existing modified files.
- Hub could not create a separate task contract for this slice (terminal HTTP 500). The existing plan/task remains the durable record; the remote, platform, signed-install, notarization, installed-GUI, visual/accessibility, and owner-license gates remain open. No hosted job validates this dirty tree.

## Coverage inventory expansion and branch gate — 2026-11-16

Expanded `[tool.coverage.run].source` to include `connection_profiles.py`, `forward_configuration.py`, `ignore_presets.py`, `portable_bundle.py`, `ssh_profiles.py`, and `sync_configuration.py`; added these root modules to the strict mypy file inventory alongside `benchmark.py` and `gui_capture.py`. Coverage threshold remains 95% branch coverage.

Added validation tests for profile-store input and identity guards, ignore conversion syntax, portable-bundle sanitization/import validation, SSH config and command failures, and sync/forward configuration parsing and proposal validation. No production behavior was changed in this continuation.

Verified on Windows/Python 3.12: `uv run python scripts/ci/run_tests.py` passed, 1,564 tests, zero failed/errors/skipped; branch coverage 3,419/3,598 (95.03%). `uv run python scripts/ci/run_static_checks.py` passed: Ruff, formatting, mypy across 82 source files, generated references, Markdown/MkDocs, and source checks. `git diff --check` passed (Git emitted only existing LF-to-CRLF notices).

The Hub impact and secret-scan actions were blocked because preprocessing mode was active (`retryable=true`); they were not retried. No hosted CI or cross-platform native Mutagen lifecycle evidence was created by this local run.

## Hosted CI recheck — 2026-11-16

Read-only GitHub recheck: [PR #1 checks](https://github.com/Harfusha/MutaUI/pull/1/checks) remains a draft at head `7715f64`. The security/dependency/workflow/YAML/secret job succeeded on Nov 15. [Checks run #66](https://github.com/Harfusha/MutaUI/actions/runs/43738015537) still reports only 1 of 4 matrix jobs completed, `checks (macos-15-intel)` exited 1, and test-report artifacts were not found. Detailed logs require GitHub sign-in and were not available. This run does not validate the current dirty local `f94e63c` worktree.

## Session configuration proposal extraction — 2026-11-18

For F3-014—016, extracted typed form-text parsing and draft validation from `MainWindow.open_session_preferences` into `src/mutaui/services/session_configuration.py`. The Qt dialog still owns layout, save/cancel flow, and user-facing error reporting; proposal parsing still uses the existing `SyncConfigurationDraft` / `ForwardConfigurationDraft` validators. Added pure sync/forward service tests and a MainWindow save-path test.

Verification on Windows/Python 3.12: `uv run python scripts/ci/run_tests.py` passed, 1,570 passed, zero failures/errors/skips; branch coverage 3,422/3,600 = 95.06%. `uv run python scripts/ci/run_static_checks.py` passed, including Ruff, formatting, mypy for 83 source files, references, Markdown/MkDocs and source/layout checks. Focused secret scans completed clean for `app.py`, the new service, and both touched test files; scans were file-scoped and did not include Git history.

Current worktree remains on `master` at `f94e63c39b21abcd589b45709466a9c4670dfa21`, with 37 modified tracked files and 13 untracked files, no staged paths or conflicts. The new service and tests are among the untracked files. Hub impact reported a high-risk broad baseline diff because this task shares the existing dirty tree; the F3 work remains uncommitted and unpushed. The Agent OS task `task_70dd39449867` now has an implementation/verification checkpoint; existing plan board still has no task items.

Read-only GitHub recheck still shows draft PR #1 at `7715f64` and run #66 as the latest failed check, with only 1/4 matrix jobs completed and macOS Intel exiting 1. Detailed job logs require sign-in. Local tests do not validate the dirty `f94e63c` tree on hosted CI or on other operating systems.

## Current local candidate validation — 2026-11-17

- Main checkout: C:/Ostatní/MutagenApp, branch `master`, commit and `origin/master` at `664cdbd8f36eeaaf9977c9237f71ec537b9270d5`. Checks run #91 passed all five jobs on that exact SHA.
- `audit/f3-hardening-2026-11-15` / `origin/audit/f3-hardening-2026-11-15` at `ac4c304` and `origin/fix/ci-platform-tests-notarization-20261115` at `855110a` are both behind master and 0 commits ahead. Neither contains master-missing commits. The attached audit worktree remains on the former branch with only an untracked local Hub plan artifact.
- Current code includes the preferences-controller extraction, abrupt daemon process-crash recovery, schema-2 dirty-tree evidence validation, durable tray-idle/CLI-launch metrics, and the owner-selected MIT metadata/notice packaging. Run #90 passed; this does not provide physical/device acceptance.
- `uv run pytest tests/test_release_license_gate.py -q`: 4 passed. `uv lock --check`, `uv run python scripts/ci/run_static_checks.py`, targeted Markdown lint, and `git diff --check` passed. Native Bash/Inno/macOS package compilation was unavailable on this Windows host.
- Workflow refs use checkout v7, setup-python v7, upload-artifact v7, and download-artifact v8. Run #90 passed Ubuntu, Windows, macOS ARM, macOS Intel, and dependency/workflow/YAML/secret checks.
- Still open: signed Windows install/upgrade, macOS notarization/Gatekeeper, Linux installed GUI, DPI/accessibility/screen-reader review, live cross-platform fault/latency tests, reference-hardware metrics, 8-hour soak, Qt LGPL legal review, signing secrets (GitHub settings still has none), and release/tag acceptance.
