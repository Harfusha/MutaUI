"""Performance constraints verified without a GUI or a live daemon."""
from performance import envelope_downsample, nearest_time_index, RefreshGate


def test_downsample_is_bounded_and_retains_short_peaks():
    rows = [(float(n), 1.0, 2.0) for n in range(10000)]
    rows[3456] = (3456.0, 9999.0, 2.0)
    rows[7699] = (7699.0, 1.0, 7000.0)
    result = envelope_downsample(rows, 480)
    assert len(result) <= 480
    assert result[0] == rows[0]
    assert result[-1] == rows[-1]
    assert rows[3456] in result and rows[7699] in result
    assert [r[0] for r in result] == sorted(r[0] for r in result)


def test_downsample_small_inputs_and_null_second_series():
    rows = [(float(i), i % 7, None) for i in range(45)]
    assert envelope_downsample(rows, 600) == rows
    assert len(envelope_downsample(rows, 12)) <= 12
    assert envelope_downsample([], 40) == []


def test_fast_binary_tooltips():
    keys = list(range(0, 20000, 2))
    assert nearest_time_index(keys, -100) == 0
    assert nearest_time_index(keys, 333.9) == 167
    assert nearest_time_index(keys, 50000) == len(keys) - 1
    assert nearest_time_index([], 100) == -1


def test_gate_coalesces_even_under_repeated_calls():
    t = [10.0]
    gate = RefreshGate(3.0, clock=lambda: t[0])
    assert gate.ready()
    assert not gate.ready()
    t[0] = 12.9
    assert not gate.ready()
    t[0] = 13.0
    assert gate.ready()
    assert gate.ready(force=True)
    t[0] = 13.5
    assert not gate.ready()
    t[0] = 8.0  # monotonic clock moved backwards (e.g. test stubs)
    assert gate.ready()
    gate.reset()
    assert gate.ready()


def test_background_statistics_uses_independent_readonly_sqlite(tmp_path):
    from monitoring import HistoryStore, Sample, statistics_from_file
    dbpath = tmp_path / 'metrics.sqlite3'
    store = HistoryStore(dbpath)
    store.add(Sample(ts=100, cpu=1, memory=50))
    store.add(Sample(ts=101, cpu=99, memory=150))
    expected = store.statistics(hours=1, now=102)
    actual = statistics_from_file(dbpath, hours=1, now=102)
    assert actual == expected
    store.add(Sample(ts=103, cpu=25, memory=120))
    assert statistics_from_file(dbpath, hours=1, now=104)['samples'] == 3
    store.close()


def test_poll_backoff_jitterless_and_manual_override():
    from performance import PollBackoff
    t = [100.0]
    policy = PollBackoff(base=2, maximum=10, clock=lambda: t[0])
    assert policy.can_retry()
    policy.observe(False)
    assert policy.remaining() == 2
    assert not policy.can_retry() and policy.can_retry(force=True)
    t[0] = 102
    assert policy.can_retry()
    policy.observe(False)
    assert policy.remaining() == 4
    policy.observe(False)
    assert policy.remaining() == 8
    policy.observe(False)
    assert policy.remaining() == 10
    policy.observe(True)
    assert policy.can_retry() and policy.remaining() == 0
