from itertools import combinations

from scripts import capture_ui_matrix


def test_capture_cases_cover_every_pair_of_presentation_values():
    cases = capture_ui_matrix.CAPTURE_CASES
    assert len(cases) == 20
    assert {case[0] for case in cases} == {"dark", "light"}
    assert {case[1] for case in cases} == {"en", "cs"}
    assert {case[2] for case in cases} == {"basic", "advanced"}
    assert {case[3] for case in cases} == {"1", "1.25", "1.5", "2", "3.2"}

    for left, right in combinations(range(4), 2):
        observed = {(case[left], case[right]) for case in cases}
        expected = {
            (left_value, right_value)
            for left_value in {case[left] for case in cases}
            for right_value in {case[right] for case in cases}
        }
        assert observed == expected


def test_capture_matrix_runs_one_demo_capture_per_case(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        capture_ui_matrix.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    capture_ui_matrix.capture_matrix(tmp_path / "gallery")

    assert len(calls) == len(capture_ui_matrix.CAPTURE_CASES)
    assert all(call[1]["check"] is True for call in calls)
    assert {call[0][call[0].index("--scale") + 1] for call in calls} == {
        "1",
        "1.25",
        "1.5",
        "2",
        "3.2",
    }
    for command, _ in calls:
        if command[command.index("--scale") + 1] == "3.2":
            assert command[command.index("--window-width") + 1] == "1200"
            assert command[command.index("--window-height") + 1] == "675"
