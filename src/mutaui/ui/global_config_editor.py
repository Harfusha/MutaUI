from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from mutaui.adapters.yaml_config import load_yaml_file
from mutaui.adapters.yaml_config_editor import (
    ConcurrentConfigChange,
    InvalidConfigForWrite,
    apply_yaml_edit,
    preview_yaml_text,
)
from mutaui.ui.localization import (
    set_localized_text,
    set_localized_title,
)
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.widgets.basic import label


def browse_global_config(window: Any) -> None:
    path, _ = QFileDialog.getOpenFileName(
        window,
        translate_text("Select Mutagen global YAML", active_language()),
        str(Path.home()),
        translate_text("YAML files (*.yml *.yaml);;All files (*)", active_language()),
    )
    if path:
        window.global_config_path_input.setText(path)


def load_global_config(window: Any) -> None:
    path = window.global_config_path_input.text().strip()
    if not path:
        QMessageBox.information(
            window,
            translate_text("Global Mutagen YAML", active_language()),
            translate_text("Choose the config file first.", active_language()),
        )
        return
    snapshot = load_yaml_file(path)
    window._global_config_snapshot = snapshot
    window.global_config_editor.setPlainText(snapshot.text or "")
    window.global_config_editor.setReadOnly(not snapshot.valid)
    window.global_yaml_recovery_button.setEnabled(not snapshot.valid)
    if snapshot.valid:
        window.global_config_status.setText(
            translate_text(
                "Loaded {path} · SHA-256 {sha256} · source retained for collision checks.",
                active_language(),
            ).format(path=path, sha256=snapshot.sha256)
        )
    else:
        window.global_config_status.setText(
            translate_text("Invalid source retained unchanged: {error}", active_language()).format(
                error=snapshot.error
            )
        )
        QMessageBox.warning(
            window,
            translate_text("Invalid Mutagen YAML", active_language()),
            translate_text(
                "The file stays unchanged. Open read-only recovery to copy its source, repair it outside MutaUI, then load it again.",
                active_language(),
            ),
        )


def show_global_yaml_recovery(window: Any) -> None:
    snapshot = getattr(window, "_global_config_snapshot", None)
    if snapshot is None or snapshot.valid:
        return
    dialog = QDialog(window)
    set_localized_title(dialog, "Global YAML recovery")
    layout = QVBoxLayout(dialog)
    explanation = label(
        "This source is read-only. Copy it, repair it in an external editor, then load it again.",
        muted=True,
    )
    explanation.setWordWrap(True)
    layout.addWidget(explanation)
    details = label(
        translate_text("Source path: {path}\\nParse error: {error}", active_language()).format(
            path=snapshot.source_path or "",
            error=snapshot.error or "Unknown parse error",
        ),
        muted=True,
        size=11,
    )
    details.setWordWrap(True)
    layout.addWidget(details)
    raw_source = QPlainTextEdit(dialog)
    raw_source.setObjectName("globalYamlRecoverySource")
    raw_source.setPlainText(snapshot.text or "")
    raw_source.setReadOnly(True)
    raw_source.setAccessibleName(translate_text("Raw Mutagen YAML source", active_language()))
    layout.addWidget(raw_source, 1)
    actions = QHBoxLayout()
    copy_button = QPushButton(translate_text("Copy raw YAML", active_language()), dialog)
    copy_button.setObjectName("copyGlobalYamlRecovery")
    copy_button.setAccessibleName(translate_text("Copy raw YAML", active_language()))
    copy_button.clicked.connect(lambda: QApplication.clipboard().setText(snapshot.text or ""))
    actions.addWidget(copy_button)
    close_button = QPushButton(translate_text("Close", active_language()), dialog)
    close_button.clicked.connect(dialog.accept)
    actions.addWidget(close_button)
    layout.addLayout(actions)
    dialog.resize(720, 520)
    dialog.exec()


def preview_global_config(window: Any) -> None:
    snapshot = getattr(window, "_global_config_snapshot", None)
    if snapshot is None:
        QMessageBox.information(
            window,
            translate_text("Global Mutagen YAML", active_language()),
            translate_text("Load a config file first.", active_language()),
        )
        return
    try:
        preview = preview_yaml_text(snapshot, window.global_config_editor.toPlainText())
    except InvalidConfigForWrite as exc:
        QMessageBox.warning(
            window, translate_text("Invalid Mutagen YAML", active_language()), str(exc)
        )
        return
    confirm = QMessageBox(window)
    set_localized_title(confirm, "Review Mutagen YAML changes")
    confirm.setIcon(QMessageBox.Icon.Question)
    set_localized_text(
        confirm, "Review this diff. Save creates a backup and atomically replaces the file."
    )
    confirm.setDetailedText(preview.diff or "No changes.")
    apply_button = confirm.addButton(
        translate_text("Save reviewed changes", active_language()),
        QMessageBox.ButtonRole.AcceptRole,
    )
    confirm.addButton(
        translate_text("Cancel", active_language()), QMessageBox.ButtonRole.RejectRole
    )
    confirm.exec()
    if confirm.clickedButton() is not apply_button:
        return
    try:
        result = apply_yaml_edit(preview)
    except ConcurrentConfigChange as collision:
        choice = QMessageBox(window)
        set_localized_title(choice, "Mutagen config changed")
        choice.setIcon(QMessageBox.Icon.Warning)
        set_localized_text(choice, "Another tool changed this file. Choose how to continue.")
        choice.setDetailedText(
            collision.latest.error or collision.latest.text or "Latest source unavailable."
        )
        reload_button = choice.addButton(
            translate_text("Reload external changes", active_language()),
            QMessageBox.ButtonRole.AcceptRole,
        )
        merge_button = choice.addButton(
            translate_text("Keep draft and merge manually", active_language()),
            QMessageBox.ButtonRole.ActionRole,
        )
        choice.addButton(
            translate_text("Cancel", active_language()), QMessageBox.ButtonRole.RejectRole
        )
        choice.exec()
        if choice.clickedButton() is reload_button:
            window.load_global_config()
        elif choice.clickedButton() is merge_button and collision.latest.valid:
            window._global_config_snapshot = collision.latest
            set_localized_text(
                window.global_config_status,
                "External version loaded as the new baseline. Draft retained; merge manually, review the new diff, then save.",
            )
        return
    except (OSError, InvalidConfigForWrite) as exc:
        QMessageBox.warning(
            window, translate_text("Could not save Mutagen config", active_language()), str(exc)
        )
        return
    window._global_config_snapshot = load_yaml_file(result.path)
    window.global_config_editor.setPlainText(window._global_config_snapshot.text or "")
    window.global_config_status.setText(
        translate_text(
            "Saved safely. Backup: {backup} · new SHA-256 {sha256}", active_language()
        ).format(backup=result.backup_path, sha256=result.new_sha256)
    )
