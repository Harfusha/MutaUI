# MutaUI integration specification adoption

Status: accepted for implementation by the user's explicit request on 2026-11-12.

## Authoritative requirements

Implement all requirements in these supplied documents:

- `C:/Users/Adam/Downloads/MutaUI_MASTER_INTEGRATION_PLAN.md`
- `C:/Users/Adam/Downloads/MutaUI_INTEGRACNI_PLAN_CZ.md`

The master plan defines product architecture, E01–E22, AC-001…AC-040, PR-001…PR-041 and delivery gates G0–G4. The Czech plan gives the matching implementation contract, safety rules, tests, documentation and release expectations. Neither source document is evidence that a requirement is already implemented. Preserve their full acceptance conditions; use `docs/implementation-inventory.md` only as a living map.

## Product contract

Build a cross-platform desktop control center for the installed Mutagen CLI and daemon. Basic and Advanced are views over one state model and safety policy. Mutagen remains the source of truth for sessions, sync and forwarding. Never create a parallel engine or hidden agent. Discover native options by installed version and platform; preserve unknown configuration; show unsupported options with reasons. Missing metrics remain unknown.

All mutations require explicit targets, capability and safety checks, read-only preflight, preview, consent, bounded execution, authoritative post-check and audit. R2/R3 actions require preview; destructive R3 actions also require exact-target confirmation and backup. Session configuration is creation-time locked. Existing sessions require a lossless, validated replacement plan; unknown fields or uncertain preconditions block automation. Hooks require informed consent. No host-key bypass, secret export, unsolicited telemetry, auto-update, or release publication.

## Delivery order

Execute PR-001…PR-041 in the source plan's phases and gates. Start with Phase 0 stabilization, measurements and CI. Then settings/UI, profiles/projects/diagnostics, conflicts/reconfiguration, and platform/release quality. Make each slice independently testable and document verified evidence, open blockers and unsupported platforms. Do not claim production readiness until G4 and AC-001…AC-040 pass.

## Acceptance

Every source requirement maps to existing verified behavior, an implementation task, or an explicit evidence-backed blocker. Required tests, safety checks, documentation, translations, accessibility, benchmarks, platform builds, packaged self-tests and release evidence must pass before their corresponding gate is marked done. No destructive user session or release action is authorized by this specification.
