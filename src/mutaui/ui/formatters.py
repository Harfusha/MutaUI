"""UI formatters, helpers, and detail HTML renderers."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape as html_escape
from pathlib import Path
from typing import Any, cast

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QWidget

from mutagen_client import human_bytes
from mutaui.ui.localization import set_localized_text
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.theme_constants import BLUE, BORDER, MUTED, TEXT
from settings import load_settings, settings_path
from settings import write_settings as save_settings_file


def get_settings_path() -> Path:
    import sys

    app_mod = sys.modules.get("app")
    if app_mod is not None and hasattr(app_mod, "settings_path"):
        return cast(Path, app_mod.settings_path())
    return cast(Path, settings_path())


def read_settings() -> dict[str, Any]:
    return cast(dict[str, Any], load_settings(get_settings_path()).values)


def get_active_language() -> str:
    import sys

    app_mod = sys.modules.get("app")
    if app_mod is not None and hasattr(app_mod, "active_language"):
        return cast(str, app_mod.active_language())
    return active_language()


def settings_warning_message(warnings: tuple[str, ...]) -> str | None:
    if not warnings:
        return None
    recovered = any(
        "restored from the last valid settings backup" in warning.casefold() for warning in warnings
    )
    message = (
        "Settings were restored from the last valid backup. Review Settings."
        if recovered
        else "Some settings were invalid. Safe defaults are active; the original will be backed up when settings are saved."
    )
    return translate_text(message, get_active_language())


def write_settings(data: dict[str, Any]) -> None:
    save_settings_file(get_settings_path(), data)


def localized_action(text: str, parent: QWidget) -> QAction:
    widget = QAction("", parent)
    set_localized_text(widget, text)
    return widget


def _czech_plural(count: int, forms: tuple[str, str, str]) -> str:
    remainder_100 = count % 100
    if remainder_100 in range(12, 15):
        return forms[2]
    remainder_10 = count % 10
    if remainder_10 == 1:
        return forms[0]
    if remainder_10 in {2, 3, 4}:
        return forms[1]
    return forms[2]


def separator() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background:{BORDER}; border:0")
    return f


def field_format(field: str, value: float | None) -> str:
    if value is None:
        return "Not measured"
    if field == "cpu":
        return f"{value:.1f} %"
    if field == "memory":
        return str(human_bytes(value))
    return str(human_bytes(value)) + "/s"


def readable_record_lines(value: object, *, indent: int = 0) -> list[str]:
    """Turn nested Mutagen conflict/problem objects into labeled text lines."""
    pad = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            label_text = "".join(
                f" {char.lower()}" if char.isupper() else char for char in str(key)
            )
            label_text = label_text.replace("_", " ").strip().capitalize()
            if isinstance(item, (dict, list, tuple)):
                lines.append(f"{pad}{label_text}:")
                lines.extend(readable_record_lines(item, indent=indent + 2))
            else:
                lines.append(f"{pad}{label_text}: {item}")
        return lines or [f"{pad}Details unavailable"]
    if isinstance(value, (list, tuple)):
        lines = []
        for index, item in enumerate(value, 1):
            if isinstance(item, (dict, list, tuple)):
                lines.append(f"{pad}Item {index}")
                lines.extend(readable_record_lines(item, indent=indent + 2))
            else:
                lines.append(f"{pad}• {item}")
        return lines or [f"{pad}None"]
    return [f"{pad}{value}"]


def session_detail_html(lines: Iterable[str], separator_text: str) -> str:
    """Render session detail rows with visual hierarchy while escaping values."""
    rendered = []
    for line in lines:
        if line == separator_text:
            rendered.append(f'<hr style="border:0;border-top:1px solid {BORDER};margin:9px 0;">')
        elif "\n" in line:
            field, value = line.split("\n", 1)
            rendered.append(
                '<div style="margin:4px 0 10px 0;">'
                f'<div style="color:{MUTED};font-size:11px;font-weight:600;">{html_escape(field)}</div>'
                f'<div style="color:{TEXT};font-size:13px;">{html_escape(value)}</div>'
                "</div>"
            )
        elif line == line.upper() and len(line) <= 42:
            rendered.append(
                f'<div style="color:{BLUE};font-size:11px;font-weight:700;margin:5px 0;">'
                f"{html_escape(line)}</div>"
            )
        elif ": " in line:
            field, value = line.split(": ", 1)
            indent = len(field) - len(field.lstrip())
            rendered.append(
                f'<div style="margin:2px 0 2px {indent * 10}px;">'
                f'<span style="color:{MUTED};">{html_escape(field.strip())}:</span> '
                f'<span style="color:{TEXT};">{html_escape(value)}</span></div>'
            )
        else:
            indent = len(line) - len(line.lstrip())
            rendered.append(
                f'<div style="margin:2px 0 2px {indent * 10}px;color:{TEXT};">'
                f"{html_escape(line.strip())}</div>"
            )
    return '<div style="line-height:1.35;">' + "".join(rendered) + "</div>"
