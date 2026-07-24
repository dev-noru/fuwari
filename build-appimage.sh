#!/usr/bin/env bash
set -euo pipefail

# ── config ──────────────────────────────────────────────────────────
APPDIR=Fuwari.AppDir
SRC="$(pwd)"
PYVER=3.11
UNIDIC_CACHE="$HOME/.cache/fuwari-unidic"
BUNDLE_LAYERSHELL=true  # set false once you confirm QML doesn't use LayerShell

export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt  # manylinux py needs this for TLS

# ── 0. prerequisites: fail early, not after a 1GB download ───────────
command -v appimagetool >/dev/null || { echo "ERROR: appimagetool missing (AUR: appimagetool-bin)"; exit 1; }
command -v cargo >/dev/null || { echo "ERROR: cargo missing (rustup or pacman: rust)"; exit 1; }
[ -f "$SRC/requirements.txt" ] || { echo "ERROR: requirements.txt missing"; exit 1; }
[ -f "$SRC/fuwari.desktop" ]   || { echo "ERROR: fuwari.desktop missing"; exit 1; }
[ -f "$SRC/fuwari.png" ]       || { echo "ERROR: fuwari.png missing"; exit 1; }

# ── 1. fetch + extract the manylinux Python base (old glibc → Deck-safe) ──
if ! ls python${PYVER}*-manylinux2014_x86_64.AppImage >/dev/null 2>&1; then
  echo "Fetching Python base..."
  URL=$(curl -s "https://api.github.com/repos/niess/python-appimage/releases/tags/python${PYVER}" \
        | grep browser_download_url | grep manylinux2014_x86_64 | grep -v aarch64 \
        | cut -d '"' -f4 | head -1)
  [ -n "$URL" ] || { echo "ERROR: couldn't find base; grab it from the python-appimage releases page"; exit 1; }
  curl -L -o "$(basename "$URL")" "$URL"
  chmod +x python${PYVER}*-manylinux2014_x86_64.AppImage
fi
./python${PYVER}*-manylinux2014_x86_64.AppImage --appimage-extract >/dev/null
rm -rf "$APPDIR"; mv squashfs-root "$APPDIR"
PYBIN=$(ls "$APPDIR"/opt/python*/bin/python3.* | grep -E 'python3\.[0-9]+$' | head -1)

# ── 2. dependencies ──────────────────────────────────────────────────
"$PYBIN" -m pip install --no-warn-script-location -r requirements.txt

# ── 3. UniDic dictionary (cache it so rebuilds don't re-download ~1GB) ──
DICDIR="$("$PYBIN" -c 'import unidic; print(unidic.DICDIR)')"
if [ -d "$UNIDIC_CACHE" ] && [ -n "$(ls -A "$UNIDIC_CACHE" 2>/dev/null)" ]; then
  echo "Restoring cached UniDic..."
  cp -rT "$UNIDIC_CACHE" "$DICDIR"
else
  echo "Downloading UniDic (~1GB, first build only)..."
  "$PYBIN" -m unidic download
  mkdir -p "$UNIDIC_CACHE"; cp -rT "$DICDIR" "$UNIDIC_CACHE"
fi

