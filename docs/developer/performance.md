# Performance / Výkon

## English

The repository includes a deterministic session-table canary in `benchmarks/session_table_benchmark.py`; CI uploads its JSON result. It measures the table model, not live remote endpoint or Mutagen transfer performance. Compare results only with the same runner and workload. Reference-hardware UI budgets remain open until measured on that hardware.

See [performance tuning](../advanced/performance-tuning.md), [session health](../session-health.md), and the [roadmap](../roadmap.md).

## Česky

Repozitář obsahuje deterministický canary tabulky relací v `benchmarks/session_table_benchmark.py`; CI nahrává JSON výsledek. Měří model tabulky, ne výkon živého vzdáleného endpointu ani přenosu Mutagenem. Porovnávejte jen stejné runner prostředí a zátěž. Rozpočty UI na referenčním hardwaru zůstávají otevřené, dokud na něm nejsou změřeny.

Viz [ladění výkonu](../advanced/performance-tuning.md), [zdraví relace](../session-health.md) a [roadmapu](../roadmap.md).

## Refresh delta benchmarks / Srovnání aktualizací

The synthetic benchmark additionally records p50/p95/max for unchanged snapshots,
updates to a single row, and structural insert/remove resets at 1,000 and
5,000 sessions (`refresh_cases` in JSON). It validates expected Qt `modelReset`
and `dataChanged` counts, and fails when no-op refreshes unexpectedly reset
the view. Small structural deltas now use rowsInserted/rowsRemoved rather
than model resets, and the benchmark records those counts separately. Compare
results from the same OS and runner; this does not measure a
live Mutagen daemon, network I/O or native compositor latency.

Český souhrn: Výstup `refresh_cases` samostatně měří nezměněný snapshot, změnu
jednoho řádku a strukturální změny. Součástí jsou počty signálů modelu a
statistiky p50/p95/max pro 1 000 a 5 000 relací. Malé změny struktury
používají signály vložení a odebrání řádku namísto resetu. Referenční hardware a
reálné přenosy Mutagen stále vyžadují zvláštní akceptační testy.
