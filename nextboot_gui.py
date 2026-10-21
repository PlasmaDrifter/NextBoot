#!/usr/bin/env python3
"""
nextboot_gui.py - Clean, muted list interface for NextBoot with distro logos
and automatic sub-distro recognition (Nobara, CachyOS, etc.).
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QKeyEvent
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from nextboot_core import (
    BootEntry,
    UEFIManager,
    create_os_shortcut,
    detect_desktop_environment,
    execute_reboot,
    load_config,
    save_config,
    set_bootnext,
    simplify_os_name,
    __version__,
)

SCRIPT_DIR = Path(__file__).parent.resolve()
possible_assets = [
    SCRIPT_DIR / "assets",
    Path.home() / ".local" / "share" / "nextboot" / "assets",
    Path("/usr/local/share/nextboot/assets"),
    Path("/usr/share/nextboot/assets"),
]
ASSETS_DIR = SCRIPT_DIR / "assets"
for p in possible_assets:
    distros_folder = p / "distros"
    try:
        if distros_folder.is_dir() and any(distros_folder.iterdir()):
            ASSETS_DIR = p
            break
    except Exception:
        pass

DISTROS_DIR = ASSETS_DIR / "distros"


def resolve_distro_icon_path(entry: Optional[BootEntry], is_firmware: bool = False) -> Path:
    if is_firmware:
        return DISTROS_DIR / "uefi.svg"
    if not entry:
        return DISTROS_DIR / "linux.svg"

    text = f"{entry.title} {entry.raw_title} {' '.join(entry.slugs)}".lower()

    mapping = [
        (["windows", "bootmgfw", "microsoft"], "windows.svg"),
        (["nobara"], "nobara.svg"),
        (["cachy"], "cachyos.svg"),
        (["bazzite"], "bazzite.svg"),
        (["mx linux", "mx-linux", "mx"], "mx.svg"),
        (["antix"], "antix.svg"),
        (["fedora"], "fedora.svg"),
        (["endeavour"], "endeavouros.svg"),
        (["garuda"], "garuda.svg"),
        (["manjaro"], "manjaro.svg"),
        (["arch", "omarchy"], "arch.svg"),
        (["artix"], "artix.svg"),
        (["pop-os", "pop_os", "popos"], "popos.svg"),
        (["mint", "linuxmint"], "mint.svg"),
        (["elementary"], "elementary.svg"),
        (["zorin"], "zorin.svg"),
        (["kubuntu"], "kubuntu.svg"),
        (["lubuntu"], "lubuntu.svg"),
        (["xubuntu"], "xubuntu.svg"),
        (["ubuntu"], "ubuntu.svg"),
        (["debian"], "debian.svg"),
        (["devuan"], "devuan.svg"),
        (["opensuse", "suse"], "opensuse.svg"),
        (["steamos"], "steamos.svg"),
        (["nixos"], "nixos.svg"),
        (["void"], "void.svg"),
        (["gentoo"], "gentoo.svg"),
        (["alpine"], "alpine.svg"),
        (["freebsd", "bsd"], "freebsd.svg"),
        (["q4os"], "q4os.svg"),
        (["tuxedo"], "tuxedo.svg"),
        (["mageia"], "mageia.svg"),
        (["pclinuxos"], "pclinuxos.svg"),
        (["puppy"], "puppy.svg"),
        (["lite", "linux lite"], "lite.svg"),
        (["kali"], "kali.svg"),
        (["solus"], "solus.svg"),
        (["deepin"], "deepin.svg"),
        (["neon", "kde neon"], "neon.svg"),
        (["vanilla"], "vanilla.svg"),
        (["pureos"], "pureos.svg"),
        (["parrot"], "parrot.svg"),
        (["centos"], "centos.svg"),
        (["rhel", "redhat", "red hat"], "rhel.svg"),
        (["raspbian", "raspberry"], "raspbian.svg"),
        (["peppermint"], "peppermint.svg"),
        (["bodhi"], "bodhi.svg"),
        (["usb", "flash drive", "samsung"], "usb.svg"),
    ]

    for keywords, filename in mapping:
        if any(k in text for k in keywords):
            p = DISTROS_DIR / filename
            if p.exists():
                return p

    return DISTROS_DIR / "linux.svg"


class OSListRowWidget(QWidget):
    def __init__(
        self,
        entry: Optional[BootEntry] = None,
        is_current: bool = False,
        is_default: bool = False,
        is_firmware_setup: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.entry = entry
        self.is_current = is_current
        self.is_default = is_default
        self.is_firmware_setup = is_firmware_setup

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 1. Distro / OS SVG Logo
        icon_path = resolve_distro_icon_path(entry, is_firmware=is_firmware_setup)
        if icon_path.exists():
            distro_icon = QSvgWidget(str(icon_path), self)
            distro_icon.setFixedSize(30, 30)
            distro_icon.setStyleSheet("background: transparent;")
            layout.addWidget(distro_icon)
        else:
            fallback = QLabel("OS", self)
            fallback.setFixedSize(30, 30)
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet("background-color: #21262d; color: #8b949e; border-radius: 6px; font-size: 10px; font-weight: bold;")
            layout.addWidget(fallback)

        # 2. Title & Subtitle Info
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        accent_orange = "#fb923c"

        if is_firmware_setup:
            title_text = "UEFI Firmware / BIOS Setup"
            sub_html = f"Reboots to BIOS / UEFI  ·  <span style='color: {accent_orange}; font-weight: 600;'>nboot uefi</span>"
        elif entry:
            title_text = entry.title
            sub_parts = [f"Boot{entry.entry_id}"]
            if entry.base_distro:
                sub_parts.append(entry.base_distro)
            if entry.slugs:
                sub_parts.append(f"<span style='color: {accent_orange}; font-weight: 600;'>nboot {entry.slugs[0]}</span>")
            sub_html = "  ·  ".join(sub_parts)
        else:
            title_text = "Unknown Entry"
            sub_html = ""

        title_lbl = QLabel(title_text, self)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #e6edf3; background: transparent;")
        text_layout.addWidget(title_lbl)

        sub_lbl = QLabel(self)
        sub_lbl.setTextFormat(Qt.TextFormat.RichText)
        sub_lbl.setText(sub_html)
        sub_lbl.setStyleSheet("color: #7d8590; font-size: 11px; background: transparent;")
        text_layout.addWidget(sub_lbl)

        layout.addLayout(text_layout, stretch=1)

        # 3. Muted Status Badges
        badge_box = QHBoxLayout()
        badge_box.setSpacing(6)
        badge_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if is_current:
            cur_lbl = QLabel("CURRENT", self)
            cur_lbl.setFixedSize(76, 24)
            cur_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cur_lbl.setStyleSheet(
                "background-color: #21262d; color: #8b949e; border: 1px solid #30363d; border-radius: 4px; font-size: 10px; font-weight: bold;"
            )
            badge_box.addWidget(cur_lbl)

        if is_default:
            def_lbl = QLabel("DEFAULT", self)
            def_lbl.setFixedSize(76, 24)
            def_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            def_lbl.setStyleSheet(
                "background-color: #21262d; color: #c9d1d9; border: 1px solid #484f58; border-radius: 4px; font-size: 10px; font-weight: bold;"
            )
            badge_box.addWidget(def_lbl)

        layout.addLayout(badge_box)


class CliHelpDialog(QDialog):
    def __init__(self, mgr: UEFIManager, parent=None):
        super().__init__(parent)
        self.mgr = mgr
        self.setWindowTitle("CLI Commands Reference - NextBoot")
        self.setFixedSize(580, 640)
        self.setStyleSheet("""
            QDialog {
                background-color: #161b22;
                color: #c9d1d9;
                font-family: system-ui, -apple-system, sans-serif;
            }
            QLabel#dialogTitle {
                color: #f0f6fc;
                font-size: 15px;
                font-weight: bold;
            }
            QLabel#dialogSubtitle {
                color: #7d8590;
                font-size: 11px;
            }
            QLabel#sectionHeader {
                color: #8b949e;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 0.5px;
                margin-top: 4px;
            }
            QFrame#cardBox {
                background-color: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            QPushButton#closeBtn {
                background-color: #21262d;
                color: #f0f6fc;
                font-size: 12px;
                font-weight: 600;
                border-radius: 6px;
                padding: 6px 18px;
                border: 1px solid #30363d;
            }
            QPushButton#closeBtn:hover {
                background-color: #30363d;
                border: 1px solid #484f58;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: #0d1117;
                width: 6px;
                margin: 0;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #30363d;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #484f58;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 20, 22, 18)
        main_layout.setSpacing(12)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(3)
        title = QLabel("CLI Commands Reference", self)
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Run nboot in terminal to set one-time reboot targets", self)
        subtitle.setObjectName("dialogSubtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main_layout.addLayout(header_layout)

        de = detect_desktop_environment()
        if de == "gnome":
            tip_desc = "Right-click any operating system in the list to add to GNOME Dash/Search or create desktop shortcuts."
        else:
            tip_desc = "Right-click any operating system in the list to create Desktop & Application Menu shortcuts."

        tip_box = QLabel(
            f"<span style='color: #fb923c; font-weight: 600;'>Tip:</span> "
            f"<span style='color: #c9d1d9;'>{tip_desc}</span>",
            self,
        )
        tip_box.setTextFormat(Qt.TextFormat.RichText)
        tip_box.setStyleSheet(
            "background-color: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 7px 10px; font-size: 11px;"
        )
        main_layout.addWidget(tip_box)

        # Scroll Area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 2, 6, 2)
        content_layout.setSpacing(10)

        # 1. Detected Boot Targets
        sec1_lbl = QLabel("DETECTED BOOT TARGETS", content)
        sec1_lbl.setObjectName("sectionHeader")
        content_layout.addWidget(sec1_lbl)

        card1 = QFrame(content)
        card1.setObjectName("cardBox")
        grid1 = QGridLayout(card1)
        grid1.setContentsMargins(12, 10, 12, 10)
        grid1.setHorizontalSpacing(16)
        grid1.setVerticalSpacing(7)

        default_entry = self.mgr.get_default_entry()
        row = 0

        # Default reboot command
        if default_entry:
            cmd_def = QLabel("<span style='color: #fb923c; font-family: monospace; font-size: 12px; font-weight: bold;'>nboot</span>")
            cmd_def.setTextFormat(Qt.TextFormat.RichText)
            desc_def = QLabel(f"<span style='color: #c9d1d9; font-size: 11px;'>Reboot to default target ({default_entry.title})</span>")
            desc_def.setTextFormat(Qt.TextFormat.RichText)
            grid1.addWidget(cmd_def, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid1.addWidget(desc_def, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

        if not self.mgr.entries:
            no_entries = QLabel("<span style='color: #8b949e; font-size: 11px;'>No active UEFI boot entries detected.</span>")
            no_entries.setTextFormat(Qt.TextFormat.RichText)
            grid1.addWidget(no_entries, row, 0, 1, 2)
            row += 1
        else:
            for entry in self.mgr.entries:
                slug = entry.slugs[0] if entry.slugs else entry.entry_id.lower()
                is_def = (default_entry and entry.entry_id == default_entry.entry_id)
                is_cur = (entry.entry_id == self.mgr.boot_current)

                badges = []
                if is_def:
                    badges.append("<span style='color: #ea580c; font-size: 10px; font-weight: 700;'>[DEFAULT]</span>")
                if is_cur:
                    badges.append("<span style='color: #58a6ff; font-size: 10px; font-weight: 700;'>[CURRENT]</span>")
                badge_html = (" " + " ".join(badges)) if badges else ""

                cmd_lbl = QLabel(f"<span style='color: #fb923c; font-family: monospace; font-size: 12px; font-weight: bold;'>nboot {slug}</span>")
                cmd_lbl.setTextFormat(Qt.TextFormat.RichText)
                desc_lbl = QLabel(f"<span style='color: #8b949e; font-size: 11px;'>{entry.title} <span style='color: #6e7681;'>(Boot{entry.entry_id})</span>{badge_html}</span>")
                desc_lbl.setTextFormat(Qt.TextFormat.RichText)

                grid1.addWidget(cmd_lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
                grid1.addWidget(desc_lbl, row, 1, Qt.AlignmentFlag.AlignLeft)
                row += 1

        # BIOS / UEFI command
        cmd_fw = QLabel("<span style='color: #fb923c; font-family: monospace; font-size: 12px; font-weight: bold;'>nboot bios | uefi</span>")
        cmd_fw.setTextFormat(Qt.TextFormat.RichText)
        desc_fw = QLabel("<span style='color: #8b949e; font-size: 11px;'>Reboot into UEFI Firmware / BIOS Setup</span>")
        desc_fw.setTextFormat(Qt.TextFormat.RichText)
        grid1.addWidget(cmd_fw, row, 0, Qt.AlignmentFlag.AlignLeft)
        grid1.addWidget(desc_fw, row, 1, Qt.AlignmentFlag.AlignLeft)

        grid1.setColumnStretch(1, 1)
        content_layout.addWidget(card1)

        # 2. Utility & Management
        sec2_lbl = QLabel("UTILITY & MANAGEMENT", content)
        sec2_lbl.setObjectName("sectionHeader")
        content_layout.addWidget(sec2_lbl)

        card2 = QFrame(content)
        card2.setObjectName("cardBox")
        grid2 = QGridLayout(card2)
        grid2.setContentsMargins(12, 10, 12, 10)
        grid2.setHorizontalSpacing(16)
        grid2.setVerticalSpacing(7)

        cmds = [
            ("nboot list | ls", "List all bootable entries with IDs and aliases"),
            ("nboot status", "Display current BootNext NVRAM status and boot order"),
            ("nboot set-default &lt;target&gt;", "Set persistent default OS (e.g. nboot set-default windows)"),
            ("nboot gui", "Launch NextBoot graphical interface"),
        ]
        for r, (c, d) in enumerate(cmds):
            c_lbl = QLabel(f"<span style='color: #fb923c; font-family: monospace; font-size: 12px; font-weight: bold;'>{c}</span>")
            c_lbl.setTextFormat(Qt.TextFormat.RichText)
            d_lbl = QLabel(f"<span style='color: #8b949e; font-size: 11px;'>{d}</span>")
            d_lbl.setTextFormat(Qt.TextFormat.RichText)
            grid2.addWidget(c_lbl, r, 0, Qt.AlignmentFlag.AlignLeft)
            grid2.addWidget(d_lbl, r, 1, Qt.AlignmentFlag.AlignLeft)
        grid2.setColumnStretch(1, 1)
        content_layout.addWidget(card2)

        # 3. Flags & Options
        sec3_lbl = QLabel("FLAGS & OPTIONS", content)
        sec3_lbl.setObjectName("sectionHeader")
        content_layout.addWidget(sec3_lbl)

        card3 = QFrame(content)
        card3.setObjectName("cardBox")
        grid3 = QGridLayout(card3)
        grid3.setContentsMargins(12, 10, 12, 10)
        grid3.setHorizontalSpacing(16)
        grid3.setVerticalSpacing(7)

        flags = [
            ("-y, --now", "Reboot immediately without confirmation prompt"),
            ("-d, --dry-run", "Simulate command without modifying NVRAM or rebooting"),
            ("-h, --help", "Display CLI help output"),
        ]
        for r, (f, d) in enumerate(flags):
            f_lbl = QLabel(f"<span style='color: #58a6ff; font-family: monospace; font-size: 12px; font-weight: bold;'>{f}</span>")
            f_lbl.setTextFormat(Qt.TextFormat.RichText)
            d_lbl = QLabel(f"<span style='color: #8b949e; font-size: 11px;'>{d}</span>")
            d_lbl.setTextFormat(Qt.TextFormat.RichText)
            grid3.addWidget(f_lbl, r, 0, Qt.AlignmentFlag.AlignLeft)
            grid3.addWidget(d_lbl, r, 1, Qt.AlignmentFlag.AlignLeft)
        grid3.setColumnStretch(1, 1)
        content_layout.addWidget(card3)

        content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll, stretch=1)

        # Footer
        footer = QHBoxLayout()
        hint = QLabel("<span style='color: #7d8590; font-size: 11px;'>Example: <span style='font-family: monospace; color: #c9d1d9;'>nboot windows --now</span></span>")
        hint.setTextFormat(Qt.TextFormat.RichText)
        footer.addWidget(hint)
        footer.addStretch()

        close_btn = QPushButton("Close", self)
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        main_layout.addLayout(footer)


class NextBootWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.mgr = UEFIManager()
        self.config = load_config()
        self.de = detect_desktop_environment()
        self.items_data: List[dict] = []

        self.setWindowTitle("NextBoot")

        # Default size 580x585, restore saved geometry if configured
        init_w = int(self.config.get("window_width", 580))
        init_h = int(self.config.get("window_height", 585))
        self.resize(init_w, init_h)
        self.setMinimumSize(480, 360)

        # Set window icon to grey/black arrow
        icon_path = ASSETS_DIR / "app_icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._load_list()
        self._apply_global_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Update config with current window dimensions
        if not self.isMaximized() and not self.isMinimized():
            self.config["window_width"] = self.width()
            self.config["window_height"] = self.height()
            save_config(self.config)

    def closeEvent(self, event):
        if not self.isMaximized() and not self.isMinimized():
            self.config["window_width"] = self.width()
            self.config["window_height"] = self.height()
            save_config(self.config)
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        count = self.list_widget.count()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.reboot_btn.isEnabled():
                self._on_reboot_clicked()
                event.accept()
                return

        elif key == Qt.Key.Key_Down:
            if count > 0:
                cur = self.list_widget.currentRow()
                nxt = (cur + 1) if (cur + 1 < count) else 0
                self.list_widget.setCurrentRow(nxt)
                self.list_widget.setFocus()
                event.accept()
                return

        elif key == Qt.Key.Key_Up:
            if count > 0:
                cur = self.list_widget.currentRow()
                prev = (cur - 1) if (cur - 1 >= 0) else (count - 1)
                self.list_widget.setCurrentRow(prev)
                self.list_widget.setFocus()
                event.accept()
                return

        elif key in (Qt.Key.Key_Question, Qt.Key.Key_F1):
            self._show_cli_help()
            event.accept()
            return

        super().keyPressEvent(event)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 18, 22, 20)
        main_layout.setSpacing(14)

        # 1. Header Bar with Grey-Black Arrow Brand
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_path = ASSETS_DIR / "app_icon.svg"
        if icon_path.exists():
            brand_icon = QSvgWidget(str(icon_path), self)
            brand_icon.setFixedSize(36, 36)
            brand_icon.setStyleSheet("background: transparent;")
            header.addWidget(brand_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        app_title = QLabel(
            f"<span style='font-size: 16px; font-weight: bold; color: #f0f6fc;'>NextBoot</span> "
            f"<span style='font-size: 11px; font-weight: 600; color: #7d8590;'>{__version__}</span>",
            self,
        )
        app_title.setTextFormat(Qt.TextFormat.RichText)
        app_title.setObjectName("appTitle")
        title_vbox.addWidget(app_title)

        app_desc = QLabel("One-Time OS Reboot Utility", self)
        app_desc.setObjectName("appSubtitle")
        title_vbox.addWidget(app_desc)
        header.addLayout(title_vbox, stretch=1)

        self.help_btn = QPushButton("?", self)
        self.help_btn.setObjectName("helpBtn")
        self.help_btn.setFixedSize(28, 28)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.setToolTip("CLI Commands Reference")
        self.help_btn.clicked.connect(self._show_cli_help)
        header.addWidget(self.help_btn)

        self.refresh_btn = QPushButton("Refresh", self)
        self.refresh_btn.setObjectName("subtleBtn")
        self.refresh_btn.setFixedHeight(28)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)

        main_layout.addLayout(header)

        # Notice banner if Windows is missing
        self.banner = QLabel(self)
        self.banner.setObjectName("statusBanner")
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        main_layout.addWidget(self.banner)

        # 2. Clean List of Entries with Distro Logos
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("bootList")
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        main_layout.addWidget(self.list_widget, stretch=1)

        # 3. Bottom Action Bar
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)
        bottom_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.one_click_chk = QCheckBox("One-click reboot", self)
        self.one_click_chk.setObjectName("oneClickCheckbox")
        self.one_click_chk.setCursor(Qt.CursorShape.PointingHandCursor)
        self.one_click_chk.setChecked(bool(self.config.get("one_click_reboot", False)))
        self.one_click_chk.toggled.connect(self._on_one_click_toggled)
        bottom_row.addWidget(self.one_click_chk)

        bottom_row.addStretch()

        self.reboot_btn = QPushButton("Reboot", self)
        self.reboot_btn.setObjectName("actionRebootBtn")
        self.reboot_btn.setFixedHeight(36)
        self.reboot_btn.setMinimumWidth(180)
        self.reboot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reboot_btn.clicked.connect(self._on_reboot_clicked)
        bottom_row.addWidget(self.reboot_btn)

        main_layout.addLayout(bottom_row)

    def _on_one_click_toggled(self, checked: bool):
        self.config["one_click_reboot"] = checked
        save_config(self.config)

    def _load_list(self):
        self.mgr.refresh()
        self.config = load_config()
        self.one_click_chk.blockSignals(True)
        self.one_click_chk.setChecked(bool(self.config.get("one_click_reboot", False)))
        self.one_click_chk.blockSignals(False)
        self.list_widget.clear()
        self.items_data.clear()

        default_entry = self.mgr.get_default_entry()

        has_windows = any(e.os_type == "windows" for e in self.mgr.entries)
        if not has_windows:
            self.banner.setText("Notice: Windows Boot Manager not found in UEFI NVRAM. Connect Windows drive to enable.")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)

        default_row = 0

        # Add detected UEFI entries
        for idx, entry in enumerate(self.mgr.entries):
            is_current = (entry.entry_id == self.mgr.boot_current)
            is_default = (default_entry and entry.entry_id == default_entry.entry_id)

            item = QListWidgetItem(self.list_widget)
            widget = OSListRowWidget(
                entry=entry,
                is_current=is_current,
                is_default=is_default,
                is_firmware_setup=False,
                parent=self.list_widget,
            )
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

            self.items_data.append({
                "entry": entry,
                "is_firmware": False,
            })

            if is_default:
                default_row = idx

        # Add UEFI Firmware Setup option
        fw_item = QListWidgetItem(self.list_widget)
        fw_widget = OSListRowWidget(
            entry=None,
            is_current=False,
            is_default=False,
            is_firmware_setup=True,
            parent=self.list_widget,
        )
        fw_item.setSizeHint(fw_widget.sizeHint())
        self.list_widget.addItem(fw_item)
        self.list_widget.setItemWidget(fw_item, fw_widget)
        self.items_data.append({
            "entry": None,
            "is_firmware": True,
        })

        if self.items_data:
            self.list_widget.setCurrentRow(default_row)
            self.list_widget.setFocus()

    def _get_selected_data(self) -> Optional[dict]:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items_data):
            return self.items_data[row]
        return None

    def _on_selection_changed(self, current: QListWidgetItem, previous: Optional[QListWidgetItem]):
        data = self._get_selected_data()
        if not data:
            self.reboot_btn.setEnabled(False)
            self.reboot_btn.setText("Reboot")
            return

        self.reboot_btn.setEnabled(True)
        if data["is_firmware"]:
            self.reboot_btn.setText("Reboot to BIOS Setup")
        else:
            entry: BootEntry = data["entry"]
            self.reboot_btn.setText(f"Reboot into {entry.title}")

    def _on_item_clicked(self, item: QListWidgetItem):
        if self.one_click_chk.isChecked():
            self._on_reboot_clicked()

    def _on_item_double_clicked(self, item: QListWidgetItem):
        self._on_reboot_clicked()

    def _refresh(self):
        self._load_list()

    def _show_cli_help(self):
        dlg = CliHelpDialog(self.mgr, self)
        dlg.exec()

    def _execute_reboot_for_data(self, data: dict):
        is_firmware = data["is_firmware"]
        entry: Optional[BootEntry] = data["entry"]

        if is_firmware:
            success, msg = execute_reboot(firmware_setup=True, dry_run=False)
        else:
            success, msg = set_bootnext(entry.entry_id, dry_run=False)
            if not success:
                QMessageBox.critical(self, "BootNext Error", msg)
                return
            success, msg = execute_reboot(firmware_setup=False, dry_run=False)

        if not success:
            QMessageBox.critical(self, "Reboot Error", msg)

    def _on_reboot_clicked(self):
        data = self._get_selected_data()
        if not data:
            return
        self._execute_reboot_for_data(data)

    def _show_status_message(self, text: str, is_error: bool = False):
        color = "#f85149" if is_error else "#58a6ff"
        border = "#da3633" if is_error else "#1f6feb"
        bg = "#161b22"
        self.banner.setStyleSheet(
            f"background-color: {bg}; color: {color}; border: 1px solid {border}; border-radius: 6px; padding: 6px 12px; font-size: 11px;"
        )
        self.banner.setText(text)
        self.banner.setVisible(True)
        QTimer.singleShot(4000, lambda: self.banner.setVisible(False))

    def _create_shortcut(self, title: str, slug: str, icon_path: Path, target: str):
        success, res = create_os_shortcut(title, slug, str(icon_path.resolve()), target=target)
        if success:
            shortcut_name = f"Reboot into {simplify_os_name(title)}"
            if target == "desktop":
                loc = "Desktop"
            elif self.de == "gnome":
                loc = "Application Menu (searchable in GNOME Dash)"
            else:
                loc = "Application Menu"
            self._show_status_message(f"Created shortcut '{shortcut_name}' in your {loc}.")
        else:
            self._show_status_message(f"Error creating shortcut: {res}", is_error=True)

    def _copy_hotkey_command(self, slug: str):
        cmd = f"nboot {slug} -y"
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(cmd)
            if self.de == "gnome":
                guide = "assign this in GNOME Settings -> Keyboard -> Custom Shortcuts."
            elif self.de == "kde":
                guide = "assign this in KDE System Settings -> Shortcuts."
            elif self.de == "hyprland":
                guide = f"bind this in ~/.config/hypr/hyprland.conf (e.g. exec, {cmd})."
            else:
                guide = "assign this in your Keyboard Shortcuts settings."
            self._show_status_message(f"Copied '{cmd}' to clipboard - {guide}")

    def _show_context_menu(self, pos: QPoint):
        item = self.list_widget.itemAt(pos)
        if not item:
            return

        row = self.list_widget.row(item)
        if not (0 <= row < len(self.items_data)):
            return

        self.list_widget.setCurrentRow(row)

        data = self.items_data[row]
        is_firmware = data["is_firmware"]
        entry: Optional[BootEntry] = data["entry"]

        if is_firmware:
            target_title = "UEFI Firmware Setup"
            slug = "uefi"
        else:
            target_title = entry.title
            slug = entry.slugs[0] if entry.slugs else entry.entry_id.lower()

        icon_path = resolve_distro_icon_path(entry, is_firmware=is_firmware)

        menu = QMenu(self)

        desktop_act = menu.addAction("Create Desktop Shortcut")
        desktop_act.triggered.connect(lambda: self._create_shortcut(target_title, slug, icon_path, "desktop"))

        app_menu_label = "Add to Application Menu (Pin to Dash)" if self.de == "gnome" else "Add to Application Menu"
        app_menu_act = menu.addAction(app_menu_label)
        app_menu_act.triggered.connect(lambda: self._create_shortcut(target_title, slug, icon_path, "applications"))

        menu.addSeparator()

        copy_act = menu.addAction("Copy CLI Command")
        copy_act.triggered.connect(lambda: self._copy_hotkey_command(slug))

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _apply_global_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0d1117;
                color: #c9d1d9;
                font-family: system-ui, -apple-system, sans-serif;
            }
            QLabel {
                background: transparent;
            }
            QLabel#appTitle {
                color: #f0f6fc;
                font-size: 16px;
                font-weight: bold;
            }
            QLabel#appSubtitle {
                color: #7d8590;
                font-size: 11px;
            }
            QLabel#statusBanner {
                background-color: #21262d;
                color: #d29922;
                border: 1px solid #30363d;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 11px;
            }
            QListWidget#bootList {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }
            QListWidget#bootList::item {
                background-color: #161b22;
                border: 1px solid transparent;
                border-radius: 4px;
                margin-bottom: 2px;
            }
            QListWidget#bootList::item:hover {
                background-color: #21262d;
            }
            QListWidget#bootList::item:selected {
                background-color: #21262d;
                border: 1px solid #484f58;
            }
            QPushButton#subtleBtn {
                background-color: #21262d;
                color: #c9d1d9;
                font-size: 11px;
                border-radius: 6px;
                padding: 6px 12px;
                border: 1px solid #30363d;
            }
            QPushButton#subtleBtn:hover {
                background-color: #30363d;
                color: #f0f6fc;
            }
            QPushButton#helpBtn {
                background-color: #21262d;
                color: #c9d1d9;
                font-size: 13px;
                font-weight: bold;
                border-radius: 6px;
                border: 1px solid #30363d;
            }
            QPushButton#helpBtn:hover {
                background-color: #30363d;
                color: #f0f6fc;
                border: 1px solid #484f58;
            }
            QPushButton#helpBtn:pressed {
                background-color: #161b22;
            }
            QPushButton#actionRebootBtn {
                background-color: #21262d;
                color: #f0f6fc;
                font-size: 12px;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 18px;
                border: 1px solid #484f58;
            }
            QPushButton#actionRebootBtn:hover {
                background-color: #30363d;
                border: 1px solid #6e7681;
            }
            QPushButton#actionRebootBtn:pressed {
                background-color: #161b22;
            }
            QCheckBox#oneClickCheckbox {
                color: #7d8590;
                font-size: 11px;
                spacing: 8px;
                background: transparent;
            }
            QCheckBox#oneClickCheckbox:hover {
                color: #c9d1d9;
            }
            QCheckBox#oneClickCheckbox::indicator {
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid #484f58;
                background-color: #21262d;
            }
            QCheckBox#oneClickCheckbox::indicator:hover {
                border: 1px solid #6e7681;
                background-color: #30363d;
            }
            QCheckBox#oneClickCheckbox::indicator:checked {
                background-color: #ea580c;
                border: 1px solid #fb923c;
                image: url(""" + str(ASSETS_DIR / "checkmark.svg") + """);
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 10px;
                margin: 4px 2px 4px 2px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #484f58;
                min-height: 28px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6e7681;
            }
            QScrollBar::handle:vertical:pressed {
                background-color: #8b949e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                background-color: transparent;
                height: 10px;
                margin: 2px 4px 2px 4px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #484f58;
                min-width: 28px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #6e7681;
            }
            QScrollBar::handle:horizontal:pressed {
                background-color: #8b949e;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
            QMenu {
                background-color: #282e38;
                color: #f0f6fc;
                border: 1px solid #484f58;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                padding: 6px 14px 6px 10px;
                border-radius: 4px;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #38414e;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3e4756;
                margin: 3px 4px;
            }
        """)


def launch_gui():
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    if os.environ.get("WAYLAND_DISPLAY") and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setApplicationName("NextBoot")
    app.setDesktopFileName("nextboot.desktop")
    icon_path = ASSETS_DIR / "app_icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = NextBootWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
