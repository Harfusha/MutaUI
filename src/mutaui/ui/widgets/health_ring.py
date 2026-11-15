"""High-DPI zero-timer health indicator ring widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from mutaui.ui.localization import (
    set_localized_accessible_name,
    set_localized_tooltip,
)
from mutaui.ui.preferences import (
    active_language,
    translate_text,
)

MUTED = "#A0AEC0"
TEAL = "#61E0B9"
AMBER = "#F2BF70"
RED = "#FB8696"
TEXT = "#F1F6FA"


class HealthRing(QWidget):
    """High-DPI, zero-timer health indicator; repaint only on status changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui_language = active_language()
        self.total = 0
        self.healthy = 0
        self.setFixedSize(122, 122)
        set_localized_tooltip(self, "Share of sessions with no reported issues")
        set_localized_accessible_name(self, "Share of sessions with no reported issues")

    def set_ui_language(self, language: str) -> None:
        self.ui_language = language
        self.update()

    def set_health(self, total: int, problem: int) -> None:
        tot = max(0, int(total))
        healthy = max(0, tot - max(0, int(problem)))
        if (tot, healthy) != (self.total, self.healthy):
            self.total, self.healthy = tot, healthy
            self.update()

    def paintEvent(self, event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(18, 18, 86, 86)
        p.setPen(
            QPen(
                QColor("#314354"),
                10,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        p.drawArc(area, 0, 360 * 16)
        if self.total:
            fraction = self.healthy / self.total
            ring_color = QColor(TEAL if fraction >= 0.9 else AMBER if fraction >= 0.7 else RED)
            p.setPen(
                QPen(
                    ring_color,
                    10,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            p.drawArc(area, 90 * 16, -round(fraction * 360 * 16))
        p.setPen(QColor(TEXT))
        value_font = QFont("Segoe UI")
        value_font.setPixelSize(23)
        value_font.setWeight(QFont.Weight.Bold)
        p.setFont(value_font)
        value = f"{self.healthy / self.total:.0%}" if self.total else "—"
        p.drawText(QRectF(12, 44, 98, 30), Qt.AlignmentFlag.AlignCenter, value)
        p.setPen(QColor(MUTED))
        caption_font = QFont("Segoe UI")
        caption_font.setPixelSize(9)
        p.setFont(caption_font)
        p.drawText(
            QRectF(20, 77, 82, 13),
            Qt.AlignmentFlag.AlignCenter,
            translate_text("no issues", self.ui_language),
        )
        p.end()
