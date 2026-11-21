"""Mutagen Control 8.2 — Windows desktop companion for Mutagen CLI.

Start with: python app.py
Preview (offline demo, actions disabled): python app.py --demo
"""

from __future__ import annotations

import json  # noqa: F401
import math  # noqa: F401
import os
import sqlite3
import sys
import tempfile  # noqa: F401
import time
import traceback  # noqa: F401
import types
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence  # noqa: F401
from contextlib import suppress  # noqa: F401
from datetime import UTC, datetime  # noqa: F401
from functools import partial
from html import escape as html_escape  # noqa: F401
from pathlib import Path
from typing import Any, Literal, cast  # noqa: F401

_SOURCE_PACKAGE_PATH = Path(__file__).resolve().parent / "src"
if _SOURCE_PACKAGE_PATH.is_dir() and str(_SOURCE_PACKAGE_PATH) not in sys.path:
    sys.path.insert(0, str(_SOURCE_PACKAGE_PATH))

# Register bundled Qt/Shiboken DLL paths before imports to avoid PATH conflicts.
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
    QPoint,  # noqa: F401
    QPointF,  # noqa: F401
    QRectF,  # noqa: F401
    Qt,
    QThreadPool,
    QTime,  # noqa: F401
    QTimer,
    QUrl,  # noqa: F401
    qVersion,  # noqa: F401
)
from PySide6.QtGui import (
    QAction,  # noqa: F401
    QBrush,  # noqa: F401
    QCloseEvent,  # noqa: F401
    QColor,  # noqa: F401
    QDesktopServices,  # noqa: F401
    QGuiApplication,
    QHideEvent,
    QIcon,  # noqa: F401
    QKeySequence,
    QLinearGradient,  # noqa: F401
    QPainter,  # noqa: F401
    QPainterPath,  # noqa: F401
    QPen,  # noqa: F401
    QPixmap,  # noqa: F401
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,  # noqa: F401
    QApplication,
    QCheckBox,  # noqa: F401
    QComboBox,
    QCompleter,  # noqa: F401
    QDialog,  # noqa: F401
    QDialogButtonBox,  # noqa: F401
    QFileDialog,  # noqa: F401
    QFormLayout,  # noqa: F401
    QFrame,
    QGridLayout,  # noqa: F401
    QHBoxLayout,
    QHeaderView,  # noqa: F401
    QInputDialog,  # noqa: F401
    QLabel,
    QLayout,  # noqa: F401
    QLineEdit,
    QListWidget,  # noqa: F401
    QListWidgetItem,  # noqa: F401
    QMainWindow,
    QMenu,  # noqa: F401
    QMessageBox,  # noqa: F401
    QPlainTextEdit,  # noqa: F401
    QProgressBar,  # noqa: F401
    QPushButton,
    QScrollArea,
    QSizePolicy,  # noqa: F401
    QSpinBox,  # noqa: F401
    QSystemTrayIcon,  # noqa: F401
    QTableView,  # noqa: F401
    QTableWidget,  # noqa: F401
    QTableWidgetItem,  # noqa: F401
    QTextBrowser,  # noqa: F401
    QTimeEdit,  # noqa: F401
    QToolTip,  # noqa: F401
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,  # noqa: F401
)

