from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mutagen_client import (
    MutagenCommandError,
    MutagenCommandTimeout,
    MutagenError,
    MutagenLaunchError,
)
from mutaui.domain.models import SessionIdentity, SessionSnapshot
from mutaui.services.action_planner import ActionPlanner, ActionRequest
from mutaui.services.reconfiguration import build_reconfiguration_preview
from mutaui.services.replacement import (
    MutagenReplacementBackend,
    ReplacementCreateError,
    ReplacementRequest,
    replace_non_project_mutagen_session,
    replace_non_project_session,
)


class FakeBackend:
    def __init__(self):
        self.fingerprint = ""
        self.sessions = {"sync-exact-123"}
        self.commands = []
        self.fail_new_verify = False
        self.fail_new_create_after_side_effect = False
        self.fail_terminate_identifier = None

    def current_fingerprint(self, session_identifier):
        assert session_identifier == "sync-exact-123"
        return self.fingerprint

    def session_exists(self, session_identifier):
        return session_identifier in self.sessions

    def terminate_exact(self, session_identifier):
        assert session_identifier in self.sessions
        self.commands.append(("terminate", session_identifier))
        if session_identifier == self.fail_terminate_identifier:
            raise OSError("injected terminate failure")
        self.sessions.discard(session_identifier)

    def create(self, arguments):
        self.commands.append(("create", tuple(arguments)))
        if "--new" in arguments and self.fail_new_create_after_side_effect:
            self.sessions.add("sync-new-ambiguous-999")
            raise TimeoutError("creation result unavailable")
        identifier = "sync-new-456" if "--new" in arguments else "sync-restored-789"
        self.sessions.add(identifier)
        return identifier

    def verify(self, session_identifier, expected_configuration):
        if session_identifier == "sync-new-456" and self.fail_new_verify:
            return False
        return session_identifier in self.sessions and bool(expected_configuration)


