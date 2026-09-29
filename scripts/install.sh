#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
# Install FreeFusion on any Linux distribution.
#
#   ./scripts/install.sh              install for the current user (~/.local)
#   ./scripts/install.sh --system     install for all users (/usr/local, needs root)
#   ./scripts/install.sh --dev        like the default, but symlink this checkout (for development)
#   ./scripts/install.sh --freecad-addon   also make the workbench appear inside regular FreeCAD
#   ./scripts/install.sh --uninstall  remove what the matching install created
set -euo pipefail

src="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
mode=user
dev=0
addon=0
uninstall=0
for a in "$@"; do
    case "$a" in
        --system) mode=system ;;
        --user) mode=user ;;
        --dev) dev=1 ;;
        --freecad-addon) addon=1 ;;
        --uninstall) uninstall=1 ;;
        -h|--help) sed -n '3,10p' "$0"; exit 0 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

if [ "$mode" = system ]; then
    prefix="${PREFIX:-/usr/local}"
    share="$prefix/share"
    bindir="$prefix/bin"
else
    share="${XDG_DATA_HOME:-$HOME/.local/share}"
    bindir="$HOME/.local/bin"
fi
dest="$share/freefusion"
apps="$share/applications"
icons="$share/icons/hicolor/scalable/apps"

# FreeCAD's per-user module folders (1.0: FreeCAD/Mod, 1.1+: FreeCAD/v1-x/Mod, Flatpak)
freecad_mod_dirs() {
    local base="${XDG_DATA_HOME:-$HOME/.local/share}/FreeCAD"
    local found=0
    if command -v freecadcmd >/dev/null 2>&1; then
        local d
        d="$(freecadcmd -c 'import FreeCAD;print(FreeCAD.getUserAppDataDir())' 2>/dev/null | tail -1 || true)"
        if [ -n "$d" ] && [ -d "$d" ]; then echo "${d%/}/Mod"; found=1; fi
    fi
    for d in "$base"/v1-*; do [ -d "$d" ] && echo "$d/Mod" && found=1; done
    [ -d "$base" ] && echo "$base/Mod" && found=1
    local fp="$HOME/.var/app/org.freecad.FreeCAD/data/FreeCAD"
    [ -d "$fp" ] && echo "$fp/Mod" && for d in "$fp"/v1-*; do [ -d "$d" ] && echo "$d/Mod"; done
    [ "$found" = 1 ] || echo "$base/Mod"
}

if [ "$uninstall" = 1 ]; then
    rm -rf "$dest"
    rm -f "$bindir/freefusion" "$apps/freefusion.desktop" "$icons/freefusion.svg"
    for m in $(freecad_mod_dirs | sort -u); do
        if [ -L "$m/FreeFusion" ]; then rm -f "$m/FreeFusion"; fi
    done
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true
    echo "FreeFusion removed. Your FreeFusion profile is kept in ~/.config/freefusion (delete it to reset)."
    exit 0
fi

mkdir -p "$share" "$bindir" "$apps" "$icons"
rm -rf "$dest"
if [ "$dev" = 1 ]; then
    ln -s "$src" "$dest"
else
    mkdir -p "$dest"
    cp -r "$src/freefusion" "$src/InitGui.py" "$src/Init.py" "$src/package.xml" "$src/LICENSE" \
          "$src/README.md" "$src/scripts" "$dest/"
    find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} +
fi
ln -sf "$dest/scripts/freefusion" "$bindir/freefusion"
chmod +x "$dest/scripts/freefusion"
sed "s|^Exec=freefusion|Exec=$bindir/freefusion|" "$src/scripts/freefusion.desktop" > "$apps/freefusion.desktop"
cp "$src/freefusion/resources/icons/FreeFusion.svg" "$icons/freefusion.svg"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q "$share/icons/hicolor" 2>/dev/null || true

if [ "$addon" = 1 ]; then
    for m in $(freecad_mod_dirs | sort -u); do
        mkdir -p "$m"
        if [ -e "$m/FreeFusion" ] && [ ! -L "$m/FreeFusion" ]; then
            echo "note: $m/FreeFusion exists (Addon Manager install?) - left untouched"
            continue
        fi
        ln -sfn "$dest" "$m/FreeFusion"
        echo "linked into $m"
    done
fi

echo "FreeFusion installed to $dest"
echo "Start it with 'freefusion' or from your application menu."
case ":$PATH:" in *":$bindir:"*) ;; *) echo "note: $bindir is not on your PATH";; esac
if ! command -v freecad >/dev/null 2>&1 && ! command -v FreeCAD >/dev/null 2>&1; then
    echo "note: FreeCAD (1.0 or newer) was not found. Install it with your package manager, e.g.:"
    echo "      Arch: sudo pacman -S freecad | Fedora: sudo dnf install freecad"
    echo "      Debian/Ubuntu: sudo apt install freecad | any: flatpak install flathub org.freecad.FreeCAD"
fi
