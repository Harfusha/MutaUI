"""Offline Qt smoke test. Build EXE invokes this with Qt's offscreen platform.

It never starts the real daemon or runs destructive CLI commands.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QFrame, QScrollArea

from app import MainWindow, SessionDialog
from sync_profiles import PROFILES


def test_demo_ui_can_render_all_pages_and_charts(tmp_path, monkeypatch):
    import app

    monkeypatch.setattr(app, "settings_path", lambda: tmp_path / "settings.json")
    qapp = QApplication.instance() or QApplication([])
    window = MainWindow(demo=True)
    try:
        # Exercise layout activation and Qt's real parent/ownership semantics.
        window.show()
        qapp.processEvents()
        assert window.pages.count() == 11
        window.apply_snapshot(window.snapshot)
        import gc

        import shiboken6

        gc.collect()
        # Regression for the real Windows crash: Graph's owning QFrame must live.
        assert shiboken6.isValid(window.cpu_chart)
        assert shiboken6.isValid(window.mem_chart)
        assert shiboken6.isValid(window.cpu_chart.parentWidget())
        assert shiboken6.isValid(window.mem_chart.parentWidget())
        # Regression for the second Windows crash: card() returns a widget and
        # a layout. The daemon page must add the widget, not its layout.
        daemon_page = window.pages.widget(4)
        assert len(daemon_page.findChildren(QFrame, "card")) >= 3
        assert shiboken6.isValid(window.register_message)
        assert daemon_page.isAncestorOf(window.register_message)
        assert window.health_ring.total == 4
        assert window.health_ring.healthy == 4
        window.refresh_resources()
        for page in range(window.pages.count()):
            window.set_page(page)
            assert window.pages.currentIndex() == page
        window.set_page(6)
        assert len(window.monitor_graphs) == 5
        assert window.stats_label.text().strip()
        window.toggle_charts()
        assert window.chart_frozen
        window.toggle_charts()
        assert not window.chart_frozen
        window.set_page(1)
        window.sync_table.selectRow(0)
        window.toggle_favorite("sync")
        assert "sync_demo_alpha" in window.favorites["sync"]
        window.set_page(3)
        window.tail_lines.extend(["INFO connected", "ERROR timeout"])
        window.render_tail()
        assert "ERROR timeout" in window.tail_view.toPlainText()
        window.tail_filter.setText("ERROR")
        assert "INFO connected" not in window.tail_view.toPlainText()
        window.set_page(9)
        assert window.endpoint_combo.count() >= 1
        window.endpoint_combo.setCurrentIndex(0)
        window.update_endpoint_details()
        assert "web-project" in window.endpoint_status.text()
        assert "Connected" in window.endpoint_cards["right"]["conn"].text()
        assert "12 486" in window.endpoint_cards["left"]["stats"].text()
        window.set_page(10)
        assert window.server_selector.count() >= 4
        assert window.server_overview.rowCount() >= 3
        assert window.server_sync_table.rowCount() == 3
        assert "3 sync sessions · 1 port forward" in window.server_scope_label.text()
        # The first server can legitimately have only port forwarding sessions.
        for index in range(1, window.server_selector.count()):
            window.server_selector.setCurrentIndex(index)
            assert window.server_sync_table.rowCount() == len(
                window.server_targets("sync", "server")
            )
            assert window.server_forward_table.rowCount() == len(
                window.server_targets("forward", "server")
            )
            assert window.server_sync_empty.isVisible() == (
                window.server_sync_table.rowCount() == 0
            )
        assert any(
            group.forward_ids and not group.sync_ids for group in window._server_groups.values()
        )
        window.set_page(1)
        assert window.sync_server_filter.count() == window.server_selector.count()
        assert "sign-in" in window.sync_autostart_button.text()
        window.set_page(1)
        assert isinstance(window.pages.widget(1), QScrollArea)
        window.set_page(5)
        assert isinstance(window.pages.widget(5), QScrollArea)
        assert window.adaptive_input.isChecked()
        assert window.new_sync_profile_input.count() == len(PROFILES)
        profile_dialog = SessionDialog("sync", window, default_profile="eco_poll")
        assert profile_dialog.profile.currentData() == "eco_poll"
        profile_dialog.a.setText("C:/data")
        profile_dialog.b.setText("user@host:/data")
        assert "--watch-polling-interval=60" in profile_dialog.arguments()
        profile_dialog.close()
        window.set_page(8)
        assert window.metric_period_ms() >= 1000
        window.cpu_alert_on.setChecked(True)
        window.cpu_alert_limit.setValue(50)
        window.save_alert_rules()
        assert app.read_settings()["cpu_alert_limit"] == 50
    finally:
        window.timer.stop()
        window.metric_timer.stop()
        window.tail_timer.stop()
        window._allow_exit = True
        window.close()
        window.history.close()
