from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QMessageBox

from mutaui.ui.preferences import active_language, translate_text
from settings import migrate_settings_file, rollback_settings_migration


def migrate_local_settings(window: Any, path: str | Path) -> None:
    try:
        result = migrate_settings_file(path)
    except OSError as exc:
        QMessageBox.warning(
            window, translate_text("Settings Migration", active_language()), str(exc)
        )
        return
    detail = translate_text(result.message, active_language())
    if result.backup_path:
        detail += "\n\n" + translate_text("Exact backup: {path}", active_language()).format(
            path=result.backup_path
        )
    QMessageBox.information(window, translate_text("Settings Migration", active_language()), detail)


def rollback_local_settings_migration(window: Any, path: str | Path) -> None:
    backup, _ = QFileDialog.getOpenFileName(
        window,
        translate_text("Select pre-migration settings backup", active_language()),
        str(Path(path).parent),
        translate_text("Migration backups (*.pre-migration.*.bak)", active_language()),
    )
    if not backup:
        return
    answer = QMessageBox.question(
        window,
        translate_text("Rollback Settings Migration", active_language()),
        translate_text(
            "Restore the exact settings bytes from this backup? A backup of current settings will also be kept.\n\n{backup}",
            active_language(),
        ).format(backup=backup),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return
    try:
        target = rollback_settings_migration(path, backup)
    except OSError as exc:
        QMessageBox.warning(
            window, translate_text("Settings Rollback", active_language()), str(exc)
        )
        return
    QMessageBox.information(
        window,
        translate_text("Settings Rollback", active_language()),
        translate_text("Exact migration backup restored: {path}", active_language()).format(
            path=target
        ),
    )
