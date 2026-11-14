# Troubleshooting / Řešení potíží

## Mutagen CLI is missing

MutaUI expects a separate local Mutagen CLI. Install it using the [official instructions](https://mutagen.io/documentation/introduction/installation), make `mutagen` available on `PATH`, then run `mutagen version` in a new terminal. Restart MutaUI after changing `PATH`. MutaUI does not install a server component or remote agent.

## A sync does not start or the preview differs

Open the session or wizard details and inspect the endpoint paths, mode, direction, and operation preview. Confirm that the selected Mutagen CLI is the intended version. Do not retry against valuable data until the difference is understood. For existing sessions, consult the [session settings reference](settings-reference.md); creation defaults do not rewrite existing Mutagen configuration.

## SSH connection fails

Check that the local OpenSSH client can resolve the alias and connect independently. Review `~/.ssh/config`, key permissions, network access, and the remote account. MutaUI requires strict host-key checking. For an unknown or changed host key, verify its fingerprint with the host administrator over a trusted channel; do not disable checking or remove a warning to force a connection. See [SSH transport](https://mutagen.io/documentation/transports/ssh) and [remote inspection](remote-inspection.md).

## A file is missing or has unexpected contents

Pause before making further changes. Do not reset, replace, or terminate the session as a recovery shortcut. Review the session’s Mutagen status and logs, then use the [conflict inspector](conflict-inspector.md), [copy comparison](conflict-diff.md), and [manual conflict recovery](manual-conflict-resolution.md). Mutagen synchronization can propagate edits and deletions; recover from a known-good copy when needed.

## The application does not open or behaves differently after an upgrade

Record the OS version and architecture, MutaUI release, Mutagen version, and the exact error. Verify the release checksum and use an artifact for the matching OS and architecture. On Linux, support evidence currently covers Ubuntu CI; other distributions remain unverified. See the [installation guide](installation.md) and [acceptance traceability](acceptance-traceability.md).

## Share diagnostics safely

Use the app’s diagnostics or the relevant session status and local logs only when needed. Remove private paths, hostnames, account names, tokens, and key material before sharing output. Never share private key contents. Report reproducible issues through the project issue tracker with the versions and steps needed to reproduce them.

## Mutagen CLI chybí

MutaUI potřebuje samostatné místní Mutagen CLI. Nainstalujte jej podle [oficiálního návodu](https://mutagen.io/documentation/introduction/installation), zpřístupněte příkaz `mutagen` v `PATH` a v novém terminálu spusťte `mutagen version`. Po změně `PATH` MutaUI restartujte. MutaUI neinstaluje serverovou část ani vzdáleného agenta.

## Synchronizace se nespustí nebo náhled neodpovídá

Otevřete podrobnosti relace nebo průvodce a zkontrolujte cesty endpointů, režim, směr a náhled operace. Ověřte, že je vybraná zamýšlená verze Mutagen CLI. Pokud rozdíl nechápete, neopakujte operaci nad důležitými daty. U existující relace si přečtěte [přehled nastavení](settings-reference.md); výchozí hodnoty pro vytvoření nepřepisují konfiguraci existující relace Mutagenu.

## SSH spojení selže

Ověřte samostatně, že místní OpenSSH klient zná alias a naváže spojení. Zkontrolujte `~/.ssh/config`, oprávnění klíče, síť a vzdálený účet. MutaUI vyžaduje striktní kontrolu host klíče. U neznámého nebo změněného klíče ověřte fingerprint se správcem hostitele důvěryhodným kanálem; nevypínejte kontrolu ani neobcházejte varování. Viz [SSH transport](https://mutagen.io/documentation/transports/ssh) a [vzdálená inspekce](remote-inspection.md).

## Soubor chybí nebo má neočekávaný obsah

Než provedete další změny, pozastavte práci. Nepoužívejte reset, nahrazení ani ukončení relace jako rychlou obnovu. Zkontrolujte stav a logy relace Mutagenu, potom použijte [inspektor konfliktů](conflict-inspector.md), [porovnání kopií](conflict-diff.md) a [ruční obnovu po konfliktu](manual-conflict-resolution.md). Synchronizace Mutagenem může šířit změny i mazání; v případě potřeby obnovujte ze známé dobré kopie.

## Aplikace se neotevře nebo se po aktualizaci chová jinak

Zaznamenejte verzi a architekturu OS, vydání MutaUI, verzi Mutagenu a přesnou chybu. Ověřte kontrolní součet vydání a použijte balíček pro odpovídající OS a architekturu. Důkazy pro Linux nyní pokrývají CI na Ubuntu; ostatní distribuce zatím ověřeny nejsou. Viz [instalace](installation.md) a [přehled akceptace](acceptance-traceability.md).

## Bezpečné sdílení diagnostiky

Diagnostiku aplikace, stav relace a místní logy použijte jen v potřebném rozsahu. Před sdílením odstraňte soukromé cesty, názvy hostitelů a účtů, tokeny a údaje o klíčích. Obsah soukromého klíče nikdy nesdílejte. Opakovatelnou chybu nahlaste v issue trackeru projektu s verzemi a kroky k reprodukci.
