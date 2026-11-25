#!/usr/bin/env python3
"""
nextboot_core.py - Core library for NextBoot (nboot)

Handles UEFI NVRAM inspection, boot entry classification with extensive sub-distro detection
(Nobara, CachyOS, EndeavourOS, Pop!_OS, Linux Mint, etc.), persistent configuration, and BootNext execution.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

__version__ = "v0.7.7"

KNOWN_SUBDISTROS = {
    "cachy": ("CachyOS", "Based on Arch Linux", ["cachyos", "cachy", "arch"]),
    "cachyos": ("CachyOS", "Based on Arch Linux", ["cachyos", "cachy", "arch"]),
    "nobara": ("Nobara Linux", "Based on Fedora", ["nobara", "nob", "fedora", "fed"]),
    "endeavouros": ("EndeavourOS", "Based on Arch Linux", ["endeavouros", "eos", "arch"]),
    "garuda": ("Garuda Linux", "Based on Arch Linux", ["garuda", "arch"]),
    "manjaro": ("Manjaro Linux", "Based on Arch Linux", ["manjaro", "arch"]),
    "pop_os": ("Pop!_OS", "Based on Ubuntu", ["pop-os", "pop", "ubuntu"]),
    "pop-os": ("Pop!_OS", "Based on Ubuntu", ["pop-os", "pop", "ubuntu"]),
    "pop!_os": ("Pop!_OS", "Based on Ubuntu", ["pop-os", "pop", "ubuntu"]),
    "linuxmint": ("Linux Mint", "Based on Ubuntu", ["mint", "linuxmint", "ubuntu"]),
    "mint": ("Linux Mint", "Based on Ubuntu", ["mint", "linuxmint", "ubuntu"]),
    "bazzite": ("Bazzite", "Based on Fedora Atomic", ["bazzite", "fedora"]),
    "chimeraos": ("ChimeraOS", "Based on Arch Linux", ["chimeraos", "chimera", "arch"]),
    "omarchy": ("Omarchy", "Based on Arch Linux", ["omarchy", "arch"]),
    "almalinux": ("AlmaLinux", "Enterprise Linux", ["almalinux", "alma", "rhel"]),
    "alma": ("AlmaLinux", "Enterprise Linux", ["almalinux", "alma", "rhel"]),
    "rocky": ("Rocky Linux", "Enterprise Linux", ["rocky", "rockylinux", "rhel"]),
    "rockylinux": ("Rocky Linux", "Enterprise Linux", ["rocky", "rockylinux", "rhel"]),
    "tails": ("Tails", "Based on Debian", ["tails", "debian"]),
    "biglinux": ("BigLinux", "Based on Manjaro / Arch", ["biglinux", "manjaro", "arch"]),
    "archcraft": ("Archcraft", "Based on Arch Linux", ["archcraft", "arch"]),
    "archbang": ("ArchBang", "Based on Arch Linux", ["archbang", "arch"]),
    "blackarch": ("BlackArch", "Based on Arch Linux", ["blackarch", "arch"]),
    "arcolinux": ("ArcoLinux", "Based on Arch Linux", ["arcolinux", "arco", "arch"]),
    "rebornos": ("RebornOS", "Based on Arch Linux", ["rebornos", "arch"]),
    "ghostbsd": ("GhostBSD", "Based on FreeBSD", ["ghostbsd", "freebsd"]),
    "bunsenlabs": ("BunsenLabs", "Based on Debian", ["bunsenlabs", "debian"]),
    "ultramarine": ("Ultramarine Linux", "Based on Fedora", ["ultramarine", "fedora"]),
    "pikaos": ("PikaOS", "Based on Ubuntu / Debian", ["pikaos", "pika", "ubuntu"]),
    "fydeos": ("FydeOS", "Based on ChromiumOS", ["fydeos", "chromeos"]),
    "zimaos": ("ZimaOS", "Personal Cloud OS", ["zimaos", "zima"]),
    "umbrelos": ("umbrelOS", "Home Server OS", ["umbrelos", "umbrel"]),
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


def _default_config() -> dict[str, Any]:
    return {
        "default_target": "windows",
        "one_click_reboot": False,
        "window_width": 580,
        "window_height": 585,
        "hidden_entries": [],
    }


def _normalize_config(data: object) -> dict[str, Any]:
    """Normalize loaded configuration to supported schema keys and valid types."""
    cfg = _default_config()
    if not isinstance(data, dict):
        return cfg

    if "default_target" in data and data["default_target"] is not None:
        cfg["default_target"] = str(data["default_target"]).strip()
    if "one_click_reboot" in data:
        cfg["one_click_reboot"] = bool(data["one_click_reboot"])
    for dim_key, min_val, default_val in (("window_width", 480, 580), ("window_height", 360, 585)):
        if dim_key in data:
            try:
                cfg[dim_key] = max(min_val, int(data[dim_key]))
            except (TypeError, ValueError):
                cfg[dim_key] = default_val
    if "hidden_entries" in data and isinstance(data["hidden_entries"], list):
        cfg["hidden_entries"] = [str(x).strip() for x in data["hidden_entries"] if str(x).strip()]
    return cfg


def load_config() -> dict[str, Any]:
    """Load configuration from config.json."""
    config_file = get_config_path()
    if not config_file.exists():
        return _default_config()
    try:
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_config(data)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return _default_config()


def save_config(config_data: dict[str, Any]) -> None:
    """Save configuration atomically to config.json."""
    config_file = get_config_path()
    normalized = _normalize_config(config_data)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_file.parent,
            prefix=".config.",
            suffix=".tmp",
            delete=False,
        ) as tf:
            tmp_path = tf.name
            json.dump(normalized, tf, indent=2)
            tf.write("\n")
        os.replace(tmp_path, config_file)
    except (OSError, TypeError, ValueError) as err:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        sys.stderr.write(f"Warning: Failed to save config: {err}\n")


def update_config(updates: dict[str, Any]) -> dict[str, Any]:
    """Perform a fresh read-modify-write update on config.json."""
    cfg = load_config()
    cfg.update(updates)
    normalized = _normalize_config(cfg)
    save_config(normalized)
    return normalized


FIRMWARE_TARGETS = {
    "bios",
    "uefi",
    "firmware",
    "uefi_setup",
    "uefi-setup",
    "firmware_setup",
    "firmware-setup",
}


def is_entry_hidden(entry: BootEntry | None, hidden_list: list[str], is_firmware: bool = False) -> bool:
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

    return any(s.lower() in hidden_normalized for s in entry.slugs)


def _strip_boot_prefix(value: str) -> str:
    """Remove a leading 'BOOT' prefix case-insensitively without stripping hex B characters."""
    upper = value.strip().upper()
    return upper[4:] if upper.startswith("BOOT") else upper  # noqa: FURB188


def hide_entry(identifier: str, mgr: UEFIManager | None = None) -> tuple[bool, str]:
    """Add an entry identifier (ID, slug, or title) to the hidden_entries list."""
    target = identifier.strip()
    if not target:
        return False, "No entry identifier provided."

    config = load_config()
    hidden_raw = config.get("hidden_entries", [])
    hidden = list(hidden_raw) if isinstance(hidden_raw, list) else []

    if target.lower() in FIRMWARE_TARGETS:
        store_id = "uefi_setup"
        display_name = "UEFI Firmware Setup"
    else:
        if mgr is None:
            mgr = UEFIManager()
        matched_entry = mgr.find_entry(target, include_non_os=True)
        if matched_entry:
            if matched_entry.entry_id == mgr.boot_current:
                return False, f"Cannot hide '{matched_entry.title}' because it is the currently active booted OS."
            store_id = matched_entry.entry_id.upper()
            display_name = f"{matched_entry.title} (Boot{store_id})"
        else:
            norm_hex = _strip_boot_prefix(target)
            if re.match(r"^[0-9A-F]{4}$", norm_hex):
                if norm_hex == mgr.boot_current:
                    return False, f"Cannot hide Boot{norm_hex} because it is the currently active booted OS."
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


def unhide_entry(identifier: str, mgr: UEFIManager | None = None) -> tuple[bool, str]:
    """Remove an entry identifier from the hidden_entries list."""
    target = identifier.strip().lower()
    if not target:
        return False, "No entry identifier provided."

    config = load_config()
    hidden_raw = config.get("hidden_entries", [])
    hidden = list(hidden_raw) if isinstance(hidden_raw, list) else []
    if not hidden:
        return False, "No entries are currently hidden."

    if target in ["all", "*"]:
        count = len(hidden)
        config["hidden_entries"] = []
        save_config(config)
        return True, f"Restored all {count} hidden entries."

    if mgr is None:
        mgr = UEFIManager()

    to_remove: list[str] = []
    restored_names: list[str] = []

    if target in FIRMWARE_TARGETS:
        for item in hidden:
            if str(item).strip().lower() in FIRMWARE_TARGETS:
                to_remove.append(str(item))
                restored_names.append("UEFI Firmware Setup")
    else:
        for item in hidden:
            item_str = str(item).strip()
            item_lower = item_str.lower()
            matched = False
            display_title = item_str

            entry = mgr.find_entry(item_str, include_non_os=True)
            if entry:
                display_title = f"{entry.title} (Boot{entry.entry_id})"
                if (
                    target == entry.entry_id.lower()
                    or target == f"boot{entry.entry_id.lower()}"
                    or target in [s.lower() for s in entry.slugs]
                    or target == entry.title.lower()
                    or target == entry.raw_title.lower()
                    or target == item_lower
                ):
                    matched = True
            elif target == item_lower or target == f"boot{item_lower}" or _strip_boot_prefix(target) == _strip_boot_prefix(item_str):
                matched = True

            if matched:
                to_remove.append(str(item))
                restored_names.append(display_title)

    if not to_remove:
        return False, f"No hidden entry matches '{identifier}'."

    remove_set = {x.strip().lower() for x in to_remove}
    new_hidden = [h for h in hidden if str(h).strip().lower() not in remove_set]
    config["hidden_entries"] = new_hidden
    save_config(config)
    names_str = ", ".join(dict.fromkeys(restored_names))
    return True, f"Restored: {names_str}"


def unhide_all_entries() -> tuple[bool, str]:
    """Restore all hidden entries."""
    config = load_config()
    hidden_raw = config.get("hidden_entries", [])
    count = len(hidden_raw) if isinstance(hidden_raw, list) else 0
    config["hidden_entries"] = []
    save_config(config)
    return True, f"Restored {count} hidden entries."


def get_host_os_info() -> dict[str, str]:
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
            except OSError:
                pass
    return info


def detect_connected_usb_labels() -> dict[str, str]:
    """
    Inspect block devices to find USB drives with recognizable volume labels (e.g. Ventoy).
    Returns a dict mapping device model keywords to their detected label (e.g., {'flash drive fit': 'Ventoy'}).
    """
    labels: dict[str, str] = {}
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
            if not model or tran != "usb":
                continue

            found_label = None
            for child in dev.get("children", []):
                clbl = (child.get("label") or "").strip()
                if clbl:
                    if clbl.lower() in ["ventoy", "vtoyefi"]:
                        found_label = "Ventoy"
                        break
                    if not found_label:
                        found_label = clbl

            if not found_label:
                top_lbl = (dev.get("label") or "").strip()
                if top_lbl:
                    found_label = "Ventoy" if top_lbl.lower() in ["ventoy", "vtoyefi"] else top_lbl

            if found_label:
                labels[model.lower()] = found_label
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        pass

    return labels


def _contains_keyword(text: str, keyword: str) -> bool:
    """Check if keyword appears in text on non-alphanumeric token boundaries."""
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(keyword) + r"(?![a-z0-9])", text))


class BootEntry:
    def __init__(
        self,
        entry_id: str,
        title: str,
        active: bool = True,
        extra: str = "",
        is_current: bool = False,
        usb_labels: dict[str, str] | None = None,
        hidden_identifier: str | None = None,
    ):
        self.entry_id = entry_id.upper()
        self.raw_title = title.strip()
        self.active = active
        self.extra = extra.strip()
        self.is_current = is_current
        self._usb_labels = usb_labels
        self.hidden_identifier = hidden_identifier or self.entry_id

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
        return bool(self.os_type == "usb" and (self.title != self.raw_title or ".efi" in extra_lower))

    def _classify(self) -> str:
        text = f"{self.raw_title} {self.extra}".lower()
        if any(_contains_keyword(text, kw) for kw in ("windows", "bootmgfw", "microsoft")):
            return "windows"
        if _contains_keyword(text, "cachy") or _contains_keyword(text, "cachyos"):
            return "cachyos"
        if any(_contains_keyword(text, kw) for kw in ("fedora", "nobara", "redhat")):
            return "fedora"
        if any(_contains_keyword(text, kw) for kw in ("ubuntu", "debian", "mint", "linuxmint", "pop_os", "pop-os", "pop!_os")):
            return "debian_ubuntu"
        if any(_contains_keyword(text, kw) for kw in ("arch", "manjaro", "endeavouros", "omarchy", "garuda", "blackarch", "archcraft", "archbang", "arcolinux", "rebornos", "chimeraos")):
            return "arch"
        if any(_contains_keyword(text, kw) for kw in ("linux", "shim", "grub", "limine", "systemd-boot")):
            return "linux"
        if any(_contains_keyword(text, kw) for kw in ("usb", "flash drive", "removable")):
            return "usb"
        if any(_contains_keyword(text, kw) for kw in ("setup", "firmware", "bios")):
            return "firmware"
        return "other"

    def _resolve_subdistro_details(self) -> tuple[str, str | None, list[str]]:
        """
        Detect sub-distros (e.g., Nobara on Fedora base, CachyOS on Arch base).
        """
        # 1. If this is the active booted operating system, check host os-release directly
        if self.is_current:
            host = get_host_os_info()
            host_name = host.get("name", "")
            host_id = host.get("id", "").lower()

            if host_id in KNOWN_SUBDISTROS:
                formal_name, sub_note, slugs = KNOWN_SUBDISTROS[host_id]
                return formal_name, sub_note, slugs
            if host_name and host_name.lower() != self.raw_title.lower():
                raw_lower = self.raw_title.lower()
                if (host_id and _contains_keyword(raw_lower, host_id)) or raw_lower in host_name.lower():
                    base_note: str | None = None
                else:
                    base_note = f"Based on {self.raw_title}" if self.raw_title else None
                return host_name, base_note, [host_id] if host_id else []

        # 2. Check if this entry is a removable/USB drive with a detected label (e.g. Ventoy)
        if self.os_type == "usb":
            usb_labels = self._usb_labels if self._usb_labels is not None else detect_connected_usb_labels()
            raw_lower = self.raw_title.lower()
            for model_kw, label in usb_labels.items():
                if model_kw in raw_lower:
                    if label.lower() == "ventoy":
                        dev_name = "Samsung Flash Drive" if "samsung" in raw_lower else "USB Drive"
                        return f"Ventoy ({dev_name})", "Multiboot USB", ["ventoy", "vtoy", "usb"]
                    return f"{label} (USB)", "Removable Media", [label.lower(), "usb"]

        # 3. Check if another non-current entry matches a known sub-distro by name or EFI path
        text = f"{self.raw_title} {self.extra}".lower()
        for key, (formal_name, base_note, slugs) in KNOWN_SUBDISTROS.items():
            if _contains_keyword(text, key):
                return formal_name, base_note, slugs

        return self.raw_title, None, []

    def _generate_slugs(self) -> list[str]:
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
            for s in ["arch"]:
                if s not in slugs:
                    slugs.append(s)
        elif self.os_type == "debian_ubuntu":
            text = f"{self.raw_title} {self.extra}".lower()
            if "ubuntu" in text:
                for s in ["ubuntu", "deb"]:
                    if s not in slugs:
                        slugs.append(s)
            elif "debian" in text:
                for s in ["debian", "deb"]:
                    if s not in slugs:
                        slugs.append(s)
            elif "mint" in text:
                for s in ["mint", "linuxmint"]:
                    if s not in slugs:
                        slugs.append(s)
            else:
                for s in ["debian", "deb"]:
                    if s not in slugs:
                        slugs.append(s)
        elif self.os_type == "usb":
            usb_slugs = ["usb", "flash"]
            if "ventoy" in f"{self.title} {self.raw_title}".lower() and "ventoy" not in slugs:
                usb_slugs.insert(0, "ventoy")
            for s in usb_slugs:
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

    def get_short_slugs(self) -> list[str]:
        """Return clean, user-friendly shorthand CLI slugs and aliases."""
        short_slugs: list[str] = []
        for s in self.slugs:
            s_clean = s.strip().lower()
            if s_clean in (self.entry_id.lower(), f"boot{self.entry_id.lower()}"):
                continue
            if len(s_clean) > 20 or s_clean.startswith("uefi-") or "-partition-" in s_clean:
                continue
            if "-" in s_clean and len(s_clean) > 10:
                continue
            if s_clean not in short_slugs:
                short_slugs.append(s_clean)
        if not short_slugs:
            short_slugs = [self.slugs[0] if self.slugs else self.entry_id.lower()]
        return short_slugs

    def matches(self, query: str) -> bool:
        q = query.strip().lower()
        if not q:
            return False
        if q == self.entry_id.lower() or q == f"boot{self.entry_id.lower()}":
            return True
        if q in self.slugs:
            return True
        if len(q) >= 2:
            return q in self.title.lower() or q in self.raw_title.lower()
        return False


class UEFIManager:
    def __init__(self):
        self.boot_current: str | None = None
        self.boot_next: str | None = None
        self.boot_order: list[str] = []
        self.all_entries: list[BootEntry] = []
        self.entries: list[BootEntry] = []
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
        except (OSError, subprocess.SubprocessError):
            return

        usb_labels = detect_connected_usb_labels()
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
                    usb_labels=usb_labels,
                )
                self.all_entries.append(entry)
                if entry.is_os_entry():
                    self.entries.append(entry)

    def _find_in_list(self, entries: list[BootEntry], q: str) -> BootEntry | None:
        for e in entries:
            if e.entry_id.lower() == q or f"boot{e.entry_id.lower()}" == q:
                return e
        for e in entries:
            if q in e.slugs:
                return e
        if len(q) >= 2:
            for e in entries:
                if q in e.title.lower() or q in e.raw_title.lower():
                    return e
        return None

    def find_entry(self, query: str, include_non_os: bool = False) -> BootEntry | None:
        """Find the best matching boot entry by ID, slug, or title."""
        q = query.strip().lower()
        if not q:
            return None

        match = self._find_in_list(self.entries, q)
        if match:
            return match

        is_hex_id = bool(re.match(r"^(?:boot)?[0-9a-f]{4}$", q))
        if include_non_os or is_hex_id:
            return self._find_in_list(self.all_entries, q)

        return None

    def get_firmware_default_entry(self) -> BootEntry | None:
        """Retrieve the UEFI BootOrder default entry."""
        if self.boot_order:
            first_id = self.boot_order[0]
            for e in self.entries:
                if e.entry_id == first_id:
                    return e
        return self.entries[0] if self.entries else None

    def get_configured_default(self) -> tuple[BootEntry | None, bool, str]:
        """
        Resolve the configured NextBoot default target from config.json.
        Returns (entry, is_firmware, configured_target_str).
        """
        config = load_config()
        target = str(config.get("default_target", "")).strip()
        if not target:
            return self.get_firmware_default_entry(), False, ""
        if target.lower() in FIRMWARE_TARGETS:
            return None, True, target
        return self.find_entry(target, include_non_os=False), False, target

    def get_default_entry(self) -> BootEntry | None:
        """Retrieve the system's UEFI BootOrder default OS entry."""
        return self.get_firmware_default_entry()

    def get_hidden_entries(self) -> list[tuple[BootEntry | None, bool]]:
        """
        Return list of tuples (entry, is_firmware) for all entries in config hidden_entries,
        including non-OS entries and currently disconnected/unavailable boot entries.
        """
        config = load_config()
        hidden_raw = config.get("hidden_entries", [])
        hidden_list = list(hidden_raw) if isinstance(hidden_raw, list) else []
        if not hidden_list:
            return []

        results: list[tuple[BootEntry | None, bool]] = []
        seen_ids: set[str] = set()
        seen_firmware = False

        for raw_item in hidden_list:
            item_str = str(raw_item).strip()
            if not item_str:
                continue
            item_lower = item_str.lower()

            if item_lower in FIRMWARE_TARGETS:
                if not seen_firmware:
                    results.append((None, True))
                    seen_firmware = True
                continue

            matched = self.find_entry(item_str, include_non_os=True)
            if matched:
                if matched.entry_id not in seen_ids:
                    results.append((matched, False))
                    seen_ids.add(matched.entry_id)
                continue

            norm_hex = _strip_boot_prefix(item_str)
            if re.match(r"^[0-9A-F]{4}$", norm_hex):
                key = f"ID:{norm_hex}"
                if key not in seen_ids:
                    placeholder = BootEntry(
                        entry_id=norm_hex,
                        title=f"Unavailable Entry (Boot{norm_hex})",
                        active=False,
                        hidden_identifier=item_str,
                    )
                    results.append((placeholder, False))
                    seen_ids.add(key)
            else:
                key = f"STR:{item_lower}"
                if key not in seen_ids:
                    placeholder = BootEntry(
                        entry_id="----",
                        title=f"Unavailable Entry ({item_str})",
                        active=False,
                        hidden_identifier=item_str,
                    )
                    results.append((placeholder, False))
                    seen_ids.add(key)

        return results


