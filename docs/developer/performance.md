# Performance / Výkon

## English

The repository includes a deterministic session-table canary in `benchmarks/session_table_benchmark.py`; CI uploads its JSON result. It measures the table model, not live remote endpoint or Mutagen transfer performance. Compare results only with the same runner and workload. Reference-hardware UI budgets remain open until measured on that hardware.

See [performance tuning](../advanced/performance-tuning.md), [session health](../session-health.md), and the [roadmap](../roadmap.md).

## Česky

Repozitář obsahuje deterministický canary tabulky relací v `benchmarks/session_table_benchmark.py`; CI nahrává JSON výsledek. Měří model tabulky, ne výkon živého vzdáleného endpointu ani přenosu Mutagenem. Porovnávejte jen stejné runner prostředí a zátěž. Rozpočty UI na referenčním hardwaru zůstávají otevřené, dokud na něm nejsou změřeny.

Viz [ladění výkonu](../advanced/performance-tuning.md), [zdraví relace](../session-health.md) a [roadmapu](../roadmap.md).
