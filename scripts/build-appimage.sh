#!/usr/bin/env bash
set -euo pipefail

# ── config ──────────────────────────────────────────────────────────
APPDIR=Fuwari.AppDir
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYVER=3.14
BUNDLE_LAYERSHELL=true  # set false once you confirm QML doesn't use LayerShell

export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt  # manylinux py needs this for TLS

# ── 0. prerequisites: fail early, not after a 1GB download ───────────
command -v appimagetool >/dev/null || { echo "ERROR: appimagetool missing (AUR: appimagetool-bin)"; exit 1; }
command -v cargo >/dev/null || { echo "ERROR: cargo missing (rustup or pacman: rust)"; exit 1; }
[ -f "$SRC/requirements.txt" ] || { echo "ERROR: requirements.txt missing"; exit 1; }
[ -f "$SRC/fuwari.desktop" ]   || { echo "ERROR: fuwari.desktop missing"; exit 1; }
[ -f "$SRC/assets/fuwari.png" ] || { echo "ERROR: assets/fuwari.png missing"; exit 1; }

# ── 1. fetch + extract the manylinux Python base (old glibc → Deck-safe) ──
if ! ls python${PYVER}*-manylinux2014_x86_64.AppImage >/dev/null 2>&1; then
  echo "Fetching Python base..."
  URL=$(curl -s "https://api.github.com/repos/niess/python-appimage/releases/tags/python${PYVER}" \
        | grep browser_download_url | grep manylinux2014_x86_64 | grep -v aarch64 | grep -v 'cp3[0-9]*t-' \
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

# ── 4. Fuwari source + native layer-shell .so ────────────────────────
install -d "$APPDIR/opt/fuwari"
cp "$SRC"/*.py "$APPDIR/opt/fuwari/"
cp -r "$SRC/ui" "$SRC/dictionary" "$SRC/ocr" "$SRC/anki" "$SRC/wayland" "$APPDIR/opt/fuwari/"
rm -rf "$APPDIR/opt/fuwari/wayland/fuwari-layer-shell/target"
# dev-only helpers live in scripts/ and are simply not copied
# development-only helpers, not part of the app

# build the release .so and bundle it at the path layer_shell.py expects
echo "Building layer-shell crate (release)..."
( cd "$SRC/wayland/fuwari-layer-shell" && cargo build --release )
install -d "$APPDIR/opt/fuwari/wayland/fuwari-layer-shell/target/release"
cp "$SRC/wayland/fuwari-layer-shell/target/release/libfuwari_layer_shell.so" \
   "$APPDIR/opt/fuwari/wayland/fuwari-layer-shell/target/release/"
[ -f "$APPDIR/opt/fuwari/wayland/fuwari-layer-shell/target/release/libfuwari_layer_shell.so" ] \
  || { echo "ERROR: libfuwari_layer_shell.so did not land in the AppDir"; exit 1; }


# ── 5. wl-paste (clipboard texthook; SteamOS may not ship wl-clipboard) ──
cp "$(command -v wl-paste)" "$APPDIR/usr/bin/" 2>/dev/null || echo "WARN: wl-paste not bundled"

# ── 6. KDE LayerShell (QML module + Wayland shell integration plugin) ──
if [ "$BUNDLE_LAYERSHELL" = true ]; then
  # Fail loudly. Skipping this silently produces an AppImage where every
  # window falls back to an ordinary toplevel -- indistinguishable from the
  # legacy_windows setting being on, so the resulting bug reports blame the
  # setting rather than the build.
  [ -d /usr/lib/qt6/qml/org/kde/layershell ] \
    || { echo "ERROR: /usr/lib/qt6/qml/org/kde/layershell missing (pacman: layer-shell-qt)"; exit 1; }
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

# ── 6b. drop libraries that must come from the host ──────────────────
# AppRun puts the bundle's usr/lib first on LD_LIBRARY_PATH while also pointing
# QT_PLUGIN_PATH at the host's Qt plugins, so the user's theme still applies.
# That mix breaks whenever the bundle ships an OLDER copy of a library a host
# plugin needs. The manylinux2014 base carries CentOS 7-era liblzma, so loading
# the host's libqt6ct.so fails with "version `XZ_5.4' not found" and Qt silently
# falls back to its default light palette -- no error, just the wrong theme.
#
# These are on the standard AppImage excludelist for exactly this reason: they
# exist on every target system and must never be shadowed by the bundle.
echo "Removing host-provided libraries from the bundle..."
for pat in 'liblzma.so*' 'libbz2.so*' 'libselinux.so*'; do
  find "$APPDIR" -name "$pat" -print -delete 2>/dev/null || true
done

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
# The palette comes from the platform theme. With none, Qt uses its built-in
# light default regardless of what the desktop is set to, which is why an
# AppImage can look light while a source run looks dark.
if [ -z "${QT_QPA_PLATFORMTHEME:-}" ]; then
  echo "fuwari: no Qt platform theme found; using Qt's default (light) palette." >&2
  echo "        Set QT_QPA_PLATFORMTHEME=qt6ct (or kde, gtk3) to match your desktop." >&2
fi
# Qt Quick Controls styles such as Breeze live in the host's QML path, which the
# bundled Qt does not search -- so a style the source run picks up is missing
# here and Controls fall back to their plain default. Opt-in, because loading
# host QML into a bundled Qt can mismatch across Qt versions.
if [ -n "${FUWARI_HOST_QML:-}" ] && [ -d /usr/lib/qt6/qml ]; then
  export QML2_IMPORT_PATH="/usr/lib/qt6/qml:${QML2_IMPORT_PATH:-}"
  export QML_IMPORT_PATH="/usr/lib/qt6/qml:${QML_IMPORT_PATH:-}"
fi
if [ -n "${FUWARI_DEBUG_THEME:-}" ]; then
  echo "fuwari: platformtheme=${QT_QPA_PLATFORMTHEME:-<none>}" >&2
  echo "fuwari: controls style=${QT_QUICK_CONTROLS_STYLE:-<default>}" >&2
  echo "fuwari: qml path=${QML2_IMPORT_PATH:-<bundled only>}" >&2
fi
export QT_QML_APPLICATION_ICON="$HERE/fuwari.png"
cd "$HERE/opt/fuwari" || { echo "source missing"; exit 1; }
exec "$PYBIN" main.py "$@"
EOF
chmod +x "$APPDIR/AppRun"

# ── 8. desktop + icon ────────────────────────────────────────────────
cp "$SRC/fuwari.desktop" "$APPDIR/"
cp "$SRC/assets/fuwari.png" "$APPDIR/"

# strip the Python base's own desktop entry + icon so they don't win
rm -f "$APPDIR"/python*.desktop "$APPDIR"/python*.png
rm -f "$APPDIR"/usr/share/applications/python*.desktop 2>/dev/null || true

# make YOUR icon the bundle icon
rm -f "$APPDIR/.DirIcon"
cp "$APPDIR/fuwari.png" "$APPDIR/.DirIcon"

# ── 9. pack ──────────────────────────────────────────────────────────
appimagetool --no-appstream "$APPDIR" Fuwari-x86_64.AppImage
