"""Opt-in, per-user Linux file-manager hooks for packaged MutaUI builds."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
from contextlib import suppress
from pathlib import Path
from typing import Final


class IntegrationError(RuntimeError):
    """Raised when an integration cannot be changed safely."""


_NAUTILUS_RELATIVE: Final = Path("nautilus/scripts/MutaUI/Open folder in MutaUI")
_DOLPHIN_RELATIVE: Final = Path("kio/servicemenus/mutaui-open-folder.desktop")
_MANIFEST_RELATIVE: Final = Path("mutaui/integrations/linux-file-manager.json")
_MANAGED_FILES: Final = (_NAUTILUS_RELATIVE, _DOLPHIN_RELATIVE)
_MANIFEST_VERSION: Final = 2


def _assert_linux(platform_name: str | None) -> None:
    platform = sys.platform if platform_name is None else platform_name
    if not platform.startswith("linux"):
        raise IntegrationError("Linux only: file-manager integration is unavailable.")


def _data_home(data_home: Path | str | None) -> Path:
    if data_home is None:
        configured = os.environ.get("XDG_DATA_HOME")
        root = Path(configured).expanduser() if configured else Path.home() / ".local/share"
    else:
        root = Path(data_home).expanduser()
    if not root.is_absolute():
        raise IntegrationError("XDG data directory must be an absolute path.")
    return root


def _safe_path(root: Path, relative: Path) -> Path:
    """Return a managed path after rejecting symlinked existing components."""
    current = root
    if current.exists() and (current.is_symlink() or not current.is_dir()):
        raise IntegrationError("XDG data directory is not a safe directory.")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"Refusing symlink in integration path: {current}")
        if current.exists() and not current.is_dir() and current != root / relative:
            raise IntegrationError(f"Integration path component is not a directory: {current}")
    return current


def _desktop_exec_arg(value: str) -> str:
    """Encode one executable argument for a freedesktop Desktop Entry Exec key."""
    escaped = value.replace("%", "%%")
    escaped = escaped.replace("\\", "\\\\")
    for char in ('"', "`", "$"):
        escaped = escaped.replace(char, "\\" + char)
    return f'"{escaped}"'


def _hook_contents(executable: Path) -> dict[Path, bytes]:
    executable_text = str(executable)
    shell_executable = shlex.quote(executable_text)
    nautilus = (
        "#!/bin/sh\n"
        "set -eu\n"
        "selected=${NAUTILUS_SCRIPT_SELECTED_FILE_PATHS-}\n"
        "newline='\n'\n"
        'case "$selected" in\n'
        '  *"$newline") selected=${selected%"$newline"} ;;\n'
        "esac\n"
        '[ -n "$selected" ] || exit 2\n'
        'case "$selected" in *"$newline"*) exit 2 ;; esac\n'
        f'exec {shell_executable} --open-folder "$selected"\n'
    ).encode()
    dolphin = (
        "[Desktop Entry]\n"
        "Type=Service\n"
        "MimeType=inode/directory;\n"
        "X-KDE-ServiceTypes=KonqPopupMenu/Plugin\n"
        "Actions=mutauiOpenFolder;\n"
        "X-KDE-Priority=TopLevel\n"
        "\n"
        "[Desktop Action mutauiOpenFolder]\n"
        "Name=Open folder in MutaUI\n"
        f"Exec={_desktop_exec_arg(executable_text)} --open-folder %f\n"
        "Icon=folder-open\n"
    ).encode()
    return {_NAUTILUS_RELATIVE: nautilus, _DOLPHIN_RELATIVE: dolphin}


def _digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _load_manifest(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise IntegrationError("Integration ownership manifest is missing or unsafe.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrationError("Integration ownership manifest is invalid.") from exc
    if not isinstance(manifest, dict) or manifest.get("version") != _MANIFEST_VERSION:
        raise IntegrationError("Integration ownership manifest has an unsupported format.")
    files = manifest.get("files")
    expected = {relative.as_posix() for relative in _MANAGED_FILES}
    if not isinstance(files, dict) or set(files) != expected:
        raise IntegrationError("Integration ownership manifest has unexpected paths.")
    executable = manifest.get("executable")
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        raise IntegrationError("Integration ownership manifest has no valid executable path.")
    return manifest


def _verify_owned_files(root: Path, manifest: dict[str, object]) -> list[tuple[Path, str]]:
    files = manifest["files"]
    assert isinstance(files, dict)
    verified: list[tuple[Path, str]] = []
    for relative in _MANAGED_FILES:
        destination = _safe_path(root, relative)
        expected_hash = files[relative.as_posix()]
        if not isinstance(expected_hash, str):
            raise IntegrationError("Integration ownership manifest has invalid hashes.")
        if not destination.is_file() or _digest(destination.read_bytes()) != expected_hash:
            raise IntegrationError(
                f"Managed integration file was modified or removed: {destination}"
            )
        verified.append((destination, expected_hash))
    return verified


def _make_parents(root: Path, destination: Path, created_dirs: list[Path]) -> None:
    if not root.exists():
        missing_root: list[Path] = []
        current = root
        while not current.exists():
            missing_root.append(current)
            current = current.parent
        if current.is_symlink() or not current.is_dir():
            raise IntegrationError("XDG data directory parent is not a safe directory.")
        for directory in reversed(missing_root):
            directory.mkdir()
            created_dirs.append(directory)
    elif root.is_symlink() or not root.is_dir():
        raise IntegrationError("XDG data directory is not a safe directory.")
    parent = destination.parent
    missing: list[Path] = []
    current = parent
    while current != root and not current.exists():
        missing.append(current)
        current = current.parent
    if current != root and (current.is_symlink() or not current.is_dir()):
        raise IntegrationError(f"Integration parent is not a safe directory: {current}")
    for directory in reversed(missing):
        directory.mkdir()
        created_dirs.append(directory)


def _write_exclusive(path: Path, contents: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def install_linux_file_manager_integration(
    executable: Path | str,
    *,
    data_home: Path | str | None = None,
    platform_name: str | None = None,
) -> str:
    """Install Nautilus and Dolphin hooks in the current user's data directory."""
    _assert_linux(platform_name)
    binary = Path(executable).expanduser()
    if not binary.is_absolute() or not binary.is_file() or binary.is_symlink():
        raise IntegrationError("Install requires an existing absolute packaged executable.")
    root = _data_home(data_home)
    contents = _hook_contents(binary)
    destinations = {relative: _safe_path(root, relative) for relative in _MANAGED_FILES}
    manifest_path = _safe_path(root, _MANIFEST_RELATIVE)

    if manifest_path.exists():
        manifest = _load_manifest(manifest_path)
        _verify_owned_files(root, manifest)
        if manifest.get("executable") != str(binary):
            raise IntegrationError(
                "Integration is installed for a different executable; remove it before reinstalling."
            )
        return "already_installed"

    if any(path.exists() for path in (*destinations.values(), manifest_path)):
        raise IntegrationError("Integration conflict: refusing to overwrite an existing file.")

    created_dirs: list[Path] = []
    created_files: list[Path] = []
    try:
        for relative, destination in destinations.items():
            _make_parents(root, destination, created_dirs)
            mode = 0o755 if relative == _NAUTILUS_RELATIVE else 0o644
            _write_exclusive(destination, contents[relative], mode)
            created_files.append(destination)
        _make_parents(root, manifest_path, created_dirs)
        manifest_bytes = (
            json.dumps(
                {
                    "version": _MANIFEST_VERSION,
                    "executable": str(binary),
                    "files": {
                        relative.as_posix(): _digest(payload)
                        for relative, payload in contents.items()
                    },
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        _write_exclusive(manifest_path, manifest_bytes, 0o600)
        created_files.append(manifest_path)
    except (OSError, IntegrationError) as exc:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            with suppress(OSError):
                directory.rmdir()
        if isinstance(exc, IntegrationError):
            raise
        raise IntegrationError(f"Could not install Linux file-manager integration: {exc}") from exc
    return "installed"


def remove_linux_file_manager_integration(
    *, data_home: Path | str | None = None, platform_name: str | None = None
) -> str:
    """Remove only unchanged hooks whose ownership is recorded by our manifest."""
    _assert_linux(platform_name)
    root = _data_home(data_home)
    manifest_path = _safe_path(root, _MANIFEST_RELATIVE)
    if not manifest_path.exists():
        if any(_safe_path(root, relative).exists() for relative in _MANAGED_FILES):
            raise IntegrationError(
                "Integration conflict: hooks exist without an ownership manifest."
            )
        return "not_installed"

    manifest = _load_manifest(manifest_path)
    verified = _verify_owned_files(root, manifest)
    for path, _ in verified:
        path.unlink()
    manifest_path.unlink()
    nautilus_directory = root / "nautilus/scripts/MutaUI"
    with suppress(OSError):
        nautilus_directory.rmdir()
    return "removed"
