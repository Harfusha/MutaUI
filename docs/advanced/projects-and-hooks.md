# Projects and hooks / Projekty a hooky

## English

Native project actions operate on a selected `mutagen.yml` project. File creation is create-if-absent; external edits are surfaced for review. The project viewer shows hooks and custom commands without executing them. Starting or running a hook can execute arbitrary shell code and therefore requires explicit high-risk confirmation. Preview the exact arguments and commands, review the project source hash, and verify the selected project scope.

See [Native Mutagen Projects](../project-yaml-editing.md), [remote inspection boundaries](../remote-inspection.md), and [security analysis](../security/static-analysis.md).

## Česky

Akce nativního projektu míří na vybraný projekt `mutagen.yml`. Soubor se vytváří pouze tehdy, když ještě neexistuje; vnější změny se zobrazí ke kontrole. Prohlížeč ukazuje hooky a vlastní příkazy, ale nespouští je. Spuštění hooku může provést libovolný shell kód, proto vyžaduje výslovné vysoce rizikové potvrzení. Zkontrolujte přesné argumenty a příkazy, hash zdroje projektu i vybraný rozsah.

Viz [Nativní Mutagen Projects](../project-yaml-editing.md), [hranice vzdálené inspekce](../remote-inspection.md) a [bezpečnostní analýzu](../security/static-analysis.md).
