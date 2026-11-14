import runpy
from pathlib import Path

from benchmark import run_benchmark, timed


def test_timed_returns_median_duration():
    calls = []
    assert timed(lambda: calls.append(None), repetitions=3) >= 0
    assert len(calls) == 3


def test_benchmark_reports_all_local_measurements():
    result = run_benchmark()
    assert set(result) == {
        "endpoint_decoding_10k_ms",
        "sqlite_write_2k_ms",
        "sqlite_aggregate_2k_ms",
        "note",
    }
    assert all(
        result[key] >= 0
        for key in (
            "endpoint_decoding_10k_ms",
            "sqlite_write_2k_ms",
            "sqlite_aggregate_2k_ms",
        )
    )


def test_benchmark_script_emits_json(capsys):
    runpy.run_path(str(Path(__file__).parents[1] / "benchmark.py"), run_name="__main__")

    output = capsys.readouterr().out
    assert '"endpoint_decoding_10k_ms"' in output
    assert '"sqlite_write_2k_ms"' in output
