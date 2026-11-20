"""Test the mutaui.app re-export proxy."""

from __future__ import annotations

import sys
from pathlib import Path


def test_mutaui_app_proxy_exports() -> None:
    import mutaui.app as app_proxy

    assert app_proxy.MainWindow is not None
    assert app_proxy.QuickNavigator is not None
    assert app_proxy.SupportBundleDialog is not None
    assert callable(app_proxy.main)


def test_mutaui_app_proxy_path_insertion() -> None:
    _root = str(Path(__file__).resolve().parent.parent)
    while _root in sys.path:
        sys.path.remove(_root)
    if "mutaui.app" in sys.modules:
        del sys.modules["mutaui.app"]

    import mutaui.app as app_proxy

    assert _root in sys.path
    assert app_proxy.MainWindow is not None
