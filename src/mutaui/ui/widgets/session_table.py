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
        """Preserve stable native session identity across polling refreshes.

        Incremental changes preserve persistent indexes for small ordered
        insertions/removals. Reorders, duplicates and large replacements
        conservatively reset the model. No native session state is modified.
        """
        incoming = list(sessions)
        previous = self._presentation_cache
        self.favorites = set(favorites)
        presentation = [self._build_presentation(session) for session in incoming]
        if self.sort_column >= 0:
            column = self.sort_column
            last = len(self.headers) - 1

            def sort_key(item: tuple[dict[str, Any], SessionRowPresentation]) -> Any:
                pres = item[1]
                if not self.dashboard and column == last:
                    return pres.extra
                return pres.cells[column].casefold()

            pairs = sorted(
                zip(incoming, presentation, strict=True),
                key=sort_key,
                reverse=self.sort_order == Qt.SortOrder.DescendingOrder,
            )
            incoming = [session for session, _presentation in pairs]
            presentation = [pres for _session, pres in pairs]

        old_ids = tuple(item.identifier for item in previous)
        new_ids = tuple(item.identifier for item in presentation)
        stable_rows = (
            old_ids == new_ids
            and len(previous) == len(presentation)
            and all(new_ids)
            and len(set(new_ids)) == len(new_ids)
        )
        if stable_rows:
            self.sessions = incoming
            self._presentation_cache = presentation
            self._id_to_row = {identifier: index for index, identifier in enumerate(new_ids)}
            if self.columnCount():
                for index, (before, after) in enumerate(zip(previous, presentation, strict=True)):
                    if before != after:
                        self.dataChanged.emit(
                            self.index(index, 0),
                            self.index(index, self.columnCount() - 1),
                            [],
                        )
            return

        # For small structural deltas where surviving IDs retain their relative
        # order, use Qt insert/remove signals rather than invalidating the whole
        # view (including scroll position and persistent selection indexes).
        old_set = set(old_ids)
        new_set = set(new_ids)
        identity_is_unambiguous = (
            bool(old_ids)
            and bool(new_ids)
            and all(old_ids)
            and all(new_ids)
            and len(old_set) == len(old_ids)
            and len(new_set) == len(new_ids)
        )
        old_survivors = tuple(identifier for identifier in old_ids if identifier in new_set)
        new_survivors = tuple(identifier for identifier in new_ids if identifier in old_set)
        change_count = len(old_set - new_set) + len(new_set - old_set)
        if identity_is_unambiguous and old_survivors == new_survivors and change_count <= 64:
            old_presentation = {item.identifier: item for item in previous}
            for index in range(len(self.sessions) - 1, -1, -1):
                if old_ids[index] not in new_set:
                    self.beginRemoveRows(QModelIndex(), index, index)
                    del self.sessions[index]
                    del self._presentation_cache[index]
                    self.endRemoveRows()

            for index, identifier in enumerate(new_ids):
                if (
                    index < len(self._presentation_cache)
                    and self._presentation_cache[index].identifier == identifier
                ):
                    continue
                self.beginInsertRows(QModelIndex(), index, index)
                self.sessions.insert(index, incoming[index])
                self._presentation_cache.insert(index, presentation[index])
                self.endInsertRows()

            self.sessions = incoming
            self._presentation_cache = presentation
            self._id_to_row = {identifier: index for index, identifier in enumerate(new_ids)}
            if self.columnCount():
                for index, item in enumerate(presentation):
                    if item.identifier in old_presentation and old_presentation[item.identifier] != item:
                        self.dataChanged.emit(
                            self.index(index, 0),
                            self.index(index, self.columnCount() - 1),
                            [],
                        )
            return

        self.beginResetModel()
        self.sessions = incoming
        self._presentation_cache = presentation
        self._id_to_row = {identifier: index for index, identifier in enumerate(new_ids)}
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
        # Persistent QModelIndex objects exist for *any* column; UserRole
        # exposes the session identifier on column 0 only. Mapping other
        # columns by UserRole would silently invalidate their persistent index.
        persistent = self.persistentIndexList()
        positions = [(index.row(), index.column()) for index in persistent]
        self.layoutAboutToBeChanged.emit()
        self.sort_column = column
        self.sort_order = order
        old_rows = self._sort_rows()
        new_position_by_old = {old: new for new, old in enumerate(old_rows)}
        updated = [
            self.index(new_position_by_old[old], col)
            if old in new_position_by_old
            else QModelIndex()
            for old, col in positions
        ]
        self.changePersistentIndexList(persistent, updated)
        self.layoutChanged.emit()

    def _sort_rows(self) -> list[int]:
        """Sort cached presentations and return the old position of each row.

        The explicit old-row mapping handles repeated/empty native IDs without
        losing persistent selection and avoids recomputing expensive cell data.
        """
        reverse = self.sort_order == Qt.SortOrder.DescendingOrder

        def sort_key(item: tuple[int, dict[str, Any], SessionRowPresentation]) -> Any:
            _old, _session, pres = item
            if not self.dashboard and self.sort_column == len(pres.cells) - 1:
                return pres.extra
            return pres.cells[self.sort_column].casefold()

        rows = [
            (
                old,
                session,
                self._presentation_cache[old]
                if old < len(self._presentation_cache)
                else self._build_presentation(session),
            )
            for old, session in enumerate(self.sessions)
        ]
        rows.sort(key=sort_key, reverse=reverse)
        self.sessions = [session for _old, session, _pres in rows]
        self._presentation_cache = [pres for _old, _session, pres in rows]
        self._id_to_row = {
            pres.identifier: new for new, pres in enumerate(self._presentation_cache)
        }
        return [old for old, _session, _pres in rows]
