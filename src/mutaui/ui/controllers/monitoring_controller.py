"""System monitoring and metrics mixin for MainWindow."""

from __future__ import annotations

import math
import sqlite3
import time
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSystemTrayIcon,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from monitoring import (
    Sample,
    query_metrics_from_file,
    statistics_from_file,
)
from mutagen_client import human_bytes
from mutaui.services.health_tracker import (
    HealthPolicy,
    health_policy_from_settings,
)
from mutaui.services.quiet_hours import quiet_hours_active
from mutaui.ui.formatters import field_format
from mutaui.ui.health_network_monitor import (
    attach_health_network_monitor as attach_health_network_monitor_ui,
)
from mutaui.ui.health_network_monitor import (
    health_network_changed as apply_health_network_change,
)
from mutaui.ui.localization import set_localized_text, set_localized_tooltip
from mutaui.ui.preferences import active_language, translate_text
from mutaui.ui.theme_constants import BG, BLUE, RED, TEAL
from mutaui.ui.widgets.basic import button, card, label, localized_label
from mutaui.ui.widgets.graph import Graph


class MonitoringMixin:
    def refresh_resources(self: Any) -> None:
        if self.demo:
            self.apply_resource_metrics(
                {
                    "cpu": 4.8,
                    "memory": 126_877_696,
                    "processes": 2,
                    "read_rate": 80_000,
                    "write_rate": 160_000,
                    "gui_cpu": 0.4,
                    "gui_memory": 124_000_000,
                }
            )
            return
        if self._resource_pending:
            return
        self._resource_pending = True
        self.submit(
            self.sampler.sample_detailed,
            self.apply_resource_metrics,
            on_error=lambda message: self.footer.setToolTip(
                translate_text("Process monitoring: {message}", active_language()).format(
                    message=message
                )
            ),
            on_done=lambda: setattr(self, "_resource_pending", False),
        )

    def apply_resource_metrics(self: Any, data: dict[str, Any]) -> None:
        # Runs in the GUI thread; psutil enumeration itself happens in QThreadPool.
        self.last_metrics = data
        cpu, ram, count = data["cpu"], data["memory"], data["processes"]
        if hasattr(self, "alert_runtime_label"):
            self.alert_runtime_label.setText(
                f"CPU: {cpu:.1f} %  ·  RAM: {human_bytes(ram)}  ·  Procesy: {count}"
            )
        if not self.demo:
            for alert in self.alert_engine.evaluate(
                cpu,
                ram,
                enabled_cpu=bool(self.conf.get("cpu_alert_on", False)),
                enabled_ram=bool(self.conf.get("ram_alert_on", False)),
                cpu_limit=float(self.conf.get("cpu_alert_limit", 90)),
                ram_limit_mb=float(self.conf.get("ram_alert_limit", 1024)),
                hold_seconds=float(self.conf.get("alert_hold", 20)),
            ):
                self.add_log("WARNING: " + alert.message)
                if (
                    self.conf.get("alerts", True)
                    and self.tray.isVisible()
                    and not quiet_hours_active(
                        datetime.now(),
                        enabled=bool(self.conf.get("quiet_hours_enabled", False)),
                        start=str(self.conf.get("quiet_hours_start", "22:00")),
                        end=str(self.conf.get("quiet_hours_end", "07:00")),
                    )
                ):
                    self._last_notification_session_keys = ()
                    self.tray.showMessage(
                        translate_text("Mutagen Control — Limit", active_language()),
                        translate_text(alert.message, active_language()),
                        QSystemTrayIcon.MessageIcon.Warning,
                        7000,
                    )
        if self.recorder is not None:
            if self.recorder.last_error:
                set_localized_text(self.writer_status, "History: write error")
                self.writer_status.setToolTip(self.recorder.last_error)
            elif self.recorder.dropped:
                self.writer_status.setText(
                    translate_text(
                        "Number of skipped history samples: {count}", active_language()
                    ).format(count=self.recorder.dropped)
                )
            else:
                set_localized_text(self.writer_status, "History: saving continuously")
        else:
            set_localized_text(self.writer_status, "History: demo mode")
        if hasattr(self, "gui_usage_label"):
            language = self.ui_language
            self.gui_usage_label.setText(
                f"{translate_text('Application load', language)}: CPU "
                f"{data.get('gui_cpu', 0):.1f} %  ·  "
                f"RAM {human_bytes(data.get('gui_memory', 0))}  ·  "
                f"{translate_text('measured for the UI process, not Mutagen', language)}"
            )
        self.snapshot.cpu, self.snapshot.memory, self.snapshot.processes = cpu, ram, count
        self.snapshot.resource_observed_at = datetime.now().astimezone()
        # State changes only on CLI polls, not on each CPU sample.
        active, problems = self.session_counts
        forward_rates = (
            self.traffic_rates if self.demo or self._traffic_sample_pending else (None, None)
        )
        self._traffic_sample_pending = False
        cli_launch_count = self.client.cli_launch_count
        sample = Sample(
            ts=time.time(),
            cpu=cpu,
            memory=ram,
            read_rate=data["read_rate"],
            write_rate=data["write_rate"],
            forward_out_rate=forward_rates[0],
            forward_in_rate=forward_rates[1],
            processes=count,
            active_sessions=active,
            problem_sessions=problems,
            tray_idle_seconds=self.tray_idle_seconds(),
            cli_launches=max(0, cli_launch_count - self._last_recorded_cli_launch_count),
        )
        recorded = False
        if self.recorder is not None:
            recorded = self.recorder.add(sample)
            if not recorded:
                set_localized_tooltip(self.footer, "History writer is no longer available")
            elif self.recorder.last_error:
                self.footer.setToolTip("History: " + self.recorder.last_error)
        else:
            try:
                self.history.add(sample)
                recorded = True
            except sqlite3.Error as exc:
                self.footer.setToolTip(str(exc))
        if recorded:
            self._last_recorded_cli_launch_count = cli_launch_count
            self.commit_tray_idle_sample()
        self.cpu_value.setText(f"{cpu:.1f} %")
        self.mem_value.setText(human_bytes(ram))
        if hasattr(self, "monitor_labels"):
            self.monitor_labels["cpu"].setText(f"{cpu:.1f} %")
            self.monitor_labels["memory"].setText(human_bytes(ram))
            self.monitor_labels["disk"].setText(
                f"↓ {human_bytes(data['read_rate'])}/s · ↑ {human_bytes(data['write_rate'])}/s"
            )
            self.monitor_labels["traffic"].setText(
                f"{translate_text('outbound', self.ui_language)} "
                f"{human_bytes(self.traffic_rates[0])}/s · "
                f"{translate_text('inbound', self.ui_language)} "
                f"{human_bytes(self.traffic_rates[1])}/s"
            )
            self.monitor_labels["sessions"].setText(
                f"{active} {translate_text('active', self.ui_language)} · "
                f"{problems} {translate_text('issues', self.ui_language)}"
            )
        if hasattr(self, "process_table") and self.pages.currentIndex() == 6:
            detail = (
                [
                    {
                        "pid": 1840,
                        "name": "mutagen.exe",
                        "cpu": 3.7,
                        "memory": 100_000_000,
                        "read_rate": 50_000,
                        "write_rate": 100_000,
                    },
                    {
                        "pid": 2480,
                        "name": "mutagen-agent.exe",
                        "cpu": 1.1,
                        "memory": 26_877_696,
                        "read_rate": 30_000,
                        "write_rate": 60_000,
                    },
                ]
                if self.demo
                else self.sampler.last_processes
            )
            self.fill_processes(detail)
        self.refresh_charts()

    def fill_processes(self: Any, processes: list[dict[str, Any]]) -> None:
        table = self.process_table
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(processes))
            for idx, proc in enumerate(processes):
                cells = [
                    str(proc["pid"]),
                    proc["name"],
                    f"{proc['cpu']:.1f} %",
                    human_bytes(proc["memory"]),
                    human_bytes(proc["read_rate"]) + "/s",
                    human_bytes(proc["write_rate"]) + "/s",
                ]
                for col, cell in enumerate(cells):
                    item = table.item(idx, col)
                    if item is None:
                        item = QTableWidgetItem(str(cell))
                        table.setItem(idx, col, item)
                        if col in (0, 2, 3, 4, 5):
                            item.setTextAlignment(
                                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                            )
                    elif item.text() != str(cell):
                        item.setText(str(cell))
                    if col == 0 and item.data(Qt.ItemDataRole.UserRole) != proc["pid"]:
                        item.setData(Qt.ItemDataRole.UserRole, proc["pid"])
            table.setSortingEnabled(True)
        finally:
            table.setUpdatesEnabled(True)
        self.fit_table_to_rows(table)

    def refresh_charts(self: Any, *_args: object, force: bool = False) -> None:
        if self.chart_frozen and not force:
            return
        page_index = self.pages.currentIndex()
        if page_index not in (0, 6):
            return  # No SQLite reads or paints for invisible chart pages.
        if not self.isVisible() and not force:
            return
        gate = self._chart_dashboard_gate if page_index == 0 else self._chart_monitor_gate
        if not gate.ready(force):
            return
        try:
            if page_index == 0:
                recent = self.history.query(hours=5 / 60, max_points=320)
                self.cpu_chart.set_data((r["ts"], r["cpu"], None) for r in recent)
                self.mem_chart.set_data((r["ts"], r["memory"], None) for r in recent)
                return
            if not hasattr(self, "monitor_graphs"):
                return
            hours = float(self.monitor_range.currentData())
            if self.demo or self.history.path == ":memory:":
                self.apply_monitor_chart_data(self.history.query(hours=hours), hours)
            elif not self._chart_query_pending:
                self._chart_query_pending = True
                self._chart_query_reschedule = False
                path = self.history.path

                def finished_query() -> None:
                    self._chart_query_pending = False
                    if self._chart_query_reschedule and self.pages.currentIndex() == 6:
                        self._chart_monitor_gate.reset()
                        self.refresh_charts(force=True)

                self.submit(
                    lambda: query_metrics_from_file(path, hours=hours),
                    lambda rows: self.apply_monitor_chart_data(rows, hours),
                    lambda error: self.stats_label.setToolTip("Graph history: " + str(error)[:150]),
                    on_done=finished_query,
                )
            else:
                self._chart_query_reschedule = True
            # Raw P95 / max over a 48h window can require 80k+ records.
            # Read and sort it in a worker using a separate read-only SQLite
            # connection, so zooming the GUI never blocks on statistics.
            if self._stats_cache_range == hours and time.monotonic() - self._stats_cache_at < 20:
                return
            if self._stats_pending:
                return
            if self.demo or self.history.path == ":memory:":
                self.apply_statistics(self.history.statistics(hours=hours), hours)
            else:
                self._stats_pending = True
                set_localized_text(self.stats_label, "Loading statistics for the selected period…")
                path = self.history.path
                self.submit(
                    lambda: statistics_from_file(path, hours=hours),
                    lambda data: self.apply_statistics(data, hours),
                    lambda error: self.stats_label.setText(
                        "Could not load statistics: " + str(error)[:140]
                    ),
                    on_done=lambda: setattr(self, "_stats_pending", False),
                )
        except sqlite3.Error:
            pass

    def apply_monitor_chart_data(self: Any, rows: list[dict[str, Any]], hours: float) -> None:
        if self.pages.currentIndex() != 6 or float(self.monitor_range.currentData()) != hours:
            return  # Ignore asynchronous results for a previously selected range.
        mapping = {
            "cpu": ("cpu", None),
            "memory": ("memory", None),
            "disk": ("read_rate", "write_rate"),
            "traffic": ("forward_out_rate", "forward_in_rate"),
            "sessions": ("active_sessions", "problem_sessions"),
        }
        for name, (left, right) in mapping.items():
            self.monitor_graphs[name].set_data(
                (row["ts"], row[left], row[right] if right else None) for row in rows
            )

    def apply_statistics(self: Any, stats: dict[str, Any], hours: float) -> None:
        if self.pages.currentIndex() != 6 or float(self.monitor_range.currentData()) != hours:
            return  # Ignore an outdated result from another selected interval.
        self._stats_cache_at = time.monotonic()
        self._stats_cache_range = hours
        self._last_monitor_stats = stats

        def fmt(field: str, unit: str) -> str:
            values = stats["fields"][field]
            localized_unit = translate_text(unit, self.ui_language)
            return (
                f"{localized_unit}: {translate_text('current', self.ui_language)} "
                f"{field_format(field, values['latest'])}  ·  "
                f"{translate_text('average', self.ui_language)} "
                f"{field_format(field, values['avg'])}  ·  "
                f"P95 {field_format(field, values['p95'])}  ·  "
                f"{translate_text('maximum', self.ui_language)} "
                f"{field_format(field, values['max'])}"
            )

        self.stats_label.setText(
            translate_text(
                "Measured {samples} samples; missing periods are not interpolated.",
                self.ui_language,
            ).format(samples=stats["samples"])
            + "\n"
            + fmt("cpu", "CPU")
            + "\n"
            + fmt("memory", "RAM")
            + "\n"
            + fmt("read_rate", "Disk Read")
            + "\n"
            + fmt("write_rate", "Disk Write")
            + "\n"
            + fmt("forward_out_rate", "Forward out")
            + "\n"
            + fmt("forward_in_rate", "Forward Inbound")
        )

    def monitoring_page(self: Any) -> QScrollArea:
        page = QScrollArea()
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("scrollbody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 3, 3, 18)
        layout.setSpacing(18)
        control, cl = card()
        heading = QHBoxLayout()
        heading.addWidget(label("Resource and Traffic Trends", size=17, bold=True))
        heading.addStretch()
        heading.addWidget(label("Show:", muted=True))
        self.monitor_range = QComboBox()
        for title, hours in [
            ("5 minutes", 5 / 60),
            ("30 minutes", 0.5),
            ("2 hours", 2),
            ("12 hours", 12),
            ("24 hours", 24),
            ("48 hours", 48),
        ]:
            self.monitor_range.addItem(title, hours)
        self.monitor_range.setCurrentIndex(1)
        self.monitor_range.currentIndexChanged.connect(
            lambda _=None: self.refresh_charts(force=True)
        )
        heading.addWidget(self.monitor_range)
        self.monitor_live_button = button("⏸ Freeze Graphs", self.toggle_charts)
        set_localized_tooltip(
            self.monitor_live_button, "Stops automatic graph updates for easier viewing"
        )
        heading.addWidget(self.monitor_live_button)
        png_btn = button("Save PNG", self.export_monitor_png)
        set_localized_tooltip(png_btn, "Saves the currently displayed graphs as a PNG image")
        heading.addWidget(png_btn)
        csv_btn = button("Export CSV", self.export_metrics, kind="primary")
        set_localized_tooltip(
            csv_btn, "Exports measured data to a CSV file for analysis in another tool"
        )
        heading.addWidget(csv_btn)
        cl.addLayout(heading)
        cl.addWidget(
            label(
                "Data are stored locally for 48 hours. Graphs show actual measurements; "
                "history has a gap while the application is closed.",
                muted=True,
                size=11,
            )
        )
        self.gui_usage_label = label(
            "Application load: waiting for measurements", muted=True, size=11
        )
        cl.addWidget(self.gui_usage_label)
        layout.addWidget(control)
        stats_panel, stats_layout = card()
        stats_layout.addWidget(
            label("Selected Period Summary · Actual Measurements", size=15, bold=True)
        )
        self.stats_label = localized_label("Waiting for data…")
        self.stats_label.setTextFormat(Qt.TextFormat.PlainText)
        self.stats_label.setWordWrap(True)
        self.stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_panel)
        self.monitor_graphs = {}
        self.monitor_labels = {}
        chart_specs = [
            ("cpu", "CPU", "Local Mutagen process usage (may exceed 100%)", BLUE, None, "percent"),
            ("memory", "RAM", "Resident memory of local processes", TEAL, None, "memory"),
            (
                "disk",
                "Process Disk I/O",
                "Read (blue) · write (green); values depend on the operating system",
                BLUE,
                TEAL,
                "bytes_s",
            ),
            (
                "traffic",
                "Forwarded Data",
                "Outbound (blue) · inbound (green); based on cumulative forward-session counters",
                BLUE,
                TEAL,
                "bytes_s",
            ),
            ("sessions", "Session Status", "Active (green) · issues (red)", TEAL, RED, "number"),
        ]
        for index in range(0, len(chart_specs), 2):
            line = QHBoxLayout()
            line.setSpacing(14)
            for key, title, subtitle, color, secondary, unit in chart_specs[index : index + 2]:
                panel, content = card()
                top = QHBoxLayout()
                top.addWidget(label(title, size=15, bold=True))
                top.addStretch()
                val = label("—", muted=True, size=12)
                self.monitor_labels[key] = val
                top.addWidget(val)
                content.addLayout(top)
                content.addWidget(label(subtitle, muted=True, size=10))
                graph = Graph(color, panel, unit=unit, secondary=secondary)
                graph.setMinimumHeight(205)
                content.addWidget(graph)
                self.monitor_graphs[key] = graph
                line.addWidget(panel, 1)
            if len(chart_specs[index : index + 2]) == 1:
                line.addStretch(1)
            layout.addLayout(line)
        process_card, process_l = card()
        process_l.addWidget(label("Individual Local Mutagen Processes", size=16, bold=True))
        process_l.addWidget(
            label("Usage is measured per process, not per sync session.", muted=True)
        )
        self.process_table = self.make_table(
            ["PID", "PROCESS", "CPU", "RAM", "READ", "WRITE"], height=180, stretch_columns=(1,)
        )
        self.process_table.setMinimumHeight(0)
        self.process_table.setMaximumHeight(16777215)
        process_l.addWidget(self.process_table)
        layout.addWidget(process_card)
        layout.addStretch()
        page.setWidget(body)
        return page

    def toggle_charts(self: Any) -> None:
        self.chart_frozen = not self.chart_frozen
        self.monitor_live_button.setText(
            "▶ Resume Graph Updates" if self.chart_frozen else "⏸ Freeze Graphs"
        )
        if not self.chart_frozen:
            self.refresh_charts(force=True)

    def export_monitor_png(self: Any) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Save Current Graphs to PNG", active_language()),
            "mutagen-monitoring.png",
            translate_text("PNG (*.png)", active_language()),
        )
        if not path:
            return
        # Export exactly what is visible on the monitoring page: all five graphs.
        # Render full scroll-area contents, including off-screen cards.
        # The QScrollArea owns the real visual body via its widget().
        scroll = self.pages.widget(6)
        body = scroll.widget()
        image = QPixmap(body.size())
        image.fill(QColor(BG))
        body.render(image)
        if not image.save(path, "PNG"):
            self.report_error("Could not save PNG image.")
        else:
            self.add_log("Monitoring saved as PNG")

    def export_metrics(self: Any) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Export monitoringu", active_language()),
            "mutagen-metrics.csv",
            translate_text("CSV (*.csv)", active_language()),
        )
        if not path:
            return
        try:
            self.history.export_csv(path, hours=float(self.monitor_range.currentData()))
            self.add_log("Monitoring history exported to CSV")
        except (sqlite3.Error, OSError) as exc:
            self.report_error(str(exc))

    def seed_demo_history(self: Any) -> None:
        """Populate illustrative graphs offline (only in explicitly marked demo mode)."""
        now = time.time()
        for i in range(125):
            phase = i / 5.0
            spike = 33 if i % 43 in range(12, 17) else 0
            cpu = max(0.0, 6 + 5 * math.sin(phase) + spike)
            memory = int((112 + i * 0.22 + 7 * math.sin(phase / 2)) * 1024**2)
            sample = Sample(
                ts=now - (124 - i) * 14,
                cpu=cpu,
                memory=memory,
                read_rate=32000 + 60000 * abs(math.sin(phase)),
                write_rate=54000 + 85000 * abs(math.cos(phase / 1.3)),
                forward_out_rate=18000 + 65000 * abs(math.cos(phase / 1.8)),
                forward_in_rate=65000 + 100000 * abs(math.sin(phase / 2)),
                processes=2,
                active_sessions=2,
                problem_sessions=0,
            )
            self.history.add(sample)

    def health_policy_from_settings(self: Any) -> HealthPolicy:
        return health_policy_from_settings(self.conf)

    def _attach_health_network_monitor(self: Any) -> None:
        attach_health_network_monitor_ui(self)

    def _health_network_changed(self: Any, reachability: object) -> None:
        apply_health_network_change(self, reachability)
