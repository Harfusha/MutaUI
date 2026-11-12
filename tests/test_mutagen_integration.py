"""Opt-in local-daemon integration test; never touches the user's normal daemon."""
import os
import shutil
import time
import uuid
from contextlib import suppress

import pytest

from mutagen_client import MutagenClient


def _mutagen_binary():
    return os.environ.get("MUTAGEN_BINARY") or shutil.which("mutagen") or shutil.which("mutagen.exe")


@pytest.mark.skipif(not _mutagen_binary(), reason="Mutagen CLI is not installed")
def test_local_sync_against_isolated_mutagen_daemon(tmp_path, monkeypatch):
    binary = _mutagen_binary()
    daemon_data = tmp_path / "daemon-data"
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    marker = alpha / "mutaui-integration.txt"
    marker.write_text("local daemon integration\n", encoding="utf-8")
    monkeypatch.setenv("MUTAGEN_DATA_DIRECTORY", str(daemon_data))
    monkeypatch.setenv("MUTAGEN_DISABLE_AUTOSTART", "0")
    client = MutagenClient(binary)
    name = "mutaui-test-" + uuid.uuid4().hex[:12]
    created_identifier = None

    try:
        client.command(["daemon", "start"], timeout=20)
        client.execute("sync", "create", options=[
            f"--name={name}", "--sync-mode=two-way-safe", str(alpha), str(beta),
        ])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            sessions = client.list_sessions("sync")
            created = next((item for item in sessions if item.get("name") == name), None)
            if created:
                created_identifier = created.get("identifier")
            if (beta / marker.name).exists():
                assert (beta / marker.name).read_text(encoding="utf-8") == "local daemon integration\n"
                break
            time.sleep(0.25)
        else:
            pytest.fail("Mutagen did not synchronize the local marker within 30 seconds")
        assert created_identifier
    finally:
        if created_identifier:
            with suppress(Exception):
                client.execute("sync", "terminate", created_identifier)
        with suppress(Exception):
            client.command(["daemon", "stop"], timeout=20)
