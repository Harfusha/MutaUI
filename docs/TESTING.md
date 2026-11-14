# Runtime and integration testing

## Packaged application

Run the `Build Mutagen Control for Windows` workflow manually to build both EXEs and run their `--self-test` checks. If either check fails, inspect the uploaded `mutagen-control-self-test.log` artifact before changing packaging inputs.

For crash-recovery acceptance, run `python scripts/run_crash_recovery_self_test.py --executable <path-to-MutagenControl.exe>` against each built EXE. The runner creates isolated settings and SQLite history in a temporary profile, exits a fixture process during a WAL transaction, then verifies that the packaged app restores the last valid settings and reopens the committed history without contacting a Mutagen daemon.

## Isolated local Mutagen daemon

The optional test `tests/test_mutagen_integration.py` starts a real Mutagen daemon against temporary local folders. It sets `MUTAGEN_DATA_DIRECTORY` to a temporary directory so the test does not use the normal daemon's session database. Run it on a machine with Mutagen installed:

```powershell
$env:MUTAGEN_BINARY = "C:\Program Files\Mutagen\mutagen.exe"
.venv\Scripts\python.exe -m pytest -q tests/test_mutagen_integration.py
```

The integration suite uses a temporary `two-way-safe` session, checks that a marker file reaches the second local folder, and terminates its test session and daemon. It also suspends the isolated daemon while the GUI issues 20 refresh requests, measures Qt heartbeat latency, and counts real Mutagen CLI processes with `psutil` to check responsiveness and process storms. CI skips these tests when no Mutagen executable is installed.

The Support Bundle dialog offers the safe allowlist, a previewed full snapshot with confirmation, and a local log snapshot. Raw event messages and monitored log lines have separate opt-in controls and a confirmation; neither is included by default, and nothing is uploaded. The real-CLI export integration test starts Mutagen with an isolated data directory, obtains a fresh snapshot through the GUI's CLI refresh, writes the Safe JSON Report, and checks that the CLI binary and isolated data paths are absent. CI installs the pinned Mutagen CLI before running this test; locally, set `MUTAGEN_BINARY` to the installed executable and run `pytest -q tests/test_mutagen_integration.py::test_real_mutagen_safe_report_export_uses_isolated_cli_snapshot`.

## SSH recovery check

SSH integration needs an operator-provided test host and credentials, so CI does not invent or use them. To validate recovery manually, use two disposable folders and a separate SSH account/path, create a `two-way-safe` session, confirm the initial sync, briefly make the SSH endpoint unavailable, then restore it and confirm the session returns to an active state and transfers a new marker. Inspect the session error and logs during the outage. Do not use production data for this check. No SSH recovery run is claimed by this repository's automated tests.

## Qt dependency

The application imports QtCore, QtGui, and QtWidgets only. Runtime requirements therefore pin `PySide6-Essentials` 6.8.3; the larger PySide6 distribution adds Qt modules the application does not import. The pin was checked in a clean Python 3.12 environment by building the Windows one-folder app and passing its packaged self-test. Qt Essentials 6.11.1 and 6.12.0 failed at frozen `QtCore` import on that same host, so they are not used until packaging is verified again.
