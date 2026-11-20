"""MutaUI main window and application entrypoint re-export module."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure root directory is on sys.path if invoked from package
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import MainWindow, QuickNavigator, SupportBundleDialog, main

__all__ = [
    "MainWindow",
    "QuickNavigator",
    "SupportBundleDialog",
    "main",
]
