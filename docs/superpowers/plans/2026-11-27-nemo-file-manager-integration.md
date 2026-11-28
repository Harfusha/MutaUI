# Nemo File Manager Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, per-user Nemo script that opens the selected folder in MutaUI.

**Architecture:** Generate `nemo/scripts/Open folder in MutaUI` beside the existing Nautilus and Dolphin hooks. Read `NEMO_SCRIPT_SELECTED_FILE_PATHS`, apply the same single-path and newline checks as Nautilus, and include the script in manifest ownership, install rollback, legacy-manifest upgrade, and uninstall.

**Tech Stack:** Python standard library, pytest, POSIX shell scripts, Nemo scripts.

**Spec:** User handoff attachment, Linux file-manager integration gate naming Nautilus, Dolphin, and Nemo.

## Global Constraints

- Install hooks only in the current user's data directory.
- Never overwrite unowned hooks; remove only unchanged files owned by the manifest.
- Preserve `MANUAL_RESOLUTION_ENABLED = False`, exact session targeting, and `StrictHostKeyChecking=yes`.
- Do not sign or notarize builds.

## Review Focus

- A selected path contains spaces — preserve it as one argument; test the Nemo script.
- Selection contains embedded newlines — reject it; test the Nemo script.
- A Nemo hook already exists without ownership — refuse without partial writes; test installer conflict handling.
- An installed v2 manifest has only Nautilus and Dolphin hooks — add Nemo without losing those hooks; test in-place manifest migration.
- A managed hook was edited — refuse uninstall and preserve all files; test ownership verification.

---

### Task 1: Add Nemo to the existing opt-in integration

**Files:**
- Modify: `src/mutaui/services/linux_file_manager_integration.py`
- Test: `tests/test_linux_file_manager_integration.py`

**Interfaces:**
- Consumes: `install_linux_file_manager_integration(...)` and `remove_linux_file_manager_integration(...)`.
- Produces: the per-user Nemo script `nemo/scripts/Open folder in MutaUI`; the existing CLI install/remove actions remain unchanged.

- [x] Add tests for new install, executable mode, selected-path handling, conflict refusal, v2 manifest migration, and ownership-safe removal.
- [x] Run the focused tests and confirm the new behavior fails before implementation.
- [x] Add the Nemo script and include it in manifest hashes, rollback, and cleanup.
- [x] Support existing v2 manifests so an already-installed Nautilus/Dolphin integration upgrades in place without overwriting an unowned Nemo script.
- [x] Run the focused test module and full test suite; keep signing excluded.

## Follow-up: Dolphin Service Menu Execution

- Ubuntu 24.04 GUI smoke used the packaged AppImage and real Nautilus, Dolphin, and Nemo processes under Xvfb.
- Nemo and Nautilus context-menu scripts executed and preserved selected paths containing spaces.
- Dolphin exposed the action but rejected it because KDE requires the user service-menu `.desktop` file to be executable. The installer now sets that mode on fresh installs, legacy upgrades, and repairs an existing owned install; the action was rerun through Dolphin and preserved the selected directory path as one argument.
- Linux integration module: 41 passed. Full Windows suite: 1,838 passed, 0 skipped, branch coverage 95.10%. Static checks passed.
- Container GUI checks do not replace physical desktop, screen-reader, DPI, sleep/wake, or multi-distro checks. No signing or notarization.

## Follow-up: Acceptance audit (2026-11-27)

- Re-ran the exact CI runner with a fresh temporary `MUTAGEN_DATA_DIRECTORY`: 1,838 passed, 0 skipped, branch coverage 95.10%.
- Linux file-manager integration module passed in disposable Fedora 40 and Arch containers: 41 passed on each. These module tests do not constitute GUI acceptance on those distributions.
- Built the Windows onedir demo and release-style onefile executable into isolated temp output directories. Both passed the packaged UI self-test and packaged crash-recovery test; the onedir native-library audit scanned 90 libraries.
- `Get-AuthenticodeSignature` reports the onefile executable as `NotSigned`, as requested. No signing was run.
- Static checks, `verify_source.py`, version consistency, `.yamllint`, secret detection, `pip-audit`, and `check_release_license.py` passed. `NOTICE.md` currently records the LGPL distribution review as approved by the repository owner.
- GitHub tag `v9.3.0` points to `a6436bc`. Hosted Checks run #121 failed at `Check GitHub Actions workflows` and `Run logic and integration tests` on all four OS jobs. Verified release run #10 also failed at the workflow check; build and publish jobs were skipped. GitHub annotations are generic; unauthenticated log and artifact downloads returned 403, so exact hosted failures remain unknown.
- GitHub release status for `v9.3.0` is inconsistent: the REST release-tag API returns 404, while the browser page renders the tag as a release with two assets but cannot load their details. Publication and usable release artifacts remain unverified. No signing or notarization was performed or added locally.
- This host has no Windows Sandbox or detected VM runner. Physical screen-reader, mixed-DPI, sleep/wake, soak, and desktop acceptance remain open. Linux manager GUI interaction was tested only in Ubuntu 24.04 Xvfb.
