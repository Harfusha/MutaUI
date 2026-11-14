# Action planner

`mutaui.services.action_planner` is the shared planning boundary for native
operations. It maps known actions to fixed risk tiers: R0 is read-only, R1 is
low-risk session control, R2 changes or replaces session configuration, and R3
can destroy or overwrite content or run project hooks. Unknown actions are
rejected.

Every mutating plan requires exact target identifiers, an argument preview, a
current preflight fingerprint, stable preconditions, and a bounded target lock.
Broad `--all` targeting is rejected. Consent rechecks the captured fingerprint;
R3 additionally requires the exact `APPLY <target IDs>` phrase and the same
backup choice shown in the preview. A changed fingerprint, expiry, cancellation,
or post-check target mismatch closes the plan and releases its locks.

The planner records planned, consented, cancelled, stale, rejected, and finished
decisions in a bounded in-memory audit and never executes a command. Single and
explicitly confirmed bulk sync/forward pause, resume, flush, reset, and terminate
now pass through this boundary. Session creation also uses an exact argument
preview and operation digest; `one-way-replica` requires a confirmed recoverable
destination backup plus the exact typed phrase. The CLI adapter compares a
reviewed existing-session fingerprint with a fresh native listing immediately
before execution, identifies one created session by exact new ID, and checks
targets afterward. Uncertain results close plans as stale. Live status and
transfer counters are excluded from existing-session fingerprints, while
configuration, endpoints, labels, pause state, and unknown fields remain covered.

Daemon start/stop/register/unregister use the same boundary with a stable
per-user target derived from the selected executable. The adapter probes with
`sync list` while autostart is disabled, fingerprints registration state,
rechecks immediately before execution, and verifies the daemon or registration
afterward. Stop remains R3 and requires the exact typed confirmation. A failed
native daemon probe is treated as unavailable for start/stop; registration is
offered only where the platform reports support.

Project pause/resume/flush/reset/start/terminate and named `project run` actions
also share the planner. Their target is the exact native project file identity;
start, terminate, and shell commands require typed R3 confirmation. Termination
post-checks that declared project session names are absent. The project YAML
dialog still shows native hooks and requires separate shell-consent for them.

The GUI action confirmation is the operator consent. The planner's argument
preview is retained in its in-memory audit. Project-native changes still need
migration through the shared boundary; controlled replacement
uses its own consented R2 plan. This document does not claim universal
enforcement or durable audit storage.
