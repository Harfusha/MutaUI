"""Mutagen Control 8.2 — Windows desktop companion for Mutagen CLI.

Start with: python app.py
Preview (offline demo, actions disabled): python app.py --demo
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import tempfile
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from functools import partial
from html import escape as html_escape
from pathlib import Path
from typing import Any, Literal, cast

_SOURCE_PACKAGE_PATH = Path(__file__).resolve().parent / "src"
if _SOURCE_PACKAGE_PATH.is_dir() and str(_SOURCE_PACKAGE_PATH) not in sys.path:
    sys.path.insert(0, str(_SOURCE_PACKAGE_PATH))

# PyInstaller places Qt and Shiboken DLLs in separate bundle subdirectories.
# Register both before importing any PySide module so Windows cannot resolve
# a same-named DLL from another Python or Qt installation on PATH.
_DLL_DIRECTORY_HANDLES = []
if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):  # pragma: no cover
    _bundle_root = Path(sys.__dict__["_MEIPASS"])
    _dll_directories = (_bundle_root / "PySide6", _bundle_root / "shiboken6")
    os.environ["PATH"] = os.pathsep.join(
        [
            *(str(path) for path in _dll_directories),
            str(_bundle_root),
            os.environ.get("PATH", ""),
        ]
    )
    for _dll_directory in _dll_directories:
        if _dll_directory.is_dir():
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(_dll_directory)))

from PySide6.QtCore import (
    QAbstractTableModel,  # noqa: F401
    QEvent,
    QModelIndex,  # noqa: F401
    QPoint,
    QPointF,  # noqa: F401
    QRectF,
    Qt,
    QThreadPool,
    QTime,
    QTimer,
    QUrl,
    qVersion,
)
from PySide6.QtGui import (
    QAction,
    QBrush,  # noqa: F401
    QCloseEvent,
    QColor,
    QDesktopServices,
    QHideEvent,
    QIcon,
    QKeySequence,
    QLinearGradient,  # noqa: F401
    QPainter,
    QPainterPath,  # noqa: F401
    QPen,
    QPixmap,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTimeEdit,
    QToolTip,  # noqa: F401
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from async_recorder import AsyncRecorder
from connection_profiles import (
    ConnectionProfile as ConnectionProfile,
)
from connection_profiles import (
    ConnectionProfileStore,
    load_profile_store,
)
from endpoint_inspector import summary as inspect_session
from forward_configuration import (
    FORWARD_CONFIG_FIELDS,
    ForwardConfigField,
    ForwardConfigRow,
    forward_configuration_rows,
)
from ignore_presets import (
    IgnorePresetError,
    IgnorePresetStore,
    apply_preset_import,
    load_ignore_presets,
    path_aware_ignore_rule,
    preset_to_record,
)
from insights import AlertEngine, local_self_check, safe_diagnostic_report, session_log_report
from log_stream import FileTail, TrackedLogLines
from monitoring import (
    ForwardTrafficMeter,
    HistoryStore,
    Sample,
    query_metrics_from_file,
    statistics_from_file,
)
from mutagen_client import (
    MutagenClient,
    MutagenError,
    ProcessSampler,
    Snapshot,
    classify,
    conflict_count,
    endpoint_text,
    example_snapshot,
    human_bytes,
    problem_count,
    read_registration,
    session_preflight_fingerprint,
)
from mutaui import __version__ as APP_VERSION
from mutaui.adapters.cli_executor import LegacyMutagenExecutor
from mutaui.adapters.mutagen_snapshot import from_legacy_session
from mutaui.services.action_planner import ACTION_SPECS, ActionPlanner, ActionRequest
from mutaui.services.health_tracker import (
    HealthObservation,
    HealthPolicy,
    HealthTracker,
    health_policy_from_settings,
)
from mutaui.services.quiet_hours import quiet_hours_active
from mutaui.services.reconfiguration import (
    build_reconfiguration_preview,
    extract_sync_configuration,
    validate_native_command_snapshot,
)
from mutaui.services.replacement import (
    ReplacementAuditEvent,
    ReplacementReceipt,
    ReplacementRequest,
    replace_non_project_mutagen_session,
)
from mutaui.services.replacement_command import render_sync_replacement_arguments
from mutaui.services.session_configuration import (
    build_session_configuration_proposal,
)
from mutaui.services.session_doctor import (
    FRESHNESS_SECONDS,
    SessionDoctorContext,
    diagnose_sessions,
)
from mutaui.services.session_notification_gate import SessionNotificationGate
from mutaui.services.session_provenance import ProvenanceStoreError, SessionProvenanceStore
from mutaui.services.update_checker import (
    RELEASES_URL,
    UpdateCheckResult,
    check_for_update,
)
from mutaui.ui import global_config_editor, settings_migration
from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog
from mutaui.ui.connection_profiles_dialog import ConnectionProfilesDialog
from mutaui.ui.health_network_monitor import (
    attach_health_network_monitor as attach_health_network_monitor_ui,
)
from mutaui.ui.health_network_monitor import (
    health_network_changed as apply_health_network_change,
)
from mutaui.ui.ignore_rules import IgnorePresetManagerDialog
from mutaui.ui.onboarding import (
    CLIDiscovery,
    host_architecture,
    inspect_cli,
    run_isolated_local_sync_test,
)
from mutaui.ui.page_shell import PAGE_ROUTES, LazyStackedWidget
from mutaui.ui.performance_tuning import (
    apply_performance_assistant,
)
from mutaui.ui.portable_import_preview import PortableImportPreviewDialog
from mutaui.ui.preferences import (
    ADVANCED_ROUTE_IDS,  # noqa: F401 -- retained as app module compatibility export
    active_language,
    set_active_language,
    translate,
    translate_route,
    translate_text,
)
from mutaui.ui.preferences_controller import PreferencesController
from mutaui.ui.project_viewer import NativeProjectManagerDialog
from mutaui.ui.session_alerts import check_alerts as check_session_alerts
from mutaui.ui.session_configuration_table import fill_session_configuration_table
from mutaui.ui.settings_page import build_settings_page
from mutaui.ui.settings_registry import setting_tooltip
from mutaui.ui.ssh_profile_manager import SSHProfileManagerDialog
from mutaui.ui.tray_status import update_tray_status as update_tray_status_ui
from mutaui.ui.widgets.basic import (
    add_localized_item,
    add_localized_items,
    add_localized_row,
    button,
    card,
    label,
    localized_button,
    localized_checkbox,
    localized_label,
)
from mutaui.ui.worker import Worker, WorkerSignals  # noqa: F401
from performance import (  # noqa: F401
    PollBackoff,
    RefreshGate,
    envelope_downsample,
    nearest_time_index,
)
from portable_bundle import (
    PortableBundleError,
    apply_profile_import,
    build_bundle,
    load_bundle,
    selected_preferences,
)
from server_groups import group_servers, session_servers
from settings import (
    load_settings,
    settings_path,
)
from settings import write_settings as save_settings_file
from sync_configuration import (
    SYNC_CONFIG_FIELDS,
    SyncConfigField,
    SyncConfigRow,
    session_configuration_rows,
)
from sync_profiles import PROFILES as PROFILES
from sync_profiles import AdaptivePolling

BG = "#0B1019"
CARD = "#141D2A"
CARD2 = "#1C2B3A"
BORDER = "#2A394A"
MUTED = "#A0AEC0"
TEXT = "#F1F6FA"
TEAL = "#61E0B9"
BLUE = "#7AAEFF"
AMBER = "#F2BF70"
RED = "#FB8696"

CSS = f"""
QWidget {{ color: {TEXT}; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
QMainWindow, QWidget#main, QScrollArea, QWidget#scrollbody {{ background: {BG}; }}
QFrame#sidebar {{ background: #101824; border-right: 1px solid {BORDER}; }}
QScrollArea#navscroll, QWidget#navcontent {{ background: #101824; border: 0; }}
QListWidget {{ background:#111D2B; border:1px solid {BORDER}; border-radius:9px; padding:5px; }}
QListWidget::item {{ padding:12px; margin:2px; border-radius:7px; }}
QListWidget::item:selected {{ background:#1D4B47; color:{TEAL}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 15px; }}
QFrame#inner {{ background: #182536; border: 1px solid {BORDER}; border-radius: 11px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#eyebrow {{ color: {MUTED}; font-size: 11px; font-weight: 700; }}
QLabel#hero {{ font-size: 25px; font-weight: 750; }}
QLabel#logo {{ font-size: 21px; font-weight: 800; letter-spacing: .2px; }}
QLabel#metric {{ font-size: 28px; font-weight: 750; }}
QLabel#section {{ font-size: 16px; font-weight: 700; }}
QLabel#smallnum {{ font-size: 19px; font-weight: 700; }}
QPushButton {{ background: {CARD2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 9px;
              padding: 10px 15px; font-weight: 600; }}
QPushButton:hover {{ background: #26344E; border-color: #435675; }}
QPushButton:pressed {{ background: #344866; }}
QPushButton:disabled {{ color: #9BAAC0; background: #171E2D; border-color: #33435B; }}
QPushButton:focus {{ border-color: {BLUE}; }}
QPushButton#primary:focus {{ border-color: #B6FFE9; }}
QPushButton#danger:focus {{ border-color: {RED}; }}
QPushButton#primary {{ background: {TEAL}; color: #071A1A; border-color: {TEAL}; font-weight: 800; }}
QPushButton#primary:hover {{ background: #94F4D9; }}
QPushButton#primary:pressed {{ background: #3EC6A2; }}
QPushButton#danger {{ background: #3B2537; border-color: #734050; color: #FFACB8; }}
QPushButton#danger:hover {{ background: #513044; }}
QPushButton#nav {{ text-align: left; background: transparent; border: 1px solid transparent;
                  color: {MUTED}; border-radius: 9px; padding: 9px 13px; font-size: 13px; }}
QPushButton#nav:hover {{ background: #1A263A; color: {TEXT}; }}
QPushButton#nav:checked {{ background: #173A35; border-color: #36685F; color: {TEAL}; font-weight: 800; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{ background: #101829; color: {TEXT};
                           border: 1px solid {BORDER}; border-radius: 9px; padding: 7px 11px;
                           min-height: 22px; selection-background-color: #385F6A; }}
QComboBox {{ padding-right: 27px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right;
                        width: 28px; border-left: 1px solid {BORDER}; }}
QComboBox::down-arrow {{ width: 7px; height: 7px; }}
QSpinBox {{ padding-right: 20px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {TEAL}; }}
QListWidget:focus, QTableWidget:focus, QTableView:focus {{ border: 2px solid {BLUE}; }}
QComboBox QAbstractItemView {{ background: #17243A; border: 1px solid {BORDER}; selection-background-color: #2D4955; }}
QTableWidget, QTableView {{ background: {CARD}; color: {TEXT}; alternate-background-color: #182136; border: 0; border-radius: 10px;
                gridline-color: transparent; selection-background-color: #233D4F; }}
QTableWidget::item, QTableView::item {{ padding: 8px 8px; border-bottom: 1px solid #232F46; }}
QTableWidget::item:selected, QTableView::item:selected {{ color: white; }}
QHeaderView::section {{ background: {CARD}; color: {MUTED}; border: 0;
                        border-bottom: 1px solid {BORDER}; padding: 11px 8px; font-size: 11px; font-weight: 750; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: #355063; border-radius: 4px; min-height: 28px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: #355063; border-radius: 4px; min-width: 28px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {BORDER}; border-radius: 4px;
                        background: #101829; }}
QCheckBox::indicator:checked {{ background: {TEAL}; border-color: {TEAL}; }}
QCheckBox::indicator:hover {{ border-color: {TEAL}; }}
QCheckBox:focus::indicator {{ border-color: {BLUE}; }}
QDialog {{ background: #101729; }}
QDialogButtonBox QPushButton {{ min-width: 90px; }}
QMenu {{ background: #17243A; border: 1px solid {BORDER}; border-radius: 9px; padding: 6px; }}
QMenu::item {{ padding: 9px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: #233D4F; color: {TEXT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 10px; }}
QProgressBar {{ background:#101829; border:1px solid #33425D; border-radius:6px; min-height:16px; text-align:center; font-size: 11px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3BC8A6, stop:1 #55E6C1); border-radius:5px; }}
QToolTip {{ background: #1E2B43; border: 1px solid #41536E; color: white; padding: 7px 10px; border-radius: 6px; }}
"""


def read_settings() -> dict[str, Any]:
    return load_settings(settings_path()).values


def settings_warning_message(warnings: tuple[str, ...]) -> str | None:
    if not warnings:
        return None
    recovered = any(
        "restored from the last valid settings backup" in warning.casefold() for warning in warnings
    )
    message = (
        "Settings were restored from the last valid backup. Review Settings."
        if recovered
        else "Some settings were invalid. Safe defaults are active; the original will be backed up when settings are saved."
    )
    return translate_text(message, active_language())


def write_settings(data: dict[str, Any]) -> None:
    save_settings_file(settings_path(), data)


from mutaui.ui.localization import (
    _LOCALIZED_ITEM_ROLE,
    set_localized_accessible_name,
    set_localized_placeholder,
    set_localized_text,
    set_localized_title,
    set_localized_tooltip,
)


def localized_action(text: str, parent: QWidget) -> QAction:
    widget = QAction("", parent)
    set_localized_text(widget, text)
    return widget


def _czech_plural(count: int, forms: tuple[str, str, str]) -> str:
    remainder_100 = count % 100
    if remainder_100 in range(12, 15):
        return forms[2]
    remainder_10 = count % 10
    if remainder_10 == 1:
        return forms[0]
    if remainder_10 in {2, 3, 4}:
        return forms[1]
    return forms[2]


def separator() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{BORDER}; border:0")
    return f


def field_format(field: str, value: float | None) -> str:
    if value is None:
        return "Not measured"
    if field == "cpu":
        return f"{value:.1f} %"
    if field == "memory":
        return human_bytes(value)
    return human_bytes(value) + "/s"


def readable_record_lines(value: object, *, indent: int = 0) -> list[str]:
    """Turn nested Mutagen conflict/problem objects into labeled text lines."""
    pad = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            label_text = "".join(
                f" {char.lower()}" if char.isupper() else char for char in str(key)
            )
            label_text = label_text.replace("_", " ").strip().capitalize()
            if isinstance(item, (dict, list, tuple)):
                lines.append(f"{pad}{label_text}:")
                lines.extend(readable_record_lines(item, indent=indent + 2))
            else:
                lines.append(f"{pad}{label_text}: {item}")
        return lines or [f"{pad}Details unavailable"]
    if isinstance(value, (list, tuple)):
        lines = []
        for index, item in enumerate(value, 1):
            if isinstance(item, (dict, list, tuple)):
                lines.append(f"{pad}Item {index}")
                lines.extend(readable_record_lines(item, indent=indent + 2))
            else:
                lines.append(f"{pad}• {item}")
        return lines or [f"{pad}None"]
    return [f"{pad}{value}"]


def session_detail_html(lines: Iterable[str], separator_text: str) -> str:
    """Render session detail rows with visual hierarchy while escaping values."""
    rendered = []
    for line in lines:
        if line == separator_text:
            rendered.append(f'<hr style="border:0;border-top:1px solid {BORDER};margin:9px 0;">')
        elif "\n" in line:
            field, value = line.split("\n", 1)
            rendered.append(
                '<div style="margin:4px 0 10px 0;">'
                f'<div style="color:{MUTED};font-size:11px;font-weight:600;">{html_escape(field)}</div>'
                f'<div style="color:{TEXT};font-size:13px;">{html_escape(value)}</div>'
                "</div>"
            )
        elif line == line.upper() and len(line) <= 42:
            rendered.append(
                f'<div style="color:{BLUE};font-size:11px;font-weight:700;margin:5px 0;">'
                f"{html_escape(line)}</div>"
            )
        elif ": " in line:
            field, value = line.split(": ", 1)
            indent = len(field) - len(field.lstrip())
            rendered.append(
                f'<div style="margin:2px 0 2px {indent * 10}px;">'
                f'<span style="color:{MUTED};">{html_escape(field.strip())}:</span> '
                f'<span style="color:{TEXT};">{html_escape(value)}</span></div>'
            )
        else:
            indent = len(line) - len(line.lstrip())
            rendered.append(
                f'<div style="margin:2px 0 2px {indent * 10}px;color:{TEXT};">'
                f"{html_escape(line.strip())}</div>"
            )
    return '<div style="line-height:1.35;">' + "".join(rendered) + "</div>"


from mutaui.ui.session_dialog import SessionDialog, configure_settings_path_provider
from mutaui.ui.widgets.graph import Graph
from mutaui.ui.widgets.health_ring import HealthRing
from mutaui.ui.widgets.session_table import SessionTableModel

configure_settings_path_provider(lambda: settings_path())


class QuickNavigator(QDialog):
    """Keyboard-first, no-network palette for navigation and exact session actions."""

    PAGES = tuple(route.title for route in PAGE_ROUTES)
    GLYPHS = tuple(route.glyph for route in PAGE_ROUTES)
    CAPTIONS = tuple(route.search_description for route in PAGE_ROUTES)

    def __init__(
        self,
        parent: QWidget | None,
        commands: Iterable[tuple[str, str | None, str | None, str, str]] = (),
    ) -> None:
        super().__init__(parent)
        set_localized_title(self, "Quick Navigation  ·  Ctrl+K")
        self.setMinimumSize(520, 420)
        self.target: int | None = None
        self.command: tuple[Any, ...] | None = None
        self.commands = tuple(commands)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(23, 21, 23, 21)
        layout.setSpacing(13)
        layout.addWidget(label("Go to page or run a command", size=19, bold=True))
        hint = label(
            "Search pages, sessions, and commands · Enter to choose · Escape to close", muted=True
        )
        layout.addWidget(hint)
        self.search = QLineEdit()
        set_localized_placeholder(self.search, "Search page…")
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSpacing(2)
        layout.addWidget(self.list, 1)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.choose)
        self.list.itemActivated.connect(lambda _: self.choose())
        self.list.itemDoubleClicked.connect(lambda _: self.choose())
        self.filter("")
        self.search.setFocus()

    def filter(self, term: str) -> None:
        self.list.clear()
        query = term.casefold().split()
        for index, page in enumerate(self.PAGES):
            caption = self.CAPTIONS[index] if index < len(self.CAPTIONS) else ""
            searchable = f"{page} {caption}".casefold()
            if all(word in searchable for word in query):
                glyph = self.GLYPHS[index] if index < len(self.GLYPHS) else "·"
                item = QListWidgetItem(f"  {glyph}   {page}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(caption)
                self.list.addItem(item)
        for action, kind, identifier, title, searchable in self.commands:
            if all(word in f"{title} {searchable}".casefold() for word in query):
                item = QListWidgetItem(f"  ↪   {title}")
                item.setData(Qt.ItemDataRole.UserRole, ("command", action, kind, identifier))
                item.setToolTip(title)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def choose(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, tuple) and value[0] == "command":
                self.command = value[1:]
            else:
                self.target = int(value)
            self.accept()


class SupportBundleDialog(QDialog):
    """Choose a local support export and preview its sensitivity before saving."""

    def __init__(
        self,
        *,
        snapshot_preview: str,
        event_count: int,
        monitored_line_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        czech = active_language().casefold().startswith("cs")
        copy = {
            "title": "Balíček podpory" if czech else "Support Bundle",
            "type": "Typ exportu" if czech else "Export type",
            "safe": "Bezpečný diagnostický report" if czech else "Safe diagnostics report",
            "full": "Úplný snímek relací" if czech else "Full session snapshot",
            "logs": "Místní snímek protokolů" if czech else "Local session log snapshot",
            "self_check": "Místní kontrola aplikace" if czech else "Local application self-check",
            "event_details": "Zahrnout text událostí (může obsahovat cesty a adresy)"
            if czech
            else "Include event text (may contain paths and addresses)",
            "line_details": "Zahrnout sledované řádky protokolu (mohou obsahovat citlivé údaje)"
            if czech
            else "Include monitored log lines (may contain sensitive details)",
            "save": "Uložit…" if czech else "Save…",
            "cancel": "Zrušit" if czech else "Cancel",
        }
        self.setWindowTitle(copy["title"])
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(copy["type"], self))
        self.mode = QComboBox(self)
        self.mode.addItem(copy["safe"], "safe")
        self.mode.addItem(copy["full"], "full")
        self.mode.addItem(copy["logs"], "logs")
        self.mode.addItem(copy["self_check"], "self_check")
        self.mode.currentIndexChanged.connect(self.update_preview)
        layout.addWidget(self.mode)
        self.preview = QPlainTextEdit(self)
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(180)
        layout.addWidget(self.preview)
        self.include_event_messages = QCheckBox(copy["event_details"], self)
        self.include_monitored_log_lines = QCheckBox(copy["line_details"], self)
        self.include_event_messages.stateChanged.connect(self.update_preview)
        self.include_monitored_log_lines.stateChanged.connect(self.update_preview)
        layout.addWidget(self.include_event_messages)
        layout.addWidget(self.include_monitored_log_lines)
        self._snapshot_preview = snapshot_preview[:2400]
        self._snapshot_preview_truncated = len(snapshot_preview) > 2400
        self._event_count = max(0, int(event_count))
        self._monitored_line_count = max(0, int(monitored_line_count))
        self._copy = copy
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setText(copy["save"])
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(copy["cancel"])
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.update_preview()

    def update_preview(self, *_args: object) -> None:
        mode = self.mode.currentData()
        logs_selected = mode == "logs"
        self.include_event_messages.setEnabled(logs_selected)
        self.include_monitored_log_lines.setEnabled(logs_selected)
        self.button_box.button(QDialogButtonBox.StandardButton.Save).setText(
            (
                "Spustit kontrolu"
                if active_language().casefold().startswith("cs")
                else "Run self-check"
            )
            if mode == "self_check"
            else self._copy["save"]
        )
        if mode == "safe":
            preview = (
                "Bezpečný export použije povolený seznam polí; cesty, hostitelé, uživatelé, klíče a text protokolů vynechá."
                if active_language().casefold().startswith("cs")
                else "Safe export uses an allowlist; paths, hosts, users, keys, and log text are omitted."
            )
        elif mode == "full":
            heading = (
                "Náhled úplného snímku; může obsahovat místní cesty a endpointy:"
                if active_language().casefold().startswith("cs")
                else "Full snapshot preview; it may contain local paths and endpoints:"
            )
            preview = f"{heading}\n{self._snapshot_preview}"
            if self._snapshot_preview_truncated:
                preview += (
                    "\n… Zobrazen je jen začátek; export může obsahovat další položky."
                    if active_language().casefold().startswith("cs")
                    else "\n… Preview truncated; the export may contain more records."
                )
        elif mode == "self_check":
            preview = (
                "Zkontroluje místní cesty, integritu databáze, Qt, Python a verzi Mutagenu. Bez vzdálených zápisů."
                if active_language().casefold().startswith("cs")
                else "Checks local paths, database integrity, Qt, Python, and Mutagen version. No remote writes."
            )
        else:
            details = []
            if self.include_event_messages.isChecked():
                details.append(
                    "zahrne text událostí"
                    if active_language().casefold().startswith("cs")
                    else "includes event text"
                )
            if self.include_monitored_log_lines.isChecked():
                details.append(
                    "zahrne sledované řádky"
                    if active_language().casefold().startswith("cs")
                    else "includes monitored log lines"
                )
            if not details:
                details.append(
                    "bez textových detailů"
                    if active_language().casefold().startswith("cs")
                    else "omits raw text"
                )
            preview = (
                f"Místní export: {self._event_count} událostí, {self._monitored_line_count} sledovaných řádků; "
                f"{', '.join(details)}."
                if active_language().casefold().startswith("cs")
                else f"Local export: {self._event_count} events, {self._monitored_line_count} monitored lines; "
                f"{', '.join(details)}."
            )
            if (
                self.include_event_messages.isChecked()
                or self.include_monitored_log_lines.isChecked()
            ):
                preview += (
                    " Citlivý text bude před uložením potvrzen."
                    if active_language().casefold().startswith("cs")
                    else " Sensitive text will require confirmation before saving."
                )
        self.preview.setPlainText(preview)


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False, *, history_path: str | Path | None = None) -> None:
        super().__init__()
        self.preferences_controller = PreferencesController(self, stylesheet=CSS)
        self.demo = demo
        self.settings_load = load_settings(settings_path())
        self.conf = self.settings_load.values
        self.client = MutagenClient(self.conf.get("binary", ""))
        self.action_planner = ActionPlanner(now=time.monotonic)
        self.session_provenance = SessionProvenanceStore(
            settings_path().with_name("session-provenance.json")
        )
        self.sampler = ProcessSampler()
        self.snapshot = example_snapshot() if demo else Snapshot(binary=self.client.binary)
        self.health_tracker = HealthTracker(self.health_policy_from_settings())
        self._power_event_filter: object | None = None
        self._last_snapshot_received_monotonic: float | None = None
        self._health_network_information = None
        self._health_network_reachability: object | None = None
        self.onboarding_wizard: QWizard | None = None
        if not demo:
            self._attach_health_network_monitor()
        self._doctor_observation_key: tuple[datetime | None, datetime | None] | None = None
        self._doctor_previous_issue_count: int | None = None
        self._doctor_current_issue_count: int | None = None
        self.cpu_series: deque[Any] = deque(maxlen=50)
        self.mem_series: deque[Any] = deque(maxlen=50)
        selected_history_path = history_path
        if selected_history_path is None:
            selected_history_path = (
                ":memory:" if demo else settings_path().parent / "metrics.sqlite3"
            )
        try:
            self.history = HistoryStore(selected_history_path)
        except (OSError, sqlite3.DatabaseError):
            self.history = HistoryStore()  # Still works without a writable user directory.
        # A dedicated writer connection batches commits outside the Qt event loop.
        # The demo uses in-memory SQLite and writes directly to its own connection.
        self.recorder = (
            None if demo or self.history.path == ":memory:" else AsyncRecorder(self.history.path)
        )
        if demo:
            self.seed_demo_history()
        self.traffic_meter = ForwardTrafficMeter()
        self.traffic_rates = (0.0, 0.0)
        self._traffic_sample_pending = False
        self.last_metrics = {"cpu": 0, "memory": 0, "read_rate": 0, "write_rate": 0, "processes": 0}
        self.previous_states = None
        self.previous_daemon = None
        self.session_counts = (0, 0)
        self.alert_engine = AlertEngine()
        self.session_notification_gate = SessionNotificationGate()
        self.chart_frozen = False
        self.tail_file: FileTail | None = None
        self.tail_lines = TrackedLogLines(maxlen=1200)
        self._tail_render_epoch = -1
        self._tail_render_count = 0
        self._tail_render_filter = ""
        self._stats_cache_at = 0.0
        self._stats_cache_range: float | None = None
        self._stats_pending = False
        self.favorites = {
            kind: set(str(x) for x in self.conf.get("favorites", {}).get(kind, []))
            for kind in ("sync", "forward")
        }
        self.logs = deque(
            (
                f"[{datetime.fromtimestamp(ts):%d.%m. %H:%M:%S}] {message}"
                for ts, severity, message in self.history.events(800)
            ),
            maxlen=800,
        )
        self.pending_poll = False
        self._pending_launch_requests: list[dict[str, Any]] = []
        self._initial_refresh_pending = True
        self._refresh_generation = 0
        self._refresh_again = False
        self.pending_action = False
        self.poll_backoff = PollBackoff(base=max(2, int(self.conf.get("interval", 4))))
        self.adaptive_policy = AdaptivePolling(
            fast=int(self.conf.get("adaptive_fast", 2)),
            idle=int(self.conf.get("adaptive_idle", 30)),
            quiet_after=int(self.conf.get("adaptive_quiet", 90)),
        )
        self._poll_started_at = 0.0
        self.current_kind = "sync"
        self.current_id = ""
        self._allow_exit = False
        self.workers: set[Worker] = set()
        self._shutdown_pending = False
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)
        self._resource_pending = False
        self._version_cache = ("", 0.0, "")
        self._version_label_text = "Version: not detected"
        self._release_check_running = False
        self._release_check_result: UpdateCheckResult | None = None
        self._release_check_error = False
        self._chart_dashboard_gate = RefreshGate(2.8)
        self._chart_monitor_gate = RefreshGate(3.2)
        self._chart_query_pending = False
        self._chart_query_reschedule = False
        self._table_signatures: dict[str, Any] = {}
        self._tail_render_pending = False
        self._eco_hidden = False
        self._tray_idle_mode = False
        self._tray_idle_started_at: float | None = None
        self._tray_idle_seconds_pending = 0.0
        self._last_recorded_cli_launch_count = 0
        # Mode stays in memory only; changing it never writes settings or Mutagen data.
        self.ui_mode = "basic"
        self.ui_language = self.conf.get("language", "en")
        set_active_language(self.ui_language)
        set_localized_title(self, "Mutagen Control 8.2 · Server Manager")
        self.setMinimumSize(940, 650)
        self.resize(1480, 940)
        self.setStyleSheet(CSS)
        self.setWindowIcon(self.make_icon())
        self.create_ui()
        self.apply_ui_language(self.ui_language)
        self.set_ui_mode(self.ui_mode)
        self.apply_theme(self.conf.get("theme", "system"))
        self.create_tray()
        shortcut = QShortcut(QKeySequence("Ctrl+R"), self)
        shortcut.activated.connect(lambda: self.refresh(force=True))
        shortcut = QShortcut(QKeySequence("F5"), self)
        shortcut.activated.connect(lambda: self.refresh(force=True))
        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.new_current_session)
        shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        shortcut.activated.connect(partial(self.set_page, 6))
        shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(self.open_navigator)
        # Direct page shortcuts: Ctrl+1 through Ctrl+0 (pages 0–9) and Ctrl+Shift+1 for page 10
        for _i in range(10):
            _idx = _i  # capture
            shortcut = QShortcut(QKeySequence(f"Ctrl+{(_i + 1) % 10 if _i < 9 else 0}"), self)
            shortcut.activated.connect(partial(self.set_page, _idx))
        shortcut = QShortcut(QKeySequence("Ctrl+Shift+1"), self)
        shortcut.activated.connect(partial(self.set_page, 10))
        self.add_log("Application started" + (" (DEMO mode)" if demo else ""))
        settings_warning = settings_warning_message(self.settings_load.warnings)
        if settings_warning:
            self.statusBar().showMessage(settings_warning, 15000)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.poll_period_ms())
        self.metric_timer = QTimer(self)
        self.metric_timer.timeout.connect(self.refresh_resources)
        self.metric_timer.start(self.metric_period_ms())
        self.tail_timer = QTimer(self)
        self.tail_timer.timeout.connect(self.poll_tail)
        # Do not wake up the UI every 900 ms until a log file is selected.
        QTimer.singleShot(200, self._start_initial_refresh)
        QTimer.singleShot(300, self.refresh_resources)
        if not demo and not self.conf.get("onboarding_completed", False):
            QTimer.singleShot(500, self.open_onboarding)
        QTimer.singleShot(1500, self.check_for_release_update_on_startup)

    def poll_period_ms(self) -> int:
        eco = self._eco_hidden and bool(self.conf.get("eco_tray", True))
        return (
            self.adaptive_policy.interval(
                enabled=bool(self.conf.get("adaptive_poll", True)),
                normal=int(self.conf.get("interval", 4)),
                eco=eco,
            )
            * 1000
        )

    def metric_period_ms(self) -> int:
        """User-selectable detail rate, with an optional low-impact tray mode."""
        seconds = max(1, min(10, int(self.conf.get("metric_interval", 2))))
        if self._eco_hidden and self.conf.get("eco_tray", True):
            seconds = max(6, seconds)
        return seconds * 1000

    def update_polling_mode(self) -> None:
        self._eco_hidden = not self.isVisible() or self.isMinimized()
        tray_idle = self._eco_hidden and bool(self.conf.get("eco_tray", True))
        now = time.monotonic()
        if tray_idle != self._tray_idle_mode:
            if self._tray_idle_mode and self._tray_idle_started_at is not None:
                self._tray_idle_seconds_pending += max(0.0, now - self._tray_idle_started_at)
            self._tray_idle_started_at = now if tray_idle else None
            self._tray_idle_mode = tray_idle
        if hasattr(self, "metric_timer"):
            self.metric_timer.setInterval(self.metric_period_ms())
        if hasattr(self, "timer"):
            self.timer.setInterval(self.poll_period_ms())

    def tray_idle_seconds(self) -> float:
        now = time.monotonic()
        elapsed = self._tray_idle_seconds_pending
        if self._tray_idle_mode and self._tray_idle_started_at is not None:
            elapsed += max(0.0, now - self._tray_idle_started_at)
        return round(elapsed, 3)

    def commit_tray_idle_sample(self) -> None:
        self._tray_idle_seconds_pending = 0.0
        self._tray_idle_started_at = time.monotonic() if self._tray_idle_mode else None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.update_polling_mode()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.update_polling_mode()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self.update_polling_mode()

    def seed_demo_history(self) -> None:
        """Populate illustrative graphs offline (only in explicitly marked demo mode)."""
        now = time.time()
        for i in range(125):
            phase = i / 5.0
            spike = 33 if i % 43 in range(12, 17) else 0
            cpu = max(0.0, 6 + 5 * math.sin(phase) + spike)
            memory = int((112 + i * 0.22 + 7 * math.sin(phase / 2)) * 1024**2)
            sample = Sample(
                ts=now - (124 - i) * 14,
                cpu=cpu,
                memory=memory,
                read_rate=32000 + 60000 * abs(math.sin(phase)),
                write_rate=54000 + 85000 * abs(math.cos(phase / 1.3)),
                forward_out_rate=18000 + 65000 * abs(math.cos(phase / 1.8)),
                forward_in_rate=65000 + 100000 * abs(math.sin(phase / 2)),
                processes=2,
                active_sessions=2,
                problem_sessions=0,
            )
            self.history.add(sample)

    @staticmethod
    def make_icon() -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(TEAL))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(3, 3, 58, 58), 17, 17)
        p.setBrush(QColor("#0C1B25"))
        p.drawRoundedRect(QRectF(16, 16, 11, 32), 5, 5)
        p.drawRoundedRect(QRectF(34, 16, 11, 32), 5, 5)
        p.end()
        return QIcon(pix)

    def create_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self._last_notification_session_keys = ()
        set_localized_tooltip(self.tray, "Mutagen Control")
        menu = QMenu(self)
        show_action = localized_action("Open Mutagen Control", self)
        show_action.triggered.connect(self.show_window)
        quit_action = localized_action("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: (
                self.show_window()
                if reason == QSystemTrayIcon.ActivationReason.DoubleClick
                else None
            )
        )
        self.tray.messageClicked.connect(self.open_notified_issue)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _tray_status_icon(self, status: str) -> QIcon:
        pixmap = self.windowIcon().pixmap(64, 64)
        painter = QPainter(pixmap)
        colors = {
            "issue": "#EF4444",
            "paused": "#F59E0B",
            "busy": "#38BDF8",
            "healthy": "#22C55E",
            "idle": "#64748B",
            "offline": "#EF4444",
            "unknown": "#A78BFA",
        }
        painter.setPen(QPen(QColor("#0B1019"), 2))
        painter.setBrush(QColor(colors.get(status, colors["unknown"])))
        painter.drawEllipse(43, 43, 18, 18)
        painter.end()
        return QIcon(pixmap)

    def update_tray_status(self, snap: Any, states: Mapping[tuple[str, str], str]) -> None:
        update_tray_status_ui(self.tray, self._tray_status_icon, snap, states)

    def open_notified_issue(self) -> None:
        keys = self._last_notification_session_keys
        if not keys:
            self.show_window()
            return
        if len(keys) == 1:
            kind, identifier = keys[0]
        else:
            labels = [f"{kind}: {identifier}" for kind, identifier in keys]
            selected, accepted = QInputDialog.getItem(
                self,
                translate_text("Session issues", active_language()),
                translate_text("Choose the session to open", active_language()),
                labels,
                0,
                False,
            )
            if not accepted:
                return
            kind, identifier = keys[labels.index(selected)]
        self.handle_launch_request({"command": "open_session", "session_id": identifier})

    def open_onboarding(self) -> None:
        if self.onboarding_wizard is not None:
            self.onboarding_wizard.raise_()
            self.onboarding_wizard.activateWindow()
            return

        wizard = QWizard(self)
        set_localized_title(wizard, "Welcome to Mutagen Control")
        wizard.setMinimumWidth(560)
        self.onboarding_wizard = wizard
        self._onboarding_pending_client: MutagenClient | None = None

        welcome = QWizardPage()
        set_localized_title(welcome, "Welcome", page_title=True)
        welcome_layout = QVBoxLayout(welcome)
        welcome_text = localized_label(
            "Mutagen Control uses the Mutagen CLI already installed on this computer. This guide checks the local CLI only. It does not connect to remote endpoints or create sessions unless you explicitly run the isolated local test."
        )
        welcome_text.setWordWrap(True)
        welcome_layout.addWidget(welcome_text)
        self.onboarding_update_check = localized_checkbox("Check releases on startup")
        self.onboarding_update_check.setChecked(
            bool(self.conf.get("check_updates_on_startup", False))
        )
        self.onboarding_update_check.setToolTip(
            setting_tooltip("check_updates_on_startup", self.ui_language)
        )
        welcome_layout.addWidget(self.onboarding_update_check)
        update_consent_note = localized_label(
            "Optional. If enabled, MutaUI checks public GitHub release metadata at startup. No session or device data is sent; no files are downloaded or installed."
        )
        update_consent_note.setWordWrap(True)
        welcome_layout.addWidget(update_consent_note)
        install_help = localized_button("Open official Mutagen installation guide")
        install_help.clicked.connect(self.open_mutagen_install_guide)
        welcome_layout.addWidget(install_help)
        wizard.addPage(welcome)

        cli_page = QWizardPage()
        set_localized_title(cli_page, "Find and check Mutagen", page_title=True)
        cli_layout = QVBoxLayout(cli_page)
        self.onboarding_cli_status = localized_label(
            "CLI not checked yet. Version and help checks are read-only and disable daemon autostart."
        )
        self.onboarding_cli_status.setWordWrap(True)
        cli_layout.addWidget(self.onboarding_cli_status)
        detect = localized_button("Check detected CLI")
        detect.clicked.connect(self.check_onboarding_cli)
        cli_layout.addWidget(detect)
        choose = localized_button("Choose Mutagen executable…")
        choose.clicked.connect(self.choose_onboarding_cli)
        cli_layout.addWidget(choose)
        wizard.addPage(cli_page)

        daemon_page = QWizardPage()
        set_localized_title(daemon_page, "Daemon and optional local test", page_title=True)
        daemon_layout = QVBoxLayout(daemon_page)
        daemon_note = localized_label(
            "Mutagen manages sessions through a per-user background daemon. The optional test uses a temporary Mutagen data directory and two local folders; it never uses SSH or your existing Mutagen daemon."
        )
        daemon_note.setWordWrap(True)
        daemon_layout.addWidget(daemon_note)
        test_button = localized_button("Run isolated local-only sync test")
        test_button.clicked.connect(self.run_onboarding_local_test)
        daemon_layout.addWidget(test_button)
        self.onboarding_test_status = localized_label("No local test has run.")
        self.onboarding_test_status.setWordWrap(True)
        daemon_layout.addWidget(self.onboarding_test_status)
        wizard.addPage(daemon_page)

        wizard.accepted.connect(self.complete_onboarding)
        wizard.open()

    def open_mutagen_install_guide(self) -> None:
        QDesktopServices.openUrl(QUrl("https://mutagen.io/documentation/introduction/installation"))

    def choose_onboarding_cli(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Select Mutagen executable", active_language()),
            str(Path.home()),
            translate_text("All files (*)", active_language()),
        )
        if not path:
            return
        candidate = MutagenClient(path)
        if not candidate.binary:
            set_localized_text(
                self.onboarding_cli_status, "That file is not an available Mutagen executable."
            )
            return
        self._onboarding_pending_client = candidate
        self.onboarding_cli_status.setText(
            f"Selected CLI: {candidate.binary}. Choose Check detected CLI to read its version and capabilities."
        )

    def check_onboarding_cli(self) -> None:
        client = self._onboarding_pending_client or self.client
        if not client.binary:
            set_localized_text(
                self.onboarding_cli_status,
                "Mutagen CLI was not found. Select its executable or open the official installation guide.",
            )
            return
        set_localized_text(
            self.onboarding_cli_status, "Checking CLI version and command capabilities…"
        )
        self.submit(lambda: inspect_cli(client), self.show_onboarding_cli_result)

    def show_onboarding_cli_result(self, result: CLIDiscovery) -> None:
        capabilities = ", ".join(result.capabilities) or "no session commands confirmed"
        binary_architecture = ", ".join(result.architectures) or "Unknown"
        detail = (
            f"{result.version or result.error}\n"
            f"Path: {result.binary or 'not found'}\n"
            f"{translate_text('Binary architecture', active_language())}: {binary_architecture}\n"
            f"{translate_text('Host architecture', active_language())}: {host_architecture()}\n"
            f"Capabilities: {capabilities}"
        )
        if result.error and result.version:
            detail += f"\nSome help checks failed: {result.error}"
        self.onboarding_cli_status.setText(detail)

    def run_onboarding_local_test(self) -> None:
        client = self._onboarding_pending_client or self.client
        if not client.binary:
            set_localized_text(
                self.onboarding_test_status,
                "Select or install the Mutagen CLI before running the local test.",
            )
            return
        set_localized_text(
            self.onboarding_test_status, "Running a disposable local-only sync test…"
        )
        self.submit(
            lambda: run_isolated_local_sync_test(client),
            self.onboarding_test_status.setText,
            on_error=lambda message: self.onboarding_test_status.setText(
                translate_text("Test failed: {message}", active_language()).format(message=message)
            ),
        )

    def complete_onboarding(self) -> None:
        previous_update_preference = bool(self.conf.get("check_updates_on_startup", False))
        if self._onboarding_pending_client is not None:
            self.client = self._onboarding_pending_client
            self.conf["binary"] = self.client.binary
            if hasattr(self, "binary_edit"):
                self.binary_edit.setText(self.client.binary)
        self.conf["onboarding_completed"] = True
        update_check = getattr(self, "onboarding_update_check", None)
        if update_check is not None:
            self.conf["check_updates_on_startup"] = update_check.isChecked()
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.statusBar().showMessage(
                translate_text(
                    "Could not save onboarding status: {error}", active_language()
                ).format(error=exc),
                10000,
            )
            self.conf["onboarding_completed"] = False
            self.conf["check_updates_on_startup"] = previous_update_preference

    def set_ui_mode(self, mode: str) -> None:
        self.preferences_controller.set_ui_mode(mode)

    def apply_theme(self, theme: str) -> None:
        self.preferences_controller.apply_theme(theme)

    def apply_ui_language(self, language: str) -> None:
        self.preferences_controller.apply_ui_language(language)

    def create_ui(self) -> None:
        root = QWidget()
        root.setObjectName("main")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(251)
        sidelay = QVBoxLayout(sidebar)
        sidelay.setContentsMargins(18, 24, 18, 18)
        sidelay.setSpacing(7)
        logorow = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self.make_icon().pixmap(39, 39))
        logorow.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(label("MUTAGEN", size=19, bold=True))
        titles.addWidget(label("CONTROL  /  SERVER MANAGER", muted=True, size=10))
        logorow.addLayout(titles)
        logorow.addStretch()
        sidelay.addLayout(logorow)
        sidelay.addSpacing(17)
        nav_scroller = QScrollArea()
        nav_scroller.setObjectName("navscroll")
        nav_scroller.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroller.setWidgetResizable(True)
        nav_scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_content = QWidget()
        nav_content.setObjectName("navcontent")
        nav_layout = QVBoxLayout(nav_content)
        nav_layout.setContentsMargins(0, 0, 2, 0)
        nav_layout.setSpacing(4)
        self.nav = []
        self.nav_section_labels = {}
        for i, route in enumerate(PAGE_ROUTES):
            if route.section:
                nav_layout.addSpacing(12 if i else 1)
                section_label = label(route.section, muted=True, size=10)
                nav_layout.addWidget(section_label)
                self.nav_section_labels[route.route_id] = section_label
            b = button(
                f"{route.glyph}    {translate_route(route.route_id, 'title', self.ui_language, route.title)}",
                partial(self.set_page, i),
                kind="nav",
            )
            b.setCheckable(True)
            b.setMinimumHeight(37)
            b.setToolTip(
                translate_route(route.route_id, "tooltip", self.ui_language, route.tooltip)
            )
            nav_layout.addWidget(b)
            self.nav.append(b)
        nav_layout.addStretch()
        nav_scroller.setWidget(nav_content)
        sidelay.addWidget(nav_scroller, 1)
        statecard = QFrame()
        statecard.setObjectName("inner")
        sc = QVBoxLayout(statecard)
        sc.setContentsMargins(15, 15, 15, 15)
        sc.addWidget(label("MUTAGEN STATUS", muted=True, size=10))
        self.side_state = label("●  Checking…", bold=True)
        sc.addWidget(self.side_state)
        self.side_sub = label("Waiting for first update", muted=True, size=11)
        self.side_sub.setWordWrap(True)
        sc.addWidget(self.side_sub)
        sidelay.addWidget(statecard)
        # Footer row: version on left, keyboard shortcut hint on right
        footer_row = QHBoxLayout()
        footer_row.setSpacing(4)
        footer_row.addWidget(label("v8.2", muted=True, size=10))
        footer_row.addStretch()
        nav_hint = label("Ctrl+K  navigation", muted=True, size=10)
        set_localized_tooltip(nav_hint, "Ctrl+K — quick navigation between pages")
        footer_row.addWidget(nav_hint)
        sidelay.addLayout(footer_row)
        outer.addWidget(sidebar)
        content = QWidget()
        content.setObjectName("main")
        cr = QVBoxLayout(content)
        cr.setContentsMargins(31, 26, 31, 18)
        cr.setSpacing(18)
        topline = QHBoxLayout()
        titlearea = QVBoxLayout()
        titlearea.setSpacing(3)
        self.page_name = label("Overview", size=25, bold=True)
        self.page_caption = label("Manage Mutagen in one place", muted=True)
        titlearea.addWidget(self.page_name)
        titlearea.addWidget(self.page_caption)
        topline.addLayout(titlearea)
        topline.addStretch()
        self.mode_selector = QComboBox()
        set_localized_accessible_name(self.mode_selector, "Interface mode")
        for mode in ("basic", "advanced"):
            self.mode_selector.addItem(translate(f"mode.{mode}", self.ui_language), mode)
        self.mode_selector.setCurrentIndex(0)
        self.mode_selector.currentIndexChanged.connect(
            lambda _index: self.set_ui_mode(self.mode_selector.currentData())
        )
        topline.addWidget(self.mode_selector)
        self.updated = label("Not updated", muted=True, size=11)
        topline.addWidget(self.updated)
        nav_btn = button("⌕  Go  Ctrl+K", self.open_navigator)
        set_localized_tooltip(nav_btn, "Ctrl+K — Quick navigation: go to any page")
        topline.addWidget(nav_btn)
        self.refresh_btn = button("↻  Refresh Status", lambda: self.refresh(force=True))
        set_localized_tooltip(
            self.refresh_btn, "Ctrl+R or F5 — Force immediate status refresh from Mutagen"
        )
        topline.addWidget(self.refresh_btn)
        cr.addLayout(topline)
        self.pages = LazyStackedWidget()
        cr.addWidget(self.pages, 1)
        page_builders: tuple[Callable[[], QWidget], ...] = (
            self.dashboard_page,
            partial(self.sessions_page, "sync"),
            partial(self.sessions_page, "forward"),
            self.logs_page,
            self.daemon_page,
            self.settings_page,
            self.monitoring_page,
            self.diagnostics_page,
            self.alerts_page,
            self.endpoints_page,
            self.servers_page,
        )
        for index, factory in enumerate(page_builders):
            if index == 5:
                self.pages.add_lazy_page(factory)
            else:
                self.pages.addWidget(factory())
        bottom = QHBoxLayout()
        self.footer = label("Mutagen CLI  /  local connection", muted=True, size=11)
        bottom.addWidget(self.footer)
        bottom.addStretch()
        self.writer_status = label("History: waiting for samples", muted=True, size=10)
        bottom.addWidget(self.writer_status)
        bottom.addSpacing(15)
        bottom.addWidget(label("CPU/RAM = all local Mutagen processes", muted=True, size=11))
        cr.addLayout(bottom)
        outer.addWidget(content, 1)
        self.set_page(0)

    def open_navigator(self) -> None:
        commands: list[tuple[str, str | None, str | None, str, str]] = [
            ("doctor", None, None, "Open Doctor", "health diagnostics"),
            ("open_project", None, None, "Open native project…", "mutagen yaml project"),
        ]
        for kind, sessions in (("sync", self.snapshot.sync), ("forward", self.snapshot.forward)):
            for session in sessions:
                if not isinstance(session, dict) or not isinstance(session.get("identifier"), str):
                    continue
                identifier = session["identifier"]
                title = str(session.get("name") or identifier)
                search_terms = [identifier, title]
                for endpoint_key in ("alpha", "beta", "source", "destination"):
                    endpoint = session.get(endpoint_key)
                    if isinstance(endpoint, str):
                        search_terms.append(endpoint)
                    elif isinstance(endpoint, dict):
                        search_terms.extend(
                            str(endpoint[key])
                            for key in ("name", "path", "host", "address")
                            if endpoint.get(key)
                        )
                tags = session.get("tags")
                if isinstance(tags, (list, tuple, set)):
                    search_terms.extend(str(tag) for tag in tags)
                searchable = " ".join(search_terms)
                commands.append(
                    ("focus_session", kind, identifier, f"Focus {kind}: {title}", searchable)
                )
                if (
                    kind == "sync"
                    and not session.get("paused")
                    and not self.demo
                    and not self.pending_action
                    and not self.snapshot.sessions_stale
                ):
                    commands.append(
                        ("flush_session", kind, identifier, f"Flush sync: {title}", searchable)
                    )
        dialog = QuickNavigator(self, commands=commands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.command is not None:
            command, kind, identifier = dialog.command
            if command == "doctor":
                self.set_page(7)
            elif command == "open_project":
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    translate_text("Open project", active_language()),
                    "",
                    translate_text(
                        "Mutagen projects (mutagen.yml mutagen.yaml)", active_language()
                    ),
                )
                if path:
                    self.handle_launch_request({"command": "open_project", "path": path})
            elif command in {"focus_session", "flush_session"}:
                self.focus_session_from_navigator(kind, identifier)
                if command == "flush_session":
                    self.session_action("sync", "flush")
        elif dialog.target is not None:
            self.set_page(dialog.target)

    def focus_session_from_navigator(self, kind: str, identifier: str) -> None:
        if kind not in {"sync", "forward"} or not identifier:
            return
        self.set_page(1 if kind == "sync" else 2)
        table = self.sync_table if kind == "sync" else self.forward_table
        search = self.sync_search if kind == "sync" else self.forward_search
        state_filter = self.sync_state_filter if kind == "sync" else self.forward_state_filter
        favorites_only = self.sync_favorites_only if kind == "sync" else self.forward_favorites_only
        search.clear()
        state_filter.setCurrentIndex(0)
        favorites_only.setChecked(False)
        if kind == "sync":
            self.sync_server_filter.setCurrentIndex(0)
        self.filter_table(kind, "")
        row = table.model().row_for_identifier(identifier)
        if row >= 0:
            table.selectRow(row)
            table.scrollTo(table.model().index(row, 0))

    def set_page(self, index: int) -> None:
        route = PAGE_ROUTES[index]
        self.pages.setCurrentIndex(index)
        self.page_name.setText(
            translate_route(route.route_id, "title", self.ui_language, route.title)
        )
        self.page_caption.setText(
            translate_route(route.route_id, "caption", self.ui_language, route.caption)
        )
        for i, b in enumerate(self.nav):
            b.setChecked(i == index)
        if index in (0, 6):
            self.refresh_charts(force=True)
        if index == 6 and hasattr(self, "process_table"):
            self.fill_processes(self.sampler.last_processes if not self.demo else [])
        if index == 9 and hasattr(self, "endpoint_combo"):
            self.update_endpoint_details()
        if index == 7 and hasattr(self, "diagnostics_view"):
            self.update_diagnostics(self.snapshot)
        if index == 10 and hasattr(self, "server_selector"):
            self.update_server_details()
        if index in (1, 2) and hasattr(self, "sync_details"):
            self.refresh_detail("sync" if index == 1 else "forward")

    def dashboard_page(self) -> QScrollArea:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        l = QVBoxLayout(body)
        l.setContentsMargins(0, 3, 2, 12)
        l.setSpacing(19)
        hero, hl = card()
        hero.setStyleSheet(
            "QFrame#card {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #152F35,stop:1 #13212F); border:1px solid #28665D; border-radius:16px; color:#EDF4F6;}"
            "QFrame#card QLabel {color:#EDF4F6;}"
            "QFrame#card QLabel#muted {color:#B9C9D0;}"
        )
        htop = QHBoxLayout()
        textblock = QVBoxLayout()
        textblock.setSpacing(6)
        eyebrow = QHBoxLayout()
        eyebrow.setSpacing(10)
        eyebrow.addWidget(label("MUTAGEN ENGINE  /  LIVE STATUS", size=11, bold=True))
        self.hero_badge = label("", size=10)
        self.hero_badge.setStyleSheet(
            f"color:{TEAL}; font-size:10px; font-weight:700; "
            f"background:#1A3A32; border:1px solid #2D6B5A; border-radius:5px; padding:1px 6px;"
        )
        eyebrow.addWidget(self.hero_badge)
        eyebrow.addStretch()
        textblock.addLayout(eyebrow)
        self.hero_title = label("Checking connection…", size=22, bold=True)
        textblock.addWidget(self.hero_title)
        self.hero_sub = label("Checking daemon and active session status", muted=True)
        textblock.addWidget(self.hero_sub)
        htop.addLayout(textblock, 1)
        daemon_btn = button("Manage Daemon  →", partial(self.set_page, 4))
        set_localized_tooltip(daemon_btn, "Go to the Daemon page to start, stop, or register it")
        htop.addWidget(daemon_btn)
        self.health_ring = HealthRing(hero)
        set_localized_tooltip(self.health_ring, "Share of sessions with no reported issues")
        htop.addWidget(self.health_ring)
        hl.addLayout(htop)
        l.addWidget(hero)
        metrics = QHBoxLayout()
        metrics.setSpacing(14)
        self.metric_widgets = {}
        for key, title, note, color in [
            ("all", "Total Sessions", "Sync + forwards", TEXT),
            ("running", "Active", "Connected / working", TEAL),
            ("paused", "Paused", "Paused manually", AMBER),
            ("errors", "Issues", "Needs attention", RED),
        ]:
            f, c = card()
            c.addWidget(label(title, muted=True, size=11))
            val = localized_button("—")
            val.setObjectName("metricValue")
            val.setCursor(Qt.CursorShape.PointingHandCursor)
            val.setAccessibleName(f"{title}. Open matching sessions")
            set_localized_tooltip(val, "Choose Sync or Forwarding sessions")
            val.setStyleSheet(
                f"QPushButton#metricValue {{ color:{color}; font-size:28px; font-weight:800; "
                "background:transparent; border:1px solid transparent; border-radius:7px; padding:2px 0; text-align:left; }"
                f"QPushButton#metricValue:hover {{ background:#1A263A; border-color:{BORDER}; }}"
                f"QPushButton#metricValue:focus {{ border-color:{BLUE}; }}"
            )
            val.clicked.connect(lambda _checked=False, k=key: self.show_metric_menu(k))
            c.addWidget(val)
            note_label = label(note + " · click to open", muted=True, size=10)
            note_label.setWordWrap(True)
            c.addWidget(note_label)
            self.metric_widgets[key] = val
            metrics.addWidget(f, 1)
        l.addLayout(metrics)
        graphs = QHBoxLayout()
        graphs.setSpacing(14)
        cpu_card, self.cpu_chart, self.cpu_value = self.graph_card("CPU", "%", BLUE)
        mem_card, self.mem_chart, self.mem_value = self.graph_card("RAM", "MB", TEAL)
        # Keep the C++ owner (QFrame) alive until Qt takes ownership via addWidget.
        # Fetching graph.parentWidget() from a discarded Python frame caused
        # libshiboken: Internal C++ object (Graph) already deleted on Windows.
        graphs.addWidget(cpu_card, 1)
        graphs.addWidget(mem_card, 1)
        l.addLayout(graphs)
        l.addWidget(
            button("▥  Open full monitoring and graph history →", partial(self.set_page, 6))
        )
        recent, rr = card()
        titlebar = QHBoxLayout()
        titlebar.addWidget(label("Sync Sessions", size=16, bold=True))
        titlebar.addStretch()
        titlebar.addWidget(button("All Sync Sessions →", partial(self.set_page, 1)))
        rr.addLayout(titlebar)
        self.dashboard_table = self.make_session_table(
            ["NAME", "STATUS", "ALPHA", "BETA"],
            height=240,
            stretch_columns=(0, 2, 3),
            dashboard=True,
        )
        set_localized_tooltip(self.dashboard_table, "Double-click to view sync details")
        rr.addWidget(self.dashboard_table)
        self.dashboard_table.doubleClicked.connect(
            lambda index: self.dashboard_select(index.row(), index.column())
        )
        # Forward sessions summary row
        fwd_row = QHBoxLayout()
        fwd_row.addWidget(label("Forwarding:", muted=True, size=11))
        self.dashboard_forward_summary = label("—", size=11)
        fwd_row.addWidget(self.dashboard_forward_summary)
        fwd_row.addStretch()
        fwd_row.addWidget(button("All Forwarding Sessions →", partial(self.set_page, 2)))
        rr.addLayout(fwd_row)
        l.addWidget(recent)
        l.addStretch()
        page.setWidget(body)
        return page

    def show_metric_menu(self, metric_key: str) -> None:
        sessions_by_kind = {"sync": self.snapshot.sync, "forward": self.snapshot.forward}
        metric_titles = {
            "all": "All sessions",
            "running": "Active / working",
            "paused": "Paused",
            "errors": "Issues",
        }
        state_sets = {"running": {"active", "busy"}, "paused": {"paused"}, "errors": {"error"}}
        menu = QMenu(self)
        for kind, title in (("sync", "Sync"), ("forward", "Forwarding")):
            sessions = sessions_by_kind[kind]
            wanted = state_sets.get(metric_key)
            count = sum(not wanted or classify(session, kind)[0] in wanted for session in sessions)
            action = menu.addAction(f"{title} · {count} {metric_titles[metric_key].lower()}")
            if action is not None:
                action.triggered.connect(
                    lambda _checked=False, k=kind, m=metric_key: self.open_metric_sessions(k, m)
                )
        button = self.metric_widgets[metric_key]
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def open_metric_sessions(self, kind: str, metric_key: str) -> None:
        self.set_page(1 if kind == "sync" else 2)
        filters = self.sync_state_filter if kind == "sync" else self.forward_state_filter
        search = self.sync_search if kind == "sync" else self.forward_search
        favorites = self.sync_favorites_only if kind == "sync" else self.forward_favorites_only
        if kind == "sync":
            self.sync_server_filter.setCurrentIndex(0)
        search.clear()
        favorites.setChecked(False)
        previous = filters.blockSignals(True)
        filters.setCurrentIndex({"all": 0, "running": 3, "paused": 4, "errors": 5}[metric_key])
        filters.blockSignals(previous)
        self.filter_table(kind)

    def session_state_filter_changed(self, kind: str) -> None:
        self.filter_table(kind)

    def graph_card(self, title: str, suffix: str, color: str) -> tuple[QFrame, Graph, QLabel]:
        f, vl = card()
        top = QHBoxLayout()
        top.addWidget(label(title + " · Mutagen procesy", muted=True, size=12))
        top.addStretch()
        value = label("—", size=20, bold=True)
        value.setStyleSheet(f"color:{color};font-size:20px;font-weight:700")
        top.addWidget(value)
        vl.addLayout(top)
        graph = Graph(color, f, unit="percent" if suffix == "%" else "memory")
        graph.setMinimumHeight(165)
        vl.addWidget(graph)
        footer = QHBoxLayout()
        footer.addWidget(label("History since launch · current value", muted=True, size=10))
        footer.addStretch()
        footer.addWidget(label("▥  Monitoring →", muted=True, size=10))
        vl.addLayout(footer)
        return f, graph, value

    def make_table(
        self, headers: Sequence[str], height: int = 370, *, stretch_columns: Iterable[int] = ()
    ) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        set_localized_accessible_name(table, "Data table")
        for column, source_header in enumerate(headers):
            header_item = QTableWidgetItem(translate_text(source_header, active_language()))
            header_item.setData(_LOCALIZED_ITEM_ROLE, source_header)
            table.setHorizontalHeaderItem(column, header_item)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        stretch_columns = set(stretch_columns)
        for column in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if column in stretch_columns
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(column, mode)
        table.setMinimumHeight(height)
        table.setSortingEnabled(True)
        header.setMinimumSectionSize(85)
        table.setWordWrap(False)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return table

    def make_session_table(
        self,
        headers: Sequence[str],
        height: int = 370,
        *,
        stretch_columns: Iterable[int] = (),
        kind: str = "sync",
        dashboard: bool = False,
    ) -> QTableView:
        table = QTableView()
        set_localized_accessible_name(
            table,
            "Forwarding sessions table" if kind == "forward" else "Sync sessions table",
        )
        model = SessionTableModel(headers, kind, dashboard=dashboard, parent=table)
        table.setModel(model)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(46)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column in range(len(headers)):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if column in set(stretch_columns)
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(column, mode)
        table.setMinimumHeight(height)
        table.setSortingEnabled(True)
        header.setMinimumSectionSize(85)
        table.setWordWrap(False)
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        return table

    def sessions_page(self, kind: str) -> QScrollArea:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget()
        root.setObjectName("scrollbody")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 3, 6, 12)
        layout.setSpacing(16)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        top, tl = card()
        row = QHBoxLayout()
        row.addWidget(label("SESSION MANAGER", muted=True, size=11))
        row.addStretch()
        new_btn = button(
            "+  New Sync" if kind == "sync" else "+  New Forward",
            partial(self.create_session, kind),
            kind="primary",
        )
        set_localized_tooltip(new_btn, "Ctrl+N — Create a session with the wizard")
        row.addWidget(new_btn)
        tl.addLayout(row)
        summary = label("No sessions loaded yet", muted=True)
        tl.addWidget(summary)
        if kind == "forward":
            forwarding_help = label(
                "Forwarding carries network connections between two endpoints, for example from your "
                "computer to a service on a server or container. It does not sync files.",
                muted=True,
                size=11,
            )
            forwarding_help.setWordWrap(True)
            tl.addWidget(forwarding_help)
        bulk_row = QHBoxLayout()
        if kind == "sync":
            sync_now_btn = button(
                "↻ Sync now · all",
                partial(self.bulk_action, "sync", "flush", "all"),
                kind="primary",
            )
            set_localized_tooltip(
                sync_now_btn, "Starts a sync cycle for all active (unpaused) sessions"
            )
            bulk_row.addWidget(sync_now_btn)
        pause_btn = button("⏸ Pause All", partial(self.bulk_action, kind, "pause", "all"))
        set_localized_tooltip(pause_btn, "Pauses all active sessions of this type")
        bulk_row.addWidget(pause_btn)
        resume_btn = button("▶ Resume All", partial(self.bulk_action, kind, "resume", "all"))
        set_localized_tooltip(resume_btn, "Resumes all paused or errored sessions")
        bulk_row.addWidget(resume_btn)
        bulk_row.addStretch()
        tl.addLayout(bulk_row)
        layout.addWidget(top)
        table_frame, table_l = card()
        header = QHBoxLayout()
        header.addWidget(label("Current Sessions", size=16, bold=True))
        header.addWidget(label("Select a row for details", muted=True, size=10))
        header.addStretch()
        search = QLineEdit()
        set_localized_placeholder(search, "Search by name / path…")
        search.setMaximumWidth(300)
        set_localized_tooltip(search, "Filters table rows by endpoint name or path")
        search.textChanged.connect(partial(self.filter_table, kind))
        header.addWidget(search)
        filter_row = QHBoxLayout()
        if kind == "sync":
            self.sync_server_filter = QComboBox()
            add_localized_item(self.sync_server_filter, "All Servers", "__all__")
            self.sync_server_filter.setMinimumWidth(155)
            set_localized_tooltip(self.sync_server_filter, "Filter by remote host")
            self.sync_server_filter.currentIndexChanged.connect(
                lambda _=None: self.filter_table("sync")
            )
            filter_row.addWidget(self.sync_server_filter)
        states = QComboBox()
        add_localized_items(
            states,
            [
                "All Statuses",
                "Active",
                "Working",
                "Active / Working",
                "Paused",
                "Issue",
                "Disconnected",
            ],
        )
        states.setMinimumWidth(140)
        set_localized_tooltip(states, "Filter sessions by current status")
        states.currentIndexChanged.connect(
            lambda _=None, k=kind: self.session_state_filter_changed(k)
        )
        filter_row.addWidget(states)
        favorites_only = localized_checkbox("★ Favorites")
        set_localized_tooltip(favorites_only, "Show only sessions marked as favorites")
        favorites_only.toggled.connect(lambda _checked, k=kind: self.filter_table(k))
        filter_row.addWidget(favorites_only)
        filter_row.addStretch()
        table_l.addLayout(header)
        table_l.addLayout(filter_row)
        if kind == "sync":
            self.sync_favorites_only = favorites_only
        else:
            self.forward_favorites_only = favorites_only
        if kind == "sync":
            self.sync_state_filter = states
        else:
            self.forward_state_filter = states
        if kind == "sync":
            self.sync_search = search
        else:
            self.forward_search = search
        fields = (
            ["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"]
            if kind == "sync"
            else ["NAME", "STATUS", "SOURCE", "DESTINATION", "CONNECTION"]
        )
        table = self.make_session_table(fields, 225, stretch_columns=(0, 2, 3), kind=kind)
        table.selectionModel().selectionChanged.connect(lambda *_args, k=kind: self.on_select(k))
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda point, k=kind: self.session_context_menu(k, point)
        )
        table.setMinimumHeight(0)
        table.setMaximumHeight(16777215)
        table_l.addWidget(table)
        layout.addWidget(table_frame)
        detail, dl = card()
        hd = QHBoxLayout()
        detail_title = label("Select a session", size=16, bold=True)
        hd.addWidget(detail_title)
        hd.addStretch()
        detail_tag = label("", muted=True)
        hd.addWidget(detail_tag)
        dl.addLayout(hd)
        details = localized_label("Session details and controls appear after you select a session.")
        details.setTextFormat(Qt.TextFormat.RichText)
        details.setWordWrap(True)
        details.setObjectName("muted")
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.setMinimumHeight(85)
        details.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        dl.addWidget(details)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setTextVisible(True)
        progress.setVisible(False)
        dl.addWidget(progress)
        utility_controls = QHBoxLayout()
        favorite_button = button("☆ Add to Favorites", partial(self.toggle_favorite, kind))
        favorite_button.setEnabled(False)
        utility_controls.addWidget(favorite_button)
        utility_controls.addWidget(button("Copy ID", partial(self.copy_session_id, kind)))
        utility_controls.addWidget(button("Export JSON", partial(self.export_session_json, kind)))
        utility_controls.addStretch()
        dl.addLayout(utility_controls)
        if kind == "sync":
            self.sync_autostart_button = button(
                "Start at sign-in: checking…", self.toggle_sync_startup
            )
            set_localized_tooltip(
                self.sync_autostart_button,
                "Uses native pause/resume and daemon registration; turning this off pauses sync immediately.",
            )
            startup_line = QHBoxLayout()
            startup_line.addWidget(self.sync_autostart_button)
            startup_line.addStretch()
            dl.addLayout(startup_line)
            note = label(
                "Automatic session start means the daemon starts at sign-in and the session is not paused. "
                "Turning off auto-start pauses it now; no additional service is needed.",
                muted=True,
                size=10,
            )
            note.setWordWrap(True)
            dl.addWidget(note)
        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(10)
        control_buttons = {}
        actions = (
            [
                ("pause", "⏸  Pause"),
                ("resume", "▶  Resume"),
                ("flush", "↻  Sync now"),
                ("reset", "Reset History"),
                ("terminate", "Terminate Session"),
            ]
            if kind == "sync"
            else [
                ("pause", "⏸  Pause"),
                ("resume", "▶  Resume"),
                ("terminate", "Terminate Session"),
            ]
        )
        for pos, (action, text) in enumerate(actions):
            b = button(
                text,
                partial(self.session_action, kind, action),
                kind="danger" if action in ("terminate", "reset") else "",
            )
            b.setEnabled(False)
            controls.addWidget(b, pos // 3, pos % 3)
            control_buttons[action] = b
        dl.addLayout(controls)
        session_prefs = button("⚙ Session Settings", partial(self.open_session_preferences, kind))
        utility_controls.insertWidget(0, session_prefs)
        layout.addWidget(detail)
        layout.addStretch(1)
        if kind == "sync":
            self.sync_table, self.sync_summary = table, summary
            self.sync_details, self.sync_title, self.sync_tag = details, detail_title, detail_tag
            self.sync_controls = control_buttons
            self.sync_progress = progress
            self.sync_favorite_button = favorite_button
            self.sync_preferences_button = session_prefs
        else:
            self.forward_table, self.forward_summary = table, summary
            self.forward_details, self.forward_title, self.forward_tag = (
                details,
                detail_title,
                detail_tag,
            )
            self.forward_controls = control_buttons
            self.forward_progress = progress
            self.forward_favorite_button = favorite_button
            self.forward_preferences_button = session_prefs
        page.setWidget(root)
        return page

    def logs_page(self) -> QScrollArea:
        root = QWidget()
        root.setObjectName("main")
        l = QVBoxLayout(root)
        l.setContentsMargins(0, 3, 0, 0)
        l.setSpacing(12)
        f, c = card()
        row = QHBoxLayout()
        row.addWidget(label("Live Session and Application Events", size=16, bold=True))
        row.addStretch()
        self.log_count_label = label("0 entries", muted=True, size=11)
        row.addWidget(self.log_count_label)
        export_logs_btn = button("Save .txt", self.export_logs)
        set_localized_tooltip(export_logs_btn, "Save displayed entries to a text file")
        row.addWidget(export_logs_btn)
        clear_logs_btn = button("Clear", self.clear_logs)
        set_localized_tooltip(
            clear_logs_btn, "Clears entries from this view (does not delete database history)"
        )
        row.addWidget(clear_logs_btn)
        c.addLayout(row)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setPlainText("\n".join(self.logs))
        self.log_view.setStyleSheet(
            f"font-family: Consolas, monospace; font-size:12px; background:#0A1421; color:{TEXT};"
        )
        c.addWidget(self.log_view)
        l.addWidget(f, 1)
        logbox, contents = card()
        row = QHBoxLayout()
        row.addWidget(label("Live Log — File Tracking", size=16, bold=True))
        row.addStretch()
        choose_btn = button("Select Log…", self.choose_tail_file, kind="primary")
        set_localized_tooltip(
            choose_btn, "Select a local log file to monitor in real time (read-only)"
        )
        row.addWidget(choose_btn)
        stop_btn = button("Stop", self.stop_tail_file)
        set_localized_tooltip(stop_btn, "Stops monitoring the current file")
        row.addWidget(stop_btn)
        export_btn = button("Export", self.export_tail_file)
        set_localized_tooltip(export_btn, "Save the currently displayed live log lines")
        row.addWidget(export_btn)
        contents.addLayout(row)
        self.tail_info = label("No log file selected.", muted=True, size=11)
        self.tail_info.setWordWrap(True)
        contents.addWidget(self.tail_info)
        filterline = QHBoxLayout()
        filterline.addWidget(label("Filter:", muted=True))
        self.tail_filter = QLineEdit()
        set_localized_placeholder(self.tail_filter, "Text to display in the log…")
        set_localized_tooltip(
            self.tail_filter, "Shows only lines containing the entered text (case-insensitive)"
        )
        self.tail_filter.textChanged.connect(self.render_tail)
        filterline.addWidget(self.tail_filter)
        self.follow_tail = localized_checkbox("Follow log end")
        self.follow_tail.setChecked(True)
        set_localized_tooltip(
            self.follow_tail, "Turn off to read older entries without automatic scrolling"
        )
        filterline.addWidget(self.follow_tail)
        self.tail_count_label = label("0 lines", muted=True, size=11)
        filterline.addWidget(self.tail_count_label)
        clear_tail_btn = button("Clear View", self.clear_tail)
        set_localized_tooltip(clear_tail_btn, "Clears displayed lines (the file remains unchanged)")
        filterline.addWidget(clear_tail_btn)
        contents.addLayout(filterline)
        self.tail_view = QPlainTextEdit()
        self.tail_view.setReadOnly(True)
        self.tail_view.setMaximumBlockCount(1200)
        self.tail_view.setStyleSheet(
            f"font-family: Consolas, monospace; font-size:12px; background:#0A1421; color:{TEXT};"
        )
        contents.addWidget(self.tail_view)
        l.addWidget(logbox, 1)
        note = label(
            "Live events above come from status changes reported by the local Mutagen daemon. "
            "This is not a complete internal debug log. You can optionally monitor an existing local "
            "log file without affecting the running daemon. The application does not start any logging process on the server.",
            muted=True,
            size=11,
        )
        note.setWordWrap(True)
        l.addWidget(note)
        return root

    def choose_tail_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Select a Continuously Updated Log", active_language()),
            "",
            translate_text("Text Logs (*.log *.txt);;All Files (*)", active_language()),
        )
        if not filename:
            return
        self.tail_file = FileTail(filename)
        self.tail_timer.start(900)
        self.tail_lines.clear()
        self.tail_info.setText("Monitoring read-only: " + filename)
        self.poll_tail()

    def stop_tail_file(self) -> None:
        self.tail_file = None
        self.tail_timer.stop()
        set_localized_text(self.tail_info, "Log monitoring stopped.")

    def clear_tail(self) -> None:
        self.tail_lines.clear()
        self.tail_view.clear()

    def poll_tail(self) -> None:
        if self.tail_file is None:
            return
        try:
            found = self.tail_file.poll()
        except OSError as exc:
            self.stop_tail_file()
            self.tail_info.setText("Could not read log: " + str(exc)[:200])
            return
        if not found:
            return
        self.tail_lines.extend(found)
        self.schedule_tail_render()

    def schedule_tail_render(self) -> None:
        """Merge bursts of debug output into one UI paint (~6 FPS at most)."""
        if not self._tail_render_pending:
            self._tail_render_pending = True
            QTimer.singleShot(160, self._render_pending_tail)

    def _render_pending_tail(self) -> None:
        self._tail_render_pending = False
        self.render_tail()

    def render_tail(self, *_: object) -> None:
        """Append only newly arrived matching lines; never reread Qt's full text.

        A filter change or explicit clear performs one full rebuild. Following
        the end is optional, so selecting an older error is not interrupted.
        """
        if not hasattr(self, "tail_view"):
            return
        term = self.tail_filter.text().casefold().strip()
        scrollbar = self.tail_view.verticalScrollBar()
        old_position = scrollbar.value()
        auto_follow = self.follow_tail.isChecked()
        reset = self._tail_render_epoch != self.tail_lines.epoch or self._tail_render_filter != term
        if reset:
            output = "\n".join(
                line for line in self.tail_lines if not term or term in line.casefold()
            )
            self.tail_view.setPlainText(output)
        else:
            addition = [
                line
                for line in self.tail_lines.since(self._tail_render_count)
                if not term or term in line.casefold()
            ]
            if addition:
                self.tail_view.appendPlainText("\n".join(addition))
        self._tail_render_epoch = self.tail_lines.epoch
        self._tail_render_filter = term
        self._tail_render_count = self.tail_lines.total
        scrollbar.setValue(scrollbar.maximum() if auto_follow else old_position)
        if hasattr(self, "tail_count_label"):
            n = self.tail_view.document().blockCount()
            self.tail_count_label.setText(
                f"{n} {'line' if n == 1 else 'lines' if 2 <= n <= 4 else 'lines'}"
            )

    def export_tail_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export Currently Displayed Live Log", active_language()),
            "mutagen-live-log.txt",
            translate_text("Text (*.txt)", active_language()),
        )
        if not path:
            return
        try:
            Path(path).write_text(self.tail_view.toPlainText() + "\n", encoding="utf-8")
        except OSError as exc:
            self.report_error(str(exc))

    def daemon_page(self) -> QScrollArea:
        root = QWidget()
        root.setObjectName("main")
        l = QVBoxLayout(root)
        l.setContentsMargins(0, 3, 0, 0)
        l.setSpacing(18)
        stat, sl = card()
        sl.addWidget(label("MUTAGEN DAEMON", muted=True, size=11))
        self.daemon_title = label("Checking daemon status…", size=22, bold=True)
        sl.addWidget(self.daemon_title)
        self.daemon_desc = label(
            "Status is checked through the CLI without starting the daemon automatically.",
            muted=True,
        )
        self.daemon_desc.setWordWrap(True)
        sl.addWidget(self.daemon_desc)
        l.addWidget(stat)
        actions, al = card()
        al.addWidget(label("Daemon Lifecycle", size=16, bold=True))
        r = QHBoxLayout()
        self.start_button = button(
            "▶  Start Daemon", partial(self.daemon_action, "start"), kind="primary"
        )
        set_localized_tooltip(
            self.start_button,
            "Starts the Mutagen daemon in the background with 'mutagen daemon start'",
        )
        self.stop_button = button(
            "■  Stop daemon", partial(self.daemon_action, "stop"), kind="danger"
        )
        set_localized_tooltip(
            self.stop_button,
            "Stops the daemon and interrupts all active sync and forwarding sessions",
        )
        r.addWidget(self.start_button)
        r.addWidget(self.stop_button)
        r.addStretch()
        al.addLayout(r)
        warning_lbl = label(
            "⚠  Stopping the daemon interrupts all its sync and forwarding sessions until it is restarted.",
            muted=True,
        )
        warning_lbl.setWordWrap(True)
        al.addWidget(warning_lbl)
        l.addWidget(actions)
        registry, reg = card()
        autostart_titles = {"win32": "Start Automatically at Windows Sign-In"}
        reg.addWidget(
            label(
                autostart_titles.get(sys.platform, "Daemon Autostart Configuration"),
                size=16,
                bold=True,
            )
        )
        autostart_descriptions = {
            "win32": (
                "Native daemon registration through the Mutagen CLI (HKCU Run). "
                "After sign-in, only unpaused sessions resume; paused sessions remain paused."
            ),
            "darwin": (
                "On macOS, Mutagen daemon can be launched via launchd user agents "
                "(~/Library/LaunchAgents). Mutagen CLI's built-in register command is Windows-only."
            ),
        }
        reg.addWidget(
            label(
                autostart_descriptions.get(
                    sys.platform,
                    "On Linux, Mutagen daemon can be managed via systemd user services "
                    "or XDG autostart. Mutagen CLI's built-in register command is Windows-only.",
                ),
                muted=True,
            )
        )
        row = QHBoxLayout()
        reg_btn = button("Register", partial(self.daemon_action, "register"), kind="primary")
        reg_tooltips = {
            "win32": "Adds the Mutagen daemon to Windows Run so it can start automatically at sign-in.",
        }
        set_localized_tooltip(
            reg_btn,
            reg_tooltips.get(
                sys.platform, "Built-in daemon register command is only supported on Windows."
            ),
        )
        reg_btn.setEnabled(sys.platform == "win32")
        row.addWidget(reg_btn)
        unreg_btn = button("Unregister", partial(self.daemon_action, "unregister"), kind="danger")
        unreg_tooltips = {
            "win32": "Removes daemon registration — the daemon will not start automatically at sign-in",
        }
        set_localized_tooltip(
            unreg_btn,
            unreg_tooltips.get(
                sys.platform, "Built-in daemon unregister command is only supported on Windows."
            ),
        )
        unreg_btn.setEnabled(sys.platform == "win32")
        row.addWidget(unreg_btn)
        row.addStretch()
        reg.addLayout(row)
        self.register_message = label("Registration: checking status…", muted=True)
        self.register_message.setWordWrap(True)
        reg.addWidget(self.register_message)
        # card() returns (QFrame, QVBoxLayout). Only the frame is a QWidget.
        # Passing reg (the QVBoxLayout) to addWidget() crashes on real PySide6.
        l.addWidget(registry)
        l.addStretch()
        return root

    def alerts_page(self) -> QScrollArea:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 3, 3, 15)
        outer.setSpacing(18)
        status, sl = card()
        sl.addWidget(label("Mutagen Resource Monitoring", size=17, bold=True))
        sl.addWidget(
            label(
                "An alert is triggered only after the threshold is exceeded continuously. "
                "Another alert is sent only after values fall below the limit and exceed it again.",
                muted=True,
            )
        )
        form = QFormLayout()
        form.setVerticalSpacing(15)
        self.cpu_alert_on = localized_checkbox("Alert on Sustained High CPU")
        self.cpu_alert_on.setChecked(bool(self.conf.get("cpu_alert_on", False)))
        self.cpu_alert_on.setToolTip(setting_tooltip("cpu_alert_on", self.ui_language))
        add_localized_row(form, "CPU", self.cpu_alert_on)
        self.cpu_alert_limit = QSpinBox()
        self.cpu_alert_limit.setRange(1, 1600)
        self.cpu_alert_limit.setSuffix(" %")
        self.cpu_alert_limit.setValue(int(self.conf.get("cpu_alert_limit", 90)))
        self.cpu_alert_limit.setToolTip(setting_tooltip("cpu_alert_limit", self.ui_language))
        add_localized_row(form, "CPU Limit (All Cores)", self.cpu_alert_limit)
        self.ram_alert_on = localized_checkbox("Alert on Sustained High RAM")
        self.ram_alert_on.setChecked(bool(self.conf.get("ram_alert_on", False)))
        self.ram_alert_on.setToolTip(setting_tooltip("ram_alert_on", self.ui_language))
        add_localized_row(form, "RAM", self.ram_alert_on)
        self.ram_alert_limit = QSpinBox()
        self.ram_alert_limit.setRange(64, 131072)
        self.ram_alert_limit.setSuffix(" MB")
        self.ram_alert_limit.setValue(int(self.conf.get("ram_alert_limit", 1024)))
        self.ram_alert_limit.setToolTip(setting_tooltip("ram_alert_limit", self.ui_language))
        add_localized_row(form, "RAM Limit", self.ram_alert_limit)
        self.alert_hold = QSpinBox()
        self.alert_hold.setRange(5, 600)
        self.alert_hold.setSuffix(" s")
        self.alert_hold.setValue(int(self.conf.get("alert_hold", 20)))
        self.alert_hold.setToolTip(setting_tooltip("alert_hold", self.ui_language))
        add_localized_row(form, "Threshold Duration", self.alert_hold)
        self.quiet_hours_enabled = localized_checkbox("Suppress notifications during quiet hours")
        self.quiet_hours_enabled.setChecked(bool(self.conf.get("quiet_hours_enabled", False)))
        add_localized_row(form, "Quiet Hours", self.quiet_hours_enabled)
        self.quiet_hours_start = QTimeEdit()
        self.quiet_hours_start.setDisplayFormat("HH:mm")
        self.quiet_hours_start.setTime(
            QTime.fromString(str(self.conf.get("quiet_hours_start", "22:00")), "HH:mm")
        )
        self.quiet_hours_start.setEnabled(self.quiet_hours_enabled.isChecked())
        self.quiet_hours_start.setToolTip(setting_tooltip("quiet_hours_start", self.ui_language))
        add_localized_row(form, "Quiet Hours Start", self.quiet_hours_start)
        self.quiet_hours_end = QTimeEdit()
        self.quiet_hours_end.setDisplayFormat("HH:mm")
        self.quiet_hours_end.setTime(
            QTime.fromString(str(self.conf.get("quiet_hours_end", "07:00")), "HH:mm")
        )
        self.quiet_hours_end.setEnabled(self.quiet_hours_enabled.isChecked())
        self.quiet_hours_end.setToolTip(setting_tooltip("quiet_hours_end", self.ui_language))
        add_localized_row(form, "Quiet Hours End", self.quiet_hours_end)
        self.quiet_hours_enabled.toggled.connect(self.quiet_hours_start.setEnabled)
        self.quiet_hours_enabled.toggled.connect(self.quiet_hours_end.setEnabled)
        sl.addLayout(form)
        sl.addWidget(button("Save Alert Rules", self.save_alert_rules, kind="primary"))
        outer.addWidget(status)
        health, hl = card()
        hl.addWidget(label("Session Health and Recovery Policy", size=17, bold=True))
        hl.addWidget(
            label(
                "Monitor-only is the default. Assisted mode can recommend a manual step. "
                "Auto-safe currently has no connected recovery action in this release slice.",
                muted=True,
            )
        )
        health_form = QFormLayout()
        health_form.setVerticalSpacing(12)
        self.health_mode = QComboBox()
        for title, value in (
            ("Monitor only", "monitor_only"),
            ("Assisted — manual recommendations", "assisted"),
            ("Auto-safe — status checks only", "auto_safe"),
        ):
            add_localized_item(self.health_mode, title, value)
        self.health_mode.setCurrentIndex(
            max(0, self.health_mode.findData(self.conf.get("health_mode", "monitor_only")))
        )
        self.health_mode.setToolTip(setting_tooltip("health_mode", self.ui_language))
        add_localized_row(health_form, "Mode", self.health_mode)
        self.health_failure_count = QSpinBox()
        self.health_failure_count.setRange(3, 10)
        self.health_failure_count.setValue(int(self.conf.get("health_failure_count", 3)))
        self.health_failure_count.setToolTip(
            setting_tooltip("health_failure_count", self.ui_language)
        )
        add_localized_row(health_form, "Confirmed failures", self.health_failure_count)
        self.health_failure_elapsed = QSpinBox()
        self.health_failure_elapsed.setRange(30, 900)
        self.health_failure_elapsed.setSuffix(" s")
        self.health_failure_elapsed.setValue(int(self.conf.get("health_failure_elapsed", 120)))
        self.health_failure_elapsed.setToolTip(
            setting_tooltip("health_failure_elapsed", self.ui_language)
        )
        add_localized_row(health_form, "Failure duration", self.health_failure_elapsed)
        self.health_cooldown = QSpinBox()
        self.health_cooldown.setRange(60, 3600)
        self.health_cooldown.setSuffix(" s")
        self.health_cooldown.setValue(int(self.conf.get("health_cooldown", 60)))
        self.health_cooldown.setToolTip(setting_tooltip("health_cooldown", self.ui_language))
        add_localized_row(health_form, "Recovery cooldown", self.health_cooldown)
        self.health_max_attempts = QSpinBox()
        self.health_max_attempts.setRange(1, 2)
        self.health_max_attempts.setValue(int(self.conf.get("health_max_attempts", 2)))
        self.health_max_attempts.setToolTip(
            setting_tooltip("health_max_attempts", self.ui_language)
        )
        add_localized_row(health_form, "Maximum attempts", self.health_max_attempts)
        self.health_attempt_window = QSpinBox()
        self.health_attempt_window.setRange(1800, 86400)
        self.health_attempt_window.setSuffix(" s")
        self.health_attempt_window.setValue(int(self.conf.get("health_attempt_window", 1800)))
        self.health_attempt_window.setToolTip(
            setting_tooltip("health_attempt_window", self.ui_language)
        )
        add_localized_row(health_form, "Attempt window", self.health_attempt_window)
        self.health_environment_grace = QSpinBox()
        self.health_environment_grace.setRange(30, 900)
        self.health_environment_grace.setSuffix(" s")
        self.health_environment_grace.setValue(int(self.conf.get("health_environment_grace", 120)))
        self.health_environment_grace.setToolTip(
            setting_tooltip("health_environment_grace", self.ui_language)
        )
        add_localized_row(health_form, "Sleep/network grace", self.health_environment_grace)
        hl.addLayout(health_form)
        hl.addWidget(button("Save Health Policy", self.save_alert_rules, kind="primary"))
        outer.addWidget(health)
        detail, dl = card()
        dl.addWidget(label("Current Values", size=16, bold=True))
        self.alert_runtime_label = label("Waiting for measurements…", muted=True)
        dl.addWidget(self.alert_runtime_label)
        dl.addWidget(
            label(
                "Alerts are recorded in Action History and can also appear as desktop notifications "
                "when a system tray is available. CPU/RAM values cover all local Mutagen processes.",
                muted=True,
            )
        )
        outer.addWidget(detail)
        updates, ul = card()
        ul.addWidget(label("Release updates", size=16, bold=True))
        ul.addWidget(
            label(
                "Save the setting to allow one GitHub Releases check at each startup. You can also check now. "
                "It sends only a public metadata request; it never downloads or installs updates.",
                muted=True,
            )
        )
        self.check_updates_on_startup = localized_checkbox("Check releases on startup")
        self.check_updates_on_startup.setChecked(
            bool(self.conf.get("check_updates_on_startup", False))
        )
        self.check_updates_on_startup.setToolTip(
            setting_tooltip("check_updates_on_startup", self.ui_language)
        )
        ul.addWidget(self.check_updates_on_startup)
        update_actions = QHBoxLayout()
        self.update_check_button = button("Check for updates now", self.check_for_release_update)
        self.update_check_button.setEnabled(
            self.check_updates_on_startup.isChecked() and not self.demo
        )
        self.save_update_preference_button = button(
            "Save release-check preference", self.save_release_check_preference
        )
        self.open_release_button = button("Open GitHub Releases", self.open_release_page)
        self.open_release_button.setVisible(False)
        update_actions.addWidget(self.save_update_preference_button)
        update_actions.addWidget(self.update_check_button)
        update_actions.addWidget(self.open_release_button)
        update_actions.addStretch()
        ul.addLayout(update_actions)
        self.update_status_label = label("Update status has not been checked.", muted=True)
        ul.addWidget(self.update_status_label)
        self.check_updates_on_startup.toggled.connect(
            lambda enabled: self.update_check_button.setEnabled(enabled and not self.demo)
        )
        outer.addWidget(updates)
        self.refresh_release_check_status()
        outer.addStretch()
        page.setWidget(body)
        return page

    def save_alert_rules(self) -> None:
        self.conf.update(
            cpu_alert_on=self.cpu_alert_on.isChecked(),
            cpu_alert_limit=self.cpu_alert_limit.value(),
            ram_alert_on=self.ram_alert_on.isChecked(),
            ram_alert_limit=self.ram_alert_limit.value(),
            alert_hold=self.alert_hold.value(),
            quiet_hours_enabled=self.quiet_hours_enabled.isChecked(),
            quiet_hours_start=self.quiet_hours_start.time().toString("HH:mm"),
            quiet_hours_end=self.quiet_hours_end.time().toString("HH:mm"),
            health_mode=self.health_mode.currentData(),
            health_failure_count=self.health_failure_count.value(),
            health_failure_elapsed=self.health_failure_elapsed.value(),
            health_cooldown=self.health_cooldown.value(),
            health_max_attempts=self.health_max_attempts.value(),
            health_attempt_window=self.health_attempt_window.value(),
            health_environment_grace=self.health_environment_grace.value(),
            check_updates_on_startup=self.check_updates_on_startup.isChecked(),
        )
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self.alert_engine = AlertEngine()  # Re-arm with new thresholds
        self.health_tracker.update_policy(self.health_policy_from_settings())
        self.add_log("Alert rules and health policy saved")

    def check_for_release_update_on_startup(self) -> None:
        if (
            not self.demo
            and self.conf.get("onboarding_completed", False)
            and self.conf.get("check_updates_on_startup", False)
        ):
            self.check_for_release_update(startup=True)

    def save_release_check_preference(self) -> None:
        self.conf["check_updates_on_startup"] = self.check_updates_on_startup.isChecked()
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self.add_log("Release-check preference saved")

    def check_for_release_update(self, *, startup: bool = False) -> None:
        if self.demo or self._release_check_running:
            return
        enabled = bool(self.conf.get("check_updates_on_startup", False))
        if not startup:
            enabled = bool(
                getattr(self, "check_updates_on_startup", None)
                and self.check_updates_on_startup.isChecked()
            )
        if not enabled:
            return
        self._release_check_running = True
        check_button = getattr(self, "update_check_button", None)
        if check_button is not None:
            check_button.setEnabled(False)
        if hasattr(self, "update_status_label"):
            self.update_status_label.setText(
                translate_text("Checking for releases…", self.ui_language)
            )
        self.submit(
            lambda: check_for_update(current_version=APP_VERSION, enabled=True),
            self._release_check_succeeded,
            self._release_check_failed,
            self._release_check_finished,
        )

    def _release_check_succeeded(self, result: UpdateCheckResult) -> None:
        self._release_check_result = result
        self._release_check_error = False
        self.refresh_release_check_status()

    def _release_check_failed(self, _message: str) -> None:
        self._release_check_result = None
        self._release_check_error = True
        self.refresh_release_check_status()

    def _release_check_finished(self) -> None:
        self._release_check_running = False
        check_button = getattr(self, "update_check_button", None)
        opt_in = getattr(self, "check_updates_on_startup", None)
        if check_button is not None and opt_in is not None:
            check_button.setEnabled(opt_in.isChecked() and not self.demo)
        self.refresh_release_check_status()

    def refresh_release_check_status(self) -> None:
        status_label = getattr(self, "update_status_label", None)
        if status_label is None:
            return
        result = self._release_check_result
        if self._release_check_running:
            message = translate_text("Checking for releases…", self.ui_language)
        elif self._release_check_error:
            message = translate_text("Release check failed. See GitHub Releases.", self.ui_language)
        elif result is None or result.latest_version is None:
            message = translate_text("Update status has not been checked.", self.ui_language)
        elif result.available:
            message = translate_text(
                "A newer release is available: v{version}.", self.ui_language
            ).format(version=result.latest_version)
        else:
            message = translate_text(
                "Latest published release: v{version}.", self.ui_language
            ).format(version=result.latest_version)
        status_label.setText(message)
        open_button = getattr(self, "open_release_button", None)
        if open_button is not None:
            open_button.setVisible(bool(result and result.available))

    def open_release_page(self) -> None:
        QDesktopServices.openUrl(QUrl(RELEASES_URL))

    def health_policy_from_settings(self) -> HealthPolicy:
        return health_policy_from_settings(self.conf)

    def _attach_health_network_monitor(self) -> None:
        attach_health_network_monitor_ui(self)

    def _health_network_changed(self, reachability: object) -> None:
        apply_health_network_change(self, reachability)

    def settings_page(self) -> QScrollArea:
        return build_settings_page(self)

    def browse_binary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Select mutagen.exe", active_language()),
            str(Path.home()),
            translate_text("Executable (*.exe);;All files (*)", active_language()),
        )
        if path:
            self.binary_edit.setText(path)

    def manage_ignore_presets(self) -> None:
        try:
            dialog = IgnorePresetManagerDialog(
                settings_path().with_name("ignore-presets.json"), self
            )
            dialog.exec()
        except (IgnorePresetError, OSError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Ignore Presets", active_language()),
                f"Could not open preset manager: {exc}",
            )

    def manage_native_projects(self) -> None:
        from mutaui.projects.native_project import ProjectStoreError

        try:
            dialog = NativeProjectManagerDialog(
                settings_path().with_name("mutagen-projects.json"),
                self,
                executor=LegacyMutagenExecutor(self.client) if self.client.binary else None,
                audit_path=settings_path().with_name("mutagen-project-actions.jsonl"),
                action_planner=self.action_planner,
            )
            dialog.exec()
        except (ProjectStoreError, OSError) as exc:
            QMessageBox.warning(
                self, translate_text("Native Mutagen Projects", active_language()), str(exc)
            )

    def manage_connection_profiles(self) -> None:
        profile_path = settings_path().with_name("connection-profiles.json")
        loaded = load_profile_store(profile_path)
        if not loaded.valid:
            QMessageBox.warning(
                self,
                translate_text("Connection Profiles Unavailable", active_language()),
                "The local profile file is invalid and was left unchanged.\n\n"
                + "\n".join(loaded.warnings),
            )
            return
        dialog = ConnectionProfilesDialog(self, ConnectionProfileStore(profile_path))
        dialog.exec()

    def manage_ssh_profiles(self) -> None:
        SSHProfileManagerDialog(self).exec()

    def export_portable_bundle(self) -> None:
        profile_path = settings_path().with_name("connection-profiles.json")
        loaded = load_profile_store(profile_path)
        if not loaded.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Export Unavailable", active_language()),
                "The local profile file is invalid and was left unchanged.\n\n"
                + "\n".join(loaded.warnings),
            )
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export Portable Bundle", active_language()),
            str(Path.home() / "mutaui-portable.json"),
            translate_text("JSON (*.json)", active_language()),
        )
        if not destination:
            return
        answer = QMessageBox.question(
            self,
            translate_text("Include machine-specific paths?", active_language()),
            translate_text(
                "Include absolute local endpoint paths? They may identify this computer or user. Choose No for the redacted portable export.",
                active_language(),
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return
        ignore_store = load_ignore_presets(settings_path().with_name("ignore-presets.json"))
        if not ignore_store.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Export Unavailable", active_language()),
                "The local ignore preset file is invalid and was left unchanged.\n\n"
                + "\n".join(ignore_store.warnings),
            )
            return
        result = build_bundle(
            list(loaded.profiles),
            load_settings(settings_path()).values,
            app_version="8.2",
            include_local_paths=answer == QMessageBox.StandardButton.Yes,
            ignore_presets=[preset_to_record(preset) for preset in ignore_store.presets],
        )
        if not result.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Export", active_language()),
                "\n".join(result.warnings),
            )
            return
        target = Path(destination)
        if target.exists():
            overwrite = QMessageBox.question(
                self,
                translate_text("Replace Portable Bundle", active_language()),
                f"Replace this file?\n\n{target}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if overwrite != QMessageBox.StandardButton.Yes:
                return
        temporary: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(result.text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            QMessageBox.information(
                self,
                translate_text("Portable Export", active_language()),
                f"Bundle saved: {target}\n\n"
                + (
                    "\n".join(result.warnings)
                    or "Absolute local paths were redacted; secrets were excluded."
                ),
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                translate_text("Portable Export", active_language()),
                f"Could not save bundle: {exc}",
            )
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def import_portable_bundle(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Import Portable Bundle", active_language()),
            str(Path.home()),
            translate_text("JSON (*.json);;All files (*)", active_language()),
        )
        if not source:
            return
        source_path = Path(source)
        try:
            if source_path.stat().st_size > 5 * 1024 * 1024:
                raise PortableBundleError("Portable bundle exceeds the 5 MiB size limit.")
            bundle = load_bundle(source_path.read_bytes())
        except (OSError, PortableBundleError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Portable Import", active_language()),
                f"Could not read bundle: {exc}",
            )
            return
        if not bundle.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Import", active_language()),
                "Bundle was not changed or imported:\n\n" + "\n".join(bundle.warnings),
            )
            return
        profile_path = settings_path().with_name("connection-profiles.json")
        current_profiles = load_profile_store(profile_path)
        if not current_profiles.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Import Unavailable", active_language()),
                "The local profile file is invalid and was left unchanged.\n\n"
                + "\n".join(current_profiles.warnings),
            )
            return
        store = ConnectionProfileStore(profile_path)
        ignore_path = settings_path().with_name("ignore-presets.json")
        ignore_state = load_ignore_presets(ignore_path)
        if not ignore_state.valid:
            QMessageBox.warning(
                self,
                translate_text("Portable Import Unavailable", active_language()),
                "The local ignore preset file is invalid and was left unchanged.\n\n"
                + "\n".join(ignore_state.warnings),
            )
            return
        ignore_store = IgnorePresetStore(ignore_path)
        preview = PortableImportPreviewDialog(self, bundle, store.profiles, ignore_store.presets)
        if preview.exec() != QDialog.DialogCode.Accepted:
            return
        prefs = bundle.data["items"]["preferences"]
        selected = preview.selected_preferences()
        ignore_choices = preview.ignore_choices()
        try:
            merged_settings = selected_preferences(
                load_settings(settings_path()).values, prefs, selected
            )
        except PortableBundleError as exc:
            QMessageBox.warning(
                self, translate_text("Portable Import", active_language()), str(exc)
            )
            return
        choices = preview.profile_choices()
        if (
            not selected
            and all(value == "skip" for value in choices.values())
            and all(value == "skip" for value in ignore_choices.values())
        ):
            QMessageBox.information(
                self,
                translate_text("Portable Import", active_language()),
                translate_text("Nothing selected; no files changed.", active_language()),
            )
            return
        answer = QMessageBox.question(
            self,
            translate_text("Apply Portable Import", active_language()),
            translate_text(
                "Apply selected local profiles, ignore presets, and preferences? Existing files get backups. Mutagen sessions, notes, history, and SSH files remain untouched.",
                active_language(),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            fresh_profiles = load_profile_store(profile_path)
            fresh_ignores = load_ignore_presets(ignore_path)
            if not fresh_profiles.valid or list(fresh_profiles.profiles) != store.profiles:
                raise PortableBundleError(
                    "Local connection profiles changed after preview; reload and review again."
                )
            if not fresh_ignores.valid or list(fresh_ignores.presets) != ignore_store.presets:
                raise PortableBundleError(
                    "Local ignore presets changed after preview; reload and review again."
                )
            merged_settings = selected_preferences(
                load_settings(settings_path()).values, prefs, selected
            )
            if any(value != "skip" for value in ignore_choices.values()):
                apply_preset_import(
                    ignore_store, bundle.data["items"]["ignore_presets"], ignore_choices
                )
            outcomes = apply_profile_import(store, bundle, choices)
            if selected:
                save_settings_file(settings_path(), merged_settings)
            QMessageBox.information(
                self,
                translate_text("Portable Import", active_language()),
                f"Profiles: {outcomes.count('create')} created, {outcomes.count('merge')} merged, {outcomes.count('skip')} skipped.\n"
                f"Ignore presets: {sum(value == 'create' for value in ignore_choices.values())} selected for create/replace.\n"
                + (
                    f"Imported preferences: {', '.join(sorted(selected))}. Restart the app to apply theme/language changes."
                    if selected
                    else "No application preferences changed."
                ),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(
                self,
                translate_text("Portable Import", active_language()),
                f"Import stopped with an error: {exc}",
            )

    def migrate_local_settings(self) -> None:
        settings_migration.migrate_local_settings(self, settings_path())

    def rollback_local_settings_migration(self) -> None:
        settings_migration.rollback_local_settings_migration(self, settings_path())

    def browse_global_config(self) -> None:
        global_config_editor.browse_global_config(self)

    def load_global_config(self) -> None:
        global_config_editor.load_global_config(self)

    def show_global_yaml_recovery(self) -> None:
        global_config_editor.show_global_yaml_recovery(self)

    def preview_global_config(self) -> None:
        global_config_editor.preview_global_config(self)

    def save_settings(self) -> None:
        binary = self.binary_edit.text().strip()
        client = MutagenClient(binary)
        if binary and not client.binary:
            QMessageBox.warning(
                self,
                translate_text("Invalid File", active_language()),
                translate_text(
                    "The selected mutagen.exe file does not exist or is unavailable.",
                    active_language(),
                ),
            )
            return
        self.conf.update(
            binary=binary,
            interval=self.interval_input.value(),
            metric_interval=self.metric_interval_input.currentData(),
            eco_tray=self.eco_tray_input.isChecked(),
            tray=self.tray_input.isChecked(),
            alerts=self.alert_input.isChecked(),
            adaptive_poll=self.adaptive_input.isChecked(),
            adaptive_fast=self.fast_interval_input.value(),
            adaptive_idle=self.idle_interval_input.value(),
            adaptive_quiet=self.quiet_after_input.value(),
            new_sync_profile=self.new_sync_profile_input.currentData(),
            theme=self.theme_input.currentData(),
            language=self.language_input.currentData(),
        )
        self.adaptive_policy.fast = self.fast_interval_input.value()
        self.adaptive_policy.idle = self.idle_interval_input.value()
        self.adaptive_policy.quiet_after = self.quiet_after_input.value()
        try:
            write_settings(self.conf)
        except OSError as exc:
            QMessageBox.critical(self, translate_text("Save Failed", active_language()), str(exc))
            return
        self.client = client
        self.apply_theme(self.conf["theme"])
        self.apply_ui_language(self.conf["language"])
        self.poll_backoff.base = max(2, self.interval_input.value())
        self.poll_backoff.observe(True)
        self.update_polling_mode()
        self._version_cache = ("", 0.0, "")
        self._table_signatures.clear()
        self.add_log("Settings saved")
        self.refresh(force=True)

    def add_log(self, message: object) -> None:
        safe_message = str(message).replace("\r", "").strip()
        self.logs.append(f"[{datetime.now():%d.%m. %H:%M:%S}] {safe_message}")
        severity = "warning" if "ERROR" in safe_message or "WARNING" in safe_message else "info"
        if self.recorder is not None:
            self.recorder.add_event(safe_message, severity)
        else:
            with suppress(sqlite3.Error):
                self.history.add_event(safe_message, severity)
        if hasattr(self, "log_view"):
            self.log_view.appendPlainText(self.logs[-1])
            bar = self.log_view.verticalScrollBar()
            bar.setValue(bar.maximum())
        if hasattr(self, "log_count_label"):
            n = len(self.logs)
            self.log_count_label.setText(
                f"{n} {'entry' if n == 1 else 'entries' if 2 <= n <= 4 else 'entries'}"
            )

    def clear_logs(self) -> None:
        self.logs.clear()
        self.log_view.clear()
        if self.recorder is not None:
            self.recorder.clear_events()
        else:
            with suppress(sqlite3.Error):
                self.history.clear_events()
        self.add_log("UI history cleared")

    def export_logs(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Save History", active_language()),
            "mutagen-control-log.txt",
            translate_text("Text (*.txt)", active_language()),
        )
        if not path:
            return
        try:
            Path(path).write_text("\n".join(self.logs) + "\n", encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, translate_text("Write Error", active_language()), str(exc))

    def submit(
        self,
        func: Callable[[], Any],
        on_result: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        worker = Worker(func)
        self.workers.add(worker)

        def deliver_result(result: Any) -> None:
            if not self._shutdown_pending:
                on_result(result)

        def deliver_error(message: str) -> None:
            if not self._shutdown_pending:
                (on_error or self.report_error)(message)

        worker.signals.result.connect(deliver_result)
        worker.signals.error.connect(deliver_error)

        def finished() -> None:
            self.workers.discard(worker)
            if on_done and not self._shutdown_pending:
                on_done()
            if self._shutdown_pending and not self.workers:
                QTimer.singleShot(0, self.close)

        worker.signals.finished.connect(finished)
        self.pool.start(worker)

    def refresh(self, *, force: bool = False) -> None:
        if not self.demo and not self.poll_backoff.can_retry(force):
            return
        if self.demo:
            self.apply_snapshot(self.snapshot)
            return
        if self.pending_poll:
            if force:
                # A settings change or completed command requested newer data.
                # Ignore this worker's now-obsolete result and rerun once.
                self._refresh_generation += 1
                self._refresh_again = True
            return
        if self.pending_action:
            return
        self.pending_poll = True
        self._refresh_generation += 1
        generation = self._refresh_generation
        self._poll_started_at = time.monotonic()
        binary = self.client.binary
        client = MutagenClient(binary)
        cached_version, cache_at, cache_binary = self._version_cache
        version_valid = cache_binary == binary and time.monotonic() - cache_at < 600

        def work() -> Snapshot:
            snap = Snapshot(binary=client.binary)
            snap.registration, snap.registration_command = read_registration(client.binary)
            if not client.binary:
                snap.error = "mutagen.exe is not configured. Open Settings."
                return snap
            try:
                command_started = time.monotonic()
                snap.sync = client.list_sessions("sync")
                snap.command_durations["sync list"] = max(0.0, time.monotonic() - command_started)
                snap.sync_observed_at = datetime.now().astimezone()
                snap.daemon = True
            except MutagenError as exc:
                snap.command_durations["sync list"] = max(0.0, time.monotonic() - command_started)
                snap.error = str(exc)
                return snap
            try:
                command_started = time.monotonic()
                snap.forward = client.list_sessions("forward")
                snap.command_durations["forward list"] = max(
                    0.0, time.monotonic() - command_started
                )
                snap.forward_observed_at = datetime.now().astimezone()
            except MutagenError as exc:
                snap.command_durations["forward list"] = max(
                    0.0, time.monotonic() - command_started
                )
                snap.error = "Forwarding: " + str(exc)
                snap.sessions_stale = True
            if version_valid:
                snap.version = cached_version
            else:
                try:
                    snap.version = client.get_version().splitlines()[0]
                except MutagenError:
                    snap.version = cached_version if cache_binary == binary else ""
            return snap

        def apply_if_current(snap: Snapshot) -> None:
            if generation == self._refresh_generation:
                self.apply_snapshot(snap, generation=generation)

        def finish_poll() -> None:
            self.pending_poll = False
            if self._refresh_again:
                self._refresh_again = False
                self.refresh(force=True)
            else:
                self._complete_pending_launch_requests()

        self.submit(
            work,
            apply_if_current,
            on_error=lambda message: (
                self.report_error(message) if generation == self._refresh_generation else None
            ),
            on_done=finish_poll,
        )

    def refresh_resources(self) -> None:
        if self.demo:
            self.apply_resource_metrics(
                {
                    "cpu": 4.8,
                    "memory": 126_877_696,
                    "processes": 2,
                    "read_rate": 80_000,
                    "write_rate": 160_000,
                    "gui_cpu": 0.4,
                    "gui_memory": 124_000_000,
                }
            )
            return
        if self._resource_pending:
            return
        self._resource_pending = True
        self.submit(
            self.sampler.sample_detailed,
            self.apply_resource_metrics,
            on_error=lambda message: self.footer.setToolTip(
                translate_text("Process monitoring: {message}", active_language()).format(
                    message=message
                )
            ),
            on_done=lambda: setattr(self, "_resource_pending", False),
        )

    def apply_resource_metrics(self, data: dict[str, Any]) -> None:
        # Runs in the GUI thread; psutil enumeration itself happens in QThreadPool.
        self.last_metrics = data
        cpu, ram, count = data["cpu"], data["memory"], data["processes"]
        if hasattr(self, "alert_runtime_label"):
            self.alert_runtime_label.setText(
                f"CPU: {cpu:.1f} %  ·  RAM: {human_bytes(ram)}  ·  Procesy: {count}"
            )
        if not self.demo:
            for alert in self.alert_engine.evaluate(
                cpu,
                ram,
                enabled_cpu=bool(self.conf.get("cpu_alert_on", False)),
                enabled_ram=bool(self.conf.get("ram_alert_on", False)),
                cpu_limit=float(self.conf.get("cpu_alert_limit", 90)),
                ram_limit_mb=float(self.conf.get("ram_alert_limit", 1024)),
                hold_seconds=float(self.conf.get("alert_hold", 20)),
            ):
                self.add_log("WARNING: " + alert.message)
                if (
                    self.conf.get("alerts", True)
                    and self.tray.isVisible()
                    and not quiet_hours_active(
                        datetime.now(),
                        enabled=bool(self.conf.get("quiet_hours_enabled", False)),
                        start=str(self.conf.get("quiet_hours_start", "22:00")),
                        end=str(self.conf.get("quiet_hours_end", "07:00")),
                    )
                ):
                    self._last_notification_session_keys = ()
                    self.tray.showMessage(
                        translate_text("Mutagen Control — Limit", active_language()),
                        translate_text(alert.message, active_language()),
                        QSystemTrayIcon.MessageIcon.Warning,
                        7000,
                    )
        if self.recorder is not None:
            if self.recorder.last_error:
                set_localized_text(self.writer_status, "History: write error")
                self.writer_status.setToolTip(self.recorder.last_error)
            elif self.recorder.dropped:
                self.writer_status.setText(
                    translate_text(
                        "Number of skipped history samples: {count}", active_language()
                    ).format(count=self.recorder.dropped)
                )
            else:
                set_localized_text(self.writer_status, "History: saving continuously")
        else:
            set_localized_text(self.writer_status, "History: demo mode")
        if hasattr(self, "gui_usage_label"):
            language = self.ui_language
            self.gui_usage_label.setText(
                f"{translate_text('Application load', language)}: CPU "
                f"{data.get('gui_cpu', 0):.1f} %  ·  "
                f"RAM {human_bytes(data.get('gui_memory', 0))}  ·  "
                f"{translate_text('measured for the UI process, not Mutagen', language)}"
            )
        self.snapshot.cpu, self.snapshot.memory, self.snapshot.processes = cpu, ram, count
        self.snapshot.resource_observed_at = datetime.now().astimezone()
        # State changes only on CLI polls, not on each CPU sample.
        active, problems = self.session_counts
        forward_rates = (
            self.traffic_rates if self.demo or self._traffic_sample_pending else (None, None)
        )
        self._traffic_sample_pending = False
        cli_launch_count = self.client.cli_launch_count
        sample = Sample(
            ts=time.time(),
            cpu=cpu,
            memory=ram,
            read_rate=data["read_rate"],
            write_rate=data["write_rate"],
            forward_out_rate=forward_rates[0],
            forward_in_rate=forward_rates[1],
            processes=count,
            active_sessions=active,
            problem_sessions=problems,
            tray_idle_seconds=self.tray_idle_seconds(),
            cli_launches=max(0, cli_launch_count - self._last_recorded_cli_launch_count),
        )
        recorded = False
        if self.recorder is not None:
            recorded = self.recorder.add(sample)
            if not recorded:
                set_localized_tooltip(self.footer, "History writer is no longer available")
            elif self.recorder.last_error:
                self.footer.setToolTip("History: " + self.recorder.last_error)
        else:
            try:
                self.history.add(sample)
                recorded = True
            except sqlite3.Error as exc:
                self.footer.setToolTip(str(exc))
        if recorded:
            self._last_recorded_cli_launch_count = cli_launch_count
            self.commit_tray_idle_sample()
        self.cpu_value.setText(f"{cpu:.1f} %")
        self.mem_value.setText(human_bytes(ram))
        if hasattr(self, "monitor_labels"):
            self.monitor_labels["cpu"].setText(f"{cpu:.1f} %")
            self.monitor_labels["memory"].setText(human_bytes(ram))
            self.monitor_labels["disk"].setText(
                f"↓ {human_bytes(data['read_rate'])}/s · ↑ {human_bytes(data['write_rate'])}/s"
            )
            self.monitor_labels["traffic"].setText(
                f"{translate_text('outbound', self.ui_language)} "
                f"{human_bytes(self.traffic_rates[0])}/s · "
                f"{translate_text('inbound', self.ui_language)} "
                f"{human_bytes(self.traffic_rates[1])}/s"
            )
            self.monitor_labels["sessions"].setText(
                f"{active} {translate_text('active', self.ui_language)} · "
                f"{problems} {translate_text('issues', self.ui_language)}"
            )
        if hasattr(self, "process_table") and self.pages.currentIndex() == 6:
            detail = (
                [
                    {
                        "pid": 1840,
                        "name": "mutagen.exe",
                        "cpu": 3.7,
                        "memory": 100_000_000,
                        "read_rate": 50_000,
                        "write_rate": 100_000,
                    },
                    {
                        "pid": 2480,
                        "name": "mutagen-agent.exe",
                        "cpu": 1.1,
                        "memory": 26_877_696,
                        "read_rate": 30_000,
                        "write_rate": 60_000,
                    },
                ]
                if self.demo
                else self.sampler.last_processes
            )
            self.fill_processes(detail)
        self.refresh_charts()

    def fill_processes(self, processes: list[dict[str, Any]]) -> None:
        table = self.process_table
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(processes))
            for idx, proc in enumerate(processes):
                cells = [
                    str(proc["pid"]),
                    proc["name"],
                    f"{proc['cpu']:.1f} %",
                    human_bytes(proc["memory"]),
                    human_bytes(proc["read_rate"]) + "/s",
                    human_bytes(proc["write_rate"]) + "/s",
                ]
                for col, cell in enumerate(cells):
                    item = table.item(idx, col)
                    if item is None:
                        item = QTableWidgetItem(str(cell))
                        table.setItem(idx, col, item)
                        if col in (0, 2, 3, 4, 5):
                            item.setTextAlignment(
                                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                            )
                    elif item.text() != str(cell):
                        item.setText(str(cell))
                    if col == 0 and item.data(Qt.ItemDataRole.UserRole) != proc["pid"]:
                        item.setData(Qt.ItemDataRole.UserRole, proc["pid"])
            table.setSortingEnabled(True)
        finally:
            table.setUpdatesEnabled(True)
        self.fit_table_to_rows(table)

    def refresh_charts(self, *_args: object, force: bool = False) -> None:
        if self.chart_frozen and not force:
            return
        page_index = self.pages.currentIndex()
        if page_index not in (0, 6):
            return  # No SQLite reads or paints for invisible chart pages.
        if not self.isVisible() and not force:
            return
        gate = self._chart_dashboard_gate if page_index == 0 else self._chart_monitor_gate
        if not gate.ready(force):
            return
        try:
            if page_index == 0:
                recent = self.history.query(hours=5 / 60, max_points=320)
                self.cpu_chart.set_data((r["ts"], r["cpu"], None) for r in recent)
                self.mem_chart.set_data((r["ts"], r["memory"], None) for r in recent)
                return
            if not hasattr(self, "monitor_graphs"):
                return
            hours = float(self.monitor_range.currentData())
            if self.demo or self.history.path == ":memory:":
                self.apply_monitor_chart_data(self.history.query(hours=hours), hours)
            elif not self._chart_query_pending:
                self._chart_query_pending = True
                self._chart_query_reschedule = False
                path = self.history.path

                def finished_query() -> None:
                    self._chart_query_pending = False
                    if self._chart_query_reschedule and self.pages.currentIndex() == 6:
                        self._chart_monitor_gate.reset()
                        self.refresh_charts(force=True)

                self.submit(
                    lambda: query_metrics_from_file(path, hours=hours),
                    lambda rows: self.apply_monitor_chart_data(rows, hours),
                    lambda error: self.stats_label.setToolTip("Graph history: " + str(error)[:150]),
                    on_done=finished_query,
                )
            else:
                self._chart_query_reschedule = True
            # Raw P95 / max over a 48h window can require 80k+ records.
            # Read and sort it in a worker using a separate read-only SQLite
            # connection, so zooming the GUI never blocks on statistics.
            if self._stats_cache_range == hours and time.monotonic() - self._stats_cache_at < 20:
                return
            if self._stats_pending:
                return
            if self.demo or self.history.path == ":memory:":
                self.apply_statistics(self.history.statistics(hours=hours), hours)
            else:
                self._stats_pending = True
                set_localized_text(self.stats_label, "Loading statistics for the selected period…")
                path = self.history.path
                self.submit(
                    lambda: statistics_from_file(path, hours=hours),
                    lambda data: self.apply_statistics(data, hours),
                    lambda error: self.stats_label.setText(
                        "Could not load statistics: " + str(error)[:140]
                    ),
                    on_done=lambda: setattr(self, "_stats_pending", False),
                )
        except sqlite3.Error:
            pass

    def apply_monitor_chart_data(self, rows: list[dict[str, Any]], hours: float) -> None:
        if self.pages.currentIndex() != 6 or float(self.monitor_range.currentData()) != hours:
            return  # Ignore asynchronous results for a previously selected range.
        mapping = {
            "cpu": ("cpu", None),
            "memory": ("memory", None),
            "disk": ("read_rate", "write_rate"),
            "traffic": ("forward_out_rate", "forward_in_rate"),
            "sessions": ("active_sessions", "problem_sessions"),
        }
        for name, (left, right) in mapping.items():
            self.monitor_graphs[name].set_data(
                (row["ts"], row[left], row[right] if right else None) for row in rows
            )

    def apply_statistics(self, stats: dict[str, Any], hours: float) -> None:
        if self.pages.currentIndex() != 6 or float(self.monitor_range.currentData()) != hours:
            return  # Ignore an outdated result from another selected interval.
        self._stats_cache_at = time.monotonic()
        self._stats_cache_range = hours
        self._last_monitor_stats = stats

        def fmt(field: str, unit: str) -> str:
            values = stats["fields"][field]
            localized_unit = translate_text(unit, self.ui_language)
            return (
                f"{localized_unit}: {translate_text('current', self.ui_language)} "
                f"{field_format(field, values['latest'])}  ·  "
                f"{translate_text('average', self.ui_language)} "
                f"{field_format(field, values['avg'])}  ·  "
                f"P95 {field_format(field, values['p95'])}  ·  "
                f"{translate_text('maximum', self.ui_language)} "
                f"{field_format(field, values['max'])}"
            )

        self.stats_label.setText(
            translate_text(
                "Measured {samples} samples; missing periods are not interpolated.",
                self.ui_language,
            ).format(samples=stats["samples"])
            + "\n"
            + fmt("cpu", "CPU")
            + "\n"
            + fmt("memory", "RAM")
            + "\n"
            + fmt("read_rate", "Disk Read")
            + "\n"
            + fmt("write_rate", "Disk Write")
            + "\n"
            + fmt("forward_out_rate", "Forward out")
            + "\n"
            + fmt("forward_in_rate", "Forward Inbound")
        )

    def apply_snapshot(self, snap: Snapshot, *, generation: int | None = None) -> None:
        if generation is not None and generation != self._refresh_generation:
            return
        received_at = time.monotonic()
        if (
            self._last_snapshot_received_monotonic is not None
            and received_at - self._last_snapshot_received_monotonic > 180
        ):
            self.health_tracker.note_environment_event("wake", now=received_at)
        self._last_snapshot_received_monotonic = received_at
        # Preserve separately sampled resource measurements.
        if not self.demo:
            snap.cpu, snap.memory, snap.processes = (
                self.snapshot.cpu,
                self.snapshot.memory,
                self.snapshot.processes,
            )
        if not self.demo and snap.binary == self.snapshot.binary:
            if not snap.daemon:
                # An unreachable daemon must not make the last known sessions
                # disappear. Keep them visible and label them as stale.
                snap.sync = list(self.snapshot.sync)
                snap.forward = list(self.snapshot.forward)
                snap.sync_observed_at = self.snapshot.sync_observed_at
                snap.forward_observed_at = self.snapshot.forward_observed_at
                snap.sessions_stale = self.snapshot.daemon or self.snapshot.sessions_stale
            elif snap.sessions_stale:
                # Sync list succeeded; keep only the failed forwarding list.
                snap.forward = list(self.snapshot.forward)
                snap.forward_observed_at = self.snapshot.forward_observed_at
            snap.resource_observed_at = self.snapshot.resource_observed_at
            snap.command_durations = dict(snap.command_durations)
        self.snapshot = snap
        if hasattr(self, "diagnostics_view"):
            self.update_diagnostics(snap)
        if snap.daemon:
            self.adaptive_policy.observe(snap)
        self.update_polling_mode()
        if snap.version and snap.binary:
            current_version, cached_at, cached_binary = self._version_cache
            if (
                snap.version != current_version
                or snap.binary != cached_binary
                or time.monotonic() - cached_at >= 600
            ):
                self._version_cache = (snap.version, time.monotonic(), snap.binary)
        if not self.demo and snap.daemon and not snap.sessions_stale:
            self.traffic_rates = self.traffic_meter.update(snap.forward)
            self._traffic_sample_pending = True
        if not self.demo:
            self.check_alerts(snap)
        if not self.demo:
            self.poll_backoff.observe(bool(snap.daemon))
        duration_ms = (
            (time.monotonic() - self._poll_started_at) * 1000 if self._poll_started_at else 0
        )
        if self.demo:
            set_localized_text(self.updated, "DEMO DATA")
        else:
            retry_seconds = self.poll_backoff.remaining()
            if snap.daemon and not snap.sessions_stale:
                refreshed_time = datetime.now().strftime("%H:%M:%S")
                english = f"Refreshed {refreshed_time}  ·  CLI {duration_ms:.0f} ms"
                czech = translate_text("Refreshed {time} · CLI {duration} ms", "cs").format(
                    time=refreshed_time, duration=f"{duration_ms:.0f}"
                )
            elif snap.daemon:
                detail = snap.error or "session data is stale"
                english = f"Showing last successful sessions · {detail}"
                czech = translate_text("Showing last successful sessions · {detail}", "cs").format(
                    detail=detail
                )
            elif snap.sessions_stale:
                english = (
                    "Daemon offline · showing last successful sessions · "
                    f"retrying in {retry_seconds:.0f} s"
                )
                czech = translate_text(
                    "Daemon offline · showing last successful sessions · retrying in {seconds} s",
                    "cs",
                ).format(seconds=f"{retry_seconds:.0f}")
            else:
                english = f"Daemon offline · retrying in {retry_seconds:.0f} s"
                czech = translate_text("Daemon offline · retrying in {seconds} s", "cs").format(
                    seconds=f"{retry_seconds:.0f}"
                )
            set_localized_text(self.updated, english, czech=czech)
        self._version_label_text = snap.version or "Version: unavailable"
        if hasattr(self, "version_label"):
            if snap.version:
                self.version_label.setText(self._version_label_text)
            else:
                set_localized_text(self.version_label, "Version: unavailable")
        regtexts = {
            "registered": "Auto-start: registered for this installation",
            "unregistered": "Auto-start: not registered",
            "other": "Auto-start: entry points to another installation/command",
            "unknown": "Auto-start: status unknown",
            "unsupported": "Auto-start: detection is available on Windows only",
        }
        registration_en = regtexts.get(snap.registration, "Registration: unknown")
        registration_cs = {
            "registered": "Automatické spuštění: registrováno pro tuto instalaci",
            "unregistered": "Automatické spuštění: není registrováno",
            "other": "Automatické spuštění: položka odkazuje na jinou instalaci nebo příkaz",
            "unknown": "Automatické spuštění: stav není známý",
            "unsupported": "Automatické spuštění: zjištění je dostupné pouze ve Windows",
        }.get(snap.registration, "Registrace: stav není známý")
        set_localized_text(self.register_message, registration_en, czech=registration_cs)
        autostart_hints = {"win32": "Registry entry in HKCU\\...\\Run\\Mutagen"}
        default_autostart_hint = autostart_hints.get(
            sys.platform, "launchd (macOS) or systemd --user / XDG (Linux)"
        )
        self.register_message.setToolTip(snap.registration_command or default_autostart_hint)
        available = bool(snap.binary)
        if not available:
            set_localized_text(self.side_state, "●  Mutagen CLI not found")
            self.side_state.setStyleSheet(f"color:{RED}")
            set_localized_text(self.side_sub, "Select mutagen.exe in Settings")
        elif snap.daemon:
            set_localized_text(self.side_state, "●  Daemon online")
            self.side_state.setStyleSheet(f"color:{TEAL}")
            sync_count = len(snap.sync)
            forward_count = len(snap.forward)
            sync_noun = "sync" if sync_count == 1 else "syncs"
            forward_noun = "port forward" if forward_count == 1 else "port forwards"
            summary_en = f"{sync_count} {sync_noun} · {forward_count} {forward_noun}"
            sync_form = _czech_plural(
                sync_count,
                ("relace", "relace", "relací"),
            )
            forward_form = _czech_plural(
                forward_count,
                ("přesměrování", "přesměrování", "přesměrování"),
            )
            summary_cs = f"{sync_count} {sync_form} · {forward_count} {forward_form}"
            set_localized_text(self.side_sub, summary_en, czech=summary_cs)
        else:
            set_localized_text(self.side_state, "●  Daemon offline")
            self.side_state.setStyleSheet(f"color:{AMBER}")
            set_localized_text(self.side_sub, (snap.error or "Not running yet")[:120])
        set_localized_text(
            self.hero_title, "Daemon is running" if snap.daemon else "Daemon is unavailable"
        )
        set_localized_text(
            self.hero_sub,
            "Sync runs in the background. The application monitors its status."
            if snap.daemon
            else "Go to the Daemon page to start the service or open Settings.",
        )
        # Version badge in hero
        if hasattr(self, "hero_badge"):
            if snap.version:
                self.hero_badge.setText(snap.version)
                self.hero_badge.setVisible(True)
            else:
                self.hero_badge.setVisible(False)
        set_localized_text(
            self.daemon_title,
            "●  Running" if snap.daemon else "●  Unavailable / stopped",
            czech="●  Spuštěno" if snap.daemon else "●  Nedostupná / zastavená",
        )
        self.daemon_title.setStyleSheet(
            f"color:{TEAL if snap.daemon else AMBER};font-size:22px;font-weight:750"
        )
        if snap.daemon:
            description_en = (
                "Daemon responded; " + snap.error if snap.error else "Daemon is responding."
            )
            description_cs = (
                "Služba Mutagen odpověděla; " + snap.error
                if snap.error
                else "Služba Mutagen odpovídá."
            )
        else:
            description_en = snap.error or "Daemon is not running."
            description_cs = snap.error or "Služba Mutagen není spuštěna."
        set_localized_text(self.daemon_desc, description_en, czech=description_cs)
        for b in (self.start_button, self.stop_button):
            b.setEnabled(not self.demo and available and not self.pending_action)
        all_sessions = [("sync", x) for x in snap.sync] + [("forward", x) for x in snap.forward]
        kinds = [classify(x, k)[0] for k, x in all_sessions]
        self.metric_widgets["all"].setText(str(len(all_sessions)))
        self.metric_widgets["running"].setText(str(sum(s in ("active", "busy") for s in kinds)))
        self.metric_widgets["paused"].setText(str(kinds.count("paused")))
        self.metric_widgets["errors"].setText(str(kinds.count("error")))
        self.health_ring.set_health(len(kinds), kinds.count("error"))
        self.session_counts = (sum(s in ("active", "busy") for s in kinds), kinds.count("error"))
        sync_count = len(snap.sync)
        sync_paused = sum(bool(x.get("paused")) for x in snap.sync)
        sync_form = _czech_plural(sync_count, ("synchronizace", "synchronizace", "synchronizací"))
        set_localized_text(
            self.sync_summary,
            f"{sync_count} sync sessions • {sync_paused} paused",
            czech=f"{sync_count} {sync_form} · {sync_paused} pozastaveno",
        )
        forward_count = len(snap.forward)
        forward_form = _czech_plural(
            forward_count, ("přesměrování", "přesměrování", "přesměrování")
        )
        set_localized_text(
            self.forward_summary,
            f"{forward_count} forwarding sessions • data and active connections in details",
            czech=f"{forward_count} {forward_form} · data a aktivní spojení v podrobnostech",
        )
        # Dashboard forward summary line
        if hasattr(self, "dashboard_forward_summary"):
            fwd_active = sum(
                1 for s in snap.forward if classify(s, "forward")[0] in ("active", "busy")
            )
            fwd_total = len(snap.forward)
            if fwd_total:
                fwd_open = sum(1 for s in snap.forward if s.get("openConnections", 0) > 0)
                set_localized_text(
                    self.dashboard_forward_summary,
                    f"{fwd_total} total · {fwd_active} active · {fwd_open} with open connections",
                    czech=f"{fwd_total} celkem · {fwd_active} aktivní · {fwd_open} s otevřeným spojením",
                )
            else:
                set_localized_text(self.dashboard_forward_summary, "No forwarding sessions")
        # Rebuilding and re-sorting entire QTableWidgets on every 4 s poll
        # causes avoidable flicker and allocates dozens of QTableWidgetItems.
        for kind, sessions, table in (
            ("sync", snap.sync, self.sync_table),
            ("forward", snap.forward, self.forward_table),
            ("dashboard", snap.sync[:5], self.dashboard_table),
        ):
            actual_kind = "sync" if kind == "dashboard" else kind
            signature = tuple(
                (
                    s.get("identifier"),
                    s.get("name"),
                    s.get("paused"),
                    s.get("status"),
                    s.get("lastError"),
                    conflict_count(s) if actual_kind == "sync" else s.get("openConnections"),
                    problem_count(s) if actual_kind == "sync" else 0,
                    endpoint_text(
                        s.get("alpha" if actual_kind == "sync" else "source"), actual_kind
                    ),
                    endpoint_text(
                        s.get("beta" if actual_kind == "sync" else "destination"), actual_kind
                    ),
                    s.get("identifier") in self.favorites[actual_kind],
                )
                for s in sessions
            )
            if signature != self._table_signatures.get(kind):
                self.fill_table(table, sessions, actual_kind, dashboard=kind == "dashboard")
                self._table_signatures[kind] = signature
                if kind != "dashboard":
                    self.filter_table(kind)
        page = self.pages.currentIndex()
        if page in (1, 2):
            self.refresh_detail("sync" if page == 1 else "forward")
        if page == 7:
            self.update_diagnostics(snap)
        self.update_endpoint_sessions(snap)
        self.update_server_groups()
        if self.demo:
            set_localized_text(self.footer, "DEMO • All actions are disabled")
        else:
            self.footer.setText(
                "Connected to " + snap.binary if available else "Select a Mutagen installation"
            )

    def fill_table(
        self,
        table: QTableView,
        sessions: list[dict[str, Any]],
        kind: str,
        dashboard: bool = False,
    ) -> None:
        """Reset one compact model while retaining the selected session and scroll."""
        model = table.model()
        current = table.currentIndex()
        selection = (
            current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) if current.isValid() else ""
        )
        old_scroll = table.verticalScrollBar().value()
        table.blockSignals(True)
        selection_model = table.selectionModel()
        selection_model.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            model.set_sessions(sessions, self.favorites[kind])
            if selection:
                row = model.row_for_identifier(selection)
                if row >= 0:
                    table.selectRow(row)
                else:
                    table.clearSelection()
            else:
                table.clearSelection()
            table.verticalScrollBar().setValue(old_scroll)
        finally:
            table.setUpdatesEnabled(True)
            selection_model.blockSignals(False)
            table.blockSignals(False)
        if table.currentIndex().isValid():
            self.on_select(kind)
        self.fit_table_to_rows(table)

    @staticmethod
    def fit_table_to_rows(table: QTableView | QTableWidget) -> None:
        row_count = table.model().rowCount() if isinstance(table, QTableView) else table.rowCount()
        visible_rows = [row for row in range(row_count) if not table.isRowHidden(row)]
        rows_height = sum(table.rowHeight(row) for row in visible_rows)
        header_height = max(
            table.horizontalHeader().height(), table.horizontalHeader().sizeHint().height()
        )
        height = min(520, max(160, header_height + rows_height + 2 * table.frameWidth() + 4))
        table.setFixedHeight(height)

    def filter_table(self, kind: str, value: str | None = None) -> None:
        table = self.sync_table if kind == "sync" else self.forward_table
        search = self.sync_search if kind == "sync" else self.forward_search
        filters = self.sync_state_filter if kind == "sync" else self.forward_state_filter
        needle = (value if isinstance(value, str) else search.text()).casefold().strip()
        code = {
            1: "active",
            2: "busy",
            3: {"active", "busy"},
            4: "paused",
            5: "error",
            6: "idle",
        }.get(filters.currentIndex())
        only_favorites = (
            self.sync_favorites_only if kind == "sync" else self.forward_favorites_only
        ).isChecked()
        server_key = self.sync_server_filter.currentData() if kind == "sync" else "__all__"
        by_id = {
            s.get("identifier"): s
            for s in (self.snapshot.sync if kind == "sync" else self.snapshot.forward)
        }
        model = table.model()
        for row in range(model.rowCount()):
            haystack = " ".join(
                str(model.index(row, col).data() or "") for col in range(model.columnCount())
            ).casefold()
            identifier = model.index(row, 0).data(Qt.ItemDataRole.UserRole)
            current = by_id.get(identifier)
            current_state = classify(current, kind)[0] if current is not None else None
            if isinstance(code, set):
                meets_state = current_state in code
            else:
                meets_state = code is None or current_state == code
            meets_server = server_key == "__all__" or (
                current is not None and server_key in session_servers(current, kind)
            )
            table.setRowHidden(
                row,
                needle not in haystack
                or not meets_state
                or not meets_server
                or (only_favorites and identifier not in self.favorites[kind]),
            )
        self.fit_table_to_rows(table)

    def dashboard_select(self, row: int, col: int) -> None:
        index = self.dashboard_table.model().index(row, 0)
        if index.isValid():
            self.current_id = index.data(Qt.ItemDataRole.UserRole) or ""
            self.current_kind = "sync"
            self.set_page(1)
            model = self.sync_table.model()
            match = model.row_for_identifier(self.current_id)
            if match >= 0:
                self.sync_table.selectRow(match)

    def on_select(self, kind: str) -> None:
        table = self.sync_table if kind == "sync" else self.forward_table
        current = table.currentIndex()
        if not current.isValid():
            if self.current_kind == kind:
                self.current_id = ""
        else:
            self.current_kind = kind
            self.current_id = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) or ""
        self.refresh_detail(kind)

    def selected_session(self, kind: str) -> dict[str, Any] | None:
        table = self.sync_table if kind == "sync" else self.forward_table
        current = table.currentIndex()
        if not current.isValid():
            return None
        identifier = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        sessions = self.snapshot.sync if kind == "sync" else self.snapshot.forward
        return next((s for s in sessions if s.get("identifier") == identifier), None)

    def refresh_detail(self, kind: str) -> None:
        sess = self.selected_session(kind)
        details = self.sync_details if kind == "sync" else self.forward_details
        title = self.sync_title if kind == "sync" else self.forward_title
        tag = self.sync_tag if kind == "sync" else self.forward_tag
        controls = self.sync_controls if kind == "sync" else self.forward_controls
        progress_bar = self.sync_progress if kind == "sync" else self.forward_progress
        progress_bar.hide()
        fav_button = self.sync_favorite_button if kind == "sync" else self.forward_favorite_button
        fav_button.setEnabled(bool(sess))
        fav_button.setText(
            "★ Remove from Favorites"
            if sess and sess.get("identifier") in self.favorites[kind]
            else "☆ Add to Favorites"
        )
        for b in controls.values():
            b.setEnabled(bool(sess) and not self.demo and not self.pending_action)
        if kind == "sync":
            auto = self.sync_autostart_button
            auto.setEnabled(bool(sess) and not self.demo and not self.pending_action)
            if not sess:
                set_localized_text(auto, "Start at sign-in: select a session")
            elif sess.get("paused"):
                set_localized_text(auto, "◯ Start at sign-in: off")
            elif self.snapshot.registration == "registered":
                set_localized_text(auto, "● Start at sign-in: on")
            else:
                set_localized_text(auto, "⚠ Enable start at sign-in · register daemon")
        if not sess:
            set_localized_text(title, "Select a session")
            tag.setText("")
            set_localized_text(
                details,
                "Select a row above to view details, status, statistics, and available actions.",
            )
            return
        state, description = classify(sess, kind)
        title.setText(sess.get("name") or "Untitled Session")
        tag.setText(description)
        tag.setStyleSheet(
            f"color:{ {'error': RED, 'active': TEAL, 'paused': AMBER}.get(state, BLUE) }"
        )
        first = endpoint_text(sess.get("alpha" if kind == "sync" else "source"), kind)
        second = endpoint_text(sess.get("beta" if kind == "sync" else "destination"), kind)
        sep = "─" * 44
        lines = [
            f"IDENTIFIER\n{sess.get('identifier', '—')}",
            sep,
            f"{'ENDPOINTS' if kind == 'sync' else 'CONNECTION'}",
            f"{'ALPHA' if kind == 'sync' else 'Source'}\n{first}",
            f"{'BETA' if kind == 'sync' else 'Destination'}\n{second}",
        ]
        if kind == "sync":
            alpha = sess.get("alpha") or {}
            beta = sess.get("beta") or {}
            lines += [
                sep,
                "SYNC OVERVIEW",
                f"Files: ALPHA {alpha.get('files', '—')} · BETA {beta.get('files', '—')}",
                f"Total size: {human_bytes(alpha.get('totalFileSize', 0))}",
                f"Successful cycles: {sess.get('successfulCycles', 0)}",
                f"Conflicts: {conflict_count(sess)} · Issues: {problem_count(sess)}",
            ]
            stages = [
                ("ALPHA", alpha.get("stagingProgress")),
                ("BETA", beta.get("stagingProgress")),
            ]
            for target, prog in stages:
                if prog:
                    expected_size = int(prog.get("expectedSize") or 0)
                    if expected_size:
                        percentage = min(
                            100, round(100 * float(prog.get("receivedSize") or 0) / expected_size)
                        )
                        progress_bar.setValue(percentage)
                        progress_bar.setFormat(f"Transfer to {target}: %p %")
                        progress_bar.show()
                    expected = max(1, prog.get("expectedSize", 0))
                    lines.append(
                        f"Transfer to {target}: {prog.get('path', '')} · {100 * prog.get('receivedSize', 0) / expected:.0f} % "
                        f"({human_bytes(prog.get('receivedSize', 0))} / {human_bytes(prog.get('expectedSize', 0))})"
                    )
            confs = sess.get("conflicts") or []
            if confs:
                lines += [sep, "RECENT CONFLICTS"]
                for index, conflict in enumerate(confs, 1):
                    lines.append(f"Conflict {index}")
                    lines.extend(readable_record_lines(conflict, indent=2))
            probs = [
                *alpha.get("scanProblems", []),
                *alpha.get("transitionProblems", []),
                *beta.get("scanProblems", []),
                *beta.get("transitionProblems", []),
            ]
            if probs:
                lines += [sep, "RECENT ISSUES"]
                for index, problem in enumerate(probs, 1):
                    lines.append(f"Issue {index}")
                    lines.extend(readable_record_lines(problem, indent=2))
        else:
            lines += [
                sep,
                "CONNECTION OVERVIEW",
                f"Open connections: {sess.get('openConnections', 0)} · Total: {sess.get('totalConnections', 0)}",
                f"Data out: {human_bytes(sess.get('totalOutboundData', 0))}",
                f"Data in: {human_bytes(sess.get('totalInboundData', 0))}",
            ]
        if sess.get("lastError"):
            lines += [sep, "⚠ LAST ERROR: " + str(sess["lastError"])]
        custom_note = (
            self.conf.get("session_prefs", {})
            .get(str(sess.get("identifier") or ""), {})
            .get("note")
        )
        if custom_note:
            lines += [sep, "📝 NOTE: " + custom_note]
        details.setText(session_detail_html(lines, sep))
        if "flush" in controls:
            controls["flush"].setEnabled(
                not sess.get("paused") and not self.demo and not self.pending_action
            )
        if "pause" in controls:
            controls["pause"].setEnabled(
                not sess.get("paused") and not self.demo and not self.pending_action
            )
        if "resume" in controls:
            controls["resume"].setEnabled(
                bool(sess.get("paused")) or state in ("error", "idle")
                if not self.demo and not self.pending_action
                else False
            )

    def open_session_preferences(self, kind: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            QMessageBox.information(
                self,
                translate_text("Select a session", active_language()),
                translate_text("First, select a session in the table.", active_language()),
            )
            return
        identifier = str(sess.get("identifier") or "")
        prefs = dict(self.conf.get("session_prefs", {}).get(identifier, {}))
        dialog = QDialog(self)
        dialog.setWindowTitle("Session Settings · " + (sess.get("name") or identifier[:14]))
        dialog.setMinimumWidth(480)
        box = QVBoxLayout(dialog)
        box.setSpacing(15)
        box.setContentsMargins(24, 22, 24, 22)
        box.addWidget(label("Display and Notification Settings", size=17, bold=True))
        box.addWidget(
            label(
                f"Exact Mutagen ID (read-only): {identifier} · Name: {sess.get('name') or 'Unnamed'}",
                muted=True,
                size=11,
            )
        )
        if self.ui_mode == "advanced":
            raw_json_button = button(
                "View raw native JSON…",
                partial(self.show_raw_native_session_json, sess, dialog),
            )
            raw_json_button.setObjectName("rawNativeSessionJson")
            box.addWidget(raw_json_button)
        notifications = localized_checkbox("Notify about new errors in this session")
        notifications.setChecked(bool(prefs.get("notifications", True)))
        box.addWidget(notifications)
        box.addWidget(label("Session Note", muted=True))
        note = QLineEdit(str(prefs.get("note", "")))
        note.setMaxLength(180)
        box.addWidget(note)
        fields_by_key: Mapping[str, SyncConfigField | ForwardConfigField]
        config_rows: Sequence[SyncConfigRow | ForwardConfigRow]
        if kind == "sync":
            box.addWidget(label("Actual Mutagen Sync Configuration", size=14, bold=True))
            proposals = prefs.get("configuration_proposal", {})
            if not isinstance(proposals, dict):
                proposals = {}
            fields_by_key = {field.key: field for field in SYNC_CONFIG_FIELDS}
            sync_rows = session_configuration_rows(sess, proposals)
            config_rows = sync_rows
            config_table = QTableWidget(len(config_rows), 6)
            set_localized_accessible_name(config_table, "Project configuration table")
            config_table.setHorizontalHeaderLabels(
                ["Field", "Native value", "Origin", "Impact", "Capability", "Proposed value"]
            )
            config_table.setWordWrap(True)
            config_table.setMinimumSize(1000, 390)
            config_table.setAlternatingRowColors(True)
            config_table.horizontalHeader().setStretchLastSection(True)
            fill_session_configuration_table(
                config_table,
                sync_rows,
                fields_by_key,
                proposals,
                proposal_tooltip="Local proposal only. Installed Mutagen support must be verified before replacement.",
            )
            box.addWidget(config_table)
            explanation = label(
                "Current values are read-only snapshots. Edit Proposed value to keep a local replacement draft. "
                "Saving this dialog does not change the existing Mutagen session. Capability checks and a reviewed replacement workflow are required before applying any proposal.",
                muted=True,
                size=11,
            )
            explanation.setWordWrap(True)
            box.addWidget(explanation)

            if self.ui_mode == "advanced":
                performance_assistant = QPushButton(
                    "Asistent ladění výkonu…"
                    if active_language().casefold().startswith("cs")
                    else "Performance Tuning Assistant…"
                )
                performance_assistant.setObjectName("performanceTuningAssistant")
                performance_assistant.setAccessibleName(
                    "Asistent ladění výkonu"
                    if active_language().casefold().startswith("cs")
                    else "Performance Tuning Assistant"
                )
                performance_assistant.setEnabled(not self.demo and not self.snapshot.sessions_stale)

                def open_performance_assistant() -> None:
                    apply_performance_assistant(
                        sess,
                        config_table,
                        sync_rows,
                        stale=self.snapshot.sessions_stale,
                        parent=dialog,
                    )

                performance_assistant.clicked.connect(open_performance_assistant)
                performance_assistant.setToolTip(
                    "Ukazuje kvalitativní doporučení z dokumentace. Návrhy vyplní pouze místní koncept náhrady."
                    if active_language().casefold().startswith("cs")
                    else "Shows qualitative, documentation-based guidance. Suggestions only fill a local replacement draft."
                )
                box.addWidget(performance_assistant)

            def quick_ignore_selected_file() -> None:
                local_roots = []
                for side, endpoint_label in (("alpha", "ALPHA"), ("beta", "BETA")):
                    endpoint = sess.get(side)
                    if not isinstance(endpoint, dict):
                        continue
                    raw_path = endpoint.get("path")
                    if (
                        endpoint.get("protocol") not in (0, "local")
                        or not isinstance(raw_path, str)
                        or not Path(raw_path).expanduser().is_dir()
                    ):
                        continue
                    local_roots.append((endpoint_label, Path(raw_path).expanduser()))
                if not local_roots:
                    QMessageBox.information(
                        dialog,
                        translate_text("Quick Ignore unavailable", active_language()),
                        translate_text("No local sync endpoint was reported.", active_language()),
                    )
                    return
                root_label, root_path = local_roots[0]
                if len(local_roots) > 1:
                    choices = [f"{side} — {path}" for side, path in local_roots]
                    choice, accepted = QInputDialog.getItem(
                        dialog,
                        translate_text("Choose Local Sync Endpoint", active_language()),
                        translate_text(
                            "Select the local root for this ignore rule:", active_language()
                        ),
                        choices,
                        0,
                        False,
                    )
                    if not accepted:
                        return
                    index = choices.index(choice)
                    root_label, root_path = local_roots[index]
                selected, _filter = QFileDialog.getOpenFileName(
                    dialog,
                    translate_text("Select file for Quick Ignore", active_language()),
                    str(root_path),
                    translate_text("All files (*)", active_language()),
                )
                if not selected:
                    return
                try:
                    pattern = path_aware_ignore_rule(root_path, selected)
                    ignore_row = next(
                        index for index, row in enumerate(config_rows) if row.key == "ignore.paths"
                    )
                    draft_text = (
                        cast(QTableWidgetItem, config_table.item(ignore_row, 5)).text().strip()
                    )
                    if draft_text:
                        patterns = json.loads(draft_text)
                    else:
                        native_ignore = sess.get("ignore", {})
                        patterns = (
                            native_ignore.get("paths", [])
                            if isinstance(native_ignore, dict)
                            else []
                        )
                    if not isinstance(patterns, list) or any(
                        not isinstance(value, str) for value in patterns
                    ):
                        raise ValueError("The current ignore paths are not a known list.")
                    if pattern not in patterns:
                        patterns.append(pattern)
                    cast(QTableWidgetItem, config_table.item(ignore_row, 5)).setText(
                        json.dumps(patterns, ensure_ascii=False)
                    )
                    self.add_log(f"Quick Ignore drafted for {root_label}: {pattern}")
                except (IgnorePresetError, OSError, ValueError, json.JSONDecodeError) as exc:
                    QMessageBox.warning(
                        dialog,
                        translate_text("Quick Ignore unavailable", active_language()),
                        str(exc),
                    )

            box.addWidget(button("Quick Ignore a Local File…", quick_ignore_selected_file))
            apply_proposal = QPushButton("Review saved replacement proposal…")
            apply_proposal.setEnabled(bool(proposals) and not self.demo)
            apply_proposal.setToolTip(
                "Uses the last saved proposal. Save edits before reviewing replacement."
            )
            apply_proposal.clicked.connect(
                lambda _checked=False, exact_id=identifier: self.review_sync_replacement(exact_id)
            )
            box.addWidget(apply_proposal)
        elif kind == "forward":
            box.addWidget(label("Actual Mutagen Forwarding Configuration", size=14, bold=True))
            proposals = prefs.get("forward_configuration_proposal", {})
            if not isinstance(proposals, dict):
                proposals = {}
            fields_by_key = {field.key: field for field in FORWARD_CONFIG_FIELDS}
            forward_rows = forward_configuration_rows(sess, proposals)
            config_rows = forward_rows
            config_table = QTableWidget(len(config_rows), 6)
            set_localized_accessible_name(config_table, "Forwarding configuration table")
            config_table.setHorizontalHeaderLabels(
                ["Field", "Native value", "Origin", "Impact", "Capability", "Proposed value"]
            )
            config_table.setWordWrap(True)
            config_table.setMinimumSize(1000, 260)
            config_table.setAlternatingRowColors(True)
            config_table.horizontalHeader().setStretchLastSection(True)
            fill_session_configuration_table(
                config_table,
                forward_rows,
                fields_by_key,
                proposals,
                proposal_tooltip="Local proposal only. CLI, endpoint and platform support must be verified before replacement.",
            )
            box.addWidget(config_table)
            explanation = label(
                "Forwarding settings are current read-only values plus a local proposal. Socket overwrite, owner, group and permissions require verified CLI, endpoint and platform support. Existing sessions stay unchanged.",
                muted=True,
                size=11,
            )
            explanation.setWordWrap(True)
            box.addWidget(explanation)
        controls = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )

        def accept_dialog() -> None:
            if kind in ("sync", "forward"):
                try:
                    proposal_values = {
                        row.key: cast(QTableWidgetItem, config_table.item(row_index, 5)).text()
                        for row_index, row in enumerate(config_rows)
                    }
                    proposal = build_session_configuration_proposal(
                        kind, sess, fields_by_key, proposal_values
                    )
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    QMessageBox.warning(
                        dialog, translate_text("Invalid proposal", active_language()), str(exc)
                    )
                    return
                proposal_key = (
                    "configuration_proposal" if kind == "sync" else "forward_configuration_proposal"
                )
                prefs[proposal_key] = proposal
            dialog.accept()

        controls.accepted.connect(accept_dialog)
        controls.rejected.connect(dialog.reject)
        box.addWidget(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.conf.setdefault("session_prefs", {})[identifier] = {
            "notifications": notifications.isChecked(),
            "note": note.text().strip(),
            **(
                {"configuration_proposal": prefs.get("configuration_proposal", {})}
                if kind == "sync"
                else {}
            ),
            **(
                {"forward_configuration_proposal": prefs.get("forward_configuration_proposal", {})}
                if kind == "forward"
                else {}
            ),
        }
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self.refresh_detail(kind)
        self.add_log("Session settings saved")

    def show_raw_native_session_json(
        self, session: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        dialog = QDialog(parent or self)
        set_localized_title(dialog, "Raw Mutagen session JSON")
        layout = QVBoxLayout(dialog)
        notice = label(
            "Read-only native snapshot. It may include local paths and remote endpoint details.",
            muted=True,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        raw_json = QPlainTextEdit(dialog)
        raw_json.setObjectName("rawNativeSessionJsonSource")
        raw_json.setPlainText(json.dumps(session, ensure_ascii=False, indent=2))
        raw_json.setReadOnly(True)
        raw_json.setAccessibleName(translate_text("Raw Mutagen session JSON", active_language()))
        layout.addWidget(raw_json, 1)
        actions = QHBoxLayout()
        copy_button = button(
            "Copy JSON", lambda: QApplication.clipboard().setText(raw_json.toPlainText())
        )
        copy_button.setObjectName("copyRawNativeSessionJson")
        actions.addWidget(copy_button)
        actions.addWidget(button("Close", dialog.accept))
        layout.addLayout(actions)
        dialog.resize(720, 560)
        dialog.exec()

    def review_sync_replacement(self, session_identifier: str) -> None:
        """Preview and, after explicit consent, replace one eligible sync session."""
        if self.demo or self.pending_action or self.snapshot.sessions_stale:
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text("Refresh current native sessions first.", active_language()),
            )
            return
        observed_at = self.snapshot.sync_observed_at
        if (
            observed_at is None
            or (datetime.now(UTC) - observed_at).total_seconds() > FRESHNESS_SECONDS
        ):
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text(
                    "Session status is stale. Refresh and review again.", active_language()
                ),
            )
            return
        session = next(
            (item for item in self.snapshot.sync if item.get("identifier") == session_identifier),
            None,
        )
        if session is None:
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text("The exact session is no longer loaded.", active_language()),
            )
            return
        labels = session.get("labels", {})
        if not isinstance(labels, dict) or "io.mutagen.project" in labels:
            QMessageBox.warning(
                self,
                translate_text("Replacement unavailable", active_language()),
                translate_text(
                    "Project-owned sessions must be changed through their native project workflow.",
                    active_language(),
                ),
            )
            return
        try:
            provenance = self.session_provenance.get(session_identifier)
            if provenance is None:
                raise ValueError("This session has no verified local creation provenance.")
            prefs = self.conf.get("session_prefs", {}).get(session_identifier, {})
            proposals = prefs.get("configuration_proposal", {}) if isinstance(prefs, dict) else {}
            if not isinstance(proposals, dict) or not proposals:
                raise ValueError("Save at least one configuration proposal before replacement.")
            native_configuration = extract_sync_configuration(session)
            if not native_configuration:
                raise ValueError("Native configuration is missing or has an unknown shape.")
            help_text = self.client.command(["sync", "create", "--help"], timeout=12, readonly=True)
            new_arguments = render_sync_replacement_arguments(
                provenance.create_arguments, proposals, help_text
            )
            new_configuration = json.loads(json.dumps(native_configuration))
            fields = {field.key: field for field in SYNC_CONFIG_FIELDS}
            for key, value in proposals.items():
                field = fields[key]
                target = new_configuration
                for part in field.path[:-1]:
                    if not isinstance(target.get(part), dict):
                        target[part] = {}
                    target = target[part]
                target[field.path[-1]] = value
            snapshot = from_legacy_session("sync", session, measured_at=datetime.now(UTC))
            validation = validate_native_command_snapshot(
                snapshot,
                command_arguments=provenance.create_arguments,
                command_target_identifier=session_identifier,
            )
            preview = build_reconfiguration_preview(
                snapshot,
                new_configuration,
                command_arguments=provenance.create_arguments,
                command_target_identifier=session_identifier,
            )
            if not validation.snapshot_inputs_complete or not preview.changes:
                raise ValueError(
                    "The native snapshot is incomplete, contains unknown fields, or has no effective changes."
                )
            if new_configuration.get("mode") == "one-way-replica":
                raise ValueError(
                    "Replica mode is a destructive R3 change and cannot use this replacement flow."
                )
            plan = self.client.action_planner.prepare(
                ActionRequest(
                    action="sync_reconfigure",
                    target_ids=(session_identifier,),
                    argv=tuple(new_arguments),
                    preflight_fingerprint=preview.source_sha256,
                    capabilities=("sync_reconfigure",),
                )
            )
            changes = "\n".join(
                f"• {change.path}: {change.current!r} → {change.proposed!r}"
                for change in preview.changes
            )
            prompt = (
                f"Replace exact Mutagen session {session_identifier}?\n\n{changes}\n\n"
                "Replacement terminates the old session, clears its sync history, and triggers a rescan. "
                "A best-effort restore runs if creation or verification fails.\n\n"
                + "Command preview: mutagen "
                + " ".join(new_arguments)
            )
            answer = QMessageBox.question(
                self,
                translate_text("Review sync replacement", active_language()),
                prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.client.action_planner.cancel(plan.plan_id)
                return
            plan = self.client.consent_action_plan(plan, consent=True)
        except Exception as exc:
            self.report_error(str(exc))
            return

        request = ReplacementRequest(
            plan=plan,
            previous_session_identifier=session_identifier,
            source_sha256=preview.source_sha256,
            old_create_arguments=provenance.create_arguments,
            new_create_arguments=tuple(new_arguments),
            old_configuration={"configuration": native_configuration},
            new_configuration={"configuration": new_configuration},
            snapshot_validation=validation,
            project_owned=False,
        )
        client = MutagenClient(self.client.binary, action_planner=self.client.action_planner)
        audit_path = settings_path().with_name("session-replacement-audit.jsonl")
        self.pending_action = True

        def execute_replacement() -> ReplacementReceipt:
            def audit(event: ReplacementAuditEvent) -> None:
                record = {
                    "plan_id": event.plan_id,
                    "session_identifier": event.session_identifier,
                    "phase": event.phase,
                    "outcome": event.outcome,
                    "argv_fingerprint": event.argv_fingerprint,
                    "note": event.note,
                    "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                audit_path.parent.mkdir(parents=True, exist_ok=True)
                with audit_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())

            try:
                receipt = replace_non_project_mutagen_session(
                    request, client, consent=True, audit=audit
                )
            except Exception:
                self.client.action_planner.finish(
                    plan.plan_id,
                    verified_target_ids=(),
                    outcome="replacement execution failed; inspect exact-ID audit and refresh",
                )
                raise
            self.client.action_planner.finish(
                plan.plan_id,
                verified_target_ids=plan.target_ids if receipt.verified else (),
                outcome=(
                    f"replacement verified as {receipt.new_session_identifier}"
                    if receipt.verified
                    else "replacement did not verify; inspect restore status and exact-ID audit"
                ),
            )
            return receipt

        def replaced(receipt: ReplacementReceipt) -> None:
            if receipt.verified and receipt.new_session_identifier:
                try:
                    self.session_provenance.record(receipt.new_session_identifier, new_arguments)
                except ProvenanceStoreError as exc:
                    self.add_log("Replacement verified; new provenance was not saved: " + str(exc))
                try:
                    session_prefs = self.conf.setdefault("session_prefs", {})
                    prior_prefs = session_prefs.pop(session_identifier, {})
                    if isinstance(prior_prefs, dict):
                        prior_prefs.pop("configuration_proposal", None)
                        session_prefs[receipt.new_session_identifier] = prior_prefs
                    if session_identifier in self.favorites["sync"]:
                        self.favorites["sync"].discard(session_identifier)
                        self.favorites["sync"].add(receipt.new_session_identifier)
                        self.conf["favorites"] = {
                            kind: sorted(ids) for kind, ids in self.favorites.items()
                        }
                    write_settings(self.conf)
                except (OSError, TypeError, ValueError) as exc:
                    self.add_log(
                        "Replacement verified; local note/favorite migration failed: " + str(exc)
                    )
                self.add_log(
                    f"Replaced exact session {session_identifier} with {receipt.new_session_identifier}."
                )
            else:
                self.add_log(
                    "Replacement did not verify. Restore session: "
                    + str(receipt.restored_session_identifier or "unverified")
                    + "; recovery uncertain: "
                    + str(receipt.recovery_uncertain)
                )
            self.refresh(force=True)

        self.submit(
            execute_replacement,
            replaced,
            lambda error: self.report_error(str(error)),
            lambda: setattr(self, "pending_action", False),
        )

    def new_current_session(self) -> None:
        page = self.pages.currentIndex()
        if page in (1, 2):
            self.create_session("sync" if page == 1 else "forward")

    def toggle_favorite(self, kind: str) -> None:
        session = self.selected_session(kind)
        if not session:
            return
        identifier = str(session.get("identifier") or "")
        if not identifier:
            return
        favorite_ids = self.favorites[kind]
        if identifier in favorite_ids:
            favorite_ids.remove(identifier)
        else:
            favorite_ids.add(identifier)
        self.conf["favorites"] = {k: sorted(ids) for k, ids in self.favorites.items()}
        try:
            write_settings(self.conf)
        except OSError as exc:
            self.report_error(str(exc))
            return
        self._table_signatures.pop(kind, None)
        self._table_signatures.pop("dashboard", None)
        self.fill_table(
            self.sync_table if kind == "sync" else self.forward_table,
            self.snapshot.sync if kind == "sync" else self.snapshot.forward,
            kind,
        )
        self.filter_table(kind)
        self.refresh_detail(kind)

    def copy_session_id(self, kind: str) -> None:
        sess = self.selected_session(kind)
        if sess:
            QApplication.clipboard().setText(str(sess.get("identifier", "")))
            self.add_log("Session identifier copied to clipboard")

    def export_session_json(self, kind: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text(
                "Export Session (may contain server names and paths)", active_language()
            ),
            "mutagen-session.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(sess, indent=2, ensure_ascii=False), encoding="utf-8")
            self.add_log("Session JSON export complete")
        except OSError as exc:
            self.report_error(str(exc))

    def session_context_menu(self, kind: str, point: QPoint) -> None:
        table = self.sync_table if kind == "sync" else self.forward_table
        item = table.itemAt(point)
        if not item:
            return
        table.selectRow(item.row())
        sess = self.selected_session(kind)
        if not sess:
            return
        menu = QMenu(table)
        favorite_text = (
            "★ Remove from Favorites"
            if sess.get("identifier") in self.favorites[kind]
            else "☆ Add to Favorites"
        )
        menu.addAction(
            translate_text(favorite_text, active_language()),
            lambda: self.toggle_favorite(kind),
        )
        menu.addAction(
            translate_text("Copy ID", active_language()), lambda: self.copy_session_id(kind)
        )
        menu.addAction(
            translate_text("Export JSON", active_language()) + "…",
            lambda: self.export_session_json(kind),
        )
        menu.addSeparator()
        if not self.demo:
            if sess.get("paused"):
                menu.addAction(
                    translate_text("Resume", active_language()),
                    lambda: self.session_action(kind, "resume"),
                )
            else:
                menu.addAction(
                    translate_text("Pause", active_language()),
                    lambda: self.session_action(kind, "pause"),
                )
            if kind == "sync":
                menu.addAction(
                    translate_text("Sync Now", active_language()),
                    lambda: self.session_action(kind, "flush"),
                )
                startup_text = (
                    "Enable Start at Sign-In"
                    if sess.get("paused")
                    else "Disable Start at Sign-In (Pause)"
                )
                menu.addAction(
                    translate_text(startup_text, active_language()),
                    self.toggle_sync_startup,
                )
        menu.exec(table.viewport().mapToGlobal(point))

    def endpoints_page(self) -> QScrollArea:
        """Both endpoints as reported by Mutagen itself. Nover open an extra connection."""
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 3, 3, 15)
        layout.setSpacing(17)
        intro, il = card()
        il.addWidget(label("Both Endpoint Statuses from the Mutagen Daemon", size=18, bold=True))
        information = label(
            "ALPHA/BETA data come from the local Mutagen daemon through 'mutagen sync list'. "
            "No additional SSH/HTTP connections are made, nothing is installed on the server, and no service is started. "
            "The remote mutagen-agent communicates only with its existing Mutagen daemon.",
            muted=True,
            size=12,
        )
        information.setWordWrap(True)
        il.addWidget(information)
        chooser = QHBoxLayout()
        chooser.addWidget(label("Session:", muted=True))
        self.endpoint_combo = QComboBox()
        self.endpoint_combo.setMinimumWidth(460)
        self.endpoint_combo.setEditable(True)
        self.endpoint_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        set_localized_placeholder(
            self.endpoint_combo.lineEdit(), "Search name, status, server, or path…"
        )
        completer = cast(QCompleter, self.endpoint_combo.completer())
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.endpoint_combo.currentIndexChanged.connect(self.update_endpoint_details)
        set_localized_tooltip(
            self.endpoint_combo,
            "Search by name, status, server, or path. Select a session for ALPHA/BETA details.",
        )
        chooser.addWidget(self.endpoint_combo, 1)
        ep_refresh_btn = button("↻ Refresh from Mutagen", lambda: self.refresh(force=True))
        set_localized_tooltip(
            ep_refresh_btn, "Immediately refreshes status from the local Mutagen daemon."
        )
        chooser.addWidget(ep_refresh_btn)
        il.addLayout(chooser)
        self.endpoint_status = label("Waiting for information from the local daemon.", muted=True)
        self.endpoint_status.setWordWrap(True)
        il.addWidget(self.endpoint_status)
        layout.addWidget(intro)
        panes = QHBoxLayout()
        panes.setSpacing(14)
        self.endpoint_cards: dict[str, dict[str, Any]] = {}
        for side in ("left", "right"):
            f, l = card()
            title = label("ALPHA" if side == "left" else "BETA", size=18, bold=True)
            address = label("—", muted=True)
            address.setWordWrap(True)
            conn = label("—", size=17, bold=True)
            stats = label("—", muted=True, size=12)
            stats.setWordWrap(True)
            issues = label("—", muted=True, size=12)
            issues.setWordWrap(True)
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.hide()
            stage = label("—", muted=True, size=11)
            stage.setWordWrap(True)
            for el in (title, address, separator(), conn, stats, issues, progress, stage):
                l.addWidget(el)
            l.addStretch()
            self.endpoint_cards[side] = dict(
                title=title,
                address=address,
                conn=conn,
                stats=stats,
                issues=issues,
                progress=progress,
                stage=stage,
            )
            panes.addWidget(f, 1)
        layout.addLayout(panes)
        bottom, bl = card()
        bl.addWidget(label("Sync Session Overview", size=15, bold=True))
        self.endpoint_session_info = label("—", muted=True)
        self.endpoint_session_info.setWordWrap(True)
        bl.addWidget(self.endpoint_session_info)
        layout.addWidget(bottom)
        explanation, el = card()
        el.addWidget(label("What Mutagen Does Not Provide", size=15, bold=True))
        note = label(
            "This view does not measure the server's overall CPU, RAM, disk, or network use, or detailed "
            "internal logs from the remote agent. This information is not included in the standard "
            "Mutagen output and cannot be reliably obtained without additional remote access. "
            "File counts are from the latest known scans, not guaranteed live counters.",
            muted=True,
            size=11,
        )
        note.setWordWrap(True)
        el.addWidget(note)
        layout.addWidget(explanation)
        layout.addStretch()
        page.setWidget(body)
        return page

    def update_endpoint_sessions(self, snapshot: Snapshot) -> None:
        if not hasattr(self, "endpoint_combo"):
            return
        options = [("sync", x) for x in snapshot.sync] + [("forward", x) for x in snapshot.forward]
        current = self.endpoint_combo.currentData()
        entries = []
        for kind, session in options:
            sid = str(session.get("identifier") or "")
            kind_name = "SYNC" if kind == "sync" else "PORT"
            name = session.get("name") or sid[:22]
            _, status = classify(session, kind)
            status = translate_text(status, self.ui_language)
            source = endpoint_text(session.get("alpha" if kind == "sync" else "source"), kind)
            target = endpoint_text(session.get("beta" if kind == "sync" else "destination"), kind)
            text = f"{kind_name} · {name} · {status} · {source} → {target}"
            entries.append((kind, sid, text, f"{text}\nID: {sid}"))
        keys = [(kind, sid) for kind, sid, _, _ in entries]
        old = [self.endpoint_combo.itemData(i) for i in range(self.endpoint_combo.count())]
        old_labels = [self.endpoint_combo.itemText(i) for i in range(self.endpoint_combo.count())]
        labels = [text for _, _, text, _ in entries]
        if keys != old or labels != old_labels:
            self.endpoint_combo.blockSignals(True)
            self.endpoint_combo.clear()
            for kind, sid, text, tooltip in entries:
                index = self.endpoint_combo.count()
                self.endpoint_combo.addItem(text, (kind, sid))
                self.endpoint_combo.setItemData(index, tooltip, Qt.ItemDataRole.ToolTipRole)
            if current in keys:
                self.endpoint_combo.setCurrentIndex(keys.index(current))
            self.endpoint_combo.blockSignals(False)
        if self.pages.currentIndex() == 9 or keys != old or labels != old_labels:
            self.update_endpoint_details()

    def update_endpoint_details(self, *_args: object) -> None:
        if not hasattr(self, "endpoint_combo"):
            return
        key = self.endpoint_combo.currentData()
        session = None
        if key:
            kind, identifier = key
            group = self.snapshot.sync if kind == "sync" else self.snapshot.forward
            session = next((s for s in group if s.get("identifier") == identifier), None)
        if not session:
            set_localized_text(
                self.endpoint_status,
                "The Mutagen daemon returned no sessions."
                if self.snapshot.daemon
                else "The local Mutagen daemon is unavailable.",
            )
            set_localized_text(self.endpoint_session_info, "—")
            for view in self.endpoint_cards.values():
                set_localized_text(view["address"], "—")
                set_localized_text(view["conn"], "Unavailable")
                set_localized_text(view["stats"], "—")
                set_localized_text(view["issues"], "—")
                view["progress"].hide()
                set_localized_text(view["stage"], "—")
            return
        data = inspect_session(session, kind)
        endpoint_status = f"{data['name']} · {data['state_text']} · status from the local daemon"
        endpoint_status_cs = (
            f"{data['name']} · {translate_text(data['state_text'], 'cs')} · "
            f"{translate_text('status from the local daemon', 'cs')}"
        )
        set_localized_text(self.endpoint_status, endpoint_status, czech=endpoint_status_cs)
        for side, endpoint in (("left", data["left"]), ("right", data["right"])):
            widgets = self.endpoint_cards[side]
            widgets["title"].setText(endpoint.side)
            widgets["address"].setText(endpoint.address)
            set_localized_text(
                widgets["conn"], "● Connected" if endpoint.connected else "● Disconnected"
            )
            widgets["conn"].setStyleSheet(
                f"color:{TEAL if endpoint.connected else AMBER};font-size:17px;font-weight:700"
            )
            if kind == "sync":

                def count(number: int | float | None) -> str:
                    return "—" if number is None else f"{number:,}".replace(",", " ")

                scan = (
                    ("Yes" if endpoint.scanned else "No")
                    if endpoint.scanned is not None
                    else "Unknown"
                )
                widgets["stats"].setText(
                    f"Scan complete: {scan}    •    Files: {count(endpoint.files)}\n"
                    f"Directories: {count(endpoint.directories)}    •    Symlinks: {count(endpoint.symlinks)}\n"
                    f"Total file size: {human_bytes(endpoint.total_file_size) if endpoint.total_file_size is not None else '—'}"
                )
                widgets["issues"].setText(
                    f"Scan issues: {endpoint.scan_problems}    •    Transition issues: {endpoint.transition_problems}"
                )
                if endpoint.staging_percent is not None:
                    widgets["progress"].setValue(round(endpoint.staging_percent))
                    widgets["progress"].show()
                else:
                    widgets["progress"].hide()
                if endpoint.staging_path or endpoint.staging_percent is not None:
                    widgets["stage"].setText(
                        f"Receiving: {endpoint.staging_path or 'file'}\n"
                        f"{human_bytes(endpoint.staging_bytes)} / {human_bytes(endpoint.staging_expected_bytes)}"
                        f" · {endpoint.staging_files}/{endpoint.staging_expected_files} files"
                    )
                else:
                    set_localized_text(
                        widgets["stage"], "No active file transfer is currently reported."
                    )
            else:
                set_localized_text(
                    widgets["stats"],
                    "Port forwarding — Mutagen reports only endpoint connection status.",
                )
                set_localized_text(
                    widgets["issues"], "Traffic details are available for the session as a whole."
                )
                widgets["progress"].hide()
                set_localized_text(widgets["stage"], "—")
        if kind == "sync":
            lines = [
                f"Successful cycles: {data['successful_cycles']}    •    Conflicts: {data['conflicts']}"
            ]
        else:
            lines = [
                f"Open connections: {data['open_connections']}    •    Total connections: {data['total_connections']}",
                f"Data to destination: {human_bytes(data['total_outbound_data'])}    •    Back: {human_bytes(data['total_inbound_data'])}",
            ]
        if data["last_error"]:
            lines.append("Last error: " + data["last_error"][:1200])
        self.endpoint_session_info.setText("\n".join(lines))

    def servers_page(self) -> QScrollArea:
        """Server grouping is based exclusively on endpoint URLs in local Mutagen data."""
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        root = QWidget()
        root.setObjectName("scrollbody")
        layout = QVBoxLayout(root)
        layout.setSpacing(15)
        layout.setContentsMargins(0, 3, 0, 0)
        top, tl = card()
        tl.addWidget(label("Server Groups", size=18, bold=True))
        desc = label(
            "Hosts are identified from Mutagen ALPHA/BETA and source/destination addresses. "
            "No new SSH connections or server service are used. An alias for the same server may be recognized as a different host.",
            muted=True,
            size=11,
        )
        desc.setWordWrap(True)
        tl.addWidget(desc)
        choose = QHBoxLayout()
        choose.addWidget(label("Action Scope:"))
        self.server_selector = QComboBox()
        add_localized_item(self.server_selector, "All Sessions", "__all__")
        self.server_selector.currentIndexChanged.connect(self.update_server_details)
        choose.addWidget(self.server_selector, 1)
        choose.addWidget(button("↻ Refresh", lambda: self.refresh(force=True)))
        tl.addLayout(choose)
        self.server_overview = self.make_table(
            ["SERVER", "SYNC", "PORTS", "PAUSED", "ISSUES"], 175, stretch_columns=(0,)
        )
        self.server_overview.setMinimumHeight(0)
        self.server_overview.setMaximumHeight(16777215)
        self.server_overview.cellDoubleClicked.connect(self.pick_server_row)
        tl.addWidget(self.server_overview)
        layout.addWidget(top)
        actions, ac = card()
        self.server_scope_label = label("Select a server or all sessions", size=15, bold=True)
        ac.addWidget(self.server_scope_label)
        first = QHBoxLayout()
        b_srv_sync = button(
            "↻ Sync now", partial(self.bulk_action, "sync", "flush", "server"), kind="primary"
        )
        set_localized_tooltip(
            b_srv_sync, "Starts an immediate sync cycle for all sessions in the selected group."
        )
        first.addWidget(b_srv_sync)
        b_srv_pause = button(
            "⏸ Pause Sync Sessions", partial(self.bulk_action, "sync", "pause", "server")
        )
        set_localized_tooltip(b_srv_pause, "Pauses all sync sessions in the selected group.")
        first.addWidget(b_srv_pause)
        b_srv_resume = button(
            "▶ Resume Sync Sessions", partial(self.bulk_action, "sync", "resume", "server")
        )
        set_localized_tooltip(b_srv_resume, "Resumes paused sync sessions in the selected group.")
        first.addWidget(b_srv_resume)
        first.addStretch()
        ac.addLayout(first)
        second = QHBoxLayout()
        b_fwd_pause = button(
            "⏸ Pause Forwards", partial(self.bulk_action, "forward", "pause", "server")
        )
        set_localized_tooltip(b_fwd_pause, "Pauses all port forwards in the selected group.")
        second.addWidget(b_fwd_pause)
        b_fwd_resume = button(
            "▶ Resume Forwards", partial(self.bulk_action, "forward", "resume", "server")
        )
        set_localized_tooltip(b_fwd_resume, "Resumes paused port forwards in the selected group.")
        second.addWidget(b_fwd_resume)
        second.addStretch()
        ac.addLayout(second)
        advanced = button("More Bulk Actions ▾", self.show_server_advanced_actions)
        set_localized_tooltip(
            advanced, "Shows more bulk actions: terminate sessions, reset, and group diagnostics."
        )
        ac.addWidget(advanced)
        warning = label(
            "Bulk commands use only the selected IDs. Pausing and resuming take effect immediately "
            "and also affect these sessions after the daemon's next start. "
            "To start at Windows sign-in, register the daemon on the Daemon page.",
            muted=True,
            size=11,
        )
        warning.setWordWrap(True)
        ac.addWidget(warning)
        layout.addWidget(actions)
        listings, ls = card()
        ls.addWidget(
            label("Sync sessions in the selected group · double-click to view details", muted=True)
        )
        self.server_sync_table = self.make_table(
            ["SESSION", "STATUS", "ALPHA", "BETA"], 155, stretch_columns=(0, 2, 3)
        )
        self.server_sync_table.setMinimumHeight(0)
        self.server_sync_table.setMaximumHeight(16777215)
        self.server_sync_table.cellDoubleClicked.connect(
            lambda row, col: self.open_group_session("sync", row)
        )
        ls.addWidget(self.server_sync_table)
        self.server_sync_empty = label("This server has no sync sessions.", muted=True)
        ls.addWidget(self.server_sync_empty)
        ls.addWidget(label("Forwarding sessions in the selected group", muted=True))
        self.server_forward_table = self.make_table(
            ["SESSION", "STATUS", "SOURCE", "DESTINATION"], 130, stretch_columns=(0, 2, 3)
        )
        self.server_forward_table.setMinimumHeight(0)
        self.server_forward_table.setMaximumHeight(16777215)
        self.server_forward_table.cellDoubleClicked.connect(
            lambda row, col: self.open_group_session("forward", row)
        )
        ls.addWidget(self.server_forward_table)
        self.server_forward_empty = label("This server has no port forwards.", muted=True)
        ls.addWidget(self.server_forward_empty)
        layout.addWidget(listings, 1)
        page.setWidget(root)
        return page

    def pick_server_row(self, row: int, col: int) -> None:
        item = self.server_overview.item(row, 0)
        if item:
            index = self.server_selector.findData(item.data(Qt.ItemDataRole.UserRole))
            if index >= 0:
                self.server_selector.setCurrentIndex(index)

    def update_server_groups(self) -> None:
        if not hasattr(self, "server_selector"):
            return
        groups = group_servers(self.snapshot.sync, self.snapshot.forward)
        self._server_groups = {g.key: g for g in groups}
        current = self.server_selector.currentData()
        choices = [("All Sessions", "__all__")] + [(g.name, g.key) for g in groups]
        visible_choices = [
            (translate_text(name, self.ui_language) if key == "__all__" else name, key)
            for name, key in choices
        ]
        if visible_choices != [
            (self.server_selector.itemText(i), self.server_selector.itemData(i))
            for i in range(self.server_selector.count())
        ]:
            self.server_selector.blockSignals(True)
            self.server_selector.clear()
            for name, key in choices:
                if key == "__all__":
                    add_localized_item(self.server_selector, name, key)
                else:
                    self.server_selector.addItem(name, key)
            found = self.server_selector.findData(current)
            self.server_selector.setCurrentIndex(max(0, found))
            self.server_selector.blockSignals(False)
        filter_widget = self.sync_server_filter
        filter_val = filter_widget.currentData()
        if visible_choices != [
            (filter_widget.itemText(i), filter_widget.itemData(i))
            for i in range(filter_widget.count())
        ]:
            filter_widget.blockSignals(True)
            filter_widget.clear()
            for name, key in choices:
                if key == "__all__":
                    add_localized_item(filter_widget, name, key)
                else:
                    filter_widget.addItem(name, key)
            found = filter_widget.findData(filter_val)
            filter_widget.setCurrentIndex(max(0, found))
            filter_widget.blockSignals(False)
            self.filter_table("sync")
        view = self.server_overview
        view.setSortingEnabled(False)
        view.setUpdatesEnabled(False)
        try:
            view.setRowCount(len(groups))
            for row, group in enumerate(groups):
                values = [
                    group.name,
                    str(len(group.sync_ids)),
                    str(len(group.forward_ids)),
                    str(group.paused),
                    str(group.errors),
                ]
                for col, value in enumerate(values):
                    item = view.item(row, col)
                    if item is None:
                        item = QTableWidgetItem(value)
                        view.setItem(row, col, item)
                    elif item.text() != value:
                        item.setText(value)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, group.key)
        finally:
            view.setUpdatesEnabled(True)
        self.fit_table_to_rows(view)
        if self.pages.currentIndex() == 10:
            self.update_server_details()

    def server_targets(self, kind: str, scope: str) -> list[dict[str, Any]]:
        sessions = self.snapshot.sync if kind == "sync" else self.snapshot.forward
        if scope == "all":
            return list(sessions)
        key = self.server_selector.currentData() if hasattr(self, "server_selector") else "__all__"
        if key == "__all__":
            return list(sessions)
        return [session for session in sessions if key in session_servers(session, kind)]

    def update_server_details(self, *_args: object) -> None:
        if not hasattr(self, "server_selector"):
            return
        selection_key = self.server_selector.currentData()
        selection_name = (
            "All Sessions" if selection_key == "__all__" else self.server_selector.currentText()
        )
        sync = self.server_targets("sync", "server")
        forward = self.server_targets("forward", "server")
        sync_noun = "session" if len(sync) == 1 else "sessions"
        forward_noun = "port forward" if len(forward) == 1 else "port forwards"
        sync_form = _czech_plural(len(sync), ("relace", "relace", "relací"))
        forward_form = _czech_plural(len(forward), ("přesměrování", "přesměrování", "přesměrování"))
        set_localized_text(
            self.server_scope_label,
            f"{selection_name} · {len(sync)} sync {sync_noun} · {len(forward)} {forward_noun}",
            czech=f"{translate_text(selection_name, 'cs')} · {len(sync)} {sync_form} · {len(forward)} {forward_form}",
        )
        self.server_sync_empty.setVisible(not sync)
        self.server_forward_empty.setVisible(not forward)
        for kind, sessions, table in (
            ("sync", sync, self.server_sync_table),
            ("forward", forward, self.server_forward_table),
        ):
            table.setSortingEnabled(False)
            table.setRowCount(len(sessions))
            for row, sess in enumerate(sessions):
                state = classify(sess, kind)[1]
                cols = [
                    sess.get("name") or str(sess.get("identifier"))[:20],
                    state,
                    endpoint_text(sess.get("alpha" if kind == "sync" else "source"), kind),
                    endpoint_text(sess.get("beta" if kind == "sync" else "destination"), kind),
                ]
                for col, value in enumerate(cols):
                    item = table.item(row, col)
                    if item is None:
                        item = QTableWidgetItem()
                        table.setItem(row, col, item)
                    item.setText(str(value))
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, sess.get("identifier"))
            self.fit_table_to_rows(table)

    def open_group_session(self, kind: str, row: int) -> None:
        listing = self.server_sync_table if kind == "sync" else self.server_forward_table
        item = listing.item(row, 0)
        if not item:
            return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        self.set_page(1 if kind == "sync" else 2)
        if kind == "sync":
            self.sync_server_filter.setCurrentIndex(0)
            self.sync_search.clear()
            self.sync_state_filter.setCurrentIndex(0)
            self.sync_favorites_only.setChecked(False)
        else:
            self.forward_search.clear()
            self.forward_state_filter.setCurrentIndex(0)
            self.forward_favorites_only.setChecked(False)
        table = self.sync_table if kind == "sync" else self.forward_table
        for index in range(table.rowCount()):
            current = table.item(index, 0)
            if current and current.data(Qt.ItemDataRole.UserRole) == identifier:
                table.selectRow(index)
                table.scrollToItem(current)
                break

    def show_server_advanced_actions(self) -> None:
        """Keep reset/termination out of the one-click toolbar."""
        menu = QMenu(self)
        menu.addAction(
            translate_text("Reset Sync History…", active_language()),
            lambda: self.bulk_action("sync", "reset", "server"),
        )
        menu.addSeparator()
        menu.addAction(
            translate_text("Permanently Terminate Sync Sessions…", active_language()),
            lambda: self.bulk_action("sync", "terminate", "server"),
        )
        menu.addAction(
            translate_text("Permanently Terminate Forwards…", active_language()),
            lambda: self.bulk_action("forward", "terminate", "server"),
        )
        menu.exec(self.cursor().pos())

    def bulk_action(self, kind: str, action: str, scope: str = "all") -> None:
        if self.demo or self.pending_action:
            return
        candidates = self.server_targets(kind, scope)
        if action == "flush" or action == "pause":
            candidates = [s for s in candidates if not s.get("paused")]
        elif action == "resume":
            candidates = [
                s
                for s in candidates
                if s.get("paused") or classify(s, kind)[0] in ("error", "idle")
            ]
        ids = [str(s.get("identifier") or "") for s in candidates]
        ids = list(dict.fromkeys(identifier for identifier in ids if identifier))
        if not ids:
            QMessageBox.information(
                self,
                translate_text("No Sessions", active_language()),
                translate_text("No eligible sessions for this action.", active_language()),
            )
            return
        action_name = {
            "flush": "Run Sync Cycle Now",
            "pause": "Pause",
            "resume": "Resume",
            "reset": "Reset History",
            "terminate": "Terminate",
        }[action]
        group_name = "all sessions" if scope == "all" else self.server_selector.currentText()
        body = f"{action_name} {len(ids)} selected sessions ({group_name})?"
        action_spec = ACTION_SPECS.get(f"{kind}_{action}")
        if action_spec is not None:
            body += f"\n\n{translate_text(action_spec.description, active_language())} · {action_spec.risk}"
        if action == "flush":
            body += "\n\nThis starts a sync cycle and does not wait for all transfers to finish."
        if action in ("pause", "resume"):
            body += "\n\nThis changes the current session status and their behavior at the daemon's next start."
        if action in ("reset", "terminate"):
            body += "\n\nThis may change sync history or permanently terminate sessions."
        preview_args = [kind, action]
        if kind == "sync" and action == "flush":
            preview_args.append("--skip-wait")
        preview_args.extend(ids)
        language = active_language()
        body += "\n\n" + translate_text("Exact session IDs:", language) + "\n" + "\n".join(ids)
        body += "\n\n" + translate_text("Command preview: {command}", language).format(
            command="mutagen " + " ".join(preview_args)
        )
        choice = QMessageBox.question(
            self,
            translate_text("Confirm Bulk Action", active_language()),
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        if action in ("reset", "terminate"):
            expected = "RESET" if action == "reset" else "TERMINATE"
            value, accepted = QInputDialog.getText(
                self,
                translate_text("Second Confirmation", active_language()),
                translate_text(
                    "To confirm this action for {count} sessions, type {expected}:",
                    active_language(),
                ).format(count=len(ids), expected=expected),
            )
            if not accepted or value.strip() != expected:
                return
        self.pending_action = True
        self.add_log(f"Bulk action: {kind} {action} · {len(ids)} explicit IDs")
        client = MutagenClient(self.client.binary, action_planner=self.action_planner)
        candidates_by_id = {
            str(session.get("identifier") or ""): session
            for session in candidates
            if str(session.get("identifier") or "") in ids
        }
        selected_records = [candidates_by_id[identifier] for identifier in ids]
        preflight_fingerprint = session_preflight_fingerprint(selected_records)

        def success(output: str) -> None:
            self.add_log(f"Bulk action submitted: {action}, {len(ids)} sessions")
            if output:
                self.add_log(output[:1000])

        def done() -> None:
            self.pending_action = False
            self.refresh(force=True)

        self.submit(
            lambda: client.execute_many(
                kind,
                action,
                ids,
                operator_consent=True,
                expected_preflight_fingerprint=preflight_fingerprint,
            ),
            success,
            self.report_error,
            done,
        )

    def toggle_sync_startup(self) -> None:
        """Native semantics: Mutagen persists paused/unpaused state across daemon restarts."""
        if self.demo or self.pending_action:
            return
        session = self.selected_session("sync")
        if not session:
            return
        ident = str(session.get("identifier") or "")
        if not ident:
            return
        if not session.get("paused"):
            if self.snapshot.registration != "registered":
                answer = QMessageBox.question(
                    self,
                    translate_text("Enable Start at Sign-In?", active_language()),
                    translate_text(
                        "Sync is running, but automatic start of the Mutagen daemon is not registered. Register the daemon to start at Windows sign-in? This also affects other active sessions.",
                        active_language(),
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.run_command("daemon", "register")
                return
            choice = QMessageBox.question(
                self,
                translate_text("Turn Off Sync Start?", active_language()),
                translate_text(
                    "Mutagen has no separate option to ‘not start next time but keep running now’. Turning this off therefore pauses the session immediately. Resume?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.run_command("sync", "pause", target=ident)
            return
        needs_registration = self.snapshot.registration != "registered"
        if needs_registration:
            response = QMessageBox.question(
                self,
                translate_text("Registrovat start Mutagen daemonu?", active_language()),
                translate_text(
                    "For sessions to resume at sign-in, the Mutagen daemon itself must be registered. Registration also affects other unpaused sessions. Register the daemon and resume this sync now?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        self.run_command("sync", "resume", target=ident, register_before=needs_registration)

    def monitoring_page(self) -> QScrollArea:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 3, 3, 18)
        layout.setSpacing(18)
        control, cl = card()
        heading = QHBoxLayout()
        heading.addWidget(label("Resource and Traffic Trends", size=17, bold=True))
        heading.addStretch()
        heading.addWidget(label("Show:", muted=True))
        self.monitor_range = QComboBox()
        for title, hours in [
            ("5 minutes", 5 / 60),
            ("30 minutes", 0.5),
            ("2 hours", 2),
            ("12 hours", 12),
            ("24 hours", 24),
            ("48 hours", 48),
        ]:
            self.monitor_range.addItem(title, hours)
        self.monitor_range.setCurrentIndex(1)
        self.monitor_range.currentIndexChanged.connect(
            lambda _=None: self.refresh_charts(force=True)
        )
        heading.addWidget(self.monitor_range)
        self.monitor_live_button = button("⏸ Freeze Graphs", self.toggle_charts)
        set_localized_tooltip(
            self.monitor_live_button, "Stops automatic graph updates for easier viewing"
        )
        heading.addWidget(self.monitor_live_button)
        png_btn = button("Save PNG", self.export_monitor_png)
        set_localized_tooltip(png_btn, "Saves the currently displayed graphs as a PNG image")
        heading.addWidget(png_btn)
        csv_btn = button("Export CSV", self.export_metrics, kind="primary")
        set_localized_tooltip(
            csv_btn, "Exports measured data to a CSV file for analysis in another tool"
        )
        heading.addWidget(csv_btn)
        cl.addLayout(heading)
        cl.addWidget(
            label(
                "Data are stored locally for 48 hours. Graphs show actual measurements; "
                "history has a gap while the application is closed.",
                muted=True,
                size=11,
            )
        )
        self.gui_usage_label = label(
            "Application load: waiting for measurements", muted=True, size=11
        )
        cl.addWidget(self.gui_usage_label)
        layout.addWidget(control)
        stats_panel, stats_layout = card()
        stats_layout.addWidget(
            label("Selected Period Summary · Actual Measurements", size=15, bold=True)
        )
        self.stats_label = localized_label("Waiting for data…")
        self.stats_label.setTextFormat(Qt.TextFormat.PlainText)
        self.stats_label.setWordWrap(True)
        self.stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_panel)
        self.monitor_graphs = {}
        self.monitor_labels = {}
        chart_specs = [
            ("cpu", "CPU", "Local Mutagen process usage (may exceed 100%)", BLUE, None, "percent"),
            ("memory", "RAM", "Resident memory of local processes", TEAL, None, "memory"),
            (
                "disk",
                "Process Disk I/O",
                "Read (blue) · write (green); values depend on the operating system",
                BLUE,
                TEAL,
                "bytes_s",
            ),
            (
                "traffic",
                "Forwarded Data",
                "Outbound (blue) · inbound (green); based on cumulative forward-session counters",
                BLUE,
                TEAL,
                "bytes_s",
            ),
            ("sessions", "Session Status", "Active (green) · issues (red)", TEAL, RED, "number"),
        ]
        for index in range(0, len(chart_specs), 2):
            line = QHBoxLayout()
            line.setSpacing(14)
            for key, title, subtitle, color, secondary, unit in chart_specs[index : index + 2]:
                panel, content = card()
                top = QHBoxLayout()
                top.addWidget(label(title, size=15, bold=True))
                top.addStretch()
                val = label("—", muted=True, size=12)
                self.monitor_labels[key] = val
                top.addWidget(val)
                content.addLayout(top)
                content.addWidget(label(subtitle, muted=True, size=10))
                graph = Graph(color, panel, unit=unit, secondary=secondary)
                graph.setMinimumHeight(205)
                content.addWidget(graph)
                self.monitor_graphs[key] = graph
                line.addWidget(panel, 1)
            if len(chart_specs[index : index + 2]) == 1:
                line.addStretch(1)
            layout.addLayout(line)
        process_card, process_l = card()
        process_l.addWidget(label("Individual Local Mutagen Processes", size=16, bold=True))
        process_l.addWidget(
            label("Usage is measured per process, not per sync session.", muted=True)
        )
        self.process_table = self.make_table(
            ["PID", "PROCESS", "CPU", "RAM", "READ", "WRITE"], height=180, stretch_columns=(1,)
        )
        self.process_table.setMinimumHeight(0)
        self.process_table.setMaximumHeight(16777215)
        process_l.addWidget(self.process_table)
        layout.addWidget(process_card)
        layout.addStretch()
        page.setWidget(body)
        return page

    def toggle_charts(self) -> None:
        self.chart_frozen = not self.chart_frozen
        self.monitor_live_button.setText(
            "▶ Resume Graph Updates" if self.chart_frozen else "⏸ Freeze Graphs"
        )
        if not self.chart_frozen:
            self.refresh_charts(force=True)

    def export_monitor_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Save Current Graphs to PNG", active_language()),
            "mutagen-monitoring.png",
            translate_text("PNG (*.png)", active_language()),
        )
        if not path:
            return
        # Export exactly what is visible on the monitoring page: all five graphs.
        # Render full scroll-area contents, including off-screen cards.
        # The QScrollArea owns the real visual body via its widget().
        scroll = self.pages.widget(6)
        body = scroll.widget()
        image = QPixmap(body.size())
        image.fill(QColor(BG))
        body.render(image)
        if not image.save(path, "PNG"):
            self.report_error("Could not save PNG image.")
        else:
            self.add_log("Monitoring saved as PNG")

    def export_metrics(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export monitoringu", active_language()),
            "mutagen-metrics.csv",
            translate_text("CSV (*.csv)", active_language()),
        )
        if not path:
            return
        try:
            self.history.export_csv(path, hours=float(self.monitor_range.currentData()))
            self.add_log("Monitoring history exported to CSV")
        except (sqlite3.Error, OSError) as exc:
            self.report_error(str(exc))

    def diagnostics_page(self) -> QWidget:
        root = QWidget()
        root.setObjectName("main")
        l = QVBoxLayout(root)
        l.setContentsMargins(0, 3, 0, 0)
        l.setSpacing(16)
        card1, vl = card()
        head = QHBoxLayout()
        head.addWidget(label("Diagnostics Overview", size=17, bold=True))
        head.addStretch()
        conflicts_btn = button("Conflict Inspector · Read only", self.open_conflict_inspector)
        set_localized_tooltip(
            conflicts_btn, "Inspect native conflict details; this view cannot resolve conflicts"
        )
        head.addWidget(conflicts_btn)
        safe_btn = button("Safe JSON Report", self.export_safe_report, kind="primary")
        set_localized_tooltip(
            safe_btn, "Exports diagnostics without actual paths or addresses — safe to share"
        )
        head.addWidget(safe_btn)
        full_btn = button("Support Bundle", self.open_support_bundle)
        set_localized_text(full_btn, "Support Bundle", czech="Balíček podpory")
        support_tooltip = "Choose a safe report, previewed full snapshot, or local session logs"
        support_tooltip_cs = "Vyberte bezpečný report, náhled úplného snímku nebo místní protokoly"
        full_btn.setProperty("mutauiSourceTooltip", support_tooltip)
        full_btn.setProperty("mutauiCzechTooltip", support_tooltip_cs)
        full_btn.setToolTip(support_tooltip_cs if active_language() == "cs" else support_tooltip)
        head.addWidget(full_btn)
        copy_btn = button("Copy Summary", self.copy_diagnostics)
        set_localized_tooltip(copy_btn, "Copies the diagnostic summary to the clipboard")
        head.addWidget(copy_btn)
        vl.addLayout(head)
        note_lbl = label(
            "The full export includes actual endpoints, paths, and errors. Review it before sharing.",
            muted=True,
        )
        note_lbl.setWordWrap(True)
        vl.addWidget(note_lbl)
        self.diag_summary = localized_label("Waiting for data…")
        self.diag_summary.setWordWrap(True)
        self.diag_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.diag_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        vl.addWidget(self.diag_summary)
        l.addWidget(card1)
        problems, pl = card()
        problems_head = QHBoxLayout()
        problems_head.addWidget(label("Conflicts, Errors, and Issues", size=16, bold=True))
        problems_head.addStretch()
        self.diag_problem_count = label("", muted=True, size=11)
        problems_head.addWidget(self.diag_problem_count)
        pl.addLayout(problems_head)
        self.diagnostics_view = QTextBrowser()
        self.diagnostics_view.setOpenExternalLinks(True)
        self.diagnostics_view.setStyleSheet(
            f"font-family:Consolas,monospace;font-size:12px;background:#0A1421;color:{TEXT};"
        )
        pl.addWidget(self.diagnostics_view)
        l.addWidget(problems, 1)
        return root

    def open_conflict_inspector(self) -> None:
        sessions = []
        for raw in self.snapshot.sync:
            if not isinstance(raw, dict) or not isinstance(raw.get("identifier"), str):
                continue
            observed_at = self.snapshot.sync_observed_at
            sessions.append(
                from_legacy_session(
                    "sync",
                    raw,
                    measured_at=observed_at or datetime(2000, 1, 1, tzinfo=UTC),
                    stale_reason=(
                        "Native snapshot is stale or has no observation timestamp"
                        if self.snapshot.sessions_stale or observed_at is None
                        else None
                    ),
                )
            )
        ConflictInspectorDialog(
            sessions,
            self,
            audit_path=settings_path().with_name("mutagen-remote-inspection.jsonl"),
            recommendation_path=settings_path().with_name("conflict-recommendations.json"),
        ).exec()

    def _start_initial_refresh(self) -> None:
        self._initial_refresh_pending = False
        if not self.pending_poll:
            self.refresh(force=True)

    def _has_authoritative_session_lists(self) -> bool:
        return self.demo or bool(
            self.snapshot.daemon
            and not self.snapshot.sessions_stale
            and self.snapshot.sync_observed_at is not None
            and self.snapshot.forward_observed_at is not None
        )

    def _complete_pending_launch_requests(self) -> None:
        if not self._pending_launch_requests:
            return
        pending = self._pending_launch_requests
        self._pending_launch_requests = []
        if not self._has_authoritative_session_lists():
            message = translate_text(
                "A current session list is unavailable. Refresh status and retry.",
                active_language(),
            )
            for request in pending:
                title = "Open folder" if request.get("command") == "open_folder" else "Open session"
                QMessageBox.information(self, translate_text(title, active_language()), message)
            return
        for request in pending:
            self.handle_launch_request(request)

    def handle_launch_request(self, message: Mapping[str, object]) -> None:
        """Route a validated local CLI or single-instance request in the UI thread."""
        command = message.get("command")
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if (
            command in {"open_folder", "open_session"}
            and not self._has_authoritative_session_lists()
        ):
            self._pending_launch_requests.append(dict(message))
            if not self.pending_poll and not self._initial_refresh_pending:
                self.refresh(force=True)
            return
        if command == "focus":
            return
        if command == "doctor":
            self.set_page(7)
            return
        if command == "open_project":
            from mutaui.ui.project_viewer import NativeProjectViewerDialog

            path = Path(str(message.get("path", ""))).expanduser().absolute()
            if path.name.casefold() not in {"mutagen.yml", "mutagen.yaml"}:
                QMessageBox.warning(
                    self,
                    translate_text("Open project", active_language()),
                    translate_text("Choose a mutagen.yml or mutagen.yaml file.", active_language()),
                )
                return
            dialog = NativeProjectViewerDialog(
                path,
                parent=self,
                executor=LegacyMutagenExecutor(self.client) if self.client.binary else None,
                audit_path=settings_path().with_name("mutagen-project-actions.jsonl"),
            )
            dialog.exec()
            return
        if command == "open_folder":
            from mutaui.services.path_lookup import find_local_sessions_for_path

            snapshots = []
            observed_at = self.snapshot.sync_observed_at
            for raw in self.snapshot.sync:
                if isinstance(raw, dict) and isinstance(raw.get("identifier"), str):
                    snapshots.append(
                        from_legacy_session(
                            "sync",
                            raw,
                            measured_at=observed_at or datetime(2000, 1, 1, tzinfo=UTC),
                            stale_reason=(
                                "stale"
                                if self.snapshot.sessions_stale or observed_at is None
                                else None
                            ),
                        )
                    )
            identifiers = find_local_sessions_for_path(snapshots, str(message.get("path", "")))
            if len(identifiers) != 1:
                detail = (
                    "No current local sync root contains this path."
                    if not identifiers
                    else "Path belongs to multiple sync sessions; choose an exact session ID:\n"
                    + "\n".join(identifiers)
                )
                QMessageBox.information(
                    self, translate_text("Open folder", active_language()), detail
                )
                return
            command = "open_session"
            message = {"command": command, "session_id": identifiers[0]}
        if command == "open_session":
            identifier = message.get("session_id")
            found = [
                ("sync", row)
                for row in self.snapshot.sync
                if isinstance(row, dict) and row.get("identifier") == identifier
            ] + [
                ("forward", row)
                for row in self.snapshot.forward
                if isinstance(row, dict) and row.get("identifier") == identifier
            ]
            if len(found) != 1:
                QMessageBox.information(
                    self,
                    translate_text("Open session", active_language()),
                    translate_text(
                        "Exact session ID is unavailable or ambiguous in the latest snapshot.",
                        active_language(),
                    ),
                )
                return
            kind, _row = found[0]
            self.current_kind = kind
            self.current_id = str(identifier)
            self.set_page(1 if kind == "sync" else 2)
            table = self.sync_table if kind == "sync" else self.forward_table
            row_index = table.model().row_for_identifier(str(identifier))
            if row_index >= 0:
                table.selectRow(row_index)
            self.refresh_detail(kind)

    def update_diagnostics(self, snap: Snapshot) -> None:
        summary = (
            f"Mutagen: {snap.binary or 'not found'}\nVersion: {snap.version or 'unknown'}\n"
            f"Daemon: {'online' if snap.daemon else 'offline'}\n"
            f"Mutagen processes: {snap.processes} | CPU: {snap.cpu:.1f} % | RAM: {human_bytes(snap.memory)}\n"
            f"Sync sessions: {len(snap.sync)} | Forwarding: {len(snap.forward)}\n"
            f"Daemon autostart: {snap.registration}"
        )
        if snap.error:
            summary += "\nCLI error: " + snap.error
        self.diag_summary.setText(summary)
        sessions = []
        observed_sessions: tuple[
            tuple[Literal["sync", "forward"], list[dict[str, Any]], datetime | None], ...
        ] = (
            ("sync", snap.sync, snap.sync_observed_at),
            ("forward", snap.forward, snap.forward_observed_at),
        )
        for kind, rows, observed_at in observed_sessions:
            for raw in rows:
                if not isinstance(raw, dict) or not isinstance(raw.get("identifier"), str):
                    continue
                sessions.append(
                    from_legacy_session(
                        kind,
                        raw,
                        measured_at=observed_at or datetime(2000, 1, 1, tzinfo=UTC),
                        stale_reason=(
                            "Native snapshot is stale or has no observation timestamp"
                            if snap.sessions_stale or observed_at is None
                            else None
                        ),
                    )
                )
        report = diagnose_sessions(
            SessionDoctorContext(
                cli_available=bool(snap.binary),
                daemon_running=snap.daemon,
                sync_observed_at=snap.sync_observed_at,
                forward_observed_at=snap.forward_observed_at,
                sessions=tuple(sessions),
                version=snap.version or None,
                snapshot_error=snap.error,
                sessions_stale=snap.sessions_stale,
                cpu_percent=snap.cpu,
                resource_observed_at=snap.resource_observed_at,
            )
        )
        self._safe_problem_codes = tuple(
            sorted({issue.code for issue in report.issues if isinstance(issue.code, str)})
        )
        failed_sessions = {
            issue.session_identifier
            for issue in report.issues
            if issue.session_identifier
            and issue.severity == "error"
            and issue.certainty == "confirmed"
        }
        health_now = time.monotonic()
        health_results = []
        for session in sessions:
            session_kind = session.identity.kind
            source_timestamp = (
                snap.sync_observed_at if session_kind == "sync" else snap.forward_observed_at
            )
            timestamp_age = (
                (datetime.now().astimezone() - source_timestamp).total_seconds()
                if source_timestamp is not None
                else None
            )
            if (
                session.stale_reason is not None
                or timestamp_age is None
                or not 0 <= timestamp_age <= FRESHNESS_SECONDS
            ):
                continue
            observation_key = (
                f"{session_kind}:{source_timestamp.isoformat()}"
                if source_timestamp is not None
                else f"{session_kind}:stale"
            )
            raw_status = session.native_config.get("status")
            paused = session.native_config.get("paused") is True
            scan_in_progress = raw_status in (7, "7") or "scan" in session.state.casefold()
            health_results.append(
                self.health_tracker.observe(
                    HealthObservation(
                        session_identifier=session.identity.identifier,
                        observation_key=observation_key,
                        observed_at=session.measured_at,
                        state=session.state,
                        confirmed_failure=session.identity.identifier in failed_sessions,
                        intentional_pause=paused,
                        scan_in_progress=scan_in_progress,
                        command_duration_seconds=snap.command_durations.get(f"{session_kind} list"),
                    ),
                    now=health_now,
                )
            )
        notes = [
            "Authoritative snapshot: "
            + ("yes" if report.authoritative else "NO — refresh required"),
            f"Sessions assessed: {report.session_count}; findings: {report.issue_count}",
            f"Health mode: {self.health_tracker.policy.mode}",
        ]
        snapshot_time_key = (snap.sync_observed_at, snap.forward_observed_at)
        if report.authoritative and snapshot_time_key != self._doctor_observation_key:
            if self._doctor_observation_key is not None:
                self._doctor_previous_issue_count = self._doctor_current_issue_count
            self._doctor_observation_key = snapshot_time_key
            self._doctor_current_issue_count = report.issue_count
        if not report.authoritative:
            notes.append("Trend: unavailable; snapshot is stale or incomplete")
        elif self._doctor_previous_issue_count is None:
            notes.append("Trend: baseline; next complete snapshot enables comparison")
        else:
            previous = self._doctor_previous_issue_count
            trend = (
                "unchanged"
                if report.issue_count == previous
                else "increased"
                if report.issue_count > previous
                else "decreased"
            )
            notes.append(f"Trend: {trend} ({previous} → {report.issue_count} findings)")
        severity_counts: dict[str, int] = {}
        for issue in report.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        notes.append(
            "Severity summary: "
            + (
                ", ".join(f"{severity}={count}" for severity, count in severity_counts.items())
                or "none"
            )
        )
        affected: dict[str, int] = {}
        for issue in report.issues:
            name = issue.session_identifier or "Mutagen / global"
            affected[name] = affected.get(name, 0) + 1
            stamp = (
                issue.observed_at.isoformat(timespec="seconds") if issue.observed_at else "unknown"
            )
            notes.extend(
                [
                    f"[{issue.severity.upper()} / {issue.certainty}] {issue.code} — {name}",
                    f"  {issue.explanation} (evidence: {stamp})",
                    *(
                        [f"  Detail: {issue.technical_detail[:500]}"]
                        if issue.technical_detail
                        else []
                    ),
                    *[f"  Safe next step: {action}" for action in issue.suggested_actions],
                    *([f"  Help: {issue.article_url}"] if issue.article_url else []),
                ]
            )
        for health in health_results:
            success_age = (
                "unknown"
                if health.last_success_at is None
                else f"{max(0.0, health_now - health.last_success_at):.0f}s ago"
            )
            duration = (
                "unknown"
                if health.last_command_duration_seconds is None
                else f"{health.last_command_duration_seconds:.2f}s"
            )
            notes.append(
                f"[HEALTH] {health.session_identifier}: {health.state}; "
                f"confirmed error streak={health.error_streak}; reconnects={health.reconnect_count}; "
                f"last healthy observation={success_age}; latest list command={duration}"
            )
            if health.incident_id:
                notes.append(f"  Incident: {health.incident_id}")
            for transition in health.transitions[-5:]:
                previous_state = transition.from_state or "initial"
                notes.append(
                    f"  Transition: {previous_state} → {transition.to_state} "
                    f"({transition.observed_at.isoformat(timespec='seconds')})"
                )
            if health.environment_event:
                notes.append(f"  Environment grace: {health.environment_event}")
            if health.recommend_manual_action:
                notes.append("  Assisted recommendation is ready; no recovery action was executed.")
        notes.append(
            "Per-session finding counts: "
            + (", ".join(f"{name}={count}" for name, count in affected.items()) or "none")
        )
        formatted_notes = []
        for line in notes:
            if line.startswith("  Help: "):
                url = line.removeprefix("  Help: ")
                safe_url = html_escape(url, quote=True)
                formatted_notes.append(
                    f'&nbsp;&nbsp;Help: <a href="{safe_url}">{html_escape(url)}</a>'
                )
            else:
                formatted_notes.append(html_escape(line))
        self.diagnostics_view.setHtml("<br>".join(formatted_notes))
        if hasattr(self, "diag_problem_count"):
            if report.issue_count:
                n = len(
                    {
                        issue.session_identifier
                        for issue in report.issues
                        if issue.session_identifier
                    }
                )
                n += int(any(issue.session_identifier is None for issue in report.issues))
                self.diag_problem_count.setText(
                    f"⚠  {report.issue_count} findings · {n} affected session(s)"
                )
                self.diag_problem_count.setStyleSheet(f"color:{RED};font-size:11px;")
            elif not report.authoritative:
                set_localized_text(self.diag_problem_count, "?  snapshot unknown or stale")
                self.diag_problem_count.setStyleSheet(f"color:{AMBER};font-size:11px;")
            else:
                set_localized_text(self.diag_problem_count, "✓  no findings in recent snapshot")
                self.diag_problem_count.setStyleSheet(f"color:{TEAL};font-size:11px;")

    def export_safe_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Safe Diagnostics Report", active_language()),
            "mutagen-safe-report.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        try:
            events = self.history.events(limit=500)
            data = safe_diagnostic_report(
                self.snapshot,
                application_version=APP_VERSION,
                qt_version=qVersion(),
                problem_codes=getattr(self, "_safe_problem_codes", ()),
                build_id=os.environ.get("GITHUB_RUN_ID"),
                recent_event_count=len(events),
                event_count_capped=len(events) == 500,
            )
            data["resource_summary"] = self.history.statistics(hours=1)
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Safe diagnostics report saved (no paths or addresses)")
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))

    def open_support_bundle(self) -> None:
        try:
            events = self.history.events(limit=500)
            snapshot_payload = self._full_snapshot_payload()
            dialog = SupportBundleDialog(
                snapshot_preview=json.dumps(snapshot_payload, ensure_ascii=False, indent=2),
                event_count=len(events),
                monitored_line_count=len(self.tail_lines),
                parent=self,
            )
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        mode = dialog.mode.currentData()
        if mode == "safe":
            self.export_safe_report()
        elif mode == "full":
            self.export_snapshot(snapshot_payload=snapshot_payload)
        elif mode == "self_check":
            self.run_local_self_check()
        else:
            self.export_session_log_snapshot(
                include_event_messages=dialog.include_event_messages.isChecked(),
                include_monitored_log_lines=dialog.include_monitored_log_lines.isChecked(),
            )

    def run_local_self_check(self) -> None:
        try:
            mutagen_version = self.client.get_version()
        except Exception:
            mutagen_version = "unavailable"
        result = local_self_check(
            app_path=Path(sys.executable if getattr(sys, "frozen", False) else __file__),
            settings_path=settings_path(),
            history=self.history,
            qt_version=qVersion(),
            mutagen_version=mutagen_version,
        )
        checks = result["checks"]
        czech = active_language().casefold().startswith("cs")
        labels = {
            "application_path": "Cesta aplikace" if czech else "Application path",
            "settings_path": "Cesta nastavení" if czech else "Settings path",
            "history_database": "Databáze historie" if czech else "History database",
            "python": "Python",
            "qt": "Qt",
            "mutagen_cli": "Mutagen CLI",
        }
        statuses = {
            "ok": "v pořádku" if czech else "ok",
            "warning": "upozornění" if czech else "warning",
            "error": "chyba" if czech else "error",
        }
        detail_translation = {
            "found": "nalezeno",
            "missing": "nenalezeno",
            "directory writable": "adresář je zapisovatelný",
            "directory unavailable or read-only": "adresář není dostupný nebo je jen pro čtení",
            "unavailable": "nedostupné",
        }
        lines = []
        for name, check in checks.items():
            detail = check["detail"]
            if czech:
                detail = detail_translation.get(detail, detail)
            lines.append(f"{labels[name]}: {statuses[check['status']]} ({detail})")
        lines.append("Vzdálené zápisy: ne" if czech else "Remote writes: no")
        title = "Místní kontrola aplikace" if czech else "Local application self-check"
        QMessageBox.information(self, title, "\n".join(lines))

    def _full_snapshot_payload(self) -> dict[str, Any]:
        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "daemon": self.snapshot.daemon,
            "version": self.snapshot.version,
            "binary": self.snapshot.binary,
            "error": self.snapshot.error,
            "registration": self.snapshot.registration,
            "sync": self.snapshot.sync,
            "forward": self.snapshot.forward,
        }

    def export_session_log_snapshot(
        self,
        *,
        include_event_messages: bool = False,
        include_monitored_log_lines: bool = False,
    ) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Session Log Snapshot", active_language()),
            "mutagen-session-logs.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        if (include_event_messages or include_monitored_log_lines) and (
            QMessageBox.question(
                self,
                translate_text("Sensitive Log Details", active_language()),
                translate_text(
                    "Selected log text may contain local paths, hostnames, usernames, or credentials. Save only to a local file you control. Continue?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            events = self.history.events(limit=500)
            data = session_log_report(
                events,
                list(self.tail_lines),
                include_event_messages=include_event_messages,
                include_monitored_log_lines=include_monitored_log_lines,
            )
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Session log snapshot saved locally")
        except (OSError, sqlite3.Error) as exc:
            self.report_error(str(exc))

    def copy_diagnostics(self) -> None:
        QApplication.clipboard().setText(
            self.diag_summary.text() + "\n\n" + self.diagnostics_view.toPlainText()
        )
        self.add_log("Diagnostics summary copied")

    def export_snapshot(self, *, snapshot_payload: dict[str, Any] | None = None) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export diagnostiky", active_language()),
            "mutagen-snapshot.json",
            translate_text("JSON (*.json)", active_language()),
        )
        if not path:
            return
        if (
            QMessageBox.question(
                self,
                translate_text("Sensitive Snapshot", active_language()),
                translate_text(
                    "This full snapshot can contain local paths, SSH hosts, usernames, and session names. Only save or share it with people you trust. Continue?",
                    active_language(),
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        data = snapshot_payload if snapshot_payload is not None else self._full_snapshot_payload()
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.add_log("Diagnostics export complete")
        except OSError as exc:
            self.report_error(str(exc))

    def check_alerts(self, snap: Snapshot) -> None:
        check_session_alerts(
            self,
            snap,
            classify_session=classify,
            quiet_hours=quiet_hours_active,
        )

    def create_session(self, kind: str) -> None:
        if self.demo:
            QMessageBox.information(
                self,
                translate_text("Demo", active_language()),
                translate_text("Actions are disabled in demo mode.", active_language()),
            )
            return
        if not self.client.binary:
            QMessageBox.warning(
                self,
                translate_text("Mutagen not found", active_language()),
                translate_text("First, configure mutagen.exe in Settings.", active_language()),
            )
            self.set_page(5)
            return
        profile_load = load_profile_store(settings_path().with_name("connection-profiles.json"))
        if not profile_load.valid:
            QMessageBox.warning(
                self,
                translate_text("Connection Profiles Unavailable", active_language()),
                "Local profiles were left unchanged and will not be applied to this session.\n\n"
                + "\n".join(profile_load.warnings),
            )
        dlg = SessionDialog(
            kind,
            self,
            default_profile=self.conf.get("new_sync_profile", "default"),
            ui_mode=self.ui_mode,
            executable=self.client.binary or "mutagen",
            saved_profiles=profile_load.profiles if profile_load.valid else (),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.run_command(
                kind,
                "create",
                options=dlg.arguments(),
                backup_choice=dlg.backup_choice,
            )

    def session_action(self, kind: str, action: str) -> None:
        sess = self.selected_session(kind)
        if not sess:
            return
        self.run_command(kind, action, target=sess.get("identifier", ""))

    def daemon_action(self, action: str) -> None:
        self.run_command("daemon", action)

    def run_command(
        self,
        kind: str,
        action: str,
        target: str = "",
        options: list[str] | None = None,
        register_before: bool = False,
        backup_choice: str | None = None,
    ) -> None:
        if self.demo or self.pending_action:
            return
        client = MutagenClient(self.client.binary, action_planner=self.action_planner)
        create_plan = None
        daemon_plan = None
        register_plan = None
        expected_preflight_fingerprint = ""
        if action == "create" and kind in {"sync", "forward"}:
            try:
                create_plan = client.prepare_create_plan(
                    kind,
                    options or [],
                    backup_choice=backup_choice,
                )
            except Exception as exc:
                self.report_error(str(exc))
                return
        if kind == "daemon":
            try:
                daemon_plan = client.prepare_daemon_plan(action)
            except Exception as exc:
                self.report_error(str(exc))
                return
            language = active_language()
            preview_lines = [
                f"{translate_text(daemon_plan.description, language)} · {daemon_plan.risk}",
                translate_text("Command preview: {command}", language).format(
                    command="mutagen " + " ".join(daemon_plan.argv)
                ),
            ]
            if action == "stop":
                preview_lines.append(
                    translate_text(
                        "Stopping interrupts all sync and forwarding sessions managed by this daemon.",
                        language,
                    )
                )
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", language),
                "\n\n".join(preview_lines),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.action_planner.cancel(daemon_plan.plan_id)
                return
            typed_confirmation = None
            if daemon_plan.requires_typed_confirmation:
                typed_confirmation, accepted = QInputDialog.getText(
                    self,
                    translate_text("Second Confirmation", language),
                    translate_text(
                        "To confirm this destructive action, type {expected}:", language
                    ).format(expected=daemon_plan.typed_confirmation),
                )
                if not accepted:
                    self.action_planner.cancel(daemon_plan.plan_id)
                    return
            try:
                daemon_plan = client.consent_action_plan(
                    daemon_plan,
                    consent=True,
                    typed_confirmation=typed_confirmation,
                )
            except Exception as exc:
                self.report_error(str(exc))
                return
        if create_plan is not None:
            language = active_language()
            preview = "\n".join(
                (
                    f"{translate_text(create_plan.description, language)} · {create_plan.risk}",
                    translate_text("Command preview: {command}", language).format(
                        command="mutagen " + " ".join(create_plan.argv)
                    ),
                    (
                        translate_text("A recoverable destination backup was confirmed.", language)
                        if create_plan.backup_required
                        else ""
                    ),
                )
            )
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", language),
                preview,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.action_planner.cancel(create_plan.plan_id)
                return
            typed_confirmation = None
            if create_plan.requires_typed_confirmation:
                typed_confirmation, accepted = QInputDialog.getText(
                    self,
                    translate_text("Second Confirmation", language),
                    translate_text(
                        "To confirm this destructive action, type {expected}:", language
                    ).format(expected=create_plan.typed_confirmation),
                )
                if not accepted:
                    self.action_planner.cancel(create_plan.plan_id)
                    return
            try:
                create_plan = client.consent_action_plan(
                    create_plan,
                    consent=True,
                    typed_confirmation=typed_confirmation,
                    backup_choice=backup_choice,
                )
            except Exception as exc:
                self.report_error(str(exc))
                return
        if kind in {"sync", "forward"} and target and action != "create":
            current_sessions = getattr(self.snapshot, kind, [])
            selected = [
                session
                for session in current_sessions
                if str(session.get("identifier") or "") == target
            ]
            if not selected:
                QMessageBox.information(
                    self,
                    translate_text("Refresh Required", active_language()),
                    translate_text(
                        "The exact session is not in the current snapshot. Refresh before retrying.",
                        active_language(),
                    ),
                )
                return
            expected_preflight_fingerprint = session_preflight_fingerprint(selected)
            action_key = f"{kind}_{action}"
            spec = ACTION_SPECS.get(action_key)
            if spec is None:
                self.report_error("This session action has no registered risk policy.")
                return
            language = active_language()
            effects = {
                "reset": "Mutagen may rescan and reevaluate file changes after clearing history.",
                "terminate": "This ends the session; files at both endpoints remain.",
            }
            effect = effects.get(action)
            preview = "\n".join(
                [
                    f"{translate_text(spec.description, language)} · {spec.risk}",
                    translate_text("Exact session identifier: {identifier}", language).format(
                        identifier=target
                    ),
                    translate_text("Command preview: {command}", language).format(
                        command="mutagen " + " ".join((kind, action, target))
                    ),
                ]
                + ([translate_text(effect, language)] if effect else [])
            )
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", active_language()),
                preview,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if register_before:
            try:
                register_plan = client.prepare_daemon_plan("register")
            except Exception as exc:
                self.report_error(str(exc))
                return
            language = active_language()
            answer = QMessageBox.question(
                self,
                translate_text("Review Planned Action", language),
                "\n\n".join(
                    (
                        f"{translate_text(register_plan.description, language)} · {register_plan.risk}",
                        translate_text("Command preview: {command}", language).format(
                            command="mutagen " + " ".join(register_plan.argv)
                        ),
                        translate_text(
                            "Registration affects every unpaused Mutagen session for this user.",
                            language,
                        ),
                    )
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.action_planner.cancel(register_plan.plan_id)
                return
            try:
                register_plan = client.consent_action_plan(register_plan, consent=True)
            except Exception as exc:
                self.report_error(str(exc))
                return
        self.pending_action = True
        self.add_log(
            f"Running: mutagen {kind} {action}" + (" (selected session)" if target else "")
        )
        if expected_preflight_fingerprint:
            self.add_log("Action preview approved: mutagen " + " ".join((kind, action, target)))
        if create_plan is not None:
            self.add_log("Action preview approved: mutagen " + " ".join(create_plan.argv))

        def do() -> str:
            if register_plan is not None:
                client.execute(
                    "daemon",
                    "register",
                    operator_consent=True,
                    action_plan=register_plan,
                )
            return client.execute(
                kind,
                action,
                target,
                options,
                operator_consent=True,
                expected_preflight_fingerprint=expected_preflight_fingerprint,
                action_plan=daemon_plan or create_plan,
            )

        def success(output: str) -> None:
            created = getattr(client, "last_created_session", None)
            if created is not None:
                created_kind, created_id, create_arguments = created
                try:
                    self.session_provenance.record(created_id, create_arguments)
                except ProvenanceStoreError as exc:
                    self.add_log(
                        "Created session verified, but replacement provenance was not saved: "
                        + str(exc)
                    )
                else:
                    self.add_log(
                        f"Saved local creation provenance for {created_kind} session {created_id}"
                    )
            if output:
                self.add_log(output[:1800])
            self.add_log(f"Completed: {kind} {action}")

        def error(message: str) -> None:
            self.report_error(message)

        def done() -> None:
            self.pending_action = False
            QTimer.singleShot(450, lambda: self.refresh(force=True))

        self.submit(do, success, error, done)

    def report_error(self, message: str) -> None:
        self.add_log("ERROR: " + message)
        QMessageBox.critical(self, translate_text("Mutagen — Error", active_language()), message)

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.update_polling_mode()

    def quit_app(self) -> None:
        if self.pending_action:
            QMessageBox.information(
                self,
                translate_text("Mutagen Command in Progress", active_language()),
                translate_text("Wait for the current command to finish first.", active_language()),
            )
            self.show_window()
            return
        self.tail_timer.stop()
        self._allow_exit = True
        self.tray.hide()
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.pending_action and self._allow_exit:
            event.ignore()
            QMessageBox.information(
                self,
                translate_text("Mutagen Command in Progress", active_language()),
                translate_text("Wait for the current command to finish first.", active_language()),
            )
            return
        if (
            self.conf.get("tray", True)
            and QSystemTrayIcon.isSystemTrayAvailable()
            and not self._allow_exit
        ):
            self.hide()
            event.ignore()
        else:
            self.tail_timer.stop()
            if hasattr(self, "metric_timer"):
                self.metric_timer.stop()
            if hasattr(self, "timer"):
                self.timer.stop()
            if self.workers:
                self._shutdown_pending = True
                self.statusBar().showMessage(
                    translate_text(
                        "Waiting for background tasks to finish before closing…",
                        active_language(),
                    )
                )
                event.ignore()
                return
            if self.recorder is not None:
                self.recorder.close(timeout=8)
            with suppress(sqlite3.Error):
                self.history.close()
            self._shutdown_pending = False
            event.accept()
            QApplication.instance().quit()


def main() -> int:
    from mutaui.services.command_line import parse_launch_command

    launch = parse_launch_command(sys.argv[1:])
    if launch.version:
        print(APP_VERSION)
        return 0
    if launch.linux_file_manager_action:
        from mutaui.services.linux_file_manager_integration import (
            IntegrationError,
            install_linux_file_manager_integration,
            remove_linux_file_manager_integration,
        )

        try:
            if launch.linux_file_manager_action == "install":
                if sys.platform != "linux":
                    raise IntegrationError("Linux only: file-manager integration is unavailable.")
                if not getattr(sys, "frozen", False):
                    raise IntegrationError(
                        "Install the packaged AppImage first; source-mode integration is unsupported."
                    )
                result = install_linux_file_manager_integration(sys.executable)
            else:
                result = remove_linux_file_manager_integration()
        except IntegrationError as exc:
            print(f"Mutagen Control: {exc}", file=sys.stderr)
            return 2
        print(f"Mutagen Control Linux integration: {result}")
        return 0
    self_test = launch.self_test
    if self_test:
        # A packaged EXE can prove it can load Qt and construct every page,
        # without touching the user's live Mutagen sessions.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import tempfile
        import traceback
        from pathlib import Path

        result_path = Path(
            os.environ.get(
                "MUTAUI_SELF_TEST_LOG",
                str(Path(tempfile.gettempdir()) / "mutagen-control-self-test.log"),
            )
        )
        result_path.write_text("Self-test started.\n", encoding="utf-8")
    # Windows taskbar icon groups the application with its native window.
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MutagenControl.Desktop")
        except Exception:
            pass
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Mutagen Control")
    app.setOrganizationName("MutagenControl")
    app.setQuitOnLastWindowClosed(False)
    if self_test:
        window = None
        try:
            result_path.write_text("Qt initialized; building demo window.\n", encoding="utf-8")
            history_path = os.environ.get("MUTAUI_SELF_TEST_HISTORY_PATH")
            window = (
                MainWindow(demo=True)
                if history_path is None
                else MainWindow(demo=True, history_path=history_path)
            )
            expected_theme = os.environ.get("MUTAUI_SELF_TEST_EXPECT_RECOVERED_THEME")
            if expected_theme is not None:
                recovery_was_reported = any(
                    "restored from the last valid settings backup" in warning.casefold()
                    for warning in window.settings_load.warnings
                )
                if not recovery_was_reported or window.conf.get("theme") != expected_theme:
                    raise AssertionError(
                        "Packaged settings recovery did not restore the expected state."
                    )
            if history_path is not None and window.history.path != str(Path(history_path)):
                raise AssertionError(
                    "Packaged self-test did not open the requested history database."
                )
            result_path.write_text("Demo window built; rendering pages.\n", encoding="utf-8")
            window.show()
            app.processEvents()
            window.apply_snapshot(window.snapshot)
            for index in range(window.pages.count()):
                window.set_page(index)
                app.processEvents()
            result_path.write_text("Pages rendered; checking server groups.\n", encoding="utf-8")
            import shiboken6

            assert shiboken6.isValid(window.cpu_chart)
            assert shiboken6.isValid(window.mem_chart)
            assert shiboken6.isValid(window.register_message)
            window.set_page(10)
            for index in range(window.server_selector.count()):
                window.server_selector.setCurrentIndex(index)
                assert window.server_sync_table.rowCount() == len(
                    window.server_targets("sync", "server")
                )
                assert window.server_forward_table.rowCount() == len(
                    window.server_targets("forward", "server")
                )
            exit_code = 0
        except Exception:
            result_path.write_text(traceback.format_exc(), encoding="utf-8")
            exit_code = 1
        finally:
            if window is not None:
                # A demo page may enqueue an action callback while Qt events
                # are pumped; self-test has no operator to answer its dialog.
                window.pending_action = False
                window._allow_exit = True
                window.close()
        if exit_code == 0:
            suffix = " Settings recovery and file-backed history reopened." if history_path else ""
            result_path.write_text(
                f"OK: UI pages and server groups rendered.{suffix}\n", encoding="utf-8"
            )
        # The windowed PyInstaller bootloader can retain worker threads after
        # the test window closes; explicit process status is the CI contract.
        os._exit(exit_code)
    from mutaui.services.instance_lifecycle import (
        InstanceLifecycleError,
        SingleInstanceBroker,
    )

    broker = SingleInstanceBroker()
    try:
        primary = broker.start_or_forward(launch.instance_message())
    except InstanceLifecycleError as exc:
        print(f"Mutagen Control: {exc}", file=sys.stderr)
        return 2
    if not primary:
        return 0
    window = MainWindow(demo=launch.demo)
    from mutaui.services.power_events import install_platform_power_event_monitor

    window._power_event_monitor = install_platform_power_event_monitor(
        app,
        lambda event: window.health_tracker.note_environment_event(event, now=time.monotonic()),
    )
    if window._power_event_monitor is not None and hasattr(window._power_event_monitor, "stop"):
        app.aboutToQuit.connect(window._power_event_monitor.stop)
    broker.request_received.connect(window.handle_launch_request)
    window.show()
    if launch.command != "focus":
        window.handle_launch_request(launch.instance_message())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
