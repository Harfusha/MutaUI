# Manual single-file conflict resolution

The staged PR-031 service supports only one regular local file on each side of
a local/local sync. It requires a native conflict digest, exact conflict path,
content hashes, one selected winner, a consented R3 `ActionPlan`, exact typed
session confirmation, a backup directory outside both sync roots, and an audit
file. Before replacement it rechecks both file hashes and native conflict
freshness, backs up both copies, records a manifest, and atomically replaces only
the losing file. It then asks the caller to flush and verify native convergence.
If verification fails, it makes a best-effort restore and reports native state
as uncertain.

`MANUAL_RESOLUTION_ENABLED` remains **false**. No resolver button is exposed.
The injected tests cover backups, freshness, single-file scope and rollback, but
the plan's full cross-platform injected-fault suite and real Mutagen flush /
convergence acceptance have not passed. Remote endpoints, directory conflicts,
deletion, mass resolution, and replica mode remain unsupported. Do not enable
the feature before those release gates pass.
