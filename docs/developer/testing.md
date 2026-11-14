# Testing / Testování

## English

The [runtime and integration testing guide](../TESTING.md) documents packaged self-tests, an isolated real Mutagen daemon, and opt-in SSH recovery. CI installs the pinned Mutagen CLI and asserts zero skipped tests. The [coverage audit](../reports/coverage-2026-11-14.md) records current local branch coverage and the remaining gap to the master-plan gate.

Distinguish focused unit tests, packaged GUI self-tests, hosted platform jobs, live SSH, and manual walkthroughs. A result from one category does not close another category's acceptance gate.

## Česky

[Návod k runtime a integračnímu testování](../TESTING.md) popisuje zabalený self-test, izolovaný skutečný daemon Mutagenu a volitelnou SSH obnovu. CI instaluje připnuté Mutagen CLI a vyžaduje nula přeskočených testů. [Coverage audit](../reports/coverage-2026-11-14.md) zaznamenává místní pokrytí větví a zbývající odstup od brány master plánu.

Rozlišujte cílené unit testy, zabalený GUI self-test, hosted platformní joby, živé SSH a ruční průchody. Výsledek jedné kategorie neuzavírá jinou akceptační bránu.
