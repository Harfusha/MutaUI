# Architektura v8.2

Data: lokální `MutagenClient` volá výhradně nativní CLI (`sync list --template`, `forward list --template`). Pro obě strany synchronizace se používají exportované nativní endpoint modely. Seskupování hostů je čisté řetězcové a nespouští vlastní SSH/DNS/HTTP připojení.

Výkon: `QThreadPool` pro CLI a procesová měření, samostatný SQLite writer, cache historie a grafové geometrie. `AdaptivePolling` pouze mění interval čtení stavů v GUI podle detekovaných změn nebo běžící fáze Mutagenu. Nepředstírá změnu frekvence skutečných synchronizačních cyklů.

Native watch profily jsou whitelist parametrů `sync create`: `portable`, `force-poll`, `no-watch` a `watch-polling-interval`. Neumožňují za běhu měnit běžící relace. Nastavení existujících relací jsou výhradně lokální preference GUI (poznámky a notifikace), nativní hodnoty se zobrazují pouze pro čtení.

Qt: detail relací a nastavení používají QScrollArea a layout s minimální přirozenou velikostí, kruhový indikátor vykresluje relativně malý pixelový text. Tabulky mají specifické prázdné stavy. GUI smoke test porovnává počty synchronizací s aktuálně vybraným serverem a nepředpokládá pevné pořadí skupin.

EXE: build skripty spouštějí jednotkové + Qt smoke testy na Windows před PyInstaller buildem. Python/PySide6 není potřebné po sestavení hotového EXE, Mutagen CLI zůstává externí.
