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
    assert all(result[key] >= 0 for key in (
        "endpoint_decoding_10k_ms",
        "sqlite_write_2k_ms",
        "sqlite_aggregate_2k_ms",
    ))
