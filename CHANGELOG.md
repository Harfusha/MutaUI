# Mutagen Control v8.2 — Windows GUI fixes and watch profiles

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
