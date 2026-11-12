"""Render offline demonstration pages into PNG for visual QA on Windows.

No Mutagen CLI commands are executed: the window uses demo=True.
Run via gui_preview.cmd after installing the Qt dependencies.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from app import MainWindow


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "ui-preview")
    root.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    if os.name == "nt" and not QFontDatabase.families():
        font_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for font_name in ("segoeui.ttf", "seguisym.ttf", "seguiemj.ttf"):
            font_file = font_dir / font_name
            if font_file.is_file():
                QFontDatabase.addApplicationFont(str(font_file))
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
