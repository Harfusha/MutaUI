# Settings reference (generated)

Generated from `mutaui.ui.settings_registry`; edit registry metadata instead of this file.
Application settings below do not directly modify Mutagen configuration unless the mapping says so.

## Theme / Vzhled

- Key: `theme`
- Group: Display
- Default: `system`
- Platforms: Windows, macOS, Linux
- Valid values: system, light, or dark. / system, light nebo dark.
- Recommended: System follows the operating-system color scheme. / Systémový vzhled sleduje nastavení operačního systému.
- Effect: Mutagen Control only. / Pouze Mutagen Control.
- Mutagen mapping: Application preference; no Mutagen option.

Select the application color theme. / Vyberte barevné téma aplikace.

## Language / Jazyk

- Key: `language`
- Group: Display
- Default: `en`
- Platforms: Windows, macOS, Linux
- Valid values: en or cs. / en nebo cs.
- Recommended: English is the default; Czech is available. / Výchozí je angličtina; dostupná je čeština.
- Effect: Mutagen Control only. / Pouze Mutagen Control.
- Mutagen mapping: Application preference; no Mutagen option.

Select the interface language foundation. / Vyberte jazykové nastavení rozhraní.

## Mutagen CLI path / Cesta k Mutagen CLI

- Key: `binary`
- Group: Application
- Default: ``
- Platforms: Windows, macOS, Linux
- Valid values: A valid executable path or blank. / Platná cesta ke spustitelnému souboru nebo prázdná hodnota.
- Recommended: Use the installed CLI discovered on PATH. / Použijte nainstalované CLI nalezené v PATH.
- Effect: Changes which local CLI the app invokes. / Mění místní CLI, které aplikace spouští.
- Mutagen mapping: Executable selection; not written to Mutagen configuration.

Path to the local Mutagen executable; blank uses PATH discovery. / Cesta k místnímu spustitelnému Mutagenu; prázdná hodnota hledá v PATH.

## Session refresh / Obnovení sessions

- Key: `interval`
- Group: Refresh
- Default: `4`
- Platforms: Windows, macOS, Linux
- Valid values: 2–30 seconds. / 2–30 sekund.
- Recommended: 4–8 seconds balances freshness and CPU use. / 4–8 sekund vyvažuje aktuálnost a zátěž CPU.
- Effect: GUI polling only; it does not change sync frequency. / Pouze obnovování GUI; nemění frekvenci synchronizace.
- Mutagen mapping: Application preference; no Mutagen option.

How often the app refreshes session status. / Jak často aplikace obnovuje stav sessions.

## CPU/RAM sampling / Vzorkování CPU/RAM

- Key: `metric_interval`
- Group: Refresh
- Default: `2`
- Platforms: Windows, macOS, Linux
- Valid values: 1, 2, 3, 5, or 10 seconds. / 1, 2, 3, 5 nebo 10 sekund.
- Recommended: 2 seconds; longer intervals reduce monitoring overhead. / 2 sekundy; delší interval snižuje režii monitorování.
- Effect: Local process monitoring only. / Pouze monitorování místních procesů.
- Mutagen mapping: Application preference; no Mutagen option.

How often local Mutagen process resources are sampled. / Jak často se měří prostředky místních procesů Mutagenu.

## Adaptive status polling / Adaptivní obnovování stavu

- Key: `adaptive_poll`
- Group: Refresh
- Default: `True`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enabled for responsive updates with less idle work. / Zapnuto pro rychlé reakce a nižší zátěž při nečinnosti.
- Effect: Changes GUI refresh timing only. / Mění pouze interval obnovování GUI.
- Mutagen mapping: Application preference; no Mutagen option.

Refresh faster during activity and slower while idle. / Obnovovat rychleji při aktivitě a pomaleji při nečinnosti.

## During activity / Při aktivitě

- Key: `adaptive_fast`
- Group: Refresh
- Default: `2`
- Platforms: Windows, macOS, Linux
- Valid values: 2–15 seconds. / 2–15 sekund.
- Recommended: 2 seconds. / 2 sekundy.
- Effect: GUI polling only. / Pouze obnovování GUI.
- Mutagen mapping: Application preference; no Mutagen option.

Status refresh interval while activity is detected. / Interval obnovování stavu při zjištěné aktivitě.

## When idle / Při nečinnosti

