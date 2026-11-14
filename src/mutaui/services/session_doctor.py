"""Deterministic, offline diagnosis for typed Mutagen snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from mutaui.domain.models import DiagnosticIssue, SessionSnapshot

FRESHNESS_SECONDS = 60
HIGH_CPU_PERCENT = 90.0
SYNC_HELP = "https://mutagen.io/documentation/synchronization/"
FORWARD_HELP = "https://mutagen.io/documentation/forwarding/"
DAEMON_HELP = "https://mutagen.io/documentation/introduction/daemon/"


@dataclass(frozen=True, slots=True)
class SessionDoctorContext:
    cli_available: bool
    daemon_running: bool | None
    sync_observed_at: datetime | None
    forward_observed_at: datetime | None
    sessions: tuple[SessionSnapshot, ...] = ()
    version: str | None = None
    snapshot_error: str = ""
    sessions_stale: bool = False
    cpu_percent: float | None = None
    resource_observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SessionDoctorReport:
    issues: tuple[DiagnosticIssue, ...]
    authoritative: bool
    generated_at: datetime
    session_count: int
    stale_kinds: tuple[str, ...]

    @property
    def issue_count(self) -> int:
        return len(self.issues)


def _recent(value: datetime | None, now: datetime, max_age: int) -> bool:
    if value is None:
        return False
    age = (now - value).total_seconds()
    return 0 <= age <= max_age


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    return 0


def _text(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key}: {item}" for key, item in value.items())[:1000]
    return str(value)[:1000]


def _error_code(text: str, *, kind: str, endpoint_name: str = "") -> str | None:
    value = text.casefold()
    if any(term in value for term in ("authentication failed", "unauthorized", "publickey")) or (
        "permission denied" in value and ("ssh" in value or kind == "ssh")
    ):
        return "ssh_authentication"
    if any(term in value for term in ("unknown host", "no such host", "host key", "known_hosts")):
        return "ssh_host_trust"
    if any(
        term in value
        for term in (
            "root is missing",
            "root missing",
            "root is empty",
            "root changed type",
            "deleted root",
            "halted: empty root",
            "halted: root type change",
        )
    ):
        return "root_problem"
    if "symlink" in value:
        return "symlink_problem"
    if any(term in value for term in ("permission", "ownership", "operation not permitted")):
        return "permission_problem"
    if any(term in value for term in ("stage", "staging", "temporary directory")):
        return "staging_problem"
    if "transition" in value:
        return "transition_problem"
    if "scan" in value:
        return "scan_problem"
    if kind == "forward" and endpoint_name and value.strip():
        return (
            "forward_source_problem" if endpoint_name == "source" else "forward_destination_problem"
        )
    return None


def _issue_copy(code: str) -> tuple[str, str, str]:
    copy = {
        "cli_missing": (
            "Mutagen CLI is unavailable.",
            "Choose or install the supported Mutagen CLI, then refresh.",
            DAEMON_HELP,
        ),
        "daemon_offline": (
            "The local Mutagen daemon did not answer.",
            "Check the Mutagen installation and daemon status. MutaUI did not start it.",
            DAEMON_HELP,
        ),
        "snapshot_stale": (
            "Current session state is unknown because no recent complete snapshot is available.",
            "Refresh Mutagen status before acting on session details.",
            DAEMON_HELP,
        ),
        "ssh_authentication": (
            "Mutagen reports an SSH authentication or permission failure.",
            "Check the selected SSH identity and remote account permissions.",
            SYNC_HELP,
        ),
        "ssh_host_trust": (
            "Mutagen reports a host or host-key resolution problem.",
            "Verify the host name and review the host key through OpenSSH.",
            SYNC_HELP,
        ),
        "ssh_disconnected": (
            "A sync endpoint is disconnected.",
            "Inspect the endpoint and its latest Mutagen error.",
            SYNC_HELP,
        ),
        "root_problem": (
            "A synchronization root may be missing, empty, or a different file type.",
            "Check both roots and confirm that each still points to the intended directory.",
            SYNC_HELP,
        ),
        "scan_problem": (
            "Mutagen reported a filesystem scan problem.",
            "Inspect the scan evidence and the affected filesystem path.",
            SYNC_HELP,
        ),
        "transition_problem": (
            "Mutagen reported a file transition problem.",
            "Inspect the transition evidence before changing files or configuration.",
            SYNC_HELP,
        ),
        "conflicts": (
            "Mutagen reports file conflicts, including excluded conflicts.",
            "Review conflict details before choosing any resolution.",
            SYNC_HELP,
        ),
        "permission_problem": (
            "Mutagen reported a permissions or ownership problem.",
            "Check access on the affected endpoint; do not change permissions automatically.",
            SYNC_HELP,
        ),
        "symlink_problem": (
            "Mutagen reported a symbolic-link problem.",
            "Review the link target and the configured symbolic-link mode.",
            SYNC_HELP,
        ),
        "staging_problem": (
            "Mutagen reported a file-staging problem.",
            "Check free space and staging configuration on the affected endpoint.",
            SYNC_HELP,
        ),
        "forward_source_problem": (
            "The forwarding source could not bind or connect.",
            "Check the local source address, port, and socket availability.",
            FORWARD_HELP,
        ),
        "forward_destination_problem": (
            "The forwarding destination could not connect.",
            "Check the destination endpoint and remote service availability.",
            FORWARD_HELP,
        ),
        "session_error": (
            "Mutagen reports a session error.",
            "Inspect the session's native error and endpoint details.",
            SYNC_HELP,
        ),
        "intentional_pause": (
            "This session is intentionally paused.",
            "Resume only if you want Mutagen to continue the session.",
            SYNC_HELP,
        ),
        "manual_mode": (
            "This session uses manual synchronization mode.",
            "Manual synchronization is intentional and is not an error.",
            SYNC_HELP,
        ),
        "high_cpu": (
            "Recent Mutagen process CPU measurement is high.",
            "Compare with active scans and synchronization before changing settings.",
            SYNC_HELP,
        ),
    }
    return copy.get(
        code, ("Mutagen reported a session issue.", "Review the native evidence.", SYNC_HELP)
    )


def diagnose_sessions(
    context: SessionDoctorContext,
    *,
    now: datetime | None = None,
    freshness_seconds: int = FRESHNESS_SECONDS,
) -> SessionDoctorReport:
    generated_at = now or datetime.now(UTC)
    stale_kinds = tuple(
        kind
        for kind, observed_at in (
            ("sync", context.sync_observed_at),
            ("forward", context.forward_observed_at),
        )
        if not _recent(observed_at, generated_at, freshness_seconds)
    )
    authoritative = (
        context.cli_available
        and context.daemon_running is True
        and not context.sessions_stale
        and not stale_kinds
    )
    issues: list[DiagnosticIssue] = []
    seen: set[tuple[str, str | None]] = set()

    def add(
        code: str,
        severity: str,
        *,
        session: SessionSnapshot | None = None,
        evidence: tuple[object, ...] = (),
        observed_at: datetime | None = None,
        certainty: str = "confirmed",
        detail: str = "",
    ) -> None:
        identifier = session.identity.identifier if session is not None else None
        key = code, identifier
        if key in seen:
            return
        seen.add(key)
        explanation, suggestion, article = _issue_copy(code)
        current_certainty = certainty
        if session is not None and (
            not _recent(session.measured_at, generated_at, freshness_seconds)
            or session.stale_reason is not None
        ):
            current_certainty = "suspected"
        issues.append(
            DiagnosticIssue(
                code,
                severity,
                0.98 if current_certainty == "confirmed" else 0.6,
                evidence,
                explanation,
                (suggestion,),
                False,
                context.version,
                current_certainty,  # type: ignore[arg-type]
                explanation,
                detail,
                article,
                identifier,
                observed_at or (session.measured_at if session is not None else generated_at),
            )
        )

    if not context.cli_available:
        add(
            "cli_missing",
            "error",
            evidence=({"source": "MutaUI settings", "value": "Mutagen path missing"},),
        )
    elif context.daemon_running is False:
        add(
            "daemon_offline",
            "error",
            evidence=(
                {"source": "Mutagen CLI", "value": context.snapshot_error or "Daemon unavailable"},
            ),
        )
    if stale_kinds or context.sessions_stale or context.daemon_running is not True:
        evidence = tuple(
            {
                "source": f"{kind} list",
                "value": (
                    "daemon unavailable"
                    if context.daemon_running is not True
                    else "missing or older than freshness limit"
                ),
                "observed_at": value,
            }
            for kind, value in (
                ("sync", context.sync_observed_at),
                ("forward", context.forward_observed_at),
            )
            if kind in stale_kinds or context.sessions_stale or context.daemon_running is not True
        )
        add(
            "snapshot_stale",
            "warning",
            evidence=evidence,
            observed_at=min(
                (
                    value
                    for value in (context.sync_observed_at, context.forward_observed_at)
                    if value
                ),
                default=None,
            ),
        )

    for session in context.sessions:
        observed = session.measured_at
        source = f"Mutagen {session.identity.kind} list"
        session_evidence = ({"source": source, "value": session.state, "observed_at": observed},)
        config = session.native_config
        paused = config.get("paused") is True or session.state.casefold() in {
            "paused",
            "manually paused",
        }
        mode = config.get("mode", config.get("watchMode"))
        manual = config.get("manual") is True or (
            isinstance(mode, str) and mode.casefold() == "manual"
        )
        if paused:
            add("intentional_pause", "info", session=session, evidence=session_evidence)
        if manual:
            add("manual_mode", "info", session=session, evidence=session_evidence)

        specialized_error = False
        if session.identity.kind == "sync":
            excluded_conflicts = _int_value(config.get("excludedConflicts"))
            conflict_total = len(session.conflicts) + excluded_conflicts
            if conflict_total:
                add(
                    "conflicts",
                    "warning",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen conflict counters",
                            "value": conflict_total,
                            "observed_at": observed,
                        },
                    ),
                )
            status = config.get("status")
            if status in (1, 2, 3, "1", "2", "3"):
                status_text = {
                    1: "Halted: empty root",
                    2: "Halted: deleted root",
                    3: "Halted: root type change",
                    "1": "Halted: empty root",
                    "2": "Halted: deleted root",
                    "3": "Halted: root type change",
                }[status]
                add(
                    "root_problem",
                    "error",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen sync status",
                            "value": status_text,
                            "observed_at": observed,
                        },
                    ),
                    detail=status_text,
                )
                specialized_error = True
            elif (
                status in (0, "0")
                and not paused
                and not manual
                and any(
                    endpoint is not None and endpoint.kind == "ssh"
                    for endpoint in (session.alpha_or_source, session.beta_or_destination)
                )
            ):
                add(
                    "ssh_disconnected",
                    "error",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen sync status",
                            "value": "Disconnected",
                            "observed_at": observed,
                        },
                    ),
                )
                specialized_error = True
            excluded_problem_count = sum(
                _int_value(config.get(key))
                for key in (
                    "excludedScanProblems",
                    "excludedTransitionProblems",
                )
            )
            if excluded_problem_count:
                add(
                    "scan_problem",
                    "warning",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen excluded problem counters",
                            "value": excluded_problem_count,
                            "observed_at": observed,
                        },
                    ),
                )

        endpoints = (
            (
                ("alpha", session.alpha_or_source),
                ("beta", session.beta_or_destination),
            )
            if session.identity.kind == "sync"
            else (
                ("source", session.alpha_or_source),
                ("destination", session.beta_or_destination),
            )
        )
        for endpoint_name, endpoint in endpoints:
            if endpoint is None:
                continue
            fields = endpoint.native_fields
            connected = fields.get("connected")
            connection_state = fields.get("connectionState", fields.get("state"))
            connection_text = (
                str(connection_state).casefold() if connection_state is not None else ""
            )
            endpoint_error = fields.get("lastError", fields.get("error", ""))
            error_text = _text(endpoint_error) if endpoint_error else ""
            disconnected = connected is False or connection_text in {
                "disconnected",
                "error",
                "failed",
            }
            if (paused or manual) and disconnected and not error_text:
                continue
            code = _error_code(error_text, kind=session.identity.kind, endpoint_name=endpoint_name)
            if code is None and disconnected:
                code = (
                    "forward_source_problem"
                    if session.identity.kind == "forward" and endpoint_name == "source"
                    else "forward_destination_problem"
                    if session.identity.kind == "forward"
                    else "ssh_disconnected"
                    if endpoint.kind == "ssh"
                    else "session_error"
                )
            if code is not None:
                add(
                    code,
                    "error",
                    session=session,
                    evidence=(
                        {
                            "source": f"{source} endpoint {endpoint_name}",
                            "value": error_text or connection_text or "disconnected",
                            "observed_at": observed,
                        },
                    ),
                    detail=error_text,
                )
                specialized_error = True

        raw_error = config.get("lastError")
        if raw_error:
            message = _text(raw_error)
            code = _error_code(message, kind=session.identity.kind)
            if code is None:
                code = "session_error"
            add(
                code,
                "error",
                session=session,
                evidence=(
                    {"source": source + " lastError", "value": message, "observed_at": observed},
                ),
                detail=message,
            )
            specialized_error = True
        if (
            session.state.casefold() == "error"
            and not paused
            and not specialized_error
            and not session.conflicts
            and not _int_value(config.get("excludedConflicts"))
            and not session.problems
        ):
            add("session_error", "error", session=session, evidence=session_evidence)

        for problem in session.problems:
            message = _text(problem)
            code = _error_code(message, kind=session.identity.kind)
            if code is None:
                code = "session_error"
            add(
                code,
                "warning",
                session=session,
                evidence=(
                    {"source": source + " problem", "value": message, "observed_at": observed},
                ),
                detail=message,
            )

    if (
        context.cpu_percent is not None
        and context.cpu_percent >= HIGH_CPU_PERCENT
        and _recent(context.resource_observed_at, generated_at, freshness_seconds)
    ):
        add(
            "high_cpu",
            "warning",
            certainty="suspected",
            observed_at=context.resource_observed_at,
            evidence=(
                {
                    "source": "Mutagen process sampler",
                    "value": context.cpu_percent,
                    "unit": "percent",
                    "observed_at": context.resource_observed_at,
                },
            ),
            detail=f"Heuristic threshold: {HIGH_CPU_PERCENT:.0f}% measured CPU.",
        )

    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    issues.sort(
        key=lambda issue: (
            severity_order.get(issue.severity, 4),
            issue.code,
            issue.session_identifier or "",
        )
    )
    return SessionDoctorReport(
        tuple(issues), authoritative, generated_at, len(context.sessions), stale_kinds
    )
