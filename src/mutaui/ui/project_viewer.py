"""Read-only Mutagen project import and external-change diff viewer."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mutaui.adapters.cli_executor import CommandExecutor
from mutaui.projects.native_project import (
    NativeProjectSnapshot,
    ProjectReference,
    ProjectReferenceStore,
    ProjectStoreError,
    create_native_project_file,
    load_native_project,
    project_diff,
    validate_native_project_text,
)
from mutaui.projects.project_actions import (
    PROJECT_ACTIONS,
    ProjectActionError,
    ProjectActionPlan,
    execute_project_action,
    plan_project_action,
    prepare_action_plan,
    project_target_id,
)
from mutaui.services.action_planner import ACTION_SPECS, ActionPlanner
from mutaui.ui.project_yaml_editor_dialog import ProjectYamlEditorDialog


class NativeProjectCreationDialog(QDialog):
    def __init__(self, audit_path: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.audit_path = Path(audit_path)
        self.setWindowTitle("Create Native Mutagen Project")
        self.resize(760, 600)
        self.created_path: Path | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Create a new mutagen.yml only. Existing files are never replaced. "
                "Hooks and project commands remain inert until a separate project action is consented to."
            )
        )
        path_row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setPlaceholderText("Choose a directory and mutagen.yml filename")
        browse = QPushButton("Choose file…")
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)
        self.yaml = QPlainTextEdit()
        self.yaml.setPlainText("sync:\n  defaults: {}\nforward:\n  defaults: {}\n")
        layout.addWidget(self.yaml, 1)
        self.status = QLabel("Preview required before file creation.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        controls = QHBoxLayout()
        self.preview_button = QPushButton("Preview and validate")
        self.create_button = QPushButton("Create new file")
        self.create_button.setEnabled(False)
        done_button = QPushButton("Cancel")
        controls.addWidget(self.preview_button)
        controls.addWidget(self.create_button)
        controls.addStretch(1)
        controls.addWidget(done_button)
        layout.addLayout(controls)
        browse.clicked.connect(self.choose_path)
        self.preview_button.clicked.connect(self.preview)
        self.create_button.clicked.connect(self.create_file)
        done_button.clicked.connect(self.reject)
        self.yaml.textChanged.connect(self.invalidate_preview)
        self.path.textChanged.connect(self.invalidate_preview)

    def invalidate_preview(self) -> None:
        self.create_button.setEnabled(False)

    def choose_path(self) -> None:
        initial = self.path.text().strip() or str(Path.home() / "mutagen.yml")
        path, _ = QFileDialog.getSaveFileName(
            self, "Create Native Mutagen Project", initial, "Mutagen project (mutagen.yml *.yaml)"
        )
        if path:
            self.path.setText(path)

    def preview(self) -> None:
        path = Path(self.path.text().strip()).expanduser() if self.path.text().strip() else None
        valid, errors = validate_native_project_text(self.yaml.toPlainText())
        if path is None:
            errors = (*errors, "Choose the new project file path.")
        elif path.name.casefold() not in {"mutagen.yml", "mutagen.yaml"}:
            errors = (*errors, "New project file must be named mutagen.yml or mutagen.yaml.")
        elif not path.parent.is_dir():
            errors = (*errors, "Project directory must already exist.")
        elif path.exists():
            errors = (*errors, "File already exists; this flow never overwrites native YAML.")
        self.create_button.setEnabled(valid and not errors)
        self.status.setText(
            "Preview valid. Creation writes a new file only; it does not execute hooks."
            if valid and not errors
            else "Preview blocked:\n" + "\n".join(errors)
        )

    def create_file(self) -> None:
        try:
            snapshot = create_native_project_file(
                self.path.text().strip(), self.yaml.toPlainText(), audit_path=self.audit_path
            )
        except (OSError, ProjectStoreError) as exc:
            self.create_button.setEnabled(False)
            QMessageBox.warning(self, "Create Native Mutagen Project", str(exc))
            return
        self.created_path = snapshot.path
        self.accept()


class NativeProjectActionDialog(QDialog):
    def __init__(
        self,
        snapshot: NativeProjectSnapshot,
        executor: CommandExecutor,
        audit_path: str | Path,
        action_planner: ActionPlanner | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.snapshot = snapshot
        self.executor = executor
        self.audit_path = Path(audit_path)
        self.action_planner = action_planner
        self.setWindowTitle("Preview Native Mutagen Project Action")
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Project actions use Mutagen's native CLI and exact project file. "
                "Mutagen hooks and custom project commands can run arbitrary system-shell commands."
            )
        )
        form = QFormLayout()
        self.action = QComboBox()
        self.action.addItems(PROJECT_ACTIONS)
        self.command = QComboBox()
        self.command.addItems([name for name, _ in snapshot.commands])
        form.addRow("Project action", self.action)
        form.addRow("Named command", self.command)
        layout.addLayout(form)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)
        self.consent = QCheckBox("I authorize this exact action for the shown mutagen.yml.")
        self.shell_consent = QCheckBox(
            "I reviewed the listed shell commands and consent to Mutagen running them."
        )
        layout.addWidget(self.consent)
        layout.addWidget(self.shell_consent)
        buttons = QDialogButtonBox()
        execute_button = buttons.addButton(
            "Execute previewed action", QDialogButtonBox.ButtonRole.AcceptRole
        )
        assert execute_button is not None
        self.execute_button: QPushButton = execute_button
        cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        self.action.currentTextChanged.connect(self.selection_changed)
        self.command.currentTextChanged.connect(self.selection_changed)
        self.execute_button.clicked.connect(self.execute)
        cancel_button.clicked.connect(self.reject)
        self.refresh_preview()

    def selection_changed(self) -> None:
        self.consent.setChecked(False)
        self.shell_consent.setChecked(False)
        self.refresh_preview()

    def current_plan(self) -> ProjectActionPlan:
        action = self.action.currentText()
        command_name = self.command.currentText() if action == "run" else None
        return plan_project_action(self.snapshot, action, command_name or None)

    def refresh_preview(self) -> None:
        try:
            plan = self.current_plan()
        except ProjectActionError as exc:
            self.preview.setPlainText(str(exc))
            self.execute_button.setEnabled(False)
            self.shell_consent.setVisible(False)
            return
        lines = [
            "Exact argv (JSON):",
            json.dumps(plan.argv, ensure_ascii=False, indent=2),
            "",
            "Native file SHA-256:",
            plan.project_sha256,
            "",
            "Project sessions affected:",
        ]
        if not plan.read_only:
            target_id = project_target_id(plan.path)
            spec = ACTION_SPECS[f"project_{plan.action}"]
            lines.extend(
                (
                    "",
                    f"Risk: {spec.risk} · {spec.description}",
                    f"Exact project target: {target_id}",
                )
            )
            if spec.risk == "R3":
                lines.append(f"Typed confirmation required: APPLY {target_id}")
        if self.snapshot.sessions:
            lines.extend(
                f"{session.kind.title()} {session.name}: "
                f"{session.alpha_or_source or 'endpoint missing'} → "
                f"{session.beta_or_destination or 'endpoint missing'}"
                for session in self.snapshot.sessions
            )
        else:
            lines.append("None declared")
        if plan.action == "start":
            lines.extend(("", "Start creates all declared sessions and may transfer files."))
        elif plan.action == "flush":
            lines.extend(("", "Flush triggers synchronization for project sessions."))
        elif plan.action == "reset":
            lines.extend(("", "Reset clears synchronization history for project sessions."))
        elif plan.action == "terminate":
            lines.extend(("", "Terminate ends project sessions and runs declared hooks."))
        if plan.hooks:
            lines.extend(("", "Hooks that Mutagen will execute:"))
            for name, commands in plan.hooks:
                lines.append(name + ":")
                lines.extend("  " + value for value in commands)
        if plan.command_text is not None:
            lines.extend(("", "Custom shell command:", plan.command_text))
        self.preview.setPlainText("\n".join(lines))
        self.consent.setVisible(not plan.read_only)
        self.shell_consent.setVisible(plan.shell_consent_required)
        self.execute_button.setEnabled(True)

    def execute(self) -> None:
        action_plan = None
        plan = None
        try:
            plan = self.current_plan()
            if not plan.read_only and self.action_planner is not None:
                action_plan = prepare_action_plan(plan, self.action_planner)
                typed_confirmation = None
                if action_plan.requires_typed_confirmation:
                    typed_confirmation, accepted = QInputDialog.getText(
                        self,
                        "Second Confirmation",
                        f"Type {action_plan.typed_confirmation} to approve this R3 project action:",
                    )
                    if not accepted:
                        self.action_planner.cancel(action_plan.plan_id)
                        return
                action_plan = self.action_planner.consent(
                    action_plan.plan_id,
                    consent=self.consent.isChecked(),
                    current_preflight_fingerprint=action_plan.preflight_fingerprint,
                    typed_confirmation=typed_confirmation,
                )
            receipt = execute_project_action(
                plan,
                self.executor,
                consent=self.consent.isChecked(),
                shell_consent=self.shell_consent.isChecked(),
                audit_path=self.audit_path,
                action_planner=self.action_planner,
                action_plan=action_plan,
            )
        except Exception as exc:
            if action_plan is not None and self.action_planner is not None:
                with suppress(ValueError):
                    self.action_planner.cancel(action_plan.plan_id)
            QMessageBox.warning(self, "Native Mutagen Project", str(exc))
            return
        result = receipt.action_result.stdout.strip() or "Mutagen completed without output."
        if receipt.postcheck_error:
            result += "\n\nAction ran; verification or audit issue: " + receipt.postcheck_error
        elif receipt.postcheck_result is not None:
            result += "\n\nPost-check:\n" + (
                receipt.postcheck_result.stdout.strip()
                or "Mutagen returned no project status output."
            )
        QMessageBox.information(self, "Native Mutagen Project", result)
        self.accept()


class NativeProjectViewerDialog(QDialog):
    def __init__(
        self,
        path: str | Path,
        reference_store: ProjectReferenceStore | None = None,
        parent: QWidget | None = None,
        *,
        executor: CommandExecutor | None = None,
        audit_path: str | Path | None = None,
        action_planner: ActionPlanner | None = None,
    ) -> None:
        super().__init__(parent)
        self.reference_store = reference_store
        self.executor = executor
        self.action_planner = action_planner
        self.audit_path = Path(audit_path) if audit_path is not None else None
        self.baseline = load_native_project(path)
        self.current = self.baseline
        self._last_seen_hash = self.current.sha256
        self.setWindowTitle("Native Mutagen Project Inspector")
        self.resize(980, 680)
        layout = QVBoxLayout(self)
        warning = QLabel(
            "Inspection never edits YAML or contacts endpoints. Project actions require a separate "
            "preview and consent. Hooks and custom commands may run arbitrary system-shell code."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.heading = QLabel()
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.tabs = QTabWidget()
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.yaml = QPlainTextEdit()
        self.yaml.setReadOnly(True)
        self.diff = QPlainTextEdit()
        self.diff.setReadOnly(True)
        self.tabs.addTab(self.summary, "Project summary")
        self.tabs.addTab(self.yaml, "Native YAML")
        self.tabs.addTab(self.diff, "External change diff")
        layout.addWidget(self.tabs, 1)
        controls = QHBoxLayout()
        self.open_button = QPushButton("Open another mutagen.yml…")
        self.refresh_button = QPushButton("Check for external changes")
        self.baseline_button = QPushButton("Use current as baseline")
        self.reference_button = QPushButton("Add local project reference")
        self.edit_button = QPushButton("Edit project YAML…")
        self.edit_button.setEnabled(audit_path is not None and self.current.valid)
        if audit_path is None:
            self.edit_button.setToolTip(
                "A local audit path is required before editing project YAML."
            )
        self.actions_button = QPushButton("Project actions…")
        self.actions_button.setEnabled(executor is not None and self.audit_path is not None)
        if executor is None:
            self.actions_button.setToolTip(
                "Select a Mutagen CLI in Settings to enable project actions."
            )
        elif self.audit_path is None:
            self.actions_button.setToolTip("A local project action audit path is required.")
        done_button = QPushButton("Done")
        for control in (
            self.open_button,
            self.refresh_button,
            self.baseline_button,
            self.reference_button,
            self.edit_button,
            self.actions_button,
        ):
            controls.addWidget(control)
        controls.addStretch(1)
        controls.addWidget(done_button)
        layout.addLayout(controls)
        self.open_button.clicked.connect(self.open_another)
        self.refresh_button.clicked.connect(self.refresh_project)
        self.baseline_button.clicked.connect(self.accept_current_baseline)
        self.reference_button.clicked.connect(self.add_reference)
        self.edit_button.clicked.connect(self.edit_yaml)
        self.actions_button.clicked.connect(self.open_actions)
        done_button.clicked.connect(self.accept)
        self.reference_button.setEnabled(reference_store is not None and self.current.valid)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._schedule_external_refresh)
        self._watcher.directoryChanged.connect(self._schedule_external_refresh)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        self._refresh_timer.timeout.connect(self._refresh_external_change)
        self._watch_current_project()
        self._render(self.current)

    def _watch_current_project(self) -> None:
        file_path = str(self.current.path)
        directory_path = str(self.current.path.parent)
        desired_files = {file_path} if self.current.path.is_file() else set()
        desired_directories = {directory_path} if self.current.path.parent.is_dir() else set()
        for stale_path in set(self._watcher.files()) - desired_files:
            self._watcher.removePath(stale_path)
        for stale_path in set(self._watcher.directories()) - desired_directories:
            self._watcher.removePath(stale_path)
        if desired_files and file_path not in self._watcher.files():
            self._watcher.addPath(file_path)
        if desired_directories and directory_path not in self._watcher.directories():
            self._watcher.addPath(directory_path)

    def _schedule_external_refresh(self, _path: str = "") -> None:
        self._refresh_timer.start()

    def _refresh_external_change(self) -> None:
        latest = load_native_project(self.current.path)
        self._watch_current_project()
        if latest.sha256 == self._last_seen_hash:
            return
        self.refresh_project()

    def _render(self, snapshot: NativeProjectSnapshot) -> None:
        self.heading.setText(f"{snapshot.path}\nSHA-256: {snapshot.sha256}")
        if not snapshot.valid:
            self.summary.setPlainText("Invalid native project file\n\n" + snapshot.error)
        else:
            rows = [
                f"Project directory: {snapshot.path.parent}",
                f"Sync sessions: {sum(item.kind == 'sync' for item in snapshot.sessions)}",
                f"Forward sessions: {sum(item.kind == 'forward' for item in snapshot.sessions)}",
                f"Sync defaults: {', '.join(snapshot.sync_defaults) or 'None declared'}",
                f"Forward defaults: {', '.join(snapshot.forward_defaults) or 'None declared'}",
                "",
                "Declared sessions:",
            ]
            for session in snapshot.sessions:
                flush = (
                    " · flushOnCreate"
                    if session.flush_on_create is True
                    else " · flushOnCreate disabled"
                    if session.flush_on_create is False
                    else ""
                )
                rows.append(
                    f"  {session.kind.title()}: {session.name}{flush}\n"
                    f"    {session.alpha_or_source or 'endpoint missing'} → "
                    f"{session.beta_or_destination or 'endpoint missing'}"
                )
                if session.effective_settings:
                    rows.extend(
                        f"    Effective {key}: {value}" for key, value in session.effective_settings
                    )
            for label, settings in (
                ("Sync default values", snapshot.sync_default_settings),
                ("Forward default values", snapshot.forward_default_settings),
            ):
                if settings:
                    rows.extend(("", label + ":"))
                    rows.extend(f"  {key}: {value}" for key, value in settings)
            rows.extend(("", "Hooks (shown, never executed):"))
            if snapshot.hooks:
                for name, commands in snapshot.hooks:
                    rows.append(f"  {name}:")
                    rows.extend(f"    {command}" for command in commands)
            else:
                rows.append("  None declared")
            rows.extend(("", "Custom commands (shown, never executed):"))
            rows.extend(f"  {name}: {command}" for name, command in snapshot.commands)
            if not snapshot.commands:
                rows.append("  None declared")
            if snapshot.unknown_root_keys:
                rows.extend(
                    ("", "Other root keys retained in source:", *snapshot.unknown_root_keys)
                )
            if snapshot.warnings:
                rows.extend(("", "Validation notes:", *("• " + item for item in snapshot.warnings)))
            self.summary.setPlainText("\n".join(rows))
        self.yaml.setPlainText(snapshot.raw_text or snapshot.error)

    def open_another(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Native Mutagen Project",
            str(self.current.path.parent),
            "Mutagen project (*.yml *.yaml);;All files (*)",
        )
        if not path:
            return
        loaded = load_native_project(path)
        self.baseline = loaded
        self.current = loaded
        self._last_seen_hash = loaded.sha256
        self.diff.setPlainText("No external changes detected.")
        self.reference_button.setEnabled(self.reference_store is not None and loaded.valid)
        self._last_seen_hash = loaded.sha256
        self._watch_current_project()
        self._render(loaded)
        self.tabs.setCurrentWidget(self.summary)

    def refresh_project(self) -> None:
        latest = load_native_project(self.current.path)
        try:
            change = project_diff(self.baseline, latest)
        except ValueError as exc:
            change = str(exc)
        self.current = latest
        self._last_seen_hash = latest.sha256
        self.diff.setPlainText(change)
        self._render(latest)
        self._watch_current_project()
        self.tabs.setCurrentWidget(self.diff)
        self.reference_button.setEnabled(self.reference_store is not None and latest.valid)

    def accept_current_baseline(self) -> None:
        self.baseline = self.current
        self.diff.setPlainText("Current source accepted as the new in-memory comparison baseline.")
        self.tabs.setCurrentWidget(self.diff)

    def add_reference(self) -> None:
        if self.reference_store is None or not self.current.valid:
            return
        try:
            reference = self.reference_store.add(self.current.path)
        except (ProjectStoreError, OSError) as exc:
            QMessageBox.warning(self, "Native Mutagen Project", str(exc))
            return
        QMessageBox.information(
            self,
            "Native Mutagen Project",
            f"Added local reference: {reference.name}\n\nThe native project file remains unchanged.",
        )

    def edit_yaml(self) -> None:
        if self.audit_path is None or not self.current.valid:
            return
        dialog = ProjectYamlEditorDialog(self.current, self.audit_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.receipt is None:
            return
        latest = load_native_project(self.current.path)
        self.baseline = latest
        self.current = latest
        self._last_seen_hash = latest.sha256
        self.diff.setPlainText(
            "Project YAML saved with a backup. Review and run project actions separately."
        )
        self._watch_current_project()
        self._render(latest)
        self.tabs.setCurrentWidget(self.diff)

    def open_actions(self) -> None:
        if self.executor is None or not self.current.valid:
            return
        self.refresh_project()
        if not self.current.valid:
            return
        if self.audit_path is None:
            return
        dialog = NativeProjectActionDialog(
            self.current,
            self.executor,
            self.audit_path,
            self.action_planner,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_project()


class NativeProjectManagerDialog(QDialog):
    def __init__(
        self,
        reference_path: str | Path,
        parent: QWidget | None = None,
        *,
        executor: CommandExecutor | None = None,
        audit_path: str | Path | None = None,
        action_planner: ActionPlanner | None = None,
    ) -> None:
        super().__init__(parent)
        self.reference_store = ProjectReferenceStore(reference_path)
        self.executor = executor
        self.action_planner = action_planner
        self.audit_path = (
            Path(audit_path)
            if audit_path is not None
            else Path(reference_path).with_name("mutagen-project-actions.jsonl")
        )
        self.setWindowTitle("Native Mutagen Projects")
        self.resize(850, 480)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Projects stay in native mutagen.yml files. This list stores local file references; "
                "project actions open a separate preview and consent step."
            )
        )
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Project", "Native file", "Reference ID"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout()
        import_button = QPushButton("Import native project…")
        controls.addWidget(import_button)
        create_button = QPushButton("Create project file…")
        controls.addWidget(create_button)
        self.open_button = QPushButton("Inspect selected…")
        self.remove_button = QPushButton("Remove local reference")
        done_button = QPushButton("Done")
        controls.addWidget(self.open_button)
        controls.addWidget(self.remove_button)
        controls.addStretch(1)
        controls.addWidget(done_button)
        layout.addLayout(controls)
        import_button.clicked.connect(self.import_project)
        create_button.clicked.connect(self.create_project)
        self.open_button.clicked.connect(self.open_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        done_button.clicked.connect(self.accept)
        self.refresh()

    def refresh(self) -> None:
        selected = self.selected_reference()
        self.table.setRowCount(len(self.reference_store.references))
        selected_row = -1
        for row, reference in enumerate(self.reference_store.references):
            self.table.setItem(row, 0, QTableWidgetItem(reference.name))
            self.table.setItem(row, 1, QTableWidgetItem(reference.path))
            item = QTableWidgetItem(reference.id)
            item.setData(Qt.ItemDataRole.UserRole, reference.id)
            self.table.setItem(row, 2, item)
            if selected is not None and selected.id == reference.id:
                selected_row = row
        if selected_row >= 0:
            self.table.selectRow(selected_row)

    def selected_reference(self) -> ProjectReference | None:
        row = self.table.currentRow()
        item = self.table.item(row, 2) if row >= 0 else None
        identifier = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return next(
            (
                reference
                for reference in self.reference_store.references
                if reference.id == identifier
            ),
            None,
        )

    def import_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Native Mutagen Project",
            str(Path.home()),
            "Mutagen project (*.yml *.yaml);;All files (*)",
        )
        if not path:
            return
        snapshot = load_native_project(path)
        if not snapshot.valid:
            QMessageBox.warning(self, "Native Mutagen Project", snapshot.error)
            return
        viewer = NativeProjectViewerDialog(
            path,
            self.reference_store,
            self,
            executor=self.executor,
            audit_path=self.audit_path,
            action_planner=self.action_planner,
        )
        viewer.exec()
        self.refresh()

    def create_project(self) -> None:
        dialog = NativeProjectCreationDialog(self.audit_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.created_path is None:
            return
        viewer = NativeProjectViewerDialog(
            dialog.created_path,
            self.reference_store,
            self,
            executor=self.executor,
            audit_path=self.audit_path,
            action_planner=self.action_planner,
        )
        viewer.exec()
        self.refresh()

    def open_selected(self) -> None:
        reference = self.selected_reference()
        if reference is None:
            return
        dialog = NativeProjectViewerDialog(
            reference.path,
            self.reference_store,
            self,
            executor=self.executor,
            audit_path=self.audit_path,
            action_planner=self.action_planner,
        )
        dialog.exec()
        self.refresh()

    def remove_selected(self) -> None:
        reference = self.selected_reference()
        if reference is None:
            return
        answer = QMessageBox.question(
            self,
            "Remove Project Reference",
            f"Remove the local reference to {reference.name}? The native project file will remain untouched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.reference_store.remove(reference.id)
            self.refresh()
        except (ProjectStoreError, OSError) as exc:
            QMessageBox.warning(self, "Native Mutagen Projects", str(exc))


__all__ = ["NativeProjectManagerDialog", "NativeProjectViewerDialog"]
