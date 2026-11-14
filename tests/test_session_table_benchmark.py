from benchmarks.session_table_benchmark import (
    SESSION_SIZES,
    measure,
    measure_main_window,
    measure_qt_view,
    percentile,
    session_fixtures,
)


def test_fixtures_cover_requested_sizes_without_external_paths():
    assert SESSION_SIZES == (0, 1, 10, 100, 500, 1000, 5000)
    fixtures = session_fixtures(2)
    assert [item["identifier"] for item in fixtures] == ["synthetic-0", "synthetic-1"]
    assert all(item["alpha"]["path"].startswith("C:/alpha/") for item in fixtures)


def test_percentile_selects_bounded_order_statistic():
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.50) == 3.0
    assert percentile([4.0, 1.0, 3.0, 2.0], 0.95) == 4.0


def test_model_benchmark_reports_latency_distribution():
    result = measure(1, repetitions=3)
    assert result["rows"] == 1
    assert result["repetitions"] == 3
    assert 0 <= result["p50_ms"] <= result["max_ms"]
    assert result["p50_ms"] <= result["p95_ms"] <= result["max_ms"]


def test_qt_view_benchmark_filters_and_renders_the_session_model():
    result = measure_qt_view(1000, repetitions=3)

    assert result["rows"] == 1000
    assert result["filtered_rows"] == 1
    assert result["viewport_rendered"] is True
    assert result["repetitions"] == 3
    assert 0 <= result["p50_ms"] <= result["p95_ms"] <= result["max_ms"]


def test_main_window_benchmark_uses_demo_data_and_isolated_settings():
    result = measure_main_window(5, repetitions=2)

    assert result["rows"] == 5
    assert result["repetitions"] == 2
    assert result["visible"] is True
    assert result["filtered_rows"] == 1
    assert result["viewport_rendered"] is True
    assert 0 <= result["p50_ms"] <= result["p95_ms"] <= result["max_ms"]
    assert 0 <= result["filter_render_p50_ms"] <= result["filter_render_p95_ms"]
