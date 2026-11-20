"""Interactive diagnostic troubleshooting assistant for Mutagen sessions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from html import escape as html_escape

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mutaui.domain.models import DiagnosticIssue, SessionSnapshot
from mutaui.services.session_doctor import (
    DiagnosticRemedy,
    SessionDoctorReport,
    get_diagnostic_remedy,
)
from mutaui.ui.formatters import get_active_language as active_language


class TroubleshooterDialog(QDialog):
    """Interactive troubleshooting assistant that guides users through resolving sync issues."""

    def __init__(
        self,
        sessions: Sequence[SessionSnapshot],
        report: SessionDoctorReport | None = None,
        *,
        selected_identifier: str | None = None,
        on_refresh: Callable[[], None] | None = None,
        on_open_settings: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sessions = list(sessions)
        self._report = report
        self._on_refresh = on_refresh
        self._on_open_settings = on_open_settings
        self._czech = active_language().casefold().startswith("cs")

        self.setWindowTitle(
            "Průvodce řešením potíží se synchronizací"
            if self._czech
            else "Sync Troubleshooting Assistant"
        )
        self.resize(720, 560)
        self.setMinimumSize(600, 480)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title_label = QLabel(
            "Diagnostický pomocník Mutagenu" if self._czech else "Mutagen Diagnostic Assistant",
            self,
        )
        title_label.setStyleSheet("font-size: 17px; font-weight: bold; color: #E8EEF5;")
        header_layout.addWidget(title_label)

        sub_label = QLabel(
            "Zde naleznete vysvětlení příčiny a doporučený postup nápravy pro časté problémy se synchronizací."
            if self._czech
            else "Explains root causes and step-by-step guidance to resolve common synchronization failures.",
            self,
        )
        sub_label.setStyleSheet("color: #8C9BAE; font-size: 12px;")
        sub_label.setWordWrap(True)
        header_layout.addWidget(sub_label)
        main_layout.addLayout(header_layout)

        # Session selector bar
        selector_layout = QHBoxLayout()
        selector_label = QLabel("Relace:" if self._czech else "Session:", self)
        selector_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        selector_layout.addWidget(selector_label)

        self.session_combo = QComboBox(self)
        self.session_combo.setStyleSheet(
            "QComboBox { padding: 6px 10px; font-size: 13px; background: #131E2B; border: 1px solid #2B3A4C; border-radius: 4px; color: #E8EEF5; } "
            "QComboBox::drop-down { border: none; } "
            "QComboBox QAbstractItemView { background: #131E2B; color: #E8EEF5; selection-background-color: #1E3148; }"
        )
        selector_layout.addWidget(self.session_combo, 1)
        main_layout.addLayout(selector_layout)

        # Scrollable content area for diagnosis & remediation
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(
            "QScrollArea { border: 1px solid #212E3F; border-radius: 6px; background: #0C1521; }"
        )

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: #0C1521;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(14)
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area, 1)

        # Bottom action bar
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        self.copy_btn = QPushButton(
            "Zkopírovat diagnostiku" if self._czech else "Copy Diagnostics", self
        )
        self.copy_btn.clicked.connect(self._copy_diagnostic_summary)
        actions_layout.addWidget(self.copy_btn)

        if self._on_open_settings is not None:
            self.settings_btn = QPushButton(
                "Nastavení relace…" if self._czech else "Session Settings…", self
            )
            self.settings_btn.clicked.connect(self._open_selected_settings)
            actions_layout.addWidget(self.settings_btn)

        if self._on_refresh is not None:
            self.refresh_btn = QPushButton(
                "Zkontrolovat stav" if self._czech else "Refresh Status", self
            )
            self.refresh_btn.clicked.connect(self._refresh_status)
            actions_layout.addWidget(self.refresh_btn)

        actions_layout.addStretch()

        close_btn = QPushButton("Zavřít" if self._czech else "Close", self)
        close_btn.setStyleSheet(
            "QPushButton { background: #1E2D40; color: #E8EEF5; border: 1px solid #2B3D55; border-radius: 4px; padding: 6px 16px; font-weight: bold; } "
            "QPushButton:hover { background: #26384F; }"
        )
        close_btn.clicked.connect(self.accept)
        actions_layout.addWidget(close_btn)

        main_layout.addLayout(actions_layout)

        # Populate sessions into combo
        self._populate_sessions(selected_identifier)
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)
        self._render_current_diagnosis()

    def _issues_for_session(self, session_id: str) -> list[DiagnosticIssue]:
        if self._report is None:
            return []
        return [issue for issue in self._report.issues if issue.session_identifier == session_id]

    def _populate_sessions(self, preselect_id: str | None = None) -> None:
        self.session_combo.clear()
        if not self._sessions:
            self.session_combo.addItem("Žádné relace" if self._czech else "No sessions", "")
            return

        first_problem_index = 0
        preselect_index = -1

        for idx, session in enumerate(self._sessions):
            ident = session.identity.identifier
            name = session.identity.name or ident[:12]
            issues = self._issues_for_session(ident)

            has_error = any(
                issue.severity == "error" for issue in issues
            ) or session.state.casefold() in {"error", "halted"}
            has_warning = any(issue.severity == "warning" for issue in issues) or bool(
                session.conflicts
            )

            icon = "🔴 " if has_error else ("🟠 " if has_warning else "🟢 ")
            label = f"{icon}{name} ({session.state})"
            self.session_combo.addItem(label, ident)

            if (has_error or has_warning) and first_problem_index == 0:
                first_problem_index = idx

            if preselect_id and ident == preselect_id:
                preselect_index = idx

        target_index = preselect_index if preselect_index >= 0 else first_problem_index
        if 0 <= target_index < self.session_combo.count():
            self.session_combo.setCurrentIndex(target_index)

    def _on_session_changed(self) -> None:
        self._render_current_diagnosis()

    def _render_current_diagnosis(self) -> None:
        # Clear existing layout
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        selected_id = self.session_combo.currentData()
        session = next((s for s in self._sessions if s.identity.identifier == selected_id), None)

        if not session:
            empty_lbl = QLabel(
                "Není vybrána žádná relace k diagnostice."
                if self._czech
                else "No session selected for diagnosis.",
                self.content_widget,
            )
            empty_lbl.setStyleSheet("color: #8C9BAE; font-size: 13px;")
            self.content_layout.addWidget(empty_lbl)
            return

        issues = self._issues_for_session(session.identity.identifier)

        # If no issues from doctor, but session state is error/halted:
        if not issues and session.state.casefold() in {"error", "halted"}:
            detail = str(session.native_config.get("lastError", ""))
            remedy = get_diagnostic_remedy(
                "session_error", language="cs" if self._czech else "en", detail=detail
            )
            self._render_issue_card(
                code="session_error",
                title=remedy.title,
                severity="error",
                explanation=remedy.explanation,
                detail=detail,
                remedy=remedy,
                session=session,
            )
            return

        # If session is healthy:
        if not issues:
            self._render_healthy_card(session)
            return

        # Render each identified issue
        for issue in issues:
            code = issue.code or "session_error"
            remedy = get_diagnostic_remedy(
                code,
                language="cs" if self._czech else "en",
                detail=issue.technical_detail or issue.explanation,
            )
            self._render_issue_card(
                code=code,
                title=remedy.title,
                severity=issue.severity,
                explanation=remedy.explanation,
                detail=issue.technical_detail,
                remedy=remedy,
                session=session,
            )

    def _render_healthy_card(self, session: SessionSnapshot) -> None:
        card = QWidget(self.content_widget)
        card.setStyleSheet(
            "background: #112217; border: 1px solid #1E462A; border-radius: 8px; padding: 14px;"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        status_lbl = QLabel(
            "🟢 Synchronizace funguje v pořádku"
            if self._czech
            else "🟢 Sync is Operating Normally",
            card,
        )
        status_lbl.setStyleSheet("color: #4ADE80; font-size: 15px; font-weight: bold;")
        layout.addWidget(status_lbl)

        info_text = (
            f"Relace <b>{html_escape(session.identity.name or session.identity.identifier)}</b> je ve stavu <b>{session.state}</b>. "
            "Mutagen nehlásí žádné chyby, odpojené koncové body ani nevyřešené konflikty."
            if self._czech
            else f"Session <b>{html_escape(session.identity.name or session.identity.identifier)}</b> is currently in state <b>{session.state}</b>. "
            "Mutagen reports no errors, disconnected endpoints, or unresolved conflicts."
        )
        info_lbl = QLabel(info_text, card)
        info_lbl.setStyleSheet("color: #A3E635; font-size: 13px;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        self.content_layout.addWidget(card)
        self.content_layout.addStretch()

    def _render_issue_card(
        self,
        *,
        code: str,
        title: str,
        severity: str,
        explanation: str,
        detail: str,
        remedy: DiagnosticRemedy,
        session: SessionSnapshot,
    ) -> None:
        card = QWidget(self.content_widget)
        border_color = "#E53E3E" if severity == "error" else "#DD6B20"
        bg_color = "#1D1619" if severity == "error" else "#1F1A14"
        card.setStyleSheet(
            f"background: {bg_color}; border: 1px solid {border_color}; border-radius: 8px; padding: 14px;"
        )
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        # Card Title Row
        title_row = QHBoxLayout()
        icon = "🔴 " if severity == "error" else "🟠 "
        title_lbl = QLabel(f"{icon}{title}", card)
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: bold;")
        title_row.addWidget(title_lbl)

        badge_text = (
            ("Chyba" if severity == "error" else "Upozornění")
            if self._czech
            else severity.capitalize()
        )
        badge_lbl = QLabel(badge_text, card)
        badge_lbl.setStyleSheet(
            f"background: {border_color}; color: #FFFFFF; font-size: 11px; font-weight: bold; border-radius: 3px; padding: 2px 6px;"
        )
        title_row.addWidget(badge_lbl)
        title_row.addStretch()
        layout.addLayout(title_row)

        # Explanation
        expl_lbl = QLabel(explanation, card)
        expl_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: 500;")
        expl_lbl.setWordWrap(True)
        layout.addWidget(expl_lbl)

        # Technical Detail (if available)
        if detail and detail.strip():
            detail_box = QPlainTextEdit(card)
            detail_box.setReadOnly(True)
            detail_box.setPlainText(detail.strip())
            detail_box.setMaximumHeight(80)
            detail_box.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 11px; background: #0A0F17; color: #CBD5E1; border: 1px solid #2B3A4C; border-radius: 4px; padding: 4px;"
            )
            layout.addWidget(detail_box)

        # Step-by-Step Remediation
        steps_header = QLabel(
            "Doporučený postup nápravy:" if self._czech else "Recommended Solution:",
            card,
        )
        steps_header.setStyleSheet(
            "color: #63B3ED; font-size: 13px; font-weight: bold; margin-top: 4px;"
        )
        layout.addWidget(steps_header)

        for idx, step in enumerate(remedy.remedy_steps, start=1):
            step_lbl = QLabel(f"<b>{idx}.</b> {html_escape(step)}", card)
            step_lbl.setStyleSheet("color: #EDF2F7; font-size: 12px; margin-left: 8px;")
            step_lbl.setWordWrap(True)
            layout.addWidget(step_lbl)

        # Quick command button if applicable
        if remedy.quick_command:
            cmd_layout = QHBoxLayout()
            cmd_layout.setContentsMargins(8, 4, 8, 4)
            cmd_box = QLabel(remedy.quick_command, card)
            cmd_box.setStyleSheet(
                "font-family: Consolas, monospace; font-size: 12px; background: #0A111A; color: #68D391; border: 1px solid #2D3748; border-radius: 4px; padding: 6px 10px;"
            )
            cmd_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cmd_layout.addWidget(cmd_box, 1)

            copy_cmd_btn = QPushButton("Kopírovat příkaz" if self._czech else "Copy Command", card)
            copy_cmd_btn.setStyleSheet(
                "background: #2B6CB0; color: #FFFFFF; font-size: 11px; font-weight: bold; padding: 6px 10px; border-radius: 4px;"
            )
            copy_cmd_btn.clicked.connect(
                lambda _, c=remedy.quick_command, btn=copy_cmd_btn: self._copy_command(c, btn)
            )
            cmd_layout.addWidget(copy_cmd_btn)
            layout.addLayout(cmd_layout)

        # Documentation URL link
        if remedy.article_url:
            doc_link = QLabel(
                f'<a href="{remedy.article_url}" style="color: #4FD1C5; text-decoration: none;">'
                + (
                    "📘 Nápověda a dokumentace k Mutagenu →"
                    if self._czech
                    else "📘 Mutagen Documentation →"
                )
                + "</a>",
                card,
            )
            doc_link.setOpenExternalLinks(True)
            doc_link.setStyleSheet("font-size: 12px; margin-top: 4px;")
            layout.addWidget(doc_link)

        self.content_layout.addWidget(card)

    def _copy_command(self, command: str, button: QPushButton) -> None:
        QApplication.clipboard().setText(command)
        orig_text = button.text()
        button.setText("Zkopírováno!" if self._czech else "Copied!")
        QTimer.singleShot(1800, lambda: button.setText(orig_text))

    def _generate_diagnostic_summary(self) -> str:
        selected_id = self.session_combo.currentData()
        session = next((s for s in self._sessions if s.identity.identifier == selected_id), None)
        if not session:
            return ""

        issues = self._issues_for_session(session.identity.identifier)
        lines = [
            f"MutaUI Session Diagnostics: {session.identity.name or session.identity.identifier}",
            f"State: {session.state}",
            f"Issues found: {len(issues)}",
            "-" * 40,
        ]
        for issue in issues:
            lines.append(f"[{issue.severity.upper()}] {issue.code}: {issue.explanation}")
            if issue.technical_detail:
                lines.append(f"Detail: {issue.technical_detail.strip()}")
            remedy = get_diagnostic_remedy(issue.code or "session_error", language="en")
            for idx, step in enumerate(remedy.remedy_steps, start=1):
                lines.append(f"  Step {idx}: {step}")
            if remedy.quick_command:
                lines.append(f"  Command: {remedy.quick_command}")
            lines.append("")

        return "\n".join(lines)

    def _copy_diagnostic_summary(self) -> None:
        summary = self._generate_diagnostic_summary()
        if not summary:
            return
        QApplication.clipboard().setText(summary)
        orig_text = self.copy_btn.text()
        self.copy_btn.setText("Zkopírováno!" if self._czech else "Copied!")
        QTimer.singleShot(1800, lambda: self.copy_btn.setText(orig_text))

    def _open_selected_settings(self) -> None:
        selected_id = self.session_combo.currentData()
        if selected_id and self._on_open_settings:
            self._on_open_settings(str(selected_id))

    def _refresh_status(self) -> None:
        if self._on_refresh:
            self._on_refresh()
            # Brief visual feedback on button
            orig_text = self.refresh_btn.text()
            self.refresh_btn.setText("Obnoveno!" if self._czech else "Refreshed!")
            QTimer.singleShot(1500, lambda: self.refresh_btn.setText(orig_text))
