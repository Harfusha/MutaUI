"""Small dialogs for managing local ignore presets and staged imports."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ignore_presets import (
    IgnoreConversionPreview,
    IgnorePresetError,
    IgnorePresetStore,
    apply_converted_rules,
)


class IgnorePresetManagerDialog(QDialog):
    def __init__(self, path: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = IgnorePresetStore(path)
        self.setWindowTitle("Ignore Presets")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Presets are local to this computer. Rule order is preserved."))
        content = QHBoxLayout()
        self.presets = QListWidget()
        self.presets.addItems([item.name for item in self.store.presets])
        self.presets.currentRowChanged.connect(self._select)
        content.addWidget(self.presets, 1)
        form = QFormLayout()
        self.name = QLineEdit()
        self.description = QLineEdit()
        self.patterns = QPlainTextEdit()
        self.patterns.setPlaceholderText("One Mutagen ignore pattern per line")
        form.addRow("Name", self.name)
        form.addRow("Description", self.description)
        form.addRow("Ordered rules", self.patterns)
        content.addLayout(form, 2)
        layout.addLayout(content)
        controls = QHBoxLayout()
        self.new_button = QPushButton("New")
        self.save_button = QPushButton("Save as new")
        self.update_button = QPushButton("Update selected")
        self.delete_button = QPushButton("Delete selected")
        for widget in (self.new_button, self.save_button, self.update_button, self.delete_button):
            controls.addWidget(widget)
        layout.addLayout(controls)
        self.new_button.clicked.connect(self._new)
        self.save_button.clicked.connect(self._create)
        self.update_button.clicked.connect(self._update)
        self.delete_button.clicked.connect(self._delete)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self.store.presets:
            self.presets.setCurrentRow(0)

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.store.presets):
            return
        preset = self.store.presets[row]
        self.name.setText(preset.name)
        self.description.setText(preset.description)
        self.patterns.setPlainText("\n".join(preset.patterns))

    def _new(self) -> None:
        self.presets.clearSelection()
        self.name.clear()
        self.description.clear()
        self.patterns.clear()

    def _values(self) -> tuple[str, str, tuple[str, ...]]:
        return (
            self.name.text(),
            self.description.text(),
            tuple(line for line in self.patterns.toPlainText().splitlines() if line),
        )

    def _report_error(self, error: Exception) -> None:
        QMessageBox.warning(self, "Ignore Presets", str(error))

    def _create(self) -> None:
        try:
            name, description, patterns = self._values()
            self.store.create(name, patterns, description)
            self._refresh()
        except (IgnorePresetError, OSError) as exc:
            self._report_error(exc)

    def _update(self) -> None:
        row = self.presets.currentRow()
        if not 0 <= row < len(self.store.presets):
            return
        try:
            name, description, patterns = self._values()
            self.store.update(
                self.store.presets[row].id, name=name, patterns=patterns, description=description
            )
            self._refresh(row)
        except (IgnorePresetError, OSError) as exc:
            self._report_error(exc)

    def _delete(self) -> None:
        row = self.presets.currentRow()
        if not 0 <= row < len(self.store.presets):
            return
        if (
            QMessageBox.question(self, "Delete Ignore Preset", "Delete this preset?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.store.delete(self.store.presets[row].id)
            self._refresh(min(row, len(self.store.presets) - 1))
        except (IgnorePresetError, OSError) as exc:
            self._report_error(exc)

    def _refresh(self, selected: int = -1) -> None:
        self.presets.clear()
        self.presets.addItems([item.name for item in self.store.presets])
        if selected >= 0:
            self.presets.setCurrentRow(selected)


class IgnoreConversionDialog(QDialog):
    def __init__(self, preview: IgnoreConversionPreview, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle(f"Convert .{preview.source_format} rules")
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Review each source line. Unsupported rows stay unchecked and cannot be applied. "
            "Conversion only changes the new session draft; it never edits source files or deletes files."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(len(preview.rules), 4)
        self.table.setHorizontalHeaderLabels(["Use", "Line", "Source rule", "Conversion note"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, rule in enumerate(preview.rules):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if rule.supported else Qt.CheckState.Unchecked
            )
            if not rule.supported:
                check.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(str(rule.line)))
            self.table.setItem(row, 2, QTableWidgetItem(rule.raw))
            self.table.setItem(row, 3, QTableWidgetItem(rule.reason))
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.warnings = preview.warnings
        if preview.warnings:
            warning = QLabel("\n".join(preview.warnings))
            warning.setWordWrap(True)
            layout.addWidget(warning)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_patterns(self) -> tuple[str, ...]:
        selected: set[int] = set()
        for row, rule in enumerate(self.preview.rules):
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                selected.add(rule.line)
        return cast(tuple[str, ...], apply_converted_rules(self.preview, selected))


__all__ = ["IgnoreConversionDialog", "IgnorePresetManagerDialog"]
