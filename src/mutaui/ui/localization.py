"""Widget localization helpers for dynamic EN/CS switching and accessibility."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QPushButton,
    QTableWidgetItem,
    QWidget,
)

from mutaui.ui.preferences import active_language, translate_text

_LOCALIZED_ITEM_ROLE = int(Qt.ItemDataRole.UserRole) + 73


def set_localized_text(
    widget: QLabel | QPushButton | QCheckBox | QAction | Any,
    text: str,
    *,
    czech: str | None = None,
) -> None:
    widget.setProperty("mutauiSourceText", text)
    widget.setProperty("mutauiCzechText", czech or translate_text(text, "cs"))
    localized = widget.property("mutauiCzechText") if active_language() == "cs" else text
    widget.setText(localized)


def set_localized_tooltip(widget: QWidget | QTableWidgetItem | Any, text: str) -> None:
    czech_tooltip = translate_text(text, "cs")
    if not isinstance(widget, QWidget):
        widget.setToolTip(czech_tooltip if active_language() == "cs" else text)
        return
    widget.setProperty("mutauiSourceTooltip", text)
    widget.setProperty("mutauiCzechTooltip", czech_tooltip)
    localized = widget.property("mutauiCzechTooltip") if active_language() == "cs" else text
    widget.setToolTip(localized)


def set_localized_placeholder(widget: QWidget | Any, text: str) -> None:
    widget.setProperty("mutauiSourcePlaceholder", text)
    widget.setProperty("mutauiCzechPlaceholder", translate_text(text, "cs"))
    localized = widget.property("mutauiCzechPlaceholder") if active_language() == "cs" else text
    widget.setPlaceholderText(localized)


def set_localized_title(widget: QWidget | Any, text: str, *, page_title: bool = False) -> None:
    widget.setProperty("mutauiSourceTitle", text)
    widget.setProperty("mutauiCzechTitle", translate_text(text, "cs"))
    widget.setProperty("mutauiTitleKind", "page" if page_title else "window")
    localized = widget.property("mutauiCzechTitle") if active_language() == "cs" else text
    if page_title:
        widget.setTitle(localized)
    else:
        widget.setWindowTitle(localized)


def set_localized_accessible_name(widget: QWidget | Any, text: str) -> None:
    widget.setProperty("mutauiSourceAccessibleName", text)
    widget.setProperty("mutauiCzechAccessibleName", translate_text(text, "cs"))
    localized = widget.property("mutauiCzechAccessibleName") if active_language() == "cs" else text
    widget.setAccessibleName(localized)
