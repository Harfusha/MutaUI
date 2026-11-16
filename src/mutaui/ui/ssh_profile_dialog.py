from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from mutaui.ui.dialog_components import button, label
from mutaui.ui.localization import set_localized_placeholder, set_localized_title
from mutaui.ui.preferences import active_language, translate_text
from ssh_profiles import parse_ssh_config, resolve_ssh_options, test_ssh_connection


class SSHProfileManagerDialog(QDialog):
    """Inspect local SSH aliases and run an explicit strict-host-key test."""

    def __init__(
        self, parent: QWidget | None = None, config_path: str | Path | None = None
    ) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path) if config_path else Path.home() / ".ssh" / "config"
        set_localized_title(self, "SSH Profiles")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Read-only OpenSSH profile inspection", size=18, bold=True))
        layout.addWidget(
            label(
                "Configuration and private keys are never changed or opened. Effective options use local `ssh -G`; the connection test requires a known host key.",
                muted=True,
            )
        )
        self.config_status = label(str(self.config_path), muted=True)
        self.config_status.setWordWrap(True)
        layout.addWidget(self.config_status)
        row = QHBoxLayout()
        self.alias_input = QComboBox()
        self.alias_input.setEditable(False)
        row.addWidget(self.alias_input, 1)
        row.addWidget(button("Reload config", self.reload_config))
        row.addWidget(button("Resolve with ssh -G", self.resolve_selected, kind="primary"))
        layout.addLayout(row)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        set_localized_placeholder(
            self.details, "Select an SSH alias to inspect its effective options."
        )
        layout.addWidget(self.details, 1)
        controls = QHBoxLayout()
        controls.addWidget(button("Test connection…", self.test_selected, kind="primary"))
        controls.addStretch(1)
        controls.addWidget(button("Done", self.accept))
        layout.addLayout(controls)
        self.reload_config()

    def reload_config(self) -> None:
        result = parse_ssh_config(self.config_path)
        self.alias_input.clear()
        self._profiles = {profile.alias: profile for profile in result.profiles}
        self.alias_input.addItems(list(self._profiles))
        notices = [str(self.config_path), "Read-only; no SSH files were changed."]
        notices.extend(result.warnings)
        if not result.valid:
            notices.insert(1, "Config could not be read safely; SSH operations are disabled.")
            self.alias_input.setEnabled(False)
        else:
            self.alias_input.setEnabled(bool(self._profiles))
        self.config_status.setText("\n".join(notices))
        self._config_valid = result.valid
        if not self._profiles:
            self.details.setPlainText(
                "No concrete SSH aliases found. Wildcard and Match rules are shown as warnings."
            )

    def resolve_selected(self) -> None:
        alias = self.alias_input.currentText()
        if not self._config_valid or alias not in self._profiles:
            return
        result = resolve_ssh_options(alias)
        if not result.success:
            self.details.setPlainText(
                result.message + ("\n" + result.stderr if result.stderr else "")
            )
            return
        keys = (
            "hostname",
            "user",
            "port",
            "identityfile",
            "identitiesonly",
            "proxyjump",
            "stricthostkeychecking",
            "userknownhostsfile",
            "globalknownhostsfile",
            "connecttimeout",
        )
        lines = [f"Alias: {alias}", "Effective values from local `ssh -G`:"]
        for key in keys:
            values = result.options.get(key)
            if not values:
                continue
            lines.append(f"{key}: " + "; ".join(values))
            if key == "identityfile":
                for value in values:
                    key_path = Path(value).expanduser()
                    lines.append(f"  key file exists: {key_path.is_file()} (contents not read)")
        profile = self._profiles[alias]
        if profile.unsupported:
            lines.append(
                "Unexpanded directives in config listing: " + ", ".join(profile.unsupported)
            )
        if str(result.options.get("stricthostkeychecking", ("",))[0]).lower() == "no":
            lines.append(
                "WARNING: effective config disables strict host-key checking. Connection test overrides it to yes."
            )
        self.details.setPlainText("\n".join(lines))

    def test_selected(self) -> None:
        alias = self.alias_input.currentText()
        if not self._config_valid or alias not in self._profiles:
            return
        answer = QMessageBox.question(
            self,
            translate_text("Test SSH connection", active_language()),
            f"Connect to {alias} now? The test uses BatchMode and StrictHostKeyChecking=yes. It will not add or replace host keys.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = test_ssh_connection(alias)
        detail = result.message
        if result.stderr.strip():
            detail += "\n\n" + result.stderr.strip()
        if result.success:
            QMessageBox.information(
                self, translate_text("SSH connection test", active_language()), detail
            )
        else:
            QMessageBox.warning(
                self, translate_text("SSH connection test", active_language()), detail
            )
