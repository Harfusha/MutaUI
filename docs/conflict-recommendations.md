# Advisory conflict rules

PR-032 provides a bounded pure policy model for operator-authored rules. Rules
name one exact conflict-relative path, one preferred side, and a reason. Duplicate
paths, globs, traversal, absolute paths, malformed IDs and more than 20 rules are
rejected.

Rules persist in versioned `conflict-recommendations.json` beside app settings.
The default policy is disabled. Corrupt, unknown-version, or invalid documents
fail closed and are never silently rewritten. The Conflict Inspector exposes a
rule manager and displays an advisory only for an exact path match. Each advisory
shows rule ID, exact session ID and path, preferred side, and operator reason.
It never calls a resolver, writes a file, changes session mode, or chooses a side
automatically. Every choice remains an operator action outside this UI.

Acceptance: round-trip storage; missing file defaults disabled; malformed or
unknown documents are rejected without changing bytes; editor enforces the pure
policy limits; matching advisory is visible only after explicit opt-in; no
mutation/resolver method is reachable from the feature. Cross-platform beta
review remains open.
