"""Operator-managed exact-path conflict advice; no file-resolution actions."""

from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mutaui.services.conflict_recommendations import (
    ConflictChoiceRule,
    ConflictRecommendationPolicy,
    RecommendationPolicyError,
)
from mutaui.ui.preferences import active_language, translate_text


def _text(source: str) -> str:
    return translate_text(source, active_language())


class ConflictRecommendationsDialog(QDialog):
    """Edit bounded advisory rules. Accepting never resolves a conflict."""

    def __init__(self, policy: ConflictRecommendationPolicy, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_text("Conflict advice rules"))
        self.resize(760, 520)
        self._rules = list(policy.rules)
        self._accepted_policy = policy

        layout = QVBoxLayout(self)
        warning = QLabel(
            _text(
                "Advice is informational. It never changes files or session settings. "
                "Review both copies and make any choice yourself."
            )
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self.enabled_checkbox = QCheckBox(_text("Show exact-path advice"))
        self.enabled_checkbox.setAccessibleName(_text("Show exact-path advice"))
        self.enabled_checkbox.setToolTip(
            _text("Recommendations remain advisory and require your manual review.")
        )
        self.enabled_checkbox.setChecked(policy.enabled)
        layout.addWidget(self.enabled_checkbox)

        self.rules_table = QTableWidget(0, 3)
        self.rules_table.setAccessibleName(_text("Conflict advice rules"))
        self.rules_table.setHorizontalHeaderLabels(
            tuple(_text(value) for value in ("Exact path", "Preferred side", "Reason"))
        )
        self.rules_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.rules_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rules_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.rules_table, 1)

        form = QFormLayout()
        self.path_input = QLineEdit()
        self.path_input.setObjectName("recommendationExactPath")
        self.path_input.setPlaceholderText(_text("e.g. database/state.db"))
        self.path_input.setAccessibleName(_text("Exact conflict-relative path"))
        form.addRow(_text("Exact conflict-relative path"), self.path_input)

        self.side_input = QComboBox()
        self.side_input.setObjectName("recommendationPreferredSide")
        self.side_input.addItem(_text("ALPHA"), "alpha")
        self.side_input.addItem(_text("BETA"), "beta")
        self.side_input.setAccessibleName(_text("Preferred side"))
        form.addRow(_text("Preferred side"), self.side_input)

        self.reason_input = QLineEdit()
        self.reason_input.setObjectName("recommendationReason")
        self.reason_input.setPlaceholderText(_text("Why should this side be preferred?"))
        self.reason_input.setAccessibleName(_text("Reason"))
        form.addRow(_text("Reason"), self.reason_input)
        layout.addLayout(form)

        rule_buttons = QHBoxLayout()
        self.add_button = QPushButton(_text("Add rule"))
        self.remove_button = QPushButton(_text("Remove selected rule"))
        self.add_button.clicked.connect(self._add_rule)
        self.remove_button.clicked.connect(self._remove_rule)
        rule_buttons.addWidget(self.add_button)
        rule_buttons.addWidget(self.remove_button)
        rule_buttons.addStretch()
        layout.addLayout(rule_buttons)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(_text("Save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_text("Cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._refresh_table()

    @property
    def policy(self) -> ConflictRecommendationPolicy:
        return self._accepted_policy

    def _candidate_policy(self) -> ConflictRecommendationPolicy:
        return ConflictRecommendationPolicy(
            tuple(self._rules), enabled=self.enabled_checkbox.isChecked()
        )

    def _add_rule(self) -> None:
        rule = ConflictChoiceRule(
            f"rule-{uuid.uuid4().hex[:12]}",
            self.path_input.text().strip(),
            self.side_input.currentData(),
            self.reason_input.text().strip(),
        )
        try:
            candidate = ConflictRecommendationPolicy(
                (*self._rules, rule), enabled=self.enabled_checkbox.isChecked()
            )
        except RecommendationPolicyError as exc:
            QMessageBox.warning(self, _text("Invalid rule"), str(exc))
            return
        self._rules = list(candidate.rules)
        self._refresh_table()
        self.path_input.clear()
        self.reason_input.clear()

    def _remove_rule(self) -> None:
        row = self.rules_table.currentRow()
        if 0 <= row < len(self._rules):
            self._rules.pop(row)
            self._refresh_table()

    def _refresh_table(self) -> None:
        self.rules_table.setRowCount(len(self._rules))
        for row, rule in enumerate(self._rules):
            values = (
                rule.exact_relative_path,
                _text(rule.preferred_side.upper()),
                rule.explanation,
            )
            for column, value in enumerate(values):
                self.rules_table.setItem(row, column, QTableWidgetItem(value))

    def accept(self) -> None:
        try:
            self._accepted_policy = self._candidate_policy()
        except RecommendationPolicyError as exc:
            QMessageBox.warning(self, _text("Invalid rule"), str(exc))
            return
        super().accept()
