"""Onboarding and release update mixin for MainWindow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from mutagen_client import MutagenClient
from mutaui import __version__ as APP_VERSION
from mutaui.services.update_checker import (
    RELEASES_URL,
    UpdateCheckResult,
    check_for_update,
)
from mutaui.ui.formatters import write_settings
from mutaui.ui.localization import (
    set_localized_text,
    set_localized_title,
)
from mutaui.ui.onboarding import (
    host_architecture,
    inspect_cli,
    run_isolated_local_sync_test,
)
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.settings_registry import setting_tooltip
from mutaui.ui.widgets.basic import (
    localized_button,
    localized_checkbox,
    localized_label,
)


class OnboardingMixin:
    onboarding_wizard: QWizard | None = None
    _release_check_result: UpdateCheckResult | None = None
    _onboarding_check_seq: int = 0

    def open_onboarding(self: Any) -> None:
        if self.onboarding_wizard is not None:
            self.onboarding_wizard.raise_()
            self.onboarding_wizard.activateWindow()
            return

        wizard = QWizard(self)
        set_localized_title(wizard, "Welcome to Mutagen Control")
        wizard.setMinimumWidth(560)
        self.onboarding_wizard = wizard
        self._onboarding_pending_client: MutagenClient | None = None

        welcome = QWizardPage()
        set_localized_title(welcome, "Welcome", page_title=True)
        welcome_layout = QVBoxLayout(welcome)
        welcome_text = localized_label(
            "Mutagen Control uses the Mutagen CLI already installed on this computer. This guide checks the local CLI only. It does not connect to remote endpoints or create sessions unless you explicitly run the isolated local test."
        )
        welcome_text.setWordWrap(True)
        welcome_layout.addWidget(welcome_text)
        self.onboarding_update_check = localized_checkbox("Check releases on startup")
        self.onboarding_update_check.setChecked(
            bool(self.conf.get("check_updates_on_startup", False))
        )
        self.onboarding_update_check.setToolTip(
            setting_tooltip("check_updates_on_startup", self.ui_language)
        )
        welcome_layout.addWidget(self.onboarding_update_check)
        update_consent_note = localized_label(
            "Optional. If enabled, MutaUI checks public GitHub release metadata at startup. No session or device data is sent; no files are downloaded or installed."
        )
        update_consent_note.setWordWrap(True)
        welcome_layout.addWidget(update_consent_note)
        install_help = localized_button("Open official Mutagen installation guide")
        install_help.clicked.connect(self.open_mutagen_install_guide)
        welcome_layout.addWidget(install_help)
        wizard.addPage(welcome)

        cli_page = QWizardPage()
        set_localized_title(cli_page, "Find and check Mutagen", page_title=True)
        cli_layout = QVBoxLayout(cli_page)
        self.onboarding_cli_status = localized_label(
            "CLI not checked yet. Version and help checks are read-only and disable daemon autostart."
        )
        self.onboarding_cli_status.setWordWrap(True)
        cli_layout.addWidget(self.onboarding_cli_status)
        detect = localized_button("Check detected CLI")
        detect.clicked.connect(self.check_onboarding_cli)
        cli_layout.addWidget(detect)
        choose = localized_button("Choose Mutagen executable…")
        choose.clicked.connect(self.choose_onboarding_cli)
        cli_layout.addWidget(choose)
        wizard.addPage(cli_page)

        daemon_page = QWizardPage()
        set_localized_title(daemon_page, "Daemon verification", page_title=True)
        daemon_layout = QVBoxLayout(daemon_page)
        daemon_note = localized_label(
            "Mutagen manages sessions through a per-user background daemon. Mutagen Control will automatically connect to your daemon when starting."
        )
        daemon_note.setWordWrap(True)
        daemon_layout.addWidget(daemon_note)
        self.onboarding_test_status = localized_label("Mutagen CLI is ready.")
        self.onboarding_test_status.setWordWrap(True)
        daemon_layout.addWidget(self.onboarding_test_status)
        start_daemon_btn = localized_button("Start Mutagen daemon")
        start_daemon_btn.clicked.connect(self.start_onboarding_daemon)
        daemon_layout.addWidget(start_daemon_btn)
        wizard.addPage(daemon_page)

        wizard.accepted.connect(self.complete_onboarding)
        wizard.open()

    def start_onboarding_daemon(self: Any) -> None:
        client = self._onboarding_pending_client or self.client
        if not client.binary:
            set_localized_text(
                self.onboarding_test_status,
                "Select or install the Mutagen CLI before starting the daemon.",
            )
            return
        set_localized_text(self.onboarding_test_status, "Starting Mutagen daemon…")
        self.submit(
            lambda: client.command(["daemon", "start"]),
            lambda out: set_localized_text(
                self.onboarding_test_status, "Mutagen daemon started successfully."
            ),
            on_error=lambda err: self.onboarding_test_status.setText(
                translate_text("Could not start daemon: {message}", active_language()).format(
                    message=err
                )
            ),
        )

    def open_mutagen_install_guide(self: Any) -> None:
        QDesktopServices.openUrl(QUrl("https://mutagen.io/documentation/introduction/installation"))

    def choose_onboarding_cli(self: Any) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Select Mutagen executable", active_language()),
            str(Path.home()),
            translate_text("All files (*)", active_language()),
        )
        if not path:
            return
        candidate = MutagenClient(path)
        if not candidate.binary:
            set_localized_text(
                self.onboarding_cli_status, "That file is not an available Mutagen executable."
            )
            return
        self._onboarding_check_seq = getattr(self, "_onboarding_check_seq", 0) + 1
        self._onboarding_pending_client = candidate
        self.onboarding_cli_status.setText(
            f"Selected CLI: {candidate.binary} ({translate_text('Unverified', active_language())}). "
            f"{translate_text('Choose Check detected CLI to read its version and capabilities.', active_language())}"
        )

    def check_onboarding_cli(self: Any) -> None:
        client = self._onboarding_pending_client or self.client
        if not client.binary:
            set_localized_text(
                self.onboarding_cli_status,
                "Mutagen CLI was not found. Select its executable or open the official installation guide.",
            )
            return
        set_localized_text(
            self.onboarding_cli_status, "Checking CLI version and command capabilities…"
        )
        self._onboarding_check_seq = getattr(self, "_onboarding_check_seq", 0) + 1
        seq = self._onboarding_check_seq
        target_binary = client.binary
        self.submit(
            lambda: (seq, target_binary, inspect_cli(client)), self.show_onboarding_cli_result
        )

    def show_onboarding_cli_result(self: Any, result_payload: Any) -> None:
        if isinstance(result_payload, tuple) and len(result_payload) == 3:
            seq, target_binary, result = result_payload
            current_target = (self._onboarding_pending_client or self.client).binary
            if seq != getattr(self, "_onboarding_check_seq", 0) or target_binary != current_target:
                return  # Discard stale check result for non-matching or superseded selection
        else:
            result = result_payload
        capabilities = ", ".join(result.capabilities) or "no session commands confirmed"
        binary_architecture = ", ".join(result.architectures) or "Unknown"
        detail = (
            f"{result.version or result.error}\n"
            f"Path: {result.binary or 'not found'}\n"
            f"{translate_text('Binary architecture', active_language())}: {binary_architecture}\n"
            f"{translate_text('Host architecture', active_language())}: {host_architecture()}\n"
            f"Capabilities: {capabilities}"
        )
        if result.error and result.version:
            detail += f"\nSome help checks failed: {result.error}"
        self.onboarding_cli_status.setText(detail)

    def run_onboarding_local_test(self: Any) -> None:
        client = self._onboarding_pending_client or self.client
        if not client.binary:
            set_localized_text(
                self.onboarding_test_status,
                "Select or install the Mutagen CLI before running the local test.",
            )
            return
        set_localized_text(
            self.onboarding_test_status, "Running a disposable local-only sync test…"
        )
        self.submit(
            lambda: run_isolated_local_sync_test(client),
            self.onboarding_test_status.setText,
            on_error=lambda message: self.onboarding_test_status.setText(
                translate_text("Test failed: {message}", active_language()).format(message=message)
            ),
        )

    def complete_onboarding(self: Any) -> None:
        staged_conf = dict(self.conf)
        staged_conf["onboarding_completed"] = True
        update_check = getattr(self, "onboarding_update_check", None)
        if update_check is not None:
            staged_conf["check_updates_on_startup"] = update_check.isChecked()
        if self._onboarding_pending_client is not None:
            staged_conf["binary"] = self._onboarding_pending_client.binary
        try:
            write_settings(staged_conf)
        except OSError as exc:
            self.statusBar().showMessage(
                translate_text(
                    "Could not save onboarding status: {error}", active_language()
                ).format(error=exc),
                10000,
            )
            return
        # Disk write succeeded: safely commit in-memory changes
        self.conf.clear()
        self.conf.update(staged_conf)
        if self._onboarding_pending_client is not None:
            self.client = self._onboarding_pending_client
            if hasattr(self, "binary_edit"):
                self.binary_edit.setText(self.client.binary)

    def check_for_release_update_on_startup(self: Any) -> None:
        if (
            not self.demo
            and self.conf.get("onboarding_completed", False)
            and self.conf.get("check_updates_on_startup", False)
        ):
            self.check_for_release_update(startup=True)

    def save_release_check_preference(self: Any) -> None:
        self.conf["check_updates_on_startup"] = self.check_updates_on_startup.isChecked()
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self.add_log("Release-check preference saved")

    def check_for_release_update(self: Any, *, startup: bool = False) -> None:
        if self.demo or self._release_check_running:
            return
        enabled = bool(self.conf.get("check_updates_on_startup", False))
        if not startup:
            enabled = bool(
                getattr(self, "check_updates_on_startup", None)
                and self.check_updates_on_startup.isChecked()
            )
        if not enabled:
            return
        self._release_check_running = True
        check_button = getattr(self, "update_check_button", None)
        if check_button is not None:
            check_button.setEnabled(False)
        if hasattr(self, "update_status_label"):
            self.update_status_label.setText(
                translate_text("Checking for releases…", self.ui_language)
            )
        self.submit(
            lambda: check_for_update(current_version=APP_VERSION, enabled=True),
            self._release_check_succeeded,
            self._release_check_failed,
            self._release_check_finished,
        )

    def _release_check_succeeded(self: Any, result: UpdateCheckResult) -> None:
        self._release_check_result = result
        self._release_check_error = False
        self.refresh_release_check_status()

    def _release_check_failed(self: Any, _message: str) -> None:
        self._release_check_result = None
        self._release_check_error = True
        self.refresh_release_check_status()

    def _release_check_finished(self: Any) -> None:
        self._release_check_running = False
        check_button = getattr(self, "update_check_button", None)
        opt_in = getattr(self, "check_updates_on_startup", None)
        if check_button is not None and opt_in is not None:
            check_button.setEnabled(opt_in.isChecked() and not self.demo)
        self.refresh_release_check_status()

    def refresh_release_check_status(self: Any) -> None:
        status_label = getattr(self, "update_status_label", None)
        if status_label is None:
            return
        result = self._release_check_result
        if self._release_check_running:
            message = translate_text("Checking for releases…", self.ui_language)
        elif self._release_check_error:
            message = translate_text("Release check failed. See GitHub Releases.", self.ui_language)
        elif result is None or result.latest_version is None:
            message = translate_text("Update status has not been checked.", self.ui_language)
        elif result.available:
            message = translate_text(
                "A newer release is available: v{version}.", self.ui_language
            ).format(version=result.latest_version)
        else:
            message = translate_text(
                "Latest published release: v{version}.", self.ui_language
            ).format(version=result.latest_version)
        status_label.setText(message)
        open_button = getattr(self, "open_release_button", None)
        if open_button is not None:
            open_button.setVisible(bool(result and result.available))

    def open_release_page(self: Any) -> None:
        target_url = (
            self._release_check_result.release_url
            if self._release_check_result and self._release_check_result.release_url
            else RELEASES_URL
        )
        QDesktopServices.openUrl(QUrl(target_url))
