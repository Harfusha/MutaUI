"""Render offline demonstration pages into PNG for visual QA on Windows.

No Mutagen CLI commands are executed: the window uses demo=True.
Run via gui_preview.cmd after installing the Qt dependencies.
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
from PySide6.QtWidgets import QApplication
from app import MainWindow


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "ui-preview")
    root.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window = MainWindow(demo=True)
    try:
        window.resize(1380, 900)
        window.show()
        app.processEvents()
        window.apply_snapshot(window.snapshot)
        for i in range(window.pages.count()):
            window.set_page(i)
            app.processEvents()
            path = root / f"page-{i:02d}.png"
            if not window.grab().save(str(path)):
                raise RuntimeError(f"Unable to capture screenshot {path}")
            print(path)
    finally:
        window.timer.stop()
        window.metric_timer.stop()
        window.tail_timer.stop()
        window._allow_exit = True
        window.close()
        window.history.close()


if __name__ == "__main__":
    main()
