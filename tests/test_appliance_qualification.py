from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from emulation.appliance import ApplianceConfig
from emulation.qualification import FAIL, HUMAN_REQUIRED, PASS, SKIP, qualification_report


def _observation(*, fs_uae: bool = True, x11: bool = True, audio: bool = True,
                 controller: bool = False, permissions: bool = True) -> dict[str, object]:
    devices = [
        {"name": "Synthetic Keyboard", "handlers": ["kbd", "event0"], "identity": "Bus=0003 Vendor=0001 Product=0001"},
        {"name": "Synthetic Mouse", "handlers": ["mouse0", "event1"], "identity": "Bus=0003 Vendor=0002 Product=0002"},
    ]
    if controller:
        devices.append({"name": "Stable Test Pad", "handlers": ["js0", "event2"],
                        "identity": "Bus=0003 Vendor=1234 Product=5678"})
    groups = ["audio", "input", "video"] if permissions else ["video"]
    return {
        "observed_at": "2026-08-11T10:00:00+00:00",
        "host": {"node": "test-host", "system": "Linux", "release": "test", "machine": "x86_64"},
        "appliance_user": {"exists": True, "user": "amigalab-appliance", "uid": 1001, "gid": 1001, "groups": groups},
        "fs_uae": {"path": "/usr/bin/fs-uae" if fs_uae else None,
                   "version_probe": {"returncode": 0, "output": "FS-UAE test"} if fs_uae else None,
                   "joystick_probe": {"returncode": 0, "output": "Stable Test Pad"} if fs_uae else None},
        "x11": {"lightdm_path": "/usr/sbin/lightdm" if x11 else None, "xorg_path": "/usr/bin/Xorg" if x11 else None,
                "session_file": x11, "lightdm_config": x11, "display": ":0" if x11 else None, "xauthority": "/run/test",
                "lightdm_service": {"active": "active", "enabled": "enabled"}},
        "audio": {"backend": "pipewire" if audio else None, "probe": {"returncode": 0 if audio else 1},
                  "device_nodes": ["/dev/snd/controlC0"] if audio else [],
                  "readable_nodes": ["/dev/snd/controlC0"] if audio and permissions else [],
                  "note": "synthetic"},
        "input": {"devices": devices, "device_nodes": ["/dev/input/event0", "/dev/input/event1"],
                  "readable_nodes": ["/dev/input/event0", "/dev/input/event1"] if permissions else []},
        "runtime": {"path": "/var/lib/amigalab-appliance/runtime", "exists": True,
                    "checked_path": "/var/lib/amigalab-appliance/runtime", "writable_by_appliance_user": permissions},
        "recovery": {"tty2_device": True, "getty_template": True,
                     "ssh": {"detectable": True, "active": "inactive-or-unavailable", "enabled": "disabled-or-unavailable"}},
        "removable_media": {"detectable": True, "devices": [{"name": "sdb", "tran": "usb", "rm": True}]},
        "session": {"lock": {"status": "none", "metadata": None}, "active_session": None,
                    "stale_or_incomplete": False, "most_recent_session": None},
    }


def _readiness(*, safe: bool = True) -> dict[str, object]:
    return {"ready": True, "issues": [], "profile_preflight": {"launchable": True, "mounts": [
        {"id": "work", "writable": True,
         "trust_zone": "mutable-workstation-state" if safe else "preservation-original"}
    ]}}


def _checks(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["id"]: item for item in report["checks"]}


def test_valid_synthetic_result_separates_automated_and_human_status() -> None:
    report = qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(), _observation(controller=True))
    checks = _checks(report)
    assert report["automated_ready"] is True
    assert report["hardware_qualified"] is False
    assert checks["fs-uae"]["status"] == PASS
    assert checks["fs-uae-version"]["status"] == PASS
    assert checks["controller-visibility"]["status"] == PASS
    assert checks["fs-uae-controller-discovery"]["status"] == PASS
    assert checks["paula-audio"]["status"] == HUMAN_REQUIRED
    assert report["status"] == "M3.0 implementation complete; hardware qualification pending"


def test_missing_fs_uae_x11_audio_and_permissions_are_deterministic_failures() -> None:
    report = qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(),
                                  _observation(fs_uae=False, x11=False, audio=False, permissions=False))
    checks = _checks(report)
    assert {checks[key]["status"] for key in ("fs-uae", "x11-lightdm-prerequisites", "audio-visibility",
                                               "input-device-permissions", "appliance-user-permissions",
                                               "runtime-writable")} == {FAIL}
    assert report["automated_ready"] is False


def test_visible_audio_device_permission_failure_is_reported() -> None:
    report = qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(),
                                  _observation(audio=True, permissions=False))
    assert _checks(report)["audio-device-permissions"]["status"] == FAIL


def test_absent_controller_is_optional_but_present_controller_needs_human_use_check() -> None:
    absent = _checks(qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(), _observation()))
    present = _checks(qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(), _observation(controller=True)))
    assert absent["controller-visibility"]["status"] == SKIP and absent["controller-use"]["status"] == SKIP
    assert present["controller-visibility"]["status"] == PASS and present["controller-use"]["status"] == HUMAN_REQUIRED
    assert present["fs-uae-controller-discovery"]["status"] == PASS


def test_malformed_config_and_unsafe_trust_zone_fail_closed() -> None:
    malformed = qualification_report(None, "invalid appliance configuration: bad JSON", None, _observation())
    unsafe = qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(safe=False), _observation())
    assert _checks(malformed)["appliance-config"]["status"] == FAIL
    assert _checks(unsafe)["preservation-zone-safety"]["status"] == FAIL


def test_removable_media_is_observed_without_becoming_an_amiga_mount() -> None:
    report = qualification_report(ApplianceConfig(1, True, "daily"), None, _readiness(), _observation())
    check = _checks(report)["removable-media-policy"]
    assert check["status"] == PASS
    assert "host-only" in check["evidence"]
    assert check["details"]["devices"][0]["tran"] == "usb"


def test_cli_json_is_valid_even_for_malformed_configuration(tmp_path: Path) -> None:
    config = tmp_path / "appliance.json"
    config.write_text("{not json", encoding="utf-8")
    completed = subprocess.run([
        sys.executable, "scripts/amigalab.py", "appliance-qualify", "--config", str(config),
        "--runtime-root", str(tmp_path / "runtime"), "--fs-uae", "definitely-missing", "--json",
    ], cwd=ROOT, capture_output=True, text=True, check=False)
    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert report["schema_version"] == 1
    assert _checks(report)["appliance-config"]["status"] == FAIL
