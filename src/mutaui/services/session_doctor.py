"""Deterministic, offline diagnosis for typed Mutagen snapshots."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from mutaui.domain.models import DiagnosticIssue, SessionSnapshot

FRESHNESS_SECONDS = 60
HIGH_CPU_PERCENT = 90.0
SYNC_HELP = "https://mutagen.io/documentation/synchronization/"
FORWARD_HELP = "https://mutagen.io/documentation/forwarding/"
DAEMON_HELP = "https://mutagen.io/documentation/introduction/daemon/"


@dataclass(frozen=True, slots=True)
class SessionDoctorContext:
    cli_available: bool
    daemon_running: bool | None
    sync_observed_at: datetime | None
    forward_observed_at: datetime | None
    sessions: tuple[SessionSnapshot, ...] = ()
    version: str | None = None
    snapshot_error: str = ""
    sessions_stale: bool = False
    cpu_percent: float | None = None
    resource_observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SessionDoctorReport:
    issues: tuple[DiagnosticIssue, ...]
    authoritative: bool
    generated_at: datetime
    session_count: int
    stale_kinds: tuple[str, ...]

    @property
    def issue_count(self) -> int:
        return len(self.issues)


def _recent(value: datetime | None, now: datetime, max_age: int) -> bool:
    if value is None:
        return False
    age = (now - value).total_seconds()
    return 0 <= age <= max_age


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    return 0


def _text(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(f"{key}: {item}" for key, item in value.items())[:1000]
    return str(value)[:1000]


def _error_code(text: str, *, kind: str, endpoint_name: str = "") -> str | None:
    value = text.casefold()
    if any(term in value for term in ("authentication failed", "unauthorized", "publickey")) or (
        "permission denied" in value and ("ssh" in value or kind == "ssh")
    ):
        return "ssh_authentication"
    if any(
        term in value
        for term in (
            "remote host identification has changed",
            "host key verification failed",
            "offending key",
        )
    ):
        return "ssh_host_key_changed"
    if any(term in value for term in ("unknown host", "no such host", "host key", "known_hosts")):
        return "ssh_host_trust"
    if any(
        term in value
        for term in (
            "used by another process",
            "sharing violation",
            "lock violation",
            "cannot access the file because it is being used",
            "being used by another process",
        )
    ):
        return "file_locked"
    if any(term in value for term in ("inotify", "user limit of inotify", "too many open files")):
        return "inotify_limit"
    if kind != "forward" and any(
        term in value
        for term in (
            "connection refused",
            "connect: connection refused",
            "refused by host",
        )
    ):
        return "ssh_connection_refused"
    if kind != "forward" and any(
        term in value
        for term in (
            "connection timed out",
            "operation timed out",
            "timed out waiting",
            "network is unreachable",
            "no route to host",
            "i/o timeout",
        )
    ):
        return "ssh_timeout"
    if any(
        term in value
        for term in (
            "root is missing",
            "root missing",
            "root is empty",
            "root changed type",
            "deleted root",
            "halted: empty root",
            "halted: root type change",
        )
    ):
        return "root_problem"
    if any(
        term in value
        for term in (
            "no such file or directory",
            "cannot find the path specified",
            "directory does not exist",
            "path does not exist",
            "path not found",
        )
    ):
        return "path_not_found"
    if any(
        term in value
        for term in (
            "unable to install agent",
            "exec format error",
            "cannot execute binary file",
            "agent executable failed",
            "agent version mismatch",
        )
    ):
        return "agent_incompatible"
    if any(
        term in value
        for term in (
            "illegal characters in path",
            "syntax is incorrect",
            "invalid filename characters",
        )
    ):
        return "filename_invalid"
    if any(
        term in value for term in ("case-insensitivity conflict", "case clash", "case conflict")
    ):
        return "case_conflict"
    if "symlink" in value:
        return "symlink_problem"
    if any(term in value for term in ("permission", "ownership", "operation not permitted")):
        return "permission_problem"
    if any(
        term in value
        for term in (
            "no space left",
            "disk full",
            "out of space",
            "not enough space",
        )
    ):
        return "disk_space"
    if any(
        term in value
        for term in (
            "address already in use",
            "port already in use",
            "bind: address already in use",
            "failed to bind",
            "cannot bind",
        )
    ):
        return "socket_bind"
    if any(term in value for term in ("stage", "staging", "temporary directory")):
        return "staging_problem"
    if "transition" in value:
        return "transition_problem"
    if "scan" in value:
        return "scan_problem"
    if kind == "forward" and endpoint_name and value.strip():
        return (
            "forward_source_problem" if endpoint_name == "source" else "forward_destination_problem"
        )
    return None


def _issue_copy(code: str) -> tuple[str, str, str]:
    copy = {
        "cli_missing": (
            "Mutagen CLI is unavailable.",
            "Choose or install the supported Mutagen CLI, then refresh.",
            DAEMON_HELP,
        ),
        "daemon_offline": (
            "The local Mutagen daemon did not answer.",
            "Check the Mutagen installation and daemon status. MutaUI did not start it.",
            DAEMON_HELP,
        ),
        "snapshot_stale": (
            "Current session state is unknown because no recent complete snapshot is available.",
            "Refresh Mutagen status before acting on session details.",
            DAEMON_HELP,
        ),
        "ssh_authentication": (
            "Mutagen reports an SSH authentication or permission failure.",
            "Check the selected SSH identity and remote account permissions.",
            SYNC_HELP,
        ),
        "ssh_host_trust": (
            "Mutagen reports a host or host-key resolution problem.",
            "Verify the host name and review the host key through OpenSSH.",
            SYNC_HELP,
        ),
        "ssh_disconnected": (
            "A sync endpoint is disconnected.",
            "Inspect the endpoint and its latest Mutagen error.",
            SYNC_HELP,
        ),
        "root_problem": (
            "A synchronization root may be missing, empty, or a different file type.",
            "Check both roots and confirm that each still points to the intended directory.",
            SYNC_HELP,
        ),
        "scan_problem": (
            "Mutagen reported a filesystem scan problem.",
            "Inspect the scan evidence and the affected filesystem path.",
            SYNC_HELP,
        ),
        "transition_problem": (
            "Mutagen reported a file transition problem.",
            "Inspect the transition evidence before changing files or configuration.",
            SYNC_HELP,
        ),
        "conflicts": (
            "Mutagen reports file conflicts, including excluded conflicts.",
            "Review conflict details before choosing any resolution.",
            SYNC_HELP,
        ),
        "permission_problem": (
            "Mutagen reported a permissions or ownership problem.",
            "Check access on the affected endpoint; do not change permissions automatically.",
            SYNC_HELP,
        ),
        "symlink_problem": (
            "Mutagen reported a symbolic-link problem.",
            "Review the link target and the configured symbolic-link mode.",
            SYNC_HELP,
        ),
        "staging_problem": (
            "Mutagen reported a file-staging problem.",
            "Check free space and staging configuration on the affected endpoint.",
            SYNC_HELP,
        ),
        "disk_space": (
            "Endpoint filesystem is out of disk space.",
            "Free up disk space on the affected volume before resuming sync.",
            SYNC_HELP,
        ),
        "socket_bind": (
            "Network port or socket could not be bound.",
            "Check for conflicting services or port reservations.",
            FORWARD_HELP,
        ),
        "forward_source_problem": (
            "The forwarding source could not bind or connect.",
            "Check the local source address, port, and socket availability.",
            FORWARD_HELP,
        ),
        "forward_destination_problem": (
            "The forwarding destination could not connect.",
            "Check the destination endpoint and remote service availability.",
            FORWARD_HELP,
        ),
        "file_locked": (
            "A file is locked by another running program or process.",
            "Close the program locking the file or add an ignore pattern for temporary/lock files.",
            SYNC_HELP,
        ),
        "inotify_limit": (
            "Linux inotify file watch limit reached for this session.",
            "Increase fs.inotify.max_user_watches sysctl limit or add heavy directories to ignore rules.",
            SYNC_HELP,
        ),
        "ssh_host_key_changed": (
            "SSH host key verification failed because the remote host key has changed.",
            "Verify remote host identity and update known_hosts (ssh-keygen -R <host>).",
            SYNC_HELP,
        ),
        "ssh_connection_refused": (
            "Remote SSH server refused the connection on the configured port.",
            "Check that sshd is running on the remote host and port 22 is open in firewall.",
            SYNC_HELP,
        ),
        "ssh_timeout": (
            "Network connection to the remote endpoint timed out.",
            "Verify network connectivity, remote host IP address, and firewall routing.",
            SYNC_HELP,
        ),
        "path_not_found": (
            "A local or remote synchronization directory does not exist or was deleted.",
            "Verify that the path exists on both machines, or create the missing target folder.",
            SYNC_HELP,
        ),
        "agent_incompatible": (
            "Mutagen remote agent binary cannot be executed on the target host.",
            "Check remote CPU architecture, ensure /tmp is not mounted with noexec, or install mutagen on remote host.",
            SYNC_HELP,
        ),
        "filename_invalid": (
            "A filename contains characters or syntax not supported by this filesystem.",
            'Rename the affected files to avoid characters unsupported by Windows (e.g. : * ? " < > |).',
            SYNC_HELP,
        ),
        "case_conflict": (
            "Two files differ only in uppercase/lowercase on a case-insensitive filesystem.",
            "Rename one of the conflicting files to a distinct name.",
            SYNC_HELP,
        ),
        "session_error": (
            "Mutagen reports a session error.",
            "Inspect the session's native error and endpoint details.",
            SYNC_HELP,
        ),
        "intentional_pause": (
            "This session is intentionally paused.",
            "Resume only if you want Mutagen to continue the session.",
            SYNC_HELP,
        ),
        "manual_mode": (
            "This session uses manual synchronization mode.",
            "Manual synchronization is intentional and is not an error.",
            SYNC_HELP,
        ),
        "high_cpu": (
            "Recent Mutagen process CPU measurement is high.",
            "Compare with active scans and synchronization before changing settings.",
            SYNC_HELP,
        ),
    }
    return copy.get(
        code, ("Mutagen reported a session issue.", "Review the native evidence.", SYNC_HELP)
    )


@dataclass(frozen=True, slots=True)
class DiagnosticRemedy:
    code: str
    title: str
    explanation: str
    remedy_steps: tuple[str, ...]
    quick_command: str = ""
    article_url: str = SYNC_HELP
    category: str = "general"


def _extract_host_from_detail(detail: str) -> str:
    match = re.search(r"host\s+([a-zA-Z0-9.\-_]+)", detail, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"ssh://(?:[^@]+@)?([a-zA-Z0-9.\-_]+)", detail, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def get_diagnostic_remedy(code: str, language: str = "en", *, detail: str = "") -> DiagnosticRemedy:
    czech = language.casefold().startswith("cs")
    host = _extract_host_from_detail(detail)

    remedies: dict[str, dict[str, Any]] = {
        "file_locked": {
            "title_en": "Locked File on Endpoint",
            "title_cs": "Uzamčený soubor v systému",
            "expl_en": "A file cannot be synchronized because another application or process has locked it.",
            "expl_cs": "Soubor nelze synchronizovat, protože jej uzamkl jiný spuštěný proces nebo program.",
            "steps_en": (
                "Identify and close the program currently accessing or editing the file.",
                "If the file is a temporary lock or cache (e.g. .lock, .tmp, node_modules), add it to session ignore rules.",
                "Click 'Refresh Status' once the file is unlocked to resume synchronization.",
            ),
            "steps_cs": (
                "Najděte a ukončete program, který soubor drží nebo upravuje.",
                "Pokud jde o dočasný soubor (např. .lock, cache nebo .tmp), přidejte jej do ignorovaných vzorů relace.",
                "Po uvolnění souboru klikněte na 'Zkontrolovat stav' pro obnovení synchronizace.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "inotify_limit": {
            "title_en": "Linux inotify Watch Limit Reached",
            "title_cs": "Dosažen limit inotify sledování",
            "expl_en": "The operating system cannot allocate more file system watchers for real-time synchronization.",
            "expl_cs": "Operační systém nemůže přidělit další sledovače změn souborů pro sledování v reálném čase.",
            "steps_en": (
                "Increase the inotify watches limit: sudo sysctl -w fs.inotify.max_user_watches=524288",
                "To make it permanent, add 'fs.inotify.max_user_watches=524288' to /etc/sysctl.conf",
                "Exclude large generated directories (like node_modules, build, .git) in session ignore settings.",
            ),
            "steps_cs": (
                "Zvyšte limit inotify sledovačů spuštěním: sudo sysctl -w fs.inotify.max_user_watches=524288",
                "Pro trvalé nastavení přidejte 'fs.inotify.max_user_watches=524288' do souboru /etc/sysctl.conf",
                "V nastavení relace přidejte do ignorovaných složek rozsáhlé generované adresáře (jako node_modules, build).",
            ),
            "command": "sudo sysctl -w fs.inotify.max_user_watches=524288",
            "url": SYNC_HELP,
            "category": "system",
        },
        "ssh_host_key_changed": {
            "title_en": "Remote SSH Host Key Changed",
            "title_cs": "Změnil se SSH klíč vzdáleného serveru",
            "expl_en": "The remote host's identification key differs from the one saved in your known_hosts file.",
            "expl_cs": "Hostitelský klíč serveru se neshoduje s klíčem uloženým ve vašem souboru known_hosts.",
            "steps_en": (
                "Verify that the remote server was legitimately reinstalled or changed IP/keys.",
                f"Remove the outdated key from your known_hosts: ssh-keygen -R {host or '<hostname>'}",
                f"Connect once via terminal 'ssh {host or '<hostname>'}' to verify and accept the new trusted fingerprint.",
            ),
            "steps_cs": (
                "Ověřte, zda byl vzdálený server přeinstalován nebo zda legitimně došlo ke změně klíčů.",
                f"Odstraňte starý klíč ze souboru known_hosts příkazem: ssh-keygen -R {host or '<host>'}",
                f"Připojte se jednou přes terminál 'ssh {host or '<host>'}' a ověřte a přijměte nový otisk klíče.",
            ),
            "command": f"ssh-keygen -R {host or '<hostname>'}",
            "url": SYNC_HELP,
            "category": "network",
        },
        "ssh_connection_refused": {
            "title_en": "SSH Connection Refused",
            "title_cs": "SSH spojení bylo odmítnuto",
            "expl_en": "The target host actively refused connection on the configured SSH port.",
            "expl_cs": "Cílový počítač aktivně odmítl pokus o připojení na zadaném SSH portu.",
            "steps_en": (
                "Verify that the SSH daemon (sshd) is running on the remote host.",
                "Ensure that firewall or security groups allow incoming traffic on port 22.",
                "Check the hostname or IP address configured in the session.",
            ),
            "steps_cs": (
                "Zkontrolujte, zda na vzdáleném serveru běží SSH služba (sshd).",
                "Ověřte, zda firewall nebo bezpečnostní pravidla nezakazují příchozí spojení na port 22.",
                "Zkontrolujte správnost zadané IP adresy nebo doménového jména hostitele.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "network",
        },
        "ssh_timeout": {
            "title_en": "Network Connection Timed Out",
            "title_cs": "Časový limit síťového spojení vypršel",
            "expl_en": "Mutagen could not establish a network connection to the remote endpoint within the timeout limit.",
            "expl_cs": "Mutagen se nedokázal připojit ke vzdálenému počítači v nastaveném časovém limitu.",
            "steps_en": (
                "Check your local internet and VPN connection.",
                "Verify that the remote machine is powered on and accessible on the network.",
                f"Test reachability using 'ping {host or '<host>'}' or 'ssh -v {host or '<host>'}'",
            ),
            "steps_cs": (
                "Zkontrolujte připojení k internetu a stav případné VPN sítě.",
                "Ověřte, že je cílový počítač zapnutý a dosažitelný v síti.",
                f"Vyzkoušejte spojení pomocí příkazu 'ssh -v {host or '<host>'}'",
            ),
            "command": f"ssh -v {host or '<host>'}" if host else "",
            "url": SYNC_HELP,
            "category": "network",
        },
        "ssh_authentication": {
            "title_en": "SSH Authentication Failed",
            "title_cs": "Chyba ověření SSH přihlášení",
            "expl_en": "Mutagen could not authenticate with the remote SSH server using the configured credentials.",
            "expl_cs": "Mutagenu se nepodařilo přihlásit ke vzdálenému SSH serveru pomocí zadaných údajů.",
            "steps_en": (
                "Check that your SSH private key is loaded or specified in SSH config.",
                "Verify remote account permissions and username.",
                f"Test connection in terminal: ssh {host or '<user>@<host>'}",
            ),
            "steps_cs": (
                "Zkontrolujte, zda máte platný SSH klíč a zda je správně nakonfigurován.",
                "Ověřte oprávnění a správnost uživatelského jména na vzdáleném serveru.",
                f"Vyzkoušejte přihlášení v terminálu: ssh {host or '<uživatel>@<host>'}",
            ),
            "command": f"ssh {host}" if host else "",
            "url": SYNC_HELP,
            "category": "network",
        },
        "ssh_host_trust": {
            "title_en": "Untrusted or Unknown SSH Host",
            "title_cs": "Neznámý nebo nedůvěryhodný SSH hostitel",
            "expl_en": "The remote SSH host is unknown or its key could not be verified in known_hosts.",
            "expl_cs": "Vzdálený SSH hostitel je neznámý nebo jeho klíč nelze ověřit v souboru known_hosts.",
            "steps_en": (
                "Connect once from your terminal to establish trust: ssh <host>",
                "Review the host fingerprint and accept it if it matches your server.",
                "Refresh MutaUI after the host key is recorded.",
            ),
            "steps_cs": (
                "Připojte se jednou z terminálu pro navázání důvěry: ssh <host>",
                "Zkontrolujte otisk klíče a potvrďte jej, pokud odpovídá vašemu serveru.",
                "Po uložení hostitelského klíče aktualizujte stav v MutaUI.",
            ),
            "command": f"ssh {host}" if host else "",
            "url": SYNC_HELP,
            "category": "network",
        },
        "ssh_disconnected": {
            "title_en": "SSH Endpoint Disconnected",
            "title_cs": "SSH koncový bod je odpojen",
            "expl_en": "The remote SSH synchronization endpoint has lost connection.",
            "expl_cs": "Vzdálený SSH koncový bod ztratil spojení.",
            "steps_en": (
                "Check whether the remote host is reachable.",
                "Inspect the endpoint error details below.",
                "Click 'Refresh Status' to trigger reconnection.",
            ),
            "steps_cs": (
                "Zkontrolujte, zda je vzdálený server dostupný.",
                "Prohlédněte si detail chyby koncového bodu níže.",
                "Klikněte na 'Zkontrolovat stav' pro pokus o znovupřipojení.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "network",
        },
        "path_not_found": {
            "title_en": "Sync Directory Not Found",
            "title_cs": "Synchronizovaná složka nenalezena",
            "expl_en": "The configured synchronization root directory does not exist on the local or remote system.",
            "expl_cs": "Zadaná kořenová složka pro synchronizaci na daném počítači neexistuje nebo byla smazána.",
            "steps_en": (
                "Verify that the directory exists at the specified path on both machines.",
                "Create the directory manually if it was newly added or deleted.",
                "Check for path typos or drive letter changes (e.g. external drives on Windows).",
            ),
            "steps_cs": (
                "Zkontrolujte, zda zadaná složka na obou počítačích skutečně existuje.",
                "Pokud byla složka nově přidána nebo smazána, vytvořte ji ručně.",
                "Ověřte správnost cesty a písmena disku (např. u vyměnitelných disků ve Windows).",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "agent_incompatible": {
            "title_en": "Remote Mutagen Agent Incompatible or Blocked",
            "title_cs": "Vzdálený agent Mutagenu nelze spustit",
            "expl_en": "Mutagen could not install or execute its helper agent on the remote machine.",
            "expl_cs": "Mutagenu se nepodařilo nainstalovat nebo spustit pomocného agenta na vzdáleném serveru.",
            "steps_en": (
                "Ensure the remote directory (e.g. /tmp or ~/.mutagen) is not mounted with 'noexec'.",
                "Verify that the remote operating system and CPU architecture are supported.",
                "Check available disk space on the remote machine.",
            ),
            "steps_cs": (
                "Zkontrolujte, zda dočasný adresář na serveru (např. /tmp nebo ~/.mutagen) není připojen s volbou 'noexec'.",
                "Ověřte, že je podporována architektura CPU a verze OS na vzdáleném serveru.",
                "Zkontrolujte dostatek volného místa na disku vzdáleného serveru.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "agent",
        },
        "filename_invalid": {
            "title_en": "Invalid Filename Characters",
            "title_cs": "Neplatné znaky v názvu souboru",
            "expl_en": 'A file name contains characters illegal on this operating system (such as : * ? " < > | on Windows).',
            "expl_cs": 'Název souboru obsahuje znaky nepodporované daným operačním systémem (např. : * ? " < > | ve Windows).',
            "steps_en": (
                "Rename the offending files to use only alphanumeric characters, dashes, and underscores.",
                "If these files are generated by builds or tools, add their directory to ignore rules.",
            ),
            "steps_cs": (
                "Přejmenujte problematické soubory tak, aby neobsahovaly speciální znaky jako dvojtečky či otazníky.",
                "Pokud jde o soubory generované nástroji, přidejte jejich složku do ignorovaných vzorů.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "case_conflict": {
            "title_en": "Case-Sensitivity File Collision",
            "title_cs": "Kolize velikosti písmen v názvu souboru",
            "expl_en": "Two files differ only in uppercase/lowercase (e.g. File.txt and file.txt) on a case-insensitive filesystem.",
            "expl_cs": "Dva soubory se liší pouze velikostí písmen na souborovém systému, který nerozlišuje velikost písmen (Windows / macOS).",
            "steps_en": (
                "Rename one of the colliding files to a distinct name on the source system.",
                "Commit and sync the renamed file before restoring changes.",
            ),
            "steps_cs": (
                "Přejmenujte jeden z kolidujících souborů na zdrojovém systému na odlišný název.",
                "Po přejmenování nechte změnu synchronizovat.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "root_problem": {
            "title_en": "Sync Root Problem",
            "title_cs": "Problém s kořenovou složkou",
            "expl_en": "A synchronization root directory is missing, empty, or has changed type.",
            "expl_cs": "Kořenová složka synchronizace chybí, je prázdná, nebo došlo ke změně jejího typu.",
            "steps_en": (
                "Check that both local and remote root folders exist.",
                "Ensure the path points to a directory, not a regular file.",
                "If the root was moved, update the session root path in settings.",
            ),
            "steps_cs": (
                "Zkontrolujte, že obě kořenové složky (místní i vzdálená) existují.",
                "Ujistěte se, že cesta ukazuje na složku, nikoliv na samostatný soubor.",
                "Pokud byla složka přesunuta, upravte cestu v nastavení relace.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "disk_space": {
            "title_en": "Disk Space Exhausted",
            "title_cs": "Nedostatek místa na disku",
            "expl_en": "The filesystem on the sync endpoint has run out of available free space.",
            "expl_cs": "Na diskovém oddílu koncového bodu došlo volné místo.",
            "steps_en": (
                "Check free disk space on the affected volume.",
                "Clean up temporary files, logs, or unused caches.",
                "Resume synchronization once space is freed.",
            ),
            "steps_cs": (
                "Zkontrolujte volné místo na disku daného počítače.",
                "Uvolněte místo smazáním dočasných souborů nebo mezipaměti.",
                "Po uvolnění místa obnovte synchronizaci.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "system",
        },
        "permission_problem": {
            "title_en": "File Permission Denied",
            "title_cs": "Nedostatečná přístupová oprávnění",
            "expl_en": "Mutagen does not have filesystem permissions to read, write, or create files on this endpoint.",
            "expl_cs": "Mutagen nemá oprávnění k zápisu, čtení nebo vytváření souborů v cílové složce.",
            "steps_en": (
                "Check file and directory ownership and permissions (chmod / chown).",
                "Ensure the user running Mutagen has write access to the target directory.",
                "On Windows, check if the folder is read-only or owned by another user.",
            ),
            "steps_cs": (
                "Zkontrolujte vlastnictví a oprávnění souborů a složek (chmod / chown).",
                "Ujistěte se, že uživatel, pod kterým Mutagen běží, má právo zápisu do dané složky.",
                "Ve Windows zkontrolujte, zda složka není chráněna nebo určena jen pro čtení.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "permission",
        },
        "conflicts": {
            "title_en": "File Synchronization Conflicts",
            "title_cs": "Konflikty synchronizace souborů",
            "expl_en": "Files were modified simultaneously on both endpoints and cannot be merged automatically.",
            "expl_cs": "Soubory byly upraveny současně na obou stranách a nelze je sloučit automaticky.",
            "steps_en": (
                "Open the Conflict Inspector to view all conflicting files.",
                "Choose whether local (Alpha) or remote (Beta) changes should take precedence.",
                "Resolve or merge the affected files.",
            ),
            "steps_cs": (
                "Otevřete Přehled konfliktů (Conflict Inspector) a prohlédněte si seznam.",
                "Zvolte, zda má mít přednost místní (Alpha) nebo vzdálená (Beta) verze.",
                "Sloučte nebo přepište konfliktní soubory.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "conflict",
        },
        "scan_problem": {
            "title_en": "Filesystem Scan Problem",
            "title_cs": "Chyba při skenování souborového systému",
            "expl_en": "Mutagen encountered an error while scanning files and folders on an endpoint.",
            "expl_cs": "Mutagen narazil na chybu při procházení a skenování souborů v koncovém bodě.",
            "steps_en": (
                "Inspect the error message to identify the problematic file or folder.",
                "Check if the file is accessible and has readable permissions.",
                "Add problematic or unreadable directories to session ignore patterns.",
            ),
            "steps_cs": (
                "Prohlédněte si detail chyby a zjistěte, který soubor či složka problém způsobuje.",
                "Zkontrolujte oprávnění a dostupnost daného souboru.",
                "Přidejte problematické složky do ignorovaných vzorů relace.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "symlink_problem": {
            "title_en": "Symbolic Link Problem",
            "title_cs": "Problém se symbolickými odkazy",
            "expl_en": "A symbolic link target cannot be resolved or is not supported by the current symlink mode.",
            "expl_cs": "Cíl symbolického odkazu nelze nalézt nebo není podporován zvoleným režimem symlinků.",
            "steps_en": (
                "Review the symbolic link target path and make sure it points to a valid destination.",
                "In session preferences, change symbolic link mode to 'Portable' or 'Ignore'.",
            ),
            "steps_cs": (
                "Zkontrolujte cíl symbolického odkazu a ujistěte se, že odkazuje na platné místo.",
                "V nastavení relace můžete změnit režim symbolických odkazů na 'Přenosné' (Portable) nebo 'Ignorovat'.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "filesystem",
        },
        "socket_bind": {
            "title_en": "Port or Socket Already in Use",
            "title_cs": "Port nebo socket je již obsazen",
            "expl_en": "The forwarding endpoint cannot bind to the specified local port or socket.",
            "expl_cs": "Koncový bod přesměrování se nemůže navázat na zadaný místní port nebo socket.",
            "steps_en": (
                "Check if another application or background process is already using this port.",
                "Change the forwarding port in session configuration to an unused port number.",
            ),
            "steps_cs": (
                "Zkontrolujte, zda daný port již nepoužívá jiná spuštěná aplikace.",
                "V nastavení relace přesměrování změňte číslo portu na volný port.",
            ),
            "command": "",
            "url": FORWARD_HELP,
            "category": "network",
        },
        "session_error": {
            "title_en": "Mutagen Session Error",
            "title_cs": "Chyba relace Mutagenu",
            "expl_en": "Mutagen reported a synchronization failure.",
            "expl_cs": "Mutagen ohlásil chybu při synchronizaci relace.",
            "steps_en": (
                "Review the technical error message below.",
                "Check if both endpoints are connected and online.",
                "Click 'Refresh Status' or restart the Mutagen daemon.",
            ),
            "steps_cs": (
                "Prohlédněte si technické hlášení o chybě níže.",
                "Zkontrolujte, zda jsou oba koncové body připojeny a dostupné.",
                "Klikněte na 'Zkontrolovat stav' nebo restartujte démona Mutagenu.",
            ),
            "command": "",
            "url": SYNC_HELP,
            "category": "general",
        },
    }

    data = remedies.get(code)
    if data:
        return DiagnosticRemedy(
            code=code,
            title=data["title_cs"] if czech else data["title_en"],
            explanation=data["expl_cs"] if czech else data["expl_en"],
            remedy_steps=data["steps_cs"] if czech else data["steps_en"],
            quick_command=data["command"],
            article_url=data["url"],
            category=data["category"],
        )

    # Fallback to copy from _issue_copy
    expl, suggestion, url = _issue_copy(code)
    return DiagnosticRemedy(
        code=code,
        title="Problém s relací" if czech else "Session Issue",
        explanation=expl,
        remedy_steps=(suggestion,),
        quick_command="",
        article_url=url,
        category="general",
    )


def diagnose_sessions(
    context: SessionDoctorContext,
    *,
    now: datetime | None = None,
    freshness_seconds: int = FRESHNESS_SECONDS,
) -> SessionDoctorReport:
    generated_at = now or datetime.now(UTC)
    stale_kinds = tuple(
        kind
        for kind, observed_at in (
            ("sync", context.sync_observed_at),
            ("forward", context.forward_observed_at),
        )
        if not _recent(observed_at, generated_at, freshness_seconds)
    )
    authoritative = (
        context.cli_available
        and context.daemon_running is True
        and not context.sessions_stale
        and not stale_kinds
    )
    issues: list[DiagnosticIssue] = []
    seen: set[tuple[str, str | None]] = set()

    def add(
        code: str,
        severity: str,
        *,
        session: SessionSnapshot | None = None,
        evidence: tuple[object, ...] = (),
        observed_at: datetime | None = None,
        certainty: str = "confirmed",
        detail: str = "",
    ) -> None:
        identifier = session.identity.identifier if session is not None else None
        key = code, identifier
        if key in seen:
            return
        seen.add(key)
        explanation, suggestion, article = _issue_copy(code)
        current_certainty: Literal["confirmed", "suspected"] = (
            "confirmed" if certainty == "confirmed" else "suspected"
        )
        if session is not None and (
            not _recent(session.measured_at, generated_at, freshness_seconds)
            or session.stale_reason is not None
        ):
            current_certainty = "suspected"
        issues.append(
            DiagnosticIssue(
                code,
                severity,
                0.98 if current_certainty == "confirmed" else 0.6,
                evidence,
                explanation,
                (suggestion,),
                False,
                context.version,
                current_certainty,
                explanation,
                detail,
                article,
                identifier,
                observed_at or (session.measured_at if session is not None else generated_at),
            )
        )

    if not context.cli_available:
        add(
            "cli_missing",
            "error",
            evidence=({"source": "MutaUI settings", "value": "Mutagen path missing"},),
        )
    elif context.daemon_running is False:
        add(
            "daemon_offline",
            "error",
            evidence=(
                {"source": "Mutagen CLI", "value": context.snapshot_error or "Daemon unavailable"},
            ),
        )
    if stale_kinds or context.sessions_stale or context.daemon_running is not True:
        evidence = tuple(
            {
                "source": f"{kind} list",
                "value": (
                    "daemon unavailable"
                    if context.daemon_running is not True
                    else "missing or older than freshness limit"
                ),
                "observed_at": value,
            }
            for kind, value in (
                ("sync", context.sync_observed_at),
                ("forward", context.forward_observed_at),
            )
            if kind in stale_kinds or context.sessions_stale or context.daemon_running is not True
        )
        add(
            "snapshot_stale",
            "warning",
            evidence=evidence,
            observed_at=min(
                (
                    value
                    for value in (context.sync_observed_at, context.forward_observed_at)
                    if value
                ),
                default=None,
            ),
        )

    for session in context.sessions:
        observed = session.measured_at
        source = f"Mutagen {session.identity.kind} list"
        session_evidence = ({"source": source, "value": session.state, "observed_at": observed},)
        config = session.native_config
        paused = config.get("paused") is True or session.state.casefold() in {
            "paused",
            "manually paused",
        }
        mode = config.get("mode", config.get("watchMode"))
        manual = config.get("manual") is True or (
            isinstance(mode, str) and mode.casefold() == "manual"
        )
        if paused:
            add("intentional_pause", "info", session=session, evidence=session_evidence)
        if manual:
            add("manual_mode", "info", session=session, evidence=session_evidence)

        specialized_error = False
        if session.identity.kind == "sync":
            excluded_conflicts = _int_value(config.get("excludedConflicts"))
            conflict_total = len(session.conflicts) + excluded_conflicts
            if conflict_total:
                add(
                    "conflicts",
                    "warning",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen conflict counters",
                            "value": conflict_total,
                            "observed_at": observed,
                        },
                    ),
                )
            status = config.get("status")
            if status in (1, 2, 3, "1", "2", "3"):
                status_text = {
                    1: "Halted: empty root",
                    2: "Halted: deleted root",
                    3: "Halted: root type change",
                    "1": "Halted: empty root",
                    "2": "Halted: deleted root",
                    "3": "Halted: root type change",
                }[status]
                add(
                    "root_problem",
                    "error",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen sync status",
                            "value": status_text,
                            "observed_at": observed,
                        },
                    ),
                    detail=status_text,
                )
                specialized_error = True
            elif (
                status in (0, "0")
                and not paused
                and not manual
                and any(
                    endpoint is not None and endpoint.kind == "ssh"
                    for endpoint in (session.alpha_or_source, session.beta_or_destination)
                )
            ):
                add(
                    "ssh_disconnected",
                    "error",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen sync status",
                            "value": "Disconnected",
                            "observed_at": observed,
                        },
                    ),
                )
                specialized_error = True
            excluded_problem_count = sum(
                _int_value(config.get(key))
                for key in (
                    "excludedScanProblems",
                    "excludedTransitionProblems",
                )
            )
            if excluded_problem_count:
                add(
                    "scan_problem",
                    "warning",
                    session=session,
                    evidence=(
                        {
                            "source": "Mutagen excluded problem counters",
                            "value": excluded_problem_count,
                            "observed_at": observed,
                        },
                    ),
                )

        endpoints = (
            (
                ("alpha", session.alpha_or_source),
                ("beta", session.beta_or_destination),
            )
            if session.identity.kind == "sync"
            else (
                ("source", session.alpha_or_source),
                ("destination", session.beta_or_destination),
            )
        )
        for endpoint_name, endpoint in endpoints:
            if endpoint is None:
                continue
            fields = endpoint.native_fields
            connected = fields.get("connected")
            connection_state = fields.get("connectionState", fields.get("state"))
            connection_text = (
                str(connection_state).casefold() if connection_state is not None else ""
            )
            endpoint_error = fields.get("lastError", fields.get("error", ""))
            error_text = _text(endpoint_error) if endpoint_error else ""
            disconnected = connected is False or connection_text in {
                "disconnected",
                "error",
                "failed",
            }
            if (paused or manual) and disconnected and not error_text:
                continue
            code = _error_code(error_text, kind=session.identity.kind, endpoint_name=endpoint_name)
            if code is None and disconnected:
                code = (
                    "forward_source_problem"
                    if session.identity.kind == "forward" and endpoint_name == "source"
                    else "forward_destination_problem"
                    if session.identity.kind == "forward"
                    else "ssh_disconnected"
                    if endpoint.kind == "ssh"
                    else "session_error"
                )
            if code is not None:
                add(
                    code,
                    "error",
                    session=session,
                    evidence=(
                        {
                            "source": f"{source} endpoint {endpoint_name}",
                            "value": error_text or connection_text or "disconnected",
                            "observed_at": observed,
                        },
                    ),
                    detail=error_text,
                )
                specialized_error = True

        raw_error = config.get("lastError")
        if raw_error:
            message = _text(raw_error)
            code = _error_code(message, kind=session.identity.kind)
            if code is None:
                code = "session_error"
            add(
                code,
                "error",
                session=session,
                evidence=(
                    {"source": source + " lastError", "value": message, "observed_at": observed},
                ),
                detail=message,
            )
            specialized_error = True
        if (
            session.state.casefold() == "error"
            and not paused
            and not specialized_error
            and not session.conflicts
            and not _int_value(config.get("excludedConflicts"))
            and not session.problems
        ):
            add("session_error", "error", session=session, evidence=session_evidence)

        for problem in session.problems:
            message = _text(problem)
            code = _error_code(message, kind=session.identity.kind)
            if code is None:
                code = "session_error"
            add(
                code,
                "warning",
                session=session,
                evidence=(
                    {"source": source + " problem", "value": message, "observed_at": observed},
                ),
                detail=message,
            )

    if (
        context.cpu_percent is not None
        and context.cpu_percent >= HIGH_CPU_PERCENT
        and _recent(context.resource_observed_at, generated_at, freshness_seconds)
    ):
        add(
            "high_cpu",
            "warning",
            certainty="suspected",
            observed_at=context.resource_observed_at,
            evidence=(
                {
                    "source": "Mutagen process sampler",
                    "value": context.cpu_percent,
                    "unit": "percent",
                    "observed_at": context.resource_observed_at,
                },
            ),
            detail=f"Heuristic threshold: {HIGH_CPU_PERCENT:.0f}% measured CPU.",
        )

    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    issues.sort(
        key=lambda issue: (
            severity_order.get(issue.severity, 4),
            issue.code,
            issue.session_identifier or "",
        )
    )
    return SessionDoctorReport(
        tuple(issues), authoritative, generated_at, len(context.sessions), stale_kinds
    )