def _case():
    snapshot = SessionSnapshot(
        identity=SessionIdentity("sync", "sync-exact-123", "source name"),
        native_config={"configuration": {"mode": "two-way-safe"}},
        alpha_or_source=None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    old_argv = ("sync", "create", "C:/alpha", "C:/beta")
    preview = build_reconfiguration_preview(
        snapshot,
        {"mode": "one-way-safe"},
        command_arguments=old_argv,
        command_target_identifier="sync-exact-123",
    )
    planner = ActionPlanner(now=lambda: 1.0)
    plan = planner.prepare(
        ActionRequest(
            action="sync_reconfigure",
            target_ids=("sync-exact-123",),
            argv=("sync", "create", "C:/alpha", "C:/beta", "--new"),
            preflight_fingerprint=preview.source_sha256,
            capabilities=("sync_reconfigure",),
        )
    )
    plan = planner.consent(
        plan.plan_id,
        consent=True,
        current_preflight_fingerprint=preview.source_sha256,
    )
    request = ReplacementRequest(
        plan=plan,
        previous_session_identifier="sync-exact-123",
        source_sha256=preview.source_sha256,
        old_create_arguments=old_argv,
        new_create_arguments=plan.argv,
        old_configuration={"mode": "two-way-safe"},
        new_configuration={"mode": "one-way-safe"},
        snapshot_validation=preview.validation,
    )
    backend = FakeBackend()
    backend.fingerprint = preview.source_sha256
    return request, backend


def test_replacement_requires_exact_snapshot_restore_command_and_no_ops_on_failure():
    request, backend = _case()
    mismatched = replace(request, old_create_arguments=("sync", "create", "other", "paths"))

    with pytest.raises(ValueError, match="validated command snapshot"):
        replace_non_project_session(mismatched, backend, consent=True, audit=lambda _: None)

    assert backend.commands == []


def test_replacement_requires_exact_consented_command_preview():
    request, backend = _case()
    mismatched = replace(
        request,
        new_create_arguments=("sync", "create", "C:/alpha", "C:/beta", "--different"),
    )

    with pytest.raises(ValueError, match="consented ActionPlan preview"):
        replace_non_project_session(mismatched, backend, consent=True, audit=lambda _: None)

    assert backend.commands == []


def test_exact_non_project_replacement_and_postcheck_succeed():
    request, backend = _case()
    events = []

    receipt = replace_non_project_session(request, backend, consent=True, audit=events.append)

    assert receipt.verified
    assert receipt.new_session_identifier == "sync-new-456"
    assert backend.commands[0] == ("terminate", "sync-exact-123")
    assert [event.phase for event in events] == ["preflight", "terminate", "postcheck"]
    assert all("C:/" not in repr(event) for event in events)


def test_failed_replacement_attempts_best_effort_restore_and_reports_uncertainty():
    request, backend = _case()
    backend.fail_new_verify = True

    receipt = replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert not receipt.verified
    assert receipt.restore_attempted
    assert receipt.restored_session_identifier == "sync-restored-789"
    assert not receipt.recovery_uncertain
    assert ("terminate", "sync-new-456") in backend.commands
    assert "sync-new-456" not in backend.sessions
    assert backend.commands[-1] == ("create", request.old_create_arguments)


def test_unknown_create_outcome_does_not_issue_a_second_restore_create():
    request, backend = _case()
    backend.fail_new_create_after_side_effect = True
    events = []

    receipt = replace_non_project_session(request, backend, consent=True, audit=events.append)

    assert not receipt.verified
    assert not receipt.restore_attempted
    assert receipt.recovery_uncertain
    assert "sync-exact-123" not in backend.sessions
    assert "sync-new-ambiguous-999" in backend.sessions
    assert backend.commands == [
        ("terminate", "sync-exact-123"),
        ("create", request.new_create_arguments),
    ]
    assert [event.phase for event in events] == ["preflight", "terminate", "replacement"]


def test_failed_replacement_cleanup_does_not_create_old_session_again():
    request, backend = _case()
    backend.fail_new_verify = True
    backend.fail_terminate_identifier = "sync-new-456"

    receipt = replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert not receipt.verified
    assert not receipt.restore_attempted
    assert receipt.recovery_uncertain
    assert "sync-exact-123" not in backend.sessions
    assert "sync-new-456" in backend.sessions
    assert backend.commands == [
        ("terminate", "sync-exact-123"),
        ("create", request.new_create_arguments),
        ("terminate", "sync-new-456"),
    ]


@pytest.mark.parametrize("failure", ["project", "fingerprint", "session"])
def test_replacement_preflight_refuses_without_terminating(failure):
    request, backend = _case()
    if failure == "project":
        request = replace(request, project_owned=True)
    elif failure == "fingerprint":
        backend.fingerprint = "changed"
    else:
        backend.sessions.clear()

    with pytest.raises(ValueError):
        replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert backend.commands == []


def test_mutagen_backend_binds_fingerprint_target_create_and_configuration():
    original = {
        "identifier": "sync-exact-123",
        "name": "old",
        "configuration": {"mode": "two-way-safe"},
        "alpha": {"protocol": 0, "path": "/alpha"},
        "beta": {"protocol": 0, "path": "/beta"},
    }
    replacement = {
        **original,
        "identifier": "sync-new-456",
        "name": "new",
        "configuration": {"mode": "one-way-safe"},
    }

    class FakeClient:
        def __init__(self):
            self.sessions = [original]
            self.commands = []

        def list_sessions(self, kind):
            assert kind == "sync"
            return list(self.sessions)

        def command(self, arguments, *, timeout):
            self.commands.append(tuple(arguments))
            if arguments[1] == "terminate":
                assert timeout == 40
                target = arguments[2]
                self.sessions = [item for item in self.sessions if item["identifier"] != target]
            else:
                assert timeout == 120
                self.sessions.append(replacement)
            return "created"

    client = FakeClient()
    backend = MutagenReplacementBackend(client)
    snapshot = SessionSnapshot(
        identity=SessionIdentity("sync", "sync-exact-123", "old"),
        native_config=original,
        alpha_or_source=None,
        beta_or_destination=None,
        state="watching",
        conflicts=(),
        problems=(),
        counters={},
        measured_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    preview = build_reconfiguration_preview(
        snapshot,
        {"mode": "one-way-safe"},
        command_arguments=("sync", "create", "/alpha", "/beta"),
        command_target_identifier="sync-exact-123",
    )
    assert backend.session_exists("sync-exact-123")
    assert not backend.session_exists("same display name")
    assert backend.current_fingerprint("sync-exact-123") == preview.source_sha256
    assert backend.verify("sync-exact-123", original["configuration"])
    assert not backend.verify("same display name", original["configuration"])

    backend.terminate_exact("sync-exact-123")
    created = backend.create(("sync", "create", "--name=new", "/alpha", "/beta"))

    assert created == "sync-new-456"
    assert backend.verify("sync-new-456", replacement["configuration"])
    assert client.commands[0] == ("sync", "terminate", "sync-exact-123")


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("sync", "terminate", "id", "extra"), "exact sync create"),
        (("sync", "create", "", "/beta"), "invalid command arguments"),
        (("sync", "create", "/alpha", "/beta", "\x00"), "invalid command arguments"),
        (("sync", "create", "/alpha", "/beta", "--ALL=true"), "--all"),
    ],
)
def test_mutagen_backend_rejects_invalid_create_arguments_before_cli(arguments, message):
    class Client:
        def list_sessions(self, _kind):
            pytest.fail("invalid arguments must be rejected before session inspection")

    backend = MutagenReplacementBackend(Client())
    with pytest.raises(ValueError, match=message):
        backend.create(arguments)


