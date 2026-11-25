"""Main settings page construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mutaui.ui.localization import set_localized_placeholder
from mutaui.ui.preferences import translate
from mutaui.ui.settings_registry import setting_tooltip
from mutaui.ui.widgets.basic import add_localized_row, button, card, label, localized_checkbox
from sync_profiles import PROFILES


def build_settings_page(window: Any) -> QScrollArea:
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setFrameShape(QFrame.Shape.NoFrame)
    root = QWidget()
    root.setObjectName("scrollbody")
    layout = QVBoxLayout(root)
    layout.setContentsMargins(0, 3, 8, 14)
    layout.setSpacing(17)
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    appearance, al = card()
    al.addWidget(label("Display and Language", size=16, bold=True))
    appearance_form = QFormLayout()
    appearance_form.setVerticalSpacing(14)
    window.theme_input = QComboBox()
    window.theme_input.setToolTip(setting_tooltip("theme", window.ui_language))
    for theme in ("system", "light", "dark"):
        window.theme_input.addItem(translate(f"appearance.{theme}", window.ui_language), theme)
    window.theme_input.setCurrentIndex(
        max(0, window.theme_input.findData(window.conf.get("theme", "system")))
    )
    window.theme_input.currentIndexChanged.connect(
        lambda _index: window.apply_theme(window.theme_input.currentData())
    )
    appearance_form.addRow(translate("appearance.theme", window.ui_language), window.theme_input)
    window.language_input = QComboBox()
    window.language_input.setToolTip(setting_tooltip("language", window.ui_language))
    for language, key in (("en", "appearance.english"), ("cs", "appearance.czech")):
        window.language_input.addItem(translate(key, window.ui_language), language)
    window.language_input.setCurrentIndex(
        max(0, window.language_input.findData(window.ui_language))
    )
    window.language_input.currentIndexChanged.connect(
        lambda _index: window.apply_ui_language(window.language_input.currentData())
    )
    appearance_form.addRow(
        translate("appearance.language", window.ui_language), window.language_input
    )
    al.addLayout(appearance_form)
    al.addWidget(
        label(
            "Mode changes are temporary. Theme and language are saved with application settings.",
            muted=True,
            size=11,
        )
    )
    layout.addWidget(appearance)
    pathcard, pl = card()
    import sys

    placeholder_path = (
        "C:\\Program Files\\Mutagen\\mutagen.exe   (or blank = PATH)"
        if sys.platform == "win32"
        else "/usr/local/bin/mutagen   (or blank = PATH)"
    )
    pl.addWidget(label("Mutagen CLI Location", size=16, bold=True))
    pl.addWidget(
        label(
            "The application communicates with the Mutagen CLI. If it is not on the system PATH, select it manually.",
            muted=True,
        )
    )
    r = QHBoxLayout()
    window.binary_edit = QLineEdit(window.conf.get("binary", ""))
    window.binary_edit.setToolTip(setting_tooltip("binary", window.ui_language))
    set_localized_placeholder(window.binary_edit, placeholder_path)
    r.addWidget(window.binary_edit, 1)
    r.addWidget(button("Select…", window.browse_binary))
    pl.addLayout(r)
    window.version_label = label(window._version_label_text, muted=True)
    pl.addWidget(window.version_label)
    layout.addWidget(pathcard)
    prefs, pr = card()
    pr.addWidget(label("Application Behavior", size=16, bold=True))
    form = QFormLayout()
    form.setVerticalSpacing(18)
    window.interval_input = QSpinBox()
    window.interval_input.setRange(2, 30)
    window.interval_input.setSuffix(" s")
    window.interval_input.setMinimumWidth(160)
    window.interval_input.setValue(max(2, min(30, int(window.conf.get("interval", 4)))))
    window.interval_input.setToolTip(setting_tooltip("interval", window.ui_language))
    add_localized_row(form, "Session Refresh", window.interval_input)
    window.metric_interval_input = QComboBox()
    for seconds in (1, 2, 3, 5, 10):
        window.metric_interval_input.addItem(f"{seconds} s", seconds)
    saved = int(window.conf.get("metric_interval", 2))
    window.metric_interval_input.setCurrentIndex(
        max(0, window.metric_interval_input.findData(saved))
    )
    window.metric_interval_input.setMinimumWidth(160)
    window.metric_interval_input.setToolTip(setting_tooltip("metric_interval", window.ui_language))
    add_localized_row(form, "CPU/RAM Sampling", window.metric_interval_input)
    window.adaptive_input = localized_checkbox("Enable adaptive polling")
    window.adaptive_input.setChecked(bool(window.conf.get("adaptive_poll", True)))
    window.adaptive_input.setToolTip(setting_tooltip("adaptive_poll", window.ui_language))
    add_localized_row(form, "Adaptive Status Polling", window.adaptive_input)
    window.fast_interval_input = QSpinBox()
    window.fast_interval_input.setRange(2, 15)
    window.fast_interval_input.setValue(int(window.conf.get("adaptive_fast", 2)))
    window.fast_interval_input.setSuffix(" s")
    window.fast_interval_input.setMinimumWidth(160)
    window.fast_interval_input.setToolTip(setting_tooltip("adaptive_fast", window.ui_language))
    add_localized_row(form, "During Activity", window.fast_interval_input)
    window.idle_interval_input = QSpinBox()
    window.idle_interval_input.setRange(5, 180)
    window.idle_interval_input.setValue(int(window.conf.get("adaptive_idle", 30)))
    window.idle_interval_input.setSuffix(" s")
    window.idle_interval_input.setMinimumWidth(160)
    window.idle_interval_input.setToolTip(setting_tooltip("adaptive_idle", window.ui_language))
    add_localized_row(form, "When Idle", window.idle_interval_input)
    window.quiet_after_input = QSpinBox()
    window.quiet_after_input.setRange(15, 900)
    window.quiet_after_input.setValue(int(window.conf.get("adaptive_quiet", 90)))
    window.quiet_after_input.setSuffix(" s")
    window.quiet_after_input.setMinimumWidth(160)
    window.quiet_after_input.setToolTip(setting_tooltip("adaptive_quiet", window.ui_language))
    add_localized_row(form, "Idle After", window.quiet_after_input)
    window.new_sync_profile_input = QComboBox()
    for code, (title, _) in PROFILES.items():
        window.new_sync_profile_input.addItem(title, code)
    window.new_sync_profile_input.setCurrentIndex(
        max(
            0,
            window.new_sync_profile_input.findData(window.conf.get("new_sync_profile", "default")),
        )
    )
    window.new_sync_profile_input.setMinimumWidth(290)
    window.new_sync_profile_input.setToolTip(
        setting_tooltip("new_sync_profile", window.ui_language)
    )
    add_localized_row(form, "New Sync Sessions", window.new_sync_profile_input)
    window.eco_tray_input = localized_checkbox("Enable power-saving mode")
    window.eco_tray_input.setChecked(window.conf.get("eco_tray", True))
    window.eco_tray_input.setToolTip(setting_tooltip("eco_tray", window.ui_language))
    add_localized_row(form, "Power Saving Mode", window.eco_tray_input)
    window.tray_input = localized_checkbox("Minimize on close")
    window.tray_input.setChecked(window.conf.get("tray", True))
    window.tray_input.setToolTip(setting_tooltip("tray", window.ui_language))
    add_localized_row(form, "Notification Area", window.tray_input)
    window.alert_input = localized_checkbox("Notify on new issues")
    window.alert_input.setChecked(window.conf.get("alerts", True))
    window.alert_input.setToolTip(setting_tooltip("alerts", window.ui_language))
    add_localized_row(form, "Notifications", window.alert_input)
    pr.addLayout(form)
    explanation = label(
        "Adaptive mode changes only how often the UI polls status. Mutagen watches for file changes itself. "
        "Profiles for new sessions configure native watch/polling settings at creation. "
        "This does not change existing sessions' internal configuration or limit transfer speed.",
        muted=True,
        size=11,
    )
    explanation.setWordWrap(True)
    pr.addWidget(explanation)
    pr.addWidget(button("Save Settings", window.save_settings, kind="primary"))
    layout.addWidget(prefs)
    global_config, global_layout = card()
    global_layout.addWidget(label("Global Mutagen YAML", size=16, bold=True))
    global_layout.addWidget(
        label(
            "Edit Mutagen defaults for newly created sessions. Existing sessions keep their creation-time configuration.",
            muted=True,
        )
    )
    config_path_row = QHBoxLayout()
    window.global_config_path_input = QLineEdit()
    window.global_config_path_input.setText(str(Path.home() / ".mutagen.yml"))
    window.global_config_path_input.setReadOnly(True)
    set_localized_placeholder(
        window.global_config_path_input, "Select the Mutagen global YAML file"
    )
    config_path_row.addWidget(window.global_config_path_input, 1)
    config_path_row.addWidget(button("Choose file…", window.browse_global_config))
    config_path_row.addWidget(button("Load", window.load_global_config))
    global_layout.addLayout(config_path_row)
    window.global_config_editor = QPlainTextEdit()
    set_localized_placeholder(
        window.global_config_editor, "Load a global Mutagen YAML file to edit it safely."
    )
    window.global_config_editor.setMinimumHeight(180)
    window.global_config_editor.setFont(QFont("Consolas"))
    global_layout.addWidget(window.global_config_editor)
    window.global_config_status = label("No global config loaded.", muted=True, size=11)
    window.global_config_status.setWordWrap(True)
    global_layout.addWidget(window.global_config_status)
    window.global_yaml_recovery_button = button(
        "Open read-only recovery…", window.show_global_yaml_recovery
    )
    window.global_yaml_recovery_button.setEnabled(False)
    global_layout.addWidget(window.global_yaml_recovery_button)
    global_layout.addWidget(
        button("Review diff and save…", window.preview_global_config, kind="primary")
    )
    layout.addWidget(global_config)
    profiles_card, profiles_layout = card()
    profiles_layout.addWidget(label("Connection Profiles", size=16, bold=True))
    profiles_layout.addWidget(
        label(
            "Store reusable endpoint pairs, safe defaults, tags, and favorites locally. Profiles do not own or change Mutagen sessions.",
            muted=True,
        )
    )
    profiles_layout.addWidget(
        button("Manage Connection Profiles…", window.manage_connection_profiles)
    )
    profiles_layout.addWidget(button("Inspect SSH Profiles…", window.manage_ssh_profiles))
    layout.addWidget(profiles_card)
    ignore_card, ignore_layout = card()
    ignore_layout.addWidget(label("Ignore Presets", size=16, bold=True))
    ignore_layout.addWidget(
        label(
            "Manage ordered local rules for new sync drafts. Imported rules are reviewed before use; source files and existing sessions stay unchanged.",
            muted=True,
        )
    )
    ignore_layout.addWidget(button("Manage Ignore Presets…", window.manage_ignore_presets))
    layout.addWidget(ignore_card)
    projects_card, projects_layout = card()
    projects_layout.addWidget(label("Native Mutagen Projects", size=16, bold=True))
    projects_layout.addWidget(
        label(
            "Import and inspect mutagen.yml files without editing them or running project hooks and commands.",
            muted=True,
        )
    )
    projects_layout.addWidget(button("Manage Native Projects…", window.manage_native_projects))
    layout.addWidget(projects_card)
    portability, portability_layout = card()
    portability_layout.addWidget(label("Import, Export, and Migration", size=16, bold=True))
    portability_layout.addWidget(
        label(
            "Portable bundles include validated connection profiles and selected safe preferences. Session notes, history, Mutagen state, executable paths, and private keys stay local.",
            muted=True,
        )
    )
    transfer = QVBoxLayout()
    transfer.addWidget(button("Export Portable Bundle…", window.export_portable_bundle))
    transfer.addWidget(button("Import Portable Bundle…", window.import_portable_bundle))
    transfer.addWidget(button("Migrate Current Settings…", window.migrate_current_settings))
    transfer.addWidget(
        button("Rollback Settings Migration…", window.rollback_current_settings_migration)
    )
    portability_layout.addLayout(transfer)
    layout.addWidget(portability)
    note, nl = card()
    nl.addWidget(label("Information and Limitations", size=16, bold=True))
    text = label(
        "• CPU, RAM, and process I/O are totals for local Mutagen processes, not individual sessions.\n"
        "• The Mutagen CLI provides no universal bandwidth limit for existing sync sessions; watch/polling profiles apply to new sessions.\n"
        "• File and conflict counts come from the exported session status.\n"
        "• Sessions may prompt for SSH credentials; unattended SSH keys are recommended.\n"
        "• This application is not an official Mutagen product and does not modify its internal database.",
        muted=True,
    )
    text.setWordWrap(True)
    nl.addWidget(text)
    layout.addWidget(note)
    layout.addStretch()
    page.setWidget(root)
    return page
