"""Stable page metadata and on-demand stacked-page construction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from PySide6.QtWidgets import QStackedWidget, QWidget


@dataclass(frozen=True, slots=True)
class PageRoute:
    route_id: str
    title: str
    caption: str
    search_description: str
    glyph: str
    tooltip: str
    section: str | None = None


PAGE_ROUTES = (
    PageRoute(
        "overview",
        "Overview",
        "Current sync status and system resource usage",
        "Session overview and system resource usage",
        "◈",
        "Ctrl+1 · Status overview and graphs",
        "WORKSPACE",
    ),
    PageRoute(
        "sync",
        "Sync",
        "Monitor, create and manage sync sessions",
        "Manage sync sessions",
        "⇄",
        "Ctrl+2 · Manage sync sessions",
        "SESSIONS",
    ),
    PageRoute(
        "forwarding",
        "Forwarding",
        "Manage port-forwarding sessions and transferred data",
        "Manage port-forwarding sessions",
        "↗",
        "Ctrl+3 · Manage port-forwarding sessions",
    ),
    PageRoute(
        "action-history",
        "Action History",
        "Records of commands run through this application",
        "Records of commands run through the application",
        "≡",
        "Ctrl+4 · Action records",
        "TOOLS & DIAGNOSTICS",
    ),
    PageRoute(
        "daemon",
        "Daemon",
        "Daemon run control and Windows registration",
        "Mutagen daemon control and registration",
        "◉",
        "Ctrl+5 · Daemon — start / stop / register",
    ),
    PageRoute(
        "settings",
        "Settings",
        "CLI path, data refresh and application behaviour",
        "CLI path, intervals and application behaviour",
        "⚙",
        "Ctrl+6 · Application settings",
    ),
    PageRoute(
        "monitoring",
        "Monitoring",
        "Historical CPU, RAM, disk I/O and traffic graphs",
        "Historical CPU, RAM and traffic graphs",
        "▥",
        "Ctrl+7 · Monitoring – historical graphs",
    ),
    PageRoute(
        "diagnostics",
        "Diagnostics",
        "Session issues and safe export of diagnostic data",
        "Session issues and diagnostics export",
        "⚕",
        "Ctrl+8 · Diagnostics and export",
    ),
    PageRoute(
        "alerts",
        "Alerts",
        "Resource limits and alerting rules",
        "Resource limits and alert rules",
        "♢",
        "Ctrl+9 · Resource alerts",
    ),
    PageRoute(
        "endpoints",
        "Endpoints",
        "ALPHA/BETA and forwarding status from local Mutagen daemon",
        "ALPHA/BETA endpoint status from the daemon",
        "◎",
        "Ctrl+0 · ALPHA / BETA endpoint status",
        "ENDPOINT STATUS",
    ),
    PageRoute(
        "servers",
        "Servers",
        "Group sessions by remote hosts and bulk actions",
        "Server groups and bulk actions",
        "▣",
        "Ctrl+Shift+1 · Server groups and bulk actions",
        "SERVER GROUPS",
    ),
)


class LazyStackedWidget(QStackedWidget):
    """Stack pages by stable index and construct registered pages on first use."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page_factories: dict[int, Callable[[], QWidget]] = {}

    def add_lazy_page(self, factory: Callable[[], QWidget]) -> int:
        index = self.addWidget(QWidget())
        self._page_factories[index] = factory
        return index

    def is_page_built(self, index: int) -> bool:
        return index not in self._page_factories

    def ensure_page(self, index: int) -> QWidget:
        factory = self._page_factories.pop(index, None)
        if factory is None:
            page = cast(QWidget | None, self.widget(index))
            if page is None:
                raise IndexError(f"No page registered at index {index}")
            return page

        try:
            page = factory()
        except Exception:
            self._page_factories[index] = factory
            raise
        placeholder = self.widget(index)
        if placeholder is None:
            self._page_factories[index] = factory
            raise IndexError(f"No placeholder registered at index {index}")
        self.removeWidget(placeholder)
        self.insertWidget(index, page)
        placeholder.deleteLater()
        return page

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < self.count():
            self.ensure_page(index)
        super().setCurrentIndex(index)
