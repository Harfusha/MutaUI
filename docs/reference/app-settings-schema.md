# Application settings schema / Schéma nastavení aplikace

## English

The local settings file is a JSON object with `schema_version: 1`. Settings are validated against typed defaults. Invalid fields fall back to defaults with warnings; unknown keys are preserved for forward compatibility. Files from a newer schema cannot be overwritten. Writes use a temporary file and atomic replace. If an invalid existing file is replaced, the first `.invalid.bak` copy is retained.

Legacy migration preserves the exact original bytes in a sibling `.pre-migration.*.bak` file, writes and reads back the current schema, and restores the source bytes if verification fails. Rollback accepts only a valid sibling pre-migration backup and creates a `.pre-rollback.*.bak` of the current settings first. Session preferences are bounded and validate notes, notification flags, and sync/forward proposals separately. The typed UI reference is generated from the same help registry: [configuration fields](configuration-fields.md).

## Česky

Místní soubor nastavení je JSON objekt s `schema_version: 1`. Hodnoty se validují podle typovaných výchozích hodnot. Neplatná pole se s varováním nahradí výchozí hodnotou; neznámé klíče se zachovají kvůli dopředné kompatibilitě. Soubor z novějšího schématu nelze přepsat. Zápis používá dočasný soubor a atomické nahrazení. Při nahrazení neplatného souboru zůstává zachována první kopie `.invalid.bak`.

Migrace zachová přesné původní bajty v sousedním souboru `.pre-migration.*.bak`, zapíše aktuální schéma a ověří jeho načtení. Při chybě obnoví původní bajty. Rollback přijímá pouze platnou sousední zálohu migrace a nejdříve vytváří zálohu současného souboru `.pre-rollback.*.bak`. Předvolby relací jsou omezené a odděleně validují poznámky, oznámení i návrhy sync/forward. Typovaná reference UI vychází ze stejného registru nápovědy: [pole konfigurace](configuration-fields.md).
