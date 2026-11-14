# Performance tuning / Ladění výkonu

## English

Application polling and Mutagen file watching are separate. MutaUI's adaptive status polling changes how often the GUI refreshes observations; it does not change sync speed or Mutagen's watch mode. CPU/RAM sampling and session-table rendering have their own settings and measurement paths. Treat benchmark budgets as targets until measured on the relevant reference hardware; do not infer remote CPU/RAM when the endpoint does not report them.

### Performance Tuning Assistant

In **Advanced → Sync → Session Settings**, the assistant reviews the selected native snapshot and local endpoint root metadata. It does not walk roots, inspect remote endpoints or network-share paths, run CLI commands, or change a live session. Entry count remains unknown unless Mutagen reports it; the assistant never invents a count or performance measurement.

Guidance is qualitative and follows the official [watching](https://mutagen.io/documentation/synchronization/watching/), [scanning](https://mutagen.io/documentation/synchronization/probing-and-scanning/), and [staging](https://mutagen.io/documentation/synchronization/staging/) documentation. It flags forced polling faster than Mutagen's documented 10-second default, full scans on potentially large roots, local root symlink/permission issues, and a known cross-filesystem staging mismatch. `portable` watching and `accelerated` scanning are optional suggestions; endpoint capabilities still need verification. When staging devices differ, the assistant may suggest endpoint-local `neighboring` staging to avoid the extra copy described by Mutagen.

Adding suggestions fills only the existing local replacement draft. Saving that draft does not affect the current session. Applying changes to an existing session requires the separate reviewed replacement flow, which recreates the session.

See [settings reference](../settings-reference.md), [session health](../session-health.md), [UI visual QA](../ui-visual-qa.md), and the [roadmap](../roadmap.md) for current measurement evidence and open budgets.

## Česky

Obnovování aplikace a sledování souborů Mutagenem jsou oddělené. Adaptivní obnovování MutaUI mění četnost aktualizace pozorovaného stavu GUI; nemění rychlost synchronizace ani režim watch Mutagenu. Vzorkování CPU/RAM a vykreslování tabulky relací mají vlastní nastavení a měření. Rozpočty benchmarků považujte za cíle, dokud nejsou změřené na příslušném referenčním hardwaru. Vzdálené CPU/RAM neodhadujte, pokud je endpoint neposkytuje.

Viz [přehled nastavení](../settings-reference.md), [zdraví relace](../session-health.md), [vizuální QA](../ui-visual-qa.md) a [roadmapu](../roadmap.md) s aktuálními měřeními a otevřenými cíli.

### Asistent ladění výkonu

V **Advanced → Sync → Nastavení relace** asistent zkontroluje vybraný nativní snímek a metadata místních kořenů. Kořeny neprochází, vzdálené endpointy ani síťová úložiště nezkoumá, nespouští CLI a živou relaci nemění. Počet položek zůstává neznámý, pokud jej Mutagen neposkytne; asistent nevymýšlí počty ani výsledky měření.

Doporučení jsou kvalitativní a vycházejí z oficiální dokumentace Mutagenu pro [watch](https://mutagen.io/documentation/synchronization/watching/), [scanning](https://mutagen.io/documentation/synchronization/probing-and-scanning/) a [staging](https://mutagen.io/documentation/synchronization/staging/). Upozorní na vynucené skenování rychlejší než dokumentovaný výchozí interval 10 sekund, úplné skeny velkých kořenů, problémy se symbolickým odkazem/oprávněními místního kořene a známý staging mezi souborovými systémy. `portable` a `accelerated` jsou volitelné návrhy; podporu endpointu je nutné ověřit. Při potvrzeném rozdílu souborových systémů může navrhnout `neighboring` staging pro daný endpoint.

Přidání návrhů vyplní pouze místní koncept náhrady. Uložení konceptu současnou relaci nezmění. Změna existující relace vyžaduje samostatnou kontrolu náhrady, která relaci znovu vytvoří.
