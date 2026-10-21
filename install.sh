#!/usr/bin/env bash
# install.sh - Installer for NextBoot (nboot)
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "Error: Installation requires administrative privileges." >&2
    echo "Please execute: sudo ./install.sh" >&2
    exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)

echo "=== Installing NextBoot ==="

# 0. System dependencies
echo "0. Checking system dependencies..."
if command -v pacman >/dev/null 2>&1; then
    echo "Arch Linux detected. Ensuring efibootmgr, python-pyqt6, and qt6-wayland are installed..."
    pacman -S --needed --noconfirm efibootmgr python-pyqt6 qt6-wayland 2>/dev/null || true
elif command -v apt-get >/dev/null 2>&1; then
    echo "Debian/Ubuntu detected. Ensuring efibootmgr, python3-pyqt6, python3-pyqt6.qtsvg, and qt6-wayland are installed..."
    apt-get update -y && apt-get install -y efibootmgr python3-pyqt6 python3-pyqt6.qtsvg qt6-wayland 2>/dev/null || true
fi

# 1. Privileged backend helper
echo "1. Installing backend helper to /usr/local/libexec/nextboot-helper..."
mkdir -p /usr/local/libexec
install -m 755 "${SRC_DIR}/nextboot-helper.sh" /usr/local/libexec/nextboot-helper

# 2. Sudoers policy drop-in
echo "2. Installing sudoers policy to /etc/sudoers.d/99-nextboot..."
mkdir -p /etc/sudoers.d
install -m 440 "${SRC_DIR}/99-nextboot.sudoers" /etc/sudoers.d/99-nextboot

if ! visudo -cf /etc/sudoers.d/99-nextboot >/dev/null 2>&1; then
    echo "Error: Sudoers validation failed! Reverting sudoers installation." >&2
    rm -f /etc/sudoers.d/99-nextboot
    exit 1
fi

# 3. Application libraries and assets
echo "3. Installing application libraries and assets to /usr/local/share/nextboot..."
mkdir -p /usr/local/share/nextboot/assets/distros
install -m 644 "${SRC_DIR}/nextboot_core.py" /usr/local/share/nextboot/
install -m 644 "${SRC_DIR}/nextboot_cli.py" /usr/local/share/nextboot/
install -m 644 "${SRC_DIR}/nextboot_gui.py" /usr/local/share/nextboot/
install -m 644 "${SRC_DIR}"/assets/*.svg /usr/local/share/nextboot/assets/ 2>/dev/null || true
install -m 644 "${SRC_DIR}"/assets/*.png /usr/local/share/nextboot/assets/ 2>/dev/null || true
cp -r "${SRC_DIR}/assets/distros/." /usr/local/share/nextboot/assets/distros/
chmod 644 /usr/local/share/nextboot/assets/distros/*.svg

if [ -n "$TARGET_HOME" ]; then
    mkdir -p "$TARGET_HOME/.local/share/nextboot/assets/distros"
    cp -r "${SRC_DIR}/assets/distros/." "$TARGET_HOME/.local/share/nextboot/assets/distros/"
    chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.local/share/nextboot"
fi

# 4. Icon installation (grey/black arrow)
echo "4. Installing grey-black arrow icon..."
mkdir -p /usr/local/share/icons/hicolor/scalable/apps
install -m 644 "${SRC_DIR}/assets/app_icon.svg" /usr/local/share/icons/hicolor/scalable/apps/nextboot.svg

if [ -n "$TARGET_HOME" ]; then
    mkdir -p "$TARGET_HOME/.local/share/icons/hicolor/scalable/apps"
    install -m 644 -o "$TARGET_USER" -g "$TARGET_USER" "${SRC_DIR}/assets/app_icon.svg" "$TARGET_HOME/.local/share/icons/hicolor/scalable/apps/nextboot.svg"
fi

# 5. Binaries
echo "5. Installing executables to /usr/local/bin..."
install -m 755 "${SRC_DIR}/nboot" /usr/local/bin/nboot
ln -sf /usr/local/bin/nboot /usr/local/bin/nextboot

# 6. Desktop entry for Utilities category
echo "6. Configuring desktop entry for 'Utilities'..."
mkdir -p /usr/local/share/applications
install -m 644 "${SRC_DIR}/nextboot.desktop" /usr/local/share/applications/nextboot.desktop

if [ -n "$TARGET_HOME" ]; then
    mkdir -p "$TARGET_HOME/.local/share/applications"
    install -m 644 -o "$TARGET_USER" -g "$TARGET_USER" "${SRC_DIR}/nextboot.desktop" "$TARGET_HOME/.local/share/applications/nextboot.desktop"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/local/share/applications 2>/dev/null || true
    if [ -n "$TARGET_HOME" ] && [ -d "$TARGET_HOME/.local/share/applications" ]; then
        update-desktop-database "$TARGET_HOME/.local/share/applications" 2>/dev/null || true
    fi
fi

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental 2>/dev/null || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
    kbuildsycoca5 --noincremental 2>/dev/null || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/local/share/icons/hicolor 2>/dev/null || true
fi

# 7. Bash completion
echo "7. Installing bash completion..."
if [ -d /usr/share/bash-completion/completions ]; then
    install -m 644 "${SRC_DIR}/completions/nboot.bash" /usr/share/bash-completion/completions/nboot
    ln -sf /usr/share/bash-completion/completions/nboot /usr/share/bash-completion/completions/nextboot 2>/dev/null || true
fi

# 8. Hyprland configuration (Floating & centered window rule)
if [ -n "$TARGET_HOME" ] && [ -d "$TARGET_HOME/.config/hypr" ]; then
    HYPR_CONF="$TARGET_HOME/.config/hypr/hyprland.conf"
    if [ -f "$HYPR_CONF" ]; then
        if ! grep -q "class:\^(nextboot|NextBoot)\$" "$HYPR_CONF" 2>/dev/null; then
            echo "8. Hyprland configuration detected. Adding floating window rule..."
            cat << 'EOF' >> "$HYPR_CONF"

# NextBoot Window Rule (Floating & Centered)
windowrulev2 = float, class:^(nextboot|NextBoot)$
windowrulev2 = size 580 585, class:^(nextboot|NextBoot)$
windowrulev2 = center, class:^(nextboot|NextBoot)$
EOF
            chown "$TARGET_USER:$TARGET_USER" "$HYPR_CONF"
        fi
    fi
fi

echo "=== NextBoot successfully installed! ==="
echo "App icon: Grey/Black arrow."
echo "Desktop launcher registered under 'Local Tools'."
echo "You can launch via 'nboot gui' or use CLI commands like 'nboot win' or 'nboot nobara'."
