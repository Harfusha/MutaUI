from __future__ import annotations

import json
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from connection_profiles import (
    ConnectionProfile,
    ConnectionProfileStore,
    ProfileStoreError,
    duplicate_profile,
)
from mutaui.ui.localization import (
    set_localized_accessible_name,
    set_localized_placeholder,
    set_localized_title,
)
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.widgets.basic import (
    add_localized_item,
    add_localized_row,
    button,
    label,
    localized_checkbox,
)


class ConnectionProfilesDialog(QDialog):
    """Manage versioned local connection profiles without touching Mutagen sessions."""

    def __init__(self, parent: QWidget | None, store: ConnectionProfileStore) -> None:
        super().__init__(parent)
        self.store = store
        set_localized_title(self, "Connection Profiles")
        self.resize(920, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Saved local connection profiles", size=18, bold=True))
        filters = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setClearButtonEnabled(True)
        set_localized_placeholder(self.search_input, "Search name or tag")
        self.kind_filter = QComboBox()
        add_localized_item(self.kind_filter, "All types", None)
        add_localized_item(self.kind_filter, "Sync", "sync")
        add_localized_item(self.kind_filter, "Forward", "forward")
        self.favorites_only = localized_checkbox("Favorites only")
        filters.addWidget(self.search_input, 1)
        filters.addWidget(self.kind_filter)
        filters.addWidget(self.favorites_only)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 6)
        set_localized_accessible_name(self.table, "Connection profiles table")
        self.table.setHorizontalHeaderLabels(
            ["Name", "Type", "Endpoint A / Source", "Endpoint B / Destination", "Tags", "Favorite"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout()
        controls.addWidget(button("New…", self.new_profile, kind="primary"))
        controls.addWidget(button("Edit…", self.edit_selected))
        controls.addWidget(button("Duplicate", self.duplicate_selected))
        controls.addWidget(button("Favorite", self.toggle_favorite))
        controls.addWidget(button("Delete…", self.delete_selected, kind="danger"))
        controls.addStretch(1)
        controls.addWidget(button("Done", self.accept))
        layout.addLayout(controls)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.edit_selected())
        self.search_input.textChanged.connect(self.refresh)
        self.kind_filter.currentIndexChanged.connect(self.refresh)
        self.favorites_only.stateChanged.connect(lambda _state: self.refresh())
        self.refresh()

    def selected_profile(self) -> ConnectionProfile | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        profile = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return profile if isinstance(profile, ConnectionProfile) else None

    def refresh(self, *_args: object) -> None:
        kind = self.kind_filter.currentData()
        profiles = self.store.search(
            self.search_input.text(),
            kind=kind,
            favorites_only=self.favorites_only.isChecked(),
        )
        selected = self.selected_profile()
        selected_id = selected.id if selected else None
        self.table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            values = (
                profile.name,
                profile.kind.title(),
                profile.endpoint_a,
                profile.endpoint_b,
                ", ".join(profile.tags),
                "★" if profile.favorite else "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, profile)
                self.table.setItem(row, column, item)
            if profile.id == selected_id:
                self.table.selectRow(row)

    def new_profile(self) -> None:
        dialog = QDialog(self)
        set_localized_title(dialog, "New Connection Profile")
        form = QFormLayout(dialog)
        name = QLineEdit()
        kind = QComboBox()
        add_localized_item(kind, "Sync", "sync")
        add_localized_item(kind, "Forward", "forward")
        endpoint_a = QLineEdit()
        endpoint_b = QLineEdit()
        tags = QLineEdit()
        favorite = localized_checkbox("Favorite")
        defaults = QPlainTextEdit("{}")
        defaults.setMaximumHeight(100)
        add_localized_row(form, "Name", name)
        add_localized_row(form, "Type", kind)
        add_localized_row(form, "Endpoint A / Source", endpoint_a)
        add_localized_row(form, "Endpoint B / Destination", endpoint_b)
        add_localized_row(form, "Tags (comma-separated)", tags)
        add_localized_row(form, "Default settings (JSON)", defaults)
        form.addRow("", favorite)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            raw_defaults = json.loads(defaults.toPlainText())
            if not isinstance(raw_defaults, dict):
                raise ValueError("Default settings must be a JSON object.")
            profile = self.store.create(
                name.text(),
                endpoint_a.text(),
                endpoint_b.text(),
                kind=kind.currentData(),
                tags=tuple(tag.strip() for tag in tags.text().split(",") if tag.strip()),
                favorite=favorite.isChecked(),
                defaults=raw_defaults,
            )
        except (ProfileStoreError, json.JSONDecodeError, ValueError, OSError) as exc:
            QMessageBox.warning(
                self, translate_text("Invalid Profile", active_language()), str(exc)
            )
            return
        self.refresh()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole).id == profile.id:
                self.table.selectRow(row)
                break

    def edit_selected(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            QMessageBox.warning(
                self,
                translate_text("No Selection", active_language()),
                translate_text("Please select a profile to edit.", active_language()),
            )
            return
        dialog = QDialog(self)
        set_localized_title(dialog, "Edit Connection Profile")
        form = QFormLayout(dialog)
        name = QLineEdit(profile.name)
        kind = QComboBox()
        add_localized_item(kind, "Sync", "sync")
        add_localized_item(kind, "Forward", "forward")
        kind.setCurrentIndex(max(0, kind.findData(profile.kind)))
        endpoint_a = QLineEdit(profile.endpoint_a)
        endpoint_b = QLineEdit(profile.endpoint_b)
        tags = QLineEdit(", ".join(profile.tags))
        favorite = localized_checkbox("Favorite")
        favorite.setChecked(profile.favorite)
        defaults = QPlainTextEdit(json.dumps(dict(profile.defaults), indent=2))
        defaults.setMaximumHeight(100)
        add_localized_row(form, "Name", name)
        add_localized_row(form, "Type", kind)
        add_localized_row(form, "Endpoint A / Source", endpoint_a)
        add_localized_row(form, "Endpoint B / Destination", endpoint_b)
        add_localized_row(form, "Tags (comma-separated)", tags)
        add_localized_row(form, "Default settings (JSON)", defaults)
        form.addRow("", favorite)
        note = label(
            "Editing a profile updates future session creation only. Existing active sessions remain unaffected.",
            muted=True,
            size=11,
        )
        form.addRow(note)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            raw_defaults = json.loads(defaults.toPlainText())
            if not isinstance(raw_defaults, dict):
                raise ValueError("Default settings must be a JSON object.")
            updated_profile = replace(
                profile,
                name=name.text().strip(),
                kind=kind.currentData(),
                endpoint_a=endpoint_a.text().strip(),
                endpoint_b=endpoint_b.text().strip(),
                tags=tuple(tag.strip() for tag in tags.text().split(",") if tag.strip()),
                favorite=favorite.isChecked(),
                defaults=raw_defaults,
            )
            self.store.update(updated_profile)
        except (ProfileStoreError, json.JSONDecodeError, ValueError, OSError) as exc:
            QMessageBox.warning(
                self, translate_text("Invalid Profile", active_language()), str(exc)
            )
            return
        self.refresh()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole).id == profile.id:
                self.table.selectRow(row)
                break

    def duplicate_selected(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            return
        duplicate = duplicate_profile(profile)
        try:
            self.store.add(duplicate)
        except (ProfileStoreError, OSError) as exc:
            QMessageBox.warning(
                self, translate_text("Could not duplicate profile", active_language()), str(exc)
            )
            return
        self.refresh()

    def toggle_favorite(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            return
        try:
            self.store.update(replace(profile, favorite=not profile.favorite))
        except (ProfileStoreError, OSError) as exc:
            QMessageBox.warning(
                self, translate_text("Could not update profile", active_language()), str(exc)
            )
            return
        self.refresh()

    def delete_selected(self) -> None:
        profile = self.selected_profile()
        if profile is None:
            return
        result = QMessageBox.question(
            self,
            translate_text("Delete Profile", active_language()),
            f"Delete local profile '{profile.name}'? This does not affect any Mutagen session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(profile.id)
        except (ProfileStoreError, OSError, KeyError) as exc:
            QMessageBox.warning(
                self, translate_text("Could not delete profile", active_language()), str(exc)
            )
        self.refresh()
