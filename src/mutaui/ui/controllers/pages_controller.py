"""Main navigation pages and logging mixin for MainWindow."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTime, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from insights import AlertEngine
from log_stream import FileTail
from mutagen_client import classify
from mutaui.ui.formatters import write_settings
from mutaui.ui.localization import (
    _LOCALIZED_ITEM_ROLE,
    set_localized_accessible_name,
    set_localized_placeholder,
    set_localized_text,
    set_localized_tooltip,
)
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.quick_navigator import QuickNavigator
from mutaui.ui.settings_registry import setting_tooltip
from mutaui.ui.theme_constants import AMBER, BLUE, BORDER, RED, TEAL, TEXT
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
from mutaui.ui.widgets.graph import Graph
from mutaui.ui.widgets.health_ring import HealthRing
from mutaui.ui.widgets.session_table import SessionTableModel


class PagesMixin:
    tail_file: FileTail | None = None

    def dashboard_page(self: Any) -> QScrollArea:
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
        set_localized_tooltip(
            self.dashboard_table, "Press Enter or double-click to view sync details"
        )
        rr.addWidget(self.dashboard_table)
        self.dashboard_table.doubleClicked.connect(self.dashboard_select)
        for key in ("Return", "Enter"):
            shortcut = QShortcut(
                QKeySequence(key), self.dashboard_table, context=Qt.ShortcutContext.WidgetShortcut
            )
            shortcut.activated.connect(
                lambda: self.dashboard_select(self.dashboard_table.currentIndex())
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

    def show_metric_menu(self: Any, metric_key: str) -> None:
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

    def open_metric_sessions(self: Any, kind: str, metric_key: str) -> None:
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

    def session_state_filter_changed(self: Any, kind: str) -> None:
        self.filter_table(kind)

    def graph_card(self: Any, title: str, suffix: str, color: str) -> tuple[QFrame, Graph, QLabel]:
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
        self: Any, headers: Sequence[str], height: int = 370, *, stretch_columns: Iterable[int] = ()
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
        self: Any,
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

    def sessions_page(self: Any, kind: str) -> QScrollArea:
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
        search.setClearButtonEnabled(True)
        set_localized_placeholder(search, "Search by name / path…")
        set_localized_accessible_name(search, "Search by name / path…")
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
            set_localized_accessible_name(self.sync_server_filter, "Filter by remote host")
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
        set_localized_accessible_name(states, "Filter sessions by current status")
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
        table.selectionModel().currentChanged.connect(lambda *_args, k=kind: self.on_select(k))
        table.doubleClicked.connect(lambda index, k=kind: self.session_double_click(k, index))
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda point, k=kind: self.session_context_menu(k, point)
        )
        table.setMinimumHeight(0)
        table.setMaximumHeight(16777215)
        table_l.addWidget(table)

        empty_frame = QFrame()
        empty_frame.setObjectName(f"{kind}EmptyStateFrame")
        empty_l = QVBoxLayout(empty_frame)
        empty_l.setContentsMargins(24, 28, 24, 28)
        empty_l.setSpacing(10)
        empty_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = label("⇄" if kind == "sync" else "↗", size=26)
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.addWidget(empty_icon)

        heading_en = "No sync sessions yet" if kind == "sync" else "No port forwarding sessions yet"
        heading_cs = (
            "Zatím žádné synchronizace" if kind == "sync" else "Zatím žádná přesměrování portů"
        )
        empty_heading = label(heading_en, size=14, bold=True)
        empty_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_localized_text(empty_heading, heading_en, czech=heading_cs)
        empty_l.addWidget(empty_heading)

        desc_en = (
            "Create a sync session to start synchronizing files between endpoints.\nTip: You can also drag and drop any folder directly into this window."
            if kind == "sync"
            else "Create a forwarding session to forward network ports between endpoints."
        )
        desc_cs = (
            "Vytvořte synchronizaci pro přenos souborů mezi koncovými body.\nTip: Libovolnou složku můžete také přetáhnout přímo do tohoto okna."
            if kind == "sync"
            else "Vytvořte přesměrování pro spojení síťových portů mezi koncovými body."
        )
        empty_desc = label(desc_en, muted=True)
        empty_desc.setWordWrap(True)
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_localized_text(empty_desc, desc_en, czech=desc_cs)
        empty_l.addWidget(empty_desc)

        btn_en = (
            "+ Create first sync session" if kind == "sync" else "+ Create first forwarding session"
        )
        btn_cs = (
            "+ Vytvořit první synchronizaci" if kind == "sync" else "+ Vytvořit první přesměrování"
        )
        empty_actions = QHBoxLayout()
        empty_actions.setSpacing(10)
        empty_actions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_create_btn = button(
            btn_en,
            partial(self.create_session, kind),
            kind="primary",
        )
        set_localized_text(empty_create_btn, btn_en, czech=btn_cs)
        empty_actions.addWidget(empty_create_btn)

        empty_diag_btn = button(
            "Troubleshoot…",
            self.open_troubleshooter,
        )
        set_localized_text(empty_diag_btn, "Troubleshoot…", czech="Řešení potíží…")
        set_localized_tooltip(
            empty_diag_btn, "Check Mutagen connection and diagnose issues (Ctrl+D)"
        )
        empty_actions.addWidget(empty_diag_btn)

        empty_l.addLayout(empty_actions)
        empty_frame.setVisible(False)
        table_l.addWidget(empty_frame)

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
        troubleshoot_btn = button(
            "⚠ Troubleshoot…", partial(self.open_troubleshooter_for_selected, kind), kind="accent"
        )
        troubleshoot_btn.setVisible(False)
        set_localized_tooltip(troubleshoot_btn, "Diagnose and resolve issues with this session.")
        utility_controls.insertWidget(1, troubleshoot_btn)
        layout.addWidget(detail)
        layout.addStretch(1)
        if kind == "sync":
            self.sync_table, self.sync_summary = table, summary
            self.sync_empty_state = empty_frame
            self.sync_details, self.sync_title, self.sync_tag = details, detail_title, detail_tag
            self.sync_controls = control_buttons
            self.sync_progress = progress
            self.sync_favorite_button = favorite_button
            self.sync_preferences_button = session_prefs
            self.sync_troubleshoot_button = troubleshoot_btn
        else:
            self.forward_table, self.forward_summary = table, summary
            self.forward_empty_state = empty_frame
            self.forward_details, self.forward_title, self.forward_tag = (
                details,
                detail_title,
                detail_tag,
            )
            self.forward_controls = control_buttons
            self.forward_progress = progress
            self.forward_favorite_button = favorite_button
            self.forward_preferences_button = session_prefs
            self.forward_troubleshoot_button = troubleshoot_btn
        page.setWidget(root)
        return page

    def logs_page(self: Any) -> QScrollArea:
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
        filter_caption = label("Filter:", muted=True)
        self.tail_filter = QLineEdit()
        self.tail_filter.setClearButtonEnabled(True)
        filter_caption.setBuddy(self.tail_filter)
        filterline.addWidget(filter_caption)
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

    def choose_tail_file(self: Any) -> None:
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

    def stop_tail_file(self: Any) -> None:
        self.tail_file = None
        self.tail_timer.stop()
        set_localized_text(self.tail_info, "Log monitoring stopped.")

    def clear_tail(self: Any) -> None:
        self.tail_lines.clear()
        self.tail_view.clear()

    def poll_tail(self: Any) -> None:
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

    def schedule_tail_render(self: Any) -> None:
        """Merge bursts of debug output into one UI paint (~6 FPS at most)."""
        if not self._tail_render_pending:
            self._tail_render_pending = True
            QTimer.singleShot(160, self._render_pending_tail)

    def _render_pending_tail(self: Any) -> None:
        self._tail_render_pending = False
        self.render_tail()

    def render_tail(self: Any, *_: object) -> None:
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

    def export_tail_file(self: Any) -> None:
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

    def daemon_page(self: Any) -> QScrollArea:
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

    def alerts_page(self: Any) -> QScrollArea:
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

    def save_alert_rules(self: Any) -> None:
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

    def open_navigator(self: Any) -> None:
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
                found = self.focus_session_from_navigator(kind, identifier)
                if found and command == "flush_session":
                    self.session_action("sync", "flush")
        elif dialog.target is not None:
            self.set_page(dialog.target)

    def focus_session_from_navigator(self: Any, kind: str, identifier: str) -> bool:
        if kind not in {"sync", "forward"} or not identifier:
            return False
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
        if row < 0:
            return False
        table.selectRow(row)
        table.scrollTo(table.model().index(row, 0))
        return True
