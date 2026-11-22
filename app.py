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
from mutaui.adapters.cli_executor import LegacyMutagenExecutor, MutagenCliExecutor  # noqa: F401
from mutaui.adapters.mutagen_snapshot import from_legacy_session  # noqa: F401


def from_session_dict(*args: Any, **kwargs: Any) -> Any:
    return from_legacy_session(*args, **kwargs)


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
from mutaui.ui.main_window import MainWindow
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

_target_dict = sys.modules["app"].__dict__ if "app" in sys.modules else globals()
if __name__ in ("__main__", "app") or "app" not in sys.modules:
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
                    _target_dict,
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
