# Session health tracking

Health tracking consumes fresh per-session snapshots and confirmed Doctor
findings. It keeps monotonic state transitions, consecutive confirmed error
streaks, reconnect counts, incident IDs, last healthy observation and native
list-command durations in memory for the current app run. Duplicate snapshot
timestamps are idempotent. Stale snapshots never count as recovery or failure.

The default mode is **Monitor only**. **Assisted** can recommend a manual next
step after three confirmed consecutive failures and at least 120 seconds. A
long scan, an external pause, or a recent sleep/wake/network change resets the
streak; MutaUI never resumes an intentionally paused session. The application
uses Qt's optional network reachability backend when available and treats a
snapshot gap over three minutes as a possible wake, then applies the configured
grace period. Network reachability is an OS signal, not a preflight or proof
that a Mutagen endpoint is reachable.

Auto-safe records eligibility only for the allowlisted `refresh_status` action
on one exact session. Mutagen-changing actions such as pause, resume, flush,
reset, terminate, and daemon stop are rejected. Every decision records the
target, action, incident, result, and reason in a bounded in-memory audit. Stable preconditions,
three confirmed failures, the elapsed threshold, a 60 second cooldown, at most
two attempts in the configured window (30 minutes by default), and an open
circuit breaker are required. No recovery executor is connected, so the gate
cannot run commands or mutate sessions or files. The app's status refresh lists
all sync and forward sessions; it is not an exact-session backend and cannot
serve as per-session Auto-safe execution. No recovery runs on opening a page.
Defaults and thresholds are configurable under Settings
→ Alerts / Health: failure count, elapsed duration, cooldown, attempt limit and
window, and sleep/network grace.

PR-022 rules are unit-tested with injected monotonic times and no sleeps.
Physical sleep/resume and OS network-backend behavior remain unverified on the
supported platform matrix.
