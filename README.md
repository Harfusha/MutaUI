# Mutagen Control

Standalone GUI for the existing Mutagen CLI. It does not install a service on the server, open its own SSH session, or install a remote agent. It reads output from `mutagen sync list` and `mutagen forward list` through the local daemon.

## Run and verify

1. Extract the ZIP into a **new folder** (do not merge it with v8/v8.1).
2. Run `start.cmd` (creates a local Python environment and installs dependencies).
3. Try `demo.cmd` first, then optionally run `check_windows.cmd`.
4. `build_fast.cmd` creates `dist-fast\MutagenControl\MutagenControl.exe` in a portable folder; **copy the entire folder**.
5. `build_exe.cmd` creates the single-file `dist\MutagenControl.exe`. Python is required during the build, but not to run the EXE. Mutagen CLI must be available on the computer.

All build scripts run the Qt GUI smoke test. If it fails, **the build stops without creating a new EXE**. Use a freshly built version, not old files in `dist-debug`.

## Settings

**Settings → Application Behavior**: status polling interval, adaptive interval during activity, interval after an idle period, idle duration, CPU/RAM sampling interval, and power-saving mode in the system tray. These settings control only how often the GUI polls; **they do not change Mutagen's sync algorithm**.

**Default profile for new sync sessions**: choose the default file change detection profile selected in the `New Sync` dialog.

**Per session → Session Settings**: local note, notifications on/off, and the actual `watch` / `scan` configuration read from Mutagen's native data. These options do not change the existing server or daemon configuration. To use a different native polling mode for an existing sync, safely replace it with a new session manually; the application does not do this because it could trigger files to be reevaluated.

### Profiles for new sync sessions

| Profile | Options passed at creation |
| --- | --- |
| Default | Keep Mutagen's default configuration |
| Event-driven | `--watch-mode=portable --scan-mode=accelerated` |
| Fast polling | `--watch-mode=force-poll --watch-polling-interval=5` |
| Medium polling | `--watch-mode=force-poll --watch-polling-interval=20` |
| Power-saving polling | `--watch-mode=force-poll --watch-polling-interval=60` |
| Manual | `--watch-mode=no-watch` |

`no-watch` does not pause a session; use **Sync Now** (`mutagen sync flush`) to force a cycle. The filesystem polling interval is separate from data transfer speed, which the GUI cannot reliably limit.

## Bulk actions and servers

The `Servers` page groups sessions by protocol, host, and port without DNS lookups. A sync session can belong to two remote hosts when both ALPHA and BETA are remote. Exact session IDs are passed to `mutagen sync flush|pause|resume|reset|terminate` or the equivalent forwarding commands. The application does not use `--all` or act on unrelated hosts.

Automatic start for native sessions uses per-session pause/resume and Mutagen daemon registration in Windows Run. Turning off automatic start pauses the session immediately. The application has no separate scheduler or service.

## Live log and remote endpoint

The application shows live status changes and can follow an **existing local log file**. The standard CLI does not provide a persistent, complete stream of the remote `mutagen-agent` internal debug logs. Remote server CPU/RAM are also absent from endpoint status, so the GUI does not invent those values.

## Verification

- `python verify_source.py` checks the code and known static issues with Qt layouts.
- `python -m pytest -q tests --ignore=tests/test_gui_smoke.py` runs the available logic tests.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_gui_smoke.py` on Windows checks **actual page creation**, navigation, graphs, and server groups. This test must pass before a build.
- Current verification results belong to the GitHub Actions run that produced them. The workflow runs static checks, tests, both Windows builds, and packaged EXE self-tests; this source checkout does not include those generated executables.

This is not an official application from the Mutagen project. The demo mode does not perform operations on real sessions.

### DPI preview

`gui_preview.cmd` saves screenshots of all 11 demo pages into `preview-1`, `preview-1.5`, and `preview-2` at 100%, 150%, and 200% scaling. Use the images to spot overlapping controls without connecting to Mutagen. This creates images but **does not evaluate their visual quality**.

### Check the packaged EXE

Previous builds checked only the source GUI. In v8.2, build scripts also run the **packaged EXE** with `--self-test` after PyInstaller. Without contacting the Mutagen daemon, it opens the demo, visits every page, and checks the server group tables. A failure stops the build with an error code.

Find the self-test log at `%TEMP%\mutagen-control-self-test.log`. Run the same check from a shell with `dist-fast\MutagenControl\MutagenControl.exe --self-test`. `--self-test` is not a benchmark and does not compare every pixel; it checks that the packaged Qt GUI runs and that its data structure is valid.
