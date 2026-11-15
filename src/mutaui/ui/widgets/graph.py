"""Time-aware interactive zero-based line/area chart widget with optional second series."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

from mutagen_client import human_bytes
from performance import envelope_downsample, nearest_time_index

MUTED = "#A0AEC0"


class Graph(QWidget):
    """Time-aware, interactive, zero-based line/area chart with optional second series."""

    def __init__(
        self,
        color: str,
        parent: QWidget | None = None,
        *,
        unit: str = "number",
        secondary: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.color = QColor(color)
        self.secondary = QColor(secondary) if secondary else None
        self.unit = unit
        self.points: deque[tuple[float, float | None, float | None]] = deque(maxlen=720)
        self.timestamps: list[float] = []
        self.hover_index = -1
        self._geometry_revision = 0
        self._geometry_cache: Any = None
        self._secondary_pts: list[QPointF | None] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(153)

    def add(
        self,
        value: float,
        second: float | None = None,
        ts: float | None = None,
    ) -> None:
        stamp = float(time.time() if ts is None else ts)
        self.points.append((stamp, float(value), float(second) if second is not None else None))
        self.timestamps = [point[0] for point in self.points]
        self._geometry_revision += 1
        self._geometry_cache = None
        self.update()

    def set_data(self, entries: Iterable[tuple[Any, Any, Any]]) -> None:
        values = envelope_downsample(
            (
                (
                    float(t),
                    None if x is None else float(x),
                    None if y is None else float(y),
                )
                for t, x, y in entries
            ),
            max_points=600,
        )
        if tuple(self.points) == tuple(values):
            return
        self.points = deque(values, maxlen=720)
        self.timestamps = [point[0] for point in values]
        self.hover_index = -1
        self._geometry_revision += 1
        self._geometry_cache = None
        self.update()

    def amount(self, value: float | None) -> str:
        if value is None:
            return "—"
        if self.unit == "bytes_s":
            return str(human_bytes(value)) + "/s"
        if self.unit == "memory":
            return str(human_bytes(value))
        if self.unit == "percent":
            return f"{value:.1f} %"
        return f"{value:.1f}" if abs(value) < 10 else f"{value:.0f}"

    def _plot_rect(self) -> QRectF:
        return QRectF(self.rect().adjusted(68, 15, -17, -30))

    def mouseMoveEvent(self, event: Any) -> None:
        items = list(self.points)
        area = self._plot_rect()
        if not items or not area.contains(event.position().toPoint()):
            self.hover_index = -1
            QToolTip.hideText()
            self.update()
            return
        beginning = items[0][0]
        span = max(1.0, items[-1][0] - beginning)
        fractional = max(0.0, min(1.0, (event.position().x() - area.left()) / max(1, area.width())))
        target = beginning + fractional * span
        new_index = nearest_time_index(self.timestamps, target)
        if new_index == self.hover_index:
            return  # Avoid repainting the entire chart for every mouse pixel.
        self.hover_index = new_index
        t, first, second = items[self.hover_index]
        value = self.amount(first)
        if self.secondary:
            value += " / " + self.amount(second)
        QToolTip.showText(
            event.globalPosition().toPoint(),
            datetime.fromtimestamp(t).strftime("%d.%m. %H:%M:%S") + "\n" + value,
            self,
        )
        self.update()

    def leaveEvent(self, event: Any) -> None:
        self.hover_index = -1
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            p.end()
            return
        items = list(self.points)
        upper = (
            max(
                [x for _, x, _ in items if x is not None]
                + [y for _, _, y in items if y is not None]
                + [1.0]
            )
            * 1.17
        )
        if self.unit == "percent" and upper <= 100:
            upper = 100
        axis_font = QFont("Segoe UI")
        axis_font.setPixelSize(10)
        p.setFont(axis_font)
        for idx in range(5):
            y = rect.bottom() - rect.height() * idx / 4
            p.setPen(QPen(QColor("#2A3650"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor(MUTED))
            p.drawText(
                QRectF(0, y - 9, rect.left() - 9, 18),
                Qt.AlignmentFlag.AlignRight,
                self.amount(upper * idx / 4),
            )
        if not items:
            p.setPen(QColor(MUTED))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for the first samples…")
            p.end()
            return
        start, end = items[0][0], items[-1][0]
        span = max(1.0, end - start)
        p.setPen(QColor(MUTED))
        timefmt = "%H:%M:%S" if span < 1200 else "%d.%m. %H:%M"
        p.drawText(
            QRectF(rect.left(), rect.bottom() + 8, 165, 18),
            Qt.AlignmentFlag.AlignLeft,
            datetime.fromtimestamp(start).strftime(timefmt),
        )
        p.drawText(
            QRectF(rect.right() - 165, rect.bottom() + 8, 165, 18),
            Qt.AlignmentFlag.AlignRight,
            datetime.fromtimestamp(end).strftime(timefmt),
        )
        cache_key = (
            self._geometry_revision,
            rect.left(),
            rect.top(),
            rect.width(),
            rect.height(),
        )
        if self._geometry_cache is None or self._geometry_cache[0] != cache_key:
            # Path generation involves hundreds of QPointF/QPainterPath allocations.
            # Cache it until new data or a resize; hover only redraws the cursor.
            render_items = (
                items if len(items) > 1 else [items[0], (items[0][0] + 1, items[0][1], items[0][2])]
            )

            def coords(index: int) -> list[QPointF | None]:
                points: list[QPointF | None] = []
                for t, x, y in render_items:
                    value = x if index == 1 else y
                    if value is None:
                        points.append(None)
                        continue
                    points.append(
                        QPointF(
                            rect.left() + max(0, min(1, (t - start) / span)) * rect.width(),
                            rect.bottom() - max(0, value / upper) * rect.height(),
                        )
                    )
                return points

            max_gap = max(15.0, span / 110.0)

            def paths(
                points: list[QPointF | None],
            ) -> list[tuple[QPainterPath, QPainterPath, QPointF, int]]:
                runs: list[list[QPointF]] = []
                current: list[QPointF] = []
                previous_index: int | None = None
                for i, point in enumerate(points):
                    if point is None:
                        if current:
                            runs.append(current)
                            current = []
                        previous_index = None
                        continue
                    if (
                        current
                        and previous_index is not None
                        and render_items[i][0] - render_items[previous_index][0] > max_gap
                    ):
                        runs.append(current)
                        current = []
                    current.append(point)
                    previous_index = i
                if current:
                    runs.append(current)
                output: list[tuple[QPainterPath, QPainterPath, QPointF, int]] = []
                for run in runs:
                    if not run:
                        continue
                    path = QPainterPath(run[0])
                    for point in run[1:]:
                        path.lineTo(point)
                    area = QPainterPath(path)
                    if len(run) > 1:
                        area.lineTo(QPointF(run[-1].x(), rect.bottom()))
                        area.lineTo(QPointF(run[0].x(), rect.bottom()))
                        area.closeSubpath()
                    output.append((path, area, run[-1], len(run)))
                return output

            primary_pts = coords(1)
            primary_paths = paths(primary_pts)
            secondary_pts = coords(2) if self.secondary else []
            secondary_paths = paths(secondary_pts) if self.secondary else []
            self._secondary_pts = secondary_pts
            self._geometry_cache = (
                cache_key,
                primary_pts,
                primary_paths,
                secondary_paths,
            )
        else:
            _, primary_pts, primary_paths, secondary_paths = self._geometry_cache
            secondary_pts = getattr(self, "_secondary_pts", [])

        def draw_cached(
            paths_to_draw: list[tuple[QPainterPath, QPainterPath, QPointF, int]],
            color: QColor,
            fill: bool,
        ) -> None:
            for line_path, area_path, last_point, count in paths_to_draw:
                if count == 1:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(color)
                    p.drawEllipse(last_point, 3.5, 3.5)
                    continue
                if fill:
                    gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
                    top = QColor(color)
                    top.setAlpha(78)
                    bottom = QColor(color)
                    bottom.setAlpha(3)
                    gradient.setColorAt(0, top)
                    gradient.setColorAt(1, bottom)
                    p.fillPath(area_path, QBrush(gradient))
                p.setPen(QPen(color, 2.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(line_path)
            if paths_to_draw:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawEllipse(paths_to_draw[-1][2], 3.5, 3.5)

        draw_cached(primary_paths, self.color, True)
        if self.secondary:
            draw_cached(secondary_paths, self.secondary, False)
        if 0 <= self.hover_index < len(primary_pts):
            point = primary_pts[self.hover_index]
            dot_color = self.color
            if point is None and 0 <= self.hover_index < len(secondary_pts):
                point = secondary_pts[self.hover_index]
                dot_color = self.secondary or self.color
            if point is not None:
                # Vertical + horizontal crosshair
                p.setPen(QPen(QColor("#71809C"), 1, Qt.PenStyle.DashLine))
                p.drawLine(
                    QPointF(point.x(), rect.top()),
                    QPointF(point.x(), rect.bottom()),
                )
                p.drawLine(
                    QPointF(rect.left(), point.y()),
                    QPointF(rect.right(), point.y()),
                )
                p.setBrush(dot_color)
                p.setPen(QPen(QColor("#121C2D"), 2))
                p.drawEllipse(point, 5, 5)
        p.end()
