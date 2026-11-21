"""Global configuration editor and settings page mixin for MainWindow."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QScrollArea

from mutaui.ui import global_config_editor, settings_migration
from mutaui.ui.settings_page import build_settings_page
from settings import settings_path


class GlobalConfigMixin:
    """Mixin managing settings page generation and global Mutagen YAML configuration."""

    def settings_page(self: Any) -> QScrollArea:
        return build_settings_page(self)

    def migrate_local_settings(self: Any) -> None:
        settings_migration.migrate_local_settings(self, settings_path())

    def rollback_local_settings_migration(self: Any) -> None:
        settings_migration.rollback_local_settings_migration(self, settings_path())

    def browse_global_config(self: Any) -> None:
        global_config_editor.browse_global_config(self)

    def load_global_config(self: Any) -> None:
        global_config_editor.load_global_config(self)

    def show_global_yaml_recovery(self: Any) -> None:
        global_config_editor.show_global_yaml_recovery(self)

    def preview_global_config(self: Any) -> None:
        global_config_editor.preview_global_config(self)
