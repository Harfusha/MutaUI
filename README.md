# Mutagen Control v8.2 — Windows

Samostatné GUI pro existující Mutagen CLI. Neinstaluje službu na server, nepřipojuje se vlastní SSH relací ani neinstaluje vlastní remote agent. Používá výstup `mutagen sync list` / `mutagen forward list` z místního daemonu.

## Spuštění a kontrola

1. Rozbalte ZIP do **nové složky** (neslučovat s v8/v8.1).
2. Spusťte `start.cmd` (vytvoří lokální Python prostředí a nainstaluje závislosti).
3. Nejdřív zkuste `demo.cmd` a případně `check_windows.cmd`.
4. `build_fast.cmd` vytváří `dist-fast\MutagenControl\MutagenControl.exe` v přenosné složce; **kopírujte celou složku**.
5. `build_exe.cmd` vytváří jednosouborové `dist\MutagenControl.exe`. Po dobu sestavení je vyžadován Python, pro spuštění EXE již ne. Mutagen CLI musí být na počítači dostupné.

Všechny build skripty spouštějí Qt GUI smoke test. Pokud test selže, **build se ukončí bez vytváření nového EXE**. Používejte teprve nově sestavenou variantu, ne staré soubory v `dist-debug`.

## Nastavení

**Nastavení → Chování aplikace**: interval čtení stavů, adaptivní interval při změnách, interval po delším klidu, doba klidu, interval vzorkování CPU/RAM a úsporný režim v tray. Ovládá to pouze četnost dotazů GUI, **nikoli vnitřní synchronizační algoritmus** Mutagenu.

**Globální profil pro nové synchronizace**: možnost vybrat výchozí profil sledování změn, který se předvybere v dialogu `Nová synchronizace`.

**Per synchronizace → Nastavení relace**: místní poznámka, zapnutí/vypnutí notifikací a skutečná konfigurace `watch` / `scan` vyčtená z nativních dat Mutagenu. Tyto volby nezasahují do existující konfigurace serveru/daemonu. Pokud chceš jiný nativní polling u už existující synchronizace, je třeba ji ručně bezpečně nahradit novou relací; aplikace to sama nedělá kvůli riziku opětovného vyhodnocování souborů.

### Profily nových synchronizací

| Profil | Parametry předané při vytváření |
|---|---|
| Výchozí | Ponechá výchozí konfiguraci Mutagenu |
| Reakce na události | `--watch-mode=portable --scan-mode=accelerated` |
| Rychlý polling | `--watch-mode=force-poll --watch-polling-interval=5` |
| Střední polling | `--watch-mode=force-poll --watch-polling-interval=20` |
| Úsporný polling | `--watch-mode=force-poll --watch-polling-interval=60` |
| Ručně | `--watch-mode=no-watch` |

`no-watch` neznamená pozastavení relace; vynucený cyklus použije `Sync now` (`mutagen sync flush`). Nastavení frekvence polling souborového systému je odlišné od rychlosti přenosu dat, kterou GUI neumí spolehlivě limitovat.

## Hromadné akce a servery

Stránka `Servery` sdružuje relace podle protokolu / hostitele / portu, bez DNS dotazů. Jedna synchronizace může být přiřazena dvěma vzdáleným hostitelům, pokud jsou ALPHA i BETA vzdálené. Přesné ID relací jsou předávána do `mutagen sync flush|pause|resume|reset|terminate` či ekvivalentních forward příkazů. Žádné `--all` ani svévolný zásah do jiných hostitelů.

Automatický start nativních relací funguje pomocí per-session pause/resume a registrace Mutagen daemonu do Windows Run. Vypnutí auto-startu relaci ihned pozastaví. Nemá vlastní plánovač ani další službu.

## Live log a vzdálená strana

Aplikace zobrazuje živé změny stavu a může průběžně číst **existující lokální log soubor**. Standardní CLI neposkytuje trvalý plnohodnotný stream všech interních debug logů vzdáleného `mutagen-agent`. CPU/RAM vzdáleného serveru také nejsou součástí stavu endpointu; GUI proto taková čísla nevymýšlí.

## Ověření

- `python verify_source.py` kontroluje kód a známé statické chyby práce s Qt layouty.
- `python -m pytest -q tests --ignore=tests/test_gui_smoke.py` ověřuje dostupné logické testy.
- `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_gui_smoke.py` na Windows ověřuje **skutečné vytvoření stránek**, přepínání, grafy a skupiny serverů. Test musí projít před buildem.
- V tomto prostředí není PySide6 ani Windows; neposkytujeme zde předem otestované `.exe`.

Zdrojové kódy nejsou oficiální aplikací projektu Mutagen. Žádné operace nad skutečnými relacemi neprobíhají v demonstračním režimu.

### Náhled vzhledu pro kontrolu DPI

`gui_preview.cmd` ukládá obrazovky všech 11 stránek demonstračního režimu do složek `preview-1`, `preview-1.5` a `preview-2` při škálování 100 %, 150 % a 200 %. Při vizuální kontrole lze rychle dohledat případné překrytí prvků bez připojování k Mutagenu. Tento test vytváří obrázky, ale **sám nevyhodnocuje jejich estetickou kvalitu**.

### Kontrola samotného sestaveného EXE

Předchozí buildy ověřovaly pouze zdrojové GUI. Ve v8.2 build skripty po PyInstalleru také spouštějí **zabalený EXE** s parametrem `--self-test`. Ten bez kontaktu s Mutagen daemonem otevře demo, projde všechny stránky a zkontroluje tabulky serverových skupin. Neúspěch ukončí build chybovým kódem.

Diagnostický výstup self-testu najdete v `%TEMP%\mutagen-control-self-test.log`. Přes shell lze stejnou kontrolu opakovat příkazem `dist-fast\MutagenControl\MutagenControl.exe --self-test`. `--self-test` není benchmark a nekontroluje vzhled pixel po pixelu, pouze běh zabaleného Qt GUI a strukturu dat.
