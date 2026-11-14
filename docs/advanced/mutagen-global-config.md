# Global Mutagen configuration / Globální konfigurace Mutagenu

## English

The global `~/.mutagen.yml` file is Mutagen-owned configuration. MutaUI's editor uses bounded UTF-8 input and a round-trip YAML adapter that preserves comments and unknown keys. It rejects duplicate keys and a non-mapping root. The current file is backed by its original bytes and hash; if an external edit occurs while the editor is open, reload, merge, or cancel instead of overwriting it blindly.

The effective configuration preview distinguishes known defaults, global values, session overrides, and unknown provenance. A global change affects new sessions only. Existing sessions require an explicit reviewed replacement. See [settings reference](../settings-reference.md), [reconfiguration preview](../reconfiguration-preview.md), and [architecture decisions](../architecture.md).

## Česky

Globální soubor `~/.mutagen.yml` vlastní Mutagen. Editor MutaUI používá omezený UTF-8 vstup a round-trip YAML adaptér, který zachová komentáře a neznámé klíče. Odmítá duplicitní klíče a kořen, který není mapou. Původní bajty a hash chrání před přepsáním; zjistí-li editor souběžnou vnější změnu, zvolte načtení, sloučení nebo zrušení.

Náhled výsledné konfigurace rozlišuje známé výchozí hodnoty, globální hodnoty, přepsání relace a neznámý původ hodnoty. Globální změna platí jen pro nové relace. Existující relace vyžaduje výslovně potvrzené nahrazení. Viz [přehled nastavení](../settings-reference.md), [náhled změny](../reconfiguration-preview.md) a [architekturu](../architecture.md).
