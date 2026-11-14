# Native projects / Nativní projekty

## English

MutaUI can inspect and edit native `mutagen.yml` projects while preserving comments and unknown fields through the round-trip YAML adapter. Creating a project does not overwrite an existing file. External edits are detected and presented for review. Project hooks and custom commands are shown in previews and can execute arbitrary shell code only after explicit user confirmation.

See [Native Mutagen Projects](../project-yaml-editing.md) for file behavior and [security notes](../security/static-analysis.md) before enabling hooks.

## Česky

MutaUI umí prohlížet a upravovat nativní projekty `mutagen.yml` a pomocí round-trip YAML adaptéru zachovává komentáře i neznámá pole. Vytvoření nepřepíše existující soubor. Externí změny se zobrazí ke kontrole. Hooky a vlastní příkazy se nejprve ukážou v náhledu; protože mohou spustit libovolný shell kód, vyžadují výslovné potvrzení uživatele.

Chování souborů popisují [Nativní Mutagen Projects](../project-yaml-editing.md). Před povolením hooků si přečtěte [bezpečnostní poznámky](../security/static-analysis.md).
