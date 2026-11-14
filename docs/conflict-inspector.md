# Conflict Inspector

Open **Diagnostics → Conflict Inspector** to review conflicts from the latest
successful native `sync list` snapshot. The view groups and sorts conflicts by
session and relative path, supports text and session filters, and shows the exact
session identifier plus the reported ALPHA/BETA changes. Mutagen may truncate
large conflict lists; MutaUI reports the native excluded count when present.

Change kinds come only from native `old`/`new` fields. Missing fields remain
unknown. The inspector does not infer which side should win, fetch remote files,
modify files, or resolve conflicts. Open-path buttons appear only for an
existing local path contained within that endpoint root. Paths that traverse
outside the root or resolve through an escaping symlink are refused.

Conflict metadata is stale when the underlying native snapshot is stale or has
no successful observation time. In that case, the inspector shows no conflict
rows rather than presenting old data as current. Remote inspection and manual
resolution belong to later stages and remain unavailable here.