- Key: `adaptive_idle`
- Group: Refresh
- Default: `30`
- Platforms: Windows, macOS, Linux
- Valid values: 5–180 seconds. / 5–180 sekund.
- Recommended: 30 seconds. / 30 sekund.
- Effect: GUI polling only. / Pouze obnovování GUI.
- Mutagen mapping: Application preference; no Mutagen option.

Status refresh interval after activity subsides. / Interval obnovování stavu po odeznění aktivity.

## Idle delay / Prodleva do nečinnosti

- Key: `adaptive_quiet`
- Group: Refresh
- Default: `90`
- Platforms: Windows, macOS, Linux
- Valid values: 15–900 seconds. / 15–900 sekund.
- Recommended: 90 seconds. / 90 sekund.
- Effect: GUI polling only. / Pouze obnovování GUI.
- Mutagen mapping: Application preference; no Mutagen option.

Quiet time before adaptive polling switches to the idle interval. / Doba klidu, po které adaptivní obnovování přejde na interval nečinnosti.

## Default profile for new syncs / Výchozí profil nových syncs

- Key: `new_sync_profile`
- Group: Sync creation
- Default: `default`
- Platforms: Windows, macOS, Linux
- Valid values: A profile defined in sync_profiles.PROFILES. / Profil definovaný v sync_profiles.PROFILES.
- Recommended: Default Mutagen configuration. / Výchozí konfigurace Mutagenu.
- Effect: New sync sessions only; existing sessions are not changed. / Pouze nové sync sessions; stávající sessions se nemění.
- Mutagen mapping: Maps to the selected profile's whitelisted sync create flags.

