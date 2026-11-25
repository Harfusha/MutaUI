"""Keyboard-first, no-network palette for navigation and exact session actions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mutaui.ui.localization import (
    set_localized_accessible_name,
    set_localized_placeholder,
    set_localized_title,
)
from mutaui.ui.page_shell import PAGE_ROUTES
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.widgets.basic import label


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
            "Search pages, sessions, and commands · ↑/↓ to navigate · Enter to choose · Escape to close",
            muted=True,
        )
        layout.addWidget(hint)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        set_localized_placeholder(self.search, "Search page…")
        set_localized_accessible_name(self.search, "Search pages, sessions, and commands")
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSpacing(2)
        set_localized_accessible_name(self.list, "Search results")
        layout.addWidget(self.list, 1)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.choose)
        self.list.itemActivated.connect(lambda _: self.choose())
        self.list.itemDoubleClicked.connect(lambda _: self.choose())
        self.filter("")
        self.search.setFocus()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            if key_event.key() == Qt.Key.Key_Down:
                row = self.list.currentRow()
                if row < self.list.count() - 1:
                    self.list.setCurrentRow(row + 1)
                return True
            if key_event.key() == Qt.Key.Key_Up:
                row = self.list.currentRow()
                if row > 0:
                    self.list.setCurrentRow(row - 1)
                return True
        return super().eventFilter(watched, event)

    def filter(self, term: str) -> None:
        self.list.clear()
        query = term.casefold().split()
        lang = active_language()
        for index, page in enumerate(self.PAGES):
            caption = self.CAPTIONS[index] if index < len(self.CAPTIONS) else ""
            route = PAGE_ROUTES[index] if index < len(PAGE_ROUTES) else None
            title_en = page
            title_cs = translate_text(page, "cs")
            caption_en = caption
            caption_cs = translate_text(caption, "cs")
            route_id = route.route_id if route else ""
            searchable = f"{title_en} {title_cs} {caption_en} {caption_cs} {route_id}".casefold()
            if all(word in searchable for word in query):
                glyph = self.GLYPHS[index] if index < len(self.GLYPHS) else "·"
                display_title = translate_text(page, lang)
                item = QListWidgetItem(f"  {glyph}   {display_title}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(translate_text(caption, lang))
                self.list.addItem(item)
        for action, kind, identifier, title, searchable in self.commands:
            title_localized = translate_text(title, lang)
            searchable_full = f"{title} {title_localized} {searchable}".casefold()
            if all(word in searchable_full for word in query):
                item = QListWidgetItem(f"  ↪   {title_localized}")
                item.setData(Qt.ItemDataRole.UserRole, ("command", action, kind, identifier))
                item.setToolTip(title_localized)
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


__all__ = ["QuickNavigator"]
