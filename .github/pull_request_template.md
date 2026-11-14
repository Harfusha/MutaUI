## Change

<!-- What changed and why? Link the source requirement and AC/E/PR IDs. -->

## Verification

- [ ] Commands and results recorded; distinguish local, hosted, runtime, and manual OS evidence.
- [ ] Relevant tests and static checks pass.
- [ ] Unsupported platforms or remaining acceptance gaps are stated.

## Safety and compatibility

- [ ] Mutagen remains the source of truth; existing sessions are not silently rewritten.
- [ ] Mutating operations retain exact-ID targeting, preview, confirmation, cancellation, and recovery behavior as applicable.
- [ ] No secrets, private keys, personal data, generated binaries, or unrelated workspace changes included.

## User experience and documentation

- [ ] English and Czech copy/help updated where needed.
- [ ] Screenshots regenerated from the real demo UI and manually inspected for visible changes.
- [ ] README, docs, changelog, and architecture/ADR updated when applicable.
