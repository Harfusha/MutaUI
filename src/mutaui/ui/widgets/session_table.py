"""Optimized model/view adapter for frequently refreshed session tables (CORE-02 / F2-021)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QWidget

from mutagen_client import classify, conflict_count, endpoint_text, problem_count
from mutaui.ui.preferences import active_language, translate_text

TEAL = "#61E0B9"
BLUE = "#4E97D1"
RED = "#FB8696"
AMBER = "#F2BF70"


@dataclass(slots=True, frozen=True)
class SessionRowPresentation:
    cells: list[str]
    status: str
    identifier: str
    extra: int


class SessionTableModel(QAbstractTableModel):
    """Data adapter for session lists with ID index and presentation caching."""

    def __init__(
        self,
        headers: Sequence[str],
        kind: str,
        *,
        dashboard: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.headers = list(headers)
        self.kind = kind
        self.dashboard = dashboard
        self.sessions: list[dict[str, Any]] = []
        self.favorites: set[str] = set()
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.ui_language = active_language()
        self._id_to_row: dict[str, int] = {}
        self._presentation_cache: list[SessionRowPresentation] = []

    def set_ui_language(self, language: str) -> None:
        self.ui_language = language
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole],
            )
        if self.columnCount():
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.sessions)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.headers)

    def _build_presentation(self, session: dict[str, Any]) -> SessionRowPresentation:
        status, description = classify(session, self.kind)
        identifier = str(session.get("identifier") or "")
        name = session.get("name") or identifier[:22] or "(unnamed)"
        if identifier in self.favorites:
            name = "★ " + name
        source = endpoint_text(session.get("alpha" if self.kind == "sync" else "source"), self.kind)
        target = endpoint_text(
            session.get("beta" if self.kind == "sync" else "destination"),
            self.kind,
        )
        extra = (
            conflict_count(session) + problem_count(session)
            if self.kind == "sync"
            else int(session.get("openConnections") or 0)
            if str(session.get("openConnections") or "").isdigit()
            else 0
        )
        cells = [name, description, source, target] + (
            []
            if self.dashboard
            else [str(session.get("openConnections", 0)) if self.kind != "sync" else str(extra)]
        )
        return SessionRowPresentation(
            cells=cells,
            status=status,
            identifier=identifier,
            extra=extra,
        )

    def _cells(self, session: dict[str, Any]) -> tuple[list[str], str, str, int]:
        ident = session.get("identifier")
        row = self._id_to_row.get(ident, -1) if ident is not None else -1
        if 0 <= row < len(self._presentation_cache):
            pres = self._presentation_cache[row]
            return pres.cells, pres.status, pres.identifier, pres.extra
        pres = self._build_presentation(session)
        return pres.cells, pres.status, pres.identifier, pres.extra

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self.sessions)):
            return None
        row = index.row()
        pres = (
            self._presentation_cache[row]
            if 0 <= row < len(self._presentation_cache)
            else self._build_presentation(self.sessions[row])
        )

        cells = pres.cells
        value = cells[index.column()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if index.column() == 1:
                return translate_text(value, self.ui_language)
            return value
        if role == Qt.ItemDataRole.UserRole and index.column() == 0:
            return pres.identifier
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 1:
            color = {
                "active": TEAL,
                "busy": BLUE,
                "error": RED,
                "paused": AMBER,
            }.get(pres.status)
            return QColor(color) if color else None
        if role == Qt.ItemDataRole.FontRole and index.column() == 0:
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ItemDataRole.UserRole + 1:
            return (
                pres.extra
                if index.column() == len(cells) - 1 and not self.dashboard
                else value.casefold()
            )
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            header = self.headers[section] if 0 <= section < len(self.headers) else None
            return translate_text(header, self.ui_language) if header else None
        return None

    def set_sessions(
        self,
        sessions: Sequence[dict[str, Any]],
        favorites: Sequence[str] = (),
    ) -> None:
        self.beginResetModel()
        self.sessions = list(sessions)
        self.favorites = set(favorites)
        self._rebuild_indices_and_cache()
        if self.sort_column >= 0:
            self._sort_rows()
        self.endResetModel()

    def _rebuild_indices_and_cache(self) -> None:
        self._id_to_row = {
            str(session.get("identifier") or ""): row for row, session in enumerate(self.sessions)
        }
        self._presentation_cache = [self._build_presentation(session) for session in self.sessions]

    def row_for_identifier(self, identifier: Any) -> int:
        return self._id_to_row.get(str(identifier or ""), -1)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(self.headers):
            return
        persistent = self.persistentIndexList()
        identity = [(index.data(Qt.ItemDataRole.UserRole), index.column()) for index in persistent]
        self.layoutAboutToBeChanged.emit()
        self.sort_column = column
        self.sort_order = order
        self._sort_rows()
        updated = [
            self.index(self.row_for_identifier(identifier), col)
            if self.row_for_identifier(identifier) >= 0
            else QModelIndex()
            for identifier, col in identity
        ]
        self.changePersistentIndexList(persistent, updated)
        self.layoutChanged.emit()

    def _sort_rows(self) -> None:
        reverse = self.sort_order == Qt.SortOrder.DescendingOrder

        def sort_key(item: tuple[int, dict[str, Any]]) -> Any:
            idx, session = item
            pres = (
                self._presentation_cache[idx]
                if 0 <= idx < len(self._presentation_cache)
                else self._build_presentation(session)
            )
            cells = pres.cells
            if not self.dashboard and self.sort_column == len(cells) - 1:
                return int(pres.extra)
            return cells[self.sort_column].casefold()

        indexed = list(enumerate(self.sessions))
        indexed.sort(key=sort_key, reverse=reverse)
        self.sessions = [session for _, session in indexed]
        self._rebuild_indices_and_cache()