def test_mutagen_backend_requires_exact_existing_identifier_to_terminate():
    class Client:
        def list_sessions(self, _kind):
            return [{"identifier": "sync-exact-123"}]

        def command(self, *_args, **_kwargs):
            pytest.fail("invalid or absent identifiers must not invoke the CLI")

    backend = MutagenReplacementBackend(Client())
    for identifier in ("", "-all"):
        with pytest.raises(ValueError, match="valid exact"):
            backend.terminate_exact(identifier)
    with pytest.raises(ValueError, match="no longer exists"):
        backend.terminate_exact("display name")


@pytest.mark.parametrize(
    "created",
    [
        [],
        [{"name": "one", "identifier": "id-1"}, {"name": "two", "identifier": "id-2"}],
        [{"name": "one"}],
    ],
)
def test_mutagen_backend_requires_one_new_exact_identifier(created):
    class Client:
        sessions = [{"identifier": "sync-old-123"}]

        def list_sessions(self, _kind):
            return list(self.sessions)

        def command(self, *_args, **_kwargs):
            self.sessions.extend(created)

    backend = MutagenReplacementBackend(Client())
    with pytest.raises(RuntimeError, match="exact session identifier|exactly one"):
        backend.create(("sync", "create", "/alpha", "/beta"))


@pytest.mark.parametrize(
    "failure",
    [
        "consent",
        "state",
        "action",
        "risk",
        "target",
        "incomplete",
        "snapshot_id",
        "snapshot_hash",
        "plan_hash",
    ],
)
def test_replacement_rejects_stale_or_unsafe_preflight_without_commands(failure):
    request, backend = _case()
    consent = failure != "consent"
    if failure == "state":
        request = replace(request, plan=replace(request.plan, state="prepared"))
    elif failure == "action":
        request = replace(request, plan=replace(request.plan, action="sync_create"))
    elif failure == "risk":
        request = replace(request, plan=replace(request.plan, risk="R1"))
    elif failure == "target":
        request = replace(request, plan=replace(request.plan, target_ids=("other-id",)))
    elif failure == "incomplete":
        request = replace(
            request,
            snapshot_validation=replace(request.snapshot_validation, round_trip_valid=False),
        )
    elif failure == "snapshot_id":
        request = replace(
            request,
            snapshot_validation=replace(
                request.snapshot_validation, exact_session_identifier="other-id"
            ),
        )
    elif failure == "snapshot_hash":
        request = replace(
            request,
            snapshot_validation=replace(request.snapshot_validation, source_sha256="stale"),
        )
    elif failure == "plan_hash":
        request = replace(request, plan=replace(request.plan, preflight_fingerprint="stale"))

    with pytest.raises(ValueError):
        replace_non_project_session(request, backend, consent=consent, audit=lambda _: None)

    assert backend.commands == []


def test_replacement_fails_closed_when_original_termination_fails():
    request, backend = _case()
    backend.fail_terminate_identifier = "sync-exact-123"
    events = []

    with pytest.raises(OSError, match="injected terminate failure"):
        replace_non_project_session(request, backend, consent=True, audit=events.append)

    assert [event.phase for event in events] == ["preflight"]
    assert backend.sessions == {"sync-exact-123"}


def test_replacement_does_not_restore_if_exact_old_identifier_remains():
    request, backend = _case()

    def keep_old(identifier):
        backend.commands.append(("terminate", identifier))

    backend.terminate_exact = keep_old
    receipt = replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert not receipt.verified
    assert receipt.recovery_uncertain
    assert not receipt.restore_attempted
    assert "sync-exact-123" in backend.sessions
    assert ("create", request.old_create_arguments) not in backend.commands


