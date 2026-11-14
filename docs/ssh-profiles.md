# SSH profiles / SSH profily

MutaUI uses the local OpenSSH client for SSH endpoints. It does not implement a separate SSH transport or copy your private keys. Mutagen remains responsible for establishing SSH-backed endpoints and sessions. Read the official [Mutagen SSH transport guide](https://mutagen.io/documentation/transports/ssh) before configuring a remote endpoint.

## Inspect an existing profile

Open **Settings → SSH Profiles** to inspect aliases from `~/.ssh/config` and bounded `Include` files. MutaUI reads those files without writing them. Selecting an alias displays effective options reported by local `ssh -G`; it does not connect to the host. The connection test is explicit and uses batch mode with `StrictHostKeyChecking=yes`.

## Host key errors

An unknown host key or a key that changed is a security check, not a setup shortcut. Confirm the host fingerprint with its administrator through a trusted channel and update OpenSSH configuration only after verification. MutaUI does not add keys to `known_hosts`, rewrite SSH configuration, inspect private-key contents, or disable host-key checking. Do not bypass a mismatch to make a test pass.

## Before creating a Mutagen session

1. Confirm that the local OpenSSH client works with the alias and identity you intend to use.
2. Verify host identity and network access independently.
3. In MutaUI, inspect the selected alias and run the explicit connection check only when you intend to connect.
4. In the sync or forward wizard, review the remote endpoint and complete operation preview before creating a session.

SSH authentication and host-key behavior are also described in the [installation guide](installation.md#ssh-endpoints). Use the [troubleshooting guide](troubleshooting.md#ssh-connection-fails) for connection failures.

## Kontrola SSH profilů

MutaUI používá pro SSH endpointy místního klienta OpenSSH. Nevytváří vlastní SSH transport ani nekopíruje soukromé klíče. SSH endpointy a relace vytváří Mutagen. Před nastavením vzdáleného endpointu si přečtěte oficiální [dokumentaci SSH transportu Mutagenu](https://mutagen.io/documentation/transports/ssh).

### Kontrola existujícího profilu

V **Nastavení → SSH Profiles** lze prohlížet aliasy z `~/.ssh/config` a omezeně načítaných souborů `Include`. MutaUI je čte, ale nezapisuje do nich. Výběr aliasu zobrazí efektivní volby, které vrátí místní `ssh -G`; k hostiteli se nepřipojí. Test spojení je výslovný a používá batch režim spolu s `StrictHostKeyChecking=yes`.

### Chyba host klíče

Neznámý nebo změněný host klíč je bezpečnostní kontrola, ne překážka k obejití. Ověřte fingerprint u správce hostitele důvěryhodným kanálem a konfiguraci OpenSSH změňte až po ověření. MutaUI nepřidává klíče do `known_hosts`, nepřepisuje SSH konfiguraci, nečte obsah soukromých klíčů a nevypíná kontrolu host klíče. Neshodu neobcházejte jen kvůli úspěchu testu.

### Před vytvořením relace Mutagenu

1. Ověřte, že místní klient OpenSSH funguje se zamýšleným aliasem a identitou.
2. Nezávisle ověřte identitu hostitele a síťové spojení.
3. V MutaUI zkontrolujte vybraný alias a spusťte výslovný test spojení jen tehdy, když se chcete připojit.
4. V průvodci synchronizací nebo přeposíláním zkontrolujte vzdálený endpoint a celý náhled operace před vytvořením relace.

Další informace o SSH ověřování a host klíčích jsou v [instalačním návodu](installation.md#ssh-endpoints). Při chybě spojení použijte [řešení potíží](troubleshooting.md#ssh-connection-fails).
