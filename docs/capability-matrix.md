# Platform and version capability policy

| Capability | Windows | macOS | Linux | Evidence policy |
|---|---|---|---|---|
| GUI runtime | CI packaged self-test passed; clean-user install/upgrade not verified | macOS ARM CI packaged self-test passed; signed Gatekeeper install not verified | Ubuntu 26.04 x86-64 CI package self-tests passed; desktop/file-manager session not verified | CI evidence is not a clean-user support guarantee |
| Mutagen CLI | Discover installed binary and query `version`/`--help` | Same | Same | Runtime capability detection; do not infer from OS |
| Daemon registration | Gate on installed CLI/platform | Gate on installed CLI/platform | Native user-controlled integration only | Never fake Linux `daemon register` |
| Forward transports | Capability-gate TCP/npipe | Capability-gate TCP/Unix | Capability-gate TCP/Unix | Exact installed CLI help is authoritative |
| Packaging | Portable and single-file workflow; packaged self-test passed in CI | ARM CI disk image build and verification passed; signing/notarization remains open | AppImage and DEB built; AppImage self-test and installed DEB self-test passed on Ubuntu 26.04 x86-64 | Clean-user install and supported-distro matrix remain required |

## Candidate Mutagen CLI matrix (2026-11-17)

The official stable release list identifies v0.18.1 as latest and v0.18.0 as the immediately preceding stable release. These are the candidate test pair only; this table does not claim either version is supported by MutaUI.

| Candidate | Role | CLI / daemon smoke | Sync and forwarding integration | Result |
|---|---|---|---|---|
| v0.18.1 | Latest stable | Windows x64 passed: version, help, isolated daemon start/stop, empty sync/forward lists; `daemon register --help` available | Not run; local SSH server absent | SHA256SUMS matched `76f8223d5e6b607efdd9516473669ae5492e4f142887352d59bc6934d1f07a2d`; Authenticode `NotSigned` |
| v0.18.0 | Previous stable | Windows x64 passed: version, help, isolated daemon start/stop, empty sync/forward lists; `daemon register --help` available | Not run; local SSH server absent | SHA256SUMS matched `438405c73c26078120472612613ad97d9dc8e318a0656ab88eb71ff4b0ca4eee`; Authenticode `NotSigned` |

The release `SHA256SUMS` manifests were downloaded over HTTPS and matched; their GPG signatures were not verified because GPG is not installed. Targeted help comparison found identical long-option sets for v0.18.1/v0.18.0: 46 `sync create`, 18 `forward create`, and 1 `daemon register`; all help commands exited 0. No register/create operation, live SSH/SFTP session, or cross-platform native check was performed. Acceptance still requires sync/forward scenarios and native checks on each supported OS. Mutagen documents that the daemon must be restarted after upgrades because its command API is not stable.

Sources: [v0.18.1 release](https://github.com/mutagen-io/mutagen/releases/tag/v0.18.1), [v0.18.0 release](https://github.com/mutagen-io/mutagen/releases/tag/v0.18.0), [daemon upgrade guidance](https://mutagen.io/documentation/introduction/daemon/).

## Version strategy

- Keep dependency declarations in `pyproject.toml`, update `uv.lock`, and regenerate the pinned `requirements*.txt` compatibility exports. Review upgrades only after clean package smoke.
- PySide6 Essentials 6.8.3 is the current repository pin. `docs/TESTING.md` records later Qt pins that failed frozen import on the tested host.
- Do not pin Mutagen behavior to a remembered “latest” version. Discover installed version and supported commands/options at runtime.
- Establish a tested Mutagen compatibility matrix with current and previous supported releases before advertising compatibility.
- Unknown future native keys remain visible and preserved; unsupported actions fail closed with a reason.
