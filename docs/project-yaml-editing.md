# Project owned YAML editing

PR-028 adds an in-place editor for an existing `mutagen.yml` or
`mutagen.yaml`. It validates the proposed project structure, shows a unified
diff, retains comments and unknown YAML values through the round-trip parser,
requires a checked consent control and a second confirmation, rechecks the
source hash, writes a backup, and records a local JSONL audit event.

Editing the file does not terminate or recreate sessions and does not execute
project hooks. After a successful edit, the project viewer reloads the source;
the operator can separately review a native project action to apply changes.
This preserves project ownership and keeps the edit and native action as
separate explicit operations.

## Concurrency and External Changes

When an external process modifies the configuration file while it is being edited in MutaUI:

- Save operations verify the source hash against the baseline and detect the collision.
- The editor offers explicit choices:
  - **Reload external changes**: Discards the editor draft and reloads the current disk file.
  - **Compare with draft**: Displays a unified diff comparing disk changes with the local draft.
  - **Keep draft and merge manually**: Adopts the external version as the new comparison baseline while retaining current draft text for manual editing.
  - **Cancel**: Leaves the draft in the editor without modifying disk files or baseline state.
- Save preflight explicitly discloses the target path, backup location, and explains that global configuration affects newly created sessions while running sessions continue unaffected.

Tests use temporary YAML files and do not invoke Mutagen. Installed CLI behavior,
cross platform filesystem guarantees, external edits during real project actions,
and the full injected fault matrix remain release acceptance work.
