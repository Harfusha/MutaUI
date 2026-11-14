"""Read-only Qt view for conflicts present in the latest native snapshots."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mutaui.domain.models import Endpoint, SessionSnapshot
from mutaui.services.conflict_inspector import (
    ConflictChange,
    ConflictRecord,
    conflicts_for_snapshot,
    filter_conflicts,
    safe_local_conflict_path,
)
from mutaui.services.conflict_recommendations import (
    RECOMMENDATIONS_ENABLED,
    ConflictRecommendationPolicy,
    RecommendationPolicyError,
    load_recommendation_policy,
    recommend_conflict_choice,
    save_recommendation_policy,
)
from mutaui.services.diff_integration import (
    DiffIntegrationError,
    copy_local_conflict_for_diff,
    external_diff_arguments,
)
from mutaui.services.remote_inspector import (
    ParamikoRemoteInspector,
    RemoteInspectionArtifact,
    RemoteInspectionRequest,
)
from mutaui.ui.conflict_recommendations_dialog import ConflictRecommendationsDialog
from mutaui.ui.preferences import active_language, translate_text


def _text(value: str) -> str:
    return translate_text(value, active_language())


class _InspectionSignals(QObject):
    completed = Signal(object, object)


class _InspectionTask(QRunnable):
    def __init__(self, request: RemoteInspectionRequest) -> None:
        super().__init__()
        self.request = request
        self.signals = _InspectionSignals()

    def run(self) -> None:
        try:
            result = ParamikoRemoteInspector().inspect(self.request, consent=True)
        except Exception as exc:
            self.signals.completed.emit(None, exc)
        else:
            self.signals.completed.emit(result, None)


def _changes_text(changes: tuple[ConflictChange, ...]) -> str:
    if not changes:
        return "No change details reported"
    return "\n".join(f"{change.kind}: {change.path}" for change in changes)


class ConflictInspectorDialog(QDialog):
    """Displays native conflict metadata and opens only contained local paths."""

    def __init__(
        self,
        snapshots: Sequence[SessionSnapshot],
        parent: QWidget | None = None,
        *,
        audit_path: str | Path | None = None,
        recommendation_path: str | Path | None = None,
        recommendation_policy: ConflictRecommendationPolicy | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conflict Inspector · Read only")
        self.resize(980, 650)
        self._snapshots = {item.identity.identifier: item for item in snapshots}
        self._records = tuple(
            record for snapshot in snapshots for record in conflicts_for_snapshot(snapshot)
        )
        self._visible_records: tuple[ConflictRecord, ...] = ()
        self._audit_path = Path(audit_path) if audit_path is not None else None
        self._recommendation_path = (
            Path(recommendation_path) if recommendation_path is not None else None
        )
        self._recommendation_load_error: str | None = None
        if recommendation_policy is not None:
            self._recommendation_policy = recommendation_policy
        elif self._recommendation_path is not None:
            try:
                self._recommendation_policy = load_recommendation_policy(self._recommendation_path)
            except RecommendationPolicyError as exc:
                self._recommendation_policy = ConflictRecommendationPolicy(())
                self._recommendation_load_error = str(exc)
        else:
            self._recommendation_policy = ConflictRecommendationPolicy(())
        self._remote_artifact: RemoteInspectionArtifact | None = None
        self._remote_artifact_side: str | None = None
        self._remote_artifact_target: tuple[str, str] | None = None
        self._inspection_task: _InspectionTask | None = None
        self._inspection_target: tuple[str, str] | None = None
        self._inspection_side: str | None = None
        self._close_pending = False
        self._diff_process: QProcess | None = None
        self._inspection_pool = QThreadPool(self)
        self._inspection_pool.setMaxThreadCount(2)

        layout = QVBoxLayout(self)
        note = QLabel(
            "Conflicts come from the latest successful sync-list snapshot. "
            "This inspector is read-only. Remote files are fetched only after a separate explicit consent."
        )
        excluded = sum(
            value
            for snapshot in snapshots
            if isinstance((value := snapshot.native_config.get("excludedConflicts")), int)
            and not isinstance(value, bool)
        )
        if excluded:
            note.setText(
                note.text() + f" The native list omitted {excluded} additional conflict(s)."
            )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.recommendation_status = QLabel()
        self.recommendation_status.setWordWrap(True)
        self.manage_recommendations = QPushButton(_text("Manage advice rules…"))
        self.manage_recommendations.setAccessibleName(_text("Manage advice rules"))
        self.manage_recommendations.setEnabled(self._recommendation_path is not None)
        if self._recommendation_path is None:
            self.manage_recommendations.setToolTip(
                _text("An app settings location is required to save advice rules.")
            )
        self.manage_recommendations.clicked.connect(self._manage_recommendations)
        advice_row = QHBoxLayout()
        advice_row.addWidget(self.recommendation_status, 1)
        advice_row.addWidget(self.manage_recommendations)
        layout.addLayout(advice_row)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by session or relative path")
        self.session_filter = QComboBox()
        self.session_filter.addItem("All sessions", "")
        for identifier, snapshot in sorted(self._snapshots.items()):
            if any(record.session_identifier == identifier for record in self._records):
                self.session_filter.addItem(snapshot.identity.name or identifier, identifier)
        filters.addWidget(self.search, 2)
        filters.addWidget(self.session_filter, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Session", "Conflict path", "ALPHA", "BETA"))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 2)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a conflict to inspect its native details.")
        layout.addWidget(self.details, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.open_alpha = QPushButton("Open ALPHA path")
        self.open_beta = QPushButton("Open BETA path")
        self.inspect_alpha = QPushButton("Inspect ALPHA remote copy…")
        self.inspect_beta = QPushButton("Inspect BETA remote copy…")
        self.open_remote_copy = QPushButton("Open inspected copy")
        self.compare_remote_local = QPushButton("Compare with local copy…")
        self.open_remote_copy.setEnabled(False)
        self.compare_remote_local.setEnabled(False)
        self.inspect_alpha.setEnabled(False)
        self.inspect_beta.setEnabled(False)
        if self._audit_path is None:
            self.inspect_alpha.setToolTip(
                "A local audit path is required before remote inspection."
            )
            self.inspect_beta.setToolTip("A local audit path is required before remote inspection.")
        close = QPushButton("Close")
        self.open_alpha.clicked.connect(lambda: self._open_selected("alpha"))
        self.open_beta.clicked.connect(lambda: self._open_selected("beta"))
        self.inspect_alpha.clicked.connect(lambda: self._inspect_selected_remote("alpha"))
        self.inspect_beta.clicked.connect(lambda: self._inspect_selected_remote("beta"))
        self.open_remote_copy.clicked.connect(self._open_remote_copy)
        self.compare_remote_local.clicked.connect(self._compare_remote_with_local)
        close.clicked.connect(self.accept)
        actions.addWidget(self.open_alpha)
        actions.addWidget(self.open_beta)
        actions.addWidget(self.inspect_alpha)
        actions.addWidget(self.inspect_beta)
        actions.addWidget(self.open_remote_copy)
        actions.addWidget(self.compare_remote_local)
        actions.addWidget(close)
        layout.addLayout(actions)
        self._update_recommendation_status()

        self.search.textChanged.connect(self._refresh)
        self.session_filter.currentIndexChanged.connect(self._refresh)
        self.table.itemSelectionChanged.connect(self._show_details)
        self._refresh()

    def _update_recommendation_status(self) -> None:
        if self._recommendation_load_error:
            message = _text("Advice rules could not be loaded; no rules are active.")
        elif self._recommendation_policy.enabled:
            message = _text("Exact-path advice is enabled. All suggestions require manual review.")
        else:
            message = _text("Exact-path advice is disabled.")
        self.recommendation_status.setText(message)

    def _manage_recommendations(self) -> None:
        if self._recommendation_path is None:
            return
        dialog = ConflictRecommendationsDialog(self._recommendation_policy, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            save_recommendation_policy(self._recommendation_path, dialog.policy)
        except RecommendationPolicyError as exc:
            QMessageBox.warning(self, _text("Advice rules not saved"), str(exc))
            return
        self._recommendation_policy = dialog.policy
        self._recommendation_load_error = None
        self._update_recommendation_status()
        self._show_details()

    def _refresh(self, *_args: object) -> None:
        self._visible_records = filter_conflicts(
            self._records,
            query=self.search.text(),
            session_identifier=str(self.session_filter.currentData() or ""),
        )
        self.table.setRowCount(len(self._visible_records))
        for row, record in enumerate(self._visible_records):
            session = self._snapshots[record.session_identifier]
            alpha = ", ".join(item.kind for item in record.alpha_changes) or "Unknown"
            beta = ", ".join(item.kind for item in record.beta_changes) or "Unknown"
            for column, value in enumerate(
                (
                    session.identity.name or record.session_identifier,
                    record.relative_path,
                    alpha,
                    beta,
                )
            ):
                cell = QTableWidgetItem(value)
                self.table.setItem(row, column, cell)
        if self._visible_records:
            self.table.selectRow(0)
        else:
            self.details.clear()
            self.open_alpha.setEnabled(False)
            self.open_beta.setEnabled(False)
            self.inspect_alpha.setEnabled(False)
            self.inspect_beta.setEnabled(False)

    def _selected(self) -> ConflictRecord | None:
        row = self.table.currentRow()
        return self._visible_records[row] if 0 <= row < len(self._visible_records) else None

    def _show_details(self) -> None:
        record = self._selected()
        if record is None:
            return
        session = self._snapshots[record.session_identifier]
        details = (
            f"Session: {record.session_name}\n"
            f"Exact session identifier: {record.session_identifier}\n"
            f"Relative conflict root: {record.relative_path}\n\n"
            f"ALPHA changes:\n{_changes_text(record.alpha_changes)}\n\n"
            f"BETA changes:\n{_changes_text(record.beta_changes)}\n\n"
            f"Native digest: {record.native_digest or 'Not reported'}\n"
            f"Staging metadata: {record.staging_metadata or 'Not reported'}\n"
            f"Snapshot: {session.measured_at.isoformat()}"
        )
        recommendation = recommend_conflict_choice(
            record, self._recommendation_policy, enabled=RECOMMENDATIONS_ENABLED
        )
        if recommendation is not None:
            details += (
                "\n\n"
                + _text("ADVISORY ONLY — manual review required")
                + f"\nRule: {recommendation.rule_id}"
                + f"\nExact session identifier: {recommendation.session_identifier}"
                + f"\nExact conflict path: {recommendation.relative_path}"
                + f"\nPreferred side: {recommendation.preferred_side.upper()}"
                + f"\nReason: {recommendation.explanation}"
            )
        self.details.setPlainText(details)
        self.open_alpha.setEnabled(self._local_path(record, "alpha") is not None)
        self.open_beta.setEnabled(self._local_path(record, "beta") is not None)
        self.inspect_alpha.setEnabled(self._remote_endpoint(record, "alpha") is not None)
        self.inspect_beta.setEnabled(self._remote_endpoint(record, "beta") is not None)
        self._update_compare_enabled(record)

    def _update_compare_enabled(self, record: ConflictRecord | None) -> None:
        if record is None or self._remote_artifact is None or self._remote_artifact_side is None:
            self.compare_remote_local.setEnabled(False)
            return
        target = (record.session_identifier, record.relative_path)
        local_side = "beta" if self._remote_artifact_side == "alpha" else "alpha"
        self.compare_remote_local.setEnabled(
            self._remote_artifact_target == target
            and self._local_path(record, local_side) is not None
        )

    def _remote_endpoint(self, record: ConflictRecord, side: str) -> Endpoint | None:
        snapshot = self._snapshots[record.session_identifier]
        endpoint = snapshot.alpha_or_source if side == "alpha" else snapshot.beta_or_destination
        if (
            snapshot.stale_reason
            or endpoint is None
            or endpoint.kind != "ssh"
            or not endpoint.host
            or not endpoint.user
            or not endpoint.path
            or self._audit_path is None
        ):
            return None
        return endpoint

    def _inspect_selected_remote(self, side: str) -> None:
        record = self._selected()
        endpoint = self._remote_endpoint(record, side) if record is not None else None
        if record is None or endpoint is None or self._audit_path is None:
            return
        hostname = endpoint.host
        username = endpoint.user
        endpoint_root = endpoint.path
        if not hostname or not username or not endpoint_root:
            return
        key_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an SSH private key",
            str(Path.home() / ".ssh"),
            "Private keys (*);;All files (*)",
        )
        if not key_path:
            return
        target = f"{hostname}:{endpoint_root}/{record.relative_path}"
        answer = QMessageBox.question(
            self,
            "Inspect remote conflict copy",
            f"Read this single conflict file over SSH/SFTP?\n\n{target}\n\n"
            "The host key must already be trusted in ~/.ssh/known_hosts. "
            "The copy is limited to 2 MiB and kept in a temporary folder until this window closes. "
            "No remote file is changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        request = RemoteInspectionRequest(
            hostname=hostname,
            username=username,
            endpoint_root=endpoint_root,
            relative_path=record.relative_path,
            known_hosts_path=Path.home() / ".ssh" / "known_hosts",
            private_key_path=Path(key_path),
            port=endpoint.port or 22,
            audit_path=self._audit_path,
        )
        self.inspect_alpha.setEnabled(False)
        self.inspect_beta.setEnabled(False)
        self.details.appendPlainText("\nRemote inspection in progress…")
        task = _InspectionTask(request)
        task.signals.completed.connect(self._inspection_completed)
        self._inspection_task = task
        self._inspection_target = (record.session_identifier, record.relative_path)
        self._inspection_side = side
        self._inspection_pool.start(task)

    def _inspection_completed(self, artifact: object, error: object) -> None:
        self._inspection_task = None
        if self._close_pending:
            if isinstance(artifact, RemoteInspectionArtifact):
                artifact.close()
            self.close()
            return
        record = self._selected()
        if record is not None:
            self.inspect_alpha.setEnabled(self._remote_endpoint(record, "alpha") is not None)
            self.inspect_beta.setEnabled(self._remote_endpoint(record, "beta") is not None)
        if isinstance(error, Exception):
            QMessageBox.warning(self, "Remote inspection", str(error))
            return
        if not isinstance(artifact, RemoteInspectionArtifact):
            return
        record = self._selected()
        current_target = (
            (record.session_identifier, record.relative_path) if record is not None else None
        )
        if current_target != self._inspection_target:
            artifact.close()
            return
        if self._remote_artifact is not None:
            self._remote_artifact.close()
        self._remote_artifact = artifact
        self._remote_artifact_side = self._inspection_side
        self._remote_artifact_target = self._inspection_target
        self.open_remote_copy.setEnabled(True)
        self._update_compare_enabled(record)
        self.details.appendPlainText(
            f"\nRemote copy: {'text' if artifact.is_text else 'binary'} · "
            f"{artifact.size_bytes} bytes\n"
            f"SHA-256: {artifact.sha256}\n"
            f"Host key SHA-256: {artifact.host_key_sha256}\n"
            f"Temporary path: {artifact.local_path}"
        )

    def _open_remote_copy(self) -> None:
        if self._remote_artifact is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._remote_artifact.local_path)))

    def _compare_remote_with_local(self) -> None:
        record = self._selected()
        artifact = self._remote_artifact
        remote_side = self._remote_artifact_side
        if record is None or artifact is None or remote_side is None:
            return
        local_side = "beta" if remote_side == "alpha" else "alpha"
        local_path = self._local_path(record, local_side)
        if local_path is None:
            QMessageBox.information(
                self,
                "External diff unavailable",
                "Comparison currently requires one remote SSH endpoint and one local endpoint.",
            )
            return
        executable, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an external diff tool",
            str(Path.home()),
            "Applications (*);;All files (*)",
        )
        if not executable:
            return
        try:
            local_copy = copy_local_conflict_for_diff(
                str(local_path.parent),
                local_path.name,
                destination_directory=artifact.temporary_root,
                max_bytes=2 * 1024 * 1024,
            )
            left, right = (
                (artifact.local_path, local_copy.path)
                if remote_side == "alpha"
                else (local_copy.path, artifact.local_path)
            )
            arguments = external_diff_arguments(executable, left, right)
        except (DiffIntegrationError, OSError) as exc:
            QMessageBox.warning(self, "External diff", str(exc))
            return
        process = QProcess(self)
        process.setProgram(arguments[0])
        process.setArguments(list(arguments[1:]))
        process.finished.connect(self._diff_finished)
        process.errorOccurred.connect(self._diff_error)
        self._diff_process = process
        process.start()
        if not process.waitForStarted(3000):
            self._diff_process = None
            QMessageBox.warning(self, "External diff", "The selected diff tool did not start.")

    def _diff_finished(self, *_args: object) -> None:
        self._diff_process = None
        if self._close_pending:
            self.close()

    def _diff_error(self, _error: QProcess.ProcessError) -> None:
        if (
            self._diff_process is not None
            and self._diff_process.state() == QProcess.ProcessState.NotRunning
        ):
            self._diff_process = None
            QMessageBox.warning(self, "External diff", "The selected diff tool failed to start.")
            if self._close_pending:
                self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._inspection_task is not None or (
            self._diff_process is not None
            and self._diff_process.state() != QProcess.ProcessState.NotRunning
        ):
            self._close_pending = True
            event.ignore()
            return
        if self._remote_artifact is not None:
            self._remote_artifact.close()
            self._remote_artifact = None
        super().closeEvent(event)

    def _local_path(self, record: ConflictRecord, side: str) -> Path | None:
        snapshot = self._snapshots[record.session_identifier]
        endpoint = snapshot.alpha_or_source if side == "alpha" else snapshot.beta_or_destination
        if endpoint is None or endpoint.kind != "local" or endpoint.path is None:
            return None
        return safe_local_conflict_path(endpoint.path, record.relative_path)

    def _open_selected(self, side: str) -> None:
        record = self._selected()
        path = self._local_path(record, side) if record is not None else None
        if path is None:
            QMessageBox.information(self, "Unavailable", "This local conflict path is unavailable.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
