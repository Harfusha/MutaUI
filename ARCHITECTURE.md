# Architecture

See the rendered [architecture diagram and data flow](docs/architecture.md).

**Data:** The local `MutagenClient` calls only the native CLI (`sync list --template`, `forward list --template`). Exported native endpoint models are used for both sides of a sync. Host grouping is string-based and does not open its own SSH, DNS, or HTTP connections.

**Performance:** `QThreadPool` handles CLI calls and process measurements; history uses a separate SQLite writer, history cache, and cached graph geometry. `AdaptivePolling` changes only the GUI status refresh interval in response to detected changes or Mutagen's current phase. It does not change the frequency of actual sync cycles.

**Native watch profiles:** A whitelist of `sync create` parameters: `portable`, `force-poll`, `no-watch`, and `watch-polling-interval`. They cannot change running sessions. Existing sync settings show native values and local proposed replacements; proposals are stored in MutaUI preferences and never mutate running sessions. Capability status remains unverified until checked against the installed CLI.

**Forwarding settings:** Native source/destination socket values are read-only. MutaUI can retain validated socket overwrite, owner, group and permission proposals locally; no running forward is modified. CLI, endpoint and platform capability checks are required before replacement.

**Connection profiles:** Versioned `connection-profiles.json` is separate from application and Mutagen configuration. It stores reusable endpoint pairs, validated defaults, tags and favorites. Corrupt or unsupported profile data is retained unchanged; duplicate profiles receive new IDs.

**SSH profiles:** `ssh_profiles.py` reads OpenSSH config and bounded includes, lists concrete aliases, and runs local `ssh -G` only on request. The user-invoked connection test uses `BatchMode=yes` and `StrictHostKeyChecking=yes`; the manager does not write SSH config, known-hosts, or key files.

**Portable data:** `portable_bundle.py` uses a versioned checksummed JSON envelope, explicit profile import preview, stable-ID/semantic duplicate checks, and per-file atomic writes with backups. It exports only an allowlist of preferences; machine paths are redacted by default, and executable paths, notes, Mutagen state and history stay local. Legacy settings migration keeps exact source bytes and supports validated rollback; SQLite history is not touched.

**Ignore presets:** `ignore_presets.py` stores ordered, versioned local rules with atomic replacement, backups and stale-write rejection. `.gitignore`/`.dockerignore` conversion is bounded and preview-only until the user applies supported rows to a new sync draft; possible negation overrides are called out. Portable imports validate preset structure and expose explicit conflict choices. Relative-path matching is advisory and not verified against a live Mutagen CLI in this environment.

**Native projects:** `mutaui.projects.native_project` reads existing `mutagen.yml` files through the round-trip YAML adapter and keeps local project references in a separate versioned store. The viewer shows sync/forward declarations, merged default/session settings, hooks, custom commands, source hash, and debounced external-change diffs. New project files use validated create-if-absent writes. `project_actions.py` previews exact CLI arguments, rechecks the source hash, gates hooks/custom commands on explicit consent, and writes a local intent/result audit. Runtime project health, lock state, and CLI operation remain unverified without the installed CLI.

**Qt:** Session details and settings use `QScrollArea` and layouts with a minimum size based on their contents. The circular indicator draws small text in pixel units. Tables have specific empty states. The GUI smoke test checks sync counts against the selected server and does not assume a fixed group order.

**Native YAML:** `mutaui.adapters.yaml_config` reads bounded UTF-8 Mutagen YAML with ruamel.yaml's safe round-trip loader. It preserves the original bytes, hash, encoding and newline metadata, retains comments and unknown fields in the in-memory document, rejects duplicate keys and non-mapping roots, and renders previews in memory only. This reader does not write configuration files.

**EXE:** Build scripts run unit tests and the Qt smoke test on Windows before the PyInstaller build. Python/PySide6 is not needed to run the finished EXE; the Mutagen CLI remains an external dependency.
