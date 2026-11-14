# Windows setup / Nastavení Windows

## English

1. Download the Windows x64 installer or portable ZIP from the project’s GitHub Releases page. Verify the release signature when present and compare the artifact with `SHA256SUMS.txt`.
2. Run the per-user installer (default: `%LOCALAPPDATA%\Programs\Mutagen Control`) or extract the portable ZIP to a new folder and run `MutagenControl.exe`. Do not merge folders from different releases. The installer does not require administrator rights; uninstall preserves user settings and history.
3. Install the Mutagen CLI separately using the [official guide](https://mutagen.io/documentation/introduction/installation). In PowerShell, run `mutagen version`; restart MutaUI if you changed `PATH`.
4. Launch MutaUI. Onboarding checks the local CLI version and sync/forward help, but does not connect to endpoints automatically.
5. Follow [First sync](first-sync.md) using disposable local folders before valuable data.

See [Troubleshooting](../troubleshooting.md), the [capability matrix](../capability-matrix.md), and the full [installation guide](../installation.md). Windows release packages are built in CI; manual acceptance on every Windows version remains an open release gate.

## Česky

1. Ze stránky GitHub Releases projektu stáhněte instalátor pro Windows x64 nebo přenosný ZIP. Je-li podpis k dispozici, ověřte jej a porovnejte soubor s `SHA256SUMS.txt`.
2. Spusťte instalátor pro aktuálního uživatele (výchozí umístění: `%LOCALAPPDATA%\Programs\Mutagen Control`) nebo rozbalte přenosný ZIP do nové složky a spusťte `MutagenControl.exe`. Složky různých vydání neslučujte. Instalátor nepotřebuje práva správce; odinstalace zachová uživatelská nastavení a historii.
3. Samostatně nainstalujte Mutagen CLI podle [oficiálního návodu](https://mutagen.io/documentation/introduction/installation). V PowerShellu spusťte `mutagen version`; pokud jste změnili `PATH`, MutaUI restartujte.
4. Spusťte MutaUI. Průvodce ověří verzi místního CLI a nápovědu k sync/forward, ale automaticky se nepřipojuje k endpointům.
5. Nejdříve proveďte [první synchronizaci](first-sync.md) nad dočasnými místními složkami.

Viz [řešení potíží](../troubleshooting.md), [matici schopností](../capability-matrix.md) a úplný [instalační návod](../installation.md). Windows balíčky vznikají v CI; ruční akceptace na každé verzi Windows zůstává otevřenou branou vydání.
