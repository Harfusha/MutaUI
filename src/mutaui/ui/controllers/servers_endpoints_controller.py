"""Endpoints and servers management mixin for MainWindow."""

from __future__ import annotations

from functools import partial
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from endpoint_inspector import summary as inspect_session
from mutagen_client import Snapshot, classify, endpoint_text, human_bytes
from mutaui.ui.formatters import _czech_plural, separator
from mutaui.ui.localization import (
    set_localized_placeholder,
    set_localized_text,
    set_localized_tooltip,
)
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.theme_constants import AMBER, TEAL
from mutaui.ui.widgets.basic import add_localized_item, button, card, label
from server_groups import group_servers, session_servers


class ServersEndpointsMixin:
    def endpoints_page(self: Any) -> QScrollArea:
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

    def update_endpoint_sessions(self: Any, snapshot: Snapshot) -> None:
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
            short_id = sid[:8] if sid else "—"
            text = f"{kind_name} · {name} ({short_id}) · {status}"
            tooltip = f"{kind_name} · {name}\nID: {sid}\nStatus: {status}\nSource: {source}\nTarget: {target}"
            entries.append((kind, sid, text, tooltip))
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

    def update_endpoint_details(self: Any, *_args: object) -> None:
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

    def servers_page(self: Any) -> QScrollArea:
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
        self.b_srv_sync = b_srv_sync
        b_srv_pause = button(
            "⏸ Pause Sync Sessions", partial(self.bulk_action, "sync", "pause", "server")
        )
        set_localized_tooltip(b_srv_pause, "Pauses all sync sessions in the selected group.")
        first.addWidget(b_srv_pause)
        self.b_srv_pause = b_srv_pause
        b_srv_resume = button(
            "▶ Resume Sync Sessions", partial(self.bulk_action, "sync", "resume", "server")
        )
        set_localized_tooltip(b_srv_resume, "Resumes paused sync sessions in the selected group.")
        first.addWidget(b_srv_resume)
        self.b_srv_resume = b_srv_resume
        first.addStretch()
        ac.addLayout(first)
        second = QHBoxLayout()
        b_fwd_pause = button(
            "⏸ Pause Forwards", partial(self.bulk_action, "forward", "pause", "server")
        )
        set_localized_tooltip(b_fwd_pause, "Pauses all port forwards in the selected group.")
        second.addWidget(b_fwd_pause)
        self.b_fwd_pause = b_fwd_pause
        b_fwd_resume = button(
            "▶ Resume Forwards", partial(self.bulk_action, "forward", "resume", "server")
        )
        set_localized_tooltip(b_fwd_resume, "Resumes paused port forwards in the selected group.")
        second.addWidget(b_fwd_resume)
        self.b_fwd_resume = b_fwd_resume
        second.addStretch()
        ac.addLayout(second)
        advanced = button("More Bulk Actions ▾", self.show_server_advanced_actions)
        self.server_advanced_button = advanced
        set_localized_tooltip(
            advanced, "Shows more bulk actions: terminate sessions, reset, and group diagnostics."
        )
        ac.addWidget(advanced)
        self.b_server_advanced = advanced
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

    def pick_server_row(self: Any, row: int, col: int) -> None:
        item = self.server_overview.item(row, 0)
        if item:
            index = self.server_selector.findData(item.data(Qt.ItemDataRole.UserRole))
            if index >= 0:
                self.server_selector.setCurrentIndex(index)

    def update_server_groups(self: Any) -> None:
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
            if found < 0 and current not in (None, "", "__all__"):
                unavailable_text = "Previously selected group is no longer available"
                self.server_selector.addItem(
                    translate_text(unavailable_text, self.ui_language),
                    "__unavailable__",
                )
                self.server_selector.setCurrentIndex(self.server_selector.count() - 1)
            else:
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

    def server_targets(self: Any, kind: str, scope: str) -> list[dict[str, Any]]:
        sessions = self.snapshot.sync if kind == "sync" else self.snapshot.forward
        if scope == "all":
            return list(sessions)
        key = self.server_selector.currentData() if hasattr(self, "server_selector") else "__all__"
        if key == "__unavailable__":
            return []
        if key == "__all__":
            return list(sessions)
        return [session for session in sessions if key in session_servers(session, kind)]

    def update_server_details(self: Any, *_args: object) -> None:
        if not hasattr(self, "server_selector"):
            return
        selection_key = self.server_selector.currentData()
        action_buttons = [
            getattr(self, "b_srv_sync", None),
            getattr(self, "b_srv_pause", None),
            getattr(self, "b_srv_resume", None),
            getattr(self, "b_fwd_pause", None),
            getattr(self, "b_fwd_resume", None),
            getattr(self, "server_advanced_button", None),
        ]
        if selection_key == "__unavailable__":
            for btn in action_buttons:
                if btn is not None:
                    btn.setEnabled(False)
            set_localized_text(
                self.server_scope_label,
                "Previously selected group is no longer available · Choose another group or All Sessions",
                czech="Dříve vybraná skupina není dostupná · Vyberte jinou skupinu nebo Všechny relace",
            )
            self.server_sync_empty.setVisible(True)
            self.server_forward_empty.setVisible(True)
            self.server_sync_table.setRowCount(0)
            self.server_forward_table.setRowCount(0)
            return
        for btn in action_buttons:
            if btn is not None:
                btn.setEnabled(True)
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

    def open_group_session(self: Any, kind: str, row: int) -> None:
        listing = self.server_sync_table if kind == "sync" else self.server_forward_table
        item = listing.item(row, 0)
        if not item:
            return
        identifier = item.data(Qt.ItemDataRole.UserRole)
        if not identifier:
            return
        identifier_str = str(identifier)
        found = False
        if hasattr(self, "focus_session_from_navigator"):
            found = bool(self.focus_session_from_navigator(kind, identifier_str))
        if not found:
            self.set_page(1 if kind == "sync" else 2)
            if kind == "sync":
                if hasattr(self, "sync_server_filter"):
                    self.sync_server_filter.setCurrentIndex(0)
                if hasattr(self, "sync_search"):
                    self.sync_search.clear()
                if hasattr(self, "sync_state_filter"):
                    self.sync_state_filter.setCurrentIndex(0)
                if hasattr(self, "sync_favorites_only"):
                    self.sync_favorites_only.setChecked(False)
            else:
                if hasattr(self, "forward_search"):
                    self.forward_search.clear()
                if hasattr(self, "forward_state_filter"):
                    self.forward_state_filter.setCurrentIndex(0)
                if hasattr(self, "forward_favorites_only"):
                    self.forward_favorites_only.setChecked(False)
            table = self.sync_table if kind == "sync" else self.forward_table
            model = getattr(table, "model", lambda: None)()
            if model is not None and hasattr(model, "row_for_identifier"):
                target_row = model.row_for_identifier(identifier_str)
                if target_row >= 0:
                    table.selectRow(target_row)
                    table.scrollTo(model.index(target_row, 0))
                    found = True
            elif hasattr(table, "rowCount") and hasattr(table, "item"):
                for r in range(table.rowCount()):
                    row_item = table.item(r, 0)
                    if row_item is not None and (
                        getattr(row_item, "identifier", None) == identifier_str
                        or row_item.data(Qt.ItemDataRole.UserRole) == identifier_str
                    ):
                        table.selectRow(r)
                        if hasattr(table, "scrollToItem"):
                            table.scrollToItem(row_item)
                        found = True
                        break
        if not found:
            QMessageBox.information(
                self,
                translate_text("Session Unavailable", active_language()),
                translate_text(
                    "The selected session is no longer available in the current snapshot.",
                    active_language(),
                ),
            )

    def show_server_advanced_actions(self: Any) -> None:
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
