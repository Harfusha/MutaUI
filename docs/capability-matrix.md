# Platform and version capability policy

| Capability | Windows | macOS | Linux | Evidence policy |
|---|---|---|---|---|
| GUI runtime | Existing workflow/build | Not verified | Not verified | Mark supported only after native CI and packaged smoke |
| Mutagen CLI | Discover installed binary and query `version`/`--help` | Same | Same | Runtime capability detection; do not infer from OS |
| Daemon registration | Gate on installed CLI/platform | Gate on installed CLI/platform | Native user-controlled integration only | Never fake Linux `daemon register` |
| Forward transports | Capability-gate TCP/npipe | Capability-gate TCP/Unix | Capability-gate TCP/Unix | Exact installed CLI help is authoritative |
| Packaging | Portable and single-file workflow exists | Not verified | Not verified | Clean-system packaged smoke required |

## Version strategy

- Keep dependency declarations in `pyproject.toml`, update `uv.lock`, and regenerate the pinned `requirements*.txt` compatibility exports. Review upgrades only after clean package smoke.
- PySide6 Essentials 6.8.3 is the current repository pin. `docs/TESTING.md` records later Qt pins that failed frozen import on the tested host.
- Do not pin Mutagen behavior to a remembered “latest” version. Discover installed version and supported commands/options at runtime.
- Establish a tested Mutagen compatibility matrix with current and previous supported releases before advertising compatibility.
- Unknown future native keys remain visible and preserved; unsupported actions fail closed with a reason.