Selects the watch and scan profile used by the New Sync dialog. / Určuje profil sledování a skenování použitý v dialogu New Sync.
[Mutagen documentation](https://mutagen.io/documentation/synchronization/watching/)

## Power saving in tray / Úspora energie v tray

- Key: `eco_tray`
- Group: Application
- Default: `True`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enabled when the app is commonly left in the tray. / Zapnuto, pokud aplikace obvykle zůstává v tray.
- Effect: Application resource use only. / Pouze spotřeba prostředků aplikace.
- Mutagen mapping: Application preference; no Mutagen option.

Reduce monitoring work while the app is hidden in the notification area. / Omezí monitorování, když je aplikace skrytá v oznamovací oblasti.

## Minimize to notification area / Minimalizovat do oznamovací oblasti

- Key: `tray`
- Group: Application
- Default: `True`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enabled if background monitoring is wanted. / Zapnuto, pokud chcete monitorování na pozadí.
- Effect: Application process behavior only. / Pouze chování procesu aplikace.
- Mutagen mapping: Application preference; no Mutagen option.

Keep the app running in the notification area when its window closes. / Ponechá aplikaci spuštěnou v oznamovací oblasti po zavření okna.

## Notifications / Oznámení

- Key: `alerts`
- Group: Alerts
- Default: `True`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enabled; individual alert rules can still be disabled. / Zapnuto; jednotlivá pravidla lze vypnout.
- Effect: Local desktop notifications only. / Pouze místní oznámení.
- Mutagen mapping: Application preference; no Mutagen option.

Enable notifications for newly detected session issues. / Povolí oznámení o nově zjištěných potížích sessions.

## Quiet hours / Tiché hodiny

- Key: `quiet_hours_enabled`
- Group: Alerts
- Default: `False`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enable when desktop alerts should remain silent overnight or during focus time. / Zapněte, pokud mají být oznámení v noci nebo při soustředění potlačená.
- Effect: Local desktop notification delivery only; issues remain in application history. / Pouze doručování místních oznámení; potíže zůstávají v historii aplikace.
- Mutagen mapping: Application preference; no Mutagen option.

Suppress desktop notifications during the configured local-time interval. / Potlačí oznámení na ploše během nastaveného místního časového intervalu.

## Quiet hours start / Začátek tichých hodin

- Key: `quiet_hours_start`
- Group: Alerts
- Default: `22:00`
- Platforms: Windows, macOS, Linux
- Valid values: 00:00–23:59. / 00:00–23:59.
- Recommended: Choose the beginning of the period when notifications should stay silent. / Zvolte začátek období, kdy mají oznámení zůstat potlačená.
- Effect: Local desktop notification delivery only. / Pouze doručování místních oznámení.
- Mutagen mapping: Application preference; no Mutagen option.

Local time when notification suppression begins, in 24-hour HH:MM format. / Místní čas začátku potlačení oznámení ve 24hodinovém formátu HH:MM.

## Quiet hours end / Konec tichých hodin

- Key: `quiet_hours_end`
- Group: Alerts
- Default: `07:00`
- Platforms: Windows, macOS, Linux
- Valid values: 00:00–23:59. / 00:00–23:59.
- Recommended: Choose the end of the period when notifications should stay silent. / Zvolte konec období, kdy mají oznámení zůstat potlačená.
- Effect: Local desktop notification delivery only. / Pouze doručování místních oznámení.
- Mutagen mapping: Application preference; no Mutagen option.

Local time when notification suppression ends, in 24-hour HH:MM format. / Místní čas konce potlačení oznámení ve 24hodinovém formátu HH:MM.

## CPU alert / Upozornění na CPU

- Key: `cpu_alert_on`
- Group: Alerts
- Default: `False`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enable only when sustained high CPU needs attention. / Zapněte, pokud chcete sledovat dlouhodobě vysoké CPU.
- Effect: Local Mutagen process monitoring only. / Pouze monitorování místních procesů Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Notify when total Mutagen process CPU stays above its limit. / Upozorní, když celkové CPU procesů Mutagenu trvale překročí limit.

## CPU threshold / Limit CPU

- Key: `cpu_alert_limit`
- Group: Alerts
- Default: `90`
- Platforms: Windows, macOS, Linux
- Valid values: 1–1600 percent. / 1–1600 procent.
- Recommended: 90–150% on a dual-core system. / 90–150 % na dvoujádrovém systému.
- Effect: Local Mutagen process monitoring only. / Pouze monitorování místních procesů Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

CPU percentage across all cores; 200% means two fully busy cores. / Procenta CPU přes všechna jádra; 200 % znamená dvě plně vytížená jádra.

## RAM alert / Upozornění na RAM

- Key: `ram_alert_on`
- Group: Alerts
- Default: `False`
- Platforms: Windows, macOS, Linux
- Valid values: Enabled or disabled. / Zapnuto nebo vypnuto.
- Recommended: Enable when sustained memory growth needs attention. / Zapněte, pokud chcete sledovat dlouhodobý růst paměti.
- Effect: Local Mutagen process monitoring only. / Pouze monitorování místních procesů Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Notify when total Mutagen process RAM stays above its limit. / Upozorní, když RAM procesů Mutagenu trvale překročí limit.

## RAM threshold / Limit RAM

- Key: `ram_alert_limit`
- Group: Alerts
- Default: `1024`
- Platforms: Windows, macOS, Linux
- Valid values: 64–131072 MB. / 64–131072 MB.
- Recommended: 512–2048 MB, depending on available memory. / 512–2048 MB podle dostupné paměti.
- Effect: Local Mutagen process monitoring only. / Pouze monitorování místních procesů Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Memory threshold in megabytes for all local Mutagen processes. / Limit paměti v megabajtech pro všechny místní procesy Mutagenu.

## Threshold duration / Doba překročení limitu

- Key: `alert_hold`
- Group: Alerts
- Default: `20`
- Platforms: Windows, macOS, Linux
- Valid values: 5–600 seconds. / 5–600 sekund.
- Recommended: 20 seconds to suppress brief spikes. / 20 sekund pro potlačení krátkých špiček.
- Effect: Local desktop notifications only. / Pouze místní oznámení.
- Mutagen mapping: Application preference; no Mutagen option.

How long a threshold must be exceeded before sending an alert. / Jak dlouho musí být limit překročen před odesláním upozornění.

## Check releases on startup / Kontrolovat vydání při spuštění

- Key: `check_updates_on_startup`
- Group: Updates
- Default: `False`
- Platforms: Windows, macOS, Linux
- Valid values: Boolean opt-in. / Výslovný přepínač ano/ne.
- Recommended: Disabled by default; enable only if you want a startup release check. / Ve výchozím stavu vypnuto; zapněte pouze, pokud chcete kontrolu vydání při spuštění.
- Effect: Public GitHub API request only when enabled; no update download or installation. / Veřejný požadavek na GitHub API pouze po zapnutí; bez stažení či instalace aktualizace.
- Mutagen mapping: Application preference; no Mutagen option.

When enabled, MutaUI requests public release metadata from the project’s GitHub Releases API once at startup. The request sends no device, session, path, or endpoint data. MutaUI does not download or install files. / Je-li volba zapnutá, MutaUI při spuštění jednou načte veřejná metadata vydání z GitHub Releases projektu. Požadavek neodesílá údaje o zařízení, relacích, cestách ani koncových bodech. MutaUI nic nestahuje ani neinstaluje.

## Session health mode / Režim zdraví sessions

- Key: `health_mode`
- Group: Health
- Default: `monitor_only`
- Platforms: Windows, macOS, Linux
- Valid values: monitor_only, assisted, or auto_safe. / monitor_only, assisted nebo auto_safe.
- Recommended: Keep monitor-only unless you want manual recovery suggestions. / Ponechte pouze monitorování, pokud nechcete ruční doporučení obnovy.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Monitor only is the default. Assisted shows a manual recommendation after sustained confirmed failures. Auto-safe records eligibility for an exact-session read-only status refresh; no Mutagen-changing action is connected. / Výchozí režim pouze sleduje. Asistovaný zobrazí ruční doporučení po potvrzených trvalých chybách. Auto-safe eviduje způsobilost k read-only kontrole přesného session; mutující akce Mutagenu nejsou připojené.

## Confirmed failure count / Počet potvrzených chyb

- Key: `health_failure_count`
- Group: Health
- Default: `3`
- Platforms: Windows, macOS, Linux
- Valid values: 3–10 observations. / 3–10 pozorování.
- Recommended: Three failures avoid reacting to a single transient error. / Tři chyby brání reakci na jedinou přechodnou chybu.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Consecutive confirmed failures required before the health policy can recommend action. / Počet po sobě jdoucích potvrzených chyb před doporučením akce.

## Failure duration threshold / Časový limit chyby

- Key: `health_failure_elapsed`
- Group: Health
- Default: `120`
- Platforms: Windows, macOS, Linux
- Valid values: 30–900 seconds. / 30–900 sekund.
- Recommended: 120 seconds filters short network interruptions. / 120 sekund odfiltruje krátké výpadky sítě.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Minimum elapsed time in the confirmed failure streak before a recommendation. / Minimální doba potvrzené série chyb před doporučením.

## Recovery cooldown / Prodleva obnovy

- Key: `health_cooldown`
- Group: Health
- Default: `60`
- Platforms: Windows, macOS, Linux
- Valid values: 60–3600 seconds. / 60–3600 sekund.
- Recommended: At least 60 seconds. / Nejméně 60 sekund.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Minimum time between eligible recovery attempts. / Minimální doba mezi povolenými pokusy o obnovu.

## Maximum recovery attempts / Maximum pokusů o obnovu

- Key: `health_max_attempts`
- Group: Health
- Default: `2`
- Platforms: Windows, macOS, Linux
- Valid values: 1–2 attempts. / 1–2 pokusy.
- Recommended: Never exceed two attempts. / Nikdy nepřekračujte dva pokusy.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Hard upper bound for eligible recovery attempts in the time window. / Pevný horní limit povolených pokusů v časovém okně.

## Recovery attempt window / Časové okno pokusů

- Key: `health_attempt_window`
- Group: Health
- Default: `1800`
- Platforms: Windows, macOS, Linux
- Valid values: 1800–86400 seconds. / 1800–86400 sekund.
- Recommended: At least 30 minutes. / Nejméně 30 minut.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Rolling window used to count recovery attempts. / Posuvné okno pro počítání pokusů o obnovu.

## Sleep/network recovery grace / Prodleva po spánku/síti

- Key: `health_environment_grace`
- Group: Health
- Default: `120`
- Platforms: Windows, macOS, Linux
- Valid values: 30–900 seconds. / 30–900 sekund.
- Recommended: 120 seconds allows connections to settle. / 120 sekund umožní ustálení připojení.
- Effect: Health tracking only; no Mutagen configuration change. / Pouze sledování zdraví; nemění konfiguraci Mutagenu.
- Mutagen mapping: Application preference; no Mutagen option.

Suppresses transient failures after sleep, wake or network changes. / Potlačí přechodné chyby po spánku, probuzení nebo změně sítě.

## Native sync configuration proposals

Current values are read-only session exports. Proposed values stay in MutaUI settings;
they do not modify running Mutagen sessions. Verify each field against the installed CLI before replacement.

| Field | Path | Recommended | Support | Impact | Help |
| --- | --- | --- | --- | --- | --- |
| `mode` | `mode` | two-way-safe | requires capability verification | Changes can overwrite data. | How changes propagate. |
| `watch.mode` | `watch.mode` | portable | requires capability verification | Frequent polling raises resource use. | How Mutagen detects file changes. |
| `watch.pollingInterval` | `watch.pollingInterval` | Mutagen default | requires capability verification | Low values raise resource use. | Seconds between polling scans. |
| `scanMode` | `scanMode` | accelerated | requires capability verification | Full scans can add substantial I/O. | How file trees are scanned. |
| `probeMode` | `probeMode` | probe | requires capability verification | Assume mode can skip safety checks. | Whether endpoint capabilities are probed. |
| `stageMode` | `stageMode` | mutagen | requires capability verification | Staging uses disk space. | Where file contents are staged. |
| `symbolicLink.mode` | `symlink.mode` | portable | requires capability verification | Native link behavior varies by platform. | How symbolic links are represented. |
| `ignore.paths` | `ignore.paths` | No custom paths | requires capability verification | Incorrect rules can omit data. | Ordered patterns excluded from sync. |
| `ignore.vcs` | `ignore.vcs` | Mutagen default | requires capability verification | Ignored metadata is not synchronized. | Ignore common version control data. |
| `ignore.syntax` | `ignore.syntax` | Detected by Mutagen | requires capability verification | Different syntax can change exclusions. | Pattern language for ignore paths. |
| `permissions.defaultFileMode` | `permissions.defaultFileMode` | Mutagen default | requires capability verification | May broaden or restrict access. | POSIX mode for new files. |
| `permissions.defaultDirectoryMode` | `permissions.defaultDirectoryMode` | Mutagen default | requires capability verification | May broaden or restrict access. | POSIX mode for new directories. |
| `permissions.defaultOwner` | `permissions.defaultOwner` | Mutagen default | requires capability verification | Can change ownership access. | Owner applied to new entries where supported. |
| `permissions.defaultGroup` | `permissions.defaultGroup` | Mutagen default | requires capability verification | Can change group access. | Group applied to new entries where supported. |
| `maxEntryCount` | `maxEntryCount` | Mutagen default | requires capability verification | A low limit can prevent complete synchronization. | Upper bound on scanned entries. |
| `maxStagingFileSize` | `maxStagingFileSize` | Mutagen default | requires capability verification | A low limit can prevent large files from synchronizing. | Upper bound for a staged file in bytes. |
| `compression.algorithm` | `compression.algorithm` | Mutagen default | requires capability verification | Compression trades CPU for network use. | Compression applied to transferred data. |
| `hash.algorithm` | `hash.algorithm` | Mutagen default | requires capability verification | Hash choice affects CPU cost and compatibility. | Algorithm used to identify content. |
| `alpha.watch.mode` | `alpha.watch.mode` | Inherited or Mutagen default | requires capability verification | Frequent polling raises resource use. | Endpoint file-change detection. |
| `alpha.watch.pollingInterval` | `alpha.watch.pollingInterval` | Inherited or Mutagen default | requires capability verification | Low values raise resource use. | Endpoint polling interval in seconds. |
| `alpha.scanMode` | `alpha.scanMode` | Inherited or Mutagen default | requires capability verification | Full scans can add substantial I/O. | Endpoint tree-scan mode. |
| `alpha.probeMode` | `alpha.probeMode` | Inherited or Mutagen default | requires capability verification | Assume mode can skip safety checks. | Endpoint capability-probe behavior. |
| `alpha.stageMode` | `alpha.stageMode` | Inherited or Mutagen default | requires capability verification | Staging uses disk space. | Endpoint staging location. |
| `alpha.permissions.defaultFileMode` | `alpha.permissions.defaultFileMode` | Inherited or Mutagen default | requires capability verification | Can broaden or restrict access. | POSIX mode for files at this endpoint. |
| `alpha.permissions.defaultDirectoryMode` | `alpha.permissions.defaultDirectoryMode` | Inherited or Mutagen default | requires capability verification | Can broaden or restrict access. | POSIX mode for directories at this endpoint. |
| `alpha.permissions.defaultOwner` | `alpha.permissions.defaultOwner` | Inherited or Mutagen default | requires capability verification | Can change access ownership. | Owner applied at this endpoint where supported. |
| `alpha.permissions.defaultGroup` | `alpha.permissions.defaultGroup` | Inherited or Mutagen default | requires capability verification | Can change access ownership. | Group applied at this endpoint where supported. |
| `alpha.compression.algorithm` | `alpha.compression.algorithm` | Inherited or Mutagen default | requires capability verification | Trades CPU for network use. | Compression choice for this endpoint. |
| `alpha.hash.algorithm` | `alpha.hash.algorithm` | Inherited or Mutagen default | requires capability verification | Affects CPU cost and compatibility. | Content hash choice for this endpoint. |
| `beta.watch.mode` | `beta.watch.mode` | Inherited or Mutagen default | requires capability verification | Frequent polling raises resource use. | Endpoint file-change detection. |
| `beta.watch.pollingInterval` | `beta.watch.pollingInterval` | Inherited or Mutagen default | requires capability verification | Low values raise resource use. | Endpoint polling interval in seconds. |
| `beta.scanMode` | `beta.scanMode` | Inherited or Mutagen default | requires capability verification | Full scans can add substantial I/O. | Endpoint tree-scan mode. |
| `beta.probeMode` | `beta.probeMode` | Inherited or Mutagen default | requires capability verification | Assume mode can skip safety checks. | Endpoint capability-probe behavior. |
| `beta.stageMode` | `beta.stageMode` | Inherited or Mutagen default | requires capability verification | Staging uses disk space. | Endpoint staging location. |
| `beta.permissions.defaultFileMode` | `beta.permissions.defaultFileMode` | Inherited or Mutagen default | requires capability verification | Can broaden or restrict access. | POSIX mode for files at this endpoint. |
| `beta.permissions.defaultDirectoryMode` | `beta.permissions.defaultDirectoryMode` | Inherited or Mutagen default | requires capability verification | Can broaden or restrict access. | POSIX mode for directories at this endpoint. |
| `beta.permissions.defaultOwner` | `beta.permissions.defaultOwner` | Inherited or Mutagen default | requires capability verification | Can change access ownership. | Owner applied at this endpoint where supported. |
| `beta.permissions.defaultGroup` | `beta.permissions.defaultGroup` | Inherited or Mutagen default | requires capability verification | Can change access ownership. | Group applied at this endpoint where supported. |
| `beta.compression.algorithm` | `beta.compression.algorithm` | Inherited or Mutagen default | requires capability verification | Trades CPU for network use. | Compression choice for this endpoint. |
| `beta.hash.algorithm` | `beta.hash.algorithm` | Inherited or Mutagen default | requires capability verification | Affects CPU cost and compatibility. | Content hash choice for this endpoint. |

## Native forwarding configuration proposals

Socket controls are proposal-only until installed CLI, endpoint and platform support is verified.
Existing forwarding sessions are not changed by MutaUI settings.

| Field | Native path | Recommended | Support | Impact | Help |
| --- | --- | --- | --- | --- | --- |
| `source.socket.overwriteMode` | `configurationSource.socket.overwriteMode` | leave | requires CLI and platform capability verification | Overwrite may affect existing paths. | How an existing socket path is handled. |
| `source.socket.owner` | `configurationSource.socket.owner` | Mutagen default | requires CLI and platform capability verification | Can change access ownership. | Owner assigned to a Unix socket where supported. |
| `source.socket.group` | `configurationSource.socket.group` | Mutagen default | requires CLI and platform capability verification | Can change access ownership. | Group assigned to a Unix socket where supported. |
| `source.socket.permissionMode` | `configurationSource.socket.permissionMode` | Mutagen default | requires CLI and platform capability verification | May broaden or restrict access. | POSIX mode for a Unix socket. |
| `destination.socket.overwriteMode` | `configurationDestination.socket.overwriteMode` | leave | requires CLI and platform capability verification | Overwrite may affect existing paths. | How an existing socket path is handled. |
| `destination.socket.owner` | `configurationDestination.socket.owner` | Mutagen default | requires CLI and platform capability verification | Can change access ownership. | Owner assigned to a Unix socket where supported. |
| `destination.socket.group` | `configurationDestination.socket.group` | Mutagen default | requires CLI and platform capability verification | Can change access ownership. | Group assigned to a Unix socket where supported. |
| `destination.socket.permissionMode` | `configurationDestination.socket.permissionMode` | Mutagen default | requires CLI and platform capability verification | May broaden or restrict access. | POSIX mode for a Unix socket. |