# ── 4. Fuwari source + native layer-shell .so ────────────────────────
install -d "$APPDIR/opt/fuwari"
cp "$SRC"/*.py "$SRC"/*.qml "$APPDIR/opt/fuwari/"

# build the release .so and bundle it at the path layer_shell.py expects
echo "Building layer-shell crate (release)..."
( cd "$SRC/fuwari-layer-shell" && cargo build --release )
install -d "$APPDIR/opt/fuwari/fuwari-layer-shell/target/release"
cp "$SRC/fuwari-layer-shell/target/release/libfuwari_layer_shell.so" \
   "$APPDIR/opt/fuwari/fuwari-layer-shell/target/release/"

# ── 5. wl-paste (clipboard texthook; SteamOS may not ship wl-clipboard) ──
cp "$(command -v wl-paste)" "$APPDIR/usr/bin/" 2>/dev/null || echo "WARN: wl-paste not bundled"

# ── 6. KDE LayerShell (QML module + Wayland shell integration plugin) ──
if [ "$BUNDLE_LAYERSHELL" = true ] && [ -d /usr/lib/qt6/qml/org/kde/layershell ]; then
  echo "Bundling KDE LayerShell..."
  KDE_QML="$("$PYBIN" -c 'import PySide6,os;print(os.path.join(os.path.dirname(PySide6.__file__),"Qt","qml","org","kde"))')"
  QT_LIB="$("$PYBIN" -c 'import PySide6,os;print(os.path.join(os.path.dirname(PySide6.__file__),"Qt","lib"))')"
  QT_PLUGINS="$("$PYBIN" -c 'import PySide6,os;print(os.path.join(os.path.dirname(PySide6.__file__),"Qt","plugins"))')"

  # the QML module itself
  mkdir -p "$KDE_QML" "$APPDIR/usr/lib"
  cp -r /usr/lib/qt6/qml/org/kde/layershell "$KDE_QML/"
  PLUGIN_SO="$(find "$KDE_QML/layershell" -name '*.so' | head -1)"
  [ -n "$PLUGIN_SO" ] || { echo "ERROR: layershell .so not found after copy"; exit 1; }

  # the shell-integration plugin LayerShellQt selects at runtime; without it
  # the import resolves but the surface is never created
  SHELL_SO=/usr/lib/qt6/plugins/wayland-shell-integration/liblayer-shell.so
  [ -f "$SHELL_SO" ] || { echo "ERROR: $SHELL_SO missing"; exit 1; }
  mkdir -p "$QT_PLUGINS/wayland-shell-integration"
  cp "$SHELL_SO" "$QT_PLUGINS/wayland-shell-integration/"

  # bundle both plugins' non-system, non-Qt-already-present deps
  for so in "$PLUGIN_SO" "$QT_PLUGINS/wayland-shell-integration/liblayer-shell.so"; do
    ldd "$so" | awk '/=> \//{print $3}' | while read -r lib; do
      name="$(basename "$lib")"
      [ -f "$QT_LIB/$name" ] && continue                       # already in PySide6's Qt
      case "$name" in libc.so*|libm.so*|libstdc++.so*|libgcc_s.so*|libdl.so*|libpthread.so*|librt.so*|libresolv.so*|libnss_*) continue;; esac
      cp "$lib" "$APPDIR/usr/lib/"
    done
  done
fi

# ── 7. AppRun ────────────────────────────────────────────────────────
rm -f "$APPDIR/AppRun"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
PYBIN="$(ls -d "$HERE"/opt/python*/bin/python3.* 2>/dev/null | grep -E 'python3\.[0-9]+$' | head -1)"
[ -n "$PYBIN" ] || { echo "ERROR: bundled Python not found"; exit 1; }
QTLIB="$("$PYBIN" -c 'import PySide6,os;print(os.path.join(os.path.dirname(PySide6.__file__),"Qt","lib"))')"
export LD_LIBRARY_PATH="$HERE/usr/lib:$QTLIB:${LD_LIBRARY_PATH:-}"
export PATH="$HERE/usr/bin:$PATH"
export QT_QPA_PLATFORM_PLUGIN_PATH="$("$PYBIN" -c 'import PySide6,os;print(os.path.join(os.path.dirname(PySide6.__file__),"Qt","plugins","platforms"))')"
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland}"
else
  export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
fi
# theme: inherit the user's Qt theme; only pick a fallback if none is set
export QT_PLUGIN_PATH="/usr/lib/qt6/plugins:${QT_PLUGIN_PATH:-}"
if [ -z "${QT_QPA_PLATFORMTHEME:-}" ]; then
  if   [ -f "$HOME/.config/qt6ct/qt6ct.conf" ] && [ -f /usr/lib/qt6/plugins/platformthemes/libqt6ct.so ]; then
    export QT_QPA_PLATFORMTHEME=qt6ct
  elif [ -f /usr/lib/qt6/plugins/platformthemes/KDEPlasmaPlatformTheme6.so ]; then
    export QT_QPA_PLATFORMTHEME=kde
  elif [ -f /usr/lib/qt6/plugins/platformthemes/libqgtk3.so ]; then
    export QT_QPA_PLATFORMTHEME=gtk3
  fi
fi
export QT_QML_APPLICATION_ICON="$HERE/fuwari.png"
cd "$HERE/opt/fuwari" || { echo "source missing"; exit 1; }
exec "$PYBIN" main.py "$@"
EOF
chmod +x "$APPDIR/AppRun"

# ── 8. desktop + icon ────────────────────────────────────────────────
cp "$SRC/fuwari.desktop" "$APPDIR/"
cp "$SRC/fuwari.png"     "$APPDIR/"

# strip the Python base's own desktop entry + icon so they don't win
rm -f "$APPDIR"/python*.desktop "$APPDIR"/python*.png
rm -f "$APPDIR"/usr/share/applications/python*.desktop 2>/dev/null || true

# make YOUR icon the bundle icon
rm -f "$APPDIR/.DirIcon"
cp "$APPDIR/fuwari.png" "$APPDIR/.DirIcon"

# ── 9. pack ──────────────────────────────────────────────────────────
appimagetool --no-appstream "$APPDIR" Fuwari-x86_64.AppImage
