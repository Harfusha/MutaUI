# Controlled session replacement

PR-027 adds a narrow replacement coordinator for non-project sync sessions.
The coordinator requires a consented R2 `sync_reconfigure` plan, one locked
session ID, a fresh native fingerprint, lossless JSON snapshot validation,
known configuration fields, and the exact original `sync create` argv captured
by the preview. Project-owned sessions and broad `--all` targeting are refused.

All Mutagen interaction is behind an injected backend. The coordinator checks
the fingerprint and exact session immediately before termination, creates the
replacement, and verifies the returned session against the proposed settings.
The production `MutagenReplacementBackend` uses `MutagenClient` with argument
arrays, exact-ID termination, a source fingerprint identical to native snapshot
validation, and post-create lookup by the exact returned ID or unique requested
name. If creation or verification fails, an identified unverified session is
terminated by exact ID before the captured old command is replayed. The receipt
reports whether restoration verified. The caller must persist emitted audit
events; the coordinator does not claim durable audit.

`replace_non_project_mutagen_session` binds the coordinator to the production
adapter. MutaUI captures verified create arguments by exact native ID in a
private, local-only provenance file after successful creation. The file is not
included in portable exports; external sessions and interrupted creates have no
trusted provenance and remain ineligible. A capability-checked renderer now
overlays a bounded set of fields only when the installed `sync create --help`
advertises the required flags. The GUI requires local exact-ID provenance, a
current loaded session, a complete known configuration, non-project ownership,
an explicit command and data-effects review, and R2 consent. Execution runs off
the UI thread, rechecks the native fingerprint before termination, persists
exact-ID phase audit events, and migrates local note/favorite links after
verified replacement. Unsupported fields and unknown flags stay blocked.
Unit tests use fake backends. On Windows, pinned Mutagen 0.18.1 passed an
isolated-daemon integration that synchronized a local marker, replaced the
session through the production backend, forced a create failure, and verified
best-effort restoration. The CLI archive was checked against Mutagen's official
SHA-256 manifest. Interactive GUI acceptance and other-platform CLI acceptance
remain open. PR-028 provides the separate project-owned workflow.
PR-030/031 and the G3 fault/platform gates remain open before conflict-file
mutation is enabled. Cross-platform and real-CLI acceptance remain open.
