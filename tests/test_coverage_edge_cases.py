"""Targeted regression and branch coverage edge-case tests."""

from __future__ import annotations

import errno
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import QApplication

import endpoint_inspector
import mutagen_client
import performance
from mutaui.adapters.yaml_config import load_yaml_file
from mutaui.adapters.yaml_config_editor import (
    InvalidConfigForWrite,
    YAMLReadResult,
    preview_yaml_text,
)
from mutaui.domain.models import (
    ActionAuditEvent,
    ActionPlan,
    ConnectionProfile,
    GlobalConfig,
    ProjectDefinition,
)
from mutaui.services.performance_advisor import _inspect_local_root
from mutaui.ui.conflict_inspector_dialog import _InspectionTask
from mutaui.ui.onboarding import inspect_cli
from mutaui.ui.widgets.graph import Graph
from mutaui.ui.widgets.session_table import SessionTableModel


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_endpoint_inspector_nonnegative_invalid_values():
    assert endpoint_inspector._nonnegative("not_a_number") is None
    assert endpoint_inspector._nonnegative(None) is None
    assert endpoint_inspector._nonnegative(object()) is None


def test_performance_envelope_downsample_recursion_and_empty_chunks():
    pts = [(float(i), 10.0 if i % 2 == 0 else -10.0) for i in range(20)]
    downsampled = performance.envelope_downsample(pts, max_points=8)
    assert len(downsampled) <= 8
    assert downsampled[0] == pts[0]
    assert downsampled[-1] == pts[-1]


def test_domain_models_freezing():
    now = datetime.now(UTC)
    cfg = GlobalConfig(
        raw_yaml="sync:\n",
        parsed_known={"sync": {}},
        unknown_tree={"custom": 1},
        file_hash="abc",
        effective_defaults={"mode": "two-way-safe"},
        read_only=False,
    )
    assert isinstance(cfg.parsed_known, dict) or hasattr(cfg.parsed_known, "get")
    assert cfg.unknown_tree["custom"] == 1

    profile = ConnectionProfile(
        id="p1",
        display_name="Profile 1",
        endpoint_specs=("user@host:/path",),
        default_settings={"max_stalls": 5},
        ssh_profile_ref=None,
        tags=("dev",),
        created=now,
        last_used=None,
        version=1,
    )
    assert profile.default_settings["max_stalls"] == 5

    proj = ProjectDefinition(
        path="/tmp/project",
        source_hash="sha",
        native_project_id="np1",
        parsed_known={"sync": {}},
        unknown_tree={"extra": 2},
        hooks=("hook1",),
        commands=("cmd1",),
    )
    assert proj.hooks == ("hook1",)
    assert proj.commands == ("cmd1",)

    plan = ActionPlan(
        id="plan1",
        kind="restart",
        exact_targets=("session1",),
        before_state={"state": "paused"},
        commands=(("mutagen", "sync", "resume"),),
        preconditions=("daemon_running",),
        risk_tier="low",
        affected_scope="session",
        backup_plan=None,
        rollback_ability=True,
        confirmation_required=False,
    )
    assert plan.before_state["state"] == "paused"

    audit = ActionAuditEvent(
        id="a1",
        plan_id="plan1",
        requested_at=now,
        completed_at=now,
        requested_by="user",
        result="success",
        error=None,
        redacted_details={"detail": "ok"},
    )
    assert audit.redacted_details["detail"] == "ok"


def test_preview_yaml_text_encoding_error(tmp_path):
    config_file = tmp_path / "mutagen.yml"
    config_file.write_text("sync:\n", encoding="ascii")
    base_snap = load_yaml_file(config_file)
    snap = YAMLReadResult(
        raw_bytes=b"sync:\n",
        text="sync:\n",
        document=base_snap.document,
        sha256=base_snap.sha256,
        encoding="ascii",
        newline="\n",
        source_path=str(config_file),
    )
    with pytest.raises(InvalidConfigForWrite, match="cannot be encoded"):
        preview_yaml_text(snap, "sync:\n  description: Příliš žluťoučký kůň\n")


def test_graph_hover_none_branch_and_repaint(qapp):
    graph = Graph("#ffffff", unit="number", secondary="#ff00ff")
    graph.resize(400, 200)
    # Both primary and secondary points are None at index 1
    graph.set_data(
        [
            (1000, 10, 20),
            (1010, None, None),
            (1020, 15, 30),
        ]
    )
    graph.hover_index = 1
    graph.show()
    qapp.processEvents()
    graph.repaint()
    qapp.processEvents()
    graph.close()


def test_session_table_cells_and_data_fallbacks(qapp):
    model = SessionTableModel(["Col1", "Col2"], "sync")
    # Uncached / unknown row fallback in _cells
    sess = {"identifier": "unknown-id", "name": "Test", "kind": "sync", "status": "ok"}
    cells, status, ident, extra = model._cells(sess)
    assert ident == "unknown-id"

    # Data fallback when row exceeds presentation cache length
    model.sessions = [sess]
    idx = model.index(0, 0)
    assert model.data(idx) is not None
    assert model.data(QModelIndex()) is None


def test_inspect_local_endpoint_oserror(tmp_path, monkeypatch):
    target = tmp_path / "unreadable_dir"
    target.mkdir()

    orig_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if "unreadable_dir" in str(self):
            raise OSError(errno.EACCES, "Permission denied")
        return orig_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)
    warnings, info = _inspect_local_root(
        "alpha",
        {"path": str(target)},
        mode="two-way-safe",
        mutagen_data_dir=tmp_path,
        session_stage_mode="mutagen",
    )
    assert any(w.get("code") == "local_root_unreadable" for w in warnings)
    assert info is None


def test_conflict_inspector_task_signals():
    task = _InspectionTask(MagicMock())
    received = []
    task.signals.completed.connect(lambda res, err: received.append((res, err)))

    # Simulate success
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "mutaui.ui.conflict_inspector_dialog.ParamikoRemoteInspector.inspect",
            lambda self, req, consent: "inspected_result",
        )
        task.run()
    assert received == [("inspected_result", None)]

    # Simulate failure
    received.clear()
    with pytest.MonkeyPatch.context() as mp:

        def raise_err(self, req, consent):
            raise RuntimeError("simulated sftp error")

        mp.setattr(
            "mutaui.ui.conflict_inspector_dialog.ParamikoRemoteInspector.inspect",
            raise_err,
        )
        task.run()
    assert len(received) == 1
    assert received[0][0] is None
    assert isinstance(received[0][1], RuntimeError)


def test_onboarding_inspect_cli_version_error():
    fake_client = MagicMock()
    fake_client.binary = "mutagen.exe"
    fake_client.command.side_effect = mutagen_client.MutagenError("version probe failed")
    discovery = inspect_cli(fake_client)
    assert not discovery.available
    assert "version probe failed" in discovery.error


def test_mutagen_client_daemon_state_and_fingerprint_errors():
    client = mutagen_client.MutagenClient("mutagen.exe")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            client,
            "list_sessions",
            MagicMock(side_effect=mutagen_client.MutagenError("daemon down")),
        )
        assert client._daemon_state() is False

        mp.setattr(
            mutagen_client,
            "read_registration",
            lambda binary: ("unregistered", ""),
        )
        fp = client._daemon_fingerprint("status", probe=True)
        assert len(fp) == 64
        assert isinstance(fp, str)
