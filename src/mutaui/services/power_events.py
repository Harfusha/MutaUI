"""Native operating-system power event adapters."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any, Literal

PowerEvent = Literal["sleep", "wake"]

_LOGIND_SERVICE = "org.freedesktop.login1"
_LOGIND_PATH = "/org/freedesktop/login1"
_LOGIND_INTERFACE = "org.freedesktop.login1.Manager"
_LOGIND_SIGNAL = "PrepareForSleep"


def decode_windows_power_broadcast(message_id: int) -> PowerEvent | None:
    """Map documented Windows suspend/resume messages to health events."""
    if message_id == 0x0004:  # PBT_APMSUSPEND
        return "sleep"
    if message_id in (0x0006, 0x0007, 0x0012):  # critical, suspend, automatic resume
        return "wake"
    return None


def install_windows_power_event_filter(
    application: Any, callback: Callable[[PowerEvent], None]
) -> Any | None:
    """Install a retained Qt native filter on Windows; return None elsewhere."""
    if sys.platform != "win32":
        return None

    from PySide6.QtCore import QAbstractNativeEventFilter

    class WindowsPowerEventFilter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, event_type: Any, message: Any) -> tuple[bool, int]:
            del event_type
            message_id = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents.message
            event = decode_windows_power_broadcast(message_id)
            if event is not None:
                callback(event)
            return False, 0

    event_filter = WindowsPowerEventFilter()
    application.installNativeEventFilter(event_filter)
    return event_filter


def decode_logind_prepare_for_sleep(starting: object) -> PowerEvent | None:
    """Map logind's PrepareForSleep boolean to a sleep/wake event."""
    if not isinstance(starting, bool):
        return None
    return "sleep" if starting else "wake"


def decode_macos_workspace_notification(name: str) -> PowerEvent | None:
    """Map device sleep/wake notifications, excluding display-only events."""
    if name == "NSWorkspaceWillSleepNotification":
        return "sleep"
    if name == "NSWorkspaceDidWakeNotification":
        return "wake"
    return None


def _linux_logind_system_bus() -> Any:
    from PySide6.QtDBus import QDBusConnection

    return QDBusConnection.systemBus()


def install_linux_logind_power_event_monitor(
    application: Any, callback: Callable[[PowerEvent], None]
) -> Any | None:
    """Observe logind sleep preparation over the system bus without inhibiting sleep."""
    del application  # QDBusConnection delivers its QObject slot through Qt's main loop.
    if not sys.platform.startswith("linux"):
        return None

    from PySide6.QtCore import SLOT, QObject, Slot

    connection = _linux_logind_system_bus()
    if not connection.isConnected():
        return None

    class LogindPowerReceiver(QObject):
        @Slot(bool, name="handlePrepareForSleep")
        def handle_prepare_for_sleep(self, starting: bool) -> None:
            event = decode_logind_prepare_for_sleep(starting)
            if event is not None:
                callback(event)

    receiver = LogindPowerReceiver()
    slot = SLOT("handlePrepareForSleep(bool)")
    args = (
        _LOGIND_SERVICE,
        _LOGIND_PATH,
        _LOGIND_INTERFACE,
        _LOGIND_SIGNAL,
        "b",
        receiver,
        slot,
    )
    if not connection.connect(*args):
        receiver.deleteLater()
        return None

    class LogindPowerMonitor:
        def stop(self) -> None:
            connection.disconnect(*args)
            receiver.deleteLater()

    return LogindPowerMonitor()


def install_macos_power_event_monitor(
    application: Any, callback: Callable[[PowerEvent], None]
) -> Any | None:
    """Observe device sleep/wake through NSWorkspace's workspace notification center."""
    del application  # NSWorkspace notifications are delivered by AppKit's main run loop.
    if sys.platform != "darwin":
        return None

    try:
        from AppKit import (  # type: ignore[import-not-found]
            NSWorkspace,
            NSWorkspaceDidWakeNotification,
            NSWorkspaceWillSleepNotification,
        )
        from Foundation import NSObject  # type: ignore[import-not-found]
    except ImportError:
        return None

    class WorkspacePowerObserver(NSObject):  # type: ignore[misc]
        _event_callback: Callable[[PowerEvent], None]

        def initWithCallback_(self, event_callback: Callable[[PowerEvent], None]) -> Any:
            self = super().init()
            if self is not None:
                self._event_callback = event_callback
            return self

        def willSleep_(self, _notification: Any) -> None:
            self._event_callback("sleep")

        def didWake_(self, _notification: Any) -> None:
            self._event_callback("wake")

    workspace = NSWorkspace.sharedWorkspace()
    center = workspace.notificationCenter()
    observer = WorkspacePowerObserver.alloc().initWithCallback_(callback)
    if observer is None:
        return None
    center.addObserver_selector_name_object_(
        observer, "willSleep:", NSWorkspaceWillSleepNotification, None
    )
    center.addObserver_selector_name_object_(
        observer, "didWake:", NSWorkspaceDidWakeNotification, None
    )

    class WorkspacePowerMonitor:
        def stop(self) -> None:
            center.removeObserver_(observer)

    return WorkspacePowerMonitor()


def install_platform_power_event_monitor(
    application: Any, callback: Callable[[PowerEvent], None]
) -> Any | None:
    """Install the native power event source supported by the current desktop OS."""
    if sys.platform == "win32":
        return install_windows_power_event_filter(application, callback)
    if sys.platform == "darwin":
        return install_macos_power_event_monitor(application, callback)
    if sys.platform.startswith("linux"):
        return install_linux_logind_power_event_monitor(application, callback)
    return None
