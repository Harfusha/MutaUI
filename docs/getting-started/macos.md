# macOS setup / Nastavení macOS

## English

1. Download the disk image (DMG) for Apple Silicon (`arm64`) or Intel (`x86_64`) from GitHub Releases.
2. Open the DMG and drag `MutagenControl.app` to the `Applications` shortcut.
3. Because community builds are ad-hoc signed and unnotarized (the project operates without an Apple Developer ID certificate), macOS Gatekeeper requires explicit confirmation on first launch: in Finder, navigate to `/Applications`, right-click (or Control-click) `MutagenControl.app`, choose **Open**, and confirm in the dialog (or go to **System Settings > Privacy & Security** and click **Open Anyway**).
4. Install Mutagen CLI separately. The [official guide](https://mutagen.io/documentation/introduction/installation) lists Homebrew and release downloads; Homebrew command: `brew install mutagen-io/mutagen/mutagen`.
5. In Terminal, run `mutagen version`, then launch MutaUI. Onboarding checks the CLI but does not connect to endpoints.
6. Follow [First sync](first-sync.md) with disposable local folders.

Release CI builds ad-hoc signed DMG packages on Apple Silicon and Intel runners; commercial Developer ID signing and notarization remain opt-in release gates when credentials are provided. See [capability matrix](../capability-matrix.md) and [Troubleshooting](../troubleshooting.md).

## Česky

1. Z GitHub Releases stáhněte diskový obraz (DMG) pro Apple Silicon (`arm64`) nebo Intel (`x86_64`).
2. Otevřete jej a přetáhněte `MutagenControl.app` na zástupce `Applications`.
3. Komunitní vydání jsou podepsána ad-hoc a nejsou notarizována (projekt nevlastní komerční certifikát Apple Developer ID), Gatekeeper proto při prvním spuštění vyžaduje potvrzení: ve Finderu otevřete `/Applications`, klikněte pravým tlačítkem (nebo Control-kliknutí) na `MutagenControl.app`, zvolte **Otevřít** a potvrďte dialog (případně v **Nastavení systému > Soukromí a zabezpečení** klikněte na **Přesto otevřít**).
4. Mutagen CLI nainstalujte zvlášť. [Oficiální návod](https://mutagen.io/documentation/introduction/installation) uvádí Homebrew i stažení vydání; příkaz pro Homebrew: `brew install mutagen-io/mutagen/mutagen`.
5. V Terminálu spusťte `mutagen version` a potom MutaUI. Průvodce CLI ověří, ale k endpointům se nepřipojuje.
6. Proveďte [první synchronizaci](first-sync.md) nad dočasnými místními složkami.

Release CI vytváří ad-hoc podepsané balíčky DMG na Apple Silicon i Intel runneru; komerční podpis a notarizace jsou podmíněny konfigurací klíčů v repozitáři. Viz [matice schopností](../capability-matrix.md) a [řešení potíží](../troubleshooting.md).