from async_recorder import AsyncRecorder
from connection_profiles import (  # noqa: F401
    ConnectionProfile,
    ConnectionProfileStore,
    load_profile_store,
)
from endpoint_inspector import summary as inspect_session  # noqa: F401
from forward_configuration import (  # noqa: F401
    FORWARD_CONFIG_FIELDS,
    ForwardConfigField,
    ForwardConfigRow,
    forward_configuration_rows,
)
from ignore_presets import (  # noqa: F401
    IgnorePresetError,
    IgnorePresetStore,
    apply_preset_import,
    load_ignore_presets,
    path_aware_ignore_rule,
    preset_to_record,
)
from insights import AlertEngine, local_self_check, safe_diagnostic_report, session_log_report  # noqa: F401
from log_stream import FileTail, TrackedLogLines
from monitoring import (
    ForwardTrafficMeter,
    HistoryStore,
    Sample,  # noqa: F401
    query_metrics_from_file,  # noqa: F401
    statistics_from_file,  # noqa: F401
)
from mutagen_client import (
    MutagenClient,
    MutagenError,  # noqa: F401
    ProcessSampler,
    Snapshot,
    classify,  # noqa: F401
    conflict_count,  # noqa: F401
    endpoint_text,  # noqa: F401
    example_snapshot,
    human_bytes,  # noqa: F401
    problem_count,  # noqa: F401
    read_registration,  # noqa: F401
    session_preflight_fingerprint,  # noqa: F401
)
from mutaui import __version__ as APP_VERSION
from mutaui.adapters.cli_executor import LegacyMutagenExecutor  # noqa: F401
from mutaui.adapters.mutagen_snapshot import from_legacy_session  # noqa: F401
from mutaui.services.action_planner import ACTION_SPECS, ActionPlanner, ActionRequest  # noqa: F401
from mutaui.services.health_tracker import (  # noqa: F401
    HealthObservation,
    HealthPolicy,
    HealthTracker,
    health_policy_from_settings,
)
from mutaui.services.quiet_hours import quiet_hours_active  # noqa: F401
from mutaui.services.reconfiguration import (
    build_reconfiguration_preview,  # noqa: F401
    extract_sync_configuration,  # noqa: F401
    validate_native_command_snapshot,  # noqa: F401
)
from mutaui.services.replacement import (  # noqa: F401
    ReplacementAuditEvent,
    ReplacementReceipt,
    ReplacementRequest,
    replace_non_project_mutagen_session,
)
from mutaui.services.replacement_command import render_sync_replacement_arguments  # noqa: F401
from mutaui.services.session_configuration import build_session_configuration_proposal  # noqa: F401
from mutaui.services.session_doctor import (  # noqa: F401
    FRESHNESS_SECONDS,
    SessionDoctorContext,
    diagnose_sessions,
)
from mutaui.services.session_notification_gate import SessionNotificationGate
from mutaui.services.session_provenance import ProvenanceStoreError, SessionProvenanceStore  # noqa: F401
from mutaui.services.update_checker import RELEASES_URL, UpdateCheckResult, check_for_update  # noqa: F401
from mutaui.ui import global_config_editor, settings_migration  # noqa: F401
from mutaui.ui.conflict_inspector_dialog import ConflictInspectorDialog  # noqa: F401
from mutaui.ui.connection_profiles_dialog import ConnectionProfilesDialog  # noqa: F401
from mutaui.ui.formatters import read_settings  # noqa: F401
from mutaui.ui.health_network_monitor import (
    attach_health_network_monitor as attach_health_network_monitor_ui,  # noqa: F401
)  # noqa: F401
from mutaui.ui.health_network_monitor import health_network_changed as apply_health_network_change  # noqa: F401
from mutaui.ui.ignore_rules import IgnorePresetManagerDialog  # noqa: F401
from mutaui.ui.localization import (
    _LOCALIZED_ITEM_ROLE,  # noqa: F401
    set_localized_accessible_name,
    set_localized_placeholder,  # noqa: F401
    set_localized_text,  # noqa: F401
    set_localized_title,
    set_localized_tooltip,
)
from mutaui.ui.onboarding import (  # noqa: F401
    CLIDiscovery,
    host_architecture,
    inspect_cli,
    run_isolated_local_sync_test,
)
from mutaui.ui.page_shell import PAGE_ROUTES, LazyStackedWidget
from mutaui.ui.performance_tuning import apply_performance_assistant  # noqa: F401
from mutaui.ui.portable_import_preview import PortableImportPreviewDialog
from mutaui.ui.preferences import (
    ADVANCED_ROUTE_IDS,  # noqa: F401 -- retained as app module compatibility export
    active_language,  # noqa: F401
    resolve_theme,
    set_active_language,
    translate,
    translate_route,
    translate_text,  # noqa: F401
)
from mutaui.ui.preferences_controller import PreferencesController
from mutaui.ui.project_viewer import NativeProjectManagerDialog  # noqa: F401
from mutaui.ui.session_alerts import check_alerts as check_session_alerts  # noqa: F401
from mutaui.ui.session_configuration_table import fill_session_configuration_table  # noqa: F401
from mutaui.ui.session_dialog import SessionDialog, configure_settings_path_provider
from mutaui.ui.settings_page import build_settings_page  # noqa: F401
from mutaui.ui.settings_registry import setting_tooltip  # noqa: F401
from mutaui.ui.ssh_profile_manager import SSHProfileManagerDialog  # noqa: F401
from mutaui.ui.styles import (
    AMBER,  # noqa: F401
    BG,  # noqa: F401
    BLUE,  # noqa: F401
    BORDER,
    CARD,  # noqa: F401
    CARD2,  # noqa: F401
    CSS,
    MUTED,  # noqa: F401
    RED,  # noqa: F401
    TEAL,  # noqa: F401
    TEXT,  # noqa: F401
)
from mutaui.ui.tray_status import update_tray_status as update_tray_status_ui  # noqa: F401
from mutaui.ui.widgets.basic import (
    add_localized_item,  # noqa: F401
    add_localized_items,  # noqa: F401
    add_localized_row,  # noqa: F401
    button,
    card,  # noqa: F401
    label,
    localized_button,  # noqa: F401
    localized_checkbox,  # noqa: F401
    localized_label,  # noqa: F401
)
from mutaui.ui.widgets.graph import Graph  # noqa: F401
from mutaui.ui.widgets.health_ring import HealthRing  # noqa: F401
from mutaui.ui.widgets.session_table import SessionTableModel
from mutaui.ui.worker import Worker, WorkerSignals  # noqa: F401
from performance import (  # noqa: F401
    PollBackoff,
    RefreshGate,
    envelope_downsample,
    nearest_time_index,
)
from portable_bundle import (  # noqa: F401
    PortableBundleError,
    apply_profile_import,
    build_bundle,
    load_bundle,
    selected_preferences,
)
from server_groups import group_servers, session_servers  # noqa: F401
from settings import load_settings, settings_path  # noqa: F401
from settings import write_settings as save_settings_file  # noqa: F401
from sync_configuration import (
    SYNC_CONFIG_FIELDS,  # noqa: F401
    SyncConfigField,  # noqa: F401
    SyncConfigRow,  # noqa: F401
    session_configuration_rows,  # noqa: F401
)
from sync_profiles import PROFILES as PROFILES
from sync_profiles import AdaptivePolling

