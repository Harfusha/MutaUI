# Mutagen Control v9.2.0 — Comprehensive Audit Remediation Release

## Audit Remediation and Stability

- **Worker Lifecycle and Resource Management (M90):** Eliminated callback reference cycles between Shiboken6 `QRunnable` workers and listener signals; constant handle/memory footprint verified over 5,000+ background tasks.
- **Packaging and Distribution Truthfulness (Batch 2F):**
  - Accurately disclosed Authenticode (unsigned) and Gatekeeper (ad-hoc signed, unnotarized) status across release artifacts and documentation (`M48`, `M86`).
  - Unified application versioning across window titles, footers, settings bundle exports, and macOS `Info.plist` metadata (`M49`, `M89`).
  - Established explicit Linux baseline (`GLIBC >= 2.38`) in deb package metadata and compatibility documentation (`M76`, `M77`).
  - Fixed Windows release workflow to sign inner application binaries before Inno Setup packaging, and pinned Inno Setup to version 6.3.3 (`M59`, `M60`, `M75`).
  - Resolved dynamic candidate versions in CI/release workflows instead of hardcoded strings or bare branch names (`M61`, `M62`).
  - Enhanced Linux SBOM generation by scanning unpacked native payload rather than archive containers (`M63`).
  - Ensured Linux desktop file-manager integration uses persistent `$APPIMAGE` paths rather than transient PyInstaller extraction mounts (`M64`).
  - Added repository line-ending normalization via `.gitattributes` (`M73`).
  - Documented isolated per-user AppImage extraction caches preventing multi-user permission collisions (`M91`).
- **Core Truthfulness and Concurrency (Batches 2A-2E):**
  - Split synchronization and forward query pipelines to prevent transient status clobbering (`M04`–`M06`, `M84`, `M85`).
  - Added pre-check selection limits, explicit pause verification, and deferred Auto-safe config recovery (`M07`, `M08`, `M16`, `M18`, `M54`).
  - Prevented profile configuration bleed and anchored ignore patterns (`M09`, `M10`, `M12`).
  - Decoupled UI log clearing from durable SQLite event history (`M23`) and added atomic config backups (`M29`–`M31`).
  - Offloaded long-running SSH checks and project commands to background threads (`M34`).
  - Enforced safe diagnostic exports by default (`M38`) and symlink-protected audit log rotation (`M39`).

## Fixes

- Fixed onboarding wizard contrast in light and dark themes.
- Live log updates preserve scroll position and selection. Manual scrolling pauses follow
  mode.

---

# Mutagen Control v8.2 — Windows GUI fixes and watch profiles

## Integration work

- Added an opt-in startup/manual release check using public GitHub metadata only; update checks default off and never download or install binaries.
- Added per-user Windows installer, Intel/Apple Silicon macOS DMGs, Linux AppImage/deb packages, and install/upgrade guidance; signing, notarization, CI secrets, and platform acceptance remain release gates.
- Added Paramiko collection to PyInstaller builds so the optional SSH/SFTP inspector is available in packaged apps.
- Added one gated tagged-release pipeline that runs platform checks, emits SBOMs and provenance, verifies hashes, and publishes only when all platform jobs pass.
- Pinned CI integration to official Mutagen v0.18.1 artifacts and verify each downloaded archive against the release SHA-256 manifest before testing.
- Added a strict MkDocs Material build to CI and release checks, with a retained documentation-site artifact for review.
- Added dependency vulnerability audits, GitHub Actions linting, YAML linting, and baseline-backed secret detection to CI and tagged releases; raised the Paramiko minimum to the audited fixed major line.
- Added the required bilingual build/release and remote-inspection security guides, with compatibility links from the earlier documentation paths.
- Added a deterministic 12-case pairwise visual-QA capture matrix across locale, theme, Basic/Advanced mode, and DPI; captures remain diagnostic until localized UI and manual review are complete.
- Added a cross-platform session-model performance canary for 0–5,000 rows with latency percentiles and machine/RSS metadata; it explicitly excludes GUI paint and native CLI time.
- Expanded Czech localization for page navigation, overview, settings sections, session status, and shared labels/buttons; a catalog test catches untranslated literal calls through the common UI helpers.
- Localized live Mutagen sync/forward status, endpoint connection state, and endpoint empty-state messages without changing native status data.
- Added Windows native suspend/resume broadcasts to the sleep/network grace tracker; polling-gap wake detection remains a fallback, and macOS/Linux event coverage is unverified.
- Classified OpenSSH's unknown-key and changed-key diagnostics distinctly while keeping strict host-key checking; isolated live-host acceptance remains open.
- Expanded conflict-resolver fault coverage: stale post-preview file content blocks before writes, and rollback retains both original backups; the resolver remains disabled pending full acceptance gates.
- Added Advanced forward source/destination Unix socket fields, safe `leave` defaults, local platform checks, installed-CLI flag checks, and R3 typed confirmation for overwrite; live Mutagen/platform and remote path preflight acceptance remain open.
- Expanded the safe diagnostics JSON allowlist with runtime versions, observation freshness, sanitized problem codes, numeric CI run ID, and event counts; raw event text and endpoint details stay excluded.

