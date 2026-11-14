"""Exact-ID non-project session replacement with preflight and restore checks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from mutagen_client import (
    MutagenClient,
    MutagenCommandError,
    MutagenCommandTimeout,
    MutagenError,
    MutagenLaunchError,
)
from mutaui.services.action_planner import ActionPlan
from mutaui.services.reconfiguration import (
    NativeCommandSnapshotValidation,
    _canonical_json,
    extract_sync_configuration,
    native_config_fingerprint,
)


class ReplacementBackend(Protocol):
    def current_fingerprint(self, session_identifier: str) -> str: ...

    def session_exists(self, session_identifier: str) -> bool: ...

    def terminate_exact(self, session_identifier: str) -> None: ...

    def create(self, arguments: Sequence[str]) -> str: ...

    def verify(
        self, session_identifier: str, expected_configuration: Mapping[str, object]
    ) -> bool: ...


class ReplacementCreateError(RuntimeError):
    """Describe whether a failed native create left a known or unknown new session."""

    def __init__(
        self,
        message: str,
        *,
        created_identifier: str | None = None,
        outcome_uncertain: bool = False,
    ) -> None:
        super().__init__(message)
        self.created_identifier = created_identifier
        self.outcome_uncertain = outcome_uncertain


class MutagenReplacementBackend:
    """Production adapter for exact-ID replacement through the native CLI."""

    def __init__(self, client: MutagenClient) -> None:
        self._client = client

    def _session(self, session_identifier: str) -> dict[str, object] | None:
        return next(
            (
                item
                for item in self._client.list_sessions("sync")
                if item.get("identifier") == session_identifier
            ),
            None,
        )

    def current_fingerprint(self, session_identifier: str) -> str:
        session = self._session(session_identifier)
        return native_config_fingerprint(session) if session is not None else ""

    def session_exists(self, session_identifier: str) -> bool:
        return self._session(session_identifier) is not None

    def terminate_exact(self, session_identifier: str) -> None:
        if not session_identifier or session_identifier.startswith("-"):
            raise ValueError("A valid exact native session identifier is required.")
        session = self._session(session_identifier)
        if session is None:
            raise ValueError("Exact sync session no longer exists.")
        self._client.command(["sync", "terminate", session_identifier], timeout=40)

    def create(self, arguments: Sequence[str]) -> str:
        _validate_create_arguments(arguments, label="Create command")
        existing_ids = {
            str(item.get("identifier") or "") for item in self._client.list_sessions("sync")
        }
        try:
            self._client.command(list(arguments), timeout=120)
        except MutagenLaunchError as exc:
            raise ReplacementCreateError(str(exc)) from exc
        except (MutagenCommandError, MutagenCommandTimeout) as exc:
            try:
                created = [
                    item
                    for item in self._client.list_sessions("sync")
                    if str(item.get("identifier") or "") not in existing_ids
                ]
            except Exception as inspect_exc:
                raise ReplacementCreateError(str(exc), outcome_uncertain=True) from inspect_exc
            requested_name = next(
                (
                    argument.removeprefix("--name=")
                    for argument in arguments
                    if argument.startswith("--name=")
                ),
                None,
            )
            matching = (
                [item for item in created if item.get("name") == requested_name]
                if requested_name is not None
                else created
            )
            if (
                len(created) == 1
                and len(matching) == 1
                and isinstance(matching[0].get("identifier"), str)
                and matching[0].get("identifier")
            ):
                raise ReplacementCreateError(
                    str(exc), created_identifier=str(matching[0]["identifier"])
                ) from exc
            no_new_session = not created and isinstance(exc, MutagenCommandError)
            raise ReplacementCreateError(str(exc), outcome_uncertain=not no_new_session) from exc
        except MutagenError as exc:
            raise ReplacementCreateError(str(exc)) from exc
        created = [
            item
            for item in self._client.list_sessions("sync")
            if str(item.get("identifier") or "") not in existing_ids
        ]
        requested_name = next(
            (
                argument.removeprefix("--name=")
                for argument in arguments
                if argument.startswith("--name=")
            ),
            None,
        )
        if requested_name is not None:
            created = [item for item in created if item.get("name") == requested_name]
        if len(created) != 1:
            raise RuntimeError("Could not identify exactly one newly created session by native ID.")
        identifier = created[0].get("identifier")
        if not isinstance(identifier, str) or not identifier:
            raise RuntimeError("Mutagen did not return a new exact session identifier.")
        return identifier

    def verify(self, session_identifier: str, expected_configuration: Mapping[str, object]) -> bool:
        session = self._session(session_identifier)
        if session is None:
            return False
        actual = extract_sync_configuration(session)
        expected: object = expected_configuration.get("configuration", expected_configuration)
        if not isinstance(actual, Mapping) or not isinstance(expected, Mapping):
            return False
        try:
            return bool(_canonical_json(actual) == _canonical_json(expected))
        except (TypeError, ValueError, OverflowError):
            return False


@dataclass(frozen=True, slots=True)
class ReplacementRequest:
    plan: ActionPlan
    previous_session_identifier: str
    source_sha256: str
    old_create_arguments: tuple[str, ...]
    new_create_arguments: tuple[str, ...]
    old_configuration: Mapping[str, object]
    new_configuration: Mapping[str, object]
    snapshot_validation: NativeCommandSnapshotValidation
    project_owned: bool = False


@dataclass(frozen=True, slots=True)
class ReplacementAuditEvent:
    plan_id: str
    session_identifier: str
    phase: str
    outcome: str
    argv_fingerprint: str
    note: str


@dataclass(frozen=True, slots=True)
class ReplacementReceipt:
    previous_session_identifier: str
    new_session_identifier: str | None
    verified: bool
    restore_attempted: bool
    restored_session_identifier: str | None
    error: str
    recovery_uncertain: bool


def _argv_fingerprint(arguments: Sequence[str]) -> str:
    encoded = json.dumps(list(arguments), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_create_arguments(arguments: Sequence[str], *, label: str) -> None:
    if len(arguments) < 4 or arguments[0:2] != ("sync", "create"):
        raise ValueError(f"{label} must be an exact sync create argument list.")
    if any(not isinstance(value, str) or not value or "\x00" in value for value in arguments):
        raise ValueError(f"{label} contains invalid command arguments.")
    if any(value.casefold() in {"--all", "--all=true"} for value in arguments):
        raise ValueError("Broad --all targeting is forbidden.")


def replace_non_project_session(
    request: ReplacementRequest,
    backend: ReplacementBackend,
    *,
    consent: bool,
    audit: Callable[[ReplacementAuditEvent], None],
) -> ReplacementReceipt:
    """Replace one session only after consent; restore best-effort on failure.

    The injected backend is the only command boundary. This function never
    discovers targets by name, invokes a shell, or operates on project sessions.
    """
    plan = request.plan
    session_id = request.previous_session_identifier
    old_argv = request.old_create_arguments
    new_argv = request.new_create_arguments
    if not consent or plan.state != "consented":
        raise ValueError("An explicitly consented ActionPlan is required.")
    if plan.action != "sync_reconfigure" or plan.risk != "R2":
        raise ValueError("Replacement requires a consented R2 sync_reconfigure plan.")
    if plan.target_ids != (session_id,):
        raise ValueError("ActionPlan must lock exactly the previous session identifier.")
    if plan.argv != tuple(new_argv):
        raise ValueError("Replacement command differs from the consented ActionPlan preview.")
    if request.project_owned:
        raise ValueError("Project-owned sessions must use their native project workflow.")
    if not request.snapshot_validation.snapshot_inputs_complete:
        raise ValueError("Incomplete native command snapshot blocks replacement.")
    if request.snapshot_validation.exact_session_identifier != session_id:
        raise ValueError("Snapshot validation is bound to a different session identifier.")
    if request.snapshot_validation.source_sha256 != request.source_sha256:
        raise ValueError("Snapshot fingerprint changed; refresh the preview.")
    if plan.preflight_fingerprint != request.source_sha256:
        raise ValueError("ActionPlan fingerprint does not match the replacement snapshot.")
    _validate_create_arguments(old_argv, label="Restore command")
    _validate_create_arguments(new_argv, label="Replacement command")
    if old_argv != request.snapshot_validation.command_arguments:
        raise ValueError("Restore command differs from the validated command snapshot.")
    if backend.current_fingerprint(session_id) != request.source_sha256:
        raise ValueError("Native session changed after preview; no command was run.")
    if not backend.session_exists(session_id):
        raise ValueError("Exact native session is no longer present; no command was run.")

    audit(
        ReplacementAuditEvent(
            plan.plan_id,
            session_id,
            "preflight",
            "passed",
            _argv_fingerprint(new_argv),
            "Exact ID, preflight fingerprint, project ownership, and snapshot validation confirmed.",
        )
    )
    backend.terminate_exact(session_id)
    audit(
        ReplacementAuditEvent(
            plan.plan_id,
            session_id,
            "terminate",
            "completed",
            _argv_fingerprint(("sync", "terminate", session_id)),
            "Previous session terminated by exact identifier.",
        )
    )

    new_identifier: str | None = None
    create_attempted = False
    cleanup_uncertain = False
    try:
        create_attempted = True
        new_identifier = backend.create(new_argv)
        if not new_identifier or backend.session_exists(session_id):
            raise RuntimeError("Replacement creation did not clear the previous exact ID.")
        verified = backend.verify(new_identifier, request.new_configuration)
        if not verified:
            raise RuntimeError("Replacement session failed native configuration post-check.")
        audit(
            ReplacementAuditEvent(
                plan.plan_id,
                session_id,
                "postcheck",
                "verified",
                _argv_fingerprint(new_argv),
                f"Created and verified exact new session ID {new_identifier}.",
            )
        )
        return ReplacementReceipt(session_id, new_identifier, True, False, None, "", False)
    except Exception as exc:
        error = f"Replacement failed: {type(exc).__name__}: {exc}"
        if isinstance(exc, ReplacementCreateError):
            new_identifier = exc.created_identifier
            cleanup_uncertain = exc.outcome_uncertain
        else:
            cleanup_uncertain = create_attempted and new_identifier is None
        audit(
            ReplacementAuditEvent(
                plan.plan_id,
                session_id,
                "replacement",
                "failed",
                _argv_fingerprint(new_argv),
                f"Replacement failed: {type(exc).__name__}.",
            )
        )

    if new_identifier:
        try:
            if backend.session_exists(new_identifier):
                backend.terminate_exact(new_identifier)
                audit(
                    ReplacementAuditEvent(
                        plan.plan_id,
                        session_id,
                        "cleanup_replacement",
                        "completed",
                        _argv_fingerprint(("sync", "terminate", new_identifier)),
                        "Unverified replacement session was terminated by its exact native ID.",
                    )
                )
        except Exception as cleanup_exc:
            cleanup_uncertain = True
            audit(
                ReplacementAuditEvent(
                    plan.plan_id,
                    session_id,
                    "cleanup_replacement",
                    "failed",
                    _argv_fingerprint(("sync", "terminate", new_identifier)),
                    f"Unverified replacement cleanup failed: {type(cleanup_exc).__name__}.",
                )
            )

    if backend.session_exists(session_id) or cleanup_uncertain:
        return ReplacementReceipt(session_id, None, False, False, None, error, True)

    try:
        restored_identifier = backend.create(old_argv)
        restored = bool(restored_identifier) and backend.verify(
            restored_identifier, request.old_configuration
        )
        audit(
            ReplacementAuditEvent(
                plan.plan_id,
                session_id,
                "restore",
                "verified" if restored else "unverified",
                _argv_fingerprint(old_argv),
                "Best-effort restore returned and post-check completed.",
            )
        )
        return ReplacementReceipt(
            session_id,
            None,
            False,
            True,
            restored_identifier if restored else None,
            error,
            not restored or cleanup_uncertain,
        )
    except Exception as restore_exc:
        audit(
            ReplacementAuditEvent(
                plan.plan_id,
                session_id,
                "restore",
                "failed",
                _argv_fingerprint(old_argv),
                f"Best-effort restore failed: {type(restore_exc).__name__}.",
            )
        )
        return ReplacementReceipt(session_id, None, False, True, None, error, True)


def replace_non_project_mutagen_session(
    request: ReplacementRequest,
    client: MutagenClient,
    *,
    consent: bool,
    audit: Callable[[ReplacementAuditEvent], None],
) -> ReplacementReceipt:
    """Run the reviewed coordinator with the real Mutagen CLI adapter."""
    return replace_non_project_session(
        request,
        MutagenReplacementBackend(client),
        consent=consent,
        audit=audit,
    )
