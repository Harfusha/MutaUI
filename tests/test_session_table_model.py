"""Session model keeps row identity and rendering data through large snapshots."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
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
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.columnCount(model.index(0, 0)) == 0
    assert model.headerData(99, Qt.Orientation.Horizontal) is None
    assert model.headerData(0, Qt.Orientation.Vertical) is None
    assert model.data(model.index(0, 1), Qt.ItemDataRole.ToolTipRole) is not None
    assert model.data(model.index(0, 0), Qt.ItemDataRole.ToolTipRole) is not None

    # Status colors
    for s_dict in (
        {"identifier": "s1", "status": 6},  # active
        {"identifier": "s2", "status": 4},  # busy
        {"identifier": "s3", "paused": True},  # paused
        {"identifier": "s4", "lastError": "err"},  # error
    ):
        m = SessionTableModel(["NAME", "STATUS"], "sync")
        m.set_sessions([s_dict])
        color = m.data(m.index(0, 1), Qt.ItemDataRole.ForegroundRole)
        assert color is not None

    # FontRole and unhandled role
    font = model.data(model.index(0, 0), Qt.ItemDataRole.FontRole)
    assert font is not None and font.bold()
    assert model.data(model.index(0, 0), 9999) is None

    # set_ui_language on populated model and set_sessions with active sort
    model.set_ui_language("cs")
    model.sort_column = 0
    model.set_sessions([{"identifier": "sort1", "name": "Sort1", "status": 6}])
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


def test_unchanged_snapshot_does_not_reset_model_and_preserves_index(qapp):
    from PySide6.QtTest import QSignalSpy

    model = SessionTableModel(["NAME", "STATUS"], "sync")
    sessions = [
        {"identifier": "stable-a", "name": "Alpha", "status": 6},
        {"identifier": "stable-b", "name": "Beta", "status": 6},
    ]
    model.set_sessions(sessions)
    reset = QSignalSpy(model.modelReset)
    changed = QSignalSpy(model.dataChanged)
    index = model.index(1, 0)
    model.set_sessions([dict(x) for x in sessions])
    assert reset.count() == 0
    assert changed.count() == 0
    assert index.isValid()
    assert index.data(Qt.ItemDataRole.UserRole) == "stable-b"

    modified = [dict(x) for x in sessions]
    modified[1]["name"] = "Beta (changed)"
    model.set_sessions(modified)
    assert reset.count() == 0
    assert changed.count() == 1
    assert index.data() == "Beta (changed)"


def test_changed_row_order_uses_safe_structural_reset(qapp):
    from PySide6.QtTest import QSignalSpy

    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions(
        [
            {"identifier": "a", "name": "A"},
            {"identifier": "b", "name": "B"},
        ]
    )
    reset = QSignalSpy(model.modelReset)
    model.set_sessions(
        [
            {"identifier": "b", "name": "B"},
            {"identifier": "a", "name": "A"},
        ]
    )
    assert reset.count() == 1
    assert model.row_for_identifier("a") == 1


def test_sorted_stable_snapshot_keeps_selection_and_no_reset(qapp):
    from PySide6.QtTest import QSignalSpy

    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions(
        [
            {"identifier": "b", "name": "Beta"},
            {"identifier": "a", "name": "Alpha"},
        ]
    )
    model.sort(0)
    reset = QSignalSpy(model.modelReset)
    model.set_sessions(
        [
            {"identifier": "b", "name": "Beta"},
            {"identifier": "a", "name": "Alpha"},
        ]
    )
    assert reset.count() == 0
    assert model.row_for_identifier("a") == 0


def test_sort_preserves_persistent_indexes_in_nonfirst_columns(qapp) -> None:
    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions(
        [
            {"identifier": "b", "name": "Beta", "status": 6},
            {"identifier": "a", "name": "Alpha", "status": 6},
        ]
    )
    persistent_status = QPersistentModelIndex(model.index(0, 1))
    persistent_name = QPersistentModelIndex(model.index(0, 0))
    model.sort(0)
    assert persistent_status.isValid()
    assert persistent_status.row() == 1
    assert persistent_status.column() == 1
    assert persistent_name.row() == 1
    assert persistent_name.data() == "Beta"


def test_sort_preserves_persistent_index_for_duplicate_ids(qapp) -> None:
    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions(
        [
            {"identifier": "dup", "name": "Zed", "status": 6},
            {"identifier": "dup", "name": "Alpha", "status": 6},
        ]
    )
    persistent = QPersistentModelIndex(model.index(0, 1))
    model.sort(0)
    assert persistent.isValid()
    assert persistent.row() == 1
    assert persistent.column() == 1
    assert model.index(1, 0).data() == "Zed"


def test_incremental_insert_and_remove_preserve_persistent_selection(qapp):
    from PySide6.QtTest import QSignalSpy

    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions(
        [
            {"identifier": "a", "name": "Alpha"},
            {"identifier": "b", "name": "Beta"},
        ]
    )
    selected_status = QPersistentModelIndex(model.index(1, 1))
    inserted = QSignalSpy(model.rowsInserted)
    removed = QSignalSpy(model.rowsRemoved)
    resets = QSignalSpy(model.modelReset)

    model.set_sessions(
        [
            {"identifier": "a", "name": "Alpha"},
            {"identifier": "new", "name": "New"},
            {"identifier": "b", "name": "Beta"},
        ]
    )
    assert inserted.count() == 1
    assert resets.count() == 0
    assert selected_status.isValid()
    assert selected_status.row() == 2
    assert selected_status.column() == 1
    assert model.row_for_identifier("b") == 2

    model.set_sessions(
        [
            {"identifier": "a", "name": "Alpha"},
            {"identifier": "b", "name": "Beta edited"},
        ]
    )
    assert removed.count() == 1
    assert resets.count() == 0
    assert selected_status.row() == 1
    assert model.index(1, 0).data() == "Beta edited"


def test_duplicate_ids_still_use_safe_reset(qapp):
    from PySide6.QtTest import QSignalSpy

    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions([{"identifier": "a", "name": "Alpha"}])
    resets = QSignalSpy(model.modelReset)
    model.set_sessions(
        [
            {"identifier": "a", "name": "Alpha"},
            {"identifier": "a", "name": "Duplicate"},
        ]
    )
    assert resets.count() == 1


def test_many_insertions_fall_back_to_bounded_reset(qapp):
    from PySide6.QtTest import QSignalSpy

    model = SessionTableModel(["NAME", "STATUS"], "sync")
    model.set_sessions([{"identifier": "stable", "name": "Stable"}])
    resets = QSignalSpy(model.modelReset)
    model.set_sessions(
        [{"identifier": "stable", "name": "Stable"}]
        + [
            {"identifier": f"new-{index}", "name": f"New {index}"}
            for index in range(65)
        ]
    )
    assert resets.count() == 1
    assert model.rowCount() == 66
