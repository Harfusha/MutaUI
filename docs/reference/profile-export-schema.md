# Profile export schema / Schéma přenosu profilů

## English

Portable bundles use schema version 1 and a 5 MiB maximum. The JSON envelope contains `schema_version`, `created_at`, `created_with`, `app_version`, `platform`, `machine_paths_included`, `items`, and `checksum`. `items` has exactly four lists/objects: connection profiles, allowlisted preferences, ignore presets, and project references. The SHA-256 checksum covers canonical JSON for the envelope without the checksum field.

Exports omit credentials, key material, executable paths, Mutagen session state, and history. Absolute local paths and URL passwords are redacted by default. Including machine-specific endpoint paths requires explicit opt-in and is recorded in the envelope. Import validates schema, checksum, size, profiles, preferences, and presets before displaying per-profile create/merge/skip choices; stale profile-store changes invalidate the preview.

## Česky

Přenosný balíček používá schéma verze 1 a maximální velikost 5 MiB. JSON obálka obsahuje `schema_version`, `created_at`, `created_with`, `app_version`, `platform`, `machine_paths_included`, `items` a `checksum`. `items` má přesně čtyři položky: profily připojení, povolené preference, ignore presety a reference projektů. SHA-256 kontrolní součet pokrývá kanonický JSON obálky bez pole checksum.

Export vynechává přihlašovací údaje, obsah klíčů, cesty k programům, stav relací Mutagenu a historii. Absolutní místní cesty a hesla v URL jsou standardně redigovány. Zahrnutí strojově specifických endpointů vyžaduje výslovnou volbu a uloží se do obálky. Import ověří schéma, součet, velikost, profily, preference a presety a teprve poté nabídne vytvořit/sloučit/přeskočit; změna místního úložiště profilů po náhledu jeho použití zablokuje.
