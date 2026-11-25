#!/usr/bin/env python3
"""
nextboot_cli.py - Command-line interface for NextBoot (nboot)
"""

from __future__ import annotations

import os
import sys

from nextboot_core import (
    FIRMWARE_TARGETS,
    UEFIManager,
    __version__,
    clear_bootnext,
    execute_reboot,
    get_config_path,
    hide_entry,
    is_entry_hidden,
    load_config,
    save_config,
    set_bootnext,
    unhide_entry,
)


def print_banner():
    print(f"NextBoot ({__version__}) - Multi-OS One-Time Reboot Utility")
    print("-" * 55)


def print_help():
    print("Usage: nboot [COMMAND|TARGET] [OPTIONS]")
    print("\nCommands:")
    print("  nboot                    Reboot into configured default OS")
    print("  nboot win | windows      Reboot into Windows")
    print("  nboot fedora | nobara    Reboot into Fedora / Nobara")
    print("  nboot bios | uefi        Reboot into UEFI Firmware / BIOS Setup")
    print("  nboot list | ls [-a]     List bootable operating systems (use -a to include hidden)")
    print("  nboot status             Show current UEFI BootNext status")
    print("  nboot set-default <os>   Set default target OS (or 'uefi')")
    print("  nboot clear              Clear any pending UEFI BootNext override")
    print("  nboot hide <target>      Hide a boot entry from the main list")
    print("  nboot unhide <target>    Restore a hidden entry (use 'all' to restore everything)")
    print("  nboot hidden             List all currently hidden entries")
    print("  nboot gui                Launch graphical interface")
    print("\nOptions:")
    print("  -a, --all                Show all entries including hidden ones in 'nboot list'")
    print("  -y, --yes, --now         Reboot immediately without confirmation prompt")
    print("  -d, --dry-run            Simulate execution without modifying NVRAM or rebooting")
    print("  -g, --gui                Launch graphical interface")
    print("  -V, --version            Show version information")
    print("  -h, --help               Show this help message")


def cmd_list(mgr: UEFIManager, show_all: bool = False):
    print_banner()

    print(f"Current Booted OS : Boot{mgr.boot_current or 'Unknown'}")
    if mgr.boot_next:
        print(f"Pending BootNext  : Boot{mgr.boot_next}\n")
    else:
        print("Pending BootNext  : None (standard boot)\n")

    print(f"{'BOOT ID':<10} {'STATUS':<18} {'OS TITLE':<30} {'CLI SHORTHAND'}")
    print("-" * 88)

    config = load_config()
    hidden_raw = config.get("hidden_entries", [])
    hidden_list = [str(x) for x in hidden_raw] if isinstance(hidden_raw, list) else []
    hidden_count = 0

    default_entry = mgr.get_firmware_default_entry()
    entries_to_show = mgr.all_entries if show_all else mgr.entries
    for entry in entries_to_show:
        is_hidden = is_entry_hidden(entry, hidden_list, is_firmware=False)
        if is_hidden:
            hidden_count += 1
            if not show_all:
                continue

        is_current = (entry.entry_id == mgr.boot_current)
        is_default = (default_entry is not None and entry.entry_id == default_entry.entry_id)

        status_flags = []
        if is_default:
            status_flags.append("DEFAULT")
        if is_current:
            status_flags.append("CURRENT")
        if not entry.active:
            status_flags.append("INACTIVE")
        if not entry.is_os_entry() and show_all:
            status_flags.append("FIRMWARE" if "fvfile" in entry.extra.lower() else "DEVICE")
        if is_hidden and show_all:
            status_flags.append("HIDDEN")

        status_str = ", ".join(status_flags) if status_flags else "READY"
        short_slugs = entry.get_short_slugs()
        shorthand_str = "nboot " + " | ".join(short_slugs)

        print(f"Boot{entry.entry_id:<6} {status_str:<18} {entry.title:<30} {shorthand_str}")

    fw_hidden = is_entry_hidden(None, hidden_list, is_firmware=True)
    if fw_hidden:
        hidden_count += 1

    print("-" * 88)
    if not fw_hidden or show_all:
        fw_hidden_note = " [HIDDEN]" if fw_hidden and show_all else ""
        print(f"Special shortcuts: nboot bios | nboot uefi (Reboots into BIOS/UEFI setup){fw_hidden_note}")
    if hidden_count > 0 and not show_all:
        print(f"Note: {hidden_count} entries are hidden. Run 'nboot list --all' or 'nboot hidden' to view.")


