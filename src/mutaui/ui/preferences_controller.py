"""Own live mode, theme, and language changes for the main window."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import QComboBox, QTableView, QTableWidget, QWidget

from mutagen_client import human_bytes
from mutaui.ui.localization import _LOCALIZED_ITEM_ROLE
from mutaui.ui.page_shell import PAGE_ROUTES
from mutaui.ui.preferences import (
    ADVANCED_ROUTE_IDS,
    resolve_theme,
    set_active_language,
    theme_stylesheet,
    translate,
    translate_route,
    translate_text,
)
from mutaui.ui.widgets.health_ring import HealthRing
from mutaui.ui.widgets.session_table import SessionTableModel


class PreferencesController:
    def __init__(self, window: Any, *, stylesheet: str = "") -> None:
        self.window = window
        self.stylesheet = stylesheet

    def set_ui_mode(self, mode: str) -> None:
        window = self.window
        window.ui_mode = mode if mode in {"basic", "advanced"} else "basic"
        if hasattr(window, "mode_selector"):
            with QSignalBlocker(window.mode_selector):
                window.mode_selector.setCurrentIndex(window.mode_selector.findData(window.ui_mode))
        advanced = window.ui_mode == "advanced"
        visible_sections: set[str] = set()
        section_route: str | None = None
        current_idx = window.pages.currentIndex() if hasattr(window, "pages") else 0
        current_route_id = (
            PAGE_ROUTES[current_idx].route_id if current_idx < len(PAGE_ROUTES) else ""
        )
        for route, nav_button in zip(PAGE_ROUTES, window.nav, strict=True):
            if route.section:
                section_route = route.route_id
            # Keep active route visible even if advanced in basic mode for context retention (M43)
            route_visible = (
                advanced
                or route.route_id not in ADVANCED_ROUTE_IDS
                or route.route_id == current_route_id
            )
            nav_button.setVisible(route_visible)
            if section_route is not None and route_visible:
                visible_sections.add(section_route)
        for route_id, section_label in window.nav_section_labels.items():
            section_label.setVisible(route_id in visible_sections)

    def apply_theme(self, theme: str) -> None:
        try:
            system_is_light = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light
        except (AttributeError, RuntimeError):
            system_is_light = False
        resolved = resolve_theme(theme, system_is_light=system_is_light)
        self.window.setStyleSheet(theme_stylesheet(self.stylesheet, resolved))

    def apply_ui_language(self, language: str) -> None:
        window = self.window
        window.ui_language = set_active_language(language)
        for health_ring in window.findChildren(HealthRing):
            health_ring.set_ui_language(window.ui_language)
        for widget in (window, *window.findChildren(QWidget)):
            source_tooltip = widget.property("mutauiSourceTooltip")
            if isinstance(source_tooltip, str):
                czech_tooltip = widget.property("mutauiCzechTooltip")
                widget.setToolTip(czech_tooltip if window.ui_language == "cs" else source_tooltip)
            source_placeholder = widget.property("mutauiSourcePlaceholder")
            if isinstance(source_placeholder, str):
                czech_placeholder = widget.property("mutauiCzechPlaceholder")
                widget.setPlaceholderText(
                    czech_placeholder if window.ui_language == "cs" else source_placeholder
                )
            source_title = widget.property("mutauiSourceTitle")
            if isinstance(source_title, str):
                czech_title = widget.property("mutauiCzechTitle")
                localized_title = czech_title if window.ui_language == "cs" else source_title
                if widget.property("mutauiTitleKind") == "page":
                    widget.setTitle(localized_title)
                else:
                    widget.setWindowTitle(localized_title)
            source_accessible_name = widget.property("mutauiSourceAccessibleName")
            if isinstance(source_accessible_name, str):
                czech_accessible_name = widget.property("mutauiCzechAccessibleName")
                widget.setAccessibleName(
                    czech_accessible_name if window.ui_language == "cs" else source_accessible_name
                )
        for widget in (
            *window.findChildren(QWidget),
            *window.findChildren(QAction),
        ):
            source_text = widget.property("mutauiSourceText")
            if isinstance(source_text, str):
                czech_text = widget.property("mutauiCzechText")
                localized = czech_text if window.ui_language == "cs" else source_text
                widget.setText(
                    localized
                    if isinstance(localized, str)
                    else translate_text(source_text, window.ui_language)
                )
        for combo in window.findChildren(QComboBox):
            for index in range(combo.count()):
                source_item = combo.itemData(index, _LOCALIZED_ITEM_ROLE)
                if isinstance(source_item, str):
                    combo.setItemText(index, translate_text(source_item, window.ui_language))
        for table in window.findChildren(QTableWidget):
            for column in range(table.columnCount()):
                header_item = table.horizontalHeaderItem(column)
                if header_item is None:
                    continue
                source_header = header_item.data(_LOCALIZED_ITEM_ROLE)
                if isinstance(source_header, str):
                    header_item.setText(translate_text(source_header, window.ui_language))
        for table in window.findChildren(QTableView):
            model = table.model()
            if isinstance(model, SessionTableModel):
                model.set_ui_language(window.ui_language)
        for index, route in enumerate(PAGE_ROUTES):
            title = translate_route(route.route_id, "title", window.ui_language, route.title)
            tooltip = translate_route(route.route_id, "tooltip", window.ui_language, route.tooltip)
            window.nav[index].setText(f"{route.glyph}    {title}")
            window.nav[index].setToolTip(tooltip)
            section_label = window.nav_section_labels.get(route.route_id)
            if section_label is not None and route.section:
                section_label.setText(translate_text(route.section, window.ui_language))
        current_route = PAGE_ROUTES[window.pages.currentIndex()]
        window.page_name.setText(
            translate_route(
                current_route.route_id, "title", window.ui_language, current_route.title
            )
        )
        window.page_caption.setText(
            translate_route(
                current_route.route_id,
                "caption",
                window.ui_language,
                current_route.caption,
            )
        )
        if hasattr(window, "last_metrics"):
            metrics = window.last_metrics
            window.gui_usage_label.setText(
                f"{translate_text('Application load', window.ui_language)}: CPU "
                f"{metrics.get('gui_cpu', 0):.1f} %  ·  "
                f"RAM {human_bytes(metrics.get('gui_memory', 0))}  ·  "
                f"{translate_text('measured for the UI process, not Mutagen', window.ui_language)}"
            )
        if hasattr(window, "_last_monitor_stats") and window._stats_cache_range is not None:
            window.apply_statistics(window._last_monitor_stats, window._stats_cache_range)
        if hasattr(window, "monitor_labels") and hasattr(window, "last_metrics"):
            window.monitor_labels["traffic"].setText(
                f"{translate_text('outbound', window.ui_language)} "
                f"{human_bytes(window.traffic_rates[0])}/s · "
                f"{translate_text('inbound', window.ui_language)} "
                f"{human_bytes(window.traffic_rates[1])}/s"
            )
            active, problems = window.session_counts
            window.monitor_labels["sessions"].setText(
                f"{active} {translate_text('active', window.ui_language)} · "
                f"{problems} {translate_text('issues', window.ui_language)}"
            )
        if hasattr(window, "mode_selector"):
            for index, mode in enumerate(("basic", "advanced")):
                window.mode_selector.setItemText(
                    index, translate(f"mode.{mode}", window.ui_language)
                )
        if hasattr(window, "theme_input"):
            for index, theme in enumerate(("system", "light", "dark")):
                window.theme_input.setItemText(
                    index, translate(f"appearance.{theme}", window.ui_language)
                )
            window.language_input.setItemText(
                0, translate("appearance.english", window.ui_language)
            )
            window.language_input.setItemText(1, translate("appearance.czech", window.ui_language))
        window.update_endpoint_sessions(window.snapshot)
