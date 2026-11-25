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

## Resolution Outcomes and Manual Recovery

Every resolution attempt classifies its final state into one of four distinct outcomes:

1. **Preview Only / Stopped Before Replacement**: Backups may be prepared, but no file modifications occurred on either endpoint.
2. **Verified Resolution**: File replacement succeeded, native flush executed, and convergence was confirmed by a fresh read.
3. **Verified Rollback**: Replacement or flush failed; the original file was restored from backup and verified against pre-replacement SHA-256.
4. **Uncertain State**: Replacement occurred but convergence failed, and automatic rollback could not verify restored content.

### Manual Recovery Procedure

When automated recovery fails or leaves native state uncertain:

1. Locate the backup folder referenced in the receipt: `mutaui-conflict-<hex>/` outside the sync roots.
2. Inspect `manifest.json` for recorded SHA-256 digests and relative path.
3. If necessary, restore the desired version by copying `alpha.backup` or `beta.backup` back to the respective endpoint.
4. Run `mutagen sync flush <session>` and check status with `mutagen sync list <session>`.
