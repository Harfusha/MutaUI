# First sync / První synchronizace

## English

1. Install Mutagen CLI separately and confirm `mutagen version` works. Read the official [Getting Started guide](https://mutagen.io/documentation/introduction/getting-started).
2. Create two disposable local folders with a few sample files. Do not use valuable or sole copies of data for a first run.
3. Launch MutaUI, choose **New Sync**, select the folders, and inspect mode, direction, endpoint paths, and the complete operation preview.
4. Start only when the preview matches your intent. Change a sample file on one side, refresh the session, and inspect the other side. Mutagen can propagate modifications and deletions.
5. Stop and remove the disposable session when done. See [Basic vs Advanced](basic-vs-advanced.md) and [Troubleshooting](../troubleshooting.md) before connecting important data.

For SSH, read [SSH profiles](../ssh-profiles.md) and the official [SSH transport guide](https://mutagen.io/documentation/transports/ssh). Unknown or changed host keys must be verified through a trusted channel; never bypass strict checking.

## Česky

1. Samostatně nainstalujte Mutagen CLI a ověřte příkaz `mutagen version`. Přečtěte si oficiální [Začínáme](https://mutagen.io/documentation/introduction/getting-started).
2. Vytvořte dvě dočasné místní složky s několika ukázkovými soubory. Při prvním pokusu nepoužívejte důležitá data ani jejich jedinou kopii.
3. Spusťte MutaUI, zvolte **New Sync**, vyberte složky a zkontrolujte režim, směr, cesty endpointů i celý náhled operace.
4. Spusťte synchronizaci jen tehdy, když náhled odpovídá záměru. Upravte vzorový soubor na jedné straně, obnovte relaci a zkontrolujte druhou stranu. Mutagen může přenášet změny i mazání.
5. Po testu zastavte a odstraňte dočasnou relaci. Před připojením důležitých dat si přečtěte [Základní a pokročilý režim](basic-vs-advanced.md) a [řešení potíží](../troubleshooting.md).

Pro SSH si přečtěte [SSH profily](../ssh-profiles.md) a oficiální [dokumentaci SSH transportu](https://mutagen.io/documentation/transports/ssh). Neznámé nebo změněné host klíče ověřte důvěryhodným kanálem; nikdy neobcházejte striktní kontrolu.