configure_settings_path_provider(lambda: settings_path())

from mutaui.ui.controllers import (
    CommandExecutionMixin,
    DiagnosticsMixin,
    GlobalConfigMixin,
    LoggingMixin,
    MonitoringMixin,
    OnboardingMixin,
    PagesMixin,
    ServersEndpointsMixin,
    SessionActionsMixin,
    SessionTableMixin,
    SettingsBundleMixin,
    SnapshotLifecycleMixin,
    TrayMixin,
)
from mutaui.ui.formatters import (
    _czech_plural,
    field_format,
    localized_action,  # noqa: F401
    readable_record_lines,
    separator,  # noqa: F401
    session_detail_html,
    settings_warning_message,
    write_settings,
)
from mutaui.ui.quick_navigator import QuickNavigator
from mutaui.ui.support_bundle_dialog import SupportBundleDialog

__all__ = [
    "MainWindow",
    "main",
    "QuickNavigator",
    "SupportBundleDialog",
    "SessionDialog",
    "PortableImportPreviewDialog",
    "SessionTableModel",
    "BORDER",
    "_czech_plural",
    "button",
    "field_format",
    "readable_record_lines",
    "session_detail_html",
    "CommandExecutionMixin",
    "DiagnosticsMixin",
    "GlobalConfigMixin",
    "LoggingMixin",
    "MonitoringMixin",
    "OnboardingMixin",
    "PagesMixin",
    "ServersEndpointsMixin",
    "SessionActionsMixin",
    "SessionTableMixin",
    "SettingsBundleMixin",
    "SnapshotLifecycleMixin",
    "TrayMixin",
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
    TrayMixin,
    SessionTableMixin,
    CommandExecutionMixin,
    SnapshotLifecycleMixin,
    GlobalConfigMixin,
    LoggingMixin,
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
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.focus_search)
        shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        shortcut.activated.connect(self.toggle_theme_quick)
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

    def focus_search(self) -> None:
        """Focus and select text in the search input matching current active page."""
        idx = self.pages.currentIndex()
        target: QLineEdit | None = None
        if idx == 1 and hasattr(self, "sync_search"):
            target = self.sync_search
        elif idx == 2 and hasattr(self, "forward_search"):
            target = self.forward_search
        elif idx in (3, 4) and hasattr(self, "tail_filter"):
            target = self.tail_filter
        if target is not None:
            target.setFocus()
            target.selectAll()

    def set_ui_mode(self, mode: str) -> None:
        self.preferences_controller.set_ui_mode(mode)

    def apply_theme(self, theme: str) -> None:
        self.preferences_controller.apply_theme(theme)
        self._update_theme_toggle_icon()

    def _update_theme_toggle_icon(self) -> None:
        if not hasattr(self, "theme_toggle_btn"):
            return
        theme = self.conf.get("theme", "dark")
        try:
            system_is_light = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light
        except (AttributeError, RuntimeError):
            system_is_light = False
        resolved = resolve_theme(theme, system_is_light=system_is_light)
        self.theme_toggle_btn.setText("☀️" if resolved == "dark" else "🌙")

    def toggle_theme_quick(self) -> None:
        theme = self.conf.get("theme", "dark")
        try:
            system_is_light = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light
        except (AttributeError, RuntimeError):
            system_is_light = False
        resolved = resolve_theme(theme, system_is_light=system_is_light)
        new_theme = "light" if resolved == "dark" else "dark"
        self.conf["theme"] = new_theme
        self.apply_theme(new_theme)
        if hasattr(self, "theme_input"):
            idx = self.theme_input.findData(new_theme)
            if idx >= 0:
                self.theme_input.setCurrentIndex(idx)
        self._update_theme_toggle_icon()
        write_settings(self.conf)
        msg = (
            f"Theme switched to {new_theme}"
            if self.ui_language == "en"
            else f"Motiv přepnut na {new_theme}"
        )
        if hasattr(self, "statusBar") and self.statusBar():
            self.statusBar().showMessage(msg, 3000)

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
        self.theme_toggle_btn = QPushButton()
        self.theme_toggle_btn.setObjectName("themeToggle")
        self.theme_toggle_btn.setFixedSize(32, 32)
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_theme_toggle_icon()
        self.theme_toggle_btn.clicked.connect(self.toggle_theme_quick)
        set_localized_tooltip(self.theme_toggle_btn, "Toggle dark/light theme")
        logorow.addWidget(self.theme_toggle_btn)
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


for _mixin in (
    DiagnosticsMixin,
    MonitoringMixin,
    ServersEndpointsMixin,
    SessionActionsMixin,
    PagesMixin,
    OnboardingMixin,
    SettingsBundleMixin,
    TrayMixin,
    SessionTableMixin,
    CommandExecutionMixin,
    SnapshotLifecycleMixin,
    GlobalConfigMixin,
    LoggingMixin,
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
