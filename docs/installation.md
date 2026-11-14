# Install and first sync / Instalace a první synchronizace

MutaUI is a desktop frontend for the **Mutagen CLI**. It does not install Mutagen, a server service, or a remote agent. Install Mutagen separately and make its `mutagen` executable available on `PATH`. Follow the [official Mutagen installation guide](https://mutagen.io/documentation/introduction/installation). The official [Getting Started guide](https://mutagen.io/documentation/introduction/getting-started) explains endpoints and synchronization behavior.

## Windows

Download the Windows x64 installer or portable ZIP from the project’s GitHub Releases page. Check the release signature when present and verify the downloaded files against that release’s `SHA256SUMS.txt`.

- The per-user installer defaults to `%LOCALAPPDATA%\Programs\Mutagen Control`; administrator rights are not required. Run a newer installer over the existing installation to upgrade. Settings and history remain in user data after uninstall.
- For the portable build, extract the ZIP to a new folder and run `MutagenControl.exe`. Keep each release in its own folder; do not merge folders.
- Install the Windows Mutagen CLI separately using the [official guide](https://mutagen.io/documentation/introduction/installation), then open PowerShell and run `mutagen version` to confirm it is on `PATH`.

## macOS

Tagged releases provide a notarized DMG for Apple Silicon and Intel. Download it from GitHub Releases, open it, then drag `MutagenControl.app` onto the `Applications` shortcut in the DMG window. Install the Mutagen CLI separately; the official guide lists Homebrew and release-download options. With Homebrew, use `brew install mutagen-io/mutagen/mutagen`. In Terminal, run `mutagen version` before opening MutaUI.

## Linux

Tagged releases provide x86-64 AppImage and amd64 Debian packages. The release workflow installs and self-tests the Debian package and runs the AppImage self-test on Ubuntu. Compatibility with other distributions and desktop environments has not been verified.

- For AppImage, download it from GitHub Releases, mark it executable in your file manager or with `chmod +x <downloaded-file>.AppImage`, then launch it.
- On Debian or Ubuntu, install the downloaded package with `sudo apt install ./<downloaded-file>.deb`.
- Install Mutagen CLI separately. Follow the [official guide](https://mutagen.io/documentation/introduction/installation); for Homebrew use `brew install mutagen-io/mutagen/mutagen`. Confirm with `mutagen version` in a terminal.

## First launch and safe local test

1. Start MutaUI and confirm the application opens. If it reports that Mutagen is unavailable, install the CLI and restart MutaUI.
2. Create two disposable local folders with a few sample files. Do not use important data for the first run.
3. Choose **New Sync**, select the two local endpoints, and review the mode, direction, paths, and exact operation preview. Start only after the preview matches your intent.
4. Change a sample file on one side, refresh the session, and check the result on the other side. Mutagen synchronization can propagate changes and deletions; read the [official synchronization documentation](https://mutagen.io/documentation/introduction/getting-started) before selecting a mode for valuable data.
5. Stop and remove the disposable session when done. See the [settings reference](settings-reference.md) and the [application overview](index.md).

Basic and Advanced are presentation modes for the same Mutagen CLI. Advanced exposes additional options and risk confirmations. Existing session configuration is owned by Mutagen; changing a creation profile does not silently rewrite a session. Review the replacement preview before replacing one.

## SSH endpoints

SSH uses the local OpenSSH client and your normal SSH configuration, keys, and aliases. Set up and verify the host in OpenSSH first. MutaUI’s connection check requires strict host-key checking; it does not add unknown host keys or bypass changed-key warnings. Verify a host key through a trusted channel before accepting it. See the [Mutagen SSH transport guide](https://mutagen.io/documentation/transports/ssh) and [SSH profiles](ssh-profiles.md).

## Downloads, support, and verification

Use only the project’s GitHub Releases page for application downloads. Release artifacts include checksums; CI produces build attestations and signs release packages when the required signing credentials are configured. A local self-test or CI package check does not prove that every supported OS version has had a manual installation walkthrough. Current platform evidence and remaining gaps are in [acceptance traceability](acceptance-traceability.md); feature details and screenshots are in the [application overview](index.md) and [screenshot gallery](screenshots.md).

Release checks are off by default. In **Settings → Alerts**, enable and save **Check releases on startup** to allow a public GitHub release metadata request at startup; the same page offers a manual check while enabled. MutaUI sends no device, session, path, or endpoint data and never downloads or installs updates. Review signatures and checksums on the release page before downloading an artifact.

For setup and recovery guidance see [Troubleshooting](troubleshooting.md) and [conflict recovery](manual-conflict-resolution.md). Report reproducible defects in the project’s issue tracker with OS version, MutaUI release, Mutagen version, and relevant diagnostic output. Remove secrets and private paths before sharing logs.

## Instalace a první synchronizace

MutaUI je desktopové rozhraní pro **Mutagen CLI**. Mutagen, serverovou službu ani vzdáleného agenta neinstaluje. Mutagen nainstalujte zvlášť a zajistěte, aby byl příkaz `mutagen` dostupný v `PATH`. Řiďte se [oficiálním návodem k instalaci Mutagenu](https://mutagen.io/documentation/introduction/installation). Oficiální [Začínáme](https://mutagen.io/documentation/introduction/getting-started) popisuje endpointy a chování synchronizace.

### Windows (česky)

Ze stránky GitHub Releases stáhněte instalátor pro Windows x64 nebo přenosný ZIP. Pokud je podpis k dispozici, ověřte jej; stažené soubory porovnejte s `SHA256SUMS.txt` daného vydání.

- Instalátor je určen aktuálnímu uživateli a standardně se uloží do `%LOCALAPPDATA%\Programs\Mutagen Control`. Nepotřebuje práva správce. Aktualizujte spuštěním nového instalátoru přes stávající instalaci. Nastavení a historie zůstávají v uživatelských datech i po odinstalaci.
- Přenosný ZIP rozbalte do nové složky a spusťte `MutagenControl.exe`. Každou verzi ponechte v samostatné složce; obsah složek neslučujte.
- Mutagen CLI pro Windows nainstalujte zvlášť podle [oficiálního návodu](https://mutagen.io/documentation/introduction/installation). V PowerShellu spusťte `mutagen version` a ověřte, že příkaz funguje z `PATH`.

### macOS (česky)

Tagovaná vydání poskytují notarizovaný DMG pro Apple Silicon i Intel. Stáhněte jej z GitHub Releases, otevřete a přetáhněte `MutagenControl.app` na zástupce `Applications` v okně DMG. Mutagen CLI nainstalujte zvlášť; oficiální návod uvádí Homebrew i stažení vydání. S Homebrew použijte `brew install mutagen-io/mutagen/mutagen`. Před spuštěním MutaUI ověřte v Terminálu příkazem `mutagen version`, že CLI funguje.

### Linux (česky)

Tagovaná vydání poskytují x86-64 AppImage a amd64 balíček Debian. Release workflow instaluje a testuje balíček Debian a spouští test AppImage na Ubuntu. Kompatibilita s ostatními distribucemi a desktopovými prostředími zatím ověřena není.

- AppImage stáhněte z GitHub Releases, označte jako spustitelný v souborovém správci nebo příkazem `chmod +x <stažený-soubor>.AppImage` a spusťte.
- V Debianu nebo Ubuntu nainstalujte stažený balíček příkazem `sudo apt install ./<stažený-soubor>.deb`.
- Mutagen CLI nainstalujte zvlášť podle [oficiálního návodu](https://mutagen.io/documentation/introduction/installation); s Homebrew použijte `brew install mutagen-io/mutagen/mutagen`. V terminálu ověřte `mutagen version`.

### První spuštění a bezpečný místní test

1. Spusťte MutaUI a ověřte, že se otevře. Pokud oznámí chybějící Mutagen, nainstalujte CLI a MutaUI restartujte.
2. Vytvořte dvě dočasné místní složky s několika ukázkovými soubory. Při prvním pokusu nepoužívejte důležitá data.
3. Zvolte **New Sync**, vyberte obě místní složky a zkontrolujte režim, směr, cesty i přesný náhled operace. Spusťte ji pouze tehdy, když náhled odpovídá záměru.
4. Upravte ukázkový soubor na jedné straně, obnovte relaci a zkontrolujte výsledek na druhé. Mutagen může přenášet změny i mazání; před volbou režimu pro důležitá data si přečtěte [oficiální dokumentaci synchronizace](https://mutagen.io/documentation/introduction/getting-started).
5. Po testu zastavte a odstraňte dočasnou relaci. Viz [přehled nastavení](settings-reference.md) a [přehled aplikace](index.md).

Základní a pokročilý režim mění prezentaci stejného Mutagen CLI. Pokročilý režim zpřístupňuje další volby a potvrzení rizik. Konfiguraci existující relace spravuje Mutagen; změna profilu pro nové relace ji potichu nepřepíše. Před nahrazením relace zkontrolujte náhled.

### SSH endpointy

SSH používá místního klienta OpenSSH a běžnou konfiguraci, klíče i aliasy. Nejprve nastavte a ověřte hostitele v OpenSSH. Test spojení MutaUI vyžaduje striktní kontrolu host klíče; nepřidává neznámé klíče ani neobchází varování při změně klíče. Před přijetím ověřte klíč důvěryhodným kanálem. Viz [dokumentace SSH transportu Mutagenu](https://mutagen.io/documentation/transports/ssh) a [SSH profily](ssh-profiles.md).

### Stažení, podpora a ověření

Aplikaci stahujte pouze ze stránky GitHub Releases projektu. Vydání obsahují kontrolní součty; CI vytváří build attestations a podepisuje balíčky, jsou-li nastaveny potřebné podpisové údaje. Lokální self-test ani kontrola balíčku v CI nedokládá ruční instalaci na každé podporované verzi OS. Aktuální důkazy a mezery jsou v [přehledu akceptace](acceptance-traceability.md); funkce a snímky obrazovky popisuje [přehled aplikace](index.md) a [galerie snímků](screenshots.md).

Kontrola vydání je ve výchozím stavu vypnutá. V **Nastavení → Upozornění** zapněte a uložte **Při spuštění kontrolovat vydání**, čímž povolíte načtení veřejných metadat GitHub Releases při spuštění. Na stejné stránce lze kontrolu spustit ručně, pokud je volba zapnutá. MutaUI neposílá údaje o zařízení, relacích, cestách ani koncových bodech a aktualizace nestahuje ani neinstaluje. Před stažením ověřte podpisy a kontrolní součty na stránce vydání.

Pokyny k nastavení a obnově najdete v [řešení potíží](troubleshooting.md) a [obnově po konfliktu](manual-conflict-resolution.md). Opakovatelnou chybu nahlaste v issue trackeru projektu a uveďte verzi OS, vydání MutaUI, verzi Mutagenu a potřebný diagnostický výstup. Před sdílením logů odstraňte tajné údaje a soukromé cesty.
