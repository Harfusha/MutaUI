"""Regression tests for Batch 2C: Profile isolation, effective configuration, ignore ordering, and socket safety (M09, M10, M12, M13, M14)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from connection_profiles import ConnectionProfile
from forward_configuration import (
    classify_forward_listener,
)
from ignore_presets import (
    explain_ignore_path,
    format_ignore_layers,
)
from mutagen_client import (
    MutagenClient,
    MutagenError,
)
from mutaui.ui.session_dialog import SessionDialog
from sync_configuration import (
    build_effective_forward_configuration,
    build_effective_sync_configuration,
    compute_global_config_fingerprint,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ============================================================================
# M09 & A07: Profile Switching Isolation
# ============================================================================


def test_profile_switching_resets_mode_and_ignore_rules_when_omitted(qapp, tmp_path):
    """M09 & A07: Switching from a full profile to a sparse profile or 'No profile' must not carry over values."""
    full_profile = ConnectionProfile(
        id="profile_a",
        name="Profile Full",
        kind="sync",
        endpoint_a=str(tmp_path / "a"),
        endpoint_b=str(tmp_path / "b"),
        defaults={
            "mode": "one-way-replica",
            "ignore.paths": ["*.log", "build/", "temp/"],
            "ignore.vcs": True,
            "watch.mode": "force-poll",
            "watch.pollingInterval": 5,
        },
    )
    sparse_profile = ConnectionProfile(
        id="profile_b",
        name="Profile Sparse",
        kind="sync",
        endpoint_a=str(tmp_path / "sparse_a"),
        endpoint_b=str(tmp_path / "sparse_b"),
        defaults={},  # No mode, no ignore rules
    )

    dialog = SessionDialog(
        kind="sync",
        ui_mode="advanced",
        saved_profiles=(full_profile, sparse_profile),
    )

    # 1. Select full profile
    idx_full = dialog.connection_profile.findText("Profile Full")
    dialog.connection_profile.setCurrentIndex(idx_full)
    assert dialog.mode.currentText() == "one-way-replica"
    assert "*.log" in dialog.ignore.toPlainText()
    assert "build/" in dialog.ignore.toPlainText()
    assert dialog.ignore_vcs.isChecked() is True

    # 2. Switch to sparse profile
    idx_sparse = dialog.connection_profile.findText("Profile Sparse")
    dialog.connection_profile.setCurrentIndex(idx_sparse)
    # Mode must reset to default "two-way-safe", not linger as "one-way-replica"
    assert dialog.mode.currentText() == "two-way-safe"
    # Ignore rules must reset to empty, not linger from Profile Full
    assert dialog.ignore.toPlainText().strip() == ""
    # VCS must reset to partially checked
    assert dialog.ignore_vcs.checkState() == Qt.CheckState.PartiallyChecked
    # Endpoints updated to Profile Sparse
    assert dialog.a.text() == str(tmp_path / "sparse_a")
    assert dialog.b.text() == str(tmp_path / "sparse_b")

    # 3. Switch to "No saved profile" (index 0)
    dialog.connection_profile.setCurrentIndex(0)
    assert dialog.mode.currentText() == "two-way-safe"
    assert dialog.ignore.toPlainText().strip() == ""
    assert dialog.ignore_vcs.checkState() == Qt.CheckState.PartiallyChecked


def test_profile_switching_forward_resets_socket_settings(qapp, tmp_path):
    """M09: Forward profiles reset socket settings cleanly when switching."""
    fwd_full = ConnectionProfile(
        id="fwd_full",
        name="Forward Full",
        kind="forward",
        endpoint_a="unix:/tmp/source.sock",
        endpoint_b="tcp:localhost:8080",
        defaults={
            "source.socket.overwriteMode": "overwrite",
            "source.socket.owner": "admin",
            "source.socket.permissionMode": "0600",
        },
    )
    fwd_sparse = ConnectionProfile(
        id="fwd_sparse",
        name="Forward Sparse",
        kind="forward",
        endpoint_a="tcp:127.0.0.1:9000",
        endpoint_b="tcp:localhost:8080",
        defaults={},
    )

    dialog = SessionDialog(
        kind="forward",
        ui_mode="advanced",
        saved_profiles=(fwd_full, fwd_sparse),
    )

    idx_full = dialog.connection_profile.findText("Forward Full")
    dialog.connection_profile.setCurrentIndex(idx_full)
    assert dialog.socket_overwrite_source.currentData() == "overwrite"
    assert dialog.socket_owner_source.text() == "admin"
    assert dialog.socket_permission_source.text() == "0600"

    # Switch to sparse profile
    idx_sparse = dialog.connection_profile.findText("Forward Sparse")
    dialog.connection_profile.setCurrentIndex(idx_sparse)
    assert dialog.socket_overwrite_source.currentData() == "leave"
    assert dialog.socket_owner_source.text() == ""
    assert dialog.socket_permission_source.text() == ""


# ============================================================================
# M10: Effective Configuration & Preflight Global Config Invalidation
# ============================================================================


def test_global_config_fingerprint_and_invalidation(tmp_path, monkeypatch):
    """M10: Modifying global config between plan preparation and execution invalidates preflight fingerprint."""
    home_dir = tmp_path / "mock_home"
    home_dir.mkdir()
    config_file = home_dir / ".mutagen.yml"
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))

    # Initial state: no file
    fp1, exists1 = compute_global_config_fingerprint(config_file)
    assert fp1 == "none"
    assert not exists1

    # Create file
    config_file.write_text("sync:\n  defaults:\n    mode: two-way-safe\n", encoding="utf-8")
    fp2, exists2 = compute_global_config_fingerprint(config_file)
    assert exists2
    assert fp2 != "none"

    client = MutagenClient("mutagen")
    options = ["--mode=two-way-safe", str(tmp_path / "a"), str(tmp_path / "b")]
    plan = client.prepare_create_plan("sync", options)
    consented = client.consent_action_plan(plan, consent=True)

    # Modify file before execution
    config_file.write_text("sync:\n  defaults:\n    mode: one-way-safe\n", encoding="utf-8")
    fp3, _ = compute_global_config_fingerprint(config_file)
    assert fp3 != fp2

    # Execution must fail due to modified global config
    with pytest.raises(MutagenError, match="Global Mutagen configuration was modified"):
        client.execute(
            "sync",
            "create",
            options=options,
            operator_consent=True,
            action_plan=consented,
        )


def test_build_effective_sync_and_forward_configuration():
    """M10 & M14: Effective configuration distinguishes global, CLI, and default origins."""
    sync_yaml = b"sync:\n  defaults:\n    mode: one-way-safe\n    ignore:\n      paths:\n        - '*.log'\n"
    sync_preview = build_effective_sync_configuration(
        sync_yaml,
        ["--mode=two-way-safe", "--ignore=build/", str(Path("/a")), str(Path("/b"))],
    )
    assert sync_preview.valid
    mapping = sync_preview.as_mapping()
    assert mapping["mode"] == "two-way-safe"
    assert sync_preview.origin_for("mode") == "command line"
    assert "*.log" in mapping["ignore.paths"]
    assert "build/" in mapping["ignore.paths"]
    assert sync_preview.origin_for("ignore.paths") == "global config + command line (appended)"

    fwd_yaml = b"forward:\n  defaults:\n    source:\n      socket:\n        overwriteMode: leave\n"
    fwd_preview = build_effective_forward_configuration(
        fwd_yaml,
        [
            "--socket-overwrite-mode-source=overwrite",
            "--socket-permission-mode-source=0600",
            "unix:/tmp/source.sock",
            "tcp:localhost:8080",
        ],
    )
    assert fwd_preview.valid
    fwd_map = fwd_preview.as_mapping()
    assert fwd_map["source.socket.overwriteMode"] == "overwrite"
    assert fwd_preview.origin_for("source.socket.overwriteMode") == "command line"
    assert fwd_map["source.socket.permissionMode"] == "0600"
    assert fwd_preview.origin_for("source.socket.permissionMode") == "command line"


# ============================================================================
# M12: Ignore Presets & Rule Evaluation Ordering
# ============================================================================


def test_ignore_rule_ordering_and_root_anchoring():
    """M12: Rules respect root anchoring (/pattern) and later negation overrides."""
    # Root anchored: '/root_only.txt' must match 'root_only.txt' but NOT 'nested/root_only.txt'
    res1 = explain_ignore_path("root_only.txt", session_rules=("/root_only.txt",))
    assert res1.ignored is True
    assert res1.matched_rule == "/root_only.txt"

    res2 = explain_ignore_path("nested/root_only.txt", session_rules=("/root_only.txt",))
    assert res2.ignored is False
    assert res2.matched_rule is None

    # Negation rule overrides earlier rule
    res3 = explain_ignore_path(
        "keep.txt",
        session_rules=("*.txt", "!keep.txt"),
    )
    assert res3.ignored is False
    assert res3.matched_rule == "!keep.txt"
    assert "negation" in res3.note

    # Global vs session rule order: session negation overrides global rule
    res4 = explain_ignore_path(
        "report.log",
        global_rules=("*.log",),
        session_rules=("!report.log",),
    )
    assert res4.ignored is False
    assert res4.matched_rule == "!report.log"
    assert res4.scope == "session"


def test_format_ignore_layers_annotations():
    """M12: format_ignore_layers with annotate=True marks negations and root-anchored rules."""
    rendered = format_ignore_layers(
        global_rules=("*.log",),
        session_rules=("/root_only.txt", "!keep.log"),
        annotate=True,
    )
    assert "[negation/override]" in rendered
    assert "[root-anchored]" in rendered
    assert "eval #1" in rendered
    assert "eval #2" in rendered
    assert "eval #3" in rendered


# ============================================================================
# M13 & A08: Forward Listener Classification Outside Loopback
# ============================================================================


@pytest.mark.parametrize(
    "endpoint,expected_scope,is_loopback,warning_required",
    [
        ("tcp:localhost:8080", "loopback", True, False),
        ("tcp:127.0.0.1:8080", "loopback", True, False),
        ("tcp:127.0.1.1:8080", "loopback", True, False),
        ("tcp4:127.0.0.1:9000", "loopback", True, False),
        ("tcp6:[::1]:9000", "loopback", True, False),
        ("unix:/tmp/test.sock", "unix", True, False),
        ("npipe:\\\\.\\pipe\\test", "named_pipe", True, False),
        # Wildcard / public
        ("tcp:0.0.0.0:8080", "wildcard", False, True),
        ("tcp4:0.0.0.0:8080", "wildcard", False, True),
        ("tcp::8080", "wildcard", False, True),
        ("tcp:::8080", "wildcard", False, True),
        ("tcp6:[::]:8080", "wildcard", False, True),
        ("tcp:*:8080", "wildcard", False, True),
        # Specific non-loopback interface
        ("tcp:192.168.1.50:8080", "specific_interface", False, True),
        ("tcp:10.0.0.1:8080", "specific_interface", False, True),
        ("tcp:myhost.local:8080", "specific_interface", False, True),
        # Remote
        ("user@remote:tcp:localhost:8080", "remote", False, True),
        ("docker://container:tcp:localhost:8080", "remote", False, True),
    ],
)
def test_classify_forward_listener(endpoint, expected_scope, is_loopback, warning_required):
    """M13 & A08: Comprehensive listener classification for loopback, wildcard, and interfaces."""
    result = classify_forward_listener(endpoint)
    assert result.scope == expected_scope
    assert result.is_loopback == is_loopback
    assert result.warning_required == warning_required


def test_session_dialog_warns_on_non_loopback_listener_and_respects_rejection(qapp, monkeypatch):
    """M13 & A08: Dialog prompts on non-loopback listener; rejection halts session creation."""
    dialog = SessionDialog(kind="forward", ui_mode="basic")
    dialog.a.setText("tcp:192.168.1.100:8080")
    dialog.b.setText("tcp:localhost:8080")

    # Simulate operator clicking "No" (rejecting the public listener)
    warn_calls = []

    def mock_warning(parent, title, text, *args, **kwargs):
        warn_calls.append((title, text))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "warning", mock_warning)

    # validate() should abort and not call accept()
    accepted = []
    dialog.accept = lambda: accepted.append(True)
    dialog.validate()

    assert len(warn_calls) == 1
    assert "Public Forwarding Listener" in warn_calls[0][0]
    assert "192.168.1.100" in warn_calls[0][1]
    assert len(accepted) == 0  # Not accepted!

    # Simulate operator clicking "Yes" (confirming)
    warn_calls.clear()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)
    dialog.validate()
    assert len(accepted) == 1  # Accepted!
