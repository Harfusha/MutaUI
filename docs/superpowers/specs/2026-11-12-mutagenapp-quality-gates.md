# Specifikace: statické kontroly a pokrytí MutagenApp

## Cíl

Doplnit opakovatelné statické kontroly a testy pro každou významnou oblast aplikace, měřit jejich pokrytí a vyžadovat quality gate ve Windows CI.

## Rozsah

- Zmapovat aktuální moduly, testy, ruční/CI kontroly a výchozí pokrytí.
- Přidat Python lint bez plošného přeformátování existujícího kódu.
- Měřit řádkové i větvové pokrytí relevantních aplikačních modulů; nastavit dosažitelný práh podle výchozích výsledků.
- Doplnit cílené testy pro neověřené významné logické větve a uživatelské GUI flows.
- Spouštět celý statický a testový gate ve Windows CI před balením.
- Výslovně uvést neotestované externí integrace a provozní scénáře.

## Omezení

- Zachovat všechny předchozí lokální změny.
- Unit testy samy nedokazují každou kombinaci vstupů ani reálné Mutagen, SSH či Windows chování.
- Testy izolují Mutagen CLI, síť, soubory a čas vhodnými fixtures/mocks; GUI smoke běží offline.
- Nelze tvrdit doslovnou úplnost; „celé testované“ znamená významné chování pokryté testy, pokrytí měřené a zbylé limity přiznané.

## Akceptace

1. Evidence mapuje každý aplikační modul na unit/integration/GUI testy nebo doloženou výjimku.
2. Statický lint a vlastní source guard běží v CI.
3. CI měří line i branch coverage a vynucuje zdůvodněný minimální práh.
4. Nové testy uzavírají významné mezery z baseline; celý dostupný test suite a GUI smoke test projdou.
5. Závěrečná zpráva uvádí přesné příkazy, výsledky, pokrytí a limity.
