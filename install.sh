#!/usr/bin/env bash
# Oracle installer — sets up the venv, installs deps, and registers the
# launcher symlink + desktop entry + theme icon (SVG + multi-size PNG
# fallbacks) for the current user. Refreshes GTK + KDE icon caches.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
SVG_SRC="$DIR/assets/oracle.svg"

# ─────────────────────────────────────────────────────────────────────────
# 1. venv + deps
# ─────────────────────────────────────────────────────────────────────────
echo "[oracle] Setting up venv at $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip >/dev/null
"$VENV/bin/pip" install -r "$DIR/requirements.txt"

# ─────────────────────────────────────────────────────────────────────────
# 2. Per-user launcher on PATH
# ─────────────────────────────────────────────────────────────────────────
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$DIR/run.sh" "$BIN_DIR/oracle"
echo "[oracle] Launcher: $BIN_DIR/oracle"

# ─────────────────────────────────────────────────────────────────────────
# 3. Install icon — SVG into scalable/apps/, and PNG fallbacks at the
#    standard hicolor sizes. KDE Plasma especially prefers size-specific
#    PNGs over SVG for menu / taskbar rendering.
# ─────────────────────────────────────────────────────────────────────────
ICON_THEME_ROOT="$HOME/.local/share/icons/hicolor"

# SVG (scalable)
SVG_DIR="$ICON_THEME_ROOT/scalable/apps"
mkdir -p "$SVG_DIR"
cp -f "$SVG_SRC" "$SVG_DIR/oracle.svg"
echo "[oracle] Icon (SVG): $SVG_DIR/oracle.svg"

# Pick an SVG-to-PNG renderer. rsvg-convert is by far the best choice
# (clean, fast, comes with librsvg). Fall back to ImageMagick if it's
# missing. If neither is available, log a warning — SVG-only install
# still works for most desktops but KDE menu icons may not appear.
RENDERER=""
if command -v rsvg-convert >/dev/null 2>&1; then
    RENDERER="rsvg-convert"
elif command -v magick >/dev/null 2>&1; then
    RENDERER="magick"
elif command -v convert >/dev/null 2>&1; then
    RENDERER="convert"
fi

render_png() {
    # $1=size, $2=output path
    local size="$1" out="$2"
    case "$RENDERER" in
        rsvg-convert) rsvg-convert -w "$size" -h "$size" -o "$out" "$SVG_SRC" ;;
        magick)       magick -background none -density 384 "$SVG_SRC" -resize "${size}x${size}" "$out" ;;
        convert)      convert -background none -density 384 "$SVG_SRC" -resize "${size}x${size}" "$out" ;;
        *) return 1 ;;
    esac
}

if [[ -n "$RENDERER" ]]; then
    SIZES=(16 22 24 32 48 64 96 128 192 256 512)
    for size in "${SIZES[@]}"; do
        PNG_DIR="$ICON_THEME_ROOT/${size}x${size}/apps"
        mkdir -p "$PNG_DIR"
        render_png "$size" "$PNG_DIR/oracle.png"
    done
    echo "[oracle] Icon PNG fallbacks: ${#SIZES[@]} sizes (16…512) via $RENDERER"
else
    echo "[oracle] WARNING: no SVG renderer found (rsvg-convert / ImageMagick)."
    echo "         Falling back to SVG-only install — KDE menu icons may not appear."
    echo "         Install librsvg2-bin or imagemagick and re-run this script."
fi

# ─────────────────────────────────────────────────────────────────────────
# 4. Desktop entry
# ─────────────────────────────────────────────────────────────────────────
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
sed -e "s|@LAUNCHER@|$DIR/run.sh|g" \
    "$DIR/oracle.desktop.in" > "$APPS_DIR/oracle.desktop"
chmod +x "$APPS_DIR/oracle.desktop"
echo "[oracle] Desktop entry: $APPS_DIR/oracle.desktop"

# ─────────────────────────────────────────────────────────────────────────
# 5. Refresh caches — GTK, KDE, and the desktop-file database. KDE Plasma
#    in particular caches .desktop entries in sycoca and will silently
#    ignore new entries until you rebuild it.
# ─────────────────────────────────────────────────────────────────────────
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache --force --ignore-theme-index "$ICON_THEME_ROOT" 2>/dev/null || true
    echo "[oracle] Refreshed GTK icon cache"
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
    echo "[oracle] Refreshed desktop database"
fi
# KDE Plasma sycoca rebuild (KDE 6 → kbuildsycoca6, KDE 5 → kbuildsycoca5)
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
    echo "[oracle] Rebuilt KDE sycoca (kbuildsycoca6)"
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
    kbuildsycoca5 --noincremental >/dev/null 2>&1 || true
    echo "[oracle] Rebuilt KDE sycoca (kbuildsycoca5)"
fi

echo
echo "[oracle] Install complete."
echo "  • Run from terminal:   oracle              (detaches, returns immediately)"
echo "  • Run in foreground:   oracle --foreground (for debugging)"
echo "  • App menu:            Development → Oracle"
echo
echo "If the icon still doesn't show up in the taskbar or menu, try:"
echo "  • Logging out / back in (some desktops aggressively cache)"
echo "  • Manually: kbuildsycoca6 --noincremental && gtk-update-icon-cache --force ~/.local/share/icons/hicolor"
