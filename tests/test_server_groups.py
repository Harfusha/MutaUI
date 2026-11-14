"""Server grouping must never need a network connection or other service."""

import pytest

from mutagen_client import example_snapshot
from server_groups import group_servers, session_servers


def ep(host, protocol=1, port=0):
    return {"protocol": protocol, "host": host, "port": port, "path": "/src"}


def ss(identifier, host, *, paused=False, status=6):
    return {
        "identifier": identifier,
        "alpha": {"protocol": 0, "path": "C:\\local"},
        "beta": ep(host),
        "paused": paused,
        "status": status,
    }


def test_many_syncs_one_server_and_other_server():
    groups = group_servers(
        [
            ss("one", "prod.example.com"),
            ss("two", "PROD.EXAMPLE.COM", paused=True),
            ss("three", "stage.example.com"),
        ],
        [],
    )
    assert len(groups) == 2
    prod = next(g for g in groups if g.name == "prod.example.com")
    assert prod.sync_ids == ["one", "two"]
    assert prod.paused == 1
    assert prod.count == 2


def test_two_remote_endpoints_do_not_double_count_single_server():
    a = ss("both", "host")
    a["alpha"] = ep("HOST")
    groups = group_servers([a], [])
    assert len(groups) == 1
    assert groups[0].sync_ids == ["both"]
    assert session_servers(a, "sync") == {"ssh:host:22"}
    assert session_servers({"alpha": [], "beta": None}, "sync") == set()


def test_forward_and_sync_share_server_but_local_endpoints_not_grouped():
    f = {
        "identifier": "forward1",
        "source": {"protocol": 0, "endpoint": "tcp:localhost:555"},
        "destination": {"protocol": 1, "host": "host", "endpoint": "tcp:127.0.0.1:55"},
        "status": 3,
    }
    groups = group_servers([ss("sync1", "host")], [f])
    assert len(groups) == 1
    assert groups[0].sync_ids == ["sync1"] and groups[0].forward_ids == ["forward1"]


def test_no_guessing_dns_aliases_and_no_network_calls(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("unexpected network access")
    )
    groups = group_servers(
        [
            ss("one", "app-alias"),
            ss("two", "app.internal"),
            ss("local", "host") | {"beta": {"protocol": 0, "path": "D:\\local"}},
        ],
        [],
    )
    assert len(groups) == 2


def test_ssh_ports_and_docker_are_distinct_servers():
    first = ss("one", "host")
    second = ss("two", "host")
    second["beta"]["port"] = 2222
    docker = ss("three", "host")
    docker["beta"]["protocol"] = 11
    groups = group_servers([first, second, docker], [])
    assert {g.key for g in groups} == {"ssh:host:22", "ssh:host:2222", "docker:host"}


def test_example_snapshot_maps_multiple_servers():
    snap = example_snapshot()
    groups = group_servers(snap.sync, snap.forward)
    assert sum(len(g.sync_ids) for g in groups) == 3
    assert sum(len(g.forward_ids) for g in groups) == 1


def test_invalid_ssh_port_falls_back_and_missing_identifier_is_ignored():
    session = ss("bad-port", "host")
    session["beta"]["port"] = "not-a-port"
    missing_id = ss("", "ignored.example")

    groups = group_servers([session, missing_id], [])

    assert len(groups) == 1
    assert groups[0].key == "ssh:host:22"
    assert groups[0].sync_ids == ["bad-port"]


def test_ssh_protocol_name_uses_conservative_protocol_mapping():
    session = ss("named-protocol", "host")
    session["beta"]["protocol"] = "SSH"

    groups = group_servers([session], [])

    assert len(groups) == 1
    assert groups[0].key == "ssh:host:22"


def test_non_mapping_endpoint_is_ignored():
    malformed = {"identifier": "bad", "alpha": {"protocol": 0}, "beta": ["not", "an endpoint"]}
    assert session_servers(malformed, "sync") == set()
