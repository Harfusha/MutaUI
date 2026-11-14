# Threat model / Model hrozeb

## Assets and trust boundaries

- User files and Mutagen's session state remain under Mutagen's control; MutaUI must not silently rewrite them.
- SSH private keys, `known_hosts`, passwords, tokens, private paths, and diagnostic data are sensitive local assets.
- The local Mutagen CLI/daemon, configured SSH host, native project files, imported bundles, and filesystem endpoints are separate trust boundaries.

## Main threats and controls

- **Wrong-target or broad command:** use exact native IDs, reject `--all`, preview argv, validate preconditions, and verify the post-action target.
- **Destructive sync/replacement:** make direction and impact visible, require applicable R2/R3 confirmation, preserve backups, and stop on stale or ambiguous state.
- **SSH host spoofing:** require strict host-key checking; do not add unknown keys or bypass changed-key warnings.
- **Project command execution:** display hook/custom-command content without running it in previews; require explicit high-risk user consent to execute.
- **Path traversal or stale files:** constrain remote inspection paths and recheck files against the preview before resolving conflicts.
- **Sensitive export leakage:** allowlist preferences, redact local paths and URL passwords by default, exclude key material and Mutagen history/state, checksum the bundle, and validate before import.

## Limits

These controls reduce risk but do not make sync operations harmless. Mutagen may propagate modifications and deletions. Automated checks do not replace review of exact paths, backups, endpoint identities, and operation previews. Platform and live-service gates remain listed in [acceptance traceability](../acceptance-traceability.md).
