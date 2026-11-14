# Common errors / Časté chyby

## English

- **Mutagen not found:** install the CLI separately, ensure `mutagen` is on `PATH`, run `mutagen version`, then restart MutaUI.
- **Unsupported option:** the installed CLI or endpoint does not advertise the requested capability. Do not force the command; inspect the [capability matrix](../capability-matrix.md).
- **SSH host key unknown or changed:** stop and verify the fingerprint with the host administrator through a trusted channel. Do not disable strict checking.
- **Sync result differs from expectation:** pause further changes, inspect the exact mode, endpoint direction, and preview; recover from a known-good copy before another mutation.
- **Settings cannot be saved:** inspect validation warnings and schema version. Newer-schema files are protected from overwrite; keep the original while resolving the version mismatch.
- **Linux app fails to start:** confirm runtime dependencies for the chosen distribution. Only the Ubuntu CI image currently has package self-test evidence.

See [Troubleshooting](../troubleshooting.md), [installation](../installation.md), and [recovery](backup-and-recovery.md).

## Česky

- **Mutagen nebyl nalezen:** nainstalujte CLI zvlášť, zpřístupněte `mutagen` v `PATH`, spusťte `mutagen version` a restartujte MutaUI.
- **Nepodporovaná volba:** nainstalované CLI nebo endpoint tuto schopnost neuvádí. Příkaz nevynucujte; ověřte [matici schopností](../capability-matrix.md).
- **Neznámý nebo změněný SSH host klíč:** zastavte se a ověřte fingerprint u správce důvěryhodným kanálem. Striktní kontrolu nevypínejte.
- **Výsledek sync neodpovídá očekávání:** nepokračujte v dalších změnách, zkontrolujte přesný režim, směr endpointů a náhled; před další mutací obnovujte ze známé dobré kopie.
- **Nastavení nelze uložit:** prohlédněte validační varování a verzi schématu. Soubor z novější verze se chrání před přepsáním; při řešení neshody zachovejte originál.
- **Aplikace na Linuxu nenastartuje:** zkontrolujte runtime závislosti distribuce. Self-test balíčku je zatím doložen jen pro Ubuntu CI.

Viz [řešení potíží](../troubleshooting.md), [instalaci](../installation.md) a [obnovu](backup-and-recovery.md).
