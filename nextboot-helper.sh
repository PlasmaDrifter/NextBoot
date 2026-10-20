#!/usr/bin/env bash
# nextboot-helper - Privileged helper for NextBoot
# Sets the UEFI BootNext variable for the specified boot entry.
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: $(basename "$0") <BOOT_ENTRY_HEX>" >&2
    echo "Example: $(basename "$0") 0000" >&2
    exit 1
fi

ENTRY="$1"

# Validate 4-digit hexadecimal format strictly
if [[ ! "$ENTRY" =~ ^[0-9A-Fa-f]{4}$ ]]; then
    echo "Error: Invalid boot entry format '$ENTRY'. Must be 4 hex digits (e.g. 0000)." >&2
    exit 1
fi

# Ensure efibootmgr is available
if ! command -v efibootmgr >/dev/null 2>&1; then
    echo "Error: efibootmgr command not found." >&2
    exit 1
fi

# Execute BootNext
echo "Setting UEFI BootNext to ${ENTRY}..."
efibootmgr --bootnext "${ENTRY}" >/dev/null

echo "UEFI BootNext successfully set to Boot${ENTRY}."
