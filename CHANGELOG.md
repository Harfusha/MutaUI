# Mutagen Control v8.2 — opravy Windows GUI a profily sledování

## Opravy

- Opraven chybný předpoklad GUI smoke testu: první server může mít pouze forward relace. Test teď kontroluje skutečný obsah každé skupiny, včetně prázdných stavů.
- Přehled **Servery** zobrazuje výslovně prázdné stavy podle typu relace.
- Panel detailu relace již není sevřen ve vertikálním splitteru. Stránka synchronizací i stránka nastavení používají přirozenou výšku obsahu s posouváním.
- Ovládací tlačítka detailu jsou rozmístěna do dvou řádků (3 + 2) místo jedné dlouhé řady.
- Kruhový ukazatel stavu používá písmo v pixelech a oddělenou oblast popisku, aby se při vysokém DPI nepřekrývaly texty.
- Ovládací prvky formulářů mají konzistentní minimální výšku a více místa pro obsah.

- Nový `--self-test` běžící přímo ze zabaleného EXE. Build po sestavení ověřuje i skutečný balík, jinak skončí chybou. Diagnostika se zapisuje do `%TEMP%\mutagen-control-self-test.log`.
- Přiložen `gui_preview.cmd` pro offline vizuální snímky všech 11 stránek při 100/150/200 % škálování.

## Nové nastavení

- **Adaptivní čtení stavů v GUI**: rychlé dotazování při změně stavu nebo v aktivní fázi, úsporný interval po nastavené době klidu. Konfigurovatelné intervaly a délka klidu.
- **Nativní profily nových synchronizací**: výchozí, event-driven, rychlý/střední/úsporný polling a ruční `no-watch`.
- **Nastavení jednotlivé existující relace**: místní poznámka, individuální vypnutí notifikací a náhled konfigurace watch/scan ze stavu Mutagenu.
- Další nezávislé testy adaptivního plánování a parametrů vytváření relací.

## Omezení

- Profily **nepřepisují již vytvořené** relace. Standardní Mutagen CLI nemá `sync edit/update` příkaz.
- Nejde o limit přenosové rychlosti. Mutagen CLI v této cestě neumožňuje jednoduchý per-session bandwidth throttling. Polling interval je perioda kontroly změn, nikoli rychlost přenosu souborů.
- Adaptivní čtení stavů GUI nemění vnitřní běh Mutagen daemonu. Po zavření GUI funguje synchronizace dál podle nativního nastavení Mutagenu.
- Desktopové Windows GUI a PyInstaller jsou nutné pro konečné integrační ověření sestavení; tyto části nelze ověřit v prostředí bez PySide6 a Windows.
