import pytest

from mutaui.services.session_notification_gate import SessionNotificationGate
from mutaui.services.tray_status import worst_tray_status


def test_error_notification_waits_for_debounce_window():
    gate = SessionNotificationGate(debounce_seconds=10)
    errors = {("sync", "one"): "One"}

    assert gate.update(errors, now=100) == ()
    assert gate.update(errors, now=109.99) == ()
    (event,) = gate.update(errors, now=110)

    assert event.kind == "issue"
    assert event.session_keys == (("sync", "one"),)
    assert event.titles == ("One",)


def test_short_error_flap_is_cleared_without_notification():
    gate = SessionNotificationGate(debounce_seconds=10)

    assert gate.update({("sync", "one"): "One"}, now=1) == ()
    assert gate.update({}, now=5) == ()
    assert gate.update({}, now=20) == ()


def test_matured_errors_are_grouped_into_one_incident_notification():
    gate = SessionNotificationGate(debounce_seconds=10)
    errors = {("sync", "one"): "One", ("forward", "two"): "Two"}

    assert gate.update(errors, now=1) == ()
    (event,) = gate.update(errors, now=11)

    assert event.kind == "issue"
    assert event.session_keys == (("sync", "one"), ("forward", "two"))
    assert event.titles == ("One", "Two")


def test_recovery_is_reported_after_confirmed_incident():
    gate = SessionNotificationGate(debounce_seconds=10)
    errors = {("sync", "one"): "One"}

    assert gate.update(errors, now=1) == ()
    assert gate.update(errors, now=11)[0].kind == "issue"
    (event,) = gate.update({}, now=12)

    assert event.kind == "recovery"
    assert event.session_keys == (("sync", "one"),)


def test_notification_throttle_is_per_session_and_retries_after_interval():
    gate = SessionNotificationGate(debounce_seconds=10, throttle_seconds=60)
    errors = {("sync", "one"): "One"}

    assert gate.update(errors, now=1) == ()
    assert gate.update(errors, now=11)[0].kind == "issue"
    assert gate.update({}, now=12)[0].kind == "recovery"
    assert gate.update(errors, now=20) == ()
    assert gate.update(errors, now=30) == ()
    (event,) = gate.update(errors, now=71)
    assert event.kind == "issue"


def test_quiet_period_keeps_matured_incident_pending_until_delivery_allowed():
    gate = SessionNotificationGate(debounce_seconds=10)
    errors = {("sync", "one"): "One"}

    assert gate.update(errors, now=1) == ()
    assert gate.update(errors, now=11, notifications_allowed=False) == ()
    (event,) = gate.update(errors, now=12, notifications_allowed=True)
    assert event.kind == "issue"


def test_tray_status_uses_worst_confirmed_session_state():
    assert (
        worst_tray_status(daemon_online=False, sessions_stale=False, states=["watching"])
        == "offline"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=True, states=["watching"]) == "unknown"
    )
    assert worst_tray_status(daemon_online=True, sessions_stale=False, states=[]) == "idle"
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["watching", "paused"])
        == "paused"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["paused", "error"])
        == "issue"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["watching", "scanning"])
        == "busy"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["watching", "active"])
        == "healthy"
    )
    assert (
        worst_tray_status(daemon_online=True, sessions_stale=False, states=["future-state"])
        == "unknown"
    )


def test_recovery_waits_until_notifications_are_allowed():
    gate = SessionNotificationGate(debounce_seconds=0)
    errors = {("sync", "one"): "One"}

    assert gate.update(errors, now=1)[0].kind == "issue"
    assert gate.update({}, now=2, notifications_allowed=False) == ()
    (event,) = gate.update({}, now=3, notifications_allowed=True)
    assert event.kind == "recovery"


@pytest.mark.parametrize(
    "intervals",
    [
        {"debounce_seconds": -1, "throttle_seconds": 0},
        {"debounce_seconds": 0, "throttle_seconds": -1},
    ],
)
def test_notification_gate_rejects_negative_intervals(intervals):
    with pytest.raises(ValueError, match="must not be negative"):
        SessionNotificationGate(**intervals)


def test_recovery_uses_latest_title_for_a_continuing_incident():
    gate = SessionNotificationGate(debounce_seconds=0)
    key = ("sync", "one")

    assert gate.update({key: "Initial"}, now=1)[0].titles == ("Initial",)
    assert gate.update({key: "Updated"}, now=2) == ()
    (event,) = gate.update({}, now=3)
    assert event.kind == "recovery"
    assert event.titles == ("Updated",)
