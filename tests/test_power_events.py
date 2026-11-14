import ctypes
from ctypes import wintypes

import pytest

import mutaui.services.power_events as power_events
from mutaui.services.power_events import (
    decode_logind_prepare_for_sleep,
    decode_macos_workspace_notification,
    decode_windows_power_broadcast,
    install_linux_logind_power_event_monitor,
    install_macos_power_event_monitor,
    install_platform_power_event_monitor,
    install_windows_power_event_filter,
)


def test_decodes_windows_suspend_and_resume_events():
    assert decode_windows_power_broadcast(0x0004) == "sleep"
    assert decode_windows_power_broadcast(0x0006) == "wake"
    assert decode_windows_power_broadcast(0x0012) == "wake"
    assert decode_windows_power_broadcast(0x0007) == "wake"


def test_ignores_unrelated_windows_power_events():
    assert decode_windows_power_broadcast(0x0000) is None
    assert decode_windows_power_broadcast(0x8000) is None


def test_native_filter_installs_and_forwards_only_known_power_events(monkeypatch):
    if not hasattr(wintypes, "MSG"):
        pytest.skip("ctypes Windows MSG is available only on Windows")
    monkeypatch.setattr(power_events.sys, "platform", "win32")
    installed = []
    received = []

    class Application:
        def installNativeEventFilter(self, event_filter):
            installed.append(event_filter)

    event_filter = install_windows_power_event_filter(Application(), received.append)
    assert event_filter is not None
    assert installed == [event_filter]

    message = wintypes.MSG()
    message.message = 0x0004
    assert event_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message)) == (
        False,
        0,
    )
    message.message = 0x8000
    assert event_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message)) == (
        False,
        0,
    )
    assert received == ["sleep"]


def test_native_power_filter_is_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(power_events.sys, "platform", "linux")
    assert install_windows_power_event_filter(object(), lambda _event: None) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "sleep"), (False, "wake"), (1, None), (None, None)],
)
def test_decodes_logind_prepare_for_sleep(value, expected):
    assert decode_logind_prepare_for_sleep(value) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("NSWorkspaceWillSleepNotification", "sleep"),
        ("NSWorkspaceDidWakeNotification", "wake"),
        ("NSWorkspaceScreensDidSleepNotification", None),
        ("NSWorkspaceScreensDidWakeNotification", None),
        ("unrelated", None),
    ],
)
def test_decodes_only_device_sleep_and_wake_notifications(name, expected):
    assert decode_macos_workspace_notification(name) == expected


def test_linux_logind_monitor_subscribes_and_disconnects(monkeypatch):
    monkeypatch.setattr(power_events.sys, "platform", "linux")
    received = []

    class Connection:
        def __init__(self):
            self.connected = []
            self.disconnected = []

        def isConnected(self):
            return True

        def connect(self, *args):
            self.connected.append(args)
            return True

        def disconnect(self, *args):
            self.disconnected.append(args)
            return True

    connection = Connection()
    monkeypatch.setattr(power_events, "_linux_logind_system_bus", lambda: connection)
    monitor = install_linux_logind_power_event_monitor(object(), received.append)
    assert monitor is not None
    assert len(connection.connected) == 1
    receiver = connection.connected[0][-2]
    receiver.handle_prepare_for_sleep(True)
    receiver.handle_prepare_for_sleep(False)
    receiver.handle_prepare_for_sleep(1)
    assert received == ["sleep", "wake"]

    monitor.stop()
    assert connection.disconnected == connection.connected


def test_linux_logind_monitor_fails_open_without_system_bus(monkeypatch):
    monkeypatch.setattr(power_events.sys, "platform", "linux")

    class Connection:
        @staticmethod
        def isConnected():
            return False

    monkeypatch.setattr(power_events, "_linux_logind_system_bus", lambda: Connection())
    assert install_linux_logind_power_event_monitor(object(), lambda _event: None) is None


def test_linux_logind_monitor_is_unavailable_off_linux(monkeypatch):
    monkeypatch.setattr(power_events.sys, "platform", "darwin")
    assert install_linux_logind_power_event_monitor(object(), lambda _event: None) is None


