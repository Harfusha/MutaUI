"""Windows-native atomic file replacement via Win32 ReplaceFileW."""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["replace_file_win32"]

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    def replace_file_win32(target: Path, temporary: Path, backup: Path) -> None:
        """Atomically replace target with temporary, creating backup, using Windows ReplaceFileW."""
        replace_file = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
        replace_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPVOID,
        ]
        replace_file.restype = wintypes.BOOL
        if not replace_file(str(target), str(temporary), str(backup), 0x00000001, None, None):
            raise ctypes.WinError(ctypes.get_last_error())
else:

    def replace_file_win32(target: Path, temporary: Path, backup: Path) -> None:
        """Fallback for non-Windows platforms."""
        raise OSError("ReplaceFileW is only available on Windows systems.")
