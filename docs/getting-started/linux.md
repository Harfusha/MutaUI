# Linux setup / Nastavení Linuxu

## English

1. Download the x86-64 AppImage or amd64 Debian package from GitHub Releases.
2. For AppImage, mark the downloaded file executable (`chmod +x <downloaded-file>.AppImage`) and launch it. On Debian or Ubuntu, install the package with `sudo apt install ./<downloaded-file>.deb`.
3. Install Mutagen CLI separately using the [official guide](https://mutagen.io/documentation/introduction/installation). Homebrew command: `brew install mutagen-io/mutagen/mutagen`. Check it in a terminal with `mutagen version`.
4. Launch MutaUI and follow [First sync](first-sync.md) using temporary local folders.
5. Optional: per-user Nautilus and Dolphin folder actions need no administrator access. Set `APPIMAGE` to the installed AppImage path, for example `APPIMAGE="$HOME/Applications/MutaUI.AppImage"`, then run `"$APPIMAGE" --install-linux-file-manager-integration`. Remove actions with `"$APPIMAGE" --remove-linux-file-manager-integration`. The install option requires the packaged AppImage; source-mode installs are not supported. If the AppImage moved, remove the old integration before installing from its new path.

Release CI installs and self-tests the Debian package and runs the AppImage self-test on Ubuntu. Other distributions, desktop environments, tray behavior, and manual upgrade/recovery remain unverified. See the [capability matrix](../capability-matrix.md), [installation guide](../installation.md), and [Troubleshooting](../troubleshooting.md).

## Česky

1. Z GitHub Releases stáhněte x86-64 AppImage nebo amd64 balíček Debian.
2. U AppImage povolte spouštění (`chmod +x <stažený-soubor>.AppImage`) a spusťte jej. V Debianu nebo Ubuntu nainstalujte balíček příkazem `sudo apt install ./<stažený-soubor>.deb`.
3. Mutagen CLI nainstalujte zvlášť podle [oficiálního návodu](https://mutagen.io/documentation/introduction/installation). Příkaz pro Homebrew: `brew install mutagen-io/mutagen/mutagen`. V terminálu ověřte `mutagen version`.
4. Spusťte MutaUI a proveďte [první synchronizaci](first-sync.md) nad dočasnými místními složkami.
5. Volitelně: akce pro Nautilus a Dolphin se instalují jen aktuálnímu uživateli a nevyžadují práva správce. Nastavte `APPIMAGE` na cestu k nainstalovanému AppImage, například `APPIMAGE="$HOME/Applications/MutaUI.AppImage"`, a spusťte `"$APPIMAGE" --install-linux-file-manager-integration`. Odebrání: `"$APPIMAGE" --remove-linux-file-manager-integration`. Instalace vyžaduje zabalený AppImage; spuštění ze zdrojového kódu podporováno není. Pokud jste AppImage přesunuli, nejdřív odeberte starou integraci a pak ji nainstalujte z nové cesty.

Release CI instaluje a testuje balíček Debian a spouští self-test AppImage na Ubuntu. Ostatní distribuce, desktopová prostředí, tray a ruční aktualizace/obnova zatím ověřeny nejsou. Viz [matice schopností](../capability-matrix.md), [instalační návod](../installation.md) a [řešení potíží](../troubleshooting.md).
