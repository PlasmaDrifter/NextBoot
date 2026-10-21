#!/usr/bin/env python3
"""
nextboot_core.py - Core library for NextBoot (nboot)

Handles UEFI NVRAM inspection, boot entry classification with extensive sub-distro detection
(Nobara, CachyOS, EndeavourOS, Pop!_OS, Linux Mint, etc.), persistent configuration, and BootNext execution.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__version__ = "v0.7.3"

KNOWN_SUBDISTROS = {
    "cachy": ("CachyOS", "Based on Arch Linux", ["cachyos", "cachy", "arch"]),
    "cachyos": ("CachyOS", "Based on Arch Linux", ["cachyos", "cachy", "arch"]),
    "nobara": ("Nobara Linux", "Based on Fedora", ["nobara", "nob", "fedora", "fed"]),
    "endeavouros": ("EndeavourOS", "Based on Arch Linux", ["endeavouros", "eos", "arch"]),
    "garuda": ("Garuda Linux", "Based on Arch Linux", ["garuda", "arch"]),
    "manjaro": ("Manjaro Linux", "Based on Arch Linux", ["manjaro", "arch"]),
    "pop_os": ("Pop!_OS", "Based on Ubuntu", ["pop-os", "pop", "ubuntu"]),
    "pop-os": ("Pop!_OS", "Based on Ubuntu", ["pop-os", "pop", "ubuntu"]),
    "linuxmint": ("Linux Mint", "Based on Ubuntu", ["mint", "linuxmint", "ubuntu"]),
    "mint": ("Linux Mint", "Based on Ubuntu", ["mint", "linuxmint", "ubuntu"]),
    "bazzite": ("Bazzite", "Based on Fedora Atomic", ["bazzite", "fedora"]),
    "chimeraos": ("ChimeraOS", "Based on Arch Linux", ["chimeraos", "chimera", "arch"]),
    "omarchy": ("Omarchy", "Based on Arch Linux", ["omarchy", "arch"]),
}


def get_config_dir() -> Path:
    """Return the NextBoot configuration directory following XDG standards."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = Path(xdg_config)
    else:
        base = Path.home() / ".config"
    config_dir = base / "nextboot"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def load_config() -> dict:
    """Load configuration from config.json."""
    config_file = get_config_path()
    default_config = {
        "default_target": "windows",
        "one_click_reboot": False,
        "window_width": 580,
        "window_height": 585,
        "hidden_entries": [],
    }
    if not config_file.exists():
        return default_config
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_config.update(data)
            if "hidden_entries" in data and isinstance(data["hidden_entries"], list):
                default_config["hidden_entries"] = [str(x).strip() for x in data["hidden_entries"] if str(x).strip()]
            return default_config
    except Exception:
        return default_config


def save_config(config_data: dict) -> None:
    """Save configuration to config.json."""
    config_file = get_config_path()
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
    except Exception as err:
        sys.stderr.write(f"Warning: Failed to save config: {err}\n")


def is_entry_hidden(entry: Optional["BootEntry"], hidden_list: List[str], is_firmware: bool = False) -> bool:
    """Determine if a boot entry or virtual firmware option is marked as hidden."""
    if not hidden_list:
        return False

FIRMWARE_TARGETS = {
    "bios",
    "uefi",
    "firmware",
    "uefi_setup",
    "uefi-setup",
    "firmware_setup",
    "firmware-setup",
}


def is_entry_hidden(entry: Optional["BootEntry"], hidden_list: List[str], is_firmware: bool = False) -> bool:
    """Determine if a boot entry or virtual firmware option is marked as hidden."""
    if not hidden_list:
        return False

    hidden_normalized = [str(h).strip().lower() for h in hidden_list if str(h).strip()]

    if is_firmware or entry is None:
        return any(h in FIRMWARE_TARGETS for h in hidden_normalized)

    eid = entry.entry_id.lower()
    if eid in hidden_normalized or f"boot{eid}" in hidden_normalized:
        return True

    raw_lower = entry.raw_title.lower()
    title_lower = entry.title.lower()
    for h in hidden_normalized:
        if h == raw_lower or h == title_lower:
            return True

    for s in entry.slugs:
        if s.lower() in hidden_normalized:
            return True

    return False


