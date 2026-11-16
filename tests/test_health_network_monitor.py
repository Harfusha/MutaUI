"""Tests for the optional Qt network reachability monitor."""

import sys
from types import ModuleType

from mutaui.services.health_network_monitor import attach_health_network_monitor


class FakeSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self, value):
        assert self.callback is not None
        self.callback(value)


def install_network_information(monkeypatch, information_type):
    network_module = ModuleType("PySide6.QtNetwork")
    network_module.QNetworkInformation = information_type
    monkeypatch.setitem(sys.modules, "PySide6.QtNetwork", network_module)


def test_returns_current_state_and_connects_callback(monkeypatch):
    class FakeInformation:
        class Feature:
            Reachability = object()

        reachabilityChanged = FakeSignal()

        @classmethod
        def loadDefaultBackend(cls):
            return True

        @classmethod
        def instance(cls):
            return cls

        @classmethod
        def supports(cls, feature):
            assert feature is cls.Feature.Reachability
            return True

        @classmethod
        def reachability(cls):
            return "online"

    install_network_information(monkeypatch, FakeInformation)
    changes = []

    information, reachability = attach_health_network_monitor(changes.append)
    FakeInformation.reachabilityChanged.emit("online")
    FakeInformation.reachabilityChanged.emit("offline")
    FakeInformation.reachabilityChanged.emit("offline")

    assert information is FakeInformation
    assert reachability == "online"
    assert changes == ["online", "offline", "offline"]


def test_unavailable_backend_disables_monitor(monkeypatch):
    class FakeInformation:
        class Feature:
            Reachability = object()

        @classmethod
        def loadDefaultBackend(cls):
            return False

        @classmethod
        def instance(cls):
            raise AssertionError("instance must not load without a backend")

    install_network_information(monkeypatch, FakeInformation)
    changes = []

    information, reachability = attach_health_network_monitor(
        lambda _value: changes.append("network_change")
    )

    assert information is None
    assert reachability is None
    assert changes == []


def test_missing_qt_network_module_disables_monitor(monkeypatch):
    monkeypatch.setitem(sys.modules, "PySide6.QtNetwork", None)

    assert attach_health_network_monitor(lambda _value: None) == (None, None)
