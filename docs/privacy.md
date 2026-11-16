# Privacy and local data

This page describes data flows implemented by MutaUI. It is a product inventory, not an independent privacy or legal review.

## Data stored on this computer

MutaUI stores settings under the `APPDATA` directory when set (on Windows, typically `%APPDATA%\MutagenControl`); otherwise it uses `~/.config/MutagenControl`. The settings file is `settings.json`; history and metrics use a local `metrics.sqlite3` database. Connection profiles and ignore presets use separate JSON files in the same directory. These files can contain local paths, endpoint names, hostnames, usernames, and other values the user entered.

MutaUI does not sync these settings, profiles, presets, or history to a MutaUI service. A sync session explicitly created through MutaUI may send or receive file contents through Mutagen and the configured endpoints; that transfer follows the selected Mutagen configuration.

## Network requests

Release checks are disabled by default. When the user enables and saves the setting, MutaUI may request public release metadata from GitHub. The request identifies the application version in its user agent. It does not include session, endpoint, path, or device data. MutaUI does not download or install an update.

During normal monitoring, MutaUI makes read-only local CLI queries to inspect the installed Mutagen daemon and session status. These queries do not upload data to a MutaUI service. Existing Mutagen sessions may continue syncing their configured endpoints independently of the MutaUI window. Session creation, reconfiguration, and recovery operations initiated in MutaUI use the installed Mutagen CLI and follow the selected endpoint configuration and consent flow.

The onboarding CLI version and help checks are read-only. Its optional sync test uses temporary local folders and a temporary Mutagen data directory; it does not use SSH or the existing Mutagen daemon.

## Export choices

- **Safe diagnostics:** uses an allowlist. It excludes session identifiers and names, paths, hosts, authentication material, and raw errors.
- **Full session snapshot:** can contain local paths, endpoints, session names, and daemon details. MutaUI previews it and asks for confirmation before saving.
- **Session log snapshot:** event messages and monitored log lines are omitted by default. Selecting either raw-text option prompts for confirmation because logs may contain paths, hostnames, usernames, or credentials. The user selects a local destination.
- **Portable profile bundle:** exports selected connection profiles, ignore presets, and safe preferences. It excludes the application binary, session notes, and history; import previews choices before writing local files.

MutaUI does not automatically upload these exports. Review each preview and save only to a location you control. See [troubleshooting and diagnostic exports](troubleshooting/debugging.md) for the available support data.

## Source references

- Settings and history paths: `app.py` (`settings_path`, `MainWindow.__init__`).
- Routine local daemon polling: `app.py` (`MainWindow.refresh`) and `mutagen_client.py`.
- Release metadata request: `src/mutaui/services/update_checker.py`.
- Safe diagnostics and log export allowlists: `insights.py`.
- Portable export/import: `portable_bundle.py` and `app.py`.
- Platform capability and acceptance limits: [capability matrix](capability-matrix.md) and [acceptance traceability](acceptance-traceability.md).
