# Linux setup / Nastavení Linuxu

## English

1. Download the x86-64 AppImage or amd64 Debian package from GitHub Releases. Prebuilt binaries require **`GLIBC >= 2.38`**. This runtime floor is not a distro support guarantee; see the [capability matrix](../capability-matrix.md) for validated targets.
2. For AppImage, mark executable (`chmod +x <file>.AppImage`) and launch. On systems without FUSE or on multi-user systems, isolate extraction via `TMPDIR="${XDG_RUNTIME_DIR:-/tmp/user-$(id -u)}" APPIMAGE_EXTRACT_AND_RUN=1 ./<file>.AppImage`. On Debian 13+ or Ubuntu 24.04+, install the package with `sudo apt install ./<file>.deb`.
3. Install Mutagen CLI separately using the [official guide](https://mutagen.io/documentation/introduction/installation). Homebrew command: `brew install mutagen-io/mutagen/mutagen`. Check it in a terminal with `mutagen version`.
4. Launch MutaUI and follow [First sync](first-sync.md) using temporary local folders.
5. Optional: per-user Nautilus, Dolphin, and Nemo folder actions need no administrator access. Set `APPIMAGE` to the installed AppImage path, for example `APPIMAGE="$HOME/Applications/MutaUI.AppImage"`, then run `"$APPIMAGE" --install-linux-file-manager-integration`. Remove actions with `"$APPIMAGE" --remove-linux-file-manager-integration`. The install option requires the packaged AppImage; source-mode installs are not supported. If the AppImage moved, remove the old integration before installing from its new path.

Release CI installs and self-tests the Debian package and runs the AppImage self-test on Ubuntu. Older distributions (Ubuntu 22.04 LTS, Debian 12 with GLIBC <= 2.36) require running from source. See the [capability matrix](../capability-matrix.md), [installation guide](../installation.md), and [Troubleshooting](../troubleshooting.md).

## Česky

1. Z GitHub Releases stáhněte x86-64 AppImage nebo amd64 balíček Debian. Předpřipravené binárky vyžadují **`GLIBC >= 2.38`**. Jde o minimální běhovou verzi, ne záruku podpory distribuce; ověřené cíle uvádí [matice schopností](../capability-matrix.md).
2. U AppImage povolte spouštění (`chmod +x <soubor>.AppImage`) a spusťte jej. Na systémech bez FUSE nebo na sdílených víceuživatelských počítačích izolujte extrakci pomocí `TMPDIR="${XDG_RUNTIME_DIR:-/tmp/user-$(id -u)}" APPIMAGE_EXTRACT_AND_RUN=1 ./<soubor>.AppImage`. V Debianu 13+ nebo Ubuntu 24.04+ nainstalujte balíček příkazem `sudo apt install ./<soubor>.deb`.
3. Mutagen CLI nainstalujte zvlášť podle [oficiálního návodu](https://mutagen.io/documentation/introduction/installation). Příkaz pro Homebrew: `brew install mutagen-io/mutagen/mutagen`. V terminálu ověřte `mutagen version`.
4. Spusťte MutaUI a proveďte [první synchronizaci](first-sync.md) nad dočasnými místními složkami.
5. Volitelně: akce pro Nautilus, Dolphin a Nemo se instalují jen aktuálnímu uživateli a nevyžadují práva správce. Nastavte `APPIMAGE` na cestu k nainstalovanému AppImage, například `APPIMAGE="$HOME/Applications/MutaUI.AppImage"`, a spusťte `"$APPIMAGE" --install-linux-file-manager-integration`. Odebrání: `"$APPIMAGE" --remove-linux-file-manager-integration`. Instalace vyžaduje zabalený AppImage; spuštění ze zdrojového kódu podporováno není. Pokud jste AppImage přesunuli, nejdřív odeberte starou integraci a pak ji nainstalujte z nové cesty.

Release CI instaluje a testuje balíček Debian a spouští self-test AppImage na Ubuntu. Starší distribuce (Ubuntu 22.04 LTS, Debian 12 s GLIBC <= 2.36) vyžadují spuštění ze zdrojového kódu. Viz [matice schopností](../capability-matrix.md), [instalační návod](../installation.md) a [řešení potíží](../troubleshooting.md).
