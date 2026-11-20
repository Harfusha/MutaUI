"""Settings import/export and preset management mixin for MainWindow."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QMessageBox,
)

from connection_profiles import (
    ConnectionProfileStore,
    load_profile_store,
)
from ignore_presets import (
    IgnorePresetError,
    IgnorePresetStore,
    apply_preset_import,
    load_ignore_presets,
    preset_to_record,
)
from mutagen_client import MutagenClient
from mutaui.adapters.cli_executor import LegacyMutagenExecutor
from mutaui.ui.connection_profiles_dialog import ConnectionProfilesDialog
from mutaui.ui.formatters import get_settings_path as settings_path
from mutaui.ui.formatters import write_settings
from mutaui.ui.ignore_rules import IgnorePresetManagerDialog
from mutaui.ui.portable_import_preview import PortableImportPreviewDialog
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.project_viewer import NativeProjectManagerDialog
from mutaui.ui.ssh_profile_manager import SSHProfileManagerDialog
from portable_bundle import (
    PortableBundleError,
    apply_profile_import,
    build_bundle,
    load_bundle,
    selected_preferences,
)
from settings import load_settings
from settings import write_settings as save_settings_file


class SettingsBundleMixin:
    def export_portable_bundle(self: Any) -> None:
        profile_path = settings_path().with_name("connection-profiles.json")
        loaded = load_profile_store(profile_path)
        if not loaded.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Export Unavailable", active_language()),
                "The local profile file is invalid and was left unchanged.\n\n"
                + "\n".join(loaded.warnings),
            )
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export Portable Bundle", active_language()),
            str(Path.home() / "mutaui-portable.json"),
            translate_text("JSON (*.json)", active_language()),
        )
        if not destination:
            return
        answer = QMessageBox.question(
            self,
            translate_text("Include machine-specific paths?", active_language()),
            translate_text(
                "Include absolute local endpoint paths? They may identify this computer or user. Choose No for the redacted portable export.",
                active_language(),
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return
        ignore_store = load_ignore_presets(settings_path().with_name("ignore-presets.json"))
        if not ignore_store.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Export Unavailable", active_language()),
                "The local ignore preset file is invalid and was left unchanged.\n\n"
                + "\n".join(ignore_store.warnings),
            )
            return
        result = build_bundle(
            list(loaded.profiles),
            load_settings(settings_path()).values,
            app_version="8.2",
            include_local_paths=answer == QMessageBox.StandardButton.Yes,
            ignore_presets=[preset_to_record(preset) for preset in ignore_store.presets],
        )
        if not result.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Export", active_language()),
                "\n".join(result.warnings),
            )
            return
        target = Path(destination)
        if target.exists():
            overwrite = QMessageBox.question(
                self,
                translate_text("Replace Portable Bundle", active_language()),
                f"Replace this file?\n\n{target}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if overwrite != QMessageBox.StandardButton.Yes:
                return
        temporary: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(result.text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            QMessageBox.information(
                self,
                translate_text("Portable Export", active_language()),
                f"Bundle saved: {target}\n\n"
                + (
                    "\n".join(result.warnings)
                    or "Absolute local paths were redacted; secrets were excluded."
                ),
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                translate_text("Portable Export", active_language()),
                f"Could not save bundle: {exc}",
            )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def import_portable_bundle(self: Any) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Import Portable Bundle", active_language()),
            str(Path.home()),
            translate_text("JSON (*.json);;All files (*)", active_language()),
        )
        if not source:
            return
        source_path = Path(source)
        try:
            if source_path.stat().st_size > 5 * 1024 * 1024:
                raise PortableBundleError("Portable bundle exceeds the 5 MiB size limit.")
            bundle = load_bundle(source_path.read_bytes())
        except (OSError, PortableBundleError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Portable Import", active_language()),
                f"Could not read bundle: {exc}",
            )
            return
        if not bundle.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Import", active_language()),
                "Bundle was not changed or imported:\n\n" + "\n".join(bundle.warnings),
            )
            return
        profile_path = settings_path().with_name("connection-profiles.json")
        current_profiles = load_profile_store(profile_path)
        if not current_profiles.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Import Unavailable", active_language()),
                "The local profile file is invalid and was left unchanged.\n\n"
                + "\n".join(current_profiles.warnings),
            )
            return
        store = ConnectionProfileStore(profile_path)
        ignore_path = settings_path().with_name("ignore-presets.json")
        ignore_state = load_ignore_presets(ignore_path)
        if not ignore_state.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Import Unavailable", active_language()),
                "The local ignore preset file is invalid and was left unchanged.\n\n"
                + "\n".join(ignore_state.warnings),
            )
            return
        ignore_store = IgnorePresetStore(ignore_path)
        preview = PortableImportPreviewDialog(self, bundle, store.profiles, ignore_store.presets)
        if preview.exec() != QDialog.DialogCode.Accepted:
            return
        prefs = bundle.data["items"]["preferences"]
        selected = preview.selected_preferences()
        ignore_choices = preview.ignore_choices()
        try:
            merged_settings = selected_preferences(
                load_settings(settings_path()).values, prefs, selected
            )
        except PortableBundleError as exc:
            QMessageBox.warning(
                self, translate_text("Portable Import", active_language()), str(exc)
            )
            return
        choices = preview.profile_choices()
        if (
            not selected
            and all(value == "skip" for value in choices.values())
            and all(value == "skip" for value in ignore_choices.values())
        ):
            QMessageBox.information(
                self,
                translate_text("Portable Import", active_language()),
                translate_text("Nothing selected; no files changed.", active_language()),
            )
            return
        answer = QMessageBox.question(
            self,
            translate_text("Apply Portable Import", active_language()),
            translate_text(
                "Apply selected local profiles, ignore presets, and preferences? Existing files get backups. Mutagen sessions, notes, history, and SSH files remain untouched.",
                active_language(),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            fresh_profiles = load_profile_store(profile_path)
            fresh_ignores = load_ignore_presets(ignore_path)
            if not fresh_profiles.valid or list(fresh_profiles.profiles) != store.profiles:
                raise PortableBundleError(
                    "Local connection profiles changed after preview; reload and review again."
                )
            if not fresh_ignores.valid or list(fresh_ignores.presets) != ignore_store.presets:
                raise PortableBundleError(
                    "Local ignore presets changed after preview; reload and review again."
                )
            merged_settings = selected_preferences(
                load_settings(settings_path()).values, prefs, selected
            )
            if any(value != "skip" for value in ignore_choices.values()):
                apply_preset_import(
                    ignore_store, bundle.data["items"]["ignore_presets"], ignore_choices
                )
            outcomes = apply_profile_import(store, bundle, choices)
            if selected:
                save_settings_file(settings_path(), merged_settings)
            QMessageBox.information(
                self,
                translate_text("Portable Import", active_language()),
                f"Profiles: {outcomes.count('create')} created, {outcomes.count('merge')} merged, {outcomes.count('skip')} skipped.\n"
                f"Ignore presets: {sum(value == 'create' for value in ignore_choices.values())} selected for create/replace.\n"
                + (
                    f"Imported preferences: {', '.join(sorted(selected))}. Restart the app to apply theme/language changes."
                    if selected
                    else "No application preferences changed."
                ),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Portable Import", active_language()),
                f"Import stopped with an error: {exc}",
            )

    def save_settings(self: Any) -> None:
        binary = self.binary_edit.text().strip()
        client = MutagenClient(binary)
        if binary and not client.binary:
            QMessageBox.warning(
                self,
                translate_text("Invalid File", active_language()),
                translate_text(
                    "The selected mutagen.exe file does not exist or is unavailable.",
                    active_language(),
                ),
            )
            return
        self.conf.update(
            binary=binary,
            interval=self.interval_input.value(),
            metric_interval=self.metric_interval_input.currentData(),
            eco_tray=self.eco_tray_input.isChecked(),
            tray=self.tray_input.isChecked(),
            alerts=self.alert_input.isChecked(),
            adaptive_poll=self.adaptive_input.isChecked(),
            adaptive_fast=self.fast_interval_input.value(),
            adaptive_idle=self.idle_interval_input.value(),
            adaptive_quiet=self.quiet_after_input.value(),
            new_sync_profile=self.new_sync_profile_input.currentData(),
            theme=self.theme_input.currentData(),
            language=self.language_input.currentData(),
        )
        self.adaptive_policy.fast = self.fast_interval_input.value()
        self.adaptive_policy.idle = self.idle_interval_input.value()
        self.adaptive_policy.quiet_after = self.quiet_after_input.value()
        try:
            write_settings(self.conf)
        except OSError as exc:
            QMessageBox.critical(self, translate_text("Save Failed", active_language()), str(exc))
            return
        self.client = client
        self.apply_theme(self.conf["theme"])
        self.apply_ui_language(self.conf["language"])
        self.poll_backoff.base = max(2, self.interval_input.value())
        self.poll_backoff.observe(True)
        self.update_polling_mode()
        self._version_cache = ("", 0.0, "")
        self._table_signatures.clear()
        self.add_log("Settings saved")
        self.refresh(force=True)

    def browse_binary(self: Any) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Select mutagen.exe", active_language()),
            str(Path.home()),
            translate_text("Executable (*.exe);;All files (*)", active_language()),
        )
        if path:
            self.binary_edit.setText(path)

    def manage_ignore_presets(self: Any) -> None:
        try:
            dialog = IgnorePresetManagerDialog(
                settings_path().with_name("ignore-presets.json"), self
            )
            dialog.exec()
        except (IgnorePresetError, OSError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Ignore Presets", active_language()),
                f"Could not open preset manager: {exc}",
            )

    def manage_native_projects(self: Any) -> None:
        from mutaui.projects.native_project import ProjectStoreError

        try:
            dialog = NativeProjectManagerDialog(
                settings_path().with_name("mutagen-projects.json"),
                self,
                executor=LegacyMutagenExecutor(self.client) if self.client.binary else None,
                audit_path=settings_path().with_name("mutagen-project-actions.jsonl"),
                action_planner=self.action_planner,
            )
            dialog.exec()
        except (ProjectStoreError, OSError) as exc:
            QMessageBox.warning(
                self, translate_text("Native Mutagen Projects", active_language()), str(exc)
            )

    def manage_connection_profiles(self: Any) -> None:
        profile_path = settings_path().with_name("connection-profiles.json")
        loaded = load_profile_store(profile_path)
        if not loaded.valid:
            QMessageBox.warning(
                self,
                translate_text("Connection Profiles Unavailable", active_language()),
                "The local profile file is invalid and was left unchanged.\n\n"
                + "\n".join(loaded.warnings),
            )
            return
        dialog = ConnectionProfilesDialog(self, ConnectionProfileStore(profile_path))
        dialog.exec()

    def manage_ssh_profiles(self: Any) -> None:
        SSHProfileManagerDialog(self).exec()
