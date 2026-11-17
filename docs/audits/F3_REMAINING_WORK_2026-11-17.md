# MutaUI F3 — remaining work handoff

- **Updated:** 2026-11-17 17:36 UTC
- **Repository:** `C:\Ostatní\MutagenApp`
- **Branch / pushed HEAD:** `master` / `8b111993818fd9abb0ac6cdb6ae715c746eef6b1`
- **Canonical plan:** `.local-ai-hub/plans/plan_3633c4195d5e.plan.json` (local, untracked; do not commit)

## Stop point

The user asked to stop work after recording everything still open. Do not describe the project as complete or resume implementation until the user resumes the goal. The existing goal remains unfinished. No release tag or binary release was created.

## Repository and CI state

- The main checkout is on `master`; the last pushed commit is `8b11199`. The tracked working tree was clean. The only untracked file in the main checkout was the Local AI Hub plan above.
- `audit/f3-hardening-2026-11-15` at `ac4c304` and `fix/ci-platform-tests-notarization-20261115` at `855110a` are behind `master`, each with **0 commits ahead**. No branch-only commits need integration. The attached audit worktree is `C:\Users\Adam\.codex\worktrees\mutaui-f3-pr\MutagenApp`; its only untracked item was its local Hub plan. Continue on the main checkout when resumed; do not remove either local plan artifact.
- Run #90 passed all five jobs on `7965d752f38cf752c0d0615e56a9f4bcfe7e059f`. Runs #91 and #92 also passed all five jobs on their exact SHAs (`664cdbd8f36eeaaf9977c9237f71ec537b9270d5` and `64b3bec347659910ee1f91f748afa8e01e80e1b4`).
- Run #93, on exact SHA `8b111993818fd9abb0ac6cdb6ae715c746eef6b1`, failed attempt 1 only at macOS Intel **Package macOS disk image**: `hdiutil: create failed - Resource busy`. Its other four jobs passed. This matches a prior transient Intel runner failure that passed on rerun without a source change.
- GitHub accepted rerun attempt 2 for the failed job and dependents. At the last direct observation (17:33:57 UTC), Windows, Ubuntu, macOS ARM, and dependency/workflow checks had passed; macOS Intel was running **Run synthetic session model performance canary**. Its final result is unknown because monitoring stopped here. On resume, check run #93 attempt 2 before changing code; do not treat this as a source failure unless its log shows one.

## Completed in this continuation

- Owner selected MIT for project-owned code. `LICENSE`, `pyproject.toml` metadata, official LGPL-3.0 and LGPL-2.1 texts, third-party notices, and package copies were added for Windows, macOS, AppImage, and DEB outputs.
- Release preflight now blocks unless `NOTICE.md` contains `LGPL distribution review: APPROVED`. Current status is **PENDING**; never change it to approved without completed owner/legal review.
- Windows installer now installs the MIT LICENSE file as well as notices and LGPL texts.
- Focused license gate tests: 4 passed. `uv lock --check`, full `scripts/ci/run_static_checks.py`, targeted Markdown lint, and `git diff --check` passed.
- Commits were pushed to `master`, including `7965d75` (license gate/package notices), `664cdbd` (checkpoint with run #90), `64b3bec` (checkpoint with run #91), and `8b11199` (current license/release blocker wording).

## Still blocked or unverified

1. **Signing secrets:** Chrome confirmed `Harfusha/MutaUI` has no repository or environment Actions secrets. A secure password-field prompt for the values was skipped; no secret values were received or stored. The owner must add these eight repository secrets directly in GitHub Settings → Secrets and variables → Actions:
   - `WINDOWS_SIGNING_CERT_BASE64`
   - `WINDOWS_SIGNING_CERT_PASSWORD`
   - `APPLE_DEVELOPER_ID_CERT_P12_BASE64`
   - `APPLE_DEVELOPER_ID_CERT_PASSWORD`
   - `APPLE_DEVELOPER_ID_APPLICATION`
   - `APPLE_NOTARY_API_KEY_P8_BASE64`
   - `APPLE_NOTARY_API_KEY_ID`
   - `APPLE_NOTARY_ISSUER_ID`
   Never ask for or put their values in chat, source control, or logs.
2. **LGPL release review:** Qt/PySide 6.8.3 under LGPLv3 and Paramiko 5.1.0 under LGPLv2.1 need an owner/legal review for the exact binaries and package set: corresponding source delivery or offer, library replacement/relinking, sufficient installation information (especially Windows one-file), and notices. Keep the preflight pending and publish no binary release until reviewed.
3. **Windows:** native signed Authenticode identity, clean install, upgrade from a genuine previous release, user-data/migration retention, and rollback remain unverified.
4. **macOS:** Developer ID signing, notarization, and Gatekeeper launch on Intel and Apple Silicon remain unverified.
5. **Linux:** clean installed-user AppImage/DEB install, run, uninstall, retained user data, and file-manager integration on Ubuntu and target Fedora remain unverified.
6. **Live runtime:** cross-platform network latency/fault matrix and installed-user project-hook consent still need live acceptance.
7. **Physical acceptance:** DPI 100/125/150/200, themes, EN/CS, keyboard-only and screen-reader behavior, reference CPU/RSS/tray/CLI metrics, and an 8-hour soak still need real-device receipts.
8. **Repository audit:** the tracked F3 repo-scope task remains in progress. Reconcile each repo-level F3-013–024 item against current source/tests and exact-SHA evidence before calling the repo audit done.
9. **Release:** after all preceding gates pass, choose/confirm the next version/tag, run the exact-tag security/package/signing workflow, and verify checksums, SBOMs, attestations, signatures, and published assets. No version tag or release was approved here.

## Validation limits

The local host is Windows and had no usable Bash/Git Bash, Inno compiler, or macOS toolchain; Linux shell syntax and native Inno/macOS package compilation were not run locally. Hosted CI built demo artifacts, not a signed/notarized public release. Run #93 attempt 1's `hdiutil` failure is a runner/resource error unless attempt 2 provides contrary log evidence.
