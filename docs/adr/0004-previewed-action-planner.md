# ADR-0004: Mutations use previewed action plans

Status: accepted as the required target architecture; implementation is incremental.

Every mutation follows typed request, capability check, safety policy, read-only preflight, explicit plan and risk tier, human preview/consent, bounded execution, authoritative refresh and audit. R2/R3 actions require preview; R3 also requires exact-target confirmation and backup. Unknown preconditions fail closed.
