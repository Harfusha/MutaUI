from __future__ import annotations

from pathlib import Path

from mutaui.services import performance_advisor
from sync_configuration import validate_sync_proposal


def test_advisor_recommends_documented_modes_for_high_frequency_full_scan(tmp_path):
    session = {
        "watch": {"mode": "force-poll", "pollingInterval": 5},
        "scanMode": "full",
        "alpha": {"protocol": 0, "path": str(tmp_path)},
    }

    advice = performance_advisor.analyze_sync_session(
        session, mutagen_data_dir=tmp_path / ".mutagen"
    )

    assert advice["recommendations"] == {
        "watch.mode": "portable",
        "scanMode": "accelerated",
    }
    assert {
        key: validate_sync_proposal(key, value) for key, value in advice["recommendations"].items()
    } == advice["recommendations"]
    assert "high_frequency_polling" in {warning["code"] for warning in advice["warnings"]}
    assert advice["measured_performance"] is False


def test_advisor_does_not_override_intentional_no_watch(tmp_path):
    advice = performance_advisor.analyze_sync_session(
        {"watch": {"mode": "no-watch"}, "scanMode": "full"},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert "watch.mode" not in advice["recommendations"]
    assert "scanMode" not in advice["recommendations"]


def test_advisor_withholds_watch_and_scan_suggestions_for_invalid_local_root(tmp_path):
    advice = performance_advisor.analyze_sync_session(
        {
            "watch": {"mode": "force-poll", "pollingInterval": 5},
            "scanMode": "full",
            "alpha": {"protocol": 0, "path": str(tmp_path / "missing-root")},
        },
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert advice["recommendations"] == {}
    assert "local_root_missing" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_keeps_missing_counts_unknown_and_does_not_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(
        performance_advisor.os,
        "walk",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not recurse")),
    )
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(tmp_path)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert advice["entry_count"] is None
    assert "entry_count_unknown" in advice["guidance"]
    assert "large_root_scan_cost" in advice["guidance"]


def test_advisor_flags_symlink_root_without_following_it(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: True if path == root else real_is_symlink(path),
    )
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": "local", "path": str(root)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )

    codes = {warning["code"] for warning in advice["warnings"]}
    assert "local_root_symlink" in codes


def test_advisor_flags_unreadable_local_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    real_access = performance_advisor.os.access
    monkeypatch.setattr(
        performance_advisor.os,
        "access",
        lambda path, mode: False if Path(path) == root else real_access(path, mode),
    )
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert "local_root_unreadable" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_flags_unwritable_receiving_endpoint(tmp_path, monkeypatch):
    root = tmp_path / "receiver"
    root.mkdir()
    real_access = performance_advisor.os.access
    monkeypatch.setattr(
        performance_advisor.os,
        "access",
        lambda path, mode: (
            False
            if Path(path) == root and mode == performance_advisor.os.W_OK
            else real_access(path, mode)
        ),
    )

    advice = performance_advisor.analyze_sync_session(
        {
            "mode": "one-way-safe",
            "beta": {"protocol": 0, "path": str(root)},
        },
        mutagen_data_dir=tmp_path / ".mutagen",
    )

    assert "local_root_unwritable" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_suggests_endpoint_local_staging_only_on_device_mismatch(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    data = tmp_path / ".mutagen"
    data.mkdir()
    real_device = performance_advisor._path_device
    monkeypatch.setattr(
        performance_advisor,
        "_path_device",
        lambda path: 1 if Path(path) == root else (2 if Path(path) == data else real_device(path)),
    )

    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root)}}, mutagen_data_dir=data
    )

    assert advice["recommendations"]["alpha.stageMode"] == "neighboring"
    assert "cross_filesystem_staging" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_skips_unreported_remote_roots(tmp_path, monkeypatch):
    checked = []
    original = performance_advisor._inspect_local_root

    def record(side, endpoint, **kwargs):
        checked.append(side)
        return original(side, endpoint, **kwargs)

    monkeypatch.setattr(performance_advisor, "_inspect_local_root", record)
    performance_advisor.analyze_sync_session(
        {
            "alpha": {"protocol": "ssh", "path": "/remote/alpha"},
            "beta": {"protocol": "local", "path": str(tmp_path)},
        },
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert checked == ["beta"]


def test_advisor_skips_unc_local_roots_without_filesystem_access(monkeypatch):
    monkeypatch.setattr(
        performance_advisor.Path,
        "stat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("UNC root touched")),
    )
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": r"\\server\share\root"}},
        mutagen_data_dir=r"\\server\share\mutagen-data",
    )
    assert "local_root_network_uninspected" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_rejects_malformed_snapshot_without_recommendations():
    advice = performance_advisor.analyze_sync_session(None)
    assert advice["recommendations"] == {}
    assert advice["entry_count"] is None
    assert advice["measured_performance"] is False


