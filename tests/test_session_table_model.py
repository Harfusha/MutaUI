"""Session model keeps row identity and rendering data through large snapshots."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app import SessionTableModel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_session_model_handles_reviewed_snapshot_sizes(qapp):
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    for count in (10, 100, 500, 1000):
        sessions = [
            {"identifier": f"session-{index}", "name": f"Project {index}", "status": 6,
             "alpha": {"path": f"C:/alpha/{index}"}, "beta": {"path": f"C:/beta/{index}"}}
            for index in range(count)
        ]
        model.set_sessions(sessions)

        assert model.rowCount() == count
        assert model.index(count - 1, 0).data(Qt.ItemDataRole.UserRole) == f"session-{count - 1}"
        assert model.index(count - 1, 0).data() == f"Project {count - 1}"


def test_session_model_sort_retains_stable_identifiers(qapp):
    model = SessionTableModel(["NAME", "STATUS", "ALPHA", "BETA", "CONFLICTS"], "sync")
    model.set_sessions([
        {"identifier": "b", "name": "Beta", "status": 6},
        {"identifier": "a", "name": "Alpha", "status": 6},
    ])

    model.sort(0, Qt.SortOrder.AscendingOrder)

    assert model.index(0, 0).data(Qt.ItemDataRole.UserRole) == "a"
    assert model.row_for_identifier("b") == 1
