from types import SimpleNamespace

import app


def test_tray_idle_seconds_measure_only_hidden_eco_intervals(monkeypatch) -> None:
    now = [0.0]
    visible = [True]
    monkeypatch.setattr(app.time, "monotonic", lambda: now[0])
    window = SimpleNamespace(
        _eco_hidden=False,
        _tray_idle_mode=False,
        _tray_idle_started_at=None,
        _tray_idle_seconds_pending=0.0,
        conf={"eco_tray": True},
        isVisible=lambda: visible[0],
        isMinimized=lambda: False,
        metric_timer=SimpleNamespace(setInterval=lambda _value: None),
        timer=SimpleNamespace(setInterval=lambda _value: None),
        metric_period_ms=lambda: 2000,
        poll_period_ms=lambda: 4000,
    )

    app.MainWindow.update_polling_mode(window)
    now[0] = 10.0
    visible[0] = False
    app.MainWindow.update_polling_mode(window)
    now[0] = 25.0
    assert app.MainWindow.tray_idle_seconds(window) == 15.0
    app.MainWindow.commit_tray_idle_sample(window)

    visible[0] = True
    now[0] = 30.0
    app.MainWindow.update_polling_mode(window)
    now[0] = 35.0
    assert app.MainWindow.tray_idle_seconds(window) == 5.0


def test_tray_idle_seconds_ignore_hidden_window_when_eco_mode_is_off(monkeypatch) -> None:
    monkeypatch.setattr(app.time, "monotonic", lambda: 12.0)
    window = SimpleNamespace(
        _eco_hidden=False,
        _tray_idle_mode=False,
        _tray_idle_started_at=None,
        _tray_idle_seconds_pending=0.0,
        conf={"eco_tray": False},
        isVisible=lambda: False,
        isMinimized=lambda: False,
        metric_timer=SimpleNamespace(setInterval=lambda _value: None),
        timer=SimpleNamespace(setInterval=lambda _value: None),
        metric_period_ms=lambda: 2000,
        poll_period_ms=lambda: 4000,
    )

    app.MainWindow.update_polling_mode(window)

    assert app.MainWindow.tray_idle_seconds(window) == 0.0
