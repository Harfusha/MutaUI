from types import SimpleNamespace
import pytest
from sync_profiles import PROFILES, profile_flags, AdaptivePolling, native_config_text


def test_profiles_use_supported_cli_create_flags_only():
    for key in PROFILES:
        flags = profile_flags(key)
        assert all(f.startswith(("--watch-mode=", "--watch-polling-interval=", "--scan-mode=")) for f in flags)
    assert profile_flags("eco_poll") == ["--watch-mode=force-poll", "--watch-polling-interval=60"]
    with pytest.raises(ValueError): profile_flags("nonexistent")


def test_adaptive_polling_settles_to_idle_and_wakes_after_change():
    ticks = [100.0]
    policy = AdaptivePolling(fast=2, idle=30, quiet_after=90, clock=lambda: ticks[0])
    snap = SimpleNamespace(sync=[{"identifier": "s1", "paused": False, "status": 6, "successfulCycles": 1}], forward=[])
    policy.observe(snap)
    assert policy.interval(enabled=True, normal=5) == 2
    ticks[0] = 195
    policy.observe(snap)
    assert policy.interval(enabled=True, normal=5) == 30
    snap.sync[0]["successfulCycles"] = 2
    policy.observe(snap)
    assert policy.interval(enabled=True, normal=5) == 2
    assert policy.interval(enabled=True, normal=5, eco=True) >= 15
    assert policy.interval(enabled=False, normal=7) == 7


def test_session_config_view_does_not_make_up_bandwidth_data():
    txt = native_config_text({"watch": {"mode": 1, "pollingInterval": 20}, "scanMode": 2})
    assert "20" in txt
    assert "Scan mode" in txt
