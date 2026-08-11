from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from emulation.profiles import load_inventory, load_profile, preflight, render_fs_uae


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    assets = tmp_path / "assets with spaces"
    assets.mkdir()
    rom = assets / "synthetic kickstart.rom"
    disk = assets / "synthetic system.adf"
    work = assets / "work state"
    rom.write_bytes(b"synthetic fixture rom; no Amiga content")
    disk.write_bytes(b"synthetic fixture disk; no Amiga content")
    work.mkdir()
    inventory = {
        "schema_version": 1,
        "assets": [
            {"id": "test-rom", "kind": "kickstart", "path": str(rom), "sha256": sha256(rom.read_bytes()).hexdigest()},
            {"id": "test-system", "kind": "system-disk", "path": str(disk), "sha256": sha256(disk.read_bytes()).hexdigest(), "trust_zone": "mutable-workstation-state"},
            {"id": "test-work", "kind": "directory", "path": str(work), "trust_zone": "mutable-workstation-state"},
        ],
    }
    profile = {
        "schema_version": 1, "id": "test-a1200", "name": "Synthetic A1200", "machine": "A1200", "cpu": "68020", "chipset": "AGA",
        "memory": {"chip_mb": 2, "fast_mb": 8}, "kickstart_asset": "test-rom", "system_disk": {"asset": "test-system", "trust_zone": "mutable-workstation-state", "writable": True},
        "display": {"fullscreen": False, "scaling": "auto"}, "sound": {"enabled": True}, "input": {"mouse_integration": True},
        "media": [], "mounts": [{"id": "work", "device": "work", "source_asset": "test-work", "trust_zone": "mutable-workstation-state", "writable": True, "volume": "Work"}],
        "launch": {"mode": "windowed"}, "runtime": {"config_dir": "config", "state_dir": "state"}, "capabilities": [], "notes": "synthetic",
    }
    return _write_json(tmp_path / "profile.json", profile), _write_json(tmp_path / "inventory.json", inventory), tmp_path / "runtime"


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_valid_synthetic_profile_and_writable_mutable_mount(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    _, _, result = preflight(profile_path, inventory_path, runtime)
    assert result.launchable
    assert result.mounts[0]["writable"] is True
    assert all(asset.hash_status == "verified" for asset in result.assets if asset.kind != "directory")
    assert not runtime.exists(), "preflight must remain read-only"


def test_missing_asset_is_actionable(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    inventory = json.loads(inventory_path.read_text())
    inventory["assets"] = [item for item in inventory["assets"] if item["id"] != "test-rom"]
    _write_json(inventory_path, inventory)
    assert "missing-asset-reference" in _codes(preflight(profile_path, inventory_path, runtime)[2])


def test_hash_mismatch_fails(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    inventory = json.loads(inventory_path.read_text())
    inventory["assets"][0]["sha256"] = "0" * 64
    _write_json(inventory_path, inventory)
    assert "hash-mismatch" in _codes(preflight(profile_path, inventory_path, runtime)[2])


def test_writable_preservation_original_fails(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    profile = json.loads(profile_path.read_text())
    profile["mounts"][0]["trust_zone"] = "preservation-original"
    inventory = json.loads(inventory_path.read_text())
    inventory["assets"][2]["trust_zone"] = "preservation-original"
    _write_json(profile_path, profile); _write_json(inventory_path, inventory)
    assert "trust-zone-write" in _codes(preflight(profile_path, inventory_path, runtime)[2])


def test_unknown_zone_and_inventory_zone_mismatch_fail(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    profile = json.loads(profile_path.read_text())
    profile["mounts"][0]["trust_zone"] = "mystery"
    _write_json(profile_path, profile)
    codes = _codes(preflight(profile_path, inventory_path, runtime)[2])
    assert {"unknown-trust-zone", "trust-zone-mismatch"} <= codes


def test_duplicate_mount_device_fails(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    profile = json.loads(profile_path.read_text())
    duplicate = dict(profile["mounts"][0]); duplicate["id"] = "other"
    profile["mounts"].append(duplicate)
    _write_json(profile_path, profile)
    assert "duplicate-device" in _codes(preflight(profile_path, inventory_path, runtime)[2])


def test_duplicate_inventory_id_fails_as_ambiguous(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    inventory = json.loads(inventory_path.read_text())
    inventory["assets"].append(dict(inventory["assets"][0]))
    _write_json(inventory_path, inventory)
    assert "duplicate-asset" in _codes(preflight(profile_path, inventory_path, runtime)[2])


def test_rendering_is_deterministic_and_explicitly_read_only(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    profile, assets, result = preflight(profile_path, inventory_path, runtime)
    assert profile is not None and result.launchable
    first = render_fs_uae(profile, assets, Path(result.runtime_path))
    second = render_fs_uae(profile, assets, Path(result.runtime_path))
    assert first.encode() == second.encode()
    assert "hard_drive_0_read_only = 0" in first
    assert "writable_floppy_images = 1" in first
    assert "uae_sound_output = exact" in first
    assert f"state_dir = {runtime / 'state'}" in first
    assert "assets with spaces" in first
    assert first.splitlines()[1:] == sorted(first.splitlines()[1:])


def test_launch_refuses_invalid_profile_without_invoking_emulator(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    Path(json.loads(inventory_path.read_text())["assets"][0]["path"]).unlink()
    command = [sys.executable, "scripts/amigalab.py", "profile-launch", str(profile_path), "--inventory", str(inventory_path), "--runtime-root", str(runtime), "--fs-uae", "/definitely/not/run"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)
    assert completed.returncode == 2
    assert not runtime.exists()


def test_dry_run_uses_argument_array_and_writes_generated_config(tmp_path: Path) -> None:
    profile_path, inventory_path, runtime = _fixture(tmp_path)
    command = [sys.executable, "scripts/amigalab.py", "profile-launch", str(profile_path), "--inventory", str(inventory_path), "--runtime-root", str(runtime), "--fs-uae", "fs-uae synthetic", "--dry-run"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert '["fs-uae synthetic", ' in completed.stdout
    assert (runtime / "config" / "test-a1200.fs-uae").is_file()


def test_tracked_example_profile_loads_without_unknown_fields() -> None:
    root = Path(__file__).resolve().parents[1]
    profile, issues = load_profile(root / "profiles" / "example-a1200.json")
    assert profile is not None
    assert not issues
    _, inventory_issues = load_inventory(root / "config" / "assets.example.json")
    assert not inventory_issues
