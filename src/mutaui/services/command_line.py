"""Small, explicit command line surface for MutaUI launch routing."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LaunchCommand:
    command: str
    argument: str | None = None
    demo: bool = False
    self_test: bool = False
    version: bool = False
    linux_file_manager_action: str | None = None

    def instance_message(self) -> dict[str, str]:
        if self.command in {"open_session", "open_folder", "open_project"}:
            if self.argument is None or not self.argument.strip() or "\x00" in self.argument:
                raise ValueError("Launch route requires one non-empty exact argument.")
            key = "session_id" if self.command == "open_session" else "path"
            argument = (
                self.argument
                if key == "session_id"
                else str(Path(self.argument).expanduser().absolute())
            )
            return {"command": self.command, key: argument}
        return {"command": self.command}


def parse_launch_command(arguments: Sequence[str]) -> LaunchCommand:
    parser = argparse.ArgumentParser(prog="mutagen-control")
    routes = parser.add_mutually_exclusive_group()
    routes.add_argument("--open-session", metavar="EXACT_ID")
    routes.add_argument("--open-folder", metavar="LOCAL_PATH")
    routes.add_argument("--open-project", metavar="PROJECT_FILE")
    routes.add_argument("--doctor", action="store_true")
    routes.add_argument("--demo", action="store_true")
    routes.add_argument("--self-test", action="store_true")
    routes.add_argument("--version", action="store_true")
    routes.add_argument(
        "--install-linux-file-manager-integration",
        dest="linux_file_manager_action",
        action="store_const",
        const="install",
    )
    routes.add_argument(
        "--remove-linux-file-manager-integration",
        dest="linux_file_manager_action",
        action="store_const",
        const="remove",
    )
    parsed = parser.parse_args(list(arguments))
    if parsed.open_session:
        return LaunchCommand("open_session", parsed.open_session)
    if parsed.open_folder:
        return LaunchCommand("open_folder", parsed.open_folder)
    if parsed.open_project:
        return LaunchCommand("open_project", parsed.open_project)
    if parsed.doctor:
        return LaunchCommand("doctor")
    if parsed.demo:
        return LaunchCommand("focus", demo=True)
    if parsed.self_test:
        return LaunchCommand("focus", self_test=True)
    if parsed.version:
        return LaunchCommand("focus", version=True)
    if parsed.linux_file_manager_action:
        return LaunchCommand("focus", linux_file_manager_action=parsed.linux_file_manager_action)
    return LaunchCommand("focus")