def cmd_hide(mgr: UEFIManager, target: str):
    success, msg = hide_entry(target, mgr)
    if success:
        print(msg)
    else:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_unhide(mgr: UEFIManager, target: str):
    success, msg = unhide_entry(target, mgr)
    if success:
        print(msg)
    else:
        print(f"Error: {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_hidden(mgr: UEFIManager):
    print_banner()
    hidden_items = mgr.get_hidden_entries()
    if not hidden_items:
        print("No boot entries are currently hidden.")
        print("To hide an entry from the list, run: nboot hide <target>")
        return

    print(f"Currently Hidden Entries ({len(hidden_items)}):")
    print("-" * 75)
    for entry, is_fw in hidden_items:
        if is_fw or entry is None:
            print("  [FIRMWARE]  UEFI Firmware Setup (restore with: nboot unhide uefi)")
        else:
            restore_id = getattr(entry, "hidden_identifier", entry.entry_id)
            label_id = f"Boot{entry.entry_id}" if entry.entry_id != "----" else "CUSTOM    "
            print(f"  {label_id:<10}  {entry.title:<30} (restore with: nboot unhide {restore_id})")
    print("-" * 75)
    print("To restore all entries at once, run: nboot unhide all")


def cmd_status(mgr: UEFIManager):
    print_banner()
    fw_default = mgr.get_firmware_default_entry()
    default_entry, is_fw_default, default_target = mgr.get_configured_default()

    if is_fw_default:
        resolved_desc = "UEFI Firmware / BIOS Setup"
    elif default_entry:
        resolved_desc = default_entry.title
    else:
        resolved_desc = "Not detected"

    fw_desc = f"Boot{fw_default.entry_id} ({fw_default.title})" if fw_default else "Unknown"

    print(f"Configuration file: {get_config_path()}")
    print(f"UEFI Default OS   : {fw_desc}")
    print(f"CLI Target (nboot): {default_target or 'auto'} ({resolved_desc})")
    print(f"Current OS ID     : Boot{mgr.boot_current or 'Unknown'}")
    print(f"Active BootOrder  : {', '.join(['Boot' + x for x in mgr.boot_order])}")
    print(f"Next Boot Target  : {('Boot' + mgr.boot_next) if mgr.boot_next else 'Standard BootOrder'}")


def cmd_set_default(mgr: UEFIManager, target: str):
    target_clean = target.strip()
    if target_clean.lower() in FIRMWARE_TARGETS:
        config = load_config()
        config["default_target"] = "uefi"
        save_config(config)
        print("Successfully set default target to: UEFI Firmware / BIOS Setup (uefi)")
        return

    entry = mgr.find_entry(target_clean, include_non_os=False)
    if not entry:
        print(f"Error: Target '{target}' not found among detected boot entries.", file=sys.stderr)
        print("Run 'nboot list' to inspect available entries.", file=sys.stderr)
        sys.exit(1)

    stored_target = entry.entry_id
    if entry.slugs:
        primary_slug = entry.slugs[0]
        matching_count = sum(1 for e in mgr.entries if primary_slug in e.slugs)
        if matching_count == 1:
            stored_target = primary_slug

    config = load_config()
    config["default_target"] = stored_target
    save_config(config)
    print(f"Successfully set default target to: {entry.title} (Boot{entry.entry_id})")


def cmd_clear(dry_run: bool = False):
    success, message = clear_bootnext(dry_run=dry_run)
    if success:
        print(message)
    else:
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)


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
    target_query: str | None = None,
    firmware_setup: bool = False,
    skip_confirm: bool = False,
    dry_run: bool = False,
):
    target_entry = None
    if firmware_setup:
        target_title = "UEFI Firmware / BIOS Setup"
    elif target_query:
        target_entry = mgr.find_entry(target_query, include_non_os=False)
        if not target_entry:
            print(f"Error: Boot target '{target_query}' not recognized.", file=sys.stderr)
            print("Run 'nboot list' to view available operating systems.", file=sys.stderr)
            sys.exit(1)
        target_title = target_entry.title
    else:
        target_entry, is_fw_default, configured_target = mgr.get_configured_default()
        if is_fw_default:
            firmware_setup = True
            target_title = "UEFI Firmware / BIOS Setup"
        elif target_entry:
            target_title = target_entry.title
        else:
            if configured_target:
                print(f"Error: Configured default target '{configured_target}' not found among active boot entries.", file=sys.stderr)
                print("Run 'nboot list' to inspect entries or 'nboot set-default <target>' to update your default.", file=sys.stderr)
            else:
                print("Error: No default boot target found.", file=sys.stderr)
                print("Please ensure your target operating system is registered or run 'nboot list'.", file=sys.stderr)
            sys.exit(1)

    if not skip_confirm:
        if sys.stdin.isatty():
            if not prompt_confirmation(target_title, is_firmware=firmware_setup):
                return
        elif not dry_run:
            print("Error: Non-interactive terminal detected. Pass -y / --now to confirm reboot.", file=sys.stderr)
            sys.exit(1)

    bootnext_armed = False
    if not firmware_setup and target_entry:
        print(f"Configuring one-time boot for: {target_entry.title} (Boot{target_entry.entry_id})...")
        success, message = set_bootnext(target_entry.entry_id, dry_run=dry_run)
        if not success:
            print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)
        print(message)
        bootnext_armed = True

    print(f"Initiating reboot into {target_title}...")
    success, message = execute_reboot(firmware_setup=firmware_setup, dry_run=dry_run)
    if not success:
        if bootnext_armed and not dry_run:
            cleared, clear_msg = clear_bootnext(dry_run=False)
            if cleared:
                print(f"Notice: {clear_msg}", file=sys.stderr)
            else:
                print(f"Warning: BootNext may still be armed ({clear_msg})", file=sys.stderr)
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)
    print(message)


