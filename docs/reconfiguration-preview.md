# Reconfiguration preview

Reconfiguration previews are read-only. They bind to the exact native session
identifier and SHA-256 of the current canonical native snapshot, then show a
structured current/proposed configuration diff. Sync replacement calls out
that session history is cleared and a new scan is triggered. The preview never
executes Mutagen commands.

The validator preserves the complete native JSON object and verifies a finite
JSON round-trip. It also requires an explicitly supplied command argument list
and exact target association; it never reconstructs missing original command
arguments from session names. Unrepresented configuration fields, broad
`--all` selectors, stale snapshots, malformed JSON values, or a target mismatch
keep the snapshot incomplete for any future replacement flow.

`snapshot_inputs_complete` means that required preview inputs were present. It
does not authorize execution. PR-027 owns controlled replacement and must add a
fresh preflight, explicit user consent, restore verification, and a hard block
for incomplete snapshots. No replacement path is enabled by PR-026.
