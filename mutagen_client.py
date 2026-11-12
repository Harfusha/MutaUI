"""Mutagen CLI adapter. No shell, no hidden destructive commands."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

SYNC_STATUS = {
    0: "Odpojeno", 1: "Zastaveno: prázdný kořen", 2: "Zastaveno: smazaný kořen",
    3: "Zastaveno: změna typu kořene", 4: "Připojování ALPHA",
    5: "Připojování BETA", 6: "Sleduje změny", 7: "Skenování",
    8: "Čeká na opakování", 9: "Porovnávání", 10: "Přenos do ALPHA",
    11: "Přenos do BETA", 12: "Zapisování změn", 13: "Ukládání",
}
FORWARD_STATUS = {0: "Odpojeno", 1: "Připojování zdroje", 2: "Připojování cíle", 3: "Přesměrování běží"}


def native_sync_startup_state(session: dict, daemon_registration: str) -> str:
    """State under Mutagen's own persistent pause + Windows daemon registration.

    There is no separate per-session auto-run flag in Mutagen.
    """
    if session.get("paused"):
        return "paused"
    return "enabled" if daemon_registration == "registered" else "needs-registration"


class MutagenError(RuntimeError):
    pass


def clean_executable(path: str) -> str:
    path = path.strip().strip('"')
    if not path:
        found = shutil.which("mutagen") or shutil.which("mutagen.exe")
        return found or ""
    expanded = os.path.expandvars(os.path.expanduser(path))
    if os.path.isfile(expanded):
        return expanded
    found = shutil.which(expanded)
    return found or ""


def parse_sessions(output: str) -> list[dict]:
    """JSON Go-template output; returns [] for an empty daemon."""
    try:
        payload = json.loads(output.strip())
    except json.JSONDecodeError as exc:
        raise MutagenError("Mutagen nevrátil platný JSON. Zkontrolujte verzi Mutagenu a podporu --template.") from exc
    if not isinstance(payload, list):
        raise MutagenError("Neočekávaná datová struktura v odpovědi Mutagenu.")
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
        return "paused", "Pozastaveno"
    endpoints = (session.get("alpha") or {}, session.get("beta") or {})
    has_problems = any(endpoint.get(key) for endpoint in endpoints for key in
                       ("scanProblems", "transitionProblems", "excludedScanProblems", "excludedTransitionProblems"))
    if session.get("lastError") or (kind == "sync" and
        (session.get("conflicts") or session.get("excludedConflicts") or has_problems)):
        return "error", "Vyžaduje pozornost"
    raw = session.get("status", 0)
    try:
        status = int(raw)
    except (ValueError, TypeError):
        status = -1
    if kind == "sync":
        text = SYNC_STATUS.get(status, str(raw))
        if status in (1, 2, 3, 8):
            return "error", text
        return ("active" if status == 6 else "busy" if status in (4, 5, 7, 9, 10, 11, 12, 13) else "idle", text)
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
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(number) < 1024 or unit == "TB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return "—"


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
    version: str = ""
    registration: str = "unknown"
    registration_command: str = ""


def read_registration(binary: str) -> tuple[str, str]:
    r"""Official Windows daemon registration lives in HKCU\...\Run\Mutagen.

    No registry modifications are done here.
    """
    if sys.platform != "win32":
        return "unsupported", ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
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
    def __init__(self, binary: str = ""):
        self.binary = clean_executable(binary)

    def command(self, args: list[str], *, timeout: int = 35, readonly: bool = False) -> str:
        if not self.binary:
            raise MutagenError("Soubor mutagen.exe nebyl nalezen. Vyberte ho v Nastavení.")
        # PATH lookup may have been reconfigured; never use a shell command string.
        if not os.path.isfile(self.binary) and not shutil.which(self.binary):
            raise MutagenError(f"Soubor Mutagenu neexistuje: {self.binary}")
        env = os.environ.copy()
        if readonly:
            env["MUTAGEN_DISABLE_AUTOSTART"] = "1"
        env["NO_COLOR"] = "1"
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            result = subprocess.run(
                [self.binary, *args], capture_output=True, text=True, errors="replace",
                stdin=subprocess.DEVNULL, env=env, timeout=timeout,
                creationflags=creationflags, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MutagenError(f"Příkaz překročil limit {timeout} s. Zkontrolujte připojení a SSH ověřování.") from exc
        except OSError as exc:
            raise MutagenError(f"Nepodařilo se spustit Mutagen: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout or f"Kód chyby: {result.returncode}").strip()
            raise MutagenError(detail[:1600])
        return (result.stdout or "").strip()

    def list_sessions(self, kind: str) -> list[dict]:
        if kind not in ("sync", "forward"):
            raise ValueError("Neznámý typ relace")
        return parse_sessions(self.command([kind, "list", "--template", "{{ json . }}"], timeout=12, readonly=True))

    def execute(self, area: str, action: str, target: str = "", options: list[str] | None = None) -> str:
        allowed = {
            "daemon": {"start", "stop", "register", "unregister"},
            "sync": {"create", "pause", "resume", "flush", "reset", "terminate"},
            "forward": {"create", "pause", "resume", "terminate"},
        }
        if action not in allowed.get(area, set()):
            raise MutagenError("Neplatný příkaz.")
        arguments = [area, action]
        if action == "create":
            if not options or len(options) < 2:
                raise MutagenError("Pro vytvoření relace jsou nutné dva koncové body.")
            arguments += options
        elif area in ("sync", "forward") and not target:
            raise MutagenError("Musíte vybrat konkrétní relaci; hromadné operace nejsou povolené.")
        elif target:
            # Accept only explicit identifier from session list, not raw CLI flags.
            if target.startswith("-"):
                raise MutagenError("Neplatný identifikátor relace.")
            arguments.append(target)
        return self.command(arguments, timeout=120 if action in {"create", "flush", "reset"} else 40)

    def execute_many(self, area: str, action: str, targets: list[str]) -> str:
        """Run an explicit bulk selection. Never use --all or shell expansion.

        The application itself confirms the scope before calling this method.
        """
        allowed = {"sync": {"pause", "resume", "flush", "reset", "terminate"},
                   "forward": {"pause", "resume", "terminate"}}
        if action not in allowed.get(area, set()):
            raise MutagenError("Hromadná akce není povolená.")
        if not targets or len(targets) > 500:
            raise MutagenError("Vyberte 1 až 500 konkrétních relací.")
        if any(not isinstance(t, str) or not t.strip() or t.startswith("-") or
               any(c.isspace() for c in t) for t in targets):
            raise MutagenError("Neplatný identifikátor relace.")
        unique = list(dict.fromkeys(targets))
        args = [area, action]
        if area == "sync" and action == "flush":
            # Force a cycle without holding the GUI action queue until every
            # remote endpoint finishes synchronizing.
            args.append("--skip-wait")
        args.extend(unique)
        return self.command(args, timeout=120 if action in ("reset", "flush") else 60)

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
                details.append({"pid": process.pid, "name": name, "cpu": previous_cpu,
                                "memory": proc_memory, "read_rate": previous_read,
                                "write_rate": previous_write})
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
        return {"cpu": round(cpu, 2), "memory": rss, "processes": count,
                "read_rate": round(read_rate, 2), "write_rate": round(write_rate, 2),
                "gui_cpu": gui_cpu, "gui_memory": gui_memory}

    def sample(self) -> tuple[float, int, int]:
        metrics = self.sample_detailed()
        return float(metrics["cpu"]), int(metrics["memory"]), int(metrics["processes"])


def example_snapshot() -> Snapshot:
    return Snapshot(
        binary=r"C:\Program Files\Mutagen\mutagen.exe", daemon=True, cpu=4.8, memory=126_877_696,
        processes=2, version="Mutagen version 0.18.1 (ukázková data)",
        sync=[
            dict(identifier="sync_demo_alpha", name="web-project", alpha=dict(protocol=0, path=r"C:\Projects\website", connected=True, files=12486, directories=1380, totalFileSize=482344112), beta=dict(protocol=1, host="dev.example.com", user="deploy", path="/var/www/app", connected=True, files=12486), paused=False, status=6, successfulCycles=1324),
            dict(identifier="sync_demo_beta", name="docker-api", alpha=dict(protocol=0, path=r"C:\Projects\backend", connected=True, files=3840), beta=dict(protocol=11, host="api", path="/app", connected=True), paused=False, status=11, successfulCycles=849),
            dict(identifier="sync_demo_gamma", name="assets-backup", alpha=dict(protocol=0, path=r"D:\Assets", connected=False), beta=dict(protocol=1, host="storage.example.com", path="/srv/assets", connected=False), paused=True, status=0),
        ],
        forward=[dict(identifier="fwrd_demo", name="database-tunnel", source=dict(protocol=0, endpoint="tcp:localhost:5432", connected=True), destination=dict(protocol=1, host="db.example.com", endpoint="tcp:localhost:5432", connected=True), paused=False, status=3, openConnections=2, totalConnections=118, totalOutboundData=1024000, totalInboundData=45126400)],
    )
