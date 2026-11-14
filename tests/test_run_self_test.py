from pathlib import Path

from scripts import run_self_test


def test_packaged_runner_waits_for_success_marker_and_stops_window(monkeypatch, tmp_path: Path):
    log_path = tmp_path / "self-test.log"

    class FakeProcess:
        def __init__(self, argv, *, env, **_kwargs):
            assert argv[-1] == "--self-test"
            assert env["QT_QPA_PLATFORM"] == "offscreen"
            Path(env["MUTAUI_SELF_TEST_LOG"]).write_text(
                run_self_test.SUCCESS_MARKER, encoding="utf-8"
            )
            self.exit_code = None
            self.terminated = False

        def poll(self):
            return self.exit_code

        def terminate(self):
            self.terminated = True
            self.exit_code = 0

        def wait(self, timeout=None):
            return self.exit_code

    monkeypatch.setattr(run_self_test, "_log_path", lambda: log_path)
    monkeypatch.setattr(run_self_test.subprocess, "Popen", FakeProcess)

    assert run_self_test.run_self_test(tmp_path / "MutagenControl") == 0


def test_packaged_runner_reports_early_exit(monkeypatch, tmp_path: Path, capsys):
    log_path = tmp_path / "self-test.log"

    class FakeProcess:
        def __init__(self, *_args, **_kwargs):
            self.exit_code = 7

        def poll(self):
            return self.exit_code

    monkeypatch.setattr(run_self_test, "_log_path", lambda: log_path)
    monkeypatch.setattr(run_self_test.subprocess, "Popen", FakeProcess)

    assert run_self_test.run_self_test(tmp_path / "MutagenControl") == 7
    assert "exit code 7" in capsys.readouterr().err