def hide_entry(identifier: str, mgr: Optional["UEFIManager"] = None) -> Tuple[bool, str]:
    """Add an entry identifier (ID, slug, or title) to the hidden_entries list."""
    target = identifier.strip()
    if not target:
        return False, "No entry identifier provided."

    config = load_config()
    hidden = list(config.get("hidden_entries", []))

    if target.lower() in FIRMWARE_TARGETS:
        store_id = "uefi_setup"
        display_name = "UEFI Firmware Setup"
    else:
        if mgr is None:
            mgr = UEFIManager()
        matched_entry = mgr.find_entry(target)
        if matched_entry:
            if matched_entry.entry_id == mgr.boot_current:
                return False, f"Cannot hide '{matched_entry.title}' because it is the currently active booted OS."
            store_id = matched_entry.entry_id.upper()
            display_name = f"{matched_entry.title} (Boot{store_id})"
        else:
            norm_hex = target.upper().lstrip("BOOT")
            if re.match(r"^[0-9A-F]{4}$", norm_hex):
                store_id = norm_hex
                display_name = f"Boot{store_id}"
            else:
                return False, f"Could not find boot entry matching '{target}'."

    if store_id.upper() in [str(h).upper() for h in hidden]:
        return False, f"'{display_name}' is already hidden."

    hidden.append(store_id)
    config["hidden_entries"] = hidden
    save_config(config)
    return True, f"Hidden '{display_name}'."


def unhide_entry(identifier: str, mgr: Optional["UEFIManager"] = None) -> Tuple[bool, str]:
    """Remove an entry identifier from the hidden_entries list."""
    target = identifier.strip().lower()
    if not target:
        return False, "No entry identifier provided."

    config = load_config()
    hidden = list(config.get("hidden_entries", []))
    if not hidden:
        return False, "No entries are currently hidden."

    if target in ["all", "*"]:
        count = len(hidden)
        config["hidden_entries"] = []
        save_config(config)
        return True, f"Restored all {count} hidden entries."

    if mgr is None:
        mgr = UEFIManager()

    to_remove = []
    restored_names = []

    if target in FIRMWARE_TARGETS:
        for item in hidden:
            if str(item).strip().lower() in FIRMWARE_TARGETS:
                to_remove.append(item)
                restored_names.append("UEFI Firmware Setup")
    else:
        for item in hidden:
            item_str = str(item).strip()
            item_lower = item_str.lower()
            matched = False
            display_title = item_str

            entry = mgr.find_entry(item_str)
            if entry:
                display_title = f"{entry.title} (Boot{entry.entry_id})"
                if (target == entry.entry_id.lower() or 
                    target == f"boot{entry.entry_id.lower()}" or 
                    target in [s.lower() for s in entry.slugs] or 
                    target == entry.title.lower() or 
                    target == entry.raw_title.lower()):
                    matched = True
            elif target == item_lower or target == f"boot{item_lower}":
                matched = True

            if matched:
                to_remove.append(item)
                restored_names.append(display_title)

    if not to_remove:
        return False, f"No hidden entry matches '{identifier}'."

    new_hidden = [h for h in hidden if h not in to_remove]
    config["hidden_entries"] = new_hidden
    save_config(config)
    names_str = ", ".join(restored_names)
    return True, f"Restored: {names_str}"


def unhide_all_entries() -> Tuple[bool, str]:
    """Restore all hidden entries."""
    config = load_config()
    count = len(config.get("hidden_entries", []))
    config["hidden_entries"] = []
    save_config(config)
    return True, f"Restored {count} hidden entries."


def get_host_os_info() -> dict:
    """Inspect local system os-release to detect active sub-distro identity."""
    info = {"name": "Linux", "id": "linux", "id_like": "", "pretty_name": "Linux"}
    for p in [Path("/etc/os-release"), Path("/usr/lib/os-release")]:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        v = v.strip('"\'')
                        key = k.lower()
                        if key in ["name", "id", "id_like", "pretty_name"]:
                            info[key] = v
                break
            except Exception:
                pass
    return info


