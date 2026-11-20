"""Keyboard-first, no-network palette for navigation and exact session actions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mutaui.ui.localization import (
    set_localized_placeholder,
    set_localized_title,
)
from mutaui.ui.page_shell import PAGE_ROUTES
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
            "Search pages, sessions, and commands · Enter to choose · Escape to close", muted=True
        )
        layout.addWidget(hint)
        self.search = QLineEdit()
        set_localized_placeholder(self.search, "Search page…")
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSpacing(2)
        layout.addWidget(self.list, 1)
        self.search.textChanged.connect(self.filter)
        self.search.returnPressed.connect(self.choose)
        self.list.itemActivated.connect(lambda _: self.choose())
        self.list.itemDoubleClicked.connect(lambda _: self.choose())
        self.filter("")
        self.search.setFocus()

    def filter(self, term: str) -> None:
        self.list.clear()
        query = term.casefold().split()
        for index, page in enumerate(self.PAGES):
            caption = self.CAPTIONS[index] if index < len(self.CAPTIONS) else ""
            searchable = f"{page} {caption}".casefold()
            if all(word in searchable for word in query):
                glyph = self.GLYPHS[index] if index < len(self.GLYPHS) else "·"
                item = QListWidgetItem(f"  {glyph}   {page}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(caption)
                self.list.addItem(item)
        for action, kind, identifier, title, searchable in self.commands:
            if all(word in f"{title} {searchable}".casefold() for word in query):
                item = QListWidgetItem(f"  ↪   {title}")
                item.setData(Qt.ItemDataRole.UserRole, ("command", action, kind, identifier))
                item.setToolTip(title)
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
