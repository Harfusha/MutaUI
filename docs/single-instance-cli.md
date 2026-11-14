# Single instance and launch commands

PR-033/034 add per-user Qt local-socket forwarding and a narrow launch CLI:
`--open-session EXACT_ID`, `--open-folder PATH`, `--open-project FILE`,
`--doctor`, `--demo`, `--self-test`, and `--version`. A second process forwards
one bounded JSON request to the first and exits after acknowledgement. The
socket name is a hash of the local user identity, messages accept only the
listed routes, and stale sockets are not removed automatically. Exact session
IDs are used; folder lookup reports every overlapping match rather than
guessing.

`Ctrl+K` searches pages, current session names and IDs, and commands to focus a
sync/forward, open a native project, or open Doctor. It offers Flush only for
current, unpaused syncs; execution still goes through the existing action
planner and exact session ID.

`--open-folder` resolves existing local paths against the latest non-stale sync
snapshot. `--open-project` opens the selected native file. Remote folders,
stale sessions, and missing IDs remain unselected.

The Windows installer offers an unchecked, per-user File Explorer **Send To**
shortcut. Enable it during installation to pass one selected path to
`--open-folder`; overlapping sync roots are shown as ambiguous choices. The
shortcut lives in the current user's Send To folder, needs no elevation, and is
removed by uninstalling Mutagen Control. To opt out later, uninstall and
reinstall without selecting the option. macOS Finder/Services and Linux file
manager packages remain unsupported and are not installed.
