"""macOS native power event monitor via NSWorkspace notifications."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, Literal

PowerEvent = Literal["sleep", "wake"]


def install_macos_power_event_monitor(
    application: Any, callback: Callable[[PowerEvent], None]
) -> Any | None:
    """Observe device sleep/wake through NSWorkspace's workspace notification center."""
    del application  # NSWorkspace notifications are delivered by AppKit's main run loop.
    if sys.platform != "darwin":
        return None

    try:
        from AppKit import (
            NSWorkspace,
            NSWorkspaceDidWakeNotification,
            NSWorkspaceWillSleepNotification,
        )
        from Foundation import NSObject
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
