"""Render offline demonstration pages into PNG for visual QA on Windows.

No Mutagen CLI commands are executed: the window uses demo=True.
Run via gui_preview.cmd after installing the Qt dependencies.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import argparse
import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from app import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture offline demo pages for visual QA.")
    parser.add_argument(
        "output", nargs="?", default="ui-preview", help="Screenshot output directory"
    )
    parser.add_argument("--theme", choices=("system", "light", "dark"), default="dark")
    parser.add_argument("--language", choices=("en", "cs"), default="en")
    parser.add_argument("--mode", choices=("basic", "advanced"), default="basic")
    parser.add_argument("--scale", choices=("1", "1.25", "1.5", "2", "3.2"), default="1")
    parser.add_argument("--window-width", type=int, default=1380)
    parser.add_argument("--window-height", type=int, default=900)
    args = parser.parse_args(sys.argv[1:])
    if args.window_width < 1 or args.window_height < 1:
        parser.error("Window dimensions must be positive.")
    os.environ["QT_SCALE_FACTOR"] = args.scale
    root = Path(args.output)
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
        window.set_ui_mode(args.mode)
        window.apply_theme(args.theme)
        window.apply_ui_language(args.language)
        window.resize(args.window_width, args.window_height)
        window.show()
        app.processEvents()
        window.apply_snapshot(window.snapshot)
        for i in range(window.pages.count()):
            if not window.nav[i].isVisible():
                continue
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
