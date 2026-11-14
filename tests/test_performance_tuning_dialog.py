from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QTableWidget, QTableWidgetItem

import mutaui.ui.performance_tuning as performance_ui
from mutaui.ui.performance_tuning import (
    PerformanceTuningDialog,
    apply_performance_assistant,
    fill_local_proposal_table,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_performance_assistant_returns_optional_local_suggestions(qapp, tmp_path):
    dialog = PerformanceTuningDialog(
        {
            "watch": {"mode": "force-poll", "pollingInterval": 5},
            "scanMode": "full",
            "alpha": {"protocol": 0, "path": str(tmp_path)},
        }
    )

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.recommendations == {
        "watch.mode": "portable",
        "scanMode": "accelerated",
    }
    text = dialog.report.toPlainText()
    assert "no performance measurement was run" in text
    assert "Entry count is not reported" in text
    assert "replacement recreates the session" in text

    dialog.apply_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_stale_session_disables_suggestions_and_explains_refresh(qapp, tmp_path):
    dialog = PerformanceTuningDialog(
        {
            "watch": {"mode": "force-poll", "pollingInterval": 5},
            "scanMode": "full",
            "alpha": {"protocol": 0, "path": str(tmp_path)},
        },
        stale=True,
    )
    assert dialog.recommendations == {}
    assert not dialog.apply_button.isEnabled()
    assert "snapshot is stale" in dialog.report.toPlainText()


def test_assistant_uses_czech_copy_and_links_official_docs(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(performance_ui, "active_language", lambda: "cs")
    dialog = PerformanceTuningDialog({"watch": {"mode": "no-watch"}})
    assert dialog.windowTitle() == "Asistent ladění výkonu"
    assert "Počet položek relace" in dialog.report.toPlainText()
    links = [label.text() for label in dialog.findChildren(QLabel) if "mutagen.io" in label.text()]
    assert links and "mutagen.io/documentation/synchronization/watching" in links[0]


def test_accepted_suggestions_only_fill_existing_proposal_cells(qapp):
    table = QTableWidget(1, 6)
    table.setItem(0, 5, QTableWidgetItem(""))
    rows = (SimpleNamespace(key="scanMode"),)

    fill_local_proposal_table(
        table,
        rows,
        {"scanMode": "accelerated", "unknown.field": "ignored"},
    )

    assert table.item(0, 5).text() == '"accelerated"'


def test_assistant_flow_copies_only_after_explicit_acceptance(qapp, tmp_path, monkeypatch):
    table = QTableWidget(2, 6)
    table.setItem(0, 5, QTableWidgetItem(""))
    table.setItem(1, 5, QTableWidgetItem(""))
    rows = (SimpleNamespace(key="watch.mode"), SimpleNamespace(key="scanMode"))

    def accept(dialog):
        dialog.apply_button.click()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(PerformanceTuningDialog, "exec", accept)
    accepted = apply_performance_assistant(
        {
            "watch": {"mode": "force-poll", "pollingInterval": 5},
            "scanMode": "full",
        },
        table,
        rows,
    )

    assert accepted is True
    assert table.item(0, 5).text() == '"portable"'
    assert table.item(1, 5).text() == '"accelerated"'


def test_assistant_cancel_leaves_local_proposal_untouched(qapp, tmp_path, monkeypatch):
    table = QTableWidget(1, 6)
    table.setItem(0, 5, QTableWidgetItem('"existing"'))
    rows = (SimpleNamespace(key="scanMode"),)
    monkeypatch.setattr(
        PerformanceTuningDialog,
        "exec",
        lambda _dialog: QDialog.DialogCode.Rejected,
    )

    accepted = apply_performance_assistant(
        {"scanMode": "full"},
        table,
        rows,
    )

    assert accepted is False
    assert table.item(0, 5).text() == '"existing"'
