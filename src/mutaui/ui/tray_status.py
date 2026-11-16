from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from mutaui.services.tray_status import worst_tray_status
from mutaui.ui.localization import set_localized_tooltip


def update_tray_status(
    tray: QSystemTrayIcon,
    icon_for_status: Callable[[str], QIcon],
    snapshot: Any,
    states: Mapping[tuple[str, str], str],
) -> None:
    status = worst_tray_status(
        daemon_online=bool(snapshot.daemon),
        sessions_stale=bool(getattr(snapshot, "sessions_stale", False)),
        states=states.values(),
    )
    set_localized_tooltip(
        tray,
        {
            "issue": "Status: session needs attention",
            "paused": "Status: session paused",
            "busy": "Status: connecting or scanning",
            "healthy": "Status: sessions active",
            "idle": "Status: no sessions",
            "offline": "Status: Mutagen daemon offline",
            "unknown": "Status: session state unknown",
        }[status],
    )
    tray.setIcon(icon_for_status(status))