def detect_connected_usb_labels() -> Dict[str, str]:
    """
    Inspect block devices to find removable/USB drives with recognizable volume labels (e.g. Ventoy).
    Returns a dict mapping device model keywords to their detected label (e.g., {'flash drive fit': 'Ventoy'}).
    """
    labels = {}
    if not shutil.which("lsblk"):
        return labels

    try:
        out = subprocess.check_output(
            ["lsblk", "-J", "-o", "NAME,LABEL,MODEL,TRAN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        data = json.loads(out)
        for dev in data.get("blockdevices", []):
            model = (dev.get("model") or "").strip()
            tran = (dev.get("tran") or "").strip().lower()
            if not model:
                continue

            found_label = None
            for child in dev.get("children", []):
                clbl = (child.get("label") or "").strip()
                if clbl:
                    if clbl.lower() in ["ventoy", "vtoyefi"]:
                        found_label = "Ventoy"
                        break
                    elif not found_label:
                        found_label = clbl

            if found_label:
                labels[model.lower()] = found_label
    except Exception:
        pass

    return labels


class BootEntry:
    def __init__(
        self,
        entry_id: str,
        title: str,
        active: bool = True,
        extra: str = "",
        is_current: bool = False,
    ):
        self.entry_id = entry_id.upper()
        self.raw_title = title.strip()
        self.active = active
        self.extra = extra.strip()
        self.is_current = is_current

        self.os_type = self._classify()
        self.title, self.base_distro, self.extra_slugs = self._resolve_subdistro_details()
        self.slugs = self._generate_slugs()

    def is_os_entry(self) -> bool:
        """
        Determine if this boot entry represents an actual installed operating system,
        filtering out motherboard firmware setup utilities (e.g. Setup, Diagnostics, Splash Screen)
        and empty hardware device slots (e.g. NVMe0, ATA HDD0, USB CD, PXE Boot).
        """
        # The currently active booted OS is always kept
        if self.is_current:
            return True

        extra_lower = self.extra.lower()
        title_clean = self.raw_title.strip().lower()

        # 1. Motherboard firmware volume files (SPI ROM utilities) are not OSes
        if "fvfile(" in extra_lower:
            return False

        # 2. Known OEM firmware setup, test, and diagnostic tools
        firmware_tools = {
            "setup",
            "boot menu",
            "diagnostic splash screen",
            "lenovo diagnostics",
            "dell diagnostics",
            "startup interrupt menu",
            "rescue and recovery",
            "regulatory information",
            "bios setup",
            "system diagnostics",
            "device configuration",
        }
        if title_clean in firmware_tools or any(title_clean.startswith(ft) for ft in ["setup", "boot menu", "lenovo diagnostics"]):
            return False

        # 3. Raw hardware drive slots and network boot ports
        hardware_stubs = {
            "nvme0", "nvme1", "nvme2", "nvme3",
            "ata hdd0", "ata hdd1", "sata hdd0", "sata hdd1",
            "usb cd", "usb fdd", "usb hdd",
            "pxe boot", "network boot", "lan boot", "ip4 pxe", "ip6 pxe",
        }
        if title_clean in hardware_stubs:
            return False

        # 4. If it has a specific EFI loader executable or hard drive partition, it is an OS
        if ".efi" in extra_lower or "hd(" in extra_lower or "file(" in extra_lower:
            return True

        # 5. Classified OS distributions
        if self.os_type in ["windows", "fedora", "cachyos", "debian_ubuntu", "arch", "linux"]:
            return True

        # 6. Detected removable media with recognized label (e.g. Ventoy)
        if self.os_type == "usb" and (self.title != self.raw_title or ".efi" in extra_lower):
            return True

        return False

    def _classify(self) -> str:
        text = f"{self.raw_title} {self.extra}".lower()
        if "windows" in text or "bootmgfw.efi" in text or "microsoft" in text:
            return "windows"
        if "cachy" in text:
            return "cachyos"
        if "fedora" in text or "nobara" in text or "redhat" in text:
            return "fedora"
        if "ubuntu" in text or "debian" in text or "mint" in text:
            return "debian_ubuntu"
        if "arch" in text or "manjaro" in text or "endeavouros" in text or "omarchy" in text:
            return "arch"
        if "linux" in text or "shim" in text or "grub" in text or "limine" in text or "systemd-boot" in text:
            return "linux"
        if "usb" in text or "flash drive" in text or "removable" in text:
            return "usb"
        if "setup" in text or "firmware" in text or "bios" in text:
            return "firmware"
        return "other"

    def _resolve_subdistro_details(self) -> Tuple[str, Optional[str], List[str]]:
        """
        Detect sub-distros (e.g., Nobara on Fedora base, CachyOS on Arch base).
        """
        # 1. If this is the active booted operating system, check host os-release directly
        if self.is_current:
            host = get_host_os_info()
            host_name = host.get("name", "")
            host_id = host.get("id", "").lower()

            if host_id in KNOWN_SUBDISTROS:
                formal_name, base_note, slugs = KNOWN_SUBDISTROS[host_id]
                return formal_name, base_note, slugs
            elif host_name and host_name.lower() != self.raw_title.lower():
                base_note = f"Based on {self.raw_title}" if self.raw_title else None
                return host_name, base_note, [host_id] if host_id else []

        # 2. Check if this entry is a removable/USB drive with a detected label (e.g. Ventoy)
        if self.os_type == "usb":
            usb_labels = detect_connected_usb_labels()
            raw_lower = self.raw_title.lower()
            for model_kw, label in usb_labels.items():
                if model_kw in raw_lower:
                    if label.lower() == "ventoy":
                        # Friendly formatted hardware model
                        dev_name = "Samsung Flash Drive" if "samsung" in raw_lower else "USB Drive"
                        return f"Ventoy ({dev_name})", "Multiboot USB", ["ventoy", "vtoy", "usb"]
                    else:
                        return f"{label} (USB)", "Removable Media", [label.lower(), "usb"]

        # 3. Check if another non-current entry matches a known sub-distro by name or EFI path
        text = f"{self.raw_title} {self.extra}".lower()
        for key, (formal_name, base_note, slugs) in KNOWN_SUBDISTROS.items():
            if key in text:
                return formal_name, base_note, slugs

        return self.raw_title, None, []

    def _generate_slugs(self) -> List[str]:
        slugs = list(self.extra_slugs)

        if self.os_type == "windows":
            for s in ["windows", "win", "w"]:
                if s not in slugs:
                    slugs.append(s)
        elif self.os_type == "fedora":
            for s in ["fedora", "fed", "f"]:
                if s not in slugs:
                    slugs.append(s)
        elif self.os_type == "cachyos":
            for s in ["cachyos", "cachy", "arch"]:
                if s not in slugs:
                    slugs.append(s)
        elif self.os_type == "arch":
            for s in ["arch", "manjaro"]:
                if s not in slugs:
                    slugs.append(s)
        elif self.os_type == "debian_ubuntu":
            for s in ["ubuntu", "debian", "mint"]:
                if s not in slugs:
                    slugs.append(s)
        elif self.os_type == "usb":
            for s in ["usb", "ventoy", "flash"]:
                if s not in slugs:
                    slugs.append(s)

        clean_title = re.sub(r"[^a-zA-Z0-9]+", "-", self.title.lower()).strip("-")
        if clean_title and clean_title not in slugs:
            slugs.append(clean_title)

        clean_raw = re.sub(r"[^a-zA-Z0-9]+", "-", self.raw_title.lower()).strip("-")
        if clean_raw and clean_raw not in slugs:
            slugs.append(clean_raw)

        slugs.append(self.entry_id.lower())
        slugs.append(f"boot{self.entry_id.lower()}")
        return slugs

    def matches(self, query: str) -> bool:
        q = query.strip().lower().lstrip("-")
        if q == self.entry_id.lower() or q == f"boot{self.entry_id.lower()}":
            return True
        if q in self.slugs:
            return True
        if q in self.title.lower() or q in self.raw_title.lower():
            return True
        return False


class UEFIManager:
    def __init__(self):
        self.boot_current: Optional[str] = None
        self.boot_next: Optional[str] = None
        self.boot_order: List[str] = []
        self.all_entries: List[BootEntry] = []
        self.entries: List[BootEntry] = []
        self.refresh()

    def refresh(self) -> None:
        self.boot_current = None
        self.boot_next = None
        self.boot_order = []
        self.all_entries = []
        self.entries = []

        if not shutil.which("efibootmgr"):
            return

        try:
            output = subprocess.check_output(["efibootmgr"], text=True, stderr=subprocess.DEVNULL)
        except Exception:
            return

        lines = output.splitlines()
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("BootCurrent:"):
                self.boot_current = line_str.split(":", 1)[1].strip().upper()
            elif line_str.startswith("BootNext:"):
                self.boot_next = line_str.split(":", 1)[1].strip().upper()
            elif line_str.startswith("BootOrder:"):
                order_part = line_str.split(":", 1)[1].strip()
                self.boot_order = [x.strip().upper() for x in order_part.split(",") if x.strip()]

        for line in lines:
            m = re.match(r"^Boot([0-9A-Fa-f]{4})(\*?)\s+(.*?)(?:\t(.*))?$", line)
            if m:
                entry_id, active_flag, title, extra = m.groups()
                is_curr = (self.boot_current == entry_id.upper())
                entry = BootEntry(
                    entry_id=entry_id,
                    title=title or "Unknown Entry",
                    active=(active_flag == "*"),
                    extra=extra or "",
                    is_current=is_curr,
                )
                self.all_entries.append(entry)
                if entry.is_os_entry():
                    self.entries.append(entry)

    def find_entry(self, query: str) -> Optional[BootEntry]:
        """Find the best matching boot entry by ID, slug, or title."""
        q = query.strip().lower().lstrip("-")
        for e in self.entries:
            if e.entry_id.lower() == q or f"boot{e.entry_id.lower()}" == q:
                return e
        for e in self.entries:
            if q in e.slugs:
                return e
        for e in self.entries:
            if q in e.title.lower() or q in e.raw_title.lower():
                return e

        for e in self.all_entries:
            if e.entry_id.lower() == q or f"boot{e.entry_id.lower()}" == q:
                return e
        for e in self.all_entries:
            if q in e.slugs or q in e.title.lower() or q in e.raw_title.lower():
                return e
        return None

    def get_default_entry(self) -> Optional[BootEntry]:
        """Retrieve the actual default boot entry from UEFI BootOrder."""
        if self.boot_order:
            first_id = self.boot_order[0]
            for e in self.entries:
                if e.entry_id == first_id:
                    return e

        return self.entries[0] if self.entries else None

    def get_hidden_entries(self) -> List[Tuple[Optional[BootEntry], bool]]:
        """
        Return list of tuples (entry, is_firmware) that are currently hidden.
        """
        config = load_config()
        hidden_list = config.get("hidden_entries", [])
        if not hidden_list:
            return []

        results: List[Tuple[Optional[BootEntry], bool]] = []
        for entry in self.entries:
            if is_entry_hidden(entry, hidden_list, is_firmware=False):
                results.append((entry, False))

        if is_entry_hidden(None, hidden_list, is_firmware=True):
            results.append((None, True))

        return results


def set_bootnext(entry_id: str, dry_run: bool = False) -> Tuple[bool, str]:
    """Execute BootNext command via the privileged helper."""
    norm_id = entry_id.strip().upper()
    if not re.match(r"^[0-9A-F]{4}$", norm_id):
        return False, f"Invalid boot entry format: {entry_id}"

    if dry_run:
        return True, f"[DRY-RUN] Would set UEFI BootNext to Boot{norm_id}"

    helper_path = shutil.which("nextboot-helper")
    if not helper_path:
        for candidate in ["/usr/local/libexec/nextboot-helper", "/usr/libexec/nextboot-helper"]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                helper_path = candidate
                break

    if not helper_path:
        local_candidate = Path(__file__).parent / "nextboot-helper.sh"
        if local_candidate.exists():
            helper_path = str(local_candidate)

    if not helper_path:
        return False, "nextboot-helper binary not found. Please run the installer."

    cmd = ["sudo", helper_path, norm_id]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True, proc.stdout.strip()
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip() or f"Helper exited with code {e.returncode}"
        return False, f"Failed to set BootNext: {err_msg}"
    except Exception as e:
        return False, f"Execution error: {e}"


def execute_reboot(firmware_setup: bool = False, dry_run: bool = False) -> Tuple[bool, str]:
    """Trigger system reboot."""
    if dry_run:
        if firmware_setup:
            return True, "[DRY-RUN] Would execute: systemctl reboot --firmware-setup"
        return True, "[DRY-RUN] Would execute: systemctl reboot"

    cmd = ["systemctl", "reboot"]
    if firmware_setup:
        cmd.append("--firmware-setup")

    try:
        subprocess.run(cmd, check=True)
        return True, "Reboot initiated."
    except Exception as e:
        return False, f"Failed to trigger reboot: {e}"


def simplify_os_name(title: str) -> str:
    """
    Simplify OS title for desktop shortcut naming:
    'Windows Boot Manager' -> 'Windows'
    'Nobara Linux' -> 'Nobara'
    'Debian GNU/Linux' -> 'Debian'
    'Fedora Linux' -> 'Fedora'
    'Linux Mint' -> 'Mint'
    'Ventoy (Samsung Flash Drive)' -> 'Ventoy'
    'UEFI Firmware Setup' -> 'UEFI Firmware'
    """
    t = title.strip()
    if re.search(r"\bwindows\b", t, re.IGNORECASE):
        return "Windows"
    if re.search(r"\bventoy\b", t, re.IGNORECASE):
        return "Ventoy"
    if re.search(r"\b(uefi|bios|firmware)\b", t, re.IGNORECASE):
        return "UEFI Firmware"

    # Strip parenthesized hardware/device info if present
    t = re.sub(r"\s*\(.*?\)$", "", t).strip()

    # Strip common suffixes/prefixes if they don't consume the entire title
    sub = re.sub(r"\s+GNU/Linux$", "", t, flags=re.IGNORECASE)
    sub = re.sub(r"\s+Linux$", "", sub, flags=re.IGNORECASE)
    sub = re.sub(r"^Linux\s+", "", sub, flags=re.IGNORECASE)
    sub = re.sub(r"\s+Boot\s+Manager$", "", sub, flags=re.IGNORECASE).strip()

    if sub:
        return sub
    return t if t else title


def create_os_shortcut(
    title: str,
    slug: str,
    icon_path: Optional[str] = None,
    target: str = "desktop",
) -> Tuple[bool, str]:
    """
    Generate an executable .desktop shortcut for rebooting into a specific OS.
    target: 'desktop' (saves to ~/Desktop) or 'applications' (saves to ~/.local/share/applications)
    """
    home = Path.home()
    os_name = simplify_os_name(title)
    shortcut_name = f"Reboot into {os_name}"

    if target == "desktop":
        target_dir = home / "Desktop"
        target_dir.mkdir(parents=True, exist_ok=True)
        clean_name = re.sub(r"[^\w\s-]", "", os_name).strip()
        desktop_file = target_dir / f"Reboot into {clean_name}.desktop"
    elif target == "applications":
        target_dir = home / ".local" / "share" / "applications"
        target_dir.mkdir(parents=True, exist_ok=True)
        clean_slug = re.sub(r"[^\w-]", "", slug).strip()
        desktop_file = target_dir / f"nextboot-reboot-{clean_slug}.desktop"
    else:
        return False, f"Unknown target location: {target}"

    icon_str = icon_path if (icon_path and Path(icon_path).exists()) else "nextboot"

    content = f"""[Desktop Entry]
Type=Application
Name={shortcut_name}
GenericName=One-Time OS Reboot
Comment=Reboot directly into {os_name} via NextBoot
Exec=nboot {slug} -y
Icon={icon_str}
Terminal=false
Categories=Utility;
StartupNotify=true
"""

    try:
        desktop_file.write_text(content, encoding="utf-8")
        desktop_file.chmod(0o755)

        if target == "applications":
            menu_file = home / ".config" / "menus" / "applications-kmenuedit.menu"
            if menu_file.exists():
                try:
                    menu_text = menu_file.read_text(encoding="utf-8")
                    pattern = rf"^\s*<Filename>{re.escape(desktop_file.name)}</Filename>\s*\n"
                    new_text = re.sub(pattern, "", menu_text, flags=re.MULTILINE)
                    if new_text != menu_text:
                        menu_file.write_text(new_text, encoding="utf-8")
                except Exception:
                    pass

            if shutil.which("update-desktop-database"):
                try:
                    subprocess.run(
                        ["update-desktop-database", str(target_dir)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                except Exception:
                    pass

            for sycoca in ("kbuildsycoca6", "kbuildsycoca5"):
                if shutil.which(sycoca):
                    try:
                        subprocess.run(
                            [sycoca, "--noincremental"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                        )
                    except Exception:
                        pass

        return True, str(desktop_file)
    except Exception as e:
        return False, f"Failed to create shortcut: {e}"


def detect_desktop_environment() -> str:
    """
    Detect the active Desktop Environment (e.g. 'gnome', 'kde', 'xfce', 'cinnamon', 'mate', 'cosmic', 'other').
    """
    curr = (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        or os.environ.get("DESKTOP_SESSION", "")
        or os.environ.get("XDG_SESSION_DESKTOP", "")
    ).lower()

    if "gnome" in curr:
        return "gnome"
    if "kde" in curr or "plasma" in curr:
        return "kde"
    if "cinnamon" in curr:
        return "cinnamon"
    if "xfce" in curr:
        return "xfce"
    if "mate" in curr:
        return "mate"
    if "cosmic" in curr:
        return "cosmic"
    if "hyprland" in curr or "hypr" in curr:
        return "hyprland"
    if "sway" in curr:
        return "sway"
    return "other"


