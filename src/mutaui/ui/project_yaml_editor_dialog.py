"""Consent-gated native project YAML editor with an explicit diff preview."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mutaui.projects.native_project import NativeProjectSnapshot
from mutaui.projects.project_editor import (
    ProjectEditError,
    ProjectEditPreview,
    ProjectEditReceipt,
    apply_project_yaml_edit,
    preview_project_yaml_edit,
)


class ProjectYamlEditorDialog(QDialog):
    def __init__(
        self,
        snapshot: NativeProjectSnapshot,
        audit_path: str | Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.snapshot = snapshot
        self.audit_path = Path(audit_path)
        self.preview: ProjectEditPreview | None = None
        self.receipt: ProjectEditReceipt | None = None
        self.setWindowTitle("Edit Native Mutagen Project")
        self.resize(920, 700)
        layout = QVBoxLayout(self)
        warning = QLabel(
            "Edits this project file in place with a backup. Project-owned sessions stay "
            "owned by mutagen.yml; this does not recreate detached sessions or run hooks."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.editor = QPlainTextEdit(snapshot.raw_text or "")
        self.editor.setTabStopDistance(28)
        self.editor.setPlaceholderText("Native Mutagen project YAML")
        layout.addWidget(self.editor, 1)
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.diff.setPlaceholderText("Stage a valid edit to review the exact YAML diff.")
        layout.addWidget(self.diff, 1)
        controls = QVBoxLayout()
        self.stage_button = QPushButton("Validate and preview diff")
        self.consent = QCheckBox(
            "I reviewed this diff and authorize changing this exact mutagen.yml."
        )
        self.apply_button = QPushButton("Apply with backup")
        self.apply_button.setEnabled(False)
        controls.addWidget(self.stage_button)
        controls.addWidget(self.consent)
        controls.addWidget(self.apply_button)
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.stage_button.clicked.connect(self.stage_edit)
        self.consent.toggled.connect(self._update_apply_enabled)
        self.apply_button.clicked.connect(self.apply_edit)

    def _update_apply_enabled(self, checked: bool) -> None:
        self.apply_button.setEnabled(checked and self.preview is not None)

    def stage_edit(self) -> None:
        self.consent.setChecked(False)
        try:
            self.preview = preview_project_yaml_edit(self.snapshot, self.editor.toPlainText())
        except ProjectEditError as exc:
            self.preview = None
            self.diff.clear()
            self._update_apply_enabled(False)
            QMessageBox.warning(self, "Native Mutagen Project", str(exc))
            return
        self.diff.setPlainText(self.preview.yaml_preview.diff or "No changes.")
        self._update_apply_enabled(False)

    def apply_edit(self) -> None:
        if self.preview is None or not self.consent.isChecked():
            return
        answer = QMessageBox.question(
            self,
            "Apply project configuration",
            "Write this reviewed diff to the exact project file and keep a backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.receipt = apply_project_yaml_edit(
                self.preview, consent=True, audit_path=self.audit_path
            )
        except (ProjectEditError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Native Mutagen Project", str(exc))
            return
        suffix = (
            " Audit completion could not be recorded." if not self.receipt.audit_complete else ""
        )
        QMessageBox.information(
            self,
            "Native Mutagen Project",
            f"Project YAML saved. Backup: {self.receipt.write.backup_path}.{suffix}\n"
            "Use the separate project action preview to apply project-owned changes.",
        )
        self.accept()
