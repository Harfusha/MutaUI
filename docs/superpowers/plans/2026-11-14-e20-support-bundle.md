# E20 Support Bundle Implementation Plan

> **For agentic workers:** Follow this plan in the current owned checkout. Keep the existing safe export format stable.

**Goal:** Provide a local-only Support Bundle flow with a safe report, a previewed and consent-gated full snapshot, bounded session-log snapshots with independent sensitive-detail controls, and a local runtime self-check.

**Architecture:** Reuse `safe_diagnostic_report`, the existing full snapshot payload, `HistoryStore.events`, and the bounded `TrackedLogLines` ring. Add a small Qt dialog that selects the export, previews the selected data class, and defaults every raw detail control off. All exports write only to a user-selected local file; there is no upload path.

**Tech Stack:** Python 3.12, PySide6, pytest, existing JSON and SQLite history interfaces.

**Spec:** `C:\Users\Adam\Downloads\MutaUI_MASTER_INTEGRATION_PLAN.md` §E20 and `C:\Users\Adam\Downloads\MutaUI_INTEGRACNI_PLAN_CZ.md` E20.

## Global Constraints

- Safe report remains a strict allowlist and excludes paths, hosts, usernames, keys, raw errors, and raw log lines.
- Full snapshots and raw log details require explicit consent after a visible preview.
- Log snapshots are bounded to the existing local event and log buffers.
- Never upload or start a remote logging process.
- Preserve the current safe and full JSON schemas unless tests show a required correction.

## Review Focus

- Sensitive data accidentally enters the safe report or a default log snapshot.
- A cancel path writes a file or exports stale/empty data as authoritative.
- Log snapshot bounds, JSON encoding, and output errors are handled.
- The dialog remains understandable in English and Czech.

## Tasks

- [x] Add failing dialog and export-flow tests for safe defaults, full-snapshot preview/consent, independent event-message and monitored-log toggles, and cancellation.
- [x] Implement the Support Bundle dialog and route its choices into the existing safe/full exports plus a bounded local session-log JSON export.
- [x] Add a no-write local self-check for app/settings paths, SQLite integrity, Python/Qt versions, and read-only Mutagen CLI version.
- [x] Update Session Doctor documentation and acceptance traceability with exact safety controls and remaining runtime evidence.
- [x] Run focused Qt/privacy tests, formatting/lint, and diff checks; keep the real Mutagen gate separate when the CLI is unavailable.