def test_advisor_fails_closed_when_link_status_cannot_be_checked(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda _path: (_ for _ in ()).throw(OSError("access denied")),
    )

    advice = performance_advisor.analyze_sync_session(
        {
            "watch": {"mode": "force-poll", "pollingInterval": 2},
            "scanMode": "full",
            "alpha": {"protocol": 0, "path": str(root)},
        },
        mutagen_data_dir=tmp_path / ".mutagen",
    )

    assert "local_root_unreadable" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_flags_unreadable_local_root_when_stat_raises_os_error(tmp_path, monkeypatch):
    root = tmp_path / "root-oserror"
    root.mkdir()
    real_stat = Path.stat

    def _fail_stat(self, *args, **kwargs):
        if self == root:
            raise PermissionError("access denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _fail_stat)
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert "local_root_unreadable" in {warning["code"] for warning in advice["warnings"]}
    assert advice["recommendations"] == {}


def test_advisor_warns_when_poll_interval_is_unknown_or_at_default(tmp_path):
    unknown = performance_advisor.analyze_sync_session(
        {"watch": {"mode": "force-poll"}}, mutagen_data_dir=tmp_path / ".mutagen"
    )
    default = performance_advisor.analyze_sync_session(
        {"watch": {"mode": "force-poll", "pollingInterval": 10}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )

    assert "polling_interval_unknown" in {warning["code"] for warning in unknown["warnings"]}
    assert "polling_interval_unknown" not in {warning["code"] for warning in default["warnings"]}
    assert "high_frequency_polling" not in {warning["code"] for warning in default["warnings"]}


def test_advisor_does_not_touch_unc_staging_path(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root)}},
        mutagen_data_dir=r"\\server\share\mutagen-data",
    )

    assert "staging_path_network_uninspected" in {warning["code"] for warning in advice["warnings"]}
    assert "alpha.stageMode" not in advice["recommendations"]


def test_path_device_returns_unknown_for_network_and_unresolvable_paths(tmp_path, monkeypatch):
    assert performance_advisor._path_device(r"\\server\share\folder") is None
    monkeypatch.setattr(Path, "exists", lambda _path: False)
    assert performance_advisor._path_device(tmp_path / "missing") is None


def test_path_device_returns_unknown_when_filesystem_probe_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(
        Path,
        "exists",
        lambda _path: (_ for _ in ()).throw(OSError("unavailable")),
    )
    assert performance_advisor._path_device(tmp_path / "root") is None


def test_advisor_reports_missing_and_unreadable_local_roots(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing-root"
    missing = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(missing_path)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert "local_root_missing" in {warning["code"] for warning in missing["warnings"]}

    root = tmp_path / "unreadable-root"
    root.mkdir()
    real_stat = Path.stat

    def fail_root_stat(path, *args, **kwargs):
        if path == root:
            raise PermissionError("denied")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_root_stat)
    unreadable = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert "local_root_unreadable" in {warning["code"] for warning in unreadable["warnings"]}


def test_advisor_handles_missing_roots_and_access_errors(tmp_path, monkeypatch):
    unreported = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0}}, mutagen_data_dir=tmp_path / ".mutagen"
    )
    assert "local_root_unreported" in {warning["code"] for warning in unreported["warnings"]}

    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(
        performance_advisor.os,
        "access",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("denied")),
    )
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root)}},
        mutagen_data_dir=tmp_path / ".mutagen",
    )
    assert "local_root_unreadable" in {warning["code"] for warning in advice["warnings"]}


def test_advisor_skips_endpoint_staging_when_endpoint_uses_neighboring_mode(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    advice = performance_advisor.analyze_sync_session(
        {"alpha": {"protocol": 0, "path": str(root), "stageMode": "neighboring"}},
        mutagen_data_dir=r"\\server\share\mutagen-data",
    )
    codes = {warning["code"] for warning in advice["warnings"]}
    assert "staging_path_network_uninspected" not in codes
    assert "cross_filesystem_staging" not in codes
