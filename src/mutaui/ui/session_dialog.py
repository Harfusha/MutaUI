"""Sync and forward session creation dialog."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from connection_profiles import ConnectionProfile
from ignore_presets import (
    IgnorePresetError,
    explain_ignore_path,
    format_ignore_layers,
    load_ignore_presets,
    parse_ignore_file,
)
from mutaui.services.session_configuration import build_session_arguments
from mutaui.ui.ignore_rules import IgnoreConversionDialog
from mutaui.ui.localization import (
    set_localized_accessible_name,
    set_localized_placeholder,
    set_localized_text,
    set_localized_title,
    set_localized_tooltip,
)
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.widgets.basic import (
    add_localized_item,
    add_localized_row,
    button,
    label,
    localized_checkbox,
)
from settings import settings_path as _default_settings_path
from sync_configuration import (
    load_effective_forward_configuration,
    load_effective_sync_configuration,
)
from sync_profiles import PROFILES

_settings_path_provider: Callable[[], Path] = _default_settings_path


def _text(text: str) -> str:
    return translate_text(text, active_language())


def configure_settings_path_provider(provider: Callable[[], Path]) -> None:
    global _settings_path_provider
    _settings_path_provider = provider


class SessionDialog(QDialog):
    def __init__(
        self,
        kind: str,
        parent: QWidget | None = None,
        default_profile: str = "default",
        ui_mode: str = "basic",
        executable: str = "mutagen",
        saved_profiles: tuple[ConnectionProfile, ...] = (),
        initial_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.kind = kind
        self.ui_mode = ui_mode if ui_mode in {"basic", "advanced"} else "basic"
        self.executable = executable or "mutagen"
        self.default_profile = default_profile
        self.default_sync_mode = "two-way-safe"
        set_localized_title(self, "New Sync" if kind == "sync" else "New Forward")
        self.setMinimumWidth(520)
        box = QVBoxLayout(self)
        box.setSpacing(16)
        box.setContentsMargins(26, 24, 26, 22)
        box.addWidget(label("New Session Settings", size=21, bold=True))
        box.addWidget(
            label(
                "Paths can be local, SSH, or Docker. For SSH, use preconfigured keys.", muted=True
            )
        )
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.name = QLineEdit()
        set_localized_placeholder(self.name, "e.g. my-project")
        add_localized_row(form, "Name", self.name)
        self.a = QLineEdit()
        self.b = QLineEdit()
        self.socket_overwrite_source: QComboBox | None = None
        self.socket_overwrite_destination: QComboBox | None = None
        self.socket_owner_source: QLineEdit | None = None
        self.socket_owner_destination: QLineEdit | None = None
        self.socket_group_source: QLineEdit | None = None
        self.socket_group_destination: QLineEdit | None = None
        self.socket_permission_source: QLineEdit | None = None
        self.socket_permission_destination: QLineEdit | None = None
        matching_profiles = [profile for profile in saved_profiles if profile.kind == kind]
        self.connection_profile = None
        if matching_profiles:
            self.connection_profile = QComboBox()
            add_localized_item(self.connection_profile, "No saved profile", None)
            for profile in matching_profiles:
                prefix = "★ " if profile.favorite else ""
                tags = f" · {', '.join(profile.tags)}" if profile.tags else ""
                self.connection_profile.addItem(prefix + profile.name + tags, profile)
            add_localized_row(form, "Connection Profile", self.connection_profile)
        if kind == "sync":
            set_localized_placeholder(self.a, "C:\\Projects\\web")
            set_localized_tooltip(
                self.a,
                "ALPHA: local or remote path.\nSSH: user@host:/path  |  Docker: docker://name/path",
            )
            set_localized_placeholder(self.b, "user@server:/var/www/web")
            set_localized_tooltip(
                self.b,
                "BETA: the second sync endpoint. Mutagen synchronizes the contents of both directories.",
            )
        else:
            set_localized_placeholder(self.a, "tcp:localhost:8080")
            set_localized_tooltip(
                self.a,
                "Source: local address where forwarding will listen.\nExample: tcp:localhost:8080",
            )
            set_localized_placeholder(self.b, "docker://web:tcp:localhost:8080")
            set_localized_tooltip(
                self.b, "Destination: remote address to which traffic is forwarded (SSH or Docker)."
            )
        rowa = QHBoxLayout()
        rowa.addWidget(self.a)
        if kind == "sync":
            rowa.addWidget(button("…", self.browse_alpha))
        form.addRow("ALPHA" if kind == "sync" else "Source", rowa)
        form.addRow("BETA" if kind == "sync" else "Destination", self.b)
        if kind == "forward" and self.ui_mode == "advanced":
            self.socket_overwrite_source = QComboBox()
            add_localized_item(self.socket_overwrite_source, "Leave existing entry", "leave")
            add_localized_item(
                self.socket_overwrite_source, "Overwrite existing entry", "overwrite"
            )
            self.socket_overwrite_destination = QComboBox()
            add_localized_item(self.socket_overwrite_destination, "Leave existing entry", "leave")
            add_localized_item(
                self.socket_overwrite_destination, "Overwrite existing entry", "overwrite"
            )
            self.socket_owner_source = QLineEdit()
            self.socket_owner_destination = QLineEdit()
            self.socket_group_source = QLineEdit()
            self.socket_group_destination = QLineEdit()
            self.socket_permission_source = QLineEdit()
            self.socket_permission_destination = QLineEdit()
            for control in (self.socket_owner_source, self.socket_owner_destination):
                set_localized_placeholder(control, "Optional socket owner")
            for control in (self.socket_group_source, self.socket_group_destination):
                set_localized_placeholder(control, "Optional socket group")
            for control in (self.socket_permission_source, self.socket_permission_destination):
                set_localized_placeholder(control, "Optional octal mode, e.g. 0600")
            add_localized_row(form, "Source socket overwrite mode", self.socket_overwrite_source)
            add_localized_row(
                form, "Destination socket overwrite mode", self.socket_overwrite_destination
            )
            add_localized_row(form, "Source socket owner", self.socket_owner_source)
            add_localized_row(form, "Destination socket owner", self.socket_owner_destination)
            add_localized_row(form, "Source socket group", self.socket_group_source)
            add_localized_row(form, "Destination socket group", self.socket_group_destination)
            add_localized_row(form, "Source socket permission mode", self.socket_permission_source)
            add_localized_row(
                form, "Destination socket permission mode", self.socket_permission_destination
            )
            socket_note = label(
                "Socket flags are checked against the installed Mutagen CLI before creation. "
                "Remote endpoint support is validated by Mutagen. Leave preserves existing "
                "entries; overwrite requires high-risk typed confirmation.",
                muted=True,
            )
            socket_note.setWordWrap(True)
            form.addRow("", socket_note)
        self.mode = QComboBox()
        sync_modes = ["two-way-safe", "one-way-safe"]
        if self.ui_mode == "advanced":
            sync_modes = ["two-way-safe", "two-way-resolved", "one-way-safe", "one-way-replica"]
        self.mode.addItems(sync_modes)
        self.mode_descriptions = {
            "two-way-safe": (
                "Bidirectional: changes from ALPHA and BETA flow both ways. Conflicts that "
                "would discard unsynchronized data stay for manual resolution.",
                "Obousměrná synchronizace: změny z ALPHA i BETA se přenášejí na druhou stranu. "
                "Konflikty, jejichž automatické vyřešení by ztratilo nesynchronizovaná data, "
                "zůstávají k ručnímu vyřešení.",
            ),
            "two-way-resolved": (
                "Bidirectional: ALPHA wins every conflict, including when an ALPHA deletion "
                "overwrites a BETA change. BETA changes can be overwritten or deleted.",
                "Obousměrná synchronizace: ALPHA vyhrává každý konflikt, i když smazání na "
                "ALPHA přepíše změnu na BETA. Změny na BETA mohou být přepsány nebo smazány.",
            ),
            "one-way-safe": (
                "Only changes from ALPHA to BETA propagate. BETA-only content is preserved; "
                "conflicting BETA edits stay unresolved, while deletions of ALPHA content on "
                "BETA are restored from ALPHA.",
                "Přenášejí se jen změny z ALPHA na BETA. Obsah pouze na BETA zůstává; "
                "konfliktní úpravy na BETA se nevyřeší automaticky a smazaný obsah ALPHA se "
                "na BETA obnoví z ALPHA.",
            ),
            "one-way-replica": (
                "One-way ALPHA to BETA: BETA becomes an exact copy of ALPHA. Deletes BETA-only "
                "content and overwrites BETA changes.",
                "Jednosměrně z ALPHA na BETA: BETA bude přesnou kopií ALPHA. Smaže obsah jen na "
                "BETA a přepíše změny na BETA.",
            ),
        }
        self.mode_help = label("", muted=True)
        self.mode_help.setWordWrap(True)

        def update_mode_help(mode: str) -> None:
            english, czech = self.mode_descriptions[mode]
            set_localized_text(self.mode_help, english, czech=czech)

        self.mode.currentTextChanged.connect(update_mode_help)
        self.ignore = QPlainTextEdit()
        self.ignore.setFixedHeight(75)
        set_localized_placeholder(self.ignore, "One ignore pattern per line, e.g. node_modules")
        set_localized_tooltip(
            self.ignore,
            "File/directory patterns to ignore (glob, one per line).\nExamples: node_modules, *.log, .DS_Store, build/",
        )
        self.ignore_vcs = localized_checkbox("Ignore .git, .svn, and other VCS directories")
        self.ignore_vcs.setTristate(True)
        self.ignore_vcs.setCheckState(Qt.CheckState.PartiallyChecked)
        set_localized_tooltip(
            self.ignore_vcs,
            "Checked: ignore VCS directories. Unchecked: propagate them. Partially checked: inherit global and Mutagen defaults.",
        )
        self.pause = localized_checkbox("Start paused")
        set_localized_tooltip(
            self.pause,
            "The session will be created, but sync will not start. Start it manually with the Resume button.",
        )
        self.replica_backup = localized_checkbox(
            "I have a recoverable backup of the BETA destination"
        )
        set_localized_tooltip(
            self.replica_backup,
            "Confirm a separate recoverable copy exists before using destructive replica mode.",
        )
        self.replica_backup.setVisible(False)
        if kind == "sync":
            self.profile = QComboBox()
            for code, (title, _flags) in PROFILES.items():
                self.profile.addItem(title, code)
            self.profile.setCurrentIndex(max(0, self.profile.findData(default_profile)))
            set_localized_tooltip(
                self.profile,
                "The profile controls how Mutagen watches for file changes when creating a session.\ninotify/FSEvents = native OS events (fast, low overhead).\nPolling = active checks — slower, but also works on network drives.",
            )
            add_localized_row(form, "File Change Detection", self.profile)
            add_localized_row(form, "Mode", self.mode)
            form.addRow("", self.mode_help)
            update_mode_help(self.mode.currentText())
            self.ignore_preset = QComboBox()
            self.ignore_presets = {
                "None": (),
                "Python": ("__pycache__/", "*.py[cod]", ".venv/", ".pytest_cache/"),
                "Node.js": ("node_modules/", "dist/"),
                "PHP / Composer": ("vendor/", "cache/", "*.log"),
                "JetBrains IDE": (".idea/",),
                "VS Code": (".vscode/",),
                "Temporary files and logs": ("*.tmp", "*.swp", "*.log", ".DS_Store", "Thumbs.db"),
                "IDE and logs": (".idea/", ".vscode/", "*.log", ".DS_Store"),
            }
            saved_ignores = load_ignore_presets(
                _settings_path_provider().with_name("ignore-presets.json")
            )
            if saved_ignores.valid:
                for preset in saved_ignores.presets:
                    title = preset.name
                    if title in self.ignore_presets:
                        title += " (custom)"
                    self.ignore_presets[title] = preset.patterns
            elif saved_ignores.warnings:
                self.ignore_store_warning = " ".join(saved_ignores.warnings)
            self.ignore_preset.addItems(list(self.ignore_presets))
            set_localized_accessible_name(self.ignore_preset, "Ignore preset")
            self.ignore_preset.activated.connect(self.apply_ignore_preset)
            preset_row = QHBoxLayout()
            preset_row.addWidget(self.ignore_preset)
            preset_row.addWidget(
                button("Import .gitignore/.dockerignore…", self.import_ignore_file)
            )
            preset_row.addWidget(button("Explain path…", self.explain_ignore))
            add_localized_row(form, "Ignore preset", preset_row)
            add_localized_row(form, "Ignore", self.ignore)
            form.addRow("", self.ignore_vcs)
        form.addRow("", self.pause)
        if kind == "sync":
            form.addRow("", self.replica_backup)
        box.addLayout(form)
        info = label(
            "Warning: one-way-replica mode can overwrite and delete files at the destination."
            if kind == "sync"
            else "Forwarding exposes the destination connection through the specified source.",
            muted=True,
        )
        info.setWordWrap(True)
        box.addWidget(info)
        box.addWidget(
            label("Exact CLI argument preview (JSON array; no shell parsing)", muted=True)
        )
        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setFixedHeight(84)
        box.addWidget(self.command_preview)
        box.addWidget(
            button(
                "Preview Effective New-Session Configuration…",
                self.preview_effective_session_configuration,
            )
        )
        self.name.textChanged.connect(self.update_command_preview)
        self.a.textChanged.connect(self.update_command_preview)
        self.b.textChanged.connect(self.update_command_preview)
        self.pause.stateChanged.connect(lambda _state: self.update_command_preview())
        if kind == "sync":
            self.mode.currentIndexChanged.connect(self.update_command_preview)
            self.profile.currentIndexChanged.connect(self.update_command_preview)
            self.ignore_vcs.stateChanged.connect(lambda _state: self.update_command_preview())
            self.ignore.textChanged.connect(self.update_command_preview)
        elif self.ui_mode == "advanced":
            for combo_control in (
                self.socket_overwrite_source,
                self.socket_overwrite_destination,
            ):
                if combo_control is not None:
                    combo_control.currentIndexChanged.connect(self.update_command_preview)
            for text_control in (
                self.socket_owner_source,
                self.socket_owner_destination,
                self.socket_group_source,
                self.socket_group_destination,
                self.socket_permission_source,
                self.socket_permission_destination,
            ):
                if text_control is not None:
                    text_control.textChanged.connect(self.update_command_preview)
        self.mode.currentIndexChanged.connect(self.update_replica_backup_visibility)
        self.update_replica_backup_visibility()
        if self.connection_profile is not None:
            self.connection_profile.currentIndexChanged.connect(self.apply_connection_profile)
        if initial_path:
            norm_path = initial_path.replace("/", "\\") if os.name == "nt" else initial_path
            self.a.setText(norm_path)
            if not self.name.text():
                folder_name = Path(initial_path).name
                if folder_name:
                    self.name.setText(folder_name)
        self._base_name = self.name.text()
        self._base_a = self.a.text()
        self._base_b = self.b.text()
        self.update_command_preview()
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        set_localized_text(controls.button(QDialogButtonBox.StandardButton.Ok), "Create Session")
        set_localized_text(controls.button(QDialogButtonBox.StandardButton.Cancel), "Cancel")
        controls.accepted.connect(self.validate)
        controls.rejected.connect(self.reject)
        box.addWidget(controls)

    def browse_alpha(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, translate_text("Choose Local Directory", active_language())
        )
        if selected:
            self.a.setText(selected.replace("/", "\\") if os.name == "nt" else selected)

    def apply_ignore_preset(self, index: int) -> None:
        preset = self.ignore_presets.get(self.ignore_preset.itemText(index), ())
        existing = self.ignore.toPlainText().splitlines()
        self.ignore.setPlainText("\n".join(dict.fromkeys([*existing, *preset])))

    def import_ignore_file(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Import Ignore Rules", active_language()),
            str(Path.cwd()),
            translate_text(
                "Ignore files (.gitignore .dockerignore);;All files (*)", active_language()
            ),
        )
        if not source:
            return
        path = Path(source)
        source_format: Literal["gitignore", "dockerignore"] = (
            "dockerignore" if path.name == ".dockerignore" else "gitignore"
        )
        try:
            if path.stat().st_size > 1024 * 1024:
                raise IgnorePresetError("Ignore source exceeds the 1 MiB size limit.")
            preview = parse_ignore_file(path.read_bytes(), source_format=source_format)
        except (OSError, IgnorePresetError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Ignore Import", active_language()),
                f"Could not read rules: {exc}",
            )
            return
        dialog = IgnoreConversionDialog(preview, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        patterns = dialog.selected_patterns()
        existing = self.ignore.toPlainText().splitlines()
        self.ignore.setPlainText("\n".join(dict.fromkeys([*existing, *patterns])))

    def explain_ignore(self) -> None:
        path, accepted = QInputDialog.getText(
            self,
            translate_text("Explain Ignore Rules", active_language()),
            translate_text("Path relative to the sync root:", active_language()),
        )
        if not accepted:
            return
        try:
            global_preview = load_effective_sync_configuration(Path.home() / ".mutagen.yml", ())
            effective_preview = load_effective_sync_configuration(
                Path.home() / ".mutagen.yml", self.arguments()[:-2]
            )
            if not global_preview.valid or not effective_preview.valid:
                raise IgnorePresetError(global_preview.error or effective_preview.error)
            global_values = global_preview.as_mapping()
            effective_values = effective_preview.as_mapping()
            global_rules = tuple(global_values.get("ignore.paths", ()))
            vcs_rules = (".git/", ".svn/", ".hg/", ".bzr/", "_darcs/")
            vcs_origin = effective_preview.origin_for("ignore.vcs")
            if effective_values.get("ignore.vcs") is True and vcs_origin == "global config":
                global_rules += vcs_rules
            project_rules: tuple[str, ...] = ()
            session_rules = tuple(self.ignore.toPlainText().splitlines())
            if effective_values.get("ignore.vcs") is True and vcs_origin == "command line":
                session_rules += vcs_rules
            result = explain_ignore_path(
                path,
                global_rules=global_rules,
                project_rules=project_rules,
                session_rules=session_rules,
            )
        except IgnorePresetError as exc:
            QMessageBox.warning(self, translate_text("Ignore Preview", active_language()), str(exc))
            return
        status = (
            "Known rules indicate ignored" if result.ignored else "Known rules indicate not ignored"
        )
        matched = (
            f"\nLast matching rule: {result.matched_rule} ({result.scope})"
            if result.matched_rule
            else "\nNo rule matched."
        )
        QMessageBox.information(
            self,
            translate_text("Ignore Preview", active_language()),
            f"{status}{matched}\n\n"
            f"{format_ignore_layers(global_rules=global_rules, project_rules=project_rules, session_rules=session_rules, annotate=True)}"
            "\n\nNative project defaults are not selected here. Built-in defaults are not enumerated.\n"
            f"{result.note}",
        )

    def preview_effective_session_configuration(self) -> None:
        config_path = Path.home() / ".mutagen.yml"
        if self.kind == "sync":
            preview = load_effective_sync_configuration(config_path, self.arguments()[:-2])
            details = (
                "New standalone sync only. Global defaults precede CLI options; ignore paths append.",
                "Built-in defaults and unselected native project defaults are not enumerated.",
            )
        else:
            preview = load_effective_forward_configuration(config_path, self.arguments()[:-2])
            details = (
                "New standalone forward only. Global defaults precede CLI options.",
                "Built-in defaults are not enumerated.",
            )
        if not preview.valid:
            QMessageBox.warning(
                self,
                translate_text("Effective Configuration", active_language()),
                preview.error,
            )
            return
        lines = [
            f"{translate_text('Global source', active_language())}: {preview.source_path}",
            translate_text(details[0], active_language()),
            translate_text(details[1], active_language()),
        ]
        lines.extend(
            f"{key} = {json.dumps(value, ensure_ascii=False)}  [{origin}]"
            for key, value, origin in preview.values
        )
        if not preview.values:
            lines.append(
                translate_text("No explicit global or CLI configuration values.", active_language())
            )
        QMessageBox.information(
            self,
            translate_text("Effective Configuration", active_language()),
            "\n\n".join(lines),
        )

    def apply_connection_profile(self, *_args: object) -> None:
        if self.connection_profile is None:
            return
        profile = self.connection_profile.currentData()
        if not isinstance(profile, ConnectionProfile):
            self.name.setText(self._base_name)
            self.a.setText(self._base_a)
            self.b.setText(self._base_b)
            if self.kind == "sync":
                self.mode.setCurrentText(self.default_sync_mode)
                self.ignore.setPlainText("")
                self.ignore_vcs.setCheckState(Qt.CheckState.PartiallyChecked)
                idx = max(0, self.profile.findData(self.default_profile))
                self.profile.setCurrentIndex(idx)
            elif self.kind == "forward" and self.ui_mode == "advanced":
                if self.socket_overwrite_source is not None:
                    self.socket_overwrite_source.setCurrentIndex(0)
                if self.socket_overwrite_destination is not None:
                    self.socket_overwrite_destination.setCurrentIndex(0)
                for ctrl in (
                    self.socket_owner_source,
                    self.socket_owner_destination,
                    self.socket_group_source,
                    self.socket_group_destination,
                    self.socket_permission_source,
                    self.socket_permission_destination,
                ):
                    if ctrl is not None:
                        ctrl.setText("")
            self.update_command_preview()
            return
        self.name.setText(profile.name)
        self.a.setText(profile.endpoint_a)
        self.b.setText(profile.endpoint_b)
        if self.kind == "sync":
            defaults = profile.defaults
            mode = defaults.get("mode")
            if isinstance(mode, str) and self.mode.findText(mode) >= 0:
                self.mode.setCurrentText(mode)
            else:
                self.mode.setCurrentText(self.default_sync_mode)
            ignore_paths = defaults.get("ignore.paths")
            if isinstance(ignore_paths, (list, tuple)):
                self.ignore.setPlainText("\n".join(str(item) for item in ignore_paths))
            else:
                self.ignore.setPlainText("")
            ignore_vcs = defaults.get("ignore.vcs")
            if isinstance(ignore_vcs, bool):
                self.ignore_vcs.setChecked(ignore_vcs)
            else:
                self.ignore_vcs.setCheckState(Qt.CheckState.PartiallyChecked)
            watch = defaults.get("watch.mode")
            interval = defaults.get("watch.pollingInterval")
            profile_code = None
            if isinstance(watch, str) and (isinstance(interval, int) or interval is None):
                profile_code = {
                    ("portable", None): "events",
                    ("force-poll", 5): "fast_poll",
                    ("force-poll", 20): "balanced_poll",
                    ("force-poll", 60): "eco_poll",
                    ("no-watch", None): "manual",
                }.get((watch, interval))
            if profile_code is not None:
                profile_index = self.profile.findData(profile_code)
                if profile_index >= 0:
                    self.profile.setCurrentIndex(profile_index)
            else:
                idx = max(0, self.profile.findData(self.default_profile))
                self.profile.setCurrentIndex(idx)
        elif self.kind == "forward" and self.ui_mode == "advanced":
            defaults = profile.defaults
            for side, combo, owner_ctrl, group_ctrl, perm_ctrl in (
                (
                    "source",
                    self.socket_overwrite_source,
                    self.socket_owner_source,
                    self.socket_group_source,
                    self.socket_permission_source,
                ),
                (
                    "destination",
                    self.socket_overwrite_destination,
                    self.socket_owner_destination,
                    self.socket_group_destination,
                    self.socket_permission_destination,
                ),
            ):
                side_overwrite = defaults.get(
                    f"{side}.socket.overwriteMode", defaults.get("socket.overwriteMode", "leave")
                )
                if combo is not None:
                    combo_idx = combo.findData(side_overwrite)
                    combo.setCurrentIndex(max(0, combo_idx))
                if owner_ctrl is not None:
                    owner_ctrl.setText(str(defaults.get(f"{side}.socket.owner", "")))
                if group_ctrl is not None:
                    group_ctrl.setText(str(defaults.get(f"{side}.socket.group", "")))
                if perm_ctrl is not None:
                    perm_ctrl.setText(str(defaults.get(f"{side}.socket.permissionMode", "")))
        self.update_command_preview()

    def update_command_preview(self, *_args: object) -> None:
        command = [self.executable, self.kind, "create", *self.arguments()]
        self.command_preview.setPlainText(json.dumps(command, ensure_ascii=False, indent=2))

    def endpoint_error(self, endpoint: str) -> str | None:
        value = endpoint.strip()
        if not value:
            return _text("Enter both endpoints.")
        if "\x00" in value or value.startswith("-"):
            return _text("Endpoint contains an invalid NUL or option-like value.")
        if self.kind == "sync":
            if value.startswith("ssh://"):
                return _text("Use Mutagen's native SSH form, such as user@host:/path.")
            if value.startswith("docker://") and not value.removeprefix("docker://").strip("/:"):
                return _text("Docker endpoint needs a container name or path.")
            if "@" in value and ":" not in value:
                return _text(
                    "SSH endpoint needs a path after the host, for example user@host:/path."
                )
            return None
        if value.startswith(("tcp:", "tcp4:", "tcp6:")):
            address = value.split(":", 1)[1]
            if ":" not in address:
                return _text("TCP endpoint needs a host and port, for example tcp:localhost:8080.")
            host, port = address.rsplit(":", 1)
            try:
                valid_port = 1 <= int(port) <= 65535
            except ValueError:
                valid_port = False
            if not host or not valid_port:
                return _text("TCP endpoint needs a host and a port from 1 to 65535.")
        elif value.startswith("unix:") and not value.removeprefix("unix:").strip():
            return _text("Unix socket endpoint needs a path.")
        elif value.startswith("unix:") and not self.local_unix_socket_supported():
            return _text("Unix sockets are unavailable on this local platform.")
        elif value.startswith("npipe:") and os.name != "nt":
            return _text("Windows named pipes are available only on Windows endpoints.")
        elif value.startswith("docker://") and not value.removeprefix("docker://").strip("/:"):
            return _text("Docker forwarding endpoint needs a container and address.")
        return None

    @staticmethod
    def local_unix_socket_supported() -> bool:
        if os.name == "posix":
            return True
        if sys.platform == "win32":
            try:
                return sys.getwindowsversion().build >= 17063
            except AttributeError:
                return False
        return False

    def forward_socket_error(self) -> str | None:
        if self.socket_overwrite_source is None:
            return None
        assert self.socket_overwrite_destination is not None
        assert self.socket_owner_source is not None
        assert self.socket_owner_destination is not None
        assert self.socket_group_source is not None
        assert self.socket_group_destination is not None
        assert self.socket_permission_source is not None
        assert self.socket_permission_destination is not None
        from forward_configuration import validate_forward_proposal

        endpoints = {
            "source": (self.a.text().strip(), "source"),
            "destination": (self.b.text().strip(), "destination"),
        }
        fields = {
            "source": {
                "overwriteMode": self.socket_overwrite_source.currentData(),
                "owner": self.socket_owner_source.text().strip(),
                "group": self.socket_group_source.text().strip(),
                "permissionMode": self.socket_permission_source.text().strip(),
            },
            "destination": {
                "overwriteMode": self.socket_overwrite_destination.currentData(),
                "owner": self.socket_owner_destination.text().strip(),
                "group": self.socket_group_destination.text().strip(),
                "permissionMode": self.socket_permission_destination.text().strip(),
            },
        }
        from forward_configuration import is_unix_forward_endpoint, local_unix_socket_entry_type

        for side, (endpoint, field_side) in endpoints.items():
            values = fields[field_side]
            explicitly_configured = values["overwriteMode"] != "leave" or any(
                values[key] for key in ("owner", "group", "permissionMode")
            )
            if explicitly_configured and not is_unix_forward_endpoint(endpoint):
                return _text("Socket settings for {side} require a Unix socket endpoint.").format(
                    side=side.title()
                )
            if values["overwriteMode"] == "overwrite":
                entry_type = local_unix_socket_entry_type(endpoint)
                if entry_type == "directory":
                    return _text(
                        "A directory already exists at the local socket path; overwrite is blocked."
                    )
                if entry_type in {"unavailable", "special filesystem entry"}:
                    return _text(
                        "The local socket path cannot be safely inspected; overwrite is blocked."
                    )
            try:
                for key, value in values.items():
                    if key in {"owner", "group", "permissionMode"} and not value:
                        continue
                    validate_forward_proposal(f"{side}.socket.{key}", value)
            except ValueError as exc:
                return _text(str(exc))
        return None

    def validate(self) -> None:
        endpoint_message = self.endpoint_error(self.a.text()) or self.endpoint_error(self.b.text())
        if endpoint_message:
            QMessageBox.warning(
                self, translate_text("Invalid Endpoint", active_language()), endpoint_message
            )
            return
        socket_message = self.forward_socket_error()
        if socket_message:
            QMessageBox.warning(
                self, translate_text("Invalid Socket Settings", active_language()), socket_message
            )
            return
        if self.kind == "forward" and any(
            control is not None and control.currentData() == "overwrite"
            for control in (self.socket_overwrite_source, self.socket_overwrite_destination)
        ):
            from forward_configuration import local_unix_socket_entry_type

            overwrite_endpoints = ", ".join(
                f"{endpoint} ({translate_text(local_unix_socket_entry_type(endpoint) or 'remote path not inspected', active_language())})"
                for control, endpoint in (
                    (self.socket_overwrite_source, self.a.text().strip()),
                    (self.socket_overwrite_destination, self.b.text().strip()),
                )
                if control is not None and control.currentData() == "overwrite"
            )
            response = QMessageBox.warning(
                self,
                translate_text("Review Socket Overwrite", active_language()),
                translate_text(
                    "Socket overwrite may remove one existing file, symbolic link, or socket at {endpoint}. A directory is never removed.",
                    active_language(),
                ).format(endpoint=overwrite_endpoints)
                + "\n\n"
                + translate_text("Continue to the high-risk confirmation?", active_language()),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        if self.kind == "sync":
            mode_warnings = {
                "two-way-resolved": (
                    "This mode resolves conflicts automatically with ALPHA as the winner. "
                    "Unmerged changes on BETA can be lost. Continue?"
                ),
                "one-way-replica": (
                    "This mode makes BETA an exact copy of ALPHA and can overwrite or delete "
                    "files on BETA that are not on ALPHA. Continue?"
                ),
            }
            warning = mode_warnings.get(self.mode.currentText())
            if warning:
                response = QMessageBox.warning(
                    self,
                    translate_text("Risky Mode", active_language()),
                    warning,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if response != QMessageBox.StandardButton.Yes:
                    return
            if self.mode.currentText() == "one-way-replica" and not self.replica_backup.isChecked():
                QMessageBox.warning(
                    self,
                    translate_text("Backup Required", active_language()),
                    translate_text(
                        "Create and verify a recoverable backup of BETA before continuing.",
                        active_language(),
                    ),
                )
                return
        if self.kind == "forward":
            from forward_configuration import classify_forward_listener

            classification = classify_forward_listener(self.a.text().strip())
            if classification.warning_required:
                response = QMessageBox.warning(
                    self,
                    translate_text("Public Forwarding Listener", active_language()),
                    translate_text(
                        "This source binds outside loopback ({scope}): {desc}.\n\n"
                        "Traffic to the destination may be exposed publicly or to other network devices. Continue?",
                        active_language(),
                    ).format(
                        scope=classification.scope,
                        desc=translate_text(classification.description, active_language()),
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if response != QMessageBox.StandardButton.Yes:
                    return
        self.accept()

    def update_replica_backup_visibility(self, *_args: object) -> None:
        visible = self.kind == "sync" and self.mode.currentText() == "one-way-replica"
        self.replica_backup.setVisible(visible)

    @property
    def backup_choice(self) -> str | None:
        if (
            self.kind == "sync"
            and self.mode.currentText() == "one-way-replica"
            and self.replica_backup.isChecked()
        ):
            return "operator-confirmed-recoverable-beta-backup"
        return None

    def arguments(self) -> list[str]:
        ignore_state = self.ignore_vcs.checkState()
        return build_session_arguments(
            self.kind,
            name=self.name.text(),
            paused=self.pause.isChecked(),
            mode=self.mode.currentText(),
            profile=self.profile.currentData() if self.kind == "sync" else "default",
            ignore_vcs=(
                True
                if ignore_state == Qt.CheckState.Checked
                else False
                if ignore_state == Qt.CheckState.Unchecked
                else None
            ),
            ignore_patterns=self.ignore.toPlainText().splitlines(),
            alpha=self.a.text(),
            beta=self.b.text(),
            socket_options={
                "source": (
                    self.socket_overwrite_source.currentData()
                    if self.socket_overwrite_source is not None
                    else None,
                    self.socket_owner_source.text() if self.socket_owner_source is not None else "",
                    self.socket_group_source.text() if self.socket_group_source is not None else "",
                    self.socket_permission_source.text()
                    if self.socket_permission_source is not None
                    else "",
                ),
                "destination": (
                    self.socket_overwrite_destination.currentData()
                    if self.socket_overwrite_destination is not None
                    else None,
                    self.socket_owner_destination.text()
                    if self.socket_owner_destination is not None
                    else "",
                    self.socket_group_destination.text()
                    if self.socket_group_destination is not None
                    else "",
                    self.socket_permission_destination.text()
                    if self.socket_permission_destination is not None
                    else "",
                ),
            },
        )
