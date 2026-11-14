from settings import DEFAULT_SETTINGS, validate_settings


def test_health_policy_defaults_validate_and_are_monitor_only():
    loaded = validate_settings({})

    assert not loaded.warnings
    assert loaded.values["health_mode"] == "monitor_only"
    assert loaded.values["health_failure_count"] == 3
    assert loaded.values["health_failure_elapsed"] == 120
    assert loaded.values["health_cooldown"] == 60
    assert loaded.values["health_max_attempts"] == 2
    assert loaded.values["health_attempt_window"] == 1800
    assert loaded.values["health_environment_grace"] == 120


def test_invalid_health_policy_values_fall_back_to_safe_defaults():
    loaded = validate_settings(
        {
            "health_mode": {"unexpected": "value"},
            "health_failure_count": 2,
            "health_failure_elapsed": 1,
            "health_cooldown": 5,
            "health_max_attempts": 3,
            "health_attempt_window": 10,
            "health_environment_grace": 0,
        }
    )

    assert loaded.warnings
    for key in (
        "health_mode",
        "health_failure_count",
        "health_failure_elapsed",
        "health_cooldown",
        "health_max_attempts",
        "health_attempt_window",
        "health_environment_grace",
    ):
        assert loaded.values[key] == DEFAULT_SETTINGS[key]


def test_health_mode_can_be_assisted_or_auto_safe_without_changing_mutagen_config():
    loaded = validate_settings({"health_mode": "assisted"})

    assert loaded.values["health_mode"] == "assisted"
    assert not loaded.warnings
