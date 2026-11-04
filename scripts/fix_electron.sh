#!/usr/bin/env bash
# Repair the dashboard's Electron install when npm left it broken.
#
# Electron's postinstall unzips its binary asynchronously; on Node 26 the event
# loop drains mid-unzip, the process exits 0, and path.txt is never written, so
# `electron` fails with "Electron failed to install correctly". This unzips the
# release zip ourselves (from Electron's download cache, or downloaded fresh)
# and writes path.txt. Safe to re-run: a working install is left alone.
#
# Overridable for tests: ELECTRON_DIR, ELECTRON_CACHE_DIR, ELECTRON_ARCH.
set -euo pipefail
cd "$(dirname "$0")/.."

DIR="${ELECTRON_DIR:-runtime/ui/node_modules/electron}"
CACHE="${ELECTRON_CACHE_DIR:-$HOME/Library/Caches/electron}"
ARCH="${ELECTRON_ARCH:-$(uname -m)}"
[ "$ARCH" = "x86_64" ] && ARCH=x64
BINARY="Electron.app/Contents/MacOS/Electron"

if [ ! -f "$DIR/package.json" ]; then
  echo "No Electron package at $DIR — run npm ci in runtime/ui first." >&2
  exit 1
fi
VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$DIR/package.json" | head -1)"

if [ -f "$DIR/path.txt" ] && [ -f "$DIR/dist/$BINARY" ]; then
  echo "Electron $VERSION already installed."
  exit 0
fi

ZIP_NAME="electron-v$VERSION-darwin-$ARCH.zip"
ZIP="$(find "$CACHE" -name "$ZIP_NAME" 2>/dev/null | head -1 || true)"
if [ -z "$ZIP" ]; then
  mkdir -p "$CACHE/manual"
  ZIP="$CACHE/manual/$ZIP_NAME"
  echo "Downloading $ZIP_NAME…"
  curl -fsSL -o "$ZIP" "https://github.com/electron/electron/releases/download/v$VERSION/$ZIP_NAME"
fi

rm -rf "$DIR/dist"
mkdir -p "$DIR/dist"
ditto -x -k "$ZIP" "$DIR/dist"   # keeps the app bundle's symlinks and permissions
printf '%s' "$BINARY" > "$DIR/path.txt"
echo "Electron $VERSION repaired from $ZIP."
