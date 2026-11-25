"""Targeted regression tests for Batch 2F: Packaging, SBOM, GLIBC, AppImage, and signing truthfulness."""

from __future__ import annotations

import plistlib
import tomllib
from pathlib import Path

import pytest

import mutaui
from mutaui.services.linux_file_manager_integration import (
    IntegrationError,
    install_linux_file_manager_integration,
    is_transient_extraction_path,
)
from mutaui.ui.preferences import translate_text
from scripts.ci.audit_native_libraries import (
    audit_directory,
    scan_glibc_symbols,
)
from scripts.ci.patch_macos_plist import patch_plist


def test_m49_version_consistency_across_modules() -> None:
    """M49: Ensure unified application version across pyproject.toml, core, and UI."""
    pyproject_path = Path("pyproject.toml")
    with pyproject_path.open("rb") as fp:
        project_data = tomllib.load(fp)
    declared_version = project_data["project"]["version"]

    assert mutaui.__version__ == declared_version

    # Check preferences dynamic localization for versioned titles
    cs_title = translate_text(f"Mutagen Control {declared_version} · Server Manager", "cs")
    assert cs_title == f"Mutagen Control {declared_version} · Správce serverů"

    # Arbitrary version string also dynamically translates correctly
    arbitrary_title = translate_text("Mutagen Control 10.4.2 · Server Manager", "cs")
    assert arbitrary_title == "Mutagen Control 10.4.2 · Správce serverů"

    # Version label
    ver_label = translate_text(f"v{declared_version}", "cs")
    assert ver_label == f"v{declared_version}"


