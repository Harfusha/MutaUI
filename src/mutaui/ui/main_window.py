"""Main window for MutaUI application."""

from __future__ import annotations

import os
import sqlite3
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, Qt, QThreadPool, QTimer
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QGuiApplication,
    QHideEvent,
    QKeySequence,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizard,
)

from async_recorder import AsyncRecorder
from insights import AlertEngine
from log_stream import FileTail, TrackedLogLines
from monitoring import ForwardTrafficMeter, HistoryStore
from mutagen_client import MutagenClient, ProcessSampler, Snapshot, example_snapshot
from mutaui.services.action_planner import ActionPlanner
from mutaui.services.health_tracker import HealthTracker
from mutaui.services.session_notification_gate import SessionNotificationGate
from mutaui.services.session_provenance import SessionProvenanceStore
from mutaui.services.update_checker import UpdateCheckResult
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
from mutaui.ui.formatters import get_settings_path as settings_path
from mutaui.ui.formatters import settings_warning_message, write_settings
from mutaui.ui.localization import (
    set_localized_accessible_name,
    set_localized_title,
    set_localized_tooltip,
)
from mutaui.ui.page_shell import PAGE_ROUTES, LazyStackedWidget
from mutaui.ui.preferences import (
    resolve_theme,
    set_active_language,
    translate,
    translate_route,
)
from mutaui.ui.preferences_controller import PreferencesController
from mutaui.ui.styles import CSS
from mutaui.ui.widgets.basic import button, label
from mutaui.ui.worker import Worker
from performance import PollBackoff, RefreshGate
from settings import load_settings
from sync_profiles import AdaptivePolling


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
        self.last_metrics = {
            "cpu": 0,
            "memory": 0,
            "read_rate": 0,
            "write_rate": 0,
            "processes": 0,
        }
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
        self.setAcceptDrops(True)
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
        shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        shortcut.activated.connect(lambda: self.open_troubleshooter())
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

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.isLocalFile() and Path(url.toLocalFile()).is_dir() for url in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.isLocalFile() and Path(url.toLocalFile()).is_dir() for url in urls):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        for url in event.mimeData().urls():
            if url.isLocalFile():
                local_path = url.toLocalFile()
                if Path(local_path).is_dir():
                    event.acceptProposedAction()
                    self.handle_dropped_folder(local_path)
                    return
        event.ignore()

    def handle_dropped_folder(self, folder_path: str) -> None:
        norm_path = os.path.normpath(folder_path)
        self.set_page(1)
        self.create_session("sync", initial_path=norm_path)

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


__all__ = ["MainWindow"]
