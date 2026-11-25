"""Snapshot polling, worker dispatch, and lifecycle mixin for MainWindow."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Any, Literal

from mutagen_client import (
    MutagenClient,
    MutagenCommandTimeout,
    MutagenError,
    MutagenLaunchError,
    Snapshot,
    classify,
    classify_daemon_error,
    conflict_count,
    endpoint_text,
    problem_count,
    read_registration,
    validate_session_rows,
)
from mutaui.services.quiet_hours import quiet_hours_active
from mutaui.services.snapshot_status import (
    compute_daemon_controls,
    compute_overview_scope,
    format_daemon_status,
    format_footer_status,
    format_hero_status,
    format_registration_status,
    format_side_status,
    parse_mutagen_version_output,
)
from mutaui.ui.formatters import _czech_plural
from mutaui.ui.localization import set_localized_text, set_localized_tooltip
from mutaui.ui.preferences import active_language
from mutaui.ui.session_alerts import check_alerts as check_session_alerts
from mutaui.ui.styles.main_stylesheet import AMBER, RED, TEAL
from mutaui.ui.worker import cleanup_worker_dispatcher, submit_background_task


class SnapshotLifecycleMixin:
    """Mixin managing worker thread pools, periodic polling, and snapshot application."""

    _last_snapshot_received_monotonic: float | None = None
    _last_snapshot_notice: str = ""

    def _cleanup_worker_dispatcher(self: Any) -> None:
        cleanup_worker_dispatcher(self)

    def submit(
        self: Any,
        work: Callable[[], Any],
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        submit_background_task(self, work, on_result=on_result, on_error=on_error, on_done=on_done)

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
        app_mod = sys.modules.get("app")
        mutagen_client_cls = (
            getattr(app_mod, "MutagenClient", MutagenClient)
            if app_mod is not None
            and getattr(app_mod, "MutagenClient", MutagenClient) is not MutagenClient
            else MutagenClient
        )
        read_registration_fn = (
            getattr(app_mod, "read_registration", read_registration)
            if app_mod is not None
            and getattr(app_mod, "read_registration", read_registration) is not read_registration
            else read_registration
        )
        binary = self.client.binary
        client = mutagen_client_cls(binary)
        cached_version, cache_at, cache_binary = self._version_cache
        version_valid = cache_binary == binary and time.monotonic() - cache_at < 600

        def work() -> Snapshot:
            snap = Snapshot(binary=client.binary)
            snap.registration, snap.registration_command = read_registration_fn(client.binary)
            if not client.binary:
                snap.daemon = False
                snap.daemon_state = "unconfigured"
                snap.sync_status = "unavailable"
                snap.forward_status = "unavailable"
                snap.error = "Mutagen CLI is not configured. Open Settings."
                return snap

            list_results: dict[
                str,
                tuple[
                    list[dict[str, Any]],
                    Literal["fresh", "stale", "unavailable", "incomplete", "unknown"],
                    str,
                    datetime | None,
                    int,
                ],
            ] = {}
            errors: list[tuple[str, MutagenError]] = []
            for kind in ("sync", "forward"):
                command_started = time.monotonic()
                try:
                    use_checked = hasattr(
                        client, "list_sessions_checked"
                    ) and "list_sessions" not in getattr(client, "__dict__", {})
                    parsed = (
                        client.list_sessions_checked(kind)
                        if use_checked
                        else validate_session_rows(
                            client.list_sessions(kind), allow_all_invalid_error=True
                        )
                    )
                    snap.command_durations[f"{kind} list"] = max(
                        0.0, time.monotonic() - command_started
                    )
                    observed_at = datetime.now().astimezone()
                    kind_status: Literal["fresh", "incomplete"] = (
                        "incomplete" if parsed.incomplete else "fresh"
                    )
                    kind_error = (
                        f"{kind.title()} list incomplete: dropped {parsed.rejected_count} invalid entries."
                        if parsed.incomplete
                        else ""
                    )
                    list_results[kind] = (
                        parsed.sessions,
                        kind_status,
                        kind_error,
                        observed_at,
                        parsed.rejected_count,
                    )
                except MutagenError as exc:
                    snap.command_durations[f"{kind} list"] = max(
                        0.0, time.monotonic() - command_started
                    )
                    errors.append((kind, exc))
                    list_results[kind] = ([], "unavailable", str(exc), None, 0)

            (
                snap.sync,
                snap.sync_status,
                snap.sync_error,
                snap.sync_observed_at,
                snap.sync_incomplete_count,
            ) = list_results["sync"]
            (
                snap.forward,
                snap.forward_status,
                snap.forward_error,
                snap.forward_observed_at,
                snap.forward_incomplete_count,
            ) = list_results["forward"]
            sync_ok = snap.sync_status in ("fresh", "incomplete")
            fwd_ok = snap.forward_status in ("fresh", "incomplete")
            snap.daemon = sync_ok or fwd_ok
            snap.sessions_stale = not (
                snap.sync_status == "fresh" and snap.forward_status == "fresh"
            )
            if snap.daemon:
                snap.daemon_state = "running"
                snap.last_contact_at = snap.sync_observed_at or snap.forward_observed_at
                detail_parts: list[str] = []
                if snap.sync_error:
                    detail_parts.append(
                        snap.sync_error
                        if snap.sync_status == "incomplete"
                        else f"Sync: {snap.sync_error}"
                    )
                if snap.forward_error:
                    detail_parts.append(
                        snap.forward_error
                        if snap.forward_status == "incomplete"
                        else f"Forwarding: {snap.forward_error}"
                    )
                snap.error = "; ".join(detail_parts)
            else:
                if len(errors) == 1:
                    snap.error = str(errors[0][1])
                else:
                    snap.error = "; ".join(
                        f"{'Sync' if kind == 'sync' else 'Forwarding'}: {exc}"
                        for kind, exc in errors
                    )
                if any(
                    isinstance(exc, (MutagenCommandTimeout, MutagenLaunchError))
                    for _, exc in errors
                ):
                    snap.daemon_state = "unavailable"
                else:
                    classified = {classify_daemon_error(str(exc)) for _, exc in errors}
                    snap.daemon_state = "unavailable" if "unavailable" in classified else "stopped"

            if version_valid:
                snap.version = cached_version
                snap.version_status = "cached"
            else:
                try:
                    raw_version = client.get_version()
                    parsed_ver, ver_status, ver_err = parse_mutagen_version_output(raw_version)
                    snap.version_status = ver_status
                    snap.version_error = ver_err
                    if ver_status == "fresh":
                        snap.version = parsed_ver
                    else:
                        snap.version = cached_version if cache_binary == binary else ""
                except MutagenError as exc:
                    snap.version_status = "unavailable"
                    snap.version_error = str(exc)
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
            prev_sync_known = (
                self.snapshot.sync_status in ("fresh", "stale", "incomplete")
                or self.snapshot.sync_observed_at is not None
                or bool(self.snapshot.daemon and self.snapshot.sync)
            )
            prev_fwd_known = (
                self.snapshot.forward_status in ("fresh", "stale", "incomplete")
                or self.snapshot.forward_observed_at is not None
                or bool(self.snapshot.daemon and self.snapshot.forward)
            )
            if snap.sync_status == "unavailable" and prev_sync_known:
                snap.sync = list(self.snapshot.sync)
                snap.sync_observed_at = self.snapshot.sync_observed_at
                snap.sync_status = "stale"
            if snap.forward_status == "unavailable" and prev_fwd_known:
                snap.forward = list(self.snapshot.forward)
                snap.forward_observed_at = self.snapshot.forward_observed_at
                snap.forward_status = "stale"
            if snap.last_contact_at is None:
                snap.last_contact_at = self.snapshot.last_contact_at
            if snap.daemon:
                snap.sessions_stale = not (
                    snap.sync_status == "fresh" and snap.forward_status == "fresh"
                )
            else:
                snap.sessions_stale = snap.sync_status in (
                    "stale",
                    "incomplete",
                ) or snap.forward_status in ("stale", "incomplete")
            snap.resource_observed_at = self.snapshot.resource_observed_at
            snap.command_durations = dict(snap.command_durations)
        self.snapshot = snap
        if hasattr(self, "diagnostics_view"):
            self.update_diagnostics(snap)
        if snap.daemon:
            self.adaptive_policy.observe(snap)
        self.update_polling_mode()
        if snap.version and snap.binary and snap.version_status in ("fresh", "unknown"):
            current_version, cached_at, cached_binary = self._version_cache
            if (
                snap.version != current_version
                or snap.binary != cached_binary
                or time.monotonic() - cached_at >= 600
            ):
                self._version_cache = (snap.version, time.monotonic(), snap.binary)
        if not self.demo and snap.daemon and snap.forward_status in ("fresh", "incomplete"):
            self.traffic_rates = self.traffic_meter.update(snap.forward)
            self._traffic_sample_pending = True
        if not self.demo:
            self.check_alerts(snap)
        if not self.demo:
            self.poll_backoff.observe(bool(snap.daemon))

        duration_ms = (
            (time.monotonic() - self._poll_started_at) * 1000 if self._poll_started_at else 0
        )
        retry_seconds = self.poll_backoff.remaining()
        refreshed_time = datetime.now().strftime("%H:%M:%S")
        overview = compute_overview_scope(
            snap,
            classify,
            retry_seconds=retry_seconds,
            duration_ms=duration_ms,
            refreshed_time=refreshed_time,
        )

        if not self.demo and hasattr(self, "add_log"):
            notice_parts: list[str] = []
            if snap.sync_status == "incomplete" and snap.sync_error:
                notice_parts.append(snap.sync_error)
            if snap.forward_status == "incomplete" and snap.forward_error:
                notice_parts.append(snap.forward_error)
            if snap.version_status in ("invalid", "unavailable") and snap.version_error:
                notice_parts.append(f"Version check: {snap.version_error}")
            notice = "; ".join(notice_parts)
            if notice and notice != self._last_snapshot_notice:
                self._last_snapshot_notice = notice
                self.add_log(notice)
            elif not notice:
                self._last_snapshot_notice = ""

        if self.demo:
            set_localized_text(self.updated, "DEMO DATA")
        else:
            set_localized_text(
                self.updated,
                overview.updated_banner.en,
                czech=overview.updated_banner.cs,
            )

        self._version_label_text = snap.version or "Version: unavailable"
        if hasattr(self, "version_label"):
            if snap.version:
                self.version_label.setText(self._version_label_text)
            else:
                set_localized_text(self.version_label, "Version: unavailable")
            if snap.version_error:
                self.version_label.setToolTip(snap.version_error)
            elif snap.version_status == "cached":
                self.version_label.setToolTip("Cached CLI version")
            else:
                self.version_label.setToolTip("")

        reg_text, default_autostart_hint = format_registration_status(
            snap.registration, platform_name=sys.platform
        )
        set_localized_text(self.register_message, reg_text.en, czech=reg_text.cs)
        self.register_message.setToolTip(snap.registration_command or default_autostart_hint)

        side_title, side_sub, side_accent = format_side_status(snap, czech_plural=_czech_plural)
        accent_colors = {"teal": TEAL, "amber": AMBER, "red": RED}
        set_localized_text(self.side_state, side_title.en, czech=side_title.cs)
        self.side_state.setStyleSheet(f"color:{accent_colors.get(side_accent, AMBER)}")
        set_localized_text(self.side_sub, side_sub.en, czech=side_sub.cs)

        hero_title, hero_sub = format_hero_status(snap)
        set_localized_text(self.hero_title, hero_title.en, czech=hero_title.cs)
        set_localized_text(self.hero_sub, hero_sub.en, czech=hero_sub.cs)
        if hasattr(self, "hero_badge"):
            if snap.version:
                self.hero_badge.setText(snap.version)
                self.hero_badge.setVisible(True)
            else:
                self.hero_badge.setVisible(False)

        daemon_title, daemon_desc, daemon_accent = format_daemon_status(snap)
        set_localized_text(self.daemon_title, daemon_title.en, czech=daemon_title.cs)
        self.daemon_title.setStyleSheet(
            f"color:{accent_colors.get(daemon_accent, AMBER)};font-size:22px;font-weight:750"
        )
        set_localized_text(self.daemon_desc, daemon_desc.en, czech=daemon_desc.cs)

        policy = compute_daemon_controls(
            snap, demo=bool(self.demo), pending_action=bool(self.pending_action)
        )
        self.start_button.setEnabled(policy.enable_start)
        self.stop_button.setEnabled(policy.enable_stop)
        if hasattr(self, "daemon_action_hint"):
            set_localized_text(
                self.daemon_action_hint,
                policy.hint.en,
                czech=policy.hint.cs,
            )
        if hasattr(self, "daemon_diagnostics_button"):
            self.daemon_diagnostics_button.setVisible(
                policy.suggest_diagnostics
                or snap.daemon_state in ("stopped", "unavailable", "unconfigured")
            )

        for key, text in overview.metric_values.items():
            self.metric_widgets[key].setText(text)
        if hasattr(self, "overview_scope_label"):
            set_localized_text(
                self.overview_scope_label,
                overview.scope_banner.en,
                czech=overview.scope_banner.cs,
            )
            scope_color = {
                "fresh": TEAL,
                "stale": AMBER,
                "unavailable": RED,
            }.get(overview.scope_severity, AMBER)
            self.overview_scope_label.setStyleSheet(f"color:{scope_color}; font-size:11px;")

        lang = active_language()
        ring_tooltip = overview.ring_detail.cs if lang == "cs" else overview.ring_detail.en
        self.health_ring.set_health(
            overview.ring_total,
            overview.ring_problem,
            scope=overview.ring_scope,
            detail=ring_tooltip,
        )
        set_localized_tooltip(self.health_ring, overview.ring_detail.en)
        self.health_ring.setProperty("mutauiCzechTooltip", overview.ring_detail.cs)
        if lang == "cs":
            self.health_ring.setToolTip(overview.ring_detail.cs)

        running_str = overview.metric_values["running"]
        error_str = overview.metric_values["errors"]
        self.session_counts = (
            int(running_str) if running_str.isdigit() else 0,
            int(error_str) if error_str.isdigit() else 0,
        )

        sync_count = len(snap.sync)
        sync_paused = sum(bool(x.get("paused")) for x in snap.sync)
        sync_form = _czech_plural(sync_count, ("synchronizace", "synchronizace", "synchronizací"))
        set_localized_text(
            self.sync_summary,
            f"{sync_count} sync sessions • {sync_paused} paused · {overview.sync_state_tag.en}",
            czech=f"{sync_count} {sync_form} · {sync_paused} pozastaveno · {overview.sync_state_tag.cs}",
        )
        forward_count = len(snap.forward)
        forward_form = _czech_plural(
            forward_count, ("přesměrování", "přesměrování", "přesměrování")
        )
        set_localized_text(
            self.forward_summary,
            f"{forward_count} forwarding sessions · {overview.forward_state_tag.en}",
            czech=f"{forward_count} {forward_form} · {overview.forward_state_tag.cs}",
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
                    (
                        f"{fwd_total} total · {fwd_active} active · {fwd_open} with open connections"
                        f" · {overview.forward_state_tag.en}"
                    ),
                    czech=(
                        f"{fwd_total} celkem · {fwd_active} aktivní · {fwd_open} s otevřeným spojením"
                        f" · {overview.forward_state_tag.cs}"
                    ),
                )
            else:
                set_localized_text(
                    self.dashboard_forward_summary,
                    f"No forwarding sessions · {overview.forward_state_tag.en}",
                    czech=f"Žádná přesměrování · {overview.forward_state_tag.cs}",
                )

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
        pending_autosafe = getattr(self, "_pending_autosafe_sessions", None)
        if pending_autosafe:
            self._pending_autosafe_sessions: list[str] = []
            succeeded = bool(snap.daemon and not snap.error)
            now = time.monotonic()
            for sid in pending_autosafe:
                with suppress(Exception):
                    self.health_tracker.record_recovery_attempt(
                        sid,
                        action="refresh_status",
                        now=now,
                        succeeded=succeeded,
                    )
        self.update_endpoint_sessions(snap)
        self.update_server_groups()
        footer_text = format_footer_status(snap, demo=bool(self.demo))
        set_localized_text(self.footer, footer_text.en, czech=footer_text.cs)

    def check_alerts(self: Any, snap: Snapshot) -> None:
        check_session_alerts(
            self,
            snap,
            classify_session=classify,
            quiet_hours=quiet_hours_active,
        )
