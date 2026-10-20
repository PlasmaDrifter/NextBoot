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

__version__ = "v0.7.0"

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
        "confirm_prompt": True,
        "window_width": 580,
        "window_height": 585,
    }
    if not config_file.exists():
        return default_config
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_config.update(data)
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
        if "arch" in text or "manjaro" in text or "endeavouros" in text:
            return "arch"
        if "linux" in text or "shim" in text or "grub" in text:
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
        self.entries: List[BootEntry] = []
        self.refresh()

    def refresh(self) -> None:
        self.boot_current = None
        self.boot_next = None
        self.boot_order = []
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
                self.entries.append(entry)

    def find_entry(self, query: str) -> Optional[BootEntry]:
        """Find the best matching boot entry by ID, slug, or title."""
        q = query.strip().lower().lstrip("-")
        for e in self.entries:
            if e.entry_id.lower() == q:
                return e
        for e in self.entries:
            if q in e.slugs:
                return e
        for e in self.entries:
            if q in e.title.lower() or q in e.raw_title.lower():
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