def test_linux_logind_monitor_fails_open_when_subscription_is_rejected(monkeypatch):
    import sys
    from types import ModuleType

    monkeypatch.setattr(power_events.sys, "platform", "linux")
    deleted = []

    class Receiver:
        def deleteLater(self):
            deleted.append(True)

        def handle_prepare_for_sleep(self, _starting):
            pass

    class Connection:
        def isConnected(self):
            return True

        def connect(self, *_args):
            return False

    qtcore = ModuleType("PySide6.QtCore")
    qtcore.QObject = Receiver
    qtcore.Slot = lambda *_args, **_kwargs: lambda method: method
    qtcore.SLOT = lambda _value: object()
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", qtcore)
    monkeypatch.setattr(power_events, "_linux_logind_system_bus", lambda: Connection())
    pyside6 = sys.modules.get("PySide6")
    if pyside6 is not None:
        monkeypatch.setattr(pyside6, "QtCore", qtcore, raising=False)

    assert install_linux_logind_power_event_monitor(object(), lambda _event: None) is None
    assert deleted == [True]


def test_macos_workspace_monitor_is_unavailable_off_macos(monkeypatch):
    monkeypatch.setattr(power_events.sys, "platform", "win32")
    assert install_macos_power_event_monitor(object(), lambda _event: None) is None


def test_macos_workspace_monitor_fails_open_without_appkit(monkeypatch):
    import sys

    monkeypatch.setattr(power_events.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "AppKit", None)
    assert install_macos_power_event_monitor(object(), lambda _event: None) is None


def test_macos_workspace_monitor_fails_open_when_observer_init_returns_none(monkeypatch):
    import sys
    from types import ModuleType

    monkeypatch.setattr(power_events.sys, "platform", "darwin")
    registrations = []

    class NotificationCenter:
        def addObserver_selector_name_object_(self, *args):
            registrations.append(args)

    class Workspace:
        @staticmethod
        def notificationCenter():
            return NotificationCenter()

        @staticmethod
        def sharedWorkspace():
            return Workspace()

    class NSObject:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return None

    appkit = ModuleType("AppKit")
    appkit.NSWorkspace = Workspace
    appkit.NSWorkspaceWillSleepNotification = "will-sleep"
    appkit.NSWorkspaceDidWakeNotification = "did-wake"
    foundation = ModuleType("Foundation")
    foundation.NSObject = NSObject
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "Foundation", foundation)

    assert install_macos_power_event_monitor(object(), lambda _event: None) is None
    assert registrations == []


def test_macos_workspace_monitor_forwards_only_device_sleep_and_wake(monkeypatch):
    import sys
    from types import ModuleType

    monkeypatch.setattr(power_events.sys, "platform", "darwin")
    received = []

    class NotificationCenter:
        def __init__(self):
            self.observers = []
            self.removed = []

        def addObserver_selector_name_object_(self, observer, selector, name, obj):
            self.observers.append((observer, selector, name, obj))

        def removeObserver_(self, observer):
            self.removed.append(observer)

    center = NotificationCenter()

    class Workspace:
        @staticmethod
        def sharedWorkspace():
            return Workspace()

        def notificationCenter(self):
            return center

    class NSObject:
        @classmethod
        def alloc(cls):
            return cls()

        def init(self):
            return self

        def initWithCallback_(self, callback):
            self.callback = callback
            return self

    appkit = ModuleType("AppKit")
    appkit.NSWorkspace = Workspace
    appkit.NSWorkspaceWillSleepNotification = "NSWorkspaceWillSleepNotification"
    appkit.NSWorkspaceDidWakeNotification = "NSWorkspaceDidWakeNotification"
    foundation = ModuleType("Foundation")
    foundation.NSObject = NSObject
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "Foundation", foundation)

    monitor = install_macos_power_event_monitor(object(), received.append)
    assert monitor is not None
    assert [entry[2] for entry in center.observers] == [
        "NSWorkspaceWillSleepNotification",
        "NSWorkspaceDidWakeNotification",
    ]
    observer = center.observers[0][0]
    observer.willSleep_(None)
    observer.didWake_(None)
    assert received == ["sleep", "wake"]
    monitor.stop()
    assert center.removed == [observer]


def test_platform_power_monitor_dispatches_by_operating_system(monkeypatch):
    app = object()
    callback = lambda _event: None
    for platform, attribute in (
        ("win32", "install_windows_power_event_filter"),
        ("darwin", "install_macos_power_event_monitor"),
        ("linux", "install_linux_logind_power_event_monitor"),
    ):
        monkeypatch.setattr(power_events.sys, "platform", platform)
        monkeypatch.setattr(
            power_events,
            attribute,
            lambda app_arg, callback_arg, selected_platform=platform: selected_platform,
        )
        assert install_platform_power_event_monitor(app, callback) == platform

    monkeypatch.setattr(power_events.sys, "platform", "freebsd")
    assert install_platform_power_event_monitor(app, callback) is None
