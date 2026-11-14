# Architecture and command flow

MutaUI is a desktop client for the locally installed Mutagen CLI. Mutagen owns sync and forwarding sessions; MutaUI reads and invokes the native CLI and stores its own preferences/history separately.

```text
Qt UI (Basic / Advanced)
  ├─ application services (validation, preview, risk gates)
  │    └─ MutagenClient (argv, exact IDs, shell disabled)
  │         └─ local Mutagen CLI → local Mutagen daemon
  │              ├─ local endpoints
  │              └─ Mutagen SSH transport → remote agent → remote endpoints
  ├─ local application preferences and profiles
  ├─ SQLite history (separate writer)
  └─ explicit remote-inspection request → local OpenSSH → approved remote paths
```

## Data and command boundaries

- The GUI does not implement a second synchronization engine. The local Mutagen CLI and daemon remain authoritative for sessions and transfers.
- Normal session inventory uses the local CLI. Host grouping is string-based; it does not open SSH, DNS, or HTTP connections.
- Mutagen SSH transport and MutaUI remote inspection are separate paths. Remote inspection runs only after an explicit user request and is constrained by its own path checks.
- Mutating operations must retain a reviewable command preview, exact target identity, applicable risk confirmation, and outcome verification. Existing session settings are read-only until the user reviews a replacement proposal.
- Application preferences, connection profiles, ignore presets, and SQLite history are local MutaUI data. They do not become Mutagen session state.
- GUI status polling and performance sampling are independent from Mutagen's file watching and sync cadence.

See the [architecture decisions](adr/0001-retain-pyside6.md), [capability policy](capability-matrix.md), and [testing limits](TESTING.md) for design rationale and evidence boundaries. The repository-root `ARCHITECTURE.md` records module-level implementation details.
