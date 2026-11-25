"""Pure presentation and truth-model helpers for Mutagen snapshots (M04, M06, M70, M84, M85)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class LocalizedPair:
    """Paired English/Czech text preserved together for dynamic UI switching."""

    en: str
    cs: str


@dataclass(frozen=True, slots=True)
class DaemonControlPolicy:
    """Explicit Start/Stop enablement and operator guidance derived from daemon state."""

    enable_start: bool
    enable_stop: bool
    hint: LocalizedPair
    suggest_diagnostics: bool = False


@dataclass(frozen=True, slots=True)
class OverviewScope:
    """Per-kind freshness, HealthRing scope, and metric summaries for Overview."""

    ring_total: int
    ring_problem: int
    ring_scope: Literal["current", "partial", "stale", "unavailable"]
    ring_detail: LocalizedPair
    metric_values: dict[str, str]
    scope_banner: LocalizedPair
    scope_severity: Literal["fresh", "stale", "unavailable"]
    sync_state_tag: LocalizedPair
    forward_state_tag: LocalizedPair
    updated_banner: LocalizedPair


def format_observed_time(observed_at: datetime | None) -> str:
    if observed_at is None:
        return ""
    try:
        return observed_at.astimezone().strftime("%H:%M:%S")
    except (OSError, ValueError):
        return observed_at.strftime("%H:%M:%S")


def parse_mutagen_version_output(
    raw: str,
) -> tuple[str, Literal["fresh", "unavailable", "invalid"], str]:
    """Safely parse `mutagen version` without crashing on empty/multiline/corrupt output."""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return "", "unavailable", "CLI returned empty version output."
    first = lines[0]
    has_control_chars = any(ord(ch) < 32 and ch != "\t" for ch in first)
    if len(first) > 160 or has_control_chars or not any(ch.isalnum() for ch in first):
        return "", "invalid", "CLI returned unreadable version output."
    detail = "Version parsed from multi-line output." if len(lines) > 1 else ""
    return first, "fresh", detail


def compute_daemon_controls(snap: Any, *, demo: bool, pending_action: bool) -> DaemonControlPolicy:
    """Separate Start/Stop availability and explain disabled states clearly."""
    if demo:
        return DaemonControlPolicy(
            enable_start=False,
            enable_stop=False,
            hint=LocalizedPair(
                "Actions are disabled in demo mode.",
                "V demo režimu jsou akce vypnuté.",
            ),
        )
    if pending_action:
        return DaemonControlPolicy(
            enable_start=False,
            enable_stop=False,
            hint=LocalizedPair(
                "Waiting for the active Mutagen command to finish.",
                "Čeká se na dokončení probíhajícího příkazu Mutagenu.",
            ),
        )
    state = getattr(
        snap, "daemon_state", "running" if getattr(snap, "daemon", False) else "stopped"
    )
    if not getattr(snap, "binary", "") or state == "unconfigured":
        return DaemonControlPolicy(
            enable_start=False,
            enable_stop=False,
            hint=LocalizedPair(
                "Start and Stop are unavailable until a Mutagen CLI path is selected in Settings.",
                "Spuštění i zastavení není dostupné, dokud v Nastavení nevyberete cestu k Mutagen CLI.",
            ),
            suggest_diagnostics=True,
        )
    if state == "checking":
        return DaemonControlPolicy(
            enable_start=False,
            enable_stop=False,
            hint=LocalizedPair(
                "Checking Mutagen daemon status before enabling controls.",
                "Před zpřístupněním ovládání se kontroluje stav služby Mutagen.",
            ),
        )
    if state == "running":
        return DaemonControlPolicy(
            enable_start=False,
            enable_stop=True,
            hint=LocalizedPair(
                "Start is disabled because the daemon is already running.",
                "Spuštění je vypnuté, protože služba Mutagen již běží.",
            ),
        )
    if state == "stopped":
        return DaemonControlPolicy(
            enable_start=True,
            enable_stop=False,
            hint=LocalizedPair(
                "Stop is disabled because the daemon is already stopped.",
                "Zastavení je vypnuté, protože služba Mutagen je již zastavena.",
            ),
        )
    detail = (getattr(snap, "error", "") or "status unverified")[:120]
    return DaemonControlPolicy(
        enable_start=False,
        enable_stop=False,
        hint=LocalizedPair(
            f"Start and Stop are disabled while daemon availability is unverified ({detail}). Open Diagnostics.",
            f"Spuštění i zastavení je vypnuté, dokud je stav služby neověřený ({detail}). Otevřete Diagnostiku.",
        ),
        suggest_diagnostics=True,
    )


def format_registration_status(
    registration: str, *, platform_name: str
) -> tuple[LocalizedPair, str]:
    """Return platform-accurate autostart description and default tooltip hint."""
    if platform_name != "win32":
        if platform_name == "darwin":
            return (
                LocalizedPair(
                    "Auto-start: managed via launchd (~/Library/LaunchAgents); CLI registration is Windows-only",
                    "Automatické spuštění: na macOS přes launchd (~/Library/LaunchAgents); registrace v CLI je jen pro Windows",
                ),
                "launchd user agent in ~/Library/LaunchAgents",
            )
        return (
            LocalizedPair(
                "Auto-start: managed via systemd --user or XDG autostart; CLI registration is Windows-only",
                "Automatické spuštění: na Linuxu přes systemd --user nebo XDG autostart; registrace v CLI je jen pro Windows",
            ),
            "systemd --user or XDG autostart",
        )
    en_map = {
        "registered": "Auto-start: registered for this installation",
        "unregistered": "Auto-start: not registered",
        "other": "Auto-start: entry points to another installation/command",
        "unknown": "Auto-start: status unknown",
        "unsupported": "Auto-start: detection is available on Windows only",
    }
    cs_map = {
        "registered": "Automatické spuštění: registrováno pro tuto instalaci",
        "unregistered": "Automatické spuštění: není registrováno",
        "other": "Automatické spuštění: položka odkazuje na jinou instalaci nebo příkaz",
        "unknown": "Automatické spuštění: stav není známý",
        "unsupported": "Automatické spuštění: zjištění je dostupné pouze ve Windows",
    }
    return (
        LocalizedPair(
            en_map.get(registration, "Registration: unknown"),
            cs_map.get(registration, "Registrace: stav není známý"),
        ),
        "Registry entry in HKCU\\...\\Run\\Mutagen",
    )


def format_footer_status(snap: Any, *, demo: bool) -> LocalizedPair:
    """Report selected CLI path separately from confirmed daemon connection state."""
    if demo:
        return LocalizedPair(
            "DEMO • All actions are disabled",
            "DEMO • Všechny akce jsou vypnuté",
        )
    binary = getattr(snap, "binary", "")
    state = getattr(
        snap, "daemon_state", "running" if getattr(snap, "daemon", False) else "stopped"
    )
    if not binary or state == "unconfigured":
        return LocalizedPair(
            "Selected CLI: none · Select a Mutagen installation",
            "Vybrané CLI: žádné · Vyberte instalaci Mutagenu",
        )
    if state == "checking":
        return LocalizedPair(
            f"Selected CLI: {binary} · Checking daemon status…",
            f"Vybrané CLI: {binary} · Kontroluje se stav služby…",
        )
    if state == "running":
        if getattr(snap, "sessions_stale", False):
            return LocalizedPair(
                f"Selected CLI: {binary} · Daemon running (partial / stale session list)",
                f"Vybrané CLI: {binary} · Služba běží (neúplný nebo zastaralý seznam relací)",
            )
        return LocalizedPair(
            f"Selected CLI: {binary} · Daemon running",
            f"Vybrané CLI: {binary} · Služba běží",
        )
    last_ts = format_observed_time(getattr(snap, "last_contact_at", None))
    if state == "stopped":
        if last_ts:
            return LocalizedPair(
                f"Selected CLI: {binary} · Daemon stopped (last contact {last_ts})",
                f"Vybrané CLI: {binary} · Služba zastavena (poslední kontakt {last_ts})",
            )
        return LocalizedPair(
            f"Selected CLI: {binary} · Daemon stopped",
            f"Vybrané CLI: {binary} · Služba zastavena",
        )
    detail = (getattr(snap, "error", "") or "status unverified")[:80]
    if last_ts:
        return LocalizedPair(
            f"Selected CLI: {binary} · Connection unverified (last contact {last_ts} · {detail})",
            f"Vybrané CLI: {binary} · Připojení neověřeno (poslední kontakt {last_ts} · {detail})",
        )
    return LocalizedPair(
        f"Selected CLI: {binary} · Connection unverified ({detail})",
        f"Vybrané CLI: {binary} · Připojení neověřeno ({detail})",
    )


def format_daemon_status(snap: Any) -> tuple[LocalizedPair, LocalizedPair, str]:
    """Return consistent (title, description, accent) for the Daemon page."""
    state = getattr(
        snap, "daemon_state", "running" if getattr(snap, "daemon", False) else "stopped"
    )
    if not getattr(snap, "binary", "") or state == "unconfigured":
        return (
            LocalizedPair("●  Mutagen CLI not found", "●  Mutagen CLI nebylo nalezeno"),
            LocalizedPair(
                "Select the Mutagen CLI executable in Settings.",
                "Vyberte spustitelný soubor Mutagen CLI v Nastavení.",
            ),
            "red",
        )
    if state == "checking":
        return (
            LocalizedPair("●  Checking daemon status…", "●  Kontroluje se stav služby Mutagen…"),
            LocalizedPair(
                "Status is checked through the CLI without starting the daemon automatically.",
                "Stav se kontroluje přes CLI bez automatického spuštění služby.",
            ),
            "amber",
        )
    if state == "running":
        err = getattr(snap, "error", "")
        if err:
            desc = LocalizedPair(
                f"Daemon responded; {err}",
                f"Služba Mutagen odpověděla; {err}",
            )
        elif getattr(snap, "version_status", "") in ("unavailable", "invalid"):
            v_err = getattr(snap, "version_error", "") or "version output unavailable"
            desc = LocalizedPair(
                f"Daemon is responding (version note: {v_err}).",
                f"Služba Mutagen odpovídá (poznámka k verzi: {v_err}).",
            )
        else:
            desc = LocalizedPair("Daemon is responding.", "Služba Mutagen odpovídá.")
        return LocalizedPair("●  Running", "●  Spuštěno"), desc, "teal"
    last_ts = format_observed_time(getattr(snap, "last_contact_at", None))
    err = getattr(snap, "error", "")
    if state == "stopped":
        base_en = err or "Daemon is not running."
        base_cs = err or "Služba Mutagen není spuštěna."
        if last_ts:
            base_en += f" Last contact: {last_ts}."
            base_cs += f" Poslední kontakt: {last_ts}."
        return (
            LocalizedPair("●  Stopped", "●  Zastavena"),
            LocalizedPair(base_en, base_cs),
            "amber",
        )
    base_en = err or "Daemon availability could not be verified."
    base_cs = err or "Dostupnost služby Mutagen se nepodařilo ověřit."
    if last_ts:
        base_en += f" Last contact: {last_ts}."
        base_cs += f" Poslední kontakt: {last_ts}."
    return (
        LocalizedPair("●  Unavailable / unverified", "●  Nedostupná / stav neověřen"),
        LocalizedPair(base_en, base_cs),
        "red",
    )


def format_hero_status(snap: Any) -> tuple[LocalizedPair, LocalizedPair]:
    """Return consistent (title, subtitle) for Overview hero card."""
    state = getattr(
        snap, "daemon_state", "running" if getattr(snap, "daemon", False) else "stopped"
    )
    if not getattr(snap, "binary", "") or state == "unconfigured":
        return (
            LocalizedPair("Mutagen CLI is not configured", "Mutagen CLI není nakonfigurováno"),
            LocalizedPair(
                "Open Settings to select the Mutagen executable.",
                "Otevřete Nastavení a vyberte spustitelný soubor Mutagenu.",
            ),
        )
    if state == "checking":
        return (
            LocalizedPair("Checking connection…", "Kontroluje se připojení…"),
            LocalizedPair(
                "Checking daemon and active session status",
                "Kontroluje se služba Mutagen a stav aktivních relací",
            ),
        )
    if state == "running":
        if getattr(snap, "sessions_stale", False):
            return (
                LocalizedPair(
                    "Daemon is running (partial session status)",
                    "Služba běží (částečný nebo zastaralý stav relací)",
                ),
                LocalizedPair(
                    "Check per-group freshness badges below before acting on session counts.",
                    "Před dalším zásahem zkontrolujte štítky aktuálnosti jednotlivých skupin níže.",
                ),
            )
        return (
            LocalizedPair("Daemon is running", "Služba Mutagen běží"),
            LocalizedPair(
                "Sync runs in the background. The application monitors its status.",
                "Synchronizace běží na pozadí. Aplikace sleduje její stav.",
            ),
        )
    last_ts = format_observed_time(getattr(snap, "last_contact_at", None))
    if state == "stopped":
        suffix_en = f" Last contact at {last_ts}." if last_ts else ""
        suffix_cs = f" Poslední kontakt v {last_ts}." if last_ts else ""
        return (
            LocalizedPair("Daemon is stopped", "Služba Mutagen je zastavena"),
            LocalizedPair(
                f"Go to the Daemon page to start the service.{suffix_en}",
                f"Službu můžete spustit na stránce Služba Mutagen.{suffix_cs}",
            ),
        )
    suffix_en = f" Last contact at {last_ts}." if last_ts else ""
    suffix_cs = f" Poslední kontakt v {last_ts}." if last_ts else ""
    return (
        LocalizedPair("Daemon status is unverified", "Stav služby Mutagen je neověřený"),
        LocalizedPair(
            f"CLI probe did not confirm daemon availability. Open Diagnostics or Daemon.{suffix_en}",
            f"Kontrola CLI nepotvrdila dostupnost služby. Otevřete Diagnostiku nebo Službu Mutagen.{suffix_cs}",
        ),
    )


def format_side_status(
    snap: Any, *, czech_plural: Callable[[int, tuple[str, str, str]], str]
) -> tuple[LocalizedPair, LocalizedPair, str]:
    """Return consistent (title, subtitle, accent) for the navigation sidebar badge."""
    state = getattr(
        snap, "daemon_state", "running" if getattr(snap, "daemon", False) else "stopped"
    )
    if not getattr(snap, "binary", "") or state == "unconfigured":
        return (
            LocalizedPair("●  Mutagen CLI not found", "●  Mutagen CLI nebylo nalezeno"),
            LocalizedPair("Select mutagen.exe in Settings", "Vyberte mutagen.exe v Nastavení"),
            "red",
        )
    if state == "checking":
        return (
            LocalizedPair("●  Checking daemon…", "●  Kontroluje se služba…"),
            LocalizedPair("Probing Mutagen CLI", "Probíhá kontrola Mutagen CLI"),
            "amber",
        )
    if state == "running":
        sync_count = len(snap.sync)
        forward_count = len(snap.forward)
        sync_noun = "sync" if sync_count == 1 else "syncs"
        forward_noun = "port forward" if forward_count == 1 else "port forwards"
        summary_en = f"{sync_count} {sync_noun} · {forward_count} {forward_noun}"
        sync_form = czech_plural(sync_count, ("relace", "relace", "relací"))
        forward_form = czech_plural(forward_count, ("přesměrování", "přesměrování", "přesměrování"))
        summary_cs = f"{sync_count} {sync_form} · {forward_count} {forward_form}"
        if getattr(snap, "sessions_stale", False):
            summary_en += " (partial)"
            summary_cs += " (částečné)"
        return (
            LocalizedPair("●  Daemon online", "●  Služba Mutagen je spuštěna"),
            LocalizedPair(summary_en, summary_cs),
            "teal",
        )
    if state == "stopped":
        last_ts = format_observed_time(getattr(snap, "last_contact_at", None))
        if last_ts:
            return (
                LocalizedPair("●  Daemon offline", "●  Služba Mutagen je zastavena"),
                LocalizedPair(
                    f"Stopped · last contact {last_ts}", f"Zastavena · kontakt {last_ts}"
                ),
                "amber",
            )
        return (
            LocalizedPair("●  Daemon offline", "●  Služba Mutagen je zastavena"),
            LocalizedPair(
                (getattr(snap, "error", "") or "Not running yet")[:120],
                (getattr(snap, "error", "") or "Zatím není spuštěna")[:120],
            ),
            "amber",
        )
    return (
        LocalizedPair("●  Daemon unavailable", "●  Služba Mutagen je nedostupná"),
        LocalizedPair(
            (getattr(snap, "error", "") or "Connection unverified")[:120],
            (getattr(snap, "error", "") or "Připojení neověřeno")[:120],
        ),
        "red",
    )


def _kind_freshness_tag(
    kind_label_en: str,
    kind_label_cs: str,
    status: str,
    observed_at: datetime | None,
    incomplete_count: int,
) -> LocalizedPair:
    ts = format_observed_time(observed_at)
    time_suffix = f" {ts}" if ts else ""
    if status == "fresh":
        return LocalizedPair(
            f"{kind_label_en}: Current{time_suffix}",
            f"{kind_label_cs}: Aktuální{time_suffix}",
        )
    if status == "incomplete":
        return LocalizedPair(
            f"{kind_label_en}: Incomplete{time_suffix} (-{incomplete_count} invalid)",
            f"{kind_label_cs}: Neúplný{time_suffix} (vyřazeno {incomplete_count} vadných)",
        )
    if status == "stale":
        return LocalizedPair(
            f"{kind_label_en}: Last known{time_suffix}",
            f"{kind_label_cs}: Poslední známý{time_suffix}",
        )
    if status == "unavailable":
        return LocalizedPair(
            f"{kind_label_en}: Unavailable",
            f"{kind_label_cs}: Nedostupný",
        )
    return LocalizedPair(
        f"{kind_label_en}: Unverified",
        f"{kind_label_cs}: Neověřený",
    )


def _short_kind_state(status: str, observed_at: datetime | None) -> LocalizedPair:
    ts = format_observed_time(observed_at)
    suffix = f" ({ts})" if ts else ""
    if status == "fresh":
        return LocalizedPair(f"Current{suffix}", f"Aktuální{suffix}")
    if status == "incomplete":
        return LocalizedPair(f"Incomplete{suffix}", f"Neúplný{suffix}")
    if status == "stale":
        return LocalizedPair(f"Last known{suffix}", f"Poslední známý{suffix}")
    if status == "unavailable":
        return LocalizedPair("Unavailable", "Nedostupný")
    return LocalizedPair("Unverified", "Neověřený")


def compute_overview_scope(
    snap: Any,
    classify_fn: Callable[[dict[str, Any], str], tuple[str, str]],
    *,
    retry_seconds: float,
    duration_ms: float,
    refreshed_time: str,
) -> OverviewScope:
    """Compute per-list freshness tags, verified HealthRing scope, metrics, and banner."""
    sync_status = getattr(
        snap, "sync_status", "fresh" if getattr(snap, "daemon", False) else "unavailable"
    )
    fwd_status = getattr(
        snap, "forward_status", "fresh" if getattr(snap, "daemon", False) else "unavailable"
    )
    sync_obs = getattr(snap, "sync_observed_at", None)
    fwd_obs = getattr(snap, "forward_observed_at", None)
    sync_tag = _kind_freshness_tag(
        "Sync",
        "Synchronizace",
        sync_status,
        sync_obs,
        getattr(snap, "sync_incomplete_count", 0),
    )
    fwd_tag = _kind_freshness_tag(
        "Forwarding",
        "Přesměrování",
        fwd_status,
        fwd_obs,
        getattr(snap, "forward_incomplete_count", 0),
    )
    sync_short = _short_kind_state(sync_status, sync_obs)
    fwd_short = _short_kind_state(fwd_status, fwd_obs)

    sync_confirmed = sync_status in ("fresh", "incomplete")
    fwd_confirmed = fwd_status in ("fresh", "incomplete")
    sync_readable = sync_confirmed or sync_status == "stale"
    fwd_readable = fwd_confirmed or fwd_status == "stale"

    verified_sessions: list[tuple[str, dict[str, Any]]] = []
    if sync_confirmed:
        verified_sessions.extend(("sync", row) for row in snap.sync)
    if fwd_confirmed:
        verified_sessions.extend(("forward", row) for row in snap.forward)

    verified_kinds = [classify_fn(row, kind)[0] for kind, row in verified_sessions]
    if sync_confirmed and fwd_confirmed and sync_status == "fresh" and fwd_status == "fresh":
        ring_scope: Literal["current", "partial", "stale", "unavailable"] = "current"
        ring_total = len(verified_kinds)
        ring_problem = verified_kinds.count("error")
        ring_detail = LocalizedPair(
            "Measured across all current sync and forwarding sessions.",
            "Počítáno ze všech aktuálních synchronizací a přesměrování.",
        )
    elif sync_confirmed or fwd_confirmed:
        ring_scope = "partial"
        ring_total = len(verified_kinds)
        ring_problem = verified_kinds.count("error")
        ring_detail = LocalizedPair(
            f"Partial scope only — {sync_tag.en}; {fwd_tag.en}.",
            f"Pouze částečný rozsah — {sync_tag.cs}; {fwd_tag.cs}.",
        )
    elif sync_readable or fwd_readable:
        ring_scope = "stale"
        ring_total = 0
        ring_problem = 0
        ring_detail = LocalizedPair(
            f"Health score paused: showing last known data only ({sync_tag.en}; {fwd_tag.en}).",
            f"Skóre zdraví pozastaveno: zobrazeny pouze poslední známé údaje ({sync_tag.cs}; {fwd_tag.cs}).",
        )
    else:
        ring_scope = "unavailable"
        ring_total = 0
        ring_problem = 0
        ring_detail = LocalizedPair(
            "Health score unavailable: neither session list could be verified.",
            "Skóre zdraví nedostupné: žádný seznam relací se nepodařilo ověřit.",
        )

    visible_sessions: list[tuple[str, dict[str, Any]]] = []
    if sync_readable:
        visible_sessions.extend(("sync", row) for row in snap.sync)
    if fwd_readable:
        visible_sessions.extend(("forward", row) for row in snap.forward)
    if not sync_readable and not fwd_readable:
        metric_values = {"all": "—", "running": "—", "paused": "—", "errors": "—"}
    else:
        vis_kinds = [classify_fn(row, kind)[0] for kind, row in visible_sessions]
        metric_values = {
            "all": str(len(vis_kinds)),
            "running": str(sum(state in ("active", "busy") for state in vis_kinds)),
            "paused": str(vis_kinds.count("paused")),
            "errors": str(vis_kinds.count("error")),
        }

    scope_banner = LocalizedPair(
        f"Scope · {sync_tag.en}  |  {fwd_tag.en}",
        f"Rozsah dat · {sync_tag.cs}  |  {fwd_tag.cs}",
    )
    if ring_scope == "current":
        scope_severity: Literal["fresh", "stale", "unavailable"] = "fresh"
    elif ring_scope in ("partial", "stale"):
        scope_severity = "stale"
    else:
        scope_severity = "unavailable"

    if getattr(snap, "daemon", False) and not getattr(snap, "sessions_stale", False):
        updated_banner = LocalizedPair(
            f"Refreshed {refreshed_time}  ·  CLI {duration_ms:.0f} ms",
            f"Obnoveno {refreshed_time} · CLI {duration_ms:.0f} ms",
        )
    elif getattr(snap, "daemon", False):
        detail = getattr(snap, "error", "") or "partial or incomplete list"
        updated_banner = LocalizedPair(
            f"{sync_tag.en} · {fwd_tag.en} · showing last successful sessions where needed · {detail}",
            f"{sync_tag.cs} · {fwd_tag.cs} · u nedostupné části poslední známý stav · {detail}",
        )
    elif getattr(snap, "sessions_stale", False):
        updated_banner = LocalizedPair(
            (
                f"Daemon offline · showing last successful sessions ({sync_tag.en}; {fwd_tag.en}) "
                f"· retrying in {retry_seconds:.0f} s"
            ),
            (
                f"Služba je offline · zobrazeny poslední známé relace ({sync_tag.cs}; {fwd_tag.cs}) "
                f"· další pokus za {retry_seconds:.0f} s"
            ),
        )
    else:
        updated_banner = LocalizedPair(
            f"Daemon offline · retrying in {retry_seconds:.0f} s",
            f"Služba je offline · další pokus za {retry_seconds:.0f} s",
        )

    return OverviewScope(
        ring_total=ring_total,
        ring_problem=ring_problem,
        ring_scope=ring_scope,
        ring_detail=ring_detail,
        metric_values=metric_values,
        scope_banner=scope_banner,
        scope_severity=scope_severity,
        sync_state_tag=sync_short,
        forward_state_tag=fwd_short,
        updated_banner=updated_banner,
    )
