from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import nextboot_cli
import nextboot_core
import nextboot_gui

SAMPLE_EFIBOOTMGR = """\
BootCurrent: 0001
Timeout: 1 seconds
BootOrder: 0001,0000,0002
Boot0000* Windows Boot Manager\tHD(1,GPT,01ef8eaf-c80b-4798-8237-6e37859644dc,0x1000,0x96000)/\\EFI\\MICROSOFT\\BOOT\\BOOTMGFW.EFI
Boot0001* Fedora\tHD(1,GPT,01ef8eaf-c80b-4798-8237-6e37859644dc,0x1000,0x96000)/\\EFI\\FEDORA\\SHIM.EFI
Boot0002* UEFI: Samsung Flash Drive FIT 1100, Partition 2\tPciRoot(0x0)/USB(0,0)/HD(2,MBR,0x34039f48,0x7772100,0x10000)
BootB001* Diagnostic Splash Screen\tFvFile(a7d8d9a6-6ab0-4aeb-ad9d-163e59a7a380)
"""

SAMPLE_LSBLK = json.dumps({
    "blockdevices": [
        {
            "name": "sda",
            "label": None,
            "model": "HUH728080ALE601",
            "tran": "sata",
            "children": [{"name": "sda1", "label": "disk8TB"}],
        },
        {
            "name": "sde",
            "label": None,
            "model": "Flash Drive FIT",
            "tran": "usb",
            "children": [
                {"name": "sde1", "label": "Ventoy"},
                {"name": "sde2", "label": "VTOYEFI"},
            ],
        },
        {
            "name": "sdf",
            "label": "RESCUEISO",
            "model": "Direct USB ISO",
            "tran": "usb",
            "children": [],
        },
    ]
})


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))

    def fake_check_output(cmd, text=True, stderr=None):
        if cmd[0] == "efibootmgr":
            return SAMPLE_EFIBOOTMGR
        if cmd[0] == "lsblk":
            return SAMPLE_LSBLK
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(nextboot_core.shutil, "which", lambda name: f"/usr/bin/{name}" if name in {"efibootmgr", "lsblk"} else None)
    monkeypatch.setattr(nextboot_core.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(
        nextboot_core,
        "get_host_os_info",
        lambda: {"name": "Nobara Linux", "id": "nobara", "id_like": "fedora", "pretty_name": "Nobara Linux 44"},
    )
    return tmp_path


def test_config_normalization_and_atomic_update(isolated_env: Path):
    cfg_path = nextboot_core.get_config_path()
    cfg_path.write_text(json.dumps({
        "default_target": " windows ",
        "one_click_reboot": True,
        "window_width": 100,
        "window_height": "bad",
        "hidden_entries": [" 0002 ", ""],
        "confirm_prompt": False,
    }))
    loaded = nextboot_core.load_config()
    assert loaded["default_target"] == "windows"
    assert loaded["one_click_reboot"] is True
    assert loaded["window_width"] == 480
    assert loaded["window_height"] == 585
    assert loaded["hidden_entries"] == ["0002"]
    assert "confirm_prompt" not in loaded

    updated = nextboot_core.update_config({"window_width": 600})
    assert updated["default_target"] == "windows"
    assert updated["window_width"] == 600


def test_configured_default_target_resolution(isolated_env: Path):
    mgr = nextboot_core.UEFIManager()
    entry, is_fw, target_str = mgr.get_configured_default()
    assert not is_fw
    assert target_str == "windows"
    assert entry is not None
    assert entry.entry_id == "0000"

    nextboot_core.update_config({"default_target": "uefi"})
    entry, is_fw, target_str = mgr.get_configured_default()
    assert is_fw is True
    assert entry is None

    nextboot_core.update_config({"default_target": "missing-os"})
    entry, is_fw, target_str = mgr.get_configured_default()
    assert not is_fw
    assert entry is None
    assert target_str == "missing-os"


def test_hide_bootb001_and_disconnected_entries(isolated_env: Path):
    mgr = nextboot_core.UEFIManager()

    ok, _ = nextboot_core.hide_entry("BootB001", mgr)
    assert ok is True
    ok_dup, _ = nextboot_core.hide_entry("B001", mgr)
    assert ok_dup is False

    ok_cur, msg_cur = nextboot_core.hide_entry("0001", mgr)
    assert ok_cur is False
    assert "active booted OS" in msg_cur

    ok_disc, _ = nextboot_core.hide_entry("0099", mgr)
    assert ok_disc is True

    hidden = mgr.get_hidden_entries()
    ids = [e.entry_id if e is not None else "UEFI" for e, _ in hidden]
    assert "B001" in ids
    assert "0099" in ids

    ok_unhide, _ = nextboot_core.unhide_entry("B001", mgr)
    assert ok_unhide is True
    ok_unhide2, _ = nextboot_core.unhide_entry("0099", mgr)
    assert ok_unhide2 is True
    assert mgr.get_hidden_entries() == []


def test_usb_detection_and_slugs(isolated_env: Path):
    labels = nextboot_core.detect_connected_usb_labels()
    assert labels == {
        "flash drive fit": "Ventoy",
        "direct usb iso": "RESCUEISO",
    }

    generic_usb = nextboot_core.BootEntry(
        "0005",
        "UEFI: SanDisk Cruzer Blade",
        True,
        "USB(0,0)/HD(1,MBR,0x1,0x1,0x10)",
        usb_labels=labels,
    )
    assert "ventoy" not in generic_usb.slugs
    assert "usb" in generic_usb.slugs

    pop_entry = nextboot_core.BootEntry("0006", "Pop!_OS 24.04", True, r"HD(1)/\EFI\SYSTEMD\SYSTEMD-BOOTX64.EFI")
    assert pop_entry.title == "Pop!_OS"


def test_fedora_current_does_not_say_based_on_fedora(isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        nextboot_core,
        "get_host_os_info",
        lambda: {"name": "Fedora Linux", "id": "fedora", "id_like": "", "pretty_name": "Fedora Linux 44"},
    )
    entry = nextboot_core.BootEntry("0001", "Fedora", True, r"HD(1)/\EFI\FEDORA\SHIM.EFI", is_current=True)
    assert entry.title == "Fedora Linux"
    assert entry.base_distro is None


def test_find_entry_rejects_short_ambiguous_queries(isolated_env: Path):
    mgr = nextboot_core.UEFIManager()
    assert mgr.find_entry("-s") is None
    assert mgr.find_entry("s") is None
    assert mgr.find_entry("a") is None
    assert mgr.find_entry("w").entry_id == "0000"  # type: ignore[union-attr]
    assert mgr.find_entry("wind").entry_id == "0000"  # type: ignore[union-attr]
    assert mgr.find_entry("diag") is None
    assert mgr.find_entry("B001").entry_id == "B001"  # type: ignore[union-attr]


def test_cli_unknown_flag_and_default_dry_run(isolated_env: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    bootnext_calls: list[str] = []

    def fake_set_bootnext(eid: str, dry_run: bool = False) -> tuple[bool, str]:
        bootnext_calls.append(eid)
        return True, "ok"

    monkeypatch.setattr(nextboot_cli, "set_bootnext", fake_set_bootnext)
    monkeypatch.setattr(nextboot_cli, "execute_reboot", lambda firmware_setup=False, dry_run=False: (True, "ok"))

    monkeypatch.setattr(sys, "argv", ["nboot", "-s", "-d", "-y"])
    with pytest.raises(SystemExit) as exc:
        nextboot_cli.main()
    assert exc.value.code == 1
    assert bootnext_calls == []
    assert "Unknown option '-s'" in capsys.readouterr().err

    monkeypatch.setattr(sys, "argv", ["nboot", "-d", "-y"])
    nextboot_cli.main()
    assert bootnext_calls == ["0000"]


def test_cli_non_tty_requires_yes_and_rollback_on_reboot_failure(isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    called_set: list[str] = []
    called_clear: list[bool] = []

    def fake_set(eid: str, dry_run: bool = False) -> tuple[bool, str]:
        called_set.append(eid)
        return True, "set"

    def fake_clear(dry_run: bool = False) -> tuple[bool, str]:
        called_clear.append(dry_run)
        return True, "cleared"

    monkeypatch.setattr(nextboot_cli, "set_bootnext", fake_set)
    monkeypatch.setattr(nextboot_cli, "clear_bootnext", fake_clear)
    monkeypatch.setattr(nextboot_cli, "execute_reboot", lambda firmware_setup=False, dry_run=False: (False, "inhibited"))

    monkeypatch.setattr(sys, "argv", ["nboot", "win"])
    with pytest.raises(SystemExit) as exc:
        nextboot_cli.main()
    assert exc.value.code == 1
    assert called_set == []

    monkeypatch.setattr(sys, "argv", ["nboot", "win", "-y"])
    with pytest.raises(SystemExit) as exc2:
        nextboot_cli.main()
    assert exc2.value.code == 1
    assert called_set == ["0000"]
    assert called_clear == [False]


def test_gui_icon_resolution_and_widgets(isolated_env: Path, monkeypatch: pytest.MonkeyPatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert app is not None

    ubuntu_samsung = nextboot_core.BootEntry(
        "0004",
        "ubuntu (Samsung SSD 980 PRO)",
        True,
        r"HD(1,GPT,0000)/\EFI\UBUNTU\GRUBX64.EFI",
    )
    assert nextboot_gui.resolve_distro_icon_path(ubuntu_samsung).name == "ubuntu.svg"

    ventoy = nextboot_core.BootEntry(
        "0002",
        "UEFI: Samsung Flash Drive FIT 1100, Partition 2",
        True,
        "USB(0,0)/HD(2,MBR,0x34039f48,0x7772100,0x10000)",
        usb_labels={"flash drive fit": "Ventoy"},
    )
    assert nextboot_gui.resolve_distro_icon_path(ventoy).name == "usb.svg"

    # Incomplete asset dir (missing app_icon.svg/checkmark.svg) must not shadow complete dir
    incomplete_dir = isolated_env / "incomplete_assets"
    (incomplete_dir / "distros").mkdir(parents=True)
    (incomplete_dir / "distros" / "linux.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(nextboot_gui, "possible_assets", [incomplete_dir, ROOT_DIR / "assets"])
    resolved_assets, resolved_distros = nextboot_gui._resolve_asset_dirs()
    assert resolved_assets == ROOT_DIR / "assets"
    assert (resolved_assets / "app_icon.svg").is_file()
    assert (resolved_assets / "checkmark.svg").is_file()
    assert resolved_distros == ROOT_DIR / "assets" / "distros"

    win = nextboot_gui.NextBootWindow()
    assert win.list_widget.count() == 4
    selected = win._get_selected_data()
    assert selected is not None and selected["entry"].entry_id == "0000"

    win._show_status_message("First")
    assert win._banner_timer.isActive()
    win._show_status_message("Second", undo_target="0002")
    assert win.current_undo_target == "0002"

    nextboot_core.hide_entry("0099", win.mgr)
    dlg = nextboot_gui.HiddenEntriesDialog(win.mgr, win)
    assert hasattr(dlg, "scroll_area")
    assert callable(dlg.scroll)
    help_dlg = nextboot_gui.CliHelpDialog(win.mgr, win)
    assert help_dlg.windowTitle() == "CLI Commands Reference - NextBoot"
    win.close()


def test_shell_scripts_syntax():
    for script in ("install.sh", "uninstall.sh", "nextboot-helper.sh", "completions/nboot.bash"):
        res = subprocess.run(["bash", "-n", str(ROOT_DIR / script)], capture_output=True, text=True, check=False)
        assert res.returncode == 0, f"{script} syntax error: {res.stderr}"
