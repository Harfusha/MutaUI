import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from mutaui.ui.page_shell import PAGE_ROUTES, LazyStackedWidget


def test_page_routes_have_stable_unique_ids_and_current_order():
    assert len(PAGE_ROUTES) == 11
    assert len({route.route_id for route in PAGE_ROUTES}) == len(PAGE_ROUTES)
    assert [route.title for route in PAGE_ROUTES[:4]] == [
        "Overview",
        "Sync",
        "Forwarding",
        "Action History",
    ]
    assert PAGE_ROUTES[9].route_id == "endpoints"
    assert PAGE_ROUTES[10].route_id == "servers"


def test_lazy_page_is_created_on_first_navigation_and_reused():
    app = QApplication.instance() or QApplication([])
    shell = LazyStackedWidget()
    created = []

    shell.addWidget(QWidget())

    def build_settings():
        page = QWidget()
        created.append(page)
        return page

    shell.add_lazy_page(build_settings)
    assert shell.count() == 2
    assert not shell.is_page_built(1)
    assert created == []

    shell.setCurrentIndex(1)
    app.processEvents()
    assert shell.is_page_built(1)
    assert len(created) == 1

    shell.setCurrentIndex(0)
    shell.setCurrentIndex(1)
    assert len(created) == 1
    assert shell.widget(1) is created[0]

    shell.deleteLater()
    app.processEvents()


def test_lazy_page_factory_failure_is_retryable_and_invalid_index_is_rejected():
    app = QApplication.instance() or QApplication([])
    shell = LazyStackedWidget()
    attempts = []

    def build():
        attempts.append("called")
        if len(attempts) == 1:
            raise RuntimeError("temporary construction failure")
        return QWidget()

    index = shell.add_lazy_page(build)
    with pytest.raises(RuntimeError, match="temporary construction failure"):
        shell.ensure_page(index)
    assert not shell.is_page_built(index)
    page = shell.ensure_page(index)
    assert shell.is_page_built(index)
    assert shell.widget(index) is page
    assert len(attempts) == 2

    with pytest.raises(IndexError, match="No page registered"):
        shell.ensure_page(50)
    shell.setCurrentIndex(-1)
    shell.deleteLater()
    app.processEvents()


def test_lazy_page_retries_when_placeholder_disappears(monkeypatch):
    app = QApplication.instance() or QApplication([])
    shell = LazyStackedWidget()
    attempts = []

    def build():
        attempts.append("called")
        return QWidget()

    index = shell.add_lazy_page(build)
    original_widget = shell.widget
    monkeypatch.setattr(
        shell,
        "widget",
        lambda requested: None if requested == index else original_widget(requested),
    )

    with pytest.raises(IndexError, match="No placeholder registered"):
        shell.ensure_page(index)
    assert not shell.is_page_built(index)
    assert attempts == ["called"]

    monkeypatch.setattr(shell, "widget", original_widget)
    assert isinstance(shell.ensure_page(index), QWidget)
    assert shell.is_page_built(index)
    shell.deleteLater()
    app.processEvents()
