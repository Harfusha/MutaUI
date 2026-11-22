"""Diagnostics and Session Doctor mixin for MainWindow."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from functools import partial
from html import escape as html_escape
from pathlib import Path
from typing import Any, Literal

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from insights import local_self_check, safe_diagnostic_report, session_log_report
from mutagen_client import Snapshot, human_bytes
from mutaui import __version__ as APP_VERSION
from mutaui.adapters.mutagen_snapshot import from_session_dict
from mutaui.services.health_tracker import HealthObservation
from mutaui.services.session_doctor import (
    FRESHNESS_SECONDS,
    SessionDoctorContext,
    diagnose_sessions,
)
from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog
from mutaui.ui.localization import set_localized_text, set_localized_tooltip
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.support_bundle_dialog import SupportBundleDialog
from mutaui.ui.theme_constants import AMBER, RED, TEAL, TEXT
from mutaui.ui.troubleshooter_dialog import TroubleshooterDialog
from mutaui.ui.widgets.basic import button, card, label, localized_label
from settings import settings_path


class DiagnosticsMixin:
    _doctor_observation_key: tuple[datetime | None, datetime | None] | None = None
    _doctor_previous_issue_count: int | None = None
    _doctor_current_issue_count: int | None = None

    def diagnostics_page(self: Any) -> QWidget:
        root = QWidget()
        root.setObjectName("main")
        l = QVBoxLayout(root)
        l.setContentsMargins(0, 3, 0, 0)
        l.setSpacing(16)
        card1, vl = card()
        head = QHBoxLayout()
        head.addWidget(label("Diagnostics Overview", size=17, bold=True))
        head.addStretch()
        troubleshoot_btn = button("Troubleshoot…", self.open_troubleshooter)
        set_localized_text(troubleshoot_btn, "Troubleshoot…", czech="Řešení potíží…")
        set_localized_tooltip(
            troubleshoot_btn, "Analyze sync failures and guide step-by-step resolution"
        )
        head.addWidget(troubleshoot_btn)
        conflicts_btn = button("Conflict Inspector", self.open_conflict_inspector)
        set_localized_text(conflicts_btn, "Conflict Inspector", czech="Přehled konfliktů")
        set_localized_tooltip(conflicts_btn, "Inspect file conflicts between endpoints")
        head.addWidget(conflicts_btn)
        full_btn = button("Support Bundle", self.open_support_bundle, kind="primary")
        set_localized_text(full_btn, "Support Bundle", czech="Balíček podpory")
        support_tooltip = "Export diagnostic reports, session snapshots, or logs"
        support_tooltip_cs = "Exportovat diagnostický report, snímek relací nebo protokoly"
        full_btn.setProperty("mutauiSourceTooltip", support_tooltip)
        full_btn.setProperty("mutauiCzechTooltip", support_tooltip_cs)
        full_btn.setToolTip(support_tooltip_cs if active_language() == "cs" else support_tooltip)
        head.addWidget(full_btn)
        copy_btn = button("Copy Summary", self.copy_diagnostics)
        set_localized_tooltip(copy_btn, "Copies the diagnostic summary to the clipboard")
        head.addWidget(copy_btn)
        vl.addLayout(head)
        note_lbl = label(
            "Diagnostics help troubleshoot session issues. Use Support Bundle to create exportable reports.",
            muted=True,
        )
        note_lbl.setWordWrap(True)
        vl.addWidget(note_lbl)
        self.diag_summary = localized_label("Waiting for data…")
        self.diag_summary.setWordWrap(True)
        self.diag_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.diag_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vl.addWidget(self.diag_summary)

        hub_row = QHBoxLayout()
        hub_row.setSpacing(10)
        hub_row.addWidget(label("Related tools:", muted=True, size=11))

        daemon_btn = button("Daemon (Ctrl+5) →", partial(self.set_page, 4))
        set_localized_text(daemon_btn, "Daemon (Ctrl+5) →", czech="Daemon (Ctrl+5) →")
        set_localized_tooltip(daemon_btn, "Open Mutagen daemon management and registration")
        hub_row.addWidget(daemon_btn)

        history_btn = button("Action History (Ctrl+4) →", partial(self.set_page, 3))
        set_localized_text(
            history_btn, "Action History (Ctrl+4) →", czech="Historie akcí (Ctrl+4) →"
        )
        set_localized_tooltip(history_btn, "View records of commands executed by this application")
        hub_row.addWidget(history_btn)

        monitoring_btn = button("Monitoring (Ctrl+7) →", partial(self.set_page, 6))
        set_localized_text(monitoring_btn, "Monitoring (Ctrl+7) →", czech="Monitoring (Ctrl+7) →")
        set_localized_tooltip(monitoring_btn, "View historical resource usage and process graphs")
        hub_row.addWidget(monitoring_btn)

        hub_row.addStretch()
        vl.addLayout(hub_row)
        l.addWidget(card1)
        problems, pl = card()
        problems_head = QHBoxLayout()
        problems_head.addWidget(label("Conflicts, Errors, and Issues", size=16, bold=True))
        problems_head.addStretch()
        self.diag_problem_count = label("", muted=True, size=11)
        problems_head.addWidget(self.diag_problem_count)
        pl.addLayout(problems_head)
        self.diagnostics_view = QTextBrowser()
        self.diagnostics_view.setOpenExternalLinks(True)
        self.diagnostics_view.setStyleSheet(
            f"font-family:Consolas,monospace;font-size:12px;background:#0A1421;color:{TEXT};"
        )
        pl.addWidget(self.diagnostics_view)
        l.addWidget(problems, 1)
        return root

    def open_conflict_inspector(self: Any) -> None:
        sessions = []
        for raw in self.snapshot.sync:
            if not isinstance(raw, dict) or not isinstance(raw.get("identifier"), str):
                continue
            observed_at = self.snapshot.sync_observed_at
            sessions.append(
                from_session_dict(
                    "sync",
                    raw,
                    measured_at=observed_at or datetime(2000, 1, 1, tzinfo=UTC),
                    stale_reason=(
                        "Native snapshot is stale or has no observation timestamp"
                        if self.snapshot.sessions_stale or observed_at is None
                        else None
                    ),
                )
            )
        ConflictInspectorDialog(
            sessions,
            self,
            audit_path=settings_path().with_name("mutagen-remote-inspection.jsonl"),
            recommendation_path=settings_path().with_name("conflict-recommendations.json"),
        ).exec()

    def open_troubleshooter(self: Any, session_id: str | None = None) -> None:
        sessions = []
        observed_sessions: tuple[
            tuple[Literal["sync", "forward"], list[dict[str, Any]], datetime | None], ...
        ] = (
            ("sync", self.snapshot.sync, self.snapshot.sync_observed_at),
            ("forward", self.snapshot.forward, self.snapshot.forward_observed_at),
        )
        for kind, rows, observed_at in observed_sessions:
            for raw in rows:
                if not isinstance(raw, dict) or not isinstance(raw.get("identifier"), str):
                    continue
                sessions.append(
                    from_session_dict(
                        kind,
                        raw,
                        measured_at=observed_at or datetime(2000, 1, 1, tzinfo=UTC),
                        stale_reason=(
                            "Native snapshot is stale or has no observation timestamp"
                            if self.snapshot.sessions_stale or observed_at is None
                            else None
                        ),
                    )
                )
        report = diagnose_sessions(
            SessionDoctorContext(
                cli_available=bool(self.snapshot.binary),
                daemon_running=self.snapshot.daemon,
                sync_observed_at=self.snapshot.sync_observed_at,
                forward_observed_at=self.snapshot.forward_observed_at,
                sessions=tuple(sessions),
                version=self.snapshot.version or None,
                snapshot_error=self.snapshot.error,
                sessions_stale=self.snapshot.sessions_stale,
                cpu_percent=self.snapshot.cpu,
                resource_observed_at=self.snapshot.resource_observed_at,
            )
        )
        TroubleshooterDialog(
            sessions=sessions,
            report=report,
            selected_identifier=session_id,
            on_refresh=self.refresh if hasattr(self, "refresh") else None,
            on_open_settings=self.edit_session if hasattr(self, "edit_session") else None,
            parent=self,
        ).exec()

    def update_diagnostics(self: Any, snap: Snapshot) -> None:
        summary = (
            f"Mutagen: {snap.binary or 'not found'}\nVersion: {snap.version or 'unknown'}\n"
            f"Daemon: {'online' if snap.daemon else 'offline'}\n"
            f"Mutagen processes: {snap.processes} | CPU: {snap.cpu:.1f} % | RAM: {human_bytes(snap.memory)}\n"
            f"Sync sessions: {len(snap.sync)} | Forwarding: {len(snap.forward)}\n"
            f"Daemon autostart: {snap.registration}"
        )
        if snap.error:
            summary += "\nCLI error: " + snap.error
        self.diag_summary.setText(summary)
        sessions = []
        observed_sessions: tuple[
            tuple[Literal["sync", "forward"], list[dict[str, Any]], datetime | None], ...
        ] = (
            ("sync", snap.sync, snap.sync_observed_at),
            ("forward", snap.forward, snap.forward_observed_at),
        )
        for kind, rows, observed_at in observed_sessions:
            for raw in rows:
                if not isinstance(raw, dict) or not isinstance(raw.get("identifier"), str):
                    continue
                sessions.append(
                    from_session_dict(
                        kind,
                        raw,
                        measured_at=observed_at or datetime(2000, 1, 1, tzinfo=UTC),
                        stale_reason=(
                            "Native snapshot is stale or has no observation timestamp"
                            if snap.sessions_stale or observed_at is None
                            else None
                        ),
                    )
                )
        report = diagnose_sessions(
            SessionDoctorContext(
                cli_available=bool(snap.binary),
                daemon_running=snap.daemon,
                sync_observed_at=snap.sync_observed_at,
                forward_observed_at=snap.forward_observed_at,
                sessions=tuple(sessions),
                version=snap.version or None,
                snapshot_error=snap.error,
                sessions_stale=snap.sessions_stale,
                cpu_percent=snap.cpu,
                resource_observed_at=snap.resource_observed_at,
            )
        )
        self._safe_problem_codes = tuple(
            sorted({issue.code for issue in report.issues if isinstance(issue.code, str)})
        )
        failed_sessions = {
            issue.session_identifier
            for issue in report.issues
            if issue.session_identifier
            and issue.severity == "error"
            and issue.certainty == "confirmed"
        }
        health_now = time.monotonic()
        health_results = []
        for session in sessions:
            session_kind = session.identity.kind
            source_timestamp = (
                snap.sync_observed_at if session_kind == "sync" else snap.forward_observed_at
            )
            timestamp_age = (
                (datetime.now().astimezone() - source_timestamp).total_seconds()
                if source_timestamp is not None
                else None
            )
            if (
                session.stale_reason is not None
                or timestamp_age is None
                or not 0 <= timestamp_age <= FRESHNESS_SECONDS
            ):
                continue
            observation_key = (
                f"{session_kind}:{source_timestamp.isoformat()}"
                if source_timestamp is not None
                else f"{session_kind}:stale"
            )
            raw_status = session.native_config.get("status")
            paused = session.native_config.get("paused") is True
            scan_in_progress = raw_status in (7, "7") or "scan" in session.state.casefold()
            health_results.append(
                self.health_tracker.observe(
                    HealthObservation(
                        session_identifier=session.identity.identifier,
                        observation_key=observation_key,
                        observed_at=session.measured_at,
                        state=session.state,
                        confirmed_failure=session.identity.identifier in failed_sessions,
                        intentional_pause=paused,
                        scan_in_progress=scan_in_progress,
                        command_duration_seconds=snap.command_durations.get(f"{session_kind} list"),
                    ),
                    now=health_now,
                )
            )
        notes = [
            "Authoritative snapshot: "
            + ("yes" if report.authoritative else "NO — refresh required"),
            f"Sessions assessed: {report.session_count}; findings: {report.issue_count}",
            f"Health mode: {self.health_tracker.policy.mode}",
        ]
        snapshot_time_key = (snap.sync_observed_at, snap.forward_observed_at)
        if report.authoritative and snapshot_time_key != self._doctor_observation_key:
            if self._doctor_observation_key is not None:
                self._doctor_previous_issue_count = self._doctor_current_issue_count
            self._doctor_observation_key = snapshot_time_key
            self._doctor_current_issue_count = report.issue_count
        if not report.authoritative:
            notes.append("Trend: unavailable; snapshot is stale or incomplete")
        elif self._doctor_previous_issue_count is None:
            notes.append("Trend: baseline; next complete snapshot enables comparison")
        else:
            previous = self._doctor_previous_issue_count
            trend = (
                "unchanged"
                if report.issue_count == previous
                else "increased"
                if report.issue_count > previous
                else "decreased"
            )
            notes.append(f"Trend: {trend} ({previous} → {report.issue_count} findings)")
        severity_counts: dict[str, int] = {}
        for issue in report.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        notes.append(
            "Severity summary: "
            + (
                ", ".join(f"{severity}={count}" for severity, count in severity_counts.items())
                or "none"
            )
        )
        affected: dict[str, int] = {}
        for issue in report.issues:
            name = issue.session_identifier or "Mutagen / global"
            affected[name] = affected.get(name, 0) + 1
            stamp = (
                issue.observed_at.isoformat(timespec="seconds") if issue.observed_at else "unknown"
            )
            notes.extend(
                [
                    f"[{issue.severity.upper()} / {issue.certainty}] {issue.code} — {name}",
                    f"  {translate_text(issue.explanation, active_language())} (evidence: {stamp})",
                    *(
                        [f"  Detail: {issue.technical_detail[:500]}"]
                        if issue.technical_detail
                        else []
                    ),
                    *[
                        f"  Safe next step: {translate_text(action, active_language())}"
                        for action in issue.suggested_actions
                    ],
                    *([f"  Help: {issue.article_url}"] if issue.article_url else []),
                ]
            )
        for health in health_results:
            success_age = (
                "unknown"
                if health.last_success_at is None
                else f"{max(0.0, health_now - health.last_success_at):.0f}s ago"
            )
            duration = (
                "unknown"
                if health.last_command_duration_seconds is None
                else f"{health.last_command_duration_seconds:.2f}s"
            )
            notes.append(
                f"[HEALTH] {health.session_identifier}: {health.state}; "
                f"confirmed error streak={health.error_streak}; reconnects={health.reconnect_count}; "
                f"last healthy observation={success_age}; latest list command={duration}"
            )
            if health.incident_id:
                notes.append(f"  Incident: {health.incident_id}")
            for transition in health.transitions[-5:]:
                previous_state = transition.from_state or "initial"
                notes.append(
                    f"  Transition: {previous_state} → {transition.to_state} "
                    f"({transition.observed_at.isoformat(timespec='seconds')})"
                )
            if health.environment_event:
                notes.append(f"  Environment grace: {health.environment_event}")
            if health.recommend_manual_action:
                notes.append("  Assisted recommendation is ready; no recovery action was executed.")
        if self.health_tracker.policy.mode == "auto_safe":
            for session in sessions:
                gate = self.health_tracker.recovery_gate(
                    session.identity.identifier,
                    action="refresh_status",
                    now=health_now,
                    preconditions_stable=bool(snap.binary and snap.daemon),
                )
                if gate.allowed:
                    try:
                        self.health_tracker.record_recovery_attempt(
                            session.identity.identifier,
                            action="refresh_status",
                            now=health_now,
                            succeeded=True,
                        )
                        notes.append(
                            f"  [AUTO-SAFE] Scoped status refresh recorded for {session.identity.identifier}"
                        )
                        if hasattr(self, "refresh") and not getattr(self, "_refreshing", False):
                            self.refresh()
                    except Exception as exc:
                        notes.append(
                            f"  [AUTO-SAFE] Recovery attempt failed for {session.identity.identifier}: {exc}"
                        )
        notes.append(
            "Per-session finding counts: "
            + (", ".join(f"{name}={count}" for name, count in affected.items()) or "none")
        )
        formatted_notes = []
        for line in notes:
            if line.startswith("  Help: "):
                url = line.removeprefix("  Help: ")
                safe_url = html_escape(url, quote=True)
                formatted_notes.append(
                    f'&nbsp;&nbsp;Help: <a href="{safe_url}">{html_escape(url)}</a>'
                )
            else:
                formatted_notes.append(html_escape(line))
        self.diagnostics_view.setHtml("<br>".join(formatted_notes))
        if hasattr(self, "diag_problem_count"):
            if report.issue_count:
                n = len(
                    {
                        issue.session_identifier
                        for issue in report.issues
                        if issue.session_identifier
                    }
                )
                n += int(any(issue.session_identifier is None for issue in report.issues))
                self.diag_problem_count.setText(
                    f"⚠  {report.issue_count} findings · {n} affected session(s)"
                )
                self.diag_problem_count.setStyleSheet(f"color:{RED};font-size:11px;")
            elif not report.authoritative:
                set_localized_text(self.diag_problem_count, "?  snapshot unknown or stale")
                self.diag_problem_count.setStyleSheet(f"color:{AMBER};font-size:11px;")
            else:
                set_localized_text(self.diag_problem_count, "✓  no findings in recent snapshot")
                self.diag_problem_count.setStyleSheet(f"color:{TEAL};font-size:11px;")

    def export_safe_report(self: Any) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Safe Diagnostics Report", active_language()),
            "mutagen-safe-report.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        try:
            events = self.history.events(limit=500)
            data = safe_diagnostic_report(
                self.snapshot,
                application_version=APP_VERSION,
                qt_version=qVersion(),
                problem_codes=getattr(self, "_safe_problem_codes", ()),
                build_id=os.environ.get("GITHUB_RUN_ID"),
                recent_event_count=len(events),
                event_count_capped=len(events) == 500,
            )
            data["resource_summary"] = self.history.statistics(hours=1)
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Safe diagnostics report saved (no paths or addresses)")
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))

    def open_support_bundle(self: Any) -> None:
        try:
            events = self.history.events(limit=500)
            snapshot_payload = self._full_snapshot_payload()
            dialog = SupportBundleDialog(
                snapshot_preview=json.dumps(snapshot_payload, ensure_ascii=False, indent=2),
                event_count=len(events),
                monitored_line_count=len(self.tail_lines),
                parent=self,
            )
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode = dialog.mode.currentData()
        if mode == "safe":
            self.export_safe_report()
        elif mode == "full":
            self.export_snapshot(snapshot_payload=snapshot_payload)
        elif mode == "self_check":
            self.run_local_self_check()
        else:
            self.export_session_log_snapshot(
                include_event_messages=dialog.include_event_messages.isChecked(),
                include_monitored_log_lines=dialog.include_monitored_log_lines.isChecked(),
            )

    def run_local_self_check(self: Any) -> None:
        try:
            mutagen_version = self.client.get_version()
        except Exception:
            mutagen_version = "unavailable"
        result = local_self_check(
            app_path=Path(sys.executable if getattr(sys, "frozen", False) else __file__),
            settings_path=settings_path(),
            history=self.history,
            qt_version=qVersion(),
            mutagen_version=mutagen_version,
        )
        checks = result["checks"]
        czech = active_language().casefold().startswith("cs")
        labels = {
            "application_path": "Cesta aplikace" if czech else "Application path",
            "settings_path": "Cesta nastavení" if czech else "Settings path",
            "history_database": "Databáze historie" if czech else "History database",
            "python": "Python",
            "qt": "Qt",
            "mutagen_cli": "Mutagen CLI",
        }
        statuses = {
            "ok": "v pořádku" if czech else "ok",
            "warning": "upozornění" if czech else "warning",
            "error": "chyba" if czech else "error",
        }
        detail_translation = {
            "found": "nalezeno",
            "missing": "nenalezeno",
            "directory writable": "adresář je zapisovatelný",
            "directory unavailable or read-only": "adresář není dostupný nebo je jen pro čtení",
            "unavailable": "nedostupné",
        }
        lines = []
        for name, check in checks.items():
            detail = check["detail"]
            if czech:
                detail = detail_translation.get(detail, detail)
            lines.append(f"{labels[name]}: {statuses[check['status']]} ({detail})")
        lines.append("Vzdálené zápisy: ne" if czech else "Remote writes: no")
        title = "Místní kontrola aplikace" if czech else "Local application self-check"
        QMessageBox.information(self, title, "\n".join(lines))

    def _full_snapshot_payload(self: Any) -> dict[str, Any]:
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "daemon": self.snapshot.daemon,
            "version": self.snapshot.version,
            "binary": self.snapshot.binary,
            "error": self.snapshot.error,
            "registration": self.snapshot.registration,
            "sync": self.snapshot.sync,
            "forward": self.snapshot.forward,
        }

    def export_session_log_snapshot(
        self: Any,
        *,
        include_event_messages: bool = False,
        include_monitored_log_lines: bool = False,
    ) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Session Log Snapshot", active_language()),
            "mutagen-session-logs.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        if (include_event_messages or include_monitored_log_lines) and (
            QMessageBox.question(
                self,
                translate_text("Sensitive Log Details", active_language()),
                translate_text(
                    "Selected log text may contain local paths, hostnames, usernames, or credentials. Save only to a local file you control. Continue?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            events = self.history.events(limit=501)
            data = session_log_report(
                events,
                list(self.tail_lines),
                include_event_messages=include_event_messages,
                include_monitored_log_lines=include_monitored_log_lines,
            )
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Session log snapshot saved locally")
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))

    def copy_diagnostics(self: Any) -> None:
        QApplication.clipboard().setText(
            self.diag_summary.text() + "\n\n" + self.diagnostics_view.toPlainText()
        )
        self.add_log("Diagnostics summary copied")

    def export_snapshot(self: Any, *, snapshot_payload: dict[str, Any] | None = None) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export diagnostiky", active_language()),
            "mutagen-snapshot.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        if (
            QMessageBox.question(
                self,
                translate_text("Sensitive Snapshot", active_language()),
                translate_text(
                    "This full snapshot can contain local paths, SSH hosts, usernames, and session names. Only save or share it with people you trust. Continue?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        data = snapshot_payload if snapshot_payload is not None else self._full_snapshot_payload()
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Diagnostics export complete")
        except OSError as exc:
            self.report_error(str(exc))
