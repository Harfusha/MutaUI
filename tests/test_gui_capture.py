import pytest

import gui_capture


@pytest.mark.parametrize(
    ("scale", "width", "height", "font_fallback"),
    [
        ("1.5", 1380, 900, False),
        ("3.2", 1200, 675, False),
        ("1.5", 1380, 900, True),
    ],
)
def test_main_captures_each_page_and_closes_window(
    monkeypatch, tmp_path, scale, width, height, font_fallback
):
    events = []

    class FakeApp:
        def processEvents(self):
            events.append("process")

    class FakeApplication:
        @staticmethod
        def instance():
            return FakeApp()

        def __init__(self, args):
            events.append(("application", args))

    class FakePages:
        def count(self):
            return 3

    class FakeNavButton:
        def __init__(self, visible):
            self.visible = visible

        def isVisible(self):
            return self.visible

    class FakeWindow:
        def __init__(self, *, demo):
            assert demo is True
            self.pages = FakePages()
            self.nav = [FakeNavButton(True), FakeNavButton(False), FakeNavButton(True)]
            self.snapshot = object()
            self.timer = self.metric_timer = self.tail_timer = FakeTimer()

        def resize(self, width, height):
            events.append(("resize", width, height))

        def show(self):
            events.append("show")

        def apply_snapshot(self, snapshot):
            events.append(("snapshot", snapshot))

        def set_ui_mode(self, mode):
            events.append(("mode", mode))

        def apply_theme(self, theme):
            events.append(("theme", theme))

        def apply_ui_language(self, language):
            events.append(("language", language))

        def set_page(self, index):
            events.append(("page", index))

        def grab(self):
            return FakeImage()

        def close(self):
            events.append("close")

    class FakeTimer:
        def stop(self):
            events.append("stop")

    class FakeHistory:
        def close(self):
            events.append("history-close")

    class FakeImage:
        save_success = True

        def save(self, path):
            events.append(("save", path))
            return self.save_success

    monkeypatch.setattr(gui_capture, "QApplication", FakeApplication)
    font_directory = tmp_path / "Fonts"
    font_directory.mkdir()
    if font_fallback:
        (font_directory / "segoeui.ttf").write_bytes(b"font")
        (font_directory / "seguiemj.ttf").write_bytes(b"font")
    font_database = type(
        "FakeFonts",
        (),
        {
            "families": staticmethod(lambda: [] if font_fallback else ["test"]),
            "addApplicationFont": staticmethod(lambda path: events.append(("font", path))),
        },
    )()
    monkeypatch.setattr(gui_capture, "QFontDatabase", font_database)
    environment = {"WINDIR": str(tmp_path)}
    monkeypatch.setattr(
        gui_capture,
        "os",
        type("FakeOs", (), {"name": "nt", "environ": environment})(),
    )
    monkeypatch.setattr(gui_capture, "MainWindow", FakeWindow)
    monkeypatch.setattr(
        gui_capture,
        "sys",
        type(
            "FakeSys",
            (),
            {
                "argv": [
                    "capture",
                    str(tmp_path),
                    "--theme",
                    "light",
                    "--language",
                    "cs",
                    "--mode",
                    "advanced",
                    "--scale",
                    scale,
                    "--window-width",
                    str(width),
                    "--window-height",
                    str(height),
                ]
            },
        )(),
    )
    monkeypatch.setattr(FakeWindow, "history", FakeHistory(), raising=False)

    gui_capture.main()

    saved = [event[1] for event in events if isinstance(event, tuple) and event[0] == "save"]
    assert saved == [str(tmp_path / "page-00.png"), str(tmp_path / "page-02.png")]
    assert ("page", 1) not in events
    assert ("page", 2) in events
    assert ("mode", "advanced") in events
    assert ("theme", "light") in events
    assert ("language", "cs") in events
    assert gui_capture.os.environ["QT_SCALE_FACTOR"] == scale
    assert ("resize", width, height) in events
    assert "close" in events and "history-close" in events

    FakeImage.save_success = False
    with pytest.raises(RuntimeError, match="Unable to capture screenshot"):
        gui_capture.main()


@pytest.mark.parametrize("dimension", ["--window-width", "--window-height"])
def test_main_rejects_nonpositive_window_dimensions(monkeypatch, tmp_path, dimension):
    monkeypatch.setattr(
        gui_capture,
        "sys",
        type("FakeSys", (), {"argv": ["capture", str(tmp_path), dimension, "0"]})(),
    )

    with pytest.raises(SystemExit) as exc_info:
        gui_capture.main()

    assert exc_info.value.code == 2


def test_gui_capture_entry_point_executes_main(monkeypatch):
    import runpy

    monkeypatch.setattr(gui_capture.sys, "argv", ["gui_capture.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("gui_capture", run_name="__main__", alter_sys=True)
    assert exc.value.code == 0
