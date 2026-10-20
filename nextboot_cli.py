#!/usr/bin/env python3
"""
nextboot_cli.py - Command-line interface for NextBoot (nboot)
"""

import argparse
import sys
import time
from typing import List, Optional

from nextboot_core import (
    BootEntry,
    UEFIManager,
    execute_reboot,
    get_config_path,
    load_config,
    save_config,
    set_bootnext,
    __version__,
)


def print_banner():
    print(f"NextBoot ({__version__}) - Multi-OS One-Time Reboot Utility")
    print("-" * 55)


def cmd_list(mgr: UEFIManager):
    print_banner()

    print(f"Current Booted OS : Boot{mgr.boot_current or 'Unknown'}")
    if mgr.boot_next:
        print(f"Pending BootNext  : Boot{mgr.boot_next}\n")
    else:
        print("Pending BootNext  : None (standard boot)\n")

    print(f"{'BOOT ID':<10} {'STATUS':<18} {'OS TITLE':<32} {'CLI SHORTHAND'}")
    print("-" * 75)

    default_entry = mgr.get_default_entry()
    for entry in mgr.entries:
        is_current = (entry.entry_id == mgr.boot_current)
        is_default = (default_entry and entry.entry_id == default_entry.entry_id)

        status_flags = []
        if is_default:
            status_flags.append("DEFAULT")
        if is_current:
            status_flags.append("CURRENT")
        if not entry.active:
            status_flags.append("INACTIVE")

        status_str = ", ".join(status_flags) if status_flags else "READY"
        primary_slug = entry.slugs[0] if entry.slugs else entry.entry_id.lower()
        shorthand_str = f"nboot {primary_slug}"

        print(f"Boot{entry.entry_id:<6} {status_str:<18} {entry.title:<32} {shorthand_str}")

    print("-" * 75)
    print("Special shortcuts: nboot bios | nboot uefi (Reboots into BIOS/UEFI setup)")


def cmd_status(mgr: UEFIManager):
    print_banner()
    config = load_config()
    default_target = config.get("default_target", "windows")
    default_entry = mgr.get_default_entry()

    print(f"Configuration file: {get_config_path()}")
    print(f"Default target    : {default_target} ({default_entry.title if default_entry else 'Not detected'})")
    print(f"Current OS ID     : Boot{mgr.boot_current or 'Unknown'}")
    print(f"Active BootOrder  : {', '.join(['Boot' + x for x in mgr.boot_order])}")
    print(f"Next Boot Target  : {('Boot' + mgr.boot_next) if mgr.boot_next else 'Standard BootOrder'}")


def cmd_set_default(mgr: UEFIManager, target: str):
    entry = mgr.find_entry(target)
    if not entry:
        print(f"Error: Target '{target}' not found among detected boot entries.")
        print("Run 'nboot list' to inspect available entries.")
        sys.exit(1)

    config = load_config()
    config["default_target"] = entry.slugs[0] if entry.slugs else entry.entry_id
    save_config(config)
    print(f"Successfully set default target to: {entry.title} (Boot{entry.entry_id})")


def prompt_confirmation(target_title: str, is_firmware: bool = False) -> bool:
    if is_firmware:
        prompt_text = "Reboot into Motherboard UEFI / BIOS Setup now? [Y/n]: "
    else:
        prompt_text = f"Reboot into '{target_title}' now? [Y/n]: "

    try:
        choice = input(prompt_text).strip().lower()
        return choice in ["", "y", "yes"]
    except (KeyboardInterrupt, EOFError):
        print("\nReboot cancelled.")
        return False


def run_reboot_flow(
    mgr: UEFIManager,
    target_query: Optional[str] = None,
    firmware_setup: bool = False,
    skip_confirm: bool = False,
    dry_run: bool = False,
):
    if firmware_setup:
        target_title = "UEFI Firmware / BIOS Setup"
        target_entry = None
    else:
        if target_query:
            target_entry = mgr.find_entry(target_query)
            if not target_entry:
                print(f"Error: Boot target '{target_query}' not recognized.")
                print("Run 'nboot list' to view available operating systems.")
                sys.exit(1)
        else:
            target_entry = mgr.get_default_entry()
            if not target_entry:
                print("Error: No default boot target found.")
                print("Please ensure your target operating system is registered or run 'nboot list'.")
                sys.exit(1)

        target_title = target_entry.title

    if not skip_confirm and sys.stdin.isatty():
        if not prompt_confirmation(target_title, is_firmware=firmware_setup):
            return

    if not firmware_setup and target_entry:
        print(f"Configuring one-time boot for: {target_entry.title} (Boot{target_entry.entry_id})...")
        success, message = set_bootnext(target_entry.entry_id, dry_run=dry_run)
        if not success:
            print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)
        print(message)

    print(f"Initiating reboot into {target_title}...")
    success, message = execute_reboot(firmware_setup=firmware_setup, dry_run=dry_run)
    if not success:
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)
    print(message)


def main():
    mgr = UEFIManager()

    args = sys.argv[1:]

    # Check for direct flags
    dry_run = False
    skip_confirm = False
    filtered_args = []

    for arg in args:
        if arg in ["-d", "--dry-run"]:
            dry_run = True
        elif arg in ["-y", "--yes", "--now"]:
            skip_confirm = True
        else:
            filtered_args.append(arg)

    if not filtered_args:
        # Default action: reboot into configured default
        run_reboot_flow(mgr, target_query=None, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    sub = filtered_args[0].lower().lstrip("-")

    if sub in ["h", "help"]:
        print("Usage: nboot [COMMAND|TARGET] [OPTIONS]")
        print("\nCommands:")
        print("  nboot                    Reboot into configured default OS")
        print("  nboot win | windows      Reboot into Windows")
        print("  nboot fedora | nobara    Reboot into Fedora / Nobara")
        print("  nboot bios | uefi        Reboot into UEFI Firmware / BIOS Setup")
        print("  nboot list | ls          List all bootable operating systems")
        print("  nboot status             Show current UEFI BootNext status")
        print("  nboot set-default <os>   Set default target OS")
        print("  nboot gui                Launch graphical interface")
        print("\nOptions:")
        print("  -y, --now                Reboot immediately without confirmation prompt")
        print("  -d, --dry-run            Simulate execution without modifying NVRAM or rebooting")
        print("  -h, --help               Show this help message")
        return

    if sub in ["l", "ls", "list"]:
        cmd_list(mgr)
        return

    if sub in ["status", "info"]:
        cmd_status(mgr)
        return

    if sub in ["set", "set-default", "setdefault"]:
        if len(filtered_args) < 2:
            print("Error: Specify target OS to set as default. Example: nboot set-default win")
            sys.exit(1)
        cmd_set_default(mgr, filtered_args[1])
        return

    if sub in ["g", "gui"]:
        # Launch GUI module
        from nextboot_gui import launch_gui
        launch_gui()
        return

    if sub in ["bios", "uefi", "firmware"]:
        run_reboot_flow(mgr, firmware_setup=True, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    if sub in ["default", "def"]:
        run_reboot_flow(mgr, target_query=None, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    # Check if sub matches any detected boot entry
    entry = mgr.find_entry(sub)
    if entry:
        run_reboot_flow(mgr, target_query=sub, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    print(f"Unknown command or target: '{filtered_args[0]}'")
    print("Run 'nboot list' to see available operating systems or 'nboot --help' for help.")
    sys.exit(1)


if __name__ == "__main__":
    main()
