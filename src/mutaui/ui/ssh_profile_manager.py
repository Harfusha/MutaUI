from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from mutaui.ui.localization import set_localized_placeholder, set_localized_title
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.widgets.basic import button, label
from mutaui.ui.worker import Worker
from ssh_profiles import (
    SSHCommandResult,
    SSHHostProfile,
    parse_ssh_config,
    resolve_ssh_options,
    test_ssh_connection,
)


class SSHProfileManagerDialog(QDialog):
    """Inspect local SSH aliases and run an explicit strict-host-key test."""

    def __init__(
        self, parent: QWidget | None = None, config_path: str | Path | None = None
    ) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path) if config_path else Path.home() / ".ssh" / "config"
        self._profiles: dict[str, SSHHostProfile] = {}
        self._config_valid = False
        self._running = False
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
        self.resolve_button = button(
            "Resolve with ssh -G",
            lambda: self.resolve_selected(async_execution=True),
            kind="primary",
        )
        row.addWidget(self.resolve_button)
        layout.addLayout(row)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        set_localized_placeholder(
            self.details, "Select an SSH alias to inspect its effective options."
        )
        layout.addWidget(self.details, 1)
        controls = QHBoxLayout()
        self.test_button = button(
            "Test connection…",
            lambda: self.test_selected(async_execution=True),
            kind="primary",
        )
        controls.addWidget(self.test_button)
        controls.addStretch(1)
        controls.addWidget(button("Done", self.accept))
        layout.addLayout(controls)
        self.reload_config()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._running:
            answer = QMessageBox.question(
                self,
                translate_text("SSH operation in progress", active_language()),
                translate_text(
                    "An SSH resolution or connection test is currently running. Close anyway?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.accept()

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

    def resolve_selected(self, checked: bool = False, *, async_execution: bool = False) -> None:
        alias = self.alias_input.currentText()
        if not self._config_valid or alias not in self._profiles or self._running:
            return
        self._running = True
        self.resolve_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.details.setPlainText(
            translate_text(
                "Resolving effective SSH configuration in background…", active_language()
            )
        )

        def do_resolve() -> SSHCommandResult:
            return resolve_ssh_options(alias)

        def on_success(result: object) -> None:
            self._running = False
            self.resolve_button.setEnabled(True)
            self.test_button.setEnabled(True)
            success = getattr(result, "success", False)
            message = getattr(result, "message", "") or "SSH resolution failed"
            stderr = getattr(result, "stderr", "")
            if not success:
                self.details.setPlainText(message + ("\n" + stderr if stderr else ""))
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
            options = getattr(result, "options", {})
            for key in keys:
                values = options.get(key)
                if not values:
                    continue
                lines.append(f"{key}: " + "; ".join(values))
                if key == "identityfile":
                    for value in values:
                        key_path = Path(value).expanduser()
                        lines.append(f"  key file exists: {key_path.is_file()} (contents not read)")
            profile = self._profiles.get(alias)
            if profile and profile.unsupported:
                lines.append(
                    "Unexpanded directives in config listing: " + ", ".join(profile.unsupported)
                )
            if str(options.get("stricthostkeychecking", ("",))[0]).lower() == "no":
                lines.append(
                    "WARNING: effective config disables strict host-key checking. Connection test overrides it to yes."
                )
            self.details.setPlainText("\n".join(lines))

        def on_error(err_str: str) -> None:
            self._running = False
            self.resolve_button.setEnabled(True)
            self.test_button.setEnabled(True)
            self.details.setPlainText(f"Error resolving SSH config: {err_str}")

        if not async_execution:
            try:
                res = do_resolve()
                on_success(res)
            except Exception as exc:
                on_error(str(exc))
            return

        worker = Worker(do_resolve)
        if worker.signals is not None:
            worker.signals.result.connect(on_success)
            worker.signals.error.connect(on_error)
            QThreadPool.globalInstance().start(worker)

    def test_selected(self, checked: bool = False, *, async_execution: bool = False) -> None:
        alias = self.alias_input.currentText()
        if not self._config_valid or alias not in self._profiles or self._running:
            return
        answer = QMessageBox.question(
            self,
            translate_text("Test SSH connection", active_language()),
            translate_text(
                "Connect to {alias} now? The test uses BatchMode and StrictHostKeyChecking=yes. It will not add or replace host keys.",
                active_language(),
            ).format(alias=alias),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._running = True
        self.resolve_button.setEnabled(False)
        self.test_button.setEnabled(False)
        self.details.appendPlainText(
            translate_text("\nTesting SSH connection in background…", active_language())
        )

        def do_test() -> SSHCommandResult:
            return test_ssh_connection(alias)

        def on_success(result: object) -> None:
            self._running = False
            self.resolve_button.setEnabled(True)
            self.test_button.setEnabled(True)
            message = getattr(result, "message", "")
            stderr = getattr(result, "stderr", "")
            success = getattr(result, "success", False)
            detail = message
            if stderr.strip():
                detail += "\n\n" + stderr.strip()
            if success:
                QMessageBox.information(
                    self, translate_text("SSH connection test", active_language()), detail
                )
            else:
                QMessageBox.warning(
                    self, translate_text("SSH connection test", active_language()), detail
                )

        def on_error(err_str: str) -> None:
            self._running = False
            self.resolve_button.setEnabled(True)
            self.test_button.setEnabled(True)
            QMessageBox.warning(
                self,
                translate_text("SSH connection test", active_language()),
                f"SSH test failed: {err_str}",
            )

        if not async_execution:
            try:
                res = do_test()
                on_success(res)
            except Exception as exc:
                on_error(str(exc))
            return

        worker = Worker(do_test)
        if worker.signals is not None:
            worker.signals.result.connect(on_success)
            worker.signals.error.connect(on_error)
            QThreadPool.globalInstance().start(worker)
