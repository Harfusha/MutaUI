"""Mutagen CLI adapter. No shell, no hidden destructive commands."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from mutaui.services.action_planner import (
    ActionPlan,
    ActionPlanner,
    ActionPlanningError,
    ActionRequest,
)

SYNC_STATUS = {
    0: "Disconnected",
    1: "Halted: empty root",
    2: "Halted: deleted root",
    3: "Halted: root type change",
    4: "Connecting ALPHA",
    5: "Connecting BETA",
    6: "Watching",
    7: "Scanning",
    8: "Waiting to retry",
    9: "Reconciling",
    10: "Staging to ALPHA",
    11: "Staging to BETA",
    12: "Saving",
    13: "Saving",
}
FORWARD_STATUS = {
    0: "Disconnected",
    1: "Connecting source",
    2: "Connecting destination",
    3: "Forwarding active",
}

_FORWARD_SOCKET_FLAGS = frozenset(
    f"--socket-{name}{endpoint}"
    for name in ("overwrite-mode", "owner", "group", "permission-mode")
    for endpoint in ("", "-source", "-destination")
)
_FORWARD_SOCKET_HELP_FLAG = re.compile(r"(?m)^\s*(--socket-[a-z0-9-]+)(?=[=\s]|$)")


def _create_action_key(area: str, options: list[str]) -> str:
    replica_mode = area == "sync" and any(
        value in {"--mode=one-way-replica", "--sync-mode=one-way-replica"} for value in options
    )
    socket_overwrite = area == "forward" and any(
        re.fullmatch(r"--socket-overwrite-mode(?:-(?:source|destination))?=overwrite", value)
        for value in options
    )
    if replica_mode:
        return "sync_replica"
    if socket_overwrite:
        return "forward_socket_overwrite"
    return f"{area}_create"


def session_preflight_fingerprint(sessions: list[dict]) -> str:
    """Fingerprint exact native rows for consent-to-execution freshness checks."""
    volatile_fields = {
        "status",
        "files",
        "conflicts",
        "problems",
        "lastError",
        "lastErrorInfo",
        "lastSuccessfulScan",
        "lastSuccessfulTransfer",
        "alphaFiles",
        "betaFiles",
    }
    stable_rows = [
        {key: value for key, value in session.items() if key not in volatile_fields}
        for session in sessions
    ]
    canonical = json.dumps(
        sorted(stable_rows, key=lambda item: str(item.get("identifier", ""))),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def native_sync_startup_state(session: dict, daemon_registration: str) -> str:
    """State under Mutagen's own persistent pause + Windows daemon registration.

    There is no separate per-session auto-run flag in Mutagen.
    """
    if session.get("paused"):
        return "paused"
    return "enabled" if daemon_registration == "registered" else "needs-registration"


class MutagenError(RuntimeError):
    pass


class MutagenCommandError(MutagenError):
    """Raised when Mutagen exits with a failure status."""


class MutagenCommandTimeout(MutagenError):
    """Raised when Mutagen does not return before its command timeout."""


class MutagenLaunchError(MutagenError):
    """Raised when the Mutagen process could not be started."""


def clean_executable(path: str) -> str:
    path = path.strip().strip('"')
    if not path:
        found = shutil.which("mutagen") or shutil.which("mutagen.exe")
        if found:
            return found
        for candidate in _known_mutagen_locations():
            if candidate.is_file():
                return str(candidate)
        return ""
    expanded = os.path.expandvars(os.path.expanduser(path))
    if os.path.isfile(expanded):
        return expanded
    found = shutil.which(expanded)
    return found or ""


def _known_mutagen_locations() -> tuple[Path, ...]:
    """Return bounded, conventional install locations without scanning user files."""
    home = Path.home()
    if sys.platform == "win32":
        locations = [
            Path(root) / "Mutagen" / "mutagen.exe"
            for root in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMW6432"))
            if root
        ]
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            locations.append(Path(local_app_data) / "Programs" / "Mutagen" / "mutagen.exe")
        locations.append(home / "bin" / "mutagen.exe")
        return tuple(locations)
    if sys.platform == "darwin":
        return (
            Path("/opt/homebrew/bin/mutagen"),
            Path("/usr/local/bin/mutagen"),
            home / "bin" / "mutagen",
        )
    return (
        Path("/usr/local/bin/mutagen"),
        Path("/usr/bin/mutagen"),
        Path("/home/linuxbrew/.linuxbrew/bin/mutagen"),
        home / ".local" / "bin" / "mutagen",
        home / "bin" / "mutagen",
    )


def parse_sessions(output: str) -> list[dict]:
    """JSON Go-template output; returns [] for an empty daemon."""
    try:
        payload = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise MutagenError(
            "Mutagen did not return valid JSON. Check the Mutagen version and --template support."
        ) from exc
    if not isinstance(payload, list):
        raise MutagenError("Unexpected data structure in Mutagen response.")
    return [item for item in payload if isinstance(item, dict)]


def endpoint_text(endpoint: Any, kind: str = "sync") -> str:
    """Reconstruct human-oriented endpoint address from exported model."""
    if not isinstance(endpoint, dict):
        return "—"
    protocol = endpoint.get("protocol", 0)
    path = str(endpoint.get("path" if kind == "sync" else "endpoint", ""))
    host = str(endpoint.get("host", ""))
    user = str(endpoint.get("user", ""))
    port = endpoint.get("port", 0)
    try:
        proto = int(protocol)
    except (TypeError, ValueError):
        proto = {"local": 0, "ssh": 1, "docker": 11}.get(str(protocol).lower(), 0)
    if proto == 1:
        who = (user + "@") if user else ""
        port_text = f":{port}" if port else ""
        return f"{who}{host}{port_text}:{path}"
    if proto == 11:
        return f"docker://{host}:{path}"
    return path or "—"


def classify(session: dict, kind: str) -> tuple[str, str]:
    if session.get("paused"):
        return "paused", "Paused"
    endpoints = (session.get("alpha") or {}, session.get("beta") or {})
    has_problems = any(
        endpoint.get(key)
        for endpoint in endpoints
        for key in (
            "scanProblems",
            "transitionProblems",
            "excludedScanProblems",
            "excludedTransitionProblems",
        )
    )
    if session.get("lastError") or (
        kind == "sync"
        and (session.get("conflicts") or session.get("excludedConflicts") or has_problems)
    ):
        return "error", "Needs attention"
    raw = session.get("status", 0)
    try:
        status = int(raw)
    except (ValueError, TypeError):
        status = -1
    if kind == "sync":
        text = SYNC_STATUS.get(status, str(raw))
        if status in (1, 2, 3, 8):
            return "error", text
        return (
            "active"
            if status == 6
            else "busy"
            if status in (4, 5, 7, 9, 10, 11, 12, 13)
            else "idle",
            text,
        )
    text = FORWARD_STATUS.get(status, str(raw))
    return ("active" if status == 3 else "busy" if status in (1, 2) else "idle", text)


def conflict_count(session: dict) -> int:
    return len(session.get("conflicts") or []) + int(session.get("excludedConflicts") or 0)


def problem_count(session: dict) -> int:
    total = 0
    for endpoint in (session.get("alpha") or {}, session.get("beta") or {}):
        for name in ("scanProblems", "transitionProblems"):
            total += len(endpoint.get(name) or [])
        for name in ("excludedScanProblems", "excludedTransitionProblems"):
            total += int(endpoint.get(name) or 0)
    return total


def human_bytes(number: float | int) -> str:
    number = float(number)
    if abs(number) < 1024:
        return f"{number:.0f} B"
    number /= 1024
    if abs(number) < 1024:
        return f"{number:.1f} KB"
    number /= 1024
    if abs(number) < 1024:
        return f"{number:.1f} MB"
    number /= 1024
    if abs(number) < 1024:
        return f"{number:.1f} GB"
    number /= 1024
    return f"{number:.1f} TB"


@dataclass
class Snapshot:
    binary: str = ""
    daemon: bool = False
    sync: list[dict] = field(default_factory=list)
    forward: list[dict] = field(default_factory=list)
    cpu: float = 0.0
    memory: int = 0
    processes: int = 0
    error: str = ""
    sessions_stale: bool = False
    version: str = ""
    registration: str = "unknown"
    registration_command: str = ""
    sync_observed_at: datetime | None = None
    forward_observed_at: datetime | None = None
    resource_observed_at: datetime | None = None
    command_durations: dict[str, float] = field(default_factory=dict)


def read_registration(binary: str) -> tuple[str, str]:
    r"""Official Windows daemon registration lives in HKCU\...\Run\Mutagen.

    No registry modifications are done here.
    """
    if sys.platform != "win32":
        return "unsupported", ""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        with key:
            raw, _ = winreg.QueryValueEx(key, "Mutagen")
    except FileNotFoundError:
        return "unregistered", ""
    except OSError:
        return "unknown", ""
    if not isinstance(raw, str):
        return "unknown", ""
    expected = f'"{binary}" daemon start'
    if binary and os.path.normcase(raw.strip()) == os.path.normcase(expected):
        return "registered", raw
    return "other", raw


class MutagenClient:
    def __init__(self, binary: str = "", *, action_planner: ActionPlanner | None = None):
        self.binary = clean_executable(binary)
        self.action_planner = action_planner or ActionPlanner(now=time.monotonic)
        self.last_created_session: tuple[str, str, tuple[str, ...]] | None = None

    @staticmethod
    def session_preflight_fingerprint(sessions: list[dict]) -> str:
        return session_preflight_fingerprint(sessions)

    def _daemon_target_id(self) -> str:
        executable = os.path.normcase(os.path.realpath(self.binary))
        digest = hashlib.sha256(executable.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"daemon:{digest}"

    def _daemon_state(self) -> bool:
        """Probe the per-user daemon without allowing session CLI autostart."""
        try:
            self.list_sessions("sync")
            return True
        except MutagenError:
            return False

    def _daemon_fingerprint(self, action: str, *, probe: bool = True) -> str:
        running: bool | str = "not-checked"
        if probe:
            try:
                running = self._daemon_state()
            except MutagenError:
                running = False
        registration, registration_command = read_registration(self.binary)
        payload = {
            "binary": os.path.normcase(os.path.realpath(self.binary)),
            "action": action,
            "running": running,
            "registration": registration,
            "registration_command": registration_command,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def prepare_daemon_plan(self, action: str) -> ActionPlan:
        allowed = {"start", "stop", "register", "unregister"}
        if action not in allowed:
            raise MutagenError("Invalid daemon command.")
        if (
            action in {"register", "unregister"}
            and read_registration(self.binary)[0] == "unsupported"
        ):
            raise MutagenError("Mutagen daemon registration is unsupported on this platform.")
        action_key = f"daemon_{action}"
        fingerprint = self._daemon_fingerprint(action)
        return self.action_planner.prepare(
            ActionRequest(
                action=action_key,
                target_ids=(self._daemon_target_id(),),
                argv=("daemon", action),
                preflight_fingerprint=fingerprint,
                capabilities=(action_key,),
            )
        )

    def _execute_planned_daemon(
        self,
        action: str,
        plan: ActionPlan | None,
        *,
        operator_consent: bool,
        timeout: int,
    ) -> str:
        action_key = f"daemon_{action}"
        target_ids = (self._daemon_target_id(),)
        if (
            not operator_consent
            or plan is None
            or plan.state != "consented"
            or plan.action != action_key
            or plan.target_ids != target_ids
            or plan.argv != ("daemon", action)
        ):
            raise MutagenError("A consented exact daemon ActionPlan is required.")
        if self._daemon_fingerprint(action) != plan.preflight_fingerprint:
            self.action_planner.finish(
                plan.plan_id,
                verified_target_ids=(),
                outcome="daemon state changed after preview; refresh before retrying",
            )
            raise MutagenError("The daemon changed after its action preview; no command ran.")
        try:
            output = self.command(["daemon", action], timeout=timeout)
            if action == "start" and not self._daemon_state():
                raise MutagenError("Native post-check could not find the started daemon.")
            if action == "stop" and self._daemon_state():
                raise MutagenError("Native post-check found the daemon still running.")
            if action == "register" and read_registration(self.binary)[0] != "registered":
                raise MutagenError("Native post-check could not verify daemon registration.")
            if action == "unregister" and read_registration(self.binary)[0] != "unregistered":
                raise MutagenError("Native post-check could not verify registration removal.")
        except Exception:
            self.action_planner.finish(
                plan.plan_id,
                verified_target_ids=(),
                outcome="daemon result or native post-check is uncertain; refresh before retrying",
            )
            raise
        self.action_planner.finish(
            plan.plan_id,
            verified_target_ids=target_ids,
            outcome=f"native daemon {action} post-check passed",
        )
        return output

    def _planned_session_action(
        self,
        area: str,
        action: str,
        target_ids: list[str],
        arguments: list[str],
        *,
        expected_fingerprint: str,
        operator_consent: bool,
        timeout: int,
    ) -> str:
        if not operator_consent:
            raise MutagenError("An explicit operator confirmation is required for this action.")
        current = self.list_sessions(area)
        by_id = {str(item.get("identifier") or ""): item for item in current}
        selected = [by_id[target] for target in target_ids if target in by_id]
        if len(selected) != len(target_ids):
            raise MutagenError(
                "A selected exact session no longer exists; refresh before retrying."
            )
        action_key = f"{area}_{action}"
        current_fingerprint = self.session_preflight_fingerprint(selected)
        plan = self.action_planner.prepare(
            ActionRequest(
                action=action_key,
                target_ids=tuple(target_ids),
                argv=tuple(arguments),
                preflight_fingerprint=expected_fingerprint,
                capabilities=(action_key,),
            )
        )
        consented = self.action_planner.consent(
            plan.plan_id,
            consent=True,
            current_preflight_fingerprint=current_fingerprint,
        )
        if consented.state != "consented":
            raise MutagenError(
                "The selected session changed after its action preview; no command ran."
            )
        try:
            output = self.command(arguments, timeout=timeout)
            after = self.list_sessions(area)
            after_ids = {str(item.get("identifier") or "") for item in after}
            if action == "terminate":
                if any(target in after_ids for target in target_ids):
                    raise MutagenError(
                        "Native post-check found a terminated session still present."
                    )
            elif any(target not in after_ids for target in target_ids):
                raise MutagenError("Native post-check could not find every selected session.")
        except Exception:
            self.action_planner.finish(
                plan.plan_id,
                verified_target_ids=(),
                outcome="native result or post-check is uncertain; refresh before retrying",
            )
            raise
        self.action_planner.finish(
            plan.plan_id,
            verified_target_ids=target_ids,
            outcome="native exact-ID post-check passed",
        )
        return output

    def prepare_create_plan(
        self,
        area: str,
        options: list[str],
        *,
        backup_choice: str | None = None,
    ) -> ActionPlan:
        if area not in {"sync", "forward"} or len(options) < 2:
            raise MutagenError("A supported create action needs two exact endpoints.")
        arguments = [area, "create", *options]
        if any(
            not isinstance(value, str)
            or not value
            or "\x00" in value
            or value.casefold() in {"--all", "--all=true"}
            for value in arguments
        ):
            raise MutagenError("Create preview contains an invalid or broad argument.")
        if area == "forward":
            self._verify_forward_socket_options(options)
        action_key = _create_action_key(area, options)
        digest = hashlib.sha256(
            json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        target = f"create:{digest}"
        return self.action_planner.prepare(
            ActionRequest(
                action=action_key,
                target_ids=(target,),
                argv=tuple(arguments),
                preflight_fingerprint=digest,
                capabilities=(action_key, "forward_create")
                if action_key == "forward_socket_overwrite"
                else (action_key,),
                backup_choice=backup_choice,
            )
        )

    def _verify_forward_socket_options(self, options: list[str]) -> None:
        requested: set[str] = set()
        for option in options:
            if not option.startswith("--socket-"):
                continue
            flag, separator, value = option.partition("=")
            if flag not in _FORWARD_SOCKET_FLAGS:
                raise MutagenError(f"Unrecognized forwarding socket option: {flag}")
            if not separator or not value.strip() or any(char in value for char in "\r\n\x00"):
                raise MutagenError(f"Invalid value for forwarding socket option: {flag}")
            requested.add(flag)
        if not requested:
            return
        try:
            help_text = self.command(["forward", "create", "--help"], timeout=5, readonly=True)
        except MutagenError as exc:
            raise MutagenError(
                "Could not verify forwarding socket options against the installed Mutagen CLI; "
                "creation is blocked."
            ) from exc
        supported = set(_FORWARD_SOCKET_HELP_FLAG.findall(help_text))
        unsupported = sorted(requested - supported)
        if unsupported:
            raise MutagenError(
                "Forwarding socket options are not supported by the installed Mutagen: "
                + ", ".join(unsupported)
            )

    def consent_action_plan(
        self,
        plan: ActionPlan,
        *,
        consent: bool,
        typed_confirmation: str | None = None,
        backup_choice: str | None = None,
    ) -> ActionPlan:
        try:
            return self.action_planner.consent(
                plan.plan_id,
                consent=consent,
                current_preflight_fingerprint=plan.preflight_fingerprint,
                typed_confirmation=typed_confirmation,
                backup_choice=backup_choice,
            )
        except ActionPlanningError:
            self.action_planner.cancel(plan.plan_id)
            raise

    def _execute_planned_create(
        self,
        arguments: list[str],
        plan: ActionPlan | None,
        *,
        operator_consent: bool,
        timeout: int,
    ) -> str:
        self.last_created_session = None
        if not operator_consent or plan is None or plan.state != "consented":
            raise MutagenError("A consented create ActionPlan is required.")
        # Recompute the deterministic plan identity without creating a second lock.
        digest = hashlib.sha256(
            json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        action_key = _create_action_key(arguments[0], arguments[2:])
        if (
            plan.action != action_key
            or plan.argv != tuple(arguments)
            or plan.preflight_fingerprint != digest
            or plan.target_ids != (f"create:{digest}",)
        ):
            self.action_planner.cancel(plan.plan_id)
            raise MutagenError("Create arguments do not match the consented ActionPlan.")
        try:
            before = self.list_sessions(arguments[0])
        except Exception:
            self.action_planner.cancel(plan.plan_id)
            raise
        before_ids = {str(item.get("identifier") or "") for item in before}
        try:
            output = self.command(arguments, timeout=timeout)
            after = self.list_sessions(arguments[0])
        except Exception:
            self.action_planner.finish(
                plan.plan_id,
                verified_target_ids=(),
                outcome="create outcome unknown; refresh native sessions before retrying",
            )
            raise
        created = [item for item in after if str(item.get("identifier") or "") not in before_ids]
        requested_name = next(
            (value.removeprefix("--name=") for value in arguments if value.startswith("--name=")),
            None,
        )
        if requested_name is not None:
            created = [item for item in created if item.get("name") == requested_name]
        if (
            len(created) != 1
            or not isinstance(created[0].get("identifier"), str)
            or not created[0].get("identifier")
        ):
            self.action_planner.finish(
                plan.plan_id,
                verified_target_ids=(),
                outcome="could not identify exactly one created session by native ID",
            )
            raise MutagenError(
                "Create completed, but the new exact session ID could not be verified."
            )
        created_identifier = str(created[0]["identifier"])
        self.action_planner.finish(
            plan.plan_id,
            verified_target_ids=plan.target_ids,
            outcome=f"native post-check identified new session {created_identifier}",
        )
        self.last_created_session = (arguments[0], created_identifier, tuple(arguments))
        return output

    def command(
        self,
        args: list[str],
        *,
        timeout: int = 35,
        readonly: bool = False,
        env_overrides: dict[str, str] | None = None,
    ) -> str:
        if not self.binary:
            raise MutagenError("mutagen.exe was not found. Please select it in Settings.")
        # PATH lookup may have been reconfigured; never use a shell command string.
        if not os.path.isfile(self.binary) and not shutil.which(self.binary):
            raise MutagenError(f"Mutagen executable not found: {self.binary}")
        env = os.environ.copy()
        if readonly:
            env["MUTAGEN_DISABLE_AUTOSTART"] = "1"
        if env_overrides:
            if set(env_overrides) != {"MUTAGEN_DATA_DIRECTORY"}:
                raise MutagenError("Unsupported Mutagen environment override.")
            data_directory = env_overrides["MUTAGEN_DATA_DIRECTORY"]
            if not os.path.isabs(data_directory):
                raise MutagenError("Mutagen data directory must be an absolute path.")
            env["MUTAGEN_DATA_DIRECTORY"] = data_directory
        env["NO_COLOR"] = "1"
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            result = subprocess.run(
                [self.binary, *args],
                capture_output=True,
                text=True,
                errors="replace",
                stdin=subprocess.DEVNULL,
                env=env,
                timeout=timeout,
                creationflags=creationflags,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MutagenCommandTimeout(
                f"Command timed out after {timeout} s. Check your connection and SSH authentication."
            ) from exc
        except OSError as exc:
            raise MutagenLaunchError(f"Failed to launch Mutagen: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout or f"Exit code: {result.returncode}").strip()
            raise MutagenCommandError(detail[:1600])
        return (result.stdout or "").strip()

    def list_sessions(self, kind: str) -> list[dict]:
        if kind not in ("sync", "forward"):
            raise ValueError("Unknown session type")
        return parse_sessions(
            self.command([kind, "list", "--template", "{{ json . }}"], timeout=12, readonly=True)
        )

    def execute(
        self,
        area: str,
        action: str,
        target: str = "",
        options: list[str] | None = None,
        *,
        operator_consent: bool = False,
        expected_preflight_fingerprint: str = "",
        action_plan: ActionPlan | None = None,
    ) -> str:
        allowed = {
            "daemon": {"start", "stop", "register", "unregister"},
            "sync": {"create", "pause", "resume", "flush", "reset", "terminate"},
            "forward": {"create", "pause", "resume", "terminate"},
        }
        if action not in allowed.get(area, set()):
            raise MutagenError("Invalid command.")
        if area == "daemon" and (target or options):
            raise MutagenError("Daemon actions do not accept session targets or options.")
        arguments = [area, action]
        if action == "create":
            if not options or len(options) < 2:
                raise MutagenError("Two endpoints are required to create a session.")
            arguments += options
        elif area in ("sync", "forward") and not target:
            raise MutagenError(
                "You must select a specific session; bulk operations are not allowed."
            )
        elif target:
            # Accept only explicit identifier from session list, not raw CLI flags.
            if target.startswith("-"):
                raise MutagenError("Invalid session identifier.")
            arguments.append(target)
        timeout = 120 if action in {"create", "flush", "reset"} else 40
        if area in {"sync", "forward"} and action != "create":
            return self._planned_session_action(
                area,
                action,
                [target],
                arguments,
                expected_fingerprint=expected_preflight_fingerprint,
                operator_consent=operator_consent,
                timeout=timeout,
            )
        if area == "daemon":
            return self._execute_planned_daemon(
                action,
                action_plan,
                operator_consent=operator_consent,
                timeout=timeout,
            )
        if not operator_consent:
            raise MutagenError("An explicit operator confirmation is required for this action.")
        return self._execute_planned_create(
            arguments,
            action_plan,
            operator_consent=operator_consent,
            timeout=timeout,
        )

    def execute_many(
        self,
        area: str,
        action: str,
        targets: list[str],
        *,
        operator_consent: bool = False,
        expected_preflight_fingerprint: str = "",
    ) -> str:
        """Run an explicit bulk selection. Never use --all or shell expansion.

        The application itself confirms the scope before calling this method.
        """
        allowed = {
            "sync": {"pause", "resume", "flush", "reset", "terminate"},
            "forward": {"pause", "resume", "terminate"},
        }
        if action not in allowed.get(area, set()):
            raise MutagenError("Bulk action is not allowed.")
        if not targets or len(targets) > 500:
            raise MutagenError("Select between 1 and 500 specific sessions.")
        if any(
            not isinstance(t, str)
            or not t.strip()
            or t.startswith("-")
            or any(c.isspace() for c in t)
            for t in targets
        ):
            raise MutagenError("Invalid session identifier.")
        unique = list(dict.fromkeys(targets))
        args = [area, action]
        if area == "sync" and action == "flush":
            # Force a cycle without holding the GUI action queue until every
            # remote endpoint finishes synchronizing.
            args.append("--skip-wait")
        args.extend(unique)
        return self._planned_session_action(
            area,
            action,
            unique,
            args,
            expected_fingerprint=expected_preflight_fingerprint,
            operator_consent=operator_consent,
            timeout=120 if action in ("reset", "flush") else 60,
        )

    def get_version(self) -> str:
        return self.command(["version"], timeout=8, readonly=True)


class ProcessSampler:
    """Aggregate local Mutagen CPU/RAM and disk activity (never per-session).

    Disk counters measure process I/O reported by the OS, not necessarily
    physical disk throughput. CPU percentage can exceed 100 on multi-core PCs.
    """

    def __init__(self):
        self._previous: dict[int, tuple[float, float, float, int, int]] = {}
        self.last_processes: list[dict] = []
        self._gui_process = psutil.Process(os.getpid())

    def sample_detailed(self) -> dict[str, float | int]:
        import time

        now = time.monotonic()
        current: dict[int, tuple[float, float, float, int, int]] = {}
        cpu = read_rate = write_rate = 0.0
        rss = count = 0
        details = []
        # Asking the OS for RSS of *every* running process is expensive on Windows.
        # Read only names first, then query memory for actual Mutagen matches.
        for process in psutil.process_iter(["pid", "name"]):
            try:
                name = (process.info.get("name") or "").lower()
                if name not in {"mutagen.exe", "mutagen", "mutagen-agent.exe", "mutagen-agent"}:
                    continue
                identity = float(process.create_time())
                times = process.cpu_times()
                total_cpu = times.user + times.system
                try:
                    io = process.io_counters()
                    read_bytes = int(io.read_bytes)
                    write_bytes = int(io.write_bytes)
                except (AttributeError, OSError, psutil.Error):
                    read_bytes = write_bytes = 0
                previous_cpu = previous_read = previous_write = 0.0
                prev = self._previous.get(process.pid)
                if prev and prev[0] == identity and now > prev[1]:
                    elapsed = now - prev[1]
                    previous_cpu = max(0, (total_cpu - prev[2]) / elapsed * 100)
                    cpu += previous_cpu
                    if read_bytes >= prev[3]:
                        previous_read = (read_bytes - prev[3]) / elapsed
                        read_rate += previous_read
                    if write_bytes >= prev[4]:
                        previous_write = (write_bytes - prev[4]) / elapsed
                        write_rate += previous_write
                current[process.pid] = (identity, now, total_cpu, read_bytes, write_bytes)
                count += 1
                memory_info = process.info.get("memory_info")
                if memory_info is None:
                    try:
                        memory_info = process.memory_info()
                    except (AttributeError, psutil.Error, OSError):
                        memory_info = None
                proc_memory = int(memory_info.rss) if memory_info else 0
                rss += proc_memory
                details.append(
                    {
                        "pid": process.pid,
                        "name": name,
                        "cpu": previous_cpu,
                        "memory": proc_memory,
                        "read_rate": previous_read,
                        "write_rate": previous_write,
                    }
                )
            except (psutil.Error, OSError, KeyError, TypeError):
                continue
        self._previous = current
        self.last_processes = sorted(details, key=lambda v: v["cpu"], reverse=True)
        # Measure GUI overhead separately, without a second sampler or timer.
        try:
            gui_cpu = float(self._gui_process.cpu_percent(interval=None))
            gui_memory = int(self._gui_process.memory_info().rss)
        except (psutil.Error, OSError):
            gui_cpu, gui_memory = 0.0, 0
        return {
            "cpu": round(cpu, 2),
            "memory": rss,
            "processes": count,
            "read_rate": round(read_rate, 2),
            "write_rate": round(write_rate, 2),
            "gui_cpu": gui_cpu,
            "gui_memory": gui_memory,
        }

    def sample(self) -> tuple[float, int, int]:
        metrics = self.sample_detailed()
        return float(metrics["cpu"]), int(metrics["memory"]), int(metrics["processes"])


def example_snapshot() -> Snapshot:
    return Snapshot(
        binary=r"C:\Program Files\Mutagen\mutagen.exe",
        daemon=True,
        cpu=4.8,
        memory=126_877_696,
        processes=2,
        version="Mutagen version 0.18.1 (demo data)",
        sync=[
            dict(
                identifier="sync_demo_alpha",
                name="web-project",
                alpha=dict(
                    protocol=0,
                    path=r"C:\Projects\website",
                    connected=True,
                    files=12486,
                    directories=1380,
                    totalFileSize=482344112,
                ),
                beta=dict(
                    protocol=1,
                    host="dev.example.com",
                    user="deploy",
                    path="/var/www/app",
                    connected=True,
                    files=12486,
                ),
                paused=False,
                status=6,
                successfulCycles=1324,
            ),
            dict(
                identifier="sync_demo_beta",
                name="docker-api",
                alpha=dict(protocol=0, path=r"C:\Projects\backend", connected=True, files=3840),
                beta=dict(protocol=11, host="api", path="/app", connected=True),
                paused=False,
                status=11,
                successfulCycles=849,
            ),
            dict(
                identifier="sync_demo_gamma",
                name="assets-backup",
                alpha=dict(protocol=0, path=r"D:\Assets", connected=False),
                beta=dict(
                    protocol=1, host="storage.example.com", path="/srv/assets", connected=False
                ),
                paused=True,
                status=0,
            ),
        ],
        forward=[
            dict(
                identifier="fwrd_demo",
                name="database-tunnel",
                source=dict(protocol=0, endpoint="tcp:localhost:5432", connected=True),
                destination=dict(
                    protocol=1, host="db.example.com", endpoint="tcp:localhost:5432", connected=True
                ),
                paused=False,
                status=3,
                openConnections=2,
                totalConnections=118,
                totalOutboundData=1024000,
                totalInboundData=45126400,
            )
        ],
    )
