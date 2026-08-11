from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from emulation.appliance import ApplianceConfig, appliance_check, load_appliance_config, save_appliance_config


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repo"
    (repository / "profiles").mkdir(parents=True)
    rom = tmp_path / "synthetic.rom"; rom.write_bytes(b"not proprietary")
    inventory = tmp_path / "assets.json"
    inventory.write_text(json.dumps({"schema_version": 1, "assets": [{"id": "rom", "kind": "kickstart", "path": str(rom), "sha256": sha256(rom.read_bytes()).hexdigest()}]}))
    profile = {"schema_version": 1, "id": "safe-profile", "name": "Synthetic", "machine": "A500", "cpu": "68000", "chipset": "OCS",
               "memory": {"chip_mb": 1, "fast_mb": 0}, "kickstart_asset": "rom", "system_disk": None,
               "display": {"fullscreen": True, "scaling": "auto"}, "sound": {"enabled": True}, "input": {"mouse_integration": True},
               "media": [], "mounts": [], "launch": {"mode": "fullscreen"}, "runtime": {"config_dir": "config", "state_dir": "state"}}
    (repository / "profiles" / "safe-profile.json").write_text(json.dumps(profile))
    return repository, inventory


def test_valid_config_round_trip_and_enable_disable_state(tmp_path: Path) -> None:
    path = tmp_path / "appliance.json"
    enabled = ApplianceConfig(1, True, "safe-profile")
    save_appliance_config(path, enabled)
    assert load_appliance_config(path) == enabled
    save_appliance_config(path, ApplianceConfig(1, False, enabled.profile_id))
    assert not load_appliance_config(path).enabled


@pytest.mark.parametrize("profile", ["../escape", "UPPER", "bad profile", "/absolute"])
def test_invalid_profile_id_rejected(tmp_path: Path, profile: str) -> None:
    path = tmp_path / "bad.json"
    value = ApplianceConfig(1, True, profile).to_dict()
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="profile_id"):
        load_appliance_config(path)


def test_check_reports_missing_profile_inventory_emulator_and_valid_readiness(tmp_path: Path) -> None:
    repository, inventory = _fixture(tmp_path)
    missing = appliance_check(ApplianceConfig(1, True, "missing"), repository, inventory, tmp_path / "run", "missing-fs-uae")
    assert not missing["ready"] and "does not exist" in missing["issues"][0]
    report = appliance_check(ApplianceConfig(1, True, "safe-profile"), repository, inventory, tmp_path / "run", "/bin/true")
    assert report["ready"] and report["restart_policy"] == "none"
    inventory.unlink()
    report = appliance_check(ApplianceConfig(1, True, "safe-profile"), repository, inventory, tmp_path / "run", "/bin/true")
    assert not report["ready"] and not report["profile_preflight"]["launchable"]


def test_generated_host_configuration_is_fixed_unprivileged_and_recoverable() -> None:
    unit = (ROOT / "ansible/roles/emulation/templates/amigalab-appliance.service.j2").read_text()
    lightdm = (ROOT / "ansible/roles/emulation/templates/lightdm-amigalab.conf.j2").read_text()
    tasks = (ROOT / "ansible/roles/emulation/tasks/main.yml").read_text()
    assert "appliance-run" in unit and "scripts/amigalab.py" in unit
    assert "Restart=no" in unit and "StartLimitIntervalSec=0" in unit
    assert "User=root" not in unit and "sudo" not in unit
    assert "autologin-user=root" not in lightdm
    assert "getty" not in tasks and "SSH" not in tasks and "sshd" not in tasks
    assert "50-amigalab-appliance.conf" in tasks and "state: absent" in tasks


def test_local_config_ignored_and_tracked_host_config_has_no_asset_paths() -> None:
    ignored = subprocess.run(["git", "check-ignore", "config/appliance.local.json"], cwd=ROOT, capture_output=True).returncode
    assert ignored == 0
    tracked = "\n".join(path.read_text(errors="ignore") for path in (ROOT / "ansible/roles/emulation").rglob("*") if path.is_file())
    assert "/home/" not in tracked and "kickstart" not in tracked.lower()
