# Sync configuration / Konfigurace sync

## English

MutaUI presents native sync values as read-only current state and keeps proposed replacement values separate. The New Sync preview resolves supported global defaults, explicit CLI values, and appended ignore rules when their provenance is known. Unknown fields remain visible and are not silently discarded. Supported options are checked against the installed CLI; version-dependent behavior must not be inferred from a remembered Mutagen release.

Basic and Advanced views share the same state model. Resolved and replica modes can have destructive impact; inspect ALPHA/BETA direction and the exact command before proceeding. Replica mode requires backup selection and a typed high-risk confirmation. See [sync wizard](../user/sync-wizard.md), [settings reference](../settings-reference.md), and [capability matrix](../capability-matrix.md).

## Česky

MutaUI zobrazuje nativní hodnoty sync pouze pro čtení a návrhy na nahrazení ukládá zvlášť. Náhled New Sync skládá podporované globální výchozí hodnoty, výslovné CLI volby a přidaná ignore pravidla, pokud zná jejich původ. Neznámá pole zůstávají viditelná a potichu se nezahazují. Podporované volby se kontrolují podle nainstalovaného CLI; chování se neodvozuje z paměti o jiné verzi Mutagenu.

Základní a pokročilý režim sdílejí stejný model stavu. Režimy resolved a replica mohou být destruktivní; před pokračováním ověřte směr ALPHA/BETA a přesný příkaz. Replica vyžaduje volbu zálohy a přesnou textovou potvrzovací frázi. Viz [průvodce sync](../user/sync-wizard.md), [přehled nastavení](../settings-reference.md) a [matici schopností](../capability-matrix.md).