def test_failed_restore_is_reported_as_uncertain():
    request, backend = _case()
    backend.fail_new_verify = True
    original_create = backend.create

    def fail_restore(arguments):
        if arguments == request.old_create_arguments:
            raise OSError("restore failed")
        return original_create(arguments)

    backend.create = fail_restore
    receipt = replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert not receipt.verified
    assert receipt.restore_attempted
    assert receipt.restored_session_identifier is None
    assert receipt.recovery_uncertain


def test_replacement_cleans_up_known_identifier_from_create_error_then_restores():
    request, backend = _case()
    original_create = backend.create

    def create_with_known_side_effect(arguments):
        if "--new" in arguments:
            backend.sessions.add("sync-new-known-999")
            raise ReplacementCreateError(
                "create returned an error", created_identifier="sync-new-known-999"
            )
        return original_create(arguments)

    backend.create = create_with_known_side_effect
    receipt = replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert receipt.restore_attempted
    assert receipt.restored_session_identifier == "sync-restored-789"
    assert not receipt.recovery_uncertain
    assert "sync-new-known-999" not in backend.sessions


def test_mutagen_backend_verify_rejects_invalid_expected_configuration():
    class Client:
        def list_sessions(self, _kind):
            return [{"identifier": "sync-exact-123", "configuration": {"mode": "safe"}}]

    backend = MutagenReplacementBackend(Client())
    assert not backend.verify("sync-exact-123", {"configuration": None})
    assert not backend.verify("sync-exact-123", {"mode": float("nan")})


def test_replacement_skips_cleanup_when_unverified_id_is_already_absent():
    request, backend = _case()
    backend.fail_new_verify = True
    original_create = backend.create

    def remove_new_after_create(arguments):
        identifier = original_create(arguments)
        if "--new" in arguments:
            backend.sessions.discard(identifier)
        return identifier

    backend.create = remove_new_after_create
    receipt = replace_non_project_session(request, backend, consent=True, audit=lambda _: None)

    assert receipt.restore_attempted
    assert receipt.restored_session_identifier == "sync-restored-789"
    assert not receipt.recovery_uncertain
    assert not any(command == ("terminate", "sync-new-456") for command in backend.commands)


def test_mutagen_session_wrapper_forwards_to_reviewed_coordinator(monkeypatch):
    import mutaui.services.replacement as replacement_module

    request, _backend = _case()
    sentinel = object()
    captured = {}

    def fake_coordinator(given_request, backend, *, consent, audit):
        captured.update(
            request=given_request,
            backend=backend,
            consent=consent,
            audit=audit,
        )
        return sentinel

    monkeypatch.setattr(replacement_module, "replace_non_project_session", fake_coordinator)
    client = object()
    audit = lambda _event: None
    result = replace_non_project_mutagen_session(request, client, consent=True, audit=audit)

    assert result is sentinel
    assert captured["request"] is request
    assert isinstance(captured["backend"], MutagenReplacementBackend)
    assert captured["backend"]._client is client
    assert captured["consent"] is True
    assert captured["audit"] is audit


@pytest.mark.parametrize(
    ("error", "after_error", "requested_name", "created", "expected_id", "uncertain"),
    [
        (MutagenLaunchError("launch"), None, None, [], None, False),
        (MutagenError("generic"), None, None, [], None, False),
        (MutagenCommandError("failed"), [], None, [], None, False),
        (MutagenCommandTimeout("timed out"), [], None, [], None, True),
        (
            MutagenCommandError("failed after create"),
            [{"identifier": "sync-new-456", "name": "wanted"}],
            "wanted",
            [{"identifier": "sync-new-456", "name": "wanted"}],
            "sync-new-456",
            False,
        ),
        (MutagenCommandError("failed"), OSError("inspect failed"), None, [], None, True),
    ],
)
def test_mutagen_backend_classifies_failed_create_outcomes(
    error, after_error, requested_name, created, expected_id, uncertain
):
    class Client:
        def __init__(self):
            self.calls = 0

        def list_sessions(self, _kind):
            self.calls += 1
            if self.calls == 1:
                return [{"identifier": "sync-old-123"}]
            if isinstance(after_error, Exception):
                raise after_error
            return [{"identifier": "sync-old-123"}, *created]

        def command(self, *_args, **_kwargs):
            raise error

    backend = MutagenReplacementBackend(Client())
    arguments = ("sync", "create", "/alpha", "/beta")
    if requested_name is not None:
        arguments = (*arguments, f"--name={requested_name}")

    with pytest.raises(ReplacementCreateError) as caught:
        backend.create(arguments)

    assert caught.value.created_identifier == expected_id
    assert caught.value.outcome_uncertain is uncertain
