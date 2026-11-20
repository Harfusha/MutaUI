"""Choose a local support export and preview its sensitivity before saving."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from mutaui.ui.formatters import get_active_language as active_language


class SupportBundleDialog(QDialog):
    """Choose a local support export and preview its sensitivity before saving."""

    def __init__(
        self,
        *,
        snapshot_preview: str,
        event_count: int,
        monitored_line_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        czech = active_language().casefold().startswith("cs")
        copy = {
            "title": "Balíček podpory" if czech else "Support Bundle",
            "type": "Typ exportu" if czech else "Export type",
            "safe": "Bezpečný diagnostický report" if czech else "Safe diagnostics report",
            "full": "Úplný snímek relací" if czech else "Full session snapshot",
            "logs": "Místní snímek protokolů" if czech else "Local session log snapshot",
            "self_check": "Místní kontrola aplikace" if czech else "Local application self-check",
            "event_details": "Zahrnout text událostí (může obsahovat cesty a adresy)"
            if czech
            else "Include event text (may contain paths and addresses)",
            "line_details": "Zahrnout sledované řádky protokolu (mohou obsahovat citlivé údaje)"
            if czech
            else "Include monitored log lines (may contain sensitive details)",
            "save": "Uložit…" if czech else "Save…",
            "cancel": "Zrušit" if czech else "Cancel",
        }
        self.setWindowTitle(copy["title"])
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(copy["type"], self))
        self.mode = QComboBox(self)
        self.mode.addItem(copy["safe"], "safe")
        self.mode.addItem(copy["full"], "full")
        self.mode.addItem(copy["logs"], "logs")
        self.mode.addItem(copy["self_check"], "self_check")
        self.mode.currentIndexChanged.connect(self.update_preview)
        layout.addWidget(self.mode)
        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(180)
        layout.addWidget(self.preview)
        self.include_event_messages = QCheckBox(copy["event_details"], self)
        self.include_monitored_log_lines = QCheckBox(copy["line_details"], self)
        self.include_event_messages.stateChanged.connect(self.update_preview)
        self.include_monitored_log_lines.stateChanged.connect(self.update_preview)
        layout.addWidget(self.include_event_messages)
        layout.addWidget(self.include_monitored_log_lines)
        self._snapshot_preview = snapshot_preview[:2400]
        self._snapshot_preview_truncated = len(snapshot_preview) > 2400
        self._event_count = max(0, int(event_count))
        self._monitored_line_count = max(0, int(monitored_line_count))
        self._copy = copy
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setText(copy["save"])
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(copy["cancel"])
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.update_preview()

    def update_preview(self, *_args: object) -> None:
        mode = self.mode.currentData()
        logs_selected = mode == "logs"
        self.include_event_messages.setEnabled(logs_selected)
        self.include_monitored_log_lines.setEnabled(logs_selected)
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setText(
            (
                "Spustit kontrolu"
                if active_language().casefold().startswith("cs")
                else "Run self-check"
            )
            if mode == "self_check"
            else self._copy["save"]
        )
        if mode == "safe":
            preview = (
                "Bezpečný export použije povolený seznam polí; cesty, hostitelé, uživatelé, klíče a text protokolů vynechá."
                if active_language().casefold().startswith("cs")
                else "Safe export uses an allowlist; paths, hosts, users, keys, and log text are omitted."
            )
        elif mode == "full":
            heading = (
                "Náhled úplného snímku; může obsahovat místní cesty a endpointy:"
                if active_language().casefold().startswith("cs")
                else "Full snapshot preview; it may contain local paths and endpoints:"
            )
            preview = f"{heading}\n{self._snapshot_preview}"
            if self._snapshot_preview_truncated:
                preview += (
                    "\n… Zobrazen je jen začátek; export může obsahovat další položky."
                    if active_language().casefold().startswith("cs")
                    else "\n… Preview truncated; the export may contain more records."
                )
        elif mode == "self_check":
            preview = (
                "Zkontroluje místní cesty, integritu databáze, Qt, Python a verzi Mutagenu. Bez vzdálených zápisů."
                if active_language().casefold().startswith("cs")
                else "Checks local paths, database integrity, Qt, Python, and Mutagen version. No remote writes."
            )
        else:
            details = []
            if self.include_event_messages.isChecked():
                details.append(
                    "zahrne text událostí"
                    if active_language().casefold().startswith("cs")
                    else "includes event text"
                )
            if self.include_monitored_log_lines.isChecked():
                details.append(
                    "zahrne sledované řádky"
                    if active_language().casefold().startswith("cs")
                    else "includes monitored log lines"
                )
            if not details:
                details.append(
                    "bez textových detailů"
                    if active_language().casefold().startswith("cs")
                    else "omits raw text"
                )
            preview = (
                f"Místní export: {self._event_count} událostí, {self._monitored_line_count} sledovaných řádků; "
                f"{', '.join(details)}."
                if active_language().casefold().startswith("cs")
                else f"Local export: {self._event_count} events, {self._monitored_line_count} monitored lines; "
                f"{', '.join(details)}."
            )
            if (
                self.include_event_messages.isChecked()
                or self.include_monitored_log_lines.isChecked()
            ):
                preview += (
                    " Citlivý text bude před uložením potvrzen."
                    if active_language().casefold().startswith("cs")
                    else " Sensitive text will require confirmation before saving."
                )
        self.preview.setPlainText(preview)


__all__ = ["SupportBundleDialog"]
