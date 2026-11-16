from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from connection_profiles import ConnectionProfile
from ignore_presets import IgnorePreset, preview_preset_import
from mutaui.ui.dialog_components import add_localized_item, button, label
from mutaui.ui.localization import set_localized_accessible_name, set_localized_title
from portable_bundle import PREFERENCE_KEYS, BundleLoad, preview_profile_import


class PortableImportPreviewDialog(QDialog):
    """Dry-run choices for portable profiles and selected safe preferences."""

    def __init__(
        self,
        parent: QWidget | None,
        bundle: BundleLoad,
        existing_profiles: list[ConnectionProfile] | tuple[ConnectionProfile, ...],
        existing_ignores: list[IgnorePreset] | tuple[IgnorePreset, ...] = (),
    ) -> None:
        super().__init__(parent)
        self.bundle = bundle
        self.preview = preview_profile_import(bundle, existing_profiles)
        self.ignore_preview = preview_preset_import(
            bundle.data["items"]["ignore_presets"], existing_ignores
        )
        set_localized_title(self, "Review Portable Import")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(label("Import preview · no files changed yet", size=18, bold=True))
        layout.addWidget(
            label(
                "Choose create, merge, or skip for each profile. Application binary, session notes, and history stay local. Import never creates or edits Mutagen sessions.",
                muted=True,
            )
        )
        if bundle.warnings:
            warning = label("\n".join(bundle.warnings), muted=True)
            warning.setWordWrap(True)
            layout.addWidget(warning)
        self.table = QTableWidget(len(self.preview), 4)
        set_localized_accessible_name(self.table, "Portable profile preview table")
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Stable ID", "Action / reason"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, item in enumerate(self.preview):
            self.table.setItem(row, 0, QTableWidgetItem(item.profile.name))
            self.table.setItem(row, 1, QTableWidgetItem(item.profile.kind.title()))
            self.table.setItem(row, 2, QTableWidgetItem(item.profile.id))
            control = QComboBox()
            options = [("Create new", "create")]
            if item.action == "conflict":
                options.append(("Merge / replace same ID", "merge"))
            options.append(("Skip", "skip"))
            for title, value in options:
                control.addItem(title, value)
            default = control.findData(
                "skip" if item.action in {"skip", "conflict"} else item.action
            )
            control.setCurrentIndex(max(0, default))
            control.setToolTip(item.reason)
            self.table.setCellWidget(row, 3, control)
        layout.addWidget(self.table, 1)
        items = bundle.data["items"]
        prefs = items["preferences"]
        self.preference_checks: dict[str, QCheckBox] = {}
        if prefs:
            layout.addWidget(label("Select safe preferences to import", bold=True))
            for key in sorted(PREFERENCE_KEYS & set(prefs)):
                check = QCheckBox(f"{key}: {prefs[key]}")
                check.setChecked(True)
                self.preference_checks[key] = check
                layout.addWidget(check)
        if self.ignore_preview:
            layout.addWidget(label("Review portable ignore presets", bold=True))
            self.ignore_table = QTableWidget(len(self.ignore_preview), 3)
            set_localized_accessible_name(self.ignore_table, "Ignore preset preview table")
            self.ignore_table.setHorizontalHeaderLabels(
                ["Preset", "Ordered rules", "Action / reason"]
            )
            self.ignore_table.horizontalHeader().setStretchLastSection(True)
            for row, ignore_item in enumerate(self.ignore_preview):
                self.ignore_table.setItem(row, 0, QTableWidgetItem(ignore_item.preset.name))
                self.ignore_table.setItem(
                    row, 1, QTableWidgetItem(" · ".join(ignore_item.preset.patterns))
                )
                control = QComboBox()
                add_localized_item(control, "Create new", "create")
                if ignore_item.action == "conflict":
                    add_localized_item(control, "Replace same ID", "merge")
                add_localized_item(control, "Skip", "skip")
                control.setCurrentIndex(
                    max(
                        0,
                        control.findData(
                            "skip"
                            if ignore_item.action in {"skip", "conflict"}
                            else ignore_item.action
                        ),
                    )
                )
                control.setToolTip(ignore_item.reason)
                self.ignore_table.setCellWidget(row, 2, control)
            layout.addWidget(self.ignore_table, 1)
        if items["project_references"]:
            layout.addWidget(
                label(
                    f"Project references: {len(items['project_references'])} (not imported in this stage).",
                    muted=True,
                )
            )
        controls = QHBoxLayout()
        controls.addStretch(1)
        controls.addWidget(button("Cancel", self.reject))
        controls.addWidget(button("Apply selected…", self.accept, kind="primary"))
        layout.addLayout(controls)

    def profile_choices(self) -> dict[str, str]:
        choices = {}
        for row, item in enumerate(self.preview):
            control = self.table.cellWidget(row, 3)
            if isinstance(control, QComboBox):
                choices[item.profile.id] = control.currentData()
        return choices

    def selected_preferences(self) -> set[str]:
        return {key for key, check in self.preference_checks.items() if check.isChecked()}

    def ignore_choices(self) -> dict[str, str]:
        choices = {}
        for row, item in enumerate(self.ignore_preview):
            control = self.ignore_table.cellWidget(row, 2)
            if isinstance(control, QComboBox):
                choices[item.preset.id] = control.currentData()
        return choices
