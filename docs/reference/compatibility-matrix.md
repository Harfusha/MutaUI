# Compatibility matrix / Matice kompatibility

## English

Compatibility is discovered from the installed Mutagen CLI and endpoint capabilities. Packaging existence does not prove that every platform version is supported.

### Operating system and packaging matrix

| Operating System | Architecture | Package Types | Signature Status | Minimum Runtime Baseline | Verification / Support Status |
|---|---|---|---|---|---|
| **Windows 10 / 11** | `x86_64` (`x64`) | Inno Setup installer, Portable ZIP, Single-file EXE | Unsigned (`Authenticode NotSigned`) | Windows 10 build 19041+ | CI test passed. SmartScreen displays unknown publisher warning on first run. User settings and history are preserved across same-user upgrades and uninstalls. |
| **macOS 12.0+** (Monterey, Ventura, Sonoma, Sequoia) | `arm64` (Apple Silicon), `x86_64` (Intel) | Disk Image (`.dmg`) | Ad-hoc signed (`ADHOC`), unnotarized | macOS 12.0 (Qt6 Cocoa minimum) | CI test passed on ARM and Intel runners. Gatekeeper prompts on first launch; user confirms via right-click Open or System Settings. |
| **Linux (Modern)** (Ubuntu 24.04+, Debian 13+, Fedora 39+) | `x86_64` (`amd64`) | AppImage, Debian package (`.deb`) | Checksum verified (`SHA256SUMS.txt`) | **`GLIBC >= 2.38`**, X11 (`libxcb`) or Wayland | Prebuilt binaries require GLIBC >= 2.38. Tested on Ubuntu 24.04 / 26.04. Supports X11 and Wayland. Non-FUSE AppImage execution requires per-user `TMPDIR`. |
| **Linux (Older)** (Ubuntu 22.04 LTS, Debian 12) | `x86_64` | Source run with system Python 3.12 | Checksum verified | `GLIBC <= 2.36` | **Unsupported by prebuilt packages.** System GLIBC is older than bundled Python/Qt requirements. Must run from source or build custom packages. |

See the maintained [capability matrix](../capability-matrix.md) and [acceptance traceability](../acceptance-traceability.md) before relying on platform-specific features.

## Česky

Kompatibilita se zjišťuje podle nainstalovaného Mutagen CLI a schopností endpointu. Existence balíčku nedokazuje podporu všech verzí platformy.

### Matice operačních systémů a distribučních balíčků

| Operační systém | Architektura | Typy balíčků | Stav podpisu | Minimální běhové požadavky | Stav ověření a podpory |
|---|---|---|---|---|---|
| **Windows 10 / 11** | `x86_64` (`x64`) | Inno Setup instalátor, Přenosný ZIP, Samostatné EXE | Bez podpisu (`Authenticode NotSigned`) | Windows 10 build 19041+ | CI testy prošly. SmartScreen zobrazí varování na neznámého vydavatele. Uživatelská nastavení a historie zůstávají zachovány při upgradu i odinstalaci. |
| **macOS 12.0+** (Monterey, Ventura, Sonoma, Sequoia) | `arm64` (Apple Silicon), `x86_64` (Intel) | Diskový obraz (`.dmg`) | Ad-hoc podpis (`ADHOC`), bez notarizace | macOS 12.0 (minimum Qt6 Cocoa) | CI testy prošly na ARM i Intel runneru. Gatekeeper vyžaduje potvrzení při prvním spuštění přes pravé tlačítko Otevřít nebo Nastavení systému. |
| **Linux (Moderní)** (Ubuntu 24.04+, Debian 13+, Fedora 39+) | `x86_64` (`amd64`) | AppImage, balíček Debian (`.deb`) | Ověřeno kontrolním součtem (`SHA256SUMS.txt`) | **`GLIBC >= 2.38`**, X11 (`libxcb`) nebo Wayland | Předpřipravené balíčky vyžadují GLIBC >= 2.38. Otestováno na Ubuntu 24.04 / 26.04. Podporuje X11 i Wayland. Spuštění AppImage bez FUSE vyžaduje privátní `TMPDIR`. |
| **Linux (Starší)** (Ubuntu 22.04 LTS, Debian 12) | `x86_64` | Spuštění ze zdroje se systémovým Pythonem 3.12 | Ověřeno kontrolním součtem | `GLIBC <= 2.36` | **Předpřipravené balíčky nejsou podporovány.** Systémová GLIBC je starší než požadavky přibalených binárek. Nutno spustit ze zdrojového kódu. |

Před použitím funkcí specifických pro platformu ověřte [matici schopností](../capability-matrix.md) a [přehled akceptace](../acceptance-traceability.md).
