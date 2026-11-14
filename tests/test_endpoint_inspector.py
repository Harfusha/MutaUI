"""No Qt or network is required to inspect both Mutagen endpoints."""

import pytest

from endpoint_inspector import endpoint_view, session_views, summary
from mutagen_client import example_snapshot


def test_both_endpoints_are_taken_from_local_snapshot():
    s = example_snapshot().sync[0]
    a, b = session_views(s, "sync")
    assert a.side == "ALPHA" and b.side == "BETA"
    assert a.connected and b.connected
    assert a.files == b.files == 12486
    assert a.address.startswith("C:")
    assert "dev.example.com" in b.address
    assert summary(s, "sync")["successful_cycles"] == 1324


def test_stage_is_reported_not_invented():
    assert endpoint_view({}, "BETA").staging_percent is None
    e = endpoint_view(
        {
            "stagingProgress": {
                "receivedSize": 25,
                "expectedSize": 100,
                "path": "/tmp/a.txt",
                "receivedFiles": 1,
                "expectedFiles": 4,
            }
        },
        "BETA",
    )
    assert e.staging_percent == 25
    assert e.staging_files == 1 and e.staging_expected_files == 4
    assert (
        endpoint_view(
            {"stagingProgress": {"receivedFiles": 1, "expectedFiles": 2}}, "BETA"
        ).staging_percent
        == 50
    )


def test_missing_values_are_unknown_not_zero():
    e = endpoint_view({"connected": False}, "ALPHA")
    assert e.scanned is None
    assert e.files is None
    assert e.total_file_size is None
    assert not e.connected


def test_problem_totals_include_truncated_records():
    e = endpoint_view(
        {
            "scanProblems": [{"path": "a"}],
            "excludedScanProblems": 3,
            "transitionProblems": [{"path": "b"}, {"path": "c"}],
            "excludedTransitionProblems": 2,
        },
        "ALPHA",
    )
    assert e.scan_problems == 4 and e.transition_problems == 4


def test_forwarding_has_source_and_destination_and_traffic():
    s = example_snapshot().forward[0]
    v = summary(s, "forward")
    assert v["left"].side == "SOURCE"
    assert v["right"].side == "DESTINATION"
    assert v["open_connections"] == 2
    assert v["total_inbound_data"] > v["total_outbound_data"]
    assert v["left"].files is None


def test_snapshot_interpretation_never_opens_a_connection(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("Network should not be needed for parsing a snapshot")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    for s in example_snapshot().sync:
        assert summary(s, "sync")["identifier"] == s["identifier"]


def test_endpoint_view_fails_closed_for_invalid_staging_and_kind_specific_fields():
    invalid_staging = endpoint_view({"stagingProgress": ["unknown"], "scanned": True}, "ALPHA")
    empty_progress = endpoint_view(
        {
            "stagingProgress": {
                "receivedSize": 5,
                "expectedSize": 0,
                "receivedFiles": 0,
                "expectedFiles": 0,
            }
        },
        "ALPHA",
    )
    forwarding = endpoint_view(
        {"scanned": True, "files": 5, "scanProblems": ["ignored"]},
        "SOURCE",
        kind="forward",
    )

    assert invalid_staging.staging_percent is None
    assert invalid_staging.scanned is True
    assert empty_progress.staging_percent is None
    assert forwarding.scanned is None
    assert forwarding.files is None
    assert forwarding.scan_problems == 0


def test_unknown_session_kind_is_rejected():
    with pytest.raises(ValueError, match="Unknown session type"):
        session_views({}, "unknown")