def _find_helper_path() -> str | None:
    """Locate the privileged nextboot-helper executable, preferring sudoers-authorized paths."""
    for candidate in ("/usr/local/libexec/nextboot-helper", "/usr/libexec/nextboot-helper"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    which_helper = shutil.which("nextboot-helper")
    if which_helper:
        return which_helper

    local_candidate = Path(__file__).parent / "nextboot-helper.sh"
    if local_candidate.exists():
        return str(local_candidate)
    return None


def set_bootnext(entry_id: str, dry_run: bool = False) -> tuple[bool, str]:
    """Execute BootNext command via the privileged helper."""
    norm_id = entry_id.strip().upper()
    if not re.match(r"^[0-9A-F]{4}$", norm_id):
        return False, f"Invalid boot entry format: {entry_id}"

    if dry_run:
        return True, f"[DRY-RUN] Would set UEFI BootNext to Boot{norm_id}"

    helper_path = _find_helper_path()
    if not helper_path:
        return False, "nextboot-helper binary not found. Please run the installer."

    cmd = ["sudo", helper_path, norm_id]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, proc.stdout.strip()
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip() or f"Helper exited with code {e.returncode}"
        return False, f"Failed to set BootNext: {err_msg}"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Execution error: {e}"


def clear_bootnext(dry_run: bool = False) -> tuple[bool, str]:
    """Clear any pending UEFI BootNext variable via the privileged helper."""
    if dry_run:
        return True, "[DRY-RUN] Would clear UEFI BootNext"

    helper_path = _find_helper_path()
    if not helper_path:
        return False, "nextboot-helper binary not found. Please run the installer."

    cmd = ["sudo", helper_path, "--clear"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, proc.stdout.strip()
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() or e.stdout.strip() or f"Helper exited with code {e.returncode}"
        return False, f"Failed to clear BootNext: {err_msg}"
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"Execution error: {e}"


def execute_reboot(firmware_setup: bool = False, dry_run: bool = False) -> tuple[bool, str]:
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
    except (OSError, subprocess.SubprocessError) as e:
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
    icon_path: str | None = None,
    target: str = "desktop",
) -> tuple[bool, str]:
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
                except OSError:
                    pass

            if shutil.which("update-desktop-database"):
                try:
                    subprocess.run(
                        ["update-desktop-database", str(target_dir)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                except OSError:
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
                    except OSError:
                        pass

        return True, str(desktop_file)
    except OSError as e:
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


