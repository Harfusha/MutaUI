from pathlib import Path

import pytest

from mutaui.services.command_line import LaunchCommand, parse_launch_command


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ([], {"command": "focus"}),
        (["--doctor"], {"command": "doctor"}),
        (["--open-session", "exact-id"], {"command": "open_session", "session_id": "exact-id"}),
        (
            ["--open-folder", "C:/Sync"],
            {"command": "open_folder", "path": str(Path("C:/Sync").absolute())},
        ),
        (
            ["--open-project", "C:/repo/mutagen.yml"],
            {"command": "open_project", "path": str(Path("C:/repo/mutagen.yml").absolute())},
        ),
    ],
)
def test_cli_routes_are_narrow_and_convert_to_instance_messages(arguments, message):
    assert parse_launch_command(arguments).instance_message() == message


def test_cli_modes_and_target_routes_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_launch_command(["--open-session", "one", "--open-folder", "C:/Sync"])
    assert parse_launch_command(["--self-test"]).self_test
    assert parse_launch_command(["--demo"]).demo
    assert parse_launch_command(["--version"]).version


@pytest.mark.parametrize(
    "command,argument",
    [
        ("open_session", None),
        ("open_folder", "  "),
        ("open_project", "project\x00.yml"),
    ],
)
def test_instance_message_rejects_missing_or_ambiguous_exact_targets(command, argument):
    with pytest.raises(ValueError, match="one non-empty exact argument"):
        LaunchCommand(command=command, argument=argument).instance_message()
