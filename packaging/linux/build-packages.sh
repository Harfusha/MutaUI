#!/usr/bin/env bash
set -euo pipefail

APP_BUNDLE="${1:-dist-platform/MutagenControl}"
OUTPUT_DIR="${2:-dist}"
VERSION="${MUTAUI_VERSION:-8.2.0}"
VERSION="${VERSION#v}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_BUNDLE="$(cd "$ROOT/$APP_BUNDLE" && pwd)"
OUTPUT_DIR="$ROOT/$OUTPUT_DIR"
ASSETS="$ROOT/packaging/linux"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

test -x "$APP_BUNDLE/MutagenControl"
mkdir -p "$OUTPUT_DIR"

APPDIR="$STAGING/MutagenControl.AppDir"
mkdir -p "$APPDIR/usr/bin/mutagen-control" "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp -a "$APP_BUNDLE/." "$APPDIR/usr/bin/mutagen-control/"
cp "$ASSETS/AppRun" "$APPDIR/AppRun"
cp "$ASSETS/mutagen-control-appimage.desktop" "$APPDIR/mutagen-control.desktop"
cp "$ASSETS/mutagen-control.svg" "$APPDIR/mutagen-control.svg"
cp "$ASSETS/mutagen-control.svg" "$APPDIR/.DirIcon"
chmod 755 "$APPDIR/AppRun"

DEB="$STAGING/deb"
mkdir -p "$DEB/DEBIAN" "$DEB/opt/mutagen-control" "$DEB/usr/bin" \
  "$DEB/usr/share/applications" "$DEB/usr/share/icons/hicolor/scalable/apps"
cp -a "$APP_BUNDLE/." "$DEB/opt/mutagen-control/"
cp "$ASSETS/mutagen-control.desktop" "$DEB/usr/share/applications/mutagen-control.desktop"
cp "$ASSETS/mutagen-control.svg" "$DEB/usr/share/icons/hicolor/scalable/apps/mutagen-control.svg"
cat > "$DEB/usr/bin/mutagen-control" <<'LAUNCHER'
#!/bin/sh
exec /opt/mutagen-control/MutagenControl "$@"
LAUNCHER
chmod 755 "$DEB/usr/bin/mutagen-control"
cat > "$DEB/DEBIAN/control" <<CONTROL
Package: mutagen-control
Version: $VERSION
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Mutagen Control contributors
Depends: libc6, libstdc++6, libx11-6, libxcb1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render0, libxcb-shape0, libxcb-xfixes0, libxcb-xinerama0, libegl1, libfontconfig1
Description: Desktop control center for the Mutagen CLI
 A PySide6 desktop application for inspecting and managing local Mutagen sessions.
CONTROL
dpkg-deb --root-owner-group --build "$DEB" "$OUTPUT_DIR/MutagenControl-$VERSION-linux-amd64.deb"

if [ ! -x "$STAGING/appimagetool.AppImage" ]; then
  curl --fail --location --retry 3 \
    --output "$STAGING/appimagetool.AppImage" \
    https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage
fi
chmod 755 "$STAGING/appimagetool.AppImage"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$STAGING/appimagetool.AppImage" \
  "$APPDIR" "$OUTPUT_DIR/MutagenControl-$VERSION-linux-x86_64.AppImage"
chmod 755 "$OUTPUT_DIR/MutagenControl-$VERSION-linux-x86_64.AppImage"
