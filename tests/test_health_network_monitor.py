from types import SimpleNamespace

from mutaui.ui.health_network_monitor import health_network_changed


def test_network_reachability_change_resets_health_environment(monkeypatch):
    events = []
    tracker = SimpleNamespace(
        note_environment_event=lambda kind, *, now: events.append((kind, now))
    )
    window = SimpleNamespace(
        _health_network_reachability=None,
        health_tracker=tracker,
    )
    monkeypatch.setattr("mutaui.ui.health_network_monitor.time.monotonic", lambda: 12.5)

    health_network_changed(window, "online")
    health_network_changed(window, "online")
    health_network_changed(window, "offline")

    assert window._health_network_reachability == "offline"
    assert events == [("network_change", 12.5)]
