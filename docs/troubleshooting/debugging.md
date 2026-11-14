# Debugging safely / Bezpečné ladění

## English

Record the application release, OS/architecture, Mutagen version, endpoint type, exact affected session ID, and a minimal reproduction. Prefer a disposable local setup. Capture the command preview and sanitized error/status text; do not collect private-key contents or full production session data. MutaUI can follow an existing local log file, but Mutagen does not expose a complete persistent stream of remote-agent debug logs through the standard CLI.

Before sharing, remove credentials, URL passwords, private paths, hostnames, account names, tokens, and personal data. The repository-root `SUPPORT.md` lists report fields; use its security policy for vulnerability reports.

## Česky

Zaznamenejte vydání aplikace, OS/architekturu, verzi Mutagenu, typ endpointu, přesné ID relace a nejmenší reprodukci. Upřednostněte dočasné místní prostředí. Přiložte náhled příkazu a očištěný text chyby/stavu; nesbírejte obsah soukromých klíčů ani úplná produkční data relace. MutaUI umí sledovat existující místní log, ale Mutagen přes standardní CLI neposkytuje úplný trvalý proud ladicích logů vzdáleného agenta.

Před sdílením odstraňte přihlašovací údaje, hesla URL, soukromé cesty, hostitele, účty, tokeny a osobní data. Pole hlášení popisuje kořenový soubor `SUPPORT.md`; postup pro bezpečnostní chyby uvádí jeho bezpečnostní politika.
