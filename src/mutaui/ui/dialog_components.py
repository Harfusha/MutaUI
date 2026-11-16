from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QPushButton, QWidget

from mutaui.ui.localization import _LOCALIZED_ITEM_ROLE, set_localized_text
from mutaui.ui.preferences import active_language, translate_text


def label(text: str, *, muted: bool = False, size: int | None = None, bold: bool = False) -> QLabel:
    result = QLabel()
    set_localized_text(result, text)
    if len(text) >= 72 or "\n" in text:
        result.setWordWrap(True)
    if muted:
        result.setObjectName("muted")
    if size or bold:
        style = []
        if size:
            style.append(f"font-size: {size}px")
        if bold:
            style.append("font-weight: 700")
        result.setStyleSheet(";".join(style))
    return result


def button(
    text: str, fn: Callable[..., Any] | None = None, *, kind: str = "", minwidth: int = 0
) -> QPushButton:
    b = QPushButton()
    set_localized_text(b, text)
    if kind:
        b.setObjectName(kind)
    if minwidth:
        b.setMinimumWidth(minwidth)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if fn:
        b.clicked.connect(fn)
    return b


def localized_label(text: str) -> QLabel:
    widget = QLabel()
    set_localized_text(widget, text)
    return widget


def add_localized_row(form: QFormLayout, text: str, *fields: QWidget) -> None:
    form.addRow(localized_label(text), *fields)


def add_localized_item(combo: QComboBox, text: str, *user_data: Any) -> None:
    combo.addItem(text, *user_data)
    index = combo.count() - 1
    combo.setItemData(index, text, _LOCALIZED_ITEM_ROLE)
    combo.setItemText(index, translate_text(text, active_language()))


def add_localized_items(combo: QComboBox, texts: list[str]) -> None:
    for text in texts:
        add_localized_item(combo, text)


def localized_checkbox(text: str) -> QCheckBox:
    widget = QCheckBox()
    set_localized_text(widget, text)
    return widget