def _launch_gui_safe():
    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY"):
        print("NextBoot GUI Error: No graphical display detected ($WAYLAND_DISPLAY or $DISPLAY is not set).", file=sys.stderr)
        print("Use CLI commands (e.g. 'nboot list' or 'nboot <target>').", file=sys.stderr)
        sys.exit(1)
    from nextboot_gui import launch_gui
    launch_gui()


def main():
    mgr = UEFIManager()

    args = sys.argv[1:]

    dry_run = False
    skip_confirm = False
    show_all = False
    show_help = False
    show_version = False
    want_gui = False
    filtered_args: list[str] = []

    for arg in args:
        if arg in ["-d", "--dry-run"]:
            dry_run = True
        elif arg in ["-y", "--yes", "--now"]:
            skip_confirm = True
        elif arg in ["-a", "--all"]:
            show_all = True
        elif arg in ["-h", "--help"]:
            show_help = True
        elif arg in ["-g", "--gui"]:
            want_gui = True
        elif arg in ["-V", "--version"]:
            show_version = True
        elif arg.startswith("-"):
            print(f"Error: Unknown option '{arg}'.", file=sys.stderr)
            print("Run 'nboot --help' for usage.", file=sys.stderr)
            sys.exit(1)
        else:
            filtered_args.append(arg)

    if show_help:
        print_help()
        return

    if show_version:
        print(f"NextBoot {__version__}")
        return

    if want_gui:
        _launch_gui_safe()
        return

    if not filtered_args:
        run_reboot_flow(mgr, target_query=None, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    sub = filtered_args[0].lower()

    if sub in ["h", "help"]:
        print_help()
        return

    if sub in ["l", "ls", "list"]:
        cmd_list(mgr, show_all=show_all)
        return

    if sub == "hidden":
        cmd_hidden(mgr)
        return

    if sub == "hide":
        if len(filtered_args) < 2:
            print("Error: Specify target entry to hide. Example: nboot hide 0013", file=sys.stderr)
            sys.exit(1)
        cmd_hide(mgr, filtered_args[1])
        return

    if sub in ["unhide", "restore"]:
        if len(filtered_args) < 2:
            print("Error: Specify target entry to unhide, or 'all'. Example: nboot unhide 0013", file=sys.stderr)
            sys.exit(1)
        cmd_unhide(mgr, filtered_args[1])
        return

    if sub in ["clear", "cancel"]:
        cmd_clear(dry_run=dry_run)
        return

    if sub in ["status", "info"]:
        cmd_status(mgr)
        return

    if sub in ["set", "set-default", "setdefault"]:
        if len(filtered_args) < 2:
            print("Error: Specify target OS to set as default. Example: nboot set-default win", file=sys.stderr)
            sys.exit(1)
        cmd_set_default(mgr, filtered_args[1])
        return

    if sub in ["g", "gui"]:
        _launch_gui_safe()
        return

    if sub in ["bios", "uefi", "firmware"]:
        run_reboot_flow(mgr, firmware_setup=True, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    if sub in ["default", "def"]:
        run_reboot_flow(mgr, target_query=None, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    # Check if sub matches any detected boot entry
    entry = mgr.find_entry(sub, include_non_os=False)
    if entry:
        run_reboot_flow(mgr, target_query=sub, skip_confirm=skip_confirm, dry_run=dry_run)
        return

    print(f"Unknown command or target: '{filtered_args[0]}'", file=sys.stderr)
    print("Run 'nboot list' to see available operating systems or 'nboot --help' for help.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
