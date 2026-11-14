# E22 Performance Tuning Assistant

## Goal

Give Advanced users evidence-based, optional guidance for Mutagen sync settings without inventing benchmark results or changing a live session.

## Behavior

- Analyze the selected native sync snapshot and inspect only reported local endpoint roots. Never recurse through a root, inspect a remote endpoint, or touch UNC/network-share paths.
- Use Mutagen's documented defaults and qualitative effects. Show entry count as unknown unless the snapshot supplies a count; explain that full scans add work for very large roots.
- Warn when forced polling is faster than Mutagen's documented 10-second default, when a reported local root is a symlink, missing, unreadable, or unwritable for a receiving endpoint, and when the configured Mutagen staging directory and a local root are on different filesystems.
- Recommend portable watching and accelerated scanning when a non-`no-watch` session is using forced high-frequency polling or full scanning. State that endpoint capabilities still need verification. Recommend endpoint-local neighboring staging only when a local filesystem mismatch is observed.
- Keep impact qualitative and explicitly unmeasured. Link guidance to the official Mutagen watching, scanning, and staging documentation.
- Applying a suggestion only fills the existing local replacement proposal draft. Saving remains local. Applying to a live session remains a separate reviewed replacement and must be described as replacing/recreating the session.

## Non-goals

- No automatic changes, CLI commands, remote probes, filesystem traversal, telemetry, or made-up speed/CPU/entry metrics.
- No changes to GUI polling cadence, which remains separate from native Mutagen watch/scan settings.

## Acceptance

- Tests cover unknown or malformed snapshots, high-frequency polling, no-watch preservation, full-scan suggestions, local path warnings, cross-filesystem staging, and no filesystem traversal.
- Qt flow proves recommendations are optional, feed only the existing proposal table, and never invoke replacement directly.
- English and Czech copy explain qualitative impact and replacement behavior.
