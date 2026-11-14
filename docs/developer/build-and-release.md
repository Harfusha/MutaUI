# Build and release / Build a vydání

## English

### Development environment

Use Python 3.12 and install uv with `python -m pip install uv==0.13.8`. Run `uv sync --locked --group build --group test --group quality` to create the environment from the committed cross-platform `uv.lock`. The `requirements*.txt` files are pinned compatibility exports for pip-based setup. The application requires the Mutagen CLI separately; verify its version and executable path before exercising live sessions. Keep local settings and credentials out of the repository.

### Local checks

The CI workflow is the source of truth for static checks and automated tests. From the repository root, run the configured Ruff lint and format checks, strict mypy, generated-settings reference validation, Markdown and MkDocs checks, source verification, and the pytest suite with the same coverage and zero-skip requirements as CI. Run them through `uv run python ...` so the locked environment is used. Use the Windows self-test script for a packaged Windows smoke check. These checks do not replace hosted CI on Windows, macOS, and Linux, live Mutagen acceptance, accessibility review, or manual installation and upgrade checks.

### Build and release

Release builds run from versioned `v*` tags. The release workflow checks that the tag matches the application version, builds Windows, macOS, and Linux artifacts, and publishes checksums, a CycloneDX SBOM, and build provenance. Windows signing and macOS signing/notarization depend on configured release secrets. Review the acceptance traceability report and release checklist before release; do not infer that a missing signature or an untested platform passed its gate. A local build is for development and is not a release artifact.

Only a maintainer may create and push a release tag after all applicable manual and hosted gates pass. This guide does not grant release authorization.

## Česky

### Vývojové prostředí

Použij Python 3.12 a nainstaluj uv příkazem `python -m pip install uv==0.13.8`. Příkaz `uv sync --locked --group build --group test --group quality` vytvoří prostředí z verzovaného multiplatformního `uv.lock`. Soubory `requirements*.txt` jsou přesně připnuté kompatibilní exporty pro pip. Mutagen CLI je samostatná závislost aplikace; před živým ověřením zkontroluj jeho verzi a cestu k programu. Místní nastavení a přihlašovací údaje neukládej do repozitáře.

### Místní kontroly

Workflow CI určuje závazné statické kontroly a automatické testy. V kořeni repozitáře spusť nakonfigurovaný Ruff, přísný mypy, kontrolu odkazů na generované nastavení, kontroly Markdownu a MkDocs, ověření zdrojů a pytest se stejným požadavkem na pokrytí a nulový počet přeskočených testů jako CI. Příkazy spusť přes `uv run python ...`, aby používaly uzamčené verze. Pro zabalenou verzi Windows použij self-test skript. Tyto kontroly nenahrazují CI na Windows, macOS a Linuxu, živé ověření Mutagen, kontrolu přístupnosti ani ruční instalaci a upgrade.

### Build a vydání

Vydávací workflow se spouští z verzovaných tagů `v*`. Ověří shodu tagu s verzí aplikace, sestaví balíčky pro Windows, macOS a Linux a vytvoří kontrolní součty, CycloneDX SBOM a provenance sestavení. Podepisování Windows a podepisování/notarizace macOS vyžadují nastavená tajemství vydání. Před vydáním zkontroluj přehled akceptace a vydávací checklist. Chybějící podpis ani neověřenou platformu nepovažuj za splněnou bránu. Místní build slouží vývoji, není vydávacím artefaktem.

Vydávací tag smí vytvořit a odeslat pouze maintainer po splnění příslušných ručních a hostovaných bran. Tento návod nedává oprávnění vydat produkt.
