# Remote conflict inspection security boundary

The Conflict Inspector reads a single SSH/SFTP conflict copy after the operator selects the exact conflict and side, selects a private key, and confirms the displayed remote target. It is an opt-in read-only operation; it never modifies the remote endpoint.

## Connection and path controls

- The remote host must already have a matching entry in the user's `known_hosts`. Unknown or changed host keys fail closed.
- The adapter uses only the explicitly selected private key. SSH-agent and implicit key discovery are disabled. The UI does not save a remote password or install keys.
- Reads use SFTP. Symlinks and paths outside the selected endpoint root are rejected.
- Transfer size is limited to 2 MiB. Network timeouts default to 10 seconds and cannot exceed 30 seconds.
- A temporary local copy is hashed, classified as text or binary, and deleted when the inspector closes. For local/SSH comparisons, the local copy is kept in the same temporary folder and an explicitly selected diff tool opens both copies. Two remote endpoints are not supported by the diff UI.
- The JSONL audit stores hashes of host and remote target, content hash, size, and host-key fingerprint. It omits usernames, private-key paths, and raw remote paths.

## Verification limits

Unit coverage uses an injected SSH/SFTP test client. The Linux integration suite also starts an isolated OpenSSH server and exercises `ParamikoRemoteInspector` over real SFTP: a pinned host key permits a read of a test-owned file, a wrong key is rejected, and audit output is checked for redaction. This proves local protocol integration, not behavior against an external host or a packaged installed application. Cross-platform, installed-user, and network-latency acceptance remain open; the manual checklist and evidence status are tracked in the acceptance traceability report.

## Hranice zabezpečení vzdálené kontroly

Conflict Inspector čte jednu SSH/SFTP kopii konfliktu až poté, co obsluha vybere konkrétní konflikt i stranu, soukromý klíč a potvrdí zobrazený vzdálený cíl. Jde o dobrovolnou operaci pouze pro čtení; vzdálený cíl nikdy nemění.

### Připojení a cesty

- Vzdálený host musí mít odpovídající záznam v uživatelském `known_hosts`. Neznámý nebo změněný klíč připojení odmítne.
- Adaptér použije pouze výslovně vybraný soukromý klíč. SSH-agent a automatické hledání klíčů jsou vypnuté. UI neukládá vzdálené heslo ani neinstaluje klíče.
- Čtení používá SFTP. Symbolické odkazy a cesty mimo kořen vybraného endpointu odmítne.
- Přenos má limit 2 MiB. Síťový timeout je standardně 10 sekund a nelze nastavit nad 30 sekund.
- Dočasná místní kopie se zahashuje, označí jako textová či binární a smaže při zavření inspektoru. Pro porovnání místní a SSH kopie se obě uloží do stejné dočasné složky a otevřou ve výslovně zvoleném diff nástroji. Dva vzdálené endpointy UI porovnat neumí.
- JSONL audit ukládá hashe hostu a vzdáleného cíle, hash obsahu, velikost a otisk host klíče. Neobsahuje uživatelská jména, cesty ke klíčům ani surové vzdálené cesty.

### Meze ověření

Jednotkové testy používají vloženého testovacího SSH/SFTP klienta. Linuxová integrační sada navíc spouští izolovaný OpenSSH server a přes skutečné SFTP ověřuje `ParamikoRemoteInspector`: připnutý host key dovolí přečíst testovací soubor, chybný klíč je odmítnut a audit neprozrazuje citlivé údaje. To dokládá místní integraci protokolu, nikoli chování vůči externímu hostu nebo zabalené nainstalované aplikaci. Stále chybí ověření na dalších platformách, u nainstalované aplikace a měření latence; ruční checklist a stav důkazů jsou v přehledu akceptace.
