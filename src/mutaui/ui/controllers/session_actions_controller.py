"""Session actions, preferences, and replacement mixin for MainWindow."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from forward_configuration import (
    FORWARD_CONFIG_FIELDS,
    ForwardConfigField,
    ForwardConfigRow,
    forward_configuration_rows,
)
from ignore_presets import (
    IgnorePresetError,
    path_aware_ignore_rule,
)
from mutagen_client import (
    MutagenClient,
    classify,
    conflict_count,
    endpoint_text,
    human_bytes,
    problem_count,
    session_preflight_fingerprint,
)
from mutaui.adapters.mutagen_snapshot import from_session_dict
from mutaui.services.action_planner import ACTION_SPECS, ActionRequest
from mutaui.services.reconfiguration import (
    build_reconfiguration_preview,
    extract_sync_configuration,
    validate_native_command_snapshot,
)
from mutaui.services.replacement import (
    ReplacementAuditEvent,
    ReplacementReceipt,
    ReplacementRequest,
    replace_non_project_mutagen_session,
)
from mutaui.services.replacement_command import (
    render_sync_replacement_arguments,
)
from mutaui.services.session_configuration import build_session_configuration_proposal
from mutaui.services.session_doctor import FRESHNESS_SECONDS
from mutaui.services.session_provenance import ProvenanceStoreError
from mutaui.ui.formatters import get_settings_path as settings_path
from mutaui.ui.formatters import (
    readable_record_lines,
    session_detail_html,
    write_settings,
)
from mutaui.ui.localization import (
    set_localized_accessible_name,
    set_localized_text,
    set_localized_title,
)
from mutaui.ui.performance_tuning import apply_performance_assistant
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.session_configuration_table import fill_session_configuration_table
from mutaui.ui.theme_constants import AMBER, BLUE, RED, TEAL
from mutaui.ui.widgets.basic import button, label, localized_checkbox
from sync_configuration import (
    SYNC_CONFIG_FIELDS,
    SyncConfigField,
    SyncConfigRow,
    session_configuration_rows,
)


class SessionActionsMixin:
    def refresh_detail(self: Any, kind: str) -> None:
        sess = self.selected_session(kind)
        details = self.sync_details if kind == "sync" else self.forward_details
        title = self.sync_title if kind == "sync" else self.forward_title
        tag = self.sync_tag if kind == "sync" else self.forward_tag
        controls = self.sync_controls if kind == "sync" else self.forward_controls
        progress_bar = self.sync_progress if kind == "sync" else self.forward_progress
        progress_bar.hide()
        fav_button = self.sync_favorite_button if kind == "sync" else self.forward_favorite_button
        fav_button.setEnabled(bool(sess))
        fav_button.setText(
            "★ Remove from Favorites"
            if sess and sess.get("identifier") in self.favorites[kind]
            else "☆ Add to Favorites"
        )
        for b in controls.values():
            b.setEnabled(bool(sess) and not self.demo and not self.pending_action)
        if kind == "sync":
            auto = self.sync_autostart_button
            auto.setEnabled(bool(sess) and not self.demo and not self.pending_action)
            if not sess:
                set_localized_text(auto, "Start at sign-in: select a session")
            elif sess.get("paused"):
                set_localized_text(auto, "◯ Start at sign-in: off")
            elif self.snapshot.registration == "registered":
                set_localized_text(auto, "● Start at sign-in: on")
            else:
                set_localized_text(auto, "⚠ Enable start at sign-in · register daemon")
        if not sess:
            troubleshoot_btn = getattr(self, f"{kind}_troubleshoot_button", None)
            if troubleshoot_btn is not None:
                troubleshoot_btn.setVisible(False)
            set_localized_text(title, "Select a session")
            tag.setText("")
            set_localized_text(
                details,
                "Select a row above to view details, status, statistics, and available actions.",
            )
            return
        state, description = classify(sess, kind)
        title.setText(sess.get("name") or "Untitled Session")
        tag.setText(description)
        tag.setStyleSheet(
            f"color:{ {'error': RED, 'active': TEAL, 'paused': AMBER}.get(state, BLUE) }"
        )
        first = endpoint_text(sess.get("alpha" if kind == "sync" else "source"), kind)
        second = endpoint_text(sess.get("beta" if kind == "sync" else "destination"), kind)
        sep = "─" * 44
        lines = [
            f"IDENTIFIER\n{sess.get('identifier', '—')}",
            sep,
            f"{'ENDPOINTS' if kind == 'sync' else 'CONNECTION'}",
            f"{'ALPHA' if kind == 'sync' else 'Source'}\n{first}",
            f"{'BETA' if kind == 'sync' else 'Destination'}\n{second}",
        ]
        if kind == "sync":
            alpha = sess.get("alpha") or {}
            beta = sess.get("beta") or {}
            lines += [
                sep,
                "SYNC OVERVIEW",
                f"Files: ALPHA {alpha.get('files', '—')} · BETA {beta.get('files', '—')}",
                f"Total size: {human_bytes(alpha.get('totalFileSize', 0))}",
                f"Successful cycles: {sess.get('successfulCycles', 0)}",
                f"Conflicts: {conflict_count(sess)} · Issues: {problem_count(sess)}",
            ]
            stages = [
                ("ALPHA", alpha.get("stagingProgress")),
                ("BETA", beta.get("stagingProgress")),
            ]
            for target, prog in stages:
                if prog:
                    expected_size = int(prog.get("expectedSize") or 0)
                    if expected_size:
                        percentage = min(
                            100, round(100 * float(prog.get("receivedSize") or 0) / expected_size)
                        )
                        progress_bar.setValue(percentage)
                        progress_bar.setFormat(f"Transfer to {target}: %p %")
                        progress_bar.show()
                    expected = max(1, prog.get("expectedSize", 0))
                    lines.append(
                        f"Transfer to {target}: {prog.get('path', '')} · {100 * prog.get('receivedSize', 0) / expected:.0f} % "
                        f"({human_bytes(prog.get('receivedSize', 0))} / {human_bytes(prog.get('expectedSize', 0))})"
                    )
            confs = sess.get("conflicts") or []
            if confs:
                lines += [sep, "RECENT CONFLICTS"]
                for index, conflict in enumerate(confs, 1):
                    lines.append(f"Conflict {index}")
                    lines.extend(readable_record_lines(conflict, indent=2))
            probs = [
                *alpha.get("scanProblems", []),
                *alpha.get("transitionProblems", []),
                *beta.get("scanProblems", []),
                *beta.get("transitionProblems", []),
            ]
            if probs:
                lines += [sep, "RECENT ISSUES"]
                for index, problem in enumerate(probs, 1):
                    lines.append(f"Issue {index}")
                    lines.extend(readable_record_lines(problem, indent=2))
        else:
            lines += [
                sep,
                "CONNECTION OVERVIEW",
                f"Open connections: {sess.get('openConnections', 0)} · Total: {sess.get('totalConnections', 0)}",
                f"Data out: {human_bytes(sess.get('totalOutboundData', 0))}",
                f"Data in: {human_bytes(sess.get('totalInboundData', 0))}",
            ]
        if sess.get("lastError"):
            lines += [sep, "⚠ LAST ERROR: " + str(sess["lastError"])]
        custom_note = (
            self.conf.get("session_prefs", {})
            .get(str(sess.get("identifier") or ""), {})
            .get("note")
        )
        if custom_note:
            lines += [sep, "📝 NOTE: " + custom_note]
        details.setText(session_detail_html(lines, sep))
        if "flush" in controls:
            controls["flush"].setEnabled(
                not sess.get("paused") and not self.demo and not self.pending_action
            )
        if "pause" in controls:
            controls["pause"].setEnabled(
                not sess.get("paused") and not self.demo and not self.pending_action
            )
        if "resume" in controls:
            controls["resume"].setEnabled(
                bool(sess.get("paused")) or state in ("error", "idle")
                if not self.demo and not self.pending_action
                else False
            )
        troubleshoot_btn = getattr(self, f"{kind}_troubleshoot_button", None)
        if troubleshoot_btn is not None:
            has_issue = bool(
                sess.get("lastError")
                or state in ("error", "halted")
                or sess.get("conflicts")
                or (kind == "sync" and bool(problem_count(sess)))
            )
            troubleshoot_btn.setVisible(has_issue)

    def open_troubleshooter_for_selected(self: Any, kind: str) -> None:
        sess = self.selected_session(kind)
        sess_id = str(sess.get("identifier")) if sess and sess.get("identifier") else None
        if hasattr(self, "open_troubleshooter"):
            self.open_troubleshooter(sess_id)

    def open_session_preferences(self: Any, kind: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            QMessageBox.information(
                self,
                translate_text("Select a session", active_language()),
                translate_text("First, select a session in the table.", active_language()),
            )
            return
        identifier = str(sess.get("identifier") or "")
        prefs = dict(self.conf.get("session_prefs", {}).get(identifier, {}))
        dialog = QDialog(self)
        dialog.setWindowTitle("Session Settings · " + (sess.get("name") or identifier[:14]))
        dialog.setMinimumWidth(480)
        box = QVBoxLayout(dialog)
        box.setSpacing(15)
        box.setContentsMargins(24, 22, 24, 22)
        box.addWidget(label("Display and Notification Settings", size=17, bold=True))
        box.addWidget(
            label(
                f"Exact Mutagen ID (read-only): {identifier} · Name: {sess.get('name') or 'Unnamed'}",
                muted=True,
                size=11,
            )
        )
        notifications = localized_checkbox("Notify about new errors in this session")
        notifications.setChecked(bool(prefs.get("notifications", True)))
        box.addWidget(notifications)
        box.addWidget(label("Session Note", muted=True))
        note = QLineEdit(str(prefs.get("note", "")))
        note.setMaxLength(180)
        box.addWidget(note)
        fields_by_key: Mapping[str, SyncConfigField | ForwardConfigField]
        config_rows: Sequence[SyncConfigRow | ForwardConfigRow]
        if kind == "sync":
            box.addWidget(label("Actual Mutagen Sync Configuration", size=14, bold=True))
            proposals = prefs.get("configuration_proposal", {})
            if not isinstance(proposals, dict):
                proposals = {}
            fields_by_key = {field.key: field for field in SYNC_CONFIG_FIELDS}
            sync_rows = session_configuration_rows(sess, proposals)
            config_rows = sync_rows
            config_table = QTableWidget(len(config_rows), 6)
            set_localized_accessible_name(config_table, "Project configuration table")
            config_table.setHorizontalHeaderLabels(
                ["Field", "Native value", "Origin", "Impact", "Capability", "Proposed value"]
            )
            config_table.setWordWrap(True)
            config_table.setMinimumSize(1000, 390)
            config_table.setAlternatingRowColors(True)
            config_table.horizontalHeader().setStretchLastSection(True)
            fill_session_configuration_table(
                config_table,
                sync_rows,
                fields_by_key,
                proposals,
                proposal_tooltip="Local proposal only. Installed Mutagen support must be verified before replacement.",
            )
            box.addWidget(config_table)
            explanation = label(
                "Current values are read-only snapshots. Edit Proposed value to keep a local replacement draft. "
                "Saving this dialog does not change the existing Mutagen session. Capability checks and a reviewed replacement workflow are required before applying any proposal.",
                muted=True,
                size=11,
            )
            explanation.setWordWrap(True)
            box.addWidget(explanation)

            if self.ui_mode == "advanced":
                performance_assistant = QPushButton(
                    "Asistent ladění výkonu…"
                    if active_language().casefold().startswith("cs")
                    else "Performance Tuning Assistant…"
                )
                performance_assistant.setObjectName("performanceTuningAssistant")
                performance_assistant.setAccessibleName(
                    "Asistent ladění výkonu"
                    if active_language().casefold().startswith("cs")
                    else "Performance Tuning Assistant"
                )
                performance_assistant.setEnabled(not self.demo and not self.snapshot.sessions_stale)

                def open_performance_assistant() -> None:
                    apply_performance_assistant(
                        sess,
                        config_table,
                        sync_rows,
                        stale=self.snapshot.sessions_stale,
                        parent=dialog,
                    )

                performance_assistant.clicked.connect(open_performance_assistant)
                performance_assistant.setToolTip(
                    "Ukazuje kvalitativní doporučení z dokumentace. Návrhy vyplní pouze místní koncept náhrady."
                    if active_language().casefold().startswith("cs")
                    else "Shows qualitative, documentation-based guidance. Suggestions only fill a local replacement draft."
                )
                box.addWidget(performance_assistant)

            def quick_ignore_selected_file() -> None:
                local_roots = []
                for side, endpoint_label in (("alpha", "ALPHA"), ("beta", "BETA")):
                    endpoint = sess.get(side)
                    if not isinstance(endpoint, dict):
                        continue
                    raw_path = endpoint.get("path")
                    if (
                        endpoint.get("protocol") not in (0, "local")
                        or not isinstance(raw_path, str)
                        or not Path(raw_path).expanduser().is_dir()
                    ):
                        continue
                    local_roots.append((endpoint_label, Path(raw_path).expanduser()))
                if not local_roots:
                    QMessageBox.information(
                        dialog,
                        translate_text("Quick Ignore unavailable", active_language()),
                        translate_text("No local sync endpoint was reported.", active_language()),
                    )
                    return
                root_label, root_path = local_roots[0]
                if len(local_roots) > 1:
                    choices = [f"{side} — {path}" for side, path in local_roots]
                    choice, accepted = QInputDialog.getItem(
                        dialog,
                        translate_text("Choose Local Sync Endpoint", active_language()),
                        translate_text(
                            "Select the local root for this ignore rule:", active_language()
                        ),
                        choices,
                        0,
                        False,
                    )
                    if not accepted:
                        return
                    index = choices.index(choice)
                    root_label, root_path = local_roots[index]
                selected, _filter = QFileDialog.getOpenFileName(
                    dialog,
                    translate_text("Select file for Quick Ignore", active_language()),
                    str(root_path),
                    translate_text("All files (*)", active_language()),
                )
                if not selected:
                    return
                try:
                    pattern = path_aware_ignore_rule(root_path, selected)
                    ignore_row = next(
                        index for index, row in enumerate(config_rows) if row.key == "ignore.paths"
                    )
                    draft_text = (
                        cast(QTableWidgetItem, config_table.item(ignore_row, 5)).text().strip()
                    )
                    if draft_text:
                        patterns = json.loads(draft_text)
                    else:
                        native_ignore = sess.get("ignore", {})
                        patterns = (
                            native_ignore.get("paths", [])
                            if isinstance(native_ignore, dict)
                            else []
                        )
                    if not isinstance(patterns, list) or any(
                        not isinstance(value, str) for value in patterns
                    ):
                        raise ValueError("The current ignore paths are not a known list.")
                    if pattern not in patterns:
                        patterns.append(pattern)
                    cast(QTableWidgetItem, config_table.item(ignore_row, 5)).setText(
                        json.dumps(patterns, ensure_ascii=False)
                    )
                    self.add_log(f"Quick Ignore drafted for {root_label}: {pattern}")
                except (IgnorePresetError, OSError, ValueError, json.JSONDecodeError) as exc:
                    QMessageBox.warning(
                        dialog,
                        translate_text("Quick Ignore unavailable", active_language()),
                        str(exc),
                    )

            box.addWidget(button("Quick Ignore a Local File…", quick_ignore_selected_file))
            apply_proposal = QPushButton("Review saved replacement proposal…")
            apply_proposal.setEnabled(bool(proposals) and not self.demo)
            apply_proposal.setToolTip(
                "Uses the last saved proposal. Save edits before reviewing replacement."
            )
            apply_proposal.clicked.connect(
                lambda _checked=False, exact_id=identifier: self.review_sync_replacement(exact_id)
            )
            box.addWidget(apply_proposal)
        elif kind == "forward":
            box.addWidget(label("Actual Mutagen Forwarding Configuration", size=14, bold=True))
            proposals = prefs.get("forward_configuration_proposal", {})
            if not isinstance(proposals, dict):
                proposals = {}
            fields_by_key = {field.key: field for field in FORWARD_CONFIG_FIELDS}
            forward_rows = forward_configuration_rows(sess, proposals)
            config_rows = forward_rows
            config_table = QTableWidget(len(config_rows), 6)
            set_localized_accessible_name(config_table, "Forwarding configuration table")
            config_table.setHorizontalHeaderLabels(
                ["Field", "Native value", "Origin", "Impact", "Capability", "Proposed value"]
            )
            config_table.setWordWrap(True)
            config_table.setMinimumSize(1000, 260)
            config_table.setAlternatingRowColors(True)
            config_table.horizontalHeader().setStretchLastSection(True)
            fill_session_configuration_table(
                config_table,
                forward_rows,
                fields_by_key,
                proposals,
                proposal_tooltip="Local proposal only. CLI, endpoint and platform support must be verified before replacement.",
            )
            box.addWidget(config_table)
            explanation = label(
                "Forwarding settings are current read-only values plus a local proposal. Socket overwrite, owner, group and permissions require verified CLI, endpoint and platform support. Existing sessions stay unchanged.",
                muted=True,
                size=11,
            )
            explanation.setWordWrap(True)
            box.addWidget(explanation)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )

        def accept_dialog() -> None:
            if kind in ("sync", "forward"):
                try:
                    proposal_values = {
                        row.key: cast(QTableWidgetItem, config_table.item(row_index, 5)).text()
                        for row_index, row in enumerate(config_rows)
                    }
                    proposal = build_session_configuration_proposal(
                        kind, sess, fields_by_key, proposal_values
                    )
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    QMessageBox.warning(
                        dialog, translate_text("Invalid proposal", active_language()), str(exc)
                    )
                    return
                proposal_key = (
                    "configuration_proposal" if kind == "sync" else "forward_configuration_proposal"
                )
                prefs[proposal_key] = proposal
            dialog.accept()

        controls.accepted.connect(accept_dialog)
        controls.rejected.connect(dialog.reject)
        box.addWidget(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.conf.setdefault("session_prefs", {})[identifier] = {
            "notifications": notifications.isChecked(),
            "note": note.text().strip(),
            **(
                {"configuration_proposal": prefs.get("configuration_proposal", {})}
                if kind == "sync"
                else {}
            ),
            **(
                {"forward_configuration_proposal": prefs.get("forward_configuration_proposal", {})}
                if kind == "forward"
                else {}
            ),
        }
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self.refresh_detail(kind)
        self.add_log("Session settings saved")

    def show_raw_native_session_json(
        self: Any, session: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        dialog = QDialog(parent or self)
        set_localized_title(dialog, "Raw Mutagen session JSON")
        layout = QVBoxLayout(dialog)
        notice = label(
            "Read-only native snapshot. It may include local paths and remote endpoint details.",
            muted=True,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        raw_json = QPlainTextEdit(dialog)
        raw_json.setObjectName("rawNativeSessionJsonSource")
        raw_json.setPlainText(json.dumps(session, ensure_ascii=False, indent=2))
        raw_json.setReadOnly(True)
        raw_json.setAccessibleName(translate_text("Raw Mutagen session JSON", active_language()))
        layout.addWidget(raw_json, 1)
        actions = QHBoxLayout()
        copy_button = button(
            "Copy JSON", lambda: QApplication.clipboard().setText(raw_json.toPlainText())
        )
        copy_button.setObjectName("copyRawNativeSessionJson")
        actions.addWidget(copy_button)
        actions.addWidget(button("Close", dialog.accept))
        layout.addLayout(actions)
        dialog.resize(720, 560)
        dialog.exec()

    def review_sync_replacement(self: Any, session_identifier: str) -> None:
        """Preview and, after explicit consent, replace one eligible sync session."""
        if self.demo or self.pending_action or self.snapshot.sessions_stale:
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text("Refresh current native sessions first.", active_language()),
            )
            return
        observed_at = self.snapshot.sync_observed_at
        if (
            observed_at is None
            or (datetime.now(UTC) - observed_at).total_seconds() > FRESHNESS_SECONDS
        ):
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text(
                    "Session status is stale. Refresh and review again.", active_language()
                ),
            )
            return
        session = next(
            (item for item in self.snapshot.sync if item.get("identifier") == session_identifier),
            None,
        )
        if session is None:
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text("The exact session is no longer loaded.", active_language()),
            )
            return
        labels = session.get("labels", {})
        if not isinstance(labels, dict) or "io.mutagen.project" in labels:
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text(
                    "Project-owned sessions must be changed through their native project workflow.",
                    active_language(),
                ),
            )
            return
        try:
            provenance = self.session_provenance.get(session_identifier)
            if provenance is None:
                raise ValueError("This session has no verified local creation provenance.")
            prefs = self.conf.get("session_prefs", {}).get(session_identifier, {})
            proposals = prefs.get("configuration_proposal", {}) if isinstance(prefs, dict) else {}
            if not isinstance(proposals, dict) or not proposals:
                raise ValueError("Save at least one configuration proposal before replacement.")
            native_configuration = extract_sync_configuration(session)
            if not native_configuration:
                raise ValueError("Native configuration is missing or has an unknown shape.")
            help_text = self.client.command(["sync", "create", "--help"], timeout=12, readonly=True)
            new_arguments = render_sync_replacement_arguments(
                provenance.create_arguments, proposals, help_text
            )
            new_configuration = json.loads(json.dumps(native_configuration))
            fields = {field.key: field for field in SYNC_CONFIG_FIELDS}
            for key, value in proposals.items():
                field = fields[key]
                target = new_configuration
                for part in field.path[:-1]:
                    if not isinstance(target.get(part), dict):
                        target[part] = {}
                    target = target[part]
                target[field.path[-1]] = value
            snapshot = from_session_dict("sync", session, measured_at=datetime.now(UTC))
            validation = validate_native_command_snapshot(
                snapshot,
                command_arguments=provenance.create_arguments,
                command_target_identifier=session_identifier,
            )
            preview = build_reconfiguration_preview(
                snapshot,
                new_configuration,
                command_arguments=provenance.create_arguments,
                command_target_identifier=session_identifier,
            )
            if not validation.snapshot_inputs_complete or not preview.changes:
                raise ValueError(
                    "The native snapshot is incomplete, contains unknown fields, or has no effective changes."
                )
            if new_configuration.get("mode") == "one-way-replica":
                raise ValueError(
                    "Replica mode is a destructive change and cannot use this replacement flow."
                )
            plan = self.client.action_planner.prepare(
                ActionRequest(
                    action="sync_reconfigure",
                    target_ids=(session_identifier,),
                    argv=tuple(new_arguments),
                    preflight_fingerprint=preview.source_sha256,
                    capabilities=("sync_reconfigure",),
                )
            )
            changes = "\n".join(
                f"• {change.path}: {change.current!r} → {change.proposed!r}"
                for change in preview.changes
            )
            prompt = (
                f"Replace exact Mutagen session {session_identifier}?\n\n{changes}\n\n"
                "Replacement terminates the old session, clears its sync history, and triggers a rescan. "
                "A best-effort restore runs if creation or verification fails.\n\n"
                + "Command preview: mutagen "
                + " ".join(new_arguments)
            )
            answer = QMessageBox.question(
                self,
                translate_text("Review sync replacement", active_language()),
                prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.client.action_planner.cancel(plan.plan_id)
                return
            plan = self.client.consent_action_plan(plan, consent=True)
        except Exception as exc:
            self.report_error(str(exc))
            return

        request = ReplacementRequest(
            plan=plan,
            previous_session_identifier=session_identifier,
            source_sha256=preview.source_sha256,
            old_create_arguments=provenance.create_arguments,
            new_create_arguments=tuple(new_arguments),
            old_configuration={"configuration": native_configuration},
            new_configuration={"configuration": new_configuration},
            snapshot_validation=validation,
            project_owned=False,
        )
        client = MutagenClient(self.client.binary, action_planner=self.client.action_planner)
        audit_path = settings_path().with_name("session-replacement-audit.jsonl")
        self.pending_action = True

        def execute_replacement() -> ReplacementReceipt:
            def audit(event: ReplacementAuditEvent) -> None:
                record = {
                    "plan_id": event.plan_id,
                    "session_identifier": event.session_identifier,
                    "phase": event.phase,
                    "outcome": event.outcome,
                    "argv_fingerprint": event.argv_fingerprint,
                    "note": event.note,
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                audit_path.parent.mkdir(parents=True, exist_ok=True)
                with audit_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

            try:
                receipt = replace_non_project_mutagen_session(
                    request, client, consent=True, audit=audit
                )
            except Exception:
                self.client.action_planner.finish(
                    plan.plan_id,
                    verified_target_ids=(),
                    outcome="replacement execution failed; inspect exact-ID audit and refresh",
                )
                raise
            self.client.action_planner.finish(
                plan.plan_id,
                verified_target_ids=plan.target_ids if receipt.verified else (),
                outcome=(
                    f"replacement verified as {receipt.new_session_identifier}"
                    if receipt.verified
                    else "replacement did not verify; inspect restore status and exact-ID audit"
                ),
            )
            return receipt

        def replaced(receipt: ReplacementReceipt) -> None:
            if receipt.verified and receipt.new_session_identifier:
                try:
                    self.session_provenance.record(receipt.new_session_identifier, new_arguments)
                except ProvenanceStoreError as exc:
                    self.add_log("Replacement verified; new provenance was not saved: " + str(exc))
                try:
                    session_prefs = self.conf.setdefault("session_prefs", {})
                    prior_prefs = session_prefs.pop(session_identifier, {})
                    if isinstance(prior_prefs, dict):
                        prior_prefs.pop("configuration_proposal", None)
                        session_prefs[receipt.new_session_identifier] = prior_prefs
                    if session_identifier in self.favorites["sync"]:
                        self.favorites["sync"].discard(session_identifier)
                        self.favorites["sync"].add(receipt.new_session_identifier)
                        self.conf["favorites"] = {
                            kind: sorted(ids) for kind, ids in self.favorites.items()
                        }
                    write_settings(self.conf)
                except (OSError, TypeError, ValueError) as exc:
                    self.add_log(
                        "Replacement verified; local note/favorite migration failed: " + str(exc)
                    )
                self.add_log(
                    f"Replaced exact session {session_identifier} with {receipt.new_session_identifier}."
                )
            else:
                self.add_log(
                    "Replacement did not verify. Restore session: "
                    + str(receipt.restored_session_identifier or "unverified")
                    + "; recovery uncertain: "
                    + str(receipt.recovery_uncertain)
                )
            self.refresh(force=True)

        self.submit(
            execute_replacement,
            replaced,
            lambda error: self.report_error(str(error)),
            lambda: setattr(self, "pending_action", False),
        )

    def new_current_session(self: Any) -> None:
        page = self.pages.currentIndex()
        if page in (1, 2):
            self.create_session("sync" if page == 1 else "forward")

    def toggle_favorite(self: Any, kind: str) -> None:
        session = self.selected_session(kind)
        if not session:
            return
        identifier = str(session.get("identifier") or "")
        if not identifier:
            return
        favorite_ids = self.favorites[kind]
        if identifier in favorite_ids:
            favorite_ids.remove(identifier)
        else:
            favorite_ids.add(identifier)
        self.conf["favorites"] = {k: sorted(ids) for k, ids in self.favorites.items()}
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self._table_signatures.pop(kind, None)
        self._table_signatures.pop("dashboard", None)
        self.fill_table(
            self.sync_table if kind == "sync" else self.forward_table,
            self.snapshot.sync if kind == "sync" else self.snapshot.forward,
            kind,
        )
        self.filter_table(kind)
        self.refresh_detail(kind)

    def copy_session_id(self: Any, kind: str) -> None:
        sess = self.selected_session(kind)
        if sess:
            QApplication.clipboard().setText(str(sess.get("identifier", "")))
            self.add_log("Session identifier copied to clipboard")

    def export_session_json(self: Any, kind: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text(
                "Export Session (may contain server names and paths)", active_language()
            ),
            "mutagen-session.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(sess, indent=2, ensure_ascii=False), encoding="utf-8")
            self.add_log("Session JSON export complete")
        except OSError as exc:
            self.report_error(str(exc))

    def copy_session_paths(self: Any, kind: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            return
        if kind == "sync":
            alpha = sess.get("alpha", {}).get("path") or sess.get("alpha", {}).get("raw") or ""
            beta = sess.get("beta", {}).get("path") or sess.get("beta", {}).get("raw") or ""
            text = f"{alpha} <-> {beta}" if alpha and beta else (alpha or beta)
        else:
            src = str(sess.get("source", ""))
            dst = str(sess.get("destination", ""))
            text = f"{src} -> {dst}" if src and dst else (src or dst)
        if text:
            QApplication.clipboard().setText(text)
            if hasattr(self, "statusBar") and self.statusBar():
                self.statusBar().showMessage(
                    translate_text("Copied endpoint paths to clipboard", active_language()),
                    3000,
                )

    def session_context_menu(self: Any, kind: str, point: QPoint) -> None:
        table = self.sync_table if kind == "sync" else self.forward_table
        if hasattr(table, "indexAt"):
            index = table.indexAt(point)
            if not index.isValid():
                return
            row = index.row()
        elif hasattr(table, "itemAt"):
            item = table.itemAt(point)
            if not item:
                return
            row = item.row() if callable(item.row) else item.row
        else:
            return
        table.selectRow(row)
        if hasattr(self, "on_select"):
            self.on_select(kind)
        sess = self.selected_session(kind)
        if not sess:
            return
        menu = QMenu(table)
        favorite_text = (
            "★ Remove from Favorites"
            if sess.get("identifier") in self.favorites[kind]
            else "☆ Add to Favorites"
        )
        menu.addAction(
            translate_text(favorite_text, active_language()),
            lambda: self.toggle_favorite(kind),
        )
        menu.addAction(
            translate_text("Copy ID", active_language()), lambda: self.copy_session_id(kind)
        )
        if hasattr(self, "statusBar") and hasattr(self, "copy_session_paths"):
            menu.addAction(
                translate_text("Copy Path / Endpoints", active_language()),
                lambda: self.copy_session_paths(kind),
            )
        menu.addAction(
            translate_text("Export JSON", active_language()) + "…",
            lambda: self.export_session_json(kind),
        )
        if hasattr(self, "open_troubleshooter"):
            menu.addAction(
                translate_text("Troubleshoot…", active_language()),
                lambda: self.open_troubleshooter(sess.get("identifier")),
            )
        menu.addSeparator()
        if not self.demo:
            if sess.get("paused"):
                menu.addAction(
                    translate_text("Resume", active_language()),
                    lambda: self.session_action(kind, "resume"),
                )
            else:
                menu.addAction(
                    translate_text("Pause", active_language()),
                    lambda: self.session_action(kind, "pause"),
                )
            if kind == "sync":
                menu.addAction(
                    translate_text("Sync Now", active_language()),
                    lambda: self.session_action(kind, "flush"),
                )
                startup_text = (
                    "Enable Start at Sign-In"
                    if sess.get("paused")
                    else "Disable Start at Sign-In (Pause)"
                )
                menu.addAction(
                    translate_text(startup_text, active_language()),
                    self.toggle_sync_startup,
                )
        menu.exec(table.viewport().mapToGlobal(point))

    def bulk_action(self: Any, kind: str, action: str, scope: str = "all") -> None:
        if self.demo or self.pending_action:
            return
        candidates = self.server_targets(kind, scope)
        if action == "flush" or action == "pause":
            candidates = [s for s in candidates if not s.get("paused")]
        elif action == "resume":
            candidates = [
                s
                for s in candidates
                if s.get("paused") or classify(s, kind)[0] in ("error", "idle")
            ]
        ids = [str(s.get("identifier") or "") for s in candidates]
        ids = list(dict.fromkeys(identifier for identifier in ids if identifier))
        if not ids:
            QMessageBox.information(
                self,
                translate_text("No Sessions", active_language()),
                translate_text("No eligible sessions for this action.", active_language()),
            )
            return
        action_name = {
            "flush": "Run Sync Cycle Now",
            "pause": "Pause",
            "resume": "Resume",
            "reset": "Reset History",
            "terminate": "Terminate",
        }[action]
        group_name = "all sessions" if scope == "all" else self.server_selector.currentText()
        body = f"{action_name} {len(ids)} selected sessions ({group_name})?"
        action_spec = ACTION_SPECS.get(f"{kind}_{action}")
        if action_spec is not None:
            body += f"\n\n{translate_text(action_spec.description, active_language())} · {action_spec.risk}"
        if action == "flush":
            body += "\n\nThis starts a sync cycle and does not wait for all transfers to finish."
        if action in ("pause", "resume"):
            body += "\n\nThis changes the current session status and their behavior at the daemon's next start."
        if action in ("reset", "terminate"):
            body += "\n\nThis may change sync history or permanently terminate sessions."
        preview_args = [kind, action]
        if kind == "sync" and action == "flush":
            preview_args.append("--skip-wait")
        preview_args.extend(ids)
        language = active_language()
        body += "\n\n" + translate_text("Exact session IDs:", language) + "\n" + "\n".join(ids)
        body += "\n\n" + translate_text("Command preview: {command}", language).format(
            command="mutagen " + " ".join(preview_args)
        )
        choice = QMessageBox.question(
            self,
            translate_text("Confirm Bulk Action", active_language()),
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if action in ("reset", "terminate"):
            expected = "RESET" if action == "reset" else "TERMINATE"
            value, accepted = QInputDialog.getText(
                self,
                translate_text("Second Confirmation", active_language()),
                translate_text(
                    "To confirm this action for {count} sessions, type {expected}:",
                    active_language(),
                ).format(count=len(ids), expected=expected),
            )
            if not accepted or value.strip() != expected:
                return
        self.pending_action = True
        self.add_log(f"Bulk action: {kind} {action} · {len(ids)} explicit IDs")
        client = MutagenClient(self.client.binary, action_planner=self.action_planner)
        candidates_by_id = {
            str(session.get("identifier") or ""): session
            for session in candidates
            if str(session.get("identifier") or "") in ids
        }
        selected_records = [candidates_by_id[identifier] for identifier in ids]
        preflight_fingerprint = session_preflight_fingerprint(selected_records)

        def success(output: str) -> None:
            self.add_log(f"Bulk action submitted: {action}, {len(ids)} sessions")
            if output:
                self.add_log(output[:1000])

        def done() -> None:
            self.pending_action = False
            self.refresh(force=True)

        self.submit(
            lambda: client.execute_many(
                kind,
                action,
                ids,
                operator_consent=True,
                expected_preflight_fingerprint=preflight_fingerprint,
            ),
            success,
            self.report_error,
            done,
        )

    def toggle_sync_startup(self: Any) -> None:
        """Native semantics: Mutagen persists paused/unpaused state across daemon restarts."""
        if self.demo or self.pending_action:
            return
        session = self.selected_session("sync")
        if not session:
            return
        ident = str(session.get("identifier") or "")
        if not ident:
            return
        if not session.get("paused"):
            if self.snapshot.registration != "registered":
                answer = QMessageBox.question(
                    self,
                    translate_text("Enable Start at Sign-In?", active_language()),
                    translate_text(
                        "Sync is running, but automatic start of the Mutagen daemon is not registered. Register the daemon to start at Windows sign-in? This also affects other active sessions.",
                        active_language(),
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.run_command("daemon", "register")
                return
            choice = QMessageBox.question(
                self,
                translate_text("Turn Off Sync Start?", active_language()),
                translate_text(
                    "Mutagen has no separate option to ‘not start next time but keep running now’. Turning this off therefore pauses the session immediately. Resume?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.run_command("sync", "pause", target=ident)
            return
        needs_registration = self.snapshot.registration != "registered"
        if needs_registration:
            response = QMessageBox.question(
                self,
                translate_text("Registrovat start Mutagen daemonu?", active_language()),
                translate_text(
                    "For sessions to resume at sign-in, the Mutagen daemon itself must be registered. Registration also affects other unpaused sessions. Register the daemon and resume this sync now?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        self.run_command("sync", "resume", target=ident, register_before=needs_registration)
