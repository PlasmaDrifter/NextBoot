#!/usr/bin/env bash
# uninstall.sh - Uninstaller for NextBoot
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "Error: Uninstallation requires administrative privileges." >&2
    echo "Please execute: sudo ./uninstall.sh" >&2
    exit 1
fi

TARGET_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)

echo "=== Removing NextBoot ==="

rm -f /usr/local/libexec/nextboot-helper
rm -f /etc/sudoers.d/99-nextboot
rm -rf /usr/local/share/nextboot
rm -f /usr/local/bin/nboot
rm -f /usr/local/bin/nextboot
rm -f /usr/local/share/applications/nextboot.desktop
rm -f /usr/local/share/icons/hicolor/scalable/apps/nextboot.svg
rm -f /usr/share/bash-completion/completions/nboot
rm -f /usr/share/bash-completion/completions/nextboot

if [ -n "$TARGET_HOME" ]; then
    rm -f "$TARGET_HOME/.local/share/applications/nextboot.desktop"
    rm -f "$TARGET_HOME/.local/share/icons/hicolor/scalable/apps/nextboot.svg"
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

echo "=== NextBoot uninstalled successfully! ==="
