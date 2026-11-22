"""Command execution and session action mixin for MainWindow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QMessageBox,
)

from connection_profiles import load_profile_store
from mutagen_client import MutagenClient, session_preflight_fingerprint
from mutaui.services.action_planner import ACTION_SPECS
from mutaui.services.session_provenance import ProvenanceStoreError
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.session_dialog import SessionDialog
from settings import settings_path


class CommandExecutionMixin:
    """Mixin providing creation, lifecycle commands, and error reporting for sessions/daemon."""

    def create_session(self: Any, kind: str, initial_path: str | None = None) -> None:
        if self.demo:
            QMessageBox.information(
                self,
                translate_text("Demo", active_language()),
                translate_text("Actions are disabled in demo mode.", active_language()),
            )
            return
        if not self.client.binary:
            QMessageBox.warning(
                self,
                translate_text("Mutagen not found", active_language()),
                translate_text("First, configure mutagen.exe in Settings.", active_language()),
            )
            self.set_page(5)
            return
        profile_load = load_profile_store(settings_path().with_name("connection-profiles.json"))
        if not profile_load.valid:
            QMessageBox.warning(
                self,
                translate_text("Connection Profiles Unavailable", active_language()),
                "Local profiles were left unchanged and will not be applied to this session.\n\n"
                + "\n".join(profile_load.warnings),
            )
        dlg = SessionDialog(
            kind,
            self,
            default_profile=self.conf.get("new_sync_profile", "default"),
            ui_mode=self.ui_mode,
            executable=self.client.binary or "mutagen",
            saved_profiles=profile_load.profiles if profile_load.valid else (),
            initial_path=initial_path,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.run_command(
                kind,
                "create",
                options=dlg.arguments(),
                backup_choice=dlg.backup_choice,
            )

    def session_action(self: Any, kind: str, action: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            return
        self.run_command(kind, action, target=sess.get("identifier", ""))

    def daemon_action(self: Any, action: str) -> None:
        self.run_command("daemon", action)

    def run_command(
        self: Any,
        kind: str,
        action: str,
        target: str = "",
        options: list[str] | None = None,
        register_before: bool = False,
        backup_choice: str | None = None,
    ) -> None:
        if self.demo or self.pending_action:
            return
        client = MutagenClient(self.client.binary, action_planner=self.action_planner)
        create_plan = None
        daemon_plan = None
        register_plan = None
        expected_preflight_fingerprint = ""
        if action == "create" and kind in {"sync", "forward"}:
            try:
                create_plan = client.prepare_create_plan(
                    kind,
                    options or [],
                    backup_choice=backup_choice,
                )
            except Exception as exc:
                self.report_error(str(exc))
                return
        if kind == "daemon":
            try:
                daemon_plan = client.prepare_daemon_plan(action)
            except Exception as exc:
                self.report_error(str(exc))
                return
            language = active_language()
            preview_lines = [
                f"{translate_text(daemon_plan.description, language)} · {daemon_plan.risk}",
                translate_text("Command preview: {command}", language).format(
                    command="mutagen " + " ".join(daemon_plan.argv)
                ),
            ]
            if action == "stop":
                preview_lines.append(
                    translate_text(
                        "Stopping interrupts all sync and forwarding sessions managed by this daemon.",
                        language,
                    )
                )
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", language),
                "\n\n".join(preview_lines),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.action_planner.cancel(daemon_plan.plan_id)
                return
            typed_confirmation = None
            if daemon_plan.requires_typed_confirmation:
                typed_confirmation, accepted = QInputDialog.getText(
                    self,
                    translate_text("Second Confirmation", language),
                    translate_text(
                        "To confirm this destructive action, type {expected}:", language
                    ).format(expected=daemon_plan.typed_confirmation),
                )
                if not accepted:
                    self.action_planner.cancel(daemon_plan.plan_id)
                    return
            try:
                daemon_plan = client.consent_action_plan(
                    daemon_plan,
                    consent=True,
                    typed_confirmation=typed_confirmation,
                )
            except Exception as exc:
                self.report_error(str(exc))
                return
        if create_plan is not None:
            language = active_language()
            preview = "\n".join(
                (
                    f"{translate_text(create_plan.description, language)} · {create_plan.risk}",
                    translate_text("Command preview: {command}", language).format(
                        command="mutagen " + " ".join(create_plan.argv)
                    ),
                    (
                        translate_text("A recoverable destination backup was confirmed.", language)
                        if create_plan.backup_required
                        else ""
                    ),
                )
            )
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", language),
                preview,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.action_planner.cancel(create_plan.plan_id)
                return
            typed_confirmation = None
            if create_plan.requires_typed_confirmation:
                typed_confirmation, accepted = QInputDialog.getText(
                    self,
                    translate_text("Second Confirmation", language),
                    translate_text(
                        "To confirm this destructive action, type {expected}:", language
                    ).format(expected=create_plan.typed_confirmation),
                )
                if not accepted:
                    self.action_planner.cancel(create_plan.plan_id)
                    return
            try:
                create_plan = client.consent_action_plan(
                    create_plan,
                    consent=True,
                    typed_confirmation=typed_confirmation,
                    backup_choice=backup_choice,
                )
            except Exception as exc:
                self.report_error(str(exc))
                return
        if kind in {"sync", "forward"} and target and action != "create":
            current_sessions = getattr(self.snapshot, kind, [])
            selected = [
                session
                for session in current_sessions
                if str(session.get("identifier") or "") == target
            ]
            if not selected:
                QMessageBox.information(
                    self,
                    translate_text("Refresh Required", active_language()),
                    translate_text(
                        "The exact session is not in the current snapshot. Refresh before retrying.",
                        active_language(),
                    ),
                )
                return
            expected_preflight_fingerprint = session_preflight_fingerprint(selected)
            action_key = f"{kind}_{action}"
            spec = ACTION_SPECS.get(action_key)
            if spec is None:
                self.report_error("This session action has no registered risk policy.")
                return
            language = active_language()
            effects = {
                "reset": "Mutagen may rescan and reevaluate file changes after clearing history.",
                "terminate": "This ends the session; files at both endpoints remain.",
            }
            effect = effects.get(action)
            preview = "\n".join(
                [
                    f"{translate_text(spec.description, language)} · {spec.risk}",
                    translate_text("Exact session identifier: {identifier}", language).format(
                        identifier=target
                    ),
                    translate_text("Command preview: {command}", language).format(
                        command="mutagen " + " ".join((kind, action, target))
                    ),
                ]
                + ([translate_text(effect, language)] if effect else [])
            )
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", active_language()),
                preview,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if register_before:
            try:
                register_plan = client.prepare_daemon_plan("register")
            except Exception as exc:
                self.report_error(str(exc))
                return
            language = active_language()
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", language),
                "\n\n".join(
                    (
                        f"{translate_text(register_plan.description, language)} · {register_plan.risk}",
                        translate_text("Command preview: {command}", language).format(
                            command="mutagen " + " ".join(register_plan.argv)
                        ),
                        translate_text(
                            "Registration affects every unpaused Mutagen session for this user.",
                            language,
                        ),
                    )
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.action_planner.cancel(register_plan.plan_id)
                return
            try:
                register_plan = client.consent_action_plan(register_plan, consent=True)
            except Exception as exc:
                self.report_error(str(exc))
                return
        self.pending_action = True
        action_labels = {
            "pause": ("Pausing session…", "Pozastavování relace…"),
            "resume": ("Resuming session…", "Obnovování relace…"),
            "flush": ("Syncing now…", "Spouštění synchronizace…"),
            "reset": ("Resetting history…", "Resetování historie…"),
            "terminate": ("Terminating session…", "Ukončování relace…"),
            "create": ("Creating session…", "Vytváření relace…"),
            "start": ("Starting daemon…", "Spouštění služby…"),
            "stop": ("Stopping daemon…", "Zastavování služby…"),
            "restart": ("Restarting daemon…", "Restartování služby…"),
        }
        lbl = action_labels.get(action, (f"{action.capitalize()}…", f"{action}…"))
        toast = lbl[1] if active_language() == "cs" else lbl[0]
        if hasattr(self, "statusBar") and self.statusBar():
            self.statusBar().showMessage(toast, 4000)
        self.add_log(
            f"Running: mutagen {kind} {action}" + (" (selected session)" if target else "")
        )
        if expected_preflight_fingerprint:
            self.add_log("Action preview approved: mutagen " + " ".join((kind, action, target)))
        if create_plan is not None:
            self.add_log("Action preview approved: mutagen " + " ".join(create_plan.argv))

        def do() -> str:
            if register_plan is not None:
                client.execute(
                    "daemon",
                    "register",
                    operator_consent=True,
                    action_plan=register_plan,
                )
            return str(
                client.execute(
                    kind,
                    action,
                    target,
                    options,
                    operator_consent=True,
                    expected_preflight_fingerprint=expected_preflight_fingerprint,
                    action_plan=daemon_plan or create_plan,
                )
            )

        def success(output: str) -> None:
            created = getattr(client, "last_created_session", None)
            if created is not None:
                created_kind, created_id, create_arguments = created
                try:
                    self.session_provenance.record(created_id, create_arguments)
                except ProvenanceStoreError as exc:
                    self.add_log(
                        "Created session verified, but replacement provenance was not saved: "
                        + str(exc)
                    )
                else:
                    self.add_log(
                        f"Saved local creation provenance for {created_kind} session {created_id}"
                    )
            if output:
                self.add_log(output[:1800])
            self.add_log(f"Completed: {kind} {action}")
            if hasattr(self, "statusBar") and self.statusBar():
                self.statusBar().showMessage(f"✓ {kind.capitalize()} {action}", 4000)

        def error(message: str) -> None:
            self.report_error(message)

        def done() -> None:
            self.pending_action = False
            QTimer.singleShot(450, lambda: self.refresh(force=True))

        self.submit(do, success, error, done)

    def report_error(self: Any, message: str) -> None:
        self.add_log("ERROR: " + message)
        QMessageBox.critical(self, translate_text("Mutagen — Error", active_language()), message)
