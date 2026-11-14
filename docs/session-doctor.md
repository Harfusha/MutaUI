# Session Doctor

Session Doctor is an offline, deterministic interpretation of typed Mutagen
snapshots. It does not execute commands or attempt recovery. Every finding has
a severity, confirmed/suspected certainty, source evidence and observation
time, a plain explanation, a safe next step, technical detail when available,
and a Mutagen documentation link. Automated fixes remain disabled.

The app records separate completion timestamps for sync and forwarding list
queries. Findings are authoritative only when the CLI is configured, the
daemon answered, both list snapshots are no more than 60 seconds old, and the
snapshot is not marked stale. Missing timestamps, an offline daemon, or a
failed list query produce an explicit unknown/stale summary; an empty session
list alone is never treated as proof that everything is healthy.

Rules cover daemon/CLI availability, stale snapshots, SSH authentication and
host trust, disconnected endpoints, missing/deleted/empty/type-changed roots,
scan and transition problems, included and excluded conflicts, permissions,
symbolic links, staging, forwarding source/destination failures, session
errors, and intentional pause/manual mode. High CPU is only a suspected finding
when a recent process measurement is available. A short in-memory trend compares
complete snapshots while the app is open; it is not persisted across launches.

Live acceptance against installed Mutagen versions and real remote endpoints
remains pending. The offline rule tests use the checked-in sync and forwarding
fixtures.

## Support Bundle

The **Support Bundle** menu offers a **Safe JSON Report**, a **Full JSON
Snapshot**, a **Local Session Log Snapshot**, and a **Local application
self-check**. Saving always uses a user-selected local file; MutaUI never
uploads the report.

The self-check verifies the application and settings paths, local SQLite
integrity, and Python, Qt, and Mutagen CLI versions. The CLI version query
disables daemon autostart. The check performs no remote writes and does not
create an export file.

The Safe JSON Report uses a fixed allowlist. It includes application, OS,
Python, Qt and Mutagen versions; daemon and session summaries; observation
ages; safe Doctor problem codes; a numeric CI run ID when present; and counts
of recent events and resource samples. It never exports event text, endpoint
identifiers, names, paths, hostnames, usernames, or raw errors.

The Full JSON Snapshot previews the selected snapshot before the save dialog
and asks for confirmation. It can contain local paths, SSH hosts, usernames,
session names, and raw error details.

The Local Session Log Snapshot is bounded to 500 recent application events and
the 1,200 lines retained from a user-selected local log file. Both raw event
messages and monitored log lines are omitted by default. Each has a separate
opt-in control; selecting either requires confirmation because its text may
contain local paths, hostnames, usernames, or credentials. The snapshot never
includes the monitored log file's path.
