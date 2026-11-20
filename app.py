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
import traceback
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
QListWidget::item:selected {{ background:#1D4B47; color:{TEXT}; }}
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
QPushButton#nav:checked {{ background: #173A35; border-color: #36685F; color: {TEXT}; font-weight: 800; }}
QPushButton#nav:focus {{ border-color: {BLUE}; }}
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


from mutaui.ui.localization import (
    _LOCALIZED_ITEM_ROLE,
    set_localized_accessible_name,
    set_localized_placeholder,
    set_localized_text,
    set_localized_title,
    set_localized_tooltip,
)
from mutaui.ui.session_dialog import SessionDialog, configure_settings_path_provider
from mutaui.ui.widgets.graph import Graph
from mutaui.ui.widgets.health_ring import HealthRing
from mutaui.ui.widgets.session_table import SessionTableModel

configure_settings_path_provider(lambda: settings_path())


import types

from mutaui.ui.controllers import (
    DiagnosticsMixin,
    MonitoringMixin,
    OnboardingMixin,
    PagesMixin,
    ServersEndpointsMixin,
    SessionActionsMixin,
    SettingsBundleMixin,
)
from mutaui.ui.formatters import (
    _czech_plural,
    field_format,
    localized_action,
    read_settings,
    readable_record_lines,
    separator,
    session_detail_html,
    settings_warning_message,
    write_settings,
)
from mutaui.ui.quick_navigator import QuickNavigator
from mutaui.ui.support_bundle_dialog import SupportBundleDialog

__all__ = [
    "ACTION_SPECS",
    "ADVANCED_ROUTE_IDS",
    "APP_VERSION",
    "ActionPlanner",
    "ActionRequest",
    "AdaptivePolling",
    "AlertEngine",
    "Any",
    "AsyncRecorder",
    "CLIDiscovery",
    "Callable",
    "ConflictInspectorDialog",
    "ConnectionProfile",
    "ConnectionProfileStore",
    "ConnectionProfilesDialog",
    "DiagnosticsMixin",
    "FORWARD_CONFIG_FIELDS",
    "FRESHNESS_SECONDS",
    "FileTail",
    "ForwardConfigField",
    "ForwardConfigRow",
    "ForwardTrafficMeter",
    "Graph",
    "HealthObservation",
    "HealthPolicy",
    "HealthRing",
    "HealthTracker",
    "HistoryStore",
    "IgnorePresetError",
    "IgnorePresetManagerDialog",
    "IgnorePresetStore",
    "Iterable",
    "LazyStackedWidget",
    "LegacyMutagenExecutor",
    "Literal",
    "MainWindow",
    "Mapping",
    "MonitoringMixin",
    "MutagenClient",
    "MutagenError",
    "NativeProjectManagerDialog",
    "OnboardingMixin",
    "PAGE_ROUTES",
    "PROFILES",
    "PagesMixin",
    "PollBackoff",
    "PortableBundleError",
    "PortableImportPreviewDialog",
    "PreferencesController",
    "ProcessSampler",
    "ProvenanceStoreError",
    "QAbstractItemView",
    "QAbstractTableModel",
    "QAction",
    "QApplication",
    "QBrush",
    "QCheckBox",
    "QCloseEvent",
    "QColor",
    "QComboBox",
    "QCompleter",
    "QDesktopServices",
    "QDialog",
    "QDialogButtonBox",
    "QEvent",
    "QFileDialog",
    "QFormLayout",
    "QFrame",
    "QGridLayout",
    "QHBoxLayout",
    "QHeaderView",
    "QHideEvent",
    "QIcon",
    "QInputDialog",
    "QKeySequence",
    "QLabel",
    "QLayout",
    "QLineEdit",
    "QLinearGradient",
    "QListWidget",
    "QListWidgetItem",
    "QMainWindow",
    "QMenu",
    "QMessageBox",
    "QModelIndex",
    "QPainter",
    "QPainterPath",
    "QPen",
    "QPixmap",
    "QPlainTextEdit",
    "QPoint",
    "QPointF",
    "QProgressBar",
    "QPushButton",
    "QRectF",
    "QScrollArea",
    "QShortcut",
    "QShowEvent",
    "QSizePolicy",
    "QSpinBox",
    "QSystemTrayIcon",
    "QTableView",
    "QTableWidget",
    "QTableWidgetItem",
    "QTextBrowser",
    "QThreadPool",
    "QTime",
    "QTimeEdit",
    "QTimer",
    "QToolTip",
    "QUrl",
    "QVBoxLayout",
    "QWidget",
    "QWizard",
    "QWizardPage",
    "Qt",
    "QuickNavigator",
    "RELEASES_URL",
    "RefreshGate",
    "ReplacementAuditEvent",
    "ReplacementReceipt",
    "ReplacementRequest",
    "SSHProfileManagerDialog",
    "SYNC_CONFIG_FIELDS",
    "Sample",
    "Sequence",
    "ServersEndpointsMixin",
    "SessionActionsMixin",
    "SessionDialog",
    "SessionDoctorContext",
    "SessionNotificationGate",
    "SessionProvenanceStore",
    "SessionTableModel",
    "SettingsBundleMixin",
    "Snapshot",
    "SupportBundleDialog",
    "SyncConfigField",
    "SyncConfigRow",
    "TrackedLogLines",
    "UTC",
    "UpdateCheckResult",
    "Worker",
    "WorkerSignals",
    "_LOCALIZED_ITEM_ROLE",
    "_czech_plural",
    "active_language",
    "add_localized_item",
    "add_localized_items",
    "add_localized_row",
    "annotations",
    "apply_health_network_change",
    "apply_performance_assistant",
    "apply_preset_import",
    "apply_profile_import",
    "attach_health_network_monitor_ui",
    "build_bundle",
    "build_reconfiguration_preview",
    "build_session_configuration_proposal",
    "build_settings_page",
    "button",
    "card",
    "cast",
    "check_for_update",
    "check_session_alerts",
    "classify",
    "configure_settings_path_provider",
    "conflict_count",
    "datetime",
    "diagnose_sessions",
    "endpoint_text",
    "envelope_downsample",
    "example_snapshot",
    "extract_sync_configuration",
    "field_format",
    "fill_session_configuration_table",
    "forward_configuration_rows",
    "from_legacy_session",
    "global_config_editor",
    "group_servers",
    "health_policy_from_settings",
    "host_architecture",
    "html_escape",
    "human_bytes",
    "inspect_cli",
    "inspect_session",
    "json",
    "label",
    "load_bundle",
    "load_ignore_presets",
    "load_profile_store",
    "load_settings",
    "local_self_check",
    "localized_action",
    "localized_button",
    "localized_checkbox",
    "localized_label",
    "main",
    "nearest_time_index",
    "path_aware_ignore_rule",
    "preset_to_record",
    "problem_count",
    "qVersion",
    "query_metrics_from_file",
    "quiet_hours_active",
    "read_registration",
    "read_settings",
    "readable_record_lines",
    "render_sync_replacement_arguments",
    "replace_non_project_mutagen_session",
    "run_isolated_local_sync_test",
    "safe_diagnostic_report",
    "save_settings_file",
    "selected_preferences",
    "separator",
    "session_configuration_rows",
    "session_detail_html",
    "session_log_report",
    "session_preflight_fingerprint",
    "session_servers",
    "set_active_language",
    "set_localized_accessible_name",
    "set_localized_placeholder",
    "set_localized_text",
    "set_localized_title",
    "set_localized_tooltip",
    "setting_tooltip",
    "settings_migration",
    "settings_path",
    "settings_warning_message",
    "statistics_from_file",
    "suppress",
    "tempfile",
    "traceback",
    "translate",
    "translate_route",
    "translate_text",
    "update_tray_status_ui",
    "validate_native_command_snapshot",
    "write_settings",
]


class MainWindow(
    QMainWindow,
    DiagnosticsMixin,
    MonitoringMixin,
    ServersEndpointsMixin,
    SessionActionsMixin,
    PagesMixin,
    OnboardingMixin,
    SettingsBundleMixin,
):
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

    def health_policy_from_settings(self) -> HealthPolicy:
        return health_policy_from_settings(self.conf)

    def _attach_health_network_monitor(self) -> None:
        attach_health_network_monitor_ui(self)

    def _health_network_changed(self, reachability: object) -> None:
        apply_health_network_change(self, reachability)

    def settings_page(self) -> QScrollArea:
        return build_settings_page(self)

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
        if kind == "sync" and hasattr(self, "sync_empty_state"):
            self.sync_empty_state.setVisible(len(sessions) == 0)
            table.setVisible(len(sessions) > 0)
        elif kind == "forward" and hasattr(self, "forward_empty_state"):
            self.forward_empty_state.setVisible(len(sessions) == 0)
            table.setVisible(len(sessions) > 0)
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
        current = table.currentIndex()
        if current.isValid() and table.isRowHidden(current.row()):
            table.selectionModel().clear()
        self.fit_table_to_rows(table)

    def dashboard_select(self, index: QModelIndex) -> None:
        if index.isValid():
            identifier = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            self.focus_session_from_navigator("sync", identifier or "")

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


for _mixin in (
    DiagnosticsMixin,
    MonitoringMixin,
    ServersEndpointsMixin,
    SessionActionsMixin,
    PagesMixin,
    OnboardingMixin,
    SettingsBundleMixin,
):
    for _name, _attr in _mixin.__dict__.items():
        if isinstance(_attr, types.FunctionType):
            _rebound = types.FunctionType(
                _attr.__code__,
                globals(),
                _attr.__name__,
                _attr.__defaults__,
                _attr.__closure__,
            )
            _rebound.__kwdefaults__ = _attr.__kwdefaults__
            _rebound.__annotations__ = getattr(_attr, "__annotations__", {})
            _rebound.__doc__ = _attr.__doc__
            setattr(MainWindow, _name, _rebound)


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
