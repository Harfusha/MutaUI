"""Session table filtering, selection, and launch request routing mixin."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QMessageBox,
    QTableView,
    QTableWidget,
)

from mutagen_client import classify
from mutaui.adapters.cli_executor import MutagenCliExecutor
from mutaui.adapters.mutagen_snapshot import from_session_dict
from mutaui.ui.preferences import active_language, translate_text
from server_groups import session_servers
from settings import settings_path


class SessionTableMixin:
    """Mixin providing session table population, filtering, selection, and launch routing."""

    def fill_table(
        self: Any,
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
        height = min(520, max(112, header_height + rows_height + 2 * table.frameWidth() + 4))
        table.setFixedHeight(height)

    def filter_table(self: Any, kind: str, value: str | None = None) -> None:
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
        total_rows = model.rowCount()
        visible_rows = 0
        for row in range(total_rows):
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
            hidden = (
                needle not in haystack
                or not meets_state
                or not meets_server
                or (only_favorites and identifier not in self.favorites[kind])
            )
            table.setRowHidden(row, hidden)
            if not hidden:
                visible_rows += 1
        current = table.currentIndex()
        if current.isValid() and table.isRowHidden(current.row()):
            table.selectionModel().clear()
        self.fit_table_to_rows(table)
        if (
            hasattr(self, "statusBar")
            and self.statusBar()
            and (needle or code is not None or server_key != "__all__" or only_favorites)
        ):
            lang = getattr(self, "ui_language", "en")
            msg = (
                f"Zobrazeno {visible_rows} z {total_rows} relací ({kind})"
                if lang == "cs"
                else f"Showing {visible_rows} of {total_rows} {kind} sessions"
            )
            self.statusBar().showMessage(msg, 3000)

    def session_double_click(self: Any, kind: str, index: QModelIndex) -> None:
        if not index.isValid():
            return
        identifier = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        if identifier and hasattr(self, "open_session_preferences"):
            self.open_session_preferences(kind)

    def dashboard_select(self: Any, index: QModelIndex) -> None:
        if index.isValid():
            identifier = index.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
            self.focus_session_from_navigator("sync", identifier or "")

    def on_select(self: Any, kind: str) -> None:
        table = self.sync_table if kind == "sync" else self.forward_table
        current = table.currentIndex()
        if not current.isValid():
            if self.current_kind == kind:
                self.current_id = ""
        else:
            self.current_kind = kind
            self.current_id = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole) or ""
        self.refresh_detail(kind)

    def selected_session(self: Any, kind: str) -> dict[str, Any] | None:
        table = self.sync_table if kind == "sync" else self.forward_table
        current = table.currentIndex()
        if not current.isValid():
            return None
        identifier = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        sessions = self.snapshot.sync if kind == "sync" else self.snapshot.forward
        return next((s for s in sessions if s.get("identifier") == identifier), None)

    def _start_initial_refresh(self: Any) -> None:
        self._initial_refresh_pending = False
        if not self.pending_poll:
            self.refresh(force=True)

    def _has_authoritative_session_lists(self: Any) -> bool:
        return self.demo or bool(
            self.snapshot.daemon
            and not self.snapshot.sessions_stale
            and self.snapshot.sync_observed_at is not None
            and self.snapshot.forward_observed_at is not None
        )

    def _complete_pending_launch_requests(self: Any) -> None:
        if not self._pending_launch_requests:
            return
        pending = self._pending_launch_requests
        self._pending_launch_requests: list[dict[str, Any]] = []
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

    def handle_launch_request(self: Any, message: Mapping[str, object]) -> None:
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
                executor=MutagenCliExecutor(self.client) if self.client.binary else None,
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
                        from_session_dict(
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
