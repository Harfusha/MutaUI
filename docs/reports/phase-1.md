# Phase 1 progress — UX and configuration

Date: 2026-11-14. Baseline: repository `master`, commit `9b5718a5f4dec6fe8f3a93d3f5f2426941e56c25` (v8.2). Environment: Python 3.12.10, PySide6 6.8.3, pytest 9.2.0, Coverage.py 7.17.3, checksum-verified Mutagen CLI 0.18.1.

## Scope delivered

- **PR-006 (Page shell and lazy routing):** Refactored navigation in `src/mutaui/ui/page_shell.py` and `app.py`. Sidebar and header share route metadata; heavy pages (Settings, Monitoring, Action History) load lazily on first access.
- **PR-007 (Basic/Advanced mode and theming):** Implemented in `src/mutaui/ui/preferences.py`. Switching modes preserves in-progress drafts across settings, wizards, alerts, and history. Basic mode hides complex settings without resetting them. Theming supports System, Light, and Dark palettes with high-contrast text. EN/CS catalog skeleton wired.
- **PR-008 (Onboarding wizard and CLI discovery):** Implemented in `src/mutaui/ui/onboarding.py`. Safely queries `mutagen version` and `mutagen <command> --help` without running daemon autostart. Detects host architecture and PE/ELF/Mach-O binary architectures; tests local sync in an isolated `MUTAGEN_DATA_DIRECTORY` with exact-ID cleanup.
- **PR-009 (Settings registry and documentation generator):** Implemented in `src/mutaui/ui/settings_registry.py` and `scripts/generate_settings_reference.py`. Central typed registry defines every setting, key, group, default, platform availability, recommended values, performance/security effects, Mutagen CLI mapping, and bilingual EN/CS help text. Generates `docs/settings-reference.md` and `docs/reference/configuration-fields.md`.
- **PR-010 (Lossless YAML round-trip reader and validator):** Implemented in `src/mutaui/adapters/yaml_config.py`. Uses `ruamel.yaml` to preserve comments, key order, quotes, indentation, and unknown fields. Rejects duplicate keys, non-mapping roots, unsafe Python tags, and oversized payloads.
- **PR-011 (Global Mutagen config editor):** Implemented in `src/mutaui/adapters/yaml_config_editor.py`. Manages `~/.mutagen.yml` with provenance tracking, structured diff preview, atomic writes via flushed temporary files, timestamped backups, and file-hash race detection (offering reload, manual merge baseline, or cancel upon external edit). Invalid source opens read-only.
- **PR-012 (Native sync session configuration editor):** Implemented in `sync_configuration.py`. Displays read-only active session configuration and validated local proposals. Supports common and ALPHA/BETA-specific parameters (`mode`, `watch`, `scan`, `probe`, `stage`, `symlink`, `permissions`, `limits`). Distinguishes inherited global defaults from explicit CLI overrides. Existing sessions remain untouched.
- **PR-013 (Native forwarding configuration editor):** Implemented in `forward_configuration.py`. Displays source and destination socket configuration. Validates local proposals for socket owner, group, mode, and overwrite with platform capability gating (Unix sockets on POSIX, named pipes on Windows). Active forwarding sessions remain unmodified.
- **PR-014 (Basic/Advanced Sync and Forward wizards):** Implemented in `app.py` (`SessionDialog`, `ForwardDialog`). Generates exact argv argument previews without shell interpolation. Basic wizard limits options to safe modes; Advanced exposes all modes with impact warnings. Validates public bind addresses and confirms R3 destructive modes (`one-way-replica`).

## Verification evidence

- `tests/test_onboarding.py`: 23 passed (PE/ELF/Mach-O detection, isolated smoke, missing CLI handling, timeout cleanup).
- `tests/test_ui_preferences.py`: 18 passed (theme resolution, language fallback, mode switching, catalog coverage).
- `tests/test_yaml_config.py`: 9 passed (comment preservation, duplicate key rejection, tag safety, BOM detection).
- `tests/test_yaml_config_editor.py`: 21 passed (atomic replace, backup creation, race detection, merge/reload/cancel).
- `tests/test_sync_configuration.py` and `tests/test_effective_configuration.py`: 24 passed (CLI overrides, ignore appending, provenance).
- `tests/test_forward_configuration.py`: 12 passed (socket permissions, platform gating, bind address warnings).
- `tests/test_mainwindow_flows.py`: wizard drafts, mode preservation, public bind confirmation, and replica phrase gates verified.
- Settings reference freshness check (`python scripts/generate_settings_reference.py --check`) passed.

## Gate G1 disposition

- Status: **Verified locally on Windows x64; cross-platform hosted evidence open.**
- Verification criteria:
  - Reversible settings and configurations: 100% verified.
  - Round-trip YAML with comments/unknowns preserved: 100% verified.
  - Exact CLI command preview without shell strings: 100% verified.
  - Existing session configurations read-only; proposals kept separate: 100% verified.
  - Multi-platform configuration tests pass locally: 100% verified.
