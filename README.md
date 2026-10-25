# NextBoot

NextBoot (`nboot`) is a lightweight graphical and command-line utility for Linux systems that enables one-click and shorthand rebooting into Windows or any other operating system installed on your computer.

It utilizes the UEFI standard `BootNext` mechanism. Setting `BootNext` instructs your motherboard to boot into the selected operating system for the next boot only. Once that operating system restarts or shuts down, your computer automatically returns to your regular default boot order.

<p align="center">
  <img src="assets/screenshot.png" alt="NextBoot Graphical Interface" width="420">
  <img src="assets/cli_reference.png" alt="NextBoot CLI Commands Reference" width="420">
</p>

## Features

- **One-Click Reboot**: Reboot into Windows or other operating systems from a native Qt GUI or terminal command.
- **Top 100+ Distro Vector Logos**: Comprehensive built-in library of 105 vector SVG logos covering top DistroWatch distributions, BSD systems, and specialized operating systems with zero bloat (< 900 KB).
- **Clean OS Filtering**: Intelligently distinguishes real bootable operating systems from raw motherboard hardware stubs (NVMe slots, SATA ports, PXE LAN) and internal firmware diagnostics.
- **Hide & Restore Unwanted Entries**: Right-click to hide any entries you don't want to see; restore them individually or all at once via the bottom action bar.
- **Desktop & Hotkey Shortcuts**: Right-click any OS entry to create an executable Desktop shortcut, add an Application Menu launcher (for GNOME Dash / KDE KRunner search and taskbar pinning), or copy its instant reboot command for global keybindings.
- **Desktop Environment & Wayland Intelligence**: Automatically adapts to GNOME, KDE Plasma, XFCE, Cinnamon, MATE, COSMIC, and Wayland/Hyprland compositors.
- **Automatic Reversion**: Subsequent boots return to your default Linux environment without manual boot menu intervention.
- **Smart Dynamic Detection**: Dynamically inspects UEFI NVRAM entries via `efibootmgr`. No hardcoded drive UUIDs or partition numbers.
- **Interactive CLI Reference**: Built-in dialog (`?` button or `F1` shortcut) dynamically displays terminal commands tailored to your active boot entries with environment-aware tips.
- **Universal Sudoers Support**: Compatible with both `%wheel` (Fedora, Nobara, Arch) and `%sudo` (Ubuntu, Debian) administrative groups.
- **Detached Drive Friendly**: If a drive is temporarily disconnected, NextBoot detects its absence gracefully. As soon as the drive is reconnected or an OS is reinstalled, NextBoot picks it up automatically.
- **Fast CLI Shorthands**: Intuitive commands like `nboot win`, `nboot fedora`, `nboot arch`, and `nboot bios`.
- **UEFI Firmware Setup**: Quick reboot directly into motherboard BIOS/UEFI setup.
- **Flexible Reboots**: Select an OS and click the action button, or toggle one-click rebooting for instant switching.

## CLI Usage

The primary command is `nboot` (with `nextboot` available as an alias).

### Quick Commands

| Command | Action |
| :--- | :--- |
| `nboot` | Reboot into your configured default OS (e.g., Windows) |
| `nboot win` / `nboot windows` | Reboot into Windows |
| `nboot fedora` / `nboot nobara` | Reboot into Fedora / Nobara |
| `nboot bios` / `nboot uefi` | Reboot directly into UEFI/BIOS Firmware Setup |
| `nboot ls` / `nboot list` | List all detected bootable OS entries (use `-a` to include hidden) |
| `nboot hide <target>` | Hide a boot entry from the main list (e.g., `nboot hide 0013`) |
| `nboot unhide <target>` | Restore a hidden entry (use `nboot unhide all` to restore all) |
| `nboot hidden` | List all currently hidden boot entries |
| `nboot status` | Display current UEFI BootNext status and default target |
| `nboot set-default <target>` | Set persistent default OS (e.g., `nboot set-default win`) |
| `nboot gui` | Open the graphical interface |

### Command Flags

- `-a`, `--all`: Show all entries including hidden ones in `nboot list`.
- `-y`, `--now`: Skip confirmation prompt and reboot immediately (e.g. `nboot win -y`).
- `-d`, `--dry-run`: Test target resolution and simulate action without modifying NVRAM or rebooting.
- `-h`, `--help`: Display CLI help and options.

## GUI Usage

Launch **NextBoot** from your desktop application launcher (under System or Utilities) or run `nboot gui` in terminal.

The interface presents:
1. All detected bootable operating systems with official distro/OS emblems.
2. An active `CURRENT` badge indicating the currently running system.
3. A button to reboot directly into the selected OS (or double-click to reboot).
4. Direct entry to reboot into Motherboard UEFI Firmware Setup.
5. A "One-click reboot" checkbox to toggle immediate rebooting when an entry is clicked.
6. A **`?`** button (or `F1` shortcut) providing an instant reference of CLI commands dynamically generated from your active boot entries.
7. Right-click context menu on any entry to create a Desktop shortcut, register an Application Menu launcher (for GNOME Dash / KDE Application Menu search and taskbar pinning), copy its terminal command, or **Hide Entry** to unclutter unwanted firmware tools.
8. A subtle grey **`Hidden (N)`** button in the center of the bottom action bar whenever entries are hidden, opening the **Hidden Boot Entries** dialog to view and restore items individually or all at once.

## Installation

### Prerequisites

NextBoot requires:
- `efibootmgr` (standard on modern Linux installations)
- Python 3.8+
- `PyQt6` (for GUI mode)
- `systemd`

### Install Steps

Clone the repository and run the installer:

```bash
git clone https://github.com/PlasmaDrifter/NextBoot.git
cd NextBoot
sudo ./install.sh
```

The installer performs out-of-the-box setup:
1. **Automated Package Dependencies**:
   - On **Arch Linux**: Automatically installs `efibootmgr`, `python-pyqt6`, and `qt6-wayland` via `pacman -S --needed`.
   - On **Debian / Ubuntu**: Automatically installs `efibootmgr`, `python3-pyqt6`, `python3-pyqt6.qtsvg`, and `qt6-wayland` via `apt-get`.
2. **Hyprland Window Rules**: Automatically detects `~/.config/hypr/hyprland.conf` and registers floating and centered window rules so NextBoot floats out of the box instead of tiling.
3. **Privileged Backend Helper**: Installs to `/usr/local/libexec/nextboot-helper`.
4. **Scoped Sudoers Policy**: Configures `/etc/sudoers.d/99-nextboot` allowing members of `%wheel` and `%sudo` to set `BootNext` without a password prompt.
5. **Core Application & 100+ Distro Logos**: Installs libraries and 106 vector SVG logos to `/usr/local/share/nextboot/`.
6. **Binaries & Desktop Launcher**: Registers `/usr/local/bin/nboot`, `/usr/local/bin/nextboot`, and `/usr/local/share/applications/nextboot.desktop`.
7. **Bash Shell Autocompletions**: Installs completions to `/usr/share/bash-completion/completions/nboot`.

## Uninstallation

To completely remove NextBoot from your system:

```bash
cd NextBoot
sudo ./uninstall.sh
```

## How It Works Under the Hood

1. NextBoot parses `efibootmgr` to locate boot entries matching operating systems.
2. When a reboot is requested, NextBoot sets the temporary UEFI variable `BootNext` to the entry ID of the chosen operating system.
3. NextBoot triggers `systemctl reboot`.
4. The motherboard reads `BootNext`, boots that operating system once, and clears `BootNext`.
5. Future boots use the standard `BootOrder`, returning you straight to Nobara.

## License

MIT License
