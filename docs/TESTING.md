# Static checks and tests

Run the same checks as Windows CI from the repository root:

```powershell
python -m ruff check .
python verify_source.py
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q tests --tb=short --cov --cov-branch --cov-report=term-missing:skip-covered
```

Coverage uses branches and fails below 75%. CI runs all tests, including the Qt
smoke test, before building and self-testing both packaged Windows variants.

## Source-to-test map

| Source area | Main tests |
| --- | --- |
| Main window, dialogs, startup and UI actions (`app.py`) | `test_mainwindow_flows.py`, `test_gui_smoke.py`, `test_ui_formatting.py`, `test_remote_history.py`, `test_v5_migration.py` |
| Mutagen CLI adapter (`mutagen_client.py`) | `test_client.py`, `test_bulk_cli.py` |
| Background history writer (`async_recorder.py`) | `test_async_recorder.py` |
| SQLite history, sampling and monitoring (`monitoring.py`) | `test_monitoring.py`, `test_remote_history.py`, `test_async_recorder.py` |
| Endpoint summaries (`endpoint_inspector.py`) | `test_endpoint_inspector.py`, `test_insights.py`, `test_benchmark.py` |
| Log stream (`log_stream.py`) | `test_log_stream.py` |
| Performance helpers (`performance.py`) | `test_performance.py` |
| Server groups (`server_groups.py`) | `test_server_groups.py` |
| Sync profiles (`sync_profiles.py`) | `test_sync_profiles.py`, `test_mainwindow_flows.py` |
| Insights (`insights.py`) | `test_insights.py` |
| Local benchmark tool (`benchmark.py`) | `test_benchmark.py` |
| Offline GUI capture (`gui_capture.py`) | `test_gui_capture.py` |
| Static source invariants and Qt layout guards | `verify_source.py`, `test_qt_source_guard.py` |

The suite uses fixture data and mocked Mutagen/process boundaries; it does not
claim live SSH, remote server, network, or real Mutagen-daemon acceptance.
Coverage is a regression floor, not proof that every line or platform-specific
runtime path is exercised. The Windows CI packaging self-tests exercise the
actual generated executables; local source tests alone do not establish that.
