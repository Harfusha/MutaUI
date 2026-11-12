import gui_capture


def test_main_captures_each_page_and_closes_window(monkeypatch, tmp_path):
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

    class FakeWindow:
        def __init__(self, *, demo):
            assert demo is True
            self.pages = FakePages()
            self.snapshot = object()
            self.timer = self.metric_timer = self.tail_timer = FakeTimer()

        def resize(self, width, height):
            events.append(("resize", width, height))

        def show(self):
            events.append("show")

        def apply_snapshot(self, snapshot):
            events.append(("snapshot", snapshot))

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
        def save(self, path):
            events.append(("save", path))
            return True

    monkeypatch.setattr(gui_capture, "QApplication", FakeApplication)
    monkeypatch.setattr(gui_capture, "QFontDatabase", type("FakeFonts", (), {"families": staticmethod(lambda: ["test"])})())
    monkeypatch.setattr(gui_capture, "MainWindow", FakeWindow)
    monkeypatch.setattr(gui_capture, "sys", type("FakeSys", (), {"argv": ["capture", str(tmp_path)]})())
    monkeypatch.setattr(FakeWindow, "history", FakeHistory(), raising=False)

    gui_capture.main()

    saved = [event[1] for event in events if isinstance(event, tuple) and event[0] == "save"]
    assert saved == [str(tmp_path / f"page-{i:02d}.png") for i in range(3)]
    assert ("page", 2) in events
    assert "close" in events and "history-close" in events
