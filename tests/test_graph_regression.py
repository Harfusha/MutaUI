"""Tests and regression matrix for Graph widget painting and hover (CORE-01 / F2-013 / F2-AC-021)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import PySide6  # noqa: F401
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

import app as app_module
from mutaui.ui.widgets.health_ring import HealthRing


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_graph_hover_when_primary_point_is_none_does_not_crash(qapp):
    """CORE-01: hovering on an index where primary sample is None must not raise AttributeError."""
    graph = app_module.Graph("#ffffff", unit="number", secondary="#00ff00")
    graph.resize(400, 200)
    # index 1 has None as primary, but valid secondary
    graph.set_data(
        [
            (1000, 10, 20),
            (1010, None, 25),
            (1020, 15, 30),
        ]
    )
    graph.hover_index = 1
    graph.show()
    qapp.processEvents()
    graph.repaint()
    qapp.processEvents()
    graph.close()


def test_graph_hover_all_none_samples(qapp):
    """Matrix: all None samples must paint cleanly without exceptions."""
    graph = app_module.Graph("#ffffff", unit="number")
    graph.resize(400, 200)
    graph.set_data([(1000, None, None), (1010, None, None), (1020, None, None)])
    for i in range(3):
        graph.hover_index = i
        graph.repaint()
        qapp.processEvents()
    graph.close()


def test_graph_hover_first_and_middle_and_last_none(qapp):
    """Matrix: first sample None, middle sample None, last sample None."""
    graph = app_module.Graph("#ffffff", unit="number", secondary="#ff00ff")
    graph.resize(400, 200)
    graph.set_data(
        [
            (1000, None, None),
            (1010, 50, 60),
            (1020, None, None),
            (1030, 70, 80),
            (1040, None, None),
        ]
    )
    for idx in (0, 2, 4):
        graph.hover_index = idx
        graph.repaint()
        qapp.processEvents()
    graph.close()


def test_graph_hover_repeatedly_and_resize(qapp):
    """Matrix: rapid hover transitions and widget resizing."""
    graph = app_module.Graph("#3b82f6", unit="kbps", secondary="#10b981")
    graph.resize(300, 150)
    graph.set_data([(1000 + i * 10, i if i % 2 == 0 else None, i * 2) for i in range(20)])
    graph.show()
    qapp.processEvents()

    for idx in range(-1, 22):
        graph.hover_index = idx
        graph.repaint()
        qapp.processEvents()

    for size in ((200, 100), (500, 300), (100, 50), (600, 400)):
        graph.resize(*size)
        graph.repaint()
        qapp.processEvents()

    graph.close()


def test_graph_leave_event_and_units_formatting(qapp):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    graph = app_module.Graph("#3b82f6", unit="bytes_s", secondary="#10b981")
    graph.resize(300, 150)
    graph.set_data([(1000 + i * 10, i * 100, i * 50) for i in range(10)])
    graph.show()
    qapp.processEvents()

    assert graph.amount(None) == "—"
    assert "/s" in graph.amount(1024)
    graph.unit = "memory"
    assert graph.amount(1024 * 1024)
    graph.unit = "percent"
    assert "%" in graph.amount(45.5)
    graph.unit = "number"
    assert graph.amount(5.5) == "5.5"
    assert graph.amount(50.0) == "50"

    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(100, 50),
        QPointF(100, 50),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    graph.mouseMoveEvent(move_event)
    qapp.processEvents()

    outside_event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(5, 5),
        QPointF(5, 5),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    graph.mouseMoveEvent(outside_event)

    graph.hover_index = 2
    graph.leaveEvent(QEvent(QEvent.Type.Leave))
    assert graph.hover_index == -1
    graph.close()

    from PySide6.QtGui import QPixmap

    ring = HealthRing()
    for total, prob in ((0, 0), (10, 0), (10, 2), (10, 6)):
        ring.set_health(total, prob)
        pix = QPixmap(122, 122)
        ring.render(pix)
    ring.set_ui_language("cs")
    pix = QPixmap(122, 122)
    ring.render(pix)
    ring.close()
