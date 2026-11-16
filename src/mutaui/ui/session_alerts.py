from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtWidgets import QSystemTrayIcon

from mutaui.services.session_notification_gate import SessionNotificationGate
from mutaui.ui.preferences import active_language, translate_text


def check_alerts(
    window: Any,
    snapshot: Any,
    *,
    classify_session: Callable[[Any, str], tuple[str, Any]],
    quiet_hours: Callable[..., bool],
) -> None:
    import insights

    if window.previous_daemon is not None and window.previous_daemon != snapshot.daemon:
        window.add_log(
            "Daemon is responding again" if snapshot.daemon else "WARNING: Daemon is not responding"
        )
    window.previous_daemon = snapshot.daemon
    if not snapshot.daemon:
        updater = getattr(window, "update_tray_status", None)
        if updater is not None:
            updater(snapshot, {})
        return

    new_states: Any = {
        (kind, sess.get("identifier")): classify_session(sess, kind)[0]
        for kind, group in (("sync", snapshot.sync), ("forward", snapshot.forward))
        for sess in group
    }
    updater = getattr(window, "update_tray_status", None)
    if updater is not None:
        updater(snapshot, new_states)
    if window.previous_states is not None:
        for kind, identifier, previous, state in insights.state_transitions(
            window.previous_states, new_states
        ):
            group = snapshot.sync if kind == "sync" else snapshot.forward
            sess: Any = next((s for s in group if s.get("identifier") == identifier), {})
            title = sess.get("name") or str(identifier)[:14]
            if state == "error":
                message = f"WARNING: Session {title} needs attention"
            elif previous == "error":
                message = f"Session {title} recovered ({state})"
            elif state == "paused":
                message = f"Session {title} was paused"
            elif previous == "paused":
                message = f"Session {title} resumed"
            else:
                message = f"Session {title}: {previous} → {state}"
            window.add_log(message)

    eligible_errors = {}
    for kind, group in (("sync", snapshot.sync), ("forward", snapshot.forward)):
        for sess in group:
            identifier = sess.get("identifier")
            key = (kind, str(identifier))
            session_notifications = (
                window.conf.get("session_prefs", {})
                .get(str(identifier), {})
                .get("notifications", True)
            )
            if new_states.get(key) == "error" and session_notifications:
                eligible_errors[key] = sess.get("name") or str(identifier)[:14]

    notifications_allowed = bool(window.conf.get("alerts", True)) and window.tray.isVisible()
    if notifications_allowed:
        notifications_allowed = not quiet_hours(
            datetime.now(),
            enabled=bool(window.conf.get("quiet_hours_enabled", False)),
            start=str(window.conf.get("quiet_hours_start", "22:00")),
            end=str(window.conf.get("quiet_hours_end", "07:00")),
        )
    gate = getattr(window, "session_notification_gate", None)
    if gate is None:
        gate = SessionNotificationGate()
        window.session_notification_gate = gate
    desktop_messages = []
    desktop_keys: list[tuple[str, str]] = []
    has_issue = False
    for notification in gate.update(
        eligible_errors,
        now=time.monotonic(),
        notifications_allowed=notifications_allowed,
    ):
        eligible = [
            (key, title)
            for key, title in zip(notification.session_keys, notification.titles, strict=True)
            if (window.conf.get("session_prefs", {}).get(key[1], {}).get("notifications", True))
        ]
        if not eligible:
            continue
        desktop_keys.extend(key for key, _title in eligible)
        titles = tuple(title for _key, title in eligible)
        if notification.kind == "issue":
            has_issue = True
            if len(titles) == 1:
                message = translate_text(
                    "Session needs attention: {title}", active_language()
                ).format(title=titles[0])
            else:
                message = translate_text(
                    "Number of sessions needing attention: {count}", active_language()
                ).format(count=len(titles))
        else:
            if len(titles) == 1:
                message = translate_text("Session recovered: {title}", active_language()).format(
                    title=titles[0]
                )
            else:
                message = translate_text(
                    "Number of recovered sessions: {count}", active_language()
                ).format(count=len(titles))
        desktop_messages.append(message)
    if desktop_messages:
        window._last_notification_session_keys = tuple(dict.fromkeys(desktop_keys))
        window.tray.showMessage(
            translate_text("Mutagen Control — Issue", active_language()),
            "\n".join(desktop_messages),
            QSystemTrayIcon.MessageIcon.Warning
            if has_issue
            else QSystemTrayIcon.MessageIcon.Information,
            7000,
        )
    window.previous_states = new_states
