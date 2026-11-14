from datetime import datetime

import pytest


def test_quiet_hours_disabled_never_suppresses():
    from mutaui.services.quiet_hours import quiet_hours_active

    assert not quiet_hours_active(datetime(2026, 1, 1, 23), enabled=False)


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (datetime(2026, 1, 1, 21, 59), False),
        (datetime(2026, 1, 1, 22), True),
        (datetime(2026, 1, 2, 6, 59), True),
        (datetime(2026, 1, 2, 7), False),
    ],
)
def test_overnight_quiet_hours_boundaries(current, expected):
    from mutaui.services.quiet_hours import quiet_hours_active

    assert quiet_hours_active(current, enabled=True, start="22:00", end="07:00") is expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (datetime(2026, 1, 1, 12), False),
        (datetime(2026, 1, 1, 13), True),
        (datetime(2026, 1, 1, 17), False),
    ],
)
def test_same_day_quiet_hours(current, expected):
    from mutaui.services.quiet_hours import quiet_hours_active

    assert quiet_hours_active(current, enabled=True, start="13:00", end="17:00") is expected


@pytest.mark.parametrize("value", ["7:00", "24:00", "12:60", "noon", ""])
def test_invalid_quiet_hour_time_is_rejected(value):
    from mutaui.services.quiet_hours import quiet_hours_active

    with pytest.raises(ValueError, match="HH:MM"):
        quiet_hours_active(datetime(2026, 1, 1, 12), enabled=True, start=value, end="07:00")


def test_invalid_quiet_hour_end_time_is_rejected():
    from mutaui.services.quiet_hours import quiet_hours_active

    with pytest.raises(ValueError, match="HH:MM"):
        quiet_hours_active(datetime(2026, 1, 1, 12), enabled=True, start="10:00", end="25:00")


def test_equal_start_and_end_means_quiet_hours_are_disabled():
    from mutaui.services.quiet_hours import quiet_hours_active

    assert not quiet_hours_active(
        datetime(2026, 1, 1, 12), enabled=True, start="12:00", end="12:00"
    )
