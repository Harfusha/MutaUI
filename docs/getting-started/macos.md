# macOS setup / Nastavení macOS

## English

1. Download the notarized DMG for Apple Silicon or Intel from GitHub Releases. Open it and drag `MutagenControl.app` to the `Applications` shortcut.
2. Install Mutagen CLI separately. The [official guide](https://mutagen.io/documentation/introduction/installation) lists Homebrew and release downloads; Homebrew command: `brew install mutagen-io/mutagen/mutagen`.
3. In Terminal, run `mutagen version`, then launch MutaUI. Onboarding checks the CLI but does not connect to endpoints.
4. Follow [First sync](first-sync.md) with disposable local folders.

Release CI builds and signs/notarizes macOS artifacts on Apple Silicon and Intel runners. This does not establish manual runtime, accessibility, or upgrade acceptance on every macOS version. See [capability matrix](../capability-matrix.md) and [Troubleshooting](../troubleshooting.md).

## Česky

1. Z GitHub Releases stáhněte notarizovaný DMG pro Apple Silicon nebo Intel. Otevřete jej a přetáhněte `MutagenControl.app` na zástupce `Applications`.
2. Mutagen CLI nainstalujte zvlášť. [Oficiální návod](https://mutagen.io/documentation/introduction/installation) uvádí Homebrew i stažení vydání; příkaz pro Homebrew: `brew install mutagen-io/mutagen/mutagen`.
3. V Terminálu spusťte `mutagen version` a potom MutaUI. Průvodce CLI ověří, ale k endpointům se nepřipojuje.
4. Proveďte [první synchronizaci](first-sync.md) nad dočasnými místními složkami.

Release CI vytváří a podepisuje/notarizuje balíčky na Apple Silicon i Intel runneru. Tím není prokázáno ruční ověření běhu, přístupnosti a aktualizace na každé verzi macOS. Viz [matice schopností](../capability-matrix.md) a [řešení potíží](../troubleshooting.md).
