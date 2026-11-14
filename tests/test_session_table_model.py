"""Session model keeps row identity and rendering data through large snapshots."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication, QTableWidget

from app import MainWindow, SessionTableModel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_session_model_handles_reviewed_snapshot_sizes(qapp):
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    for count in (10, 100, 500, 1000):
        sessions = [
            {
                "identifier": f"session-{index}",
                "name": f"Project {index}",
                "status": 6,
                "alpha": {"path": f"C:/alpha/{index}"},
                "beta": {"path": f"C:/beta/{index}"},
            }
            for index in range(count)
        ]
        model.set_sessions(sessions)

        assert model.rowCount() == count
        assert model.index(count - 1, 0).data(Qt.ItemDataRole.UserRole) == f"session-{count - 1}"
        assert model.index(count - 1, 0).data() == f"Project {count - 1}"


def test_session_model_sort_retains_stable_identifiers(qapp):
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    model.set_sessions(
        [
            {"identifier": "b", "name": "Beta", "status": 6},
            {"identifier": "a", "name": "Alpha", "status": 6},
        ]
    )

    model.sort(0, Qt.SortOrder.AscendingOrder)

    assert model.index(0, 0).data(Qt.ItemDataRole.UserRole) == "a"
    assert model.row_for_identifier("b") == 1


def test_session_table_height_stays_bounded_for_large_snapshots(qapp):
    table = QTableWidget(1000, 1)
    table.setHorizontalHeaderLabels(["NAME"])

    MainWindow.fit_table_to_rows(table)

    assert table.height() <= 520
    assert table.verticalScrollBar().maximum() > 0


def test_session_model_empty_headers_and_favorite_unnamed_session(qapp):
    model = SessionTableModel([], "sync")
    model.set_sessions([{"identifier": "", "name": "", "status": 6}], favorites=("",))

    assert model._cells(model.sessions[0])[0][0] == "★ (unnamed)"
    model.set_ui_language("cs")
    assert model.columnCount() == 0


def test_session_model_invalid_indexes_unknown_colors_and_sort_guards(qapp):
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    model.set_sessions([{"identifier": "x", "name": "X", "status": 999}])

    assert model.data(QModelIndex()) is None
    assert model.data(model.index(4, 0)) is None
    assert model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole) is None
    assert model.data(model.index(0, 4), Qt.ItemDataRole.UserRole + 1) == 0
    dashboard = SessionTableModel(["NAME", "STATUS"], "sync", dashboard=True)
    dashboard.set_sessions([{"identifier": "x", "name": "MiXeD", "status": 6}])
    assert dashboard.data(dashboard.index(0, 0), Qt.ItemDataRole.UserRole + 1) == "mixed"
    model.sort(-1)
    model.sort(99)

    forward = SessionTableModel(["NAME", "STATUS", "SOURCE", "DEST", "CONNECTIONS"], "forward")
    forward.set_sessions(
        [
            {"identifier": "valid", "name": "Valid", "openConnections": 4},
            {"identifier": "invalid", "name": "Invalid", "openConnections": "unknown"},
        ]
    )
    forward.sort(4)
    assert [session["identifier"] for session in forward.sessions] == ["invalid", "valid"]
