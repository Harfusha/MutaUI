"""Snapshot polling, worker dispatch, and lifecycle mixin for MainWindow."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QTimer

from mutagen_client import (
    MutagenClient,
    MutagenError,
    Snapshot,
    classify,
    conflict_count,
    endpoint_text,
    problem_count,
    read_registration,
)
from mutaui.services.quiet_hours import quiet_hours_active
from mutaui.ui.formatters import _czech_plural
from mutaui.ui.localization import set_localized_text
from mutaui.ui.preferences import translate_text
from mutaui.ui.session_alerts import check_alerts as check_session_alerts
from mutaui.ui.styles.main_stylesheet import AMBER, RED, TEAL
from mutaui.ui.worker import Worker


class SnapshotLifecycleMixin:
    """Mixin managing worker thread pools, periodic polling, and snapshot application."""

    def submit(
        self: Any,
        work: Callable[[], Any],
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        if self._shutdown_pending:
            return
        worker = Worker(work)
        self.workers.add(worker)

        def deliver_result(result: Any) -> None:
            if on_result and not self._shutdown_pending:
                on_result(result)

        def deliver_error(message: str) -> None:
            if not self._shutdown_pending:
                (on_error or self.report_error)(message)

        worker.signals.result.connect(deliver_result)
        worker.signals.error.connect(deliver_error)

        def finished() -> None:
            self.workers.discard(worker)
            if on_done and not self._shutdown_pending:
                on_done()
            if self._shutdown_pending and not self.workers:
                QTimer.singleShot(0, self.close)

        worker.signals.finished.connect(finished)
        self.pool.start(worker)

    def refresh(self: Any, *, force: bool = False) -> None:
        if not self.demo and not self.poll_backoff.can_retry(force):
            return
        if self.demo:
            self.apply_snapshot(self.snapshot)
            return
        if self.pending_poll:
            if force:
                self._refresh_generation += 1
                self._refresh_again = True
            return
        if self.pending_action:
            return
        self.pending_poll = True
        self._refresh_generation += 1
        generation = self._refresh_generation
        self._poll_started_at = time.monotonic()
        binary = self.client.binary
        client = MutagenClient(binary)
        cached_version, cache_at, cache_binary = self._version_cache
        version_valid = cache_binary == binary and time.monotonic() - cache_at < 600

        def work() -> Snapshot:
            snap = Snapshot(binary=client.binary)
            snap.registration, snap.registration_command = read_registration(client.binary)
            if not client.binary:
                snap.error = "mutagen.exe is not configured. Open Settings."
                return snap
            try:
                command_started = time.monotonic()
                snap.sync = client.list_sessions("sync")
                snap.command_durations["sync list"] = max(0.0, time.monotonic() - command_started)
                snap.sync_observed_at = datetime.now().astimezone()
                snap.daemon = True
            except MutagenError as exc:
                snap.command_durations["sync list"] = max(0.0, time.monotonic() - command_started)
                snap.error = str(exc)
                return snap
            try:
                command_started = time.monotonic()
                snap.forward = client.list_sessions("forward")
                snap.command_durations["forward list"] = max(
                    0.0, time.monotonic() - command_started
                )
                snap.forward_observed_at = datetime.now().astimezone()
            except MutagenError as exc:
                snap.command_durations["forward list"] = max(
                    0.0, time.monotonic() - command_started
                )
                snap.error = "Forwarding: " + str(exc)
                snap.sessions_stale = True
            if version_valid:
                snap.version = cached_version
            else:
                try:
                    snap.version = client.get_version().splitlines()[0]
                except MutagenError:
                    snap.version = cached_version if cache_binary == binary else ""
            return snap

        def apply_if_current(snap: Snapshot) -> None:
            if generation == self._refresh_generation:
                self.apply_snapshot(snap, generation=generation)

        def finish_poll() -> None:
            self.pending_poll = False
            if self._refresh_again:
                self._refresh_again = False
                self.refresh(force=True)
            else:
                self._complete_pending_launch_requests()

        self.submit(
            work,
            apply_if_current,
            on_error=lambda message: (
                self.report_error(message) if generation == self._refresh_generation else None
            ),
            on_done=finish_poll,
        )

    def apply_snapshot(self: Any, snap: Snapshot, *, generation: int | None = None) -> None:
        if generation is not None and generation != self._refresh_generation:
            return
        received_at = time.monotonic()
        if (
            self._last_snapshot_received_monotonic is not None
            and received_at - self._last_snapshot_received_monotonic > 180
        ):
            self.health_tracker.note_environment_event("wake", now=received_at)
        self._last_snapshot_received_monotonic = received_at
        if not self.demo:
            snap.cpu, snap.memory, snap.processes = (
                self.snapshot.cpu,
                self.snapshot.memory,
                self.snapshot.processes,
            )
        if not self.demo and snap.binary == self.snapshot.binary:
            if not snap.daemon:
                snap.sync = list(self.snapshot.sync)
                snap.forward = list(self.snapshot.forward)
                snap.sync_observed_at = self.snapshot.sync_observed_at
                snap.forward_observed_at = self.snapshot.forward_observed_at
                snap.sessions_stale = self.snapshot.daemon or self.snapshot.sessions_stale
            elif snap.sessions_stale:
                snap.forward = list(self.snapshot.forward)
                snap.forward_observed_at = self.snapshot.forward_observed_at
            snap.resource_observed_at = self.snapshot.resource_observed_at
            snap.command_durations = dict(snap.command_durations)
        self.snapshot = snap
        if hasattr(self, "diagnostics_view"):
            self.update_diagnostics(snap)
        if snap.daemon:
            self.adaptive_policy.observe(snap)
        self.update_polling_mode()
        if snap.version and snap.binary:
            current_version, cached_at, cached_binary = self._version_cache
            if (
                snap.version != current_version
                or snap.binary != cached_binary
                or time.monotonic() - cached_at >= 600
            ):
                self._version_cache = (snap.version, time.monotonic(), snap.binary)
        if not self.demo and snap.daemon and not snap.sessions_stale:
            self.traffic_rates = self.traffic_meter.update(snap.forward)
            self._traffic_sample_pending = True
        if not self.demo:
            self.check_alerts(snap)
        if not self.demo:
            self.poll_backoff.observe(bool(snap.daemon))
        duration_ms = (
            (time.monotonic() - self._poll_started_at) * 1000 if self._poll_started_at else 0
        )
        if self.demo:
            set_localized_text(self.updated, "DEMO DATA")
        else:
            retry_seconds = self.poll_backoff.remaining()
            if snap.daemon and not snap.sessions_stale:
                refreshed_time = datetime.now().strftime("%H:%M:%S")
                english = f"Refreshed {refreshed_time}  ·  CLI {duration_ms:.0f} ms"
                czech = translate_text("Refreshed {time} · CLI {duration} ms", "cs").format(
                    time=refreshed_time, duration=f"{duration_ms:.0f}"
                )
            elif snap.daemon:
                detail = snap.error or "session data is stale"
                english = f"Showing last successful sessions · {detail}"
                czech = translate_text("Showing last successful sessions · {detail}", "cs").format(
                    detail=detail
                )
            elif snap.sessions_stale:
                english = (
                    "Daemon offline · showing last successful sessions · "
                    f"retrying in {retry_seconds:.0f} s"
                )
                czech = translate_text(
                    "Daemon offline · showing last successful sessions · retrying in {seconds} s",
                    "cs",
                ).format(seconds=f"{retry_seconds:.0f}")
            else:
                english = f"Daemon offline · retrying in {retry_seconds:.0f} s"
                czech = translate_text("Daemon offline · retrying in {seconds} s", "cs").format(
                    seconds=f"{retry_seconds:.0f}"
                )
            set_localized_text(self.updated, english, czech=czech)
        self._version_label_text = snap.version or "Version: unavailable"
        if hasattr(self, "version_label"):
            if snap.version:
                self.version_label.setText(self._version_label_text)
            else:
                set_localized_text(self.version_label, "Version: unavailable")
        regtexts = {
            "registered": "Auto-start: registered for this installation",
            "unregistered": "Auto-start: not registered",
            "other": "Auto-start: entry points to another installation/command",
            "unknown": "Auto-start: status unknown",
            "unsupported": "Auto-start: detection is available on Windows only",
        }
        registration_en = regtexts.get(snap.registration, "Registration: unknown")
        registration_cs = {
            "registered": "Automatické spuštění: registrováno pro tuto instalaci",
            "unregistered": "Automatické spuštění: není registrováno",
            "other": "Automatické spuštění: položka odkazuje na jinou instalaci nebo příkaz",
            "unknown": "Automatické spuštění: stav není známý",
            "unsupported": "Automatické spuštění: zjištění je dostupné pouze ve Windows",
        }.get(snap.registration, "Registrace: stav není známý")
        set_localized_text(self.register_message, registration_en, czech=registration_cs)
        autostart_hints = {"win32": "Registry entry in HKCU\\...\\Run\\Mutagen"}
        default_autostart_hint = autostart_hints.get(
            sys.platform, "launchd (macOS) or systemd --user / XDG (Linux)"
        )
        self.register_message.setToolTip(snap.registration_command or default_autostart_hint)
        available = bool(snap.binary)
        if not available:
            set_localized_text(self.side_state, "●  Mutagen CLI not found")
            self.side_state.setStyleSheet(f"color:{RED}")
            set_localized_text(self.side_sub, "Select mutagen.exe in Settings")
        elif snap.daemon:
            set_localized_text(self.side_state, "●  Daemon online")
            self.side_state.setStyleSheet(f"color:{TEAL}")
            sync_count = len(snap.sync)
            forward_count = len(snap.forward)
            sync_noun = "sync" if sync_count == 1 else "syncs"
            forward_noun = "port forward" if forward_count == 1 else "port forwards"
            summary_en = f"{sync_count} {sync_noun} · {forward_count} {forward_noun}"
            sync_form = _czech_plural(
                sync_count,
                ("relace", "relace", "relací"),
            )
            forward_form = _czech_plural(
                forward_count,
                ("přesměrování", "přesměrování", "přesměrování"),
            )
            summary_cs = f"{sync_count} {sync_form} · {forward_count} {forward_form}"
            set_localized_text(self.side_sub, summary_en, czech=summary_cs)
        else:
            set_localized_text(self.side_state, "●  Daemon offline")
            self.side_state.setStyleSheet(f"color:{AMBER}")
            set_localized_text(self.side_sub, (snap.error or "Not running yet")[:120])
        set_localized_text(
            self.hero_title, "Daemon is running" if snap.daemon else "Daemon is unavailable"
        )
        set_localized_text(
            self.hero_sub,
            "Sync runs in the background. The application monitors its status."
            if snap.daemon
            else "Go to the Daemon page to start the service or open Settings.",
        )
        if hasattr(self, "hero_badge"):
            if snap.version:
                self.hero_badge.setText(snap.version)
                self.hero_badge.setVisible(True)
            else:
                self.hero_badge.setVisible(False)
        set_localized_text(
            self.daemon_title,
            "●  Running" if snap.daemon else "●  Unavailable / stopped",
            czech="●  Spuštěno" if snap.daemon else "●  Nedostupná / zastavená",
        )
        self.daemon_title.setStyleSheet(
            f"color:{TEAL if snap.daemon else AMBER};font-size:22px;font-weight:750"
        )
        if snap.daemon:
            description_en = (
                "Daemon responded; " + snap.error if snap.error else "Daemon is responding."
            )
            description_cs = (
                "Služba Mutagen odpověděla; " + snap.error
                if snap.error
                else "Služba Mutagen odpovídá."
            )
        else:
            description_en = snap.error or "Daemon is not running."
            description_cs = snap.error or "Služba Mutagen není spuštěna."
        set_localized_text(self.daemon_desc, description_en, czech=description_cs)
        for b in (self.start_button, self.stop_button):
            b.setEnabled(not self.demo and available and not self.pending_action)
        all_sessions = [("sync", x) for x in snap.sync] + [("forward", x) for x in snap.forward]
        kinds = [classify(x, k)[0] for k, x in all_sessions]
        self.metric_widgets["all"].setText(str(len(all_sessions)))
        self.metric_widgets["running"].setText(str(sum(s in ("active", "busy") for s in kinds)))
        self.metric_widgets["paused"].setText(str(kinds.count("paused")))
        self.metric_widgets["errors"].setText(str(kinds.count("error")))
        self.health_ring.set_health(len(kinds), kinds.count("error"))
        self.session_counts = (sum(s in ("active", "busy") for s in kinds), kinds.count("error"))
        sync_count = len(snap.sync)
        sync_paused = sum(bool(x.get("paused")) for x in snap.sync)
        sync_form = _czech_plural(sync_count, ("synchronizace", "synchronizace", "synchronizací"))
        set_localized_text(
            self.sync_summary,
            f"{sync_count} sync sessions • {sync_paused} paused",
            czech=f"{sync_count} {sync_form} · {sync_paused} pozastaveno",
        )
        forward_count = len(snap.forward)
        forward_form = _czech_plural(
            forward_count, ("přesměrování", "přesměrování", "přesměrování")
        )
        set_localized_text(
            self.forward_summary,
            f"{forward_count} forwarding sessions • data and active connections in details",
            czech=f"{forward_count} {forward_form} · data a aktivní spojení v podrobnostech",
        )
        if hasattr(self, "dashboard_forward_summary"):
            fwd_active = sum(
                1 for s in snap.forward if classify(s, "forward")[0] in ("active", "busy")
            )
            fwd_total = len(snap.forward)
            if fwd_total:
                fwd_open = sum(1 for s in snap.forward if s.get("openConnections", 0) > 0)
                set_localized_text(
                    self.dashboard_forward_summary,
                    f"{fwd_total} total · {fwd_active} active · {fwd_open} with open connections",
                    czech=f"{fwd_total} celkem · {fwd_active} aktivní · {fwd_open} s otevřeným spojením",
                )
            else:
                set_localized_text(self.dashboard_forward_summary, "No forwarding sessions")
        for kind, sessions, table in (
            ("sync", snap.sync, self.sync_table),
            ("forward", snap.forward, self.forward_table),
            ("dashboard", snap.sync[:5], self.dashboard_table),
        ):
            actual_kind = "sync" if kind == "dashboard" else kind
            signature = tuple(
                (
                    s.get("identifier"),
                    s.get("name"),
                    s.get("paused"),
                    s.get("status"),
                    s.get("lastError"),
                    conflict_count(s) if actual_kind == "sync" else s.get("openConnections"),
                    problem_count(s) if actual_kind == "sync" else 0,
                    endpoint_text(
                        s.get("alpha" if actual_kind == "sync" else "source"), actual_kind
                    ),
                    endpoint_text(
                        s.get("beta" if actual_kind == "sync" else "destination"), actual_kind
                    ),
                    s.get("identifier") in self.favorites[actual_kind],
                )
                for s in sessions
            )
            if signature != self._table_signatures.get(kind):
                self.fill_table(table, sessions, actual_kind, dashboard=kind == "dashboard")
                self._table_signatures[kind] = signature
                if kind != "dashboard":
                    self.filter_table(kind)
        page = self.pages.currentIndex()
        if page in (1, 2):
            self.refresh_detail("sync" if page == 1 else "forward")
        if page == 7:
            self.update_diagnostics(snap)
        self.update_endpoint_sessions(snap)
        self.update_server_groups()
        if self.demo:
            set_localized_text(self.footer, "DEMO • All actions are disabled")
        else:
            self.footer.setText(
                "Connected to " + snap.binary if available else "Select a Mutagen installation"
            )

    def check_alerts(self: Any, snap: Snapshot) -> None:
        check_session_alerts(
            self,
            snap,
            classify_session=classify,
            quiet_hours=quiet_hours_active,
        )