def test_m64_file_manager_integration_transient_path_rejection_and_appimage_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M64: Transient extraction paths must be rejected unless resolved via $APPIMAGE."""
    transient_exe = tmp_path / "appimage_extracted_12345" / "MutagenControl"
    transient_exe.parent.mkdir(parents=True)
    transient_exe.write_bytes(b"temp binary")

    assert is_transient_extraction_path(transient_exe) is True
    assert is_transient_extraction_path("/usr/bin/mutagen-control") is False
    assert is_transient_extraction_path("/home/user/Applications/MutaUI.AppImage") is False

    data_home = tmp_path / "xdg-data"

    # Unset APPIMAGE: must fail with informative error
    monkeypatch.delenv("APPIMAGE", raising=False)
    with pytest.raises(IntegrationError, match="Refusing to register transient extraction path"):
        install_linux_file_manager_integration(
            transient_exe, data_home=data_home, platform_name="linux"
        )

    # Set persistent APPIMAGE path: must succeed and resolve to stable binary
    stable_appimage = tmp_path / "Applications" / "MutagenControl.AppImage"
    stable_appimage.parent.mkdir(parents=True)
    stable_appimage.write_bytes(b"stable appimage")

    monkeypatch.setenv("APPIMAGE", str(stable_appimage))
    result = install_linux_file_manager_integration(
        transient_exe, data_home=data_home, platform_name="linux"
    )
    assert result == "installed"

    # Verify manifest recorded the stable APPIMAGE path, not the transient extraction path
    manifest_file = data_home / "mutaui" / "integrations" / "linux-file-manager.json"
    assert manifest_file.is_file()
    import json

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["executable"] == str(stable_appimage)
    assert str(transient_exe) != manifest_data["executable"]


def test_m64_file_manager_integration_auto_heals_missing_old_binary(tmp_path: Path) -> None:
    """M64: Re-registering when previous executable target no longer exists auto-heals."""
    first_bin = tmp_path / "first_app" / "MutagenControl"
    first_bin.parent.mkdir()
    first_bin.write_bytes(b"first")

    second_bin = tmp_path / "second_app" / "MutagenControl"
    second_bin.parent.mkdir()
    second_bin.write_bytes(b"second")

    data_home = tmp_path / "xdg-data"
    assert (
        install_linux_file_manager_integration(
            first_bin, data_home=data_home, platform_name="linux"
        )
        == "installed"
    )

    # While first_bin exists, installing for second_bin is rejected
    with pytest.raises(IntegrationError, match="different executable"):
        install_linux_file_manager_integration(
            second_bin, data_home=data_home, platform_name="linux"
        )

    # Delete first_bin (simulating deleted or transient path): install now auto-heals
    first_bin.unlink()
    assert (
        install_linux_file_manager_integration(
            second_bin, data_home=data_home, platform_name="linux"
        )
        == "installed"
    )


def test_m89_macos_patch_plist(tmp_path: Path) -> None:
    """M89: macOS Info.plist patcher injects version, bundle ID, and minimum OS 12.0."""
    sample_plist = tmp_path / "Info.plist"
    initial_data = {
        "CFBundleName": "MutagenControl",
        "CFBundleShortVersionString": "0.0.0",
        "CFBundleExecutable": "MutagenControl",
    }
    with sample_plist.open("wb") as fp:
        plistlib.dump(initial_data, fp, fmt=plistlib.FMT_XML)

    patch_plist(sample_plist, "9.1.1")

    with sample_plist.open("rb") as fp:
        patched = plistlib.load(fp)

    assert patched["CFBundleShortVersionString"] == "9.1.1"
    assert patched["CFBundleVersion"] == "9.1.1"
    assert patched["CFBundleIdentifier"] == "io.mutagen.control"
    assert patched["LSMinimumSystemVersion"] == "12.0"
    assert "Copyright" in patched["NSHumanReadableCopyright"]


def test_m74_native_library_classification(tmp_path: Path) -> None:
    """M74: Native library auditor accurately classifies Qt6, Python, OpenSSL, SQLite."""
    qt_lib = tmp_path / "libQt6Core.so.6.8.3"
    qt_lib.write_bytes(b"\x7fELFfake Qt library")

    py_lib = tmp_path / "libpython3.12.so.1.0"
    py_lib.write_bytes(b"\x7fELFfake Python library")

    ssl_lib = tmp_path / "libcrypto.so.3"
    ssl_lib.write_bytes(b"\x7fELFfake OpenSSL library")

    sqlite_lib = tmp_path / "sqlite3.dll"
    sqlite_lib.write_bytes(b"MZfake SQLite dll")

    records = audit_directory(tmp_path)
    components = {r.component for r in records}
    assert "Qt6" in components
    assert "Python Runtime" in components
    assert "OpenSSL" in components
    assert "SQLite" in components


def test_m76_m77_glibc_symbol_scanning(tmp_path: Path) -> None:
    """M76 & M77: ELF GLIBC scanner detects required minimum GLIBC versions."""
    fake_elf = tmp_path / "fake_binary.so"
    # Embed simulated GLIBC symbol references
    fake_elf.write_bytes(b"\x7fELF ... GLIBC_2.2.5 ... GLIBC_2.38 ... GLIBC_2.17 ...")

    max_glibc = scan_glibc_symbols(fake_elf)
    assert max_glibc == "GLIBC_2.38"


def test_m73_gitattributes_line_ending_enforcement() -> None:
    """M73: Repository must enforce LF across shell, yaml, json, desktop, python."""
    gitattributes = Path(".gitattributes")
    assert gitattributes.is_file(), ".gitattributes must be present to guarantee EOL consistency"
    content = gitattributes.read_text(encoding="utf-8")
    assert "* text=auto eol=lf" in content
    assert "*.sh text eol=lf" in content
    assert "*.yml text eol=lf" in content
    assert "*.yaml text eol=lf" in content
    assert "*.bat text eol=crlf" in content
    assert "*.cmd text eol=crlf" in content


def test_packaging_scripts_and_workflows_consistency() -> None:
    """M59, M60, M61, M62, M63, M75, M76, M77: Verify workflow & packaging constraints."""
    build_packages_sh = Path("packaging/linux/build-packages.sh").read_text(encoding="utf-8")
    assert "libc6 (>= 2.38)" in build_packages_sh
    assert "MUTAUI_VERSION:-9.2.0}" in build_packages_sh

    ci_yml = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    # Must not contain hardcoded previous version in SBOM or artifact names
    assert "dist/MutagenControl-9.1.0" not in ci_yml
    assert "dist-platform/MutagenControl" in ci_yml  # Scans unpacked payload for Linux SBOM
    assert "patch_macos_plist.py" in ci_yml

    release_yml = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    # Must not contain bare github.ref_name for Linux package version or SBOM
    assert "MUTAUI_VERSION: ${{ github.ref_name }}" not in release_yml
    assert "dist/MutagenControl-${{ github.ref_name }}-linux" not in release_yml
    # Must sign inner binaries before Inno Setup packaging
    assert release_yml.index("Sign inner Windows executables") < release_yml.index(
        "Build Windows installer"
    )
    assert release_yml.index("Build Windows installer") < release_yml.index(
        "Sign Windows installer package"
    )
    # Must pin Inno Setup
    assert "innosetup --version 6.3.3" in release_yml


def test_documentation_truthfulness_and_notarization_accuracy() -> None:
    """M48, M52, M86, M91: Verify truthful documentation of signing, GLIBC, and AppImage."""
    install_doc = Path("docs/installation.md").read_text(encoding="utf-8")
    macos_doc = Path("docs/getting-started/macos.md").read_text(encoding="utf-8")
    compat_doc = Path("docs/reference/compatibility-matrix.md").read_text(encoding="utf-8")

    # M86: Must not falsely claim notarized DMG
    assert "notarized DMG" not in macos_doc
    assert "notarizovaný DMG" not in macos_doc
    assert "ad-hoc signed" in macos_doc.lower() or "ad-hoc" in macos_doc.lower()

    # M48: Must explain unsigned Authenticode and SmartScreen
    assert "Authenticode NotSigned" in install_doc
    assert "SmartScreen" in install_doc

    # M76 & M77: Must state GLIBC >= 2.38 requirement
    assert "GLIBC >= 2.38" in install_doc
    assert "GLIBC >= 2.38" in compat_doc

    # M91: Must document non-FUSE per-user TMPDIR AppImage isolation
    assert "APPIMAGE_EXTRACT_AND_RUN=1" in install_doc
    assert "TMPDIR" in install_doc