- Added a consent-gated, exact-ID replacement coordinator with a fresh snapshot check, native post-verification, and best-effort restore. It uses an injected backend; no live Mutagen backend is connected and no live session was changed.
- Added a project YAML edit flow with exact diff, validation, stale-write guard, backup and audit. Project sessions remain owned by their native project file; editing does not recreate them or run hooks.
- Added opt-in SSH/SFTP conflict copy inspection with known-host verification, bounded reads, temporary copy cleanup and redacted audit.
- Added local/remote conflict comparison using read-only temporary copies and an explicitly selected diff application. Two-remote comparisons remain unavailable.
- Added a tested local/local single-file manual resolution service with backups and rollback reporting. Its feature flag stays off until cross-platform and live Mutagen fault acceptance passes.
- Added bounded exact-path conflict recommendations; the default-off rules never select or apply a resolution automatically.
- Added single-instance request forwarding and exact session/folder/project/Doctor launch routes; overlapping folder roots are reported instead of guessed.

## Fixes

- Fixed a GUI smoke test assumption: the first server may have forwarding sessions only. The test now checks the actual contents of each group, including empty states.
- The **Servers** overview now shows explicit empty states for each session type.
- Session details are no longer constrained by a vertical splitter. The sync and settings pages use their natural content height with scrolling.
- Session detail controls are arranged in two rows (3 + 2) instead of one long row.
- The circular status indicator uses pixel-sized text and a separate caption area to avoid overlap at high DPI.
- Form controls have consistent minimum heights and more room for their contents.
- Added `--self-test`, which runs directly from the packaged EXE. After packaging, the build checks the actual bundle and fails if the check fails. Diagnostics are written to `%TEMP%\mutagen-control-self-test.log`.
- Added `gui_preview.cmd` for offline visual screenshots of all 11 pages at 100%, 150%, and 200% scaling.

## New settings

- **Adaptive GUI status polling:** faster polling during status changes or active phases, with a lower-frequency interval after a configured idle period. Polling intervals and idle duration are configurable.
- **Native profiles for new sync sessions:** default, event-driven, fast/medium/power-saving polling, and manual `no-watch`.
- **Settings for an existing session:** local note, per-session notifications, and a preview of the watch/scan configuration read from Mutagen status.
- Added independent tests for adaptive scheduling and session creation options.

## Limitations

- Profiles **do not modify existing sessions**. The standard Mutagen CLI has no `sync edit/update` command.
- This is not a bandwidth limiter. The Mutagen CLI path used here does not offer simple per-session bandwidth throttling. The polling interval controls how often file changes are checked, not file transfer speed.
- Adaptive GUI polling does not change the Mutagen daemon's internal behavior. Sync continues after the GUI closes according to Mutagen's native settings.
- Final build integration was verified on Windows in a temporary Python environment with PySide6 6.12 and PyInstaller 6.22.3. The one-folder EXE built successfully and passed `--self-test`; the packaged artifact remains in the temporary verification folder.
