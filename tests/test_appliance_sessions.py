from __future__ import annotations

from hashlib import sha256
import fcntl
import json
from pathlib import Path
import stat
import subprocess
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from emulation.sessions import SessionConflict, SessionStore, launch_session, plan_session, session_status


def _json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path, *, fullscreen: bool = True) -> tuple[Path, Path, Path]:
    assets = tmp_path / "lawful synthetic assets with spaces"
    assets.mkdir()
    rom = assets / "test rom.bin"
    disk = assets / "test disk.adf"
    work = assets / "mutable work"
    rom.write_bytes(b"synthetic rom fixture")
    disk.write_bytes(b"synthetic disk fixture")
    work.mkdir()
    inventory = _json(tmp_path / "inventory.json", {"schema_version": 1, "assets": [
        {"id": "rom", "kind": "kickstart", "path": str(rom), "sha256": sha256(rom.read_bytes()).hexdigest()},
        {"id": "disk", "kind": "system-disk", "path": str(disk), "sha256": sha256(disk.read_bytes()).hexdigest(), "trust_zone": "mutable-workstation-state"},
        {"id": "work", "kind": "directory", "path": str(work), "trust_zone": "mutable-workstation-state"},
    ]})
    profile = _json(tmp_path / "profile.json", {
        "schema_version": 1, "id": "test-appliance", "name": "Synthetic appliance", "machine": "A1200", "cpu": "68020", "chipset": "AGA",
        "memory": {"chip_mb": 2, "fast_mb": 8}, "kickstart_asset": "rom",
        "system_disk": {"asset": "disk", "trust_zone": "mutable-workstation-state", "writable": True},
        "display": {"fullscreen": fullscreen, "scaling": "auto"}, "sound": {"enabled": True}, "input": {"mouse_integration": True},
        "media": [], "mounts": [{"id": "work", "device": "work", "source_asset": "work", "trust_zone": "mutable-workstation-state", "writable": True}],
        "launch": {"mode": "fullscreen" if fullscreen else "windowed"}, "runtime": {"config_dir": "config", "state_dir": "state"},
    })
    return profile, inventory, tmp_path / "runtime with spaces"


def _emulator(tmp_path: Path, code: int = 0) -> Path:
    path = tmp_path / "fake emulator with spaces"
    path.write_text(f"#!/bin/sh\nprintf 'fake stdout\\n'\nprintf 'fake stderr\\n' >&2\nexit {code}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_successful_isolated_fullscreen_session_and_persisted_exit(tmp_path: Path) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    plan = plan_session(profile, inventory, runtime, str(_emulator(tmp_path)), "20260101T000000000000Z-1-abcdef")
    state = launch_session(plan, runtime)
    assert state.state == "exited" and state.exit_code == 0 and not state.abnormal_exit
    assert state.pid is None and state.cleanup_status == "complete"
    assert plan.session_dir == runtime / "sessions" / plan.session_id
    assert "fullscreen = 1" in plan.config_path.read_text(encoding="utf-8")
    assert Path(state.emulator_log).read_text(encoding="utf-8") == "fake stdout\nfake stderr\n"
    assert SessionStore(runtime).load(plan.session_id).exit_code == 0
    assert session_status(runtime)["active_session"] is None
    assert session_status(runtime)["lock"]["status"] == "none"


def test_failed_preflight_and_dry_plan_create_no_runtime(tmp_path: Path) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    data = json.loads(inventory.read_text(encoding="utf-8"))
    data["assets"][0]["path"] = str(tmp_path / "missing")
    _json(inventory, data)
    plan = plan_session(profile, inventory, runtime, "must-not-run", "20260101T000000000000Z-1-abcdef")
    assert not plan.preflight.launchable
    with pytest.raises(ValueError, match="preflight failed"):
        launch_session(plan, runtime)
    assert not runtime.exists()


def test_nonzero_exit_survives_for_inspection(tmp_path: Path) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    state = launch_session(plan_session(profile, inventory, runtime, str(_emulator(tmp_path, 7))), runtime)
    assert state.state == "failed" and state.exit_code == 7
    assert state.termination_reason == "non-zero-exit" and state.abnormal_exit
    assert Path(state.lifecycle_log).is_file()


def test_single_session_lock_and_stale_metadata_recovery(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    store = SessionStore(runtime)
    held = store.acquire("held-session")
    try:
        assert store.lock_status()["status"] == "active"
        with pytest.raises(SessionConflict):
            store.acquire("second-session")
    finally:
        fcntl.flock(held, fcntl.LOCK_UN)
        held.close()
    assert store.lock_status()["status"] == "stale"
    recovered = store.acquire("recovered-session")
    recovered.close()


def test_session_status_inspects_stale_lock_without_write_access(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    lock = runtime / "appliance.lock"
    lock.write_text('{"session_id": "prior-session"}\n', encoding="utf-8")
    lock.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    before = lock.read_bytes()
    assert session_status(runtime)["lock"]["status"] == "stale"
    assert lock.read_bytes() == before


def test_invalid_transition_fails(tmp_path: Path) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    state = launch_session(plan_session(profile, inventory, runtime, str(_emulator(tmp_path))), runtime)
    with pytest.raises(ValueError, match="invalid appliance session transition"):
        SessionStore(runtime).transition(state, "running")


def test_interrupt_terminates_child_and_persists_coherent_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    emulator = _emulator(tmp_path)
    import emulation.sessions as sessions
    real_popen = sessions.subprocess.Popen

    class InterruptOnce:
        def __init__(self, *args, **kwargs):
            self.process = real_popen(*args, **kwargs)
            self.pid = self.process.pid
            self.stdout = self.process.stdout
            self.first = True

        def wait(self, *args, **kwargs):
            if self.first:
                self.first = False
                raise KeyboardInterrupt
            return self.process.wait(*args, **kwargs)

        def terminate(self):
            return self.process.terminate()

        def kill(self):
            return self.process.kill()

        def poll(self):
            return self.process.poll()

    monkeypatch.setattr(sessions.subprocess, "Popen", InterruptOnce)
    state = launch_session(plan_session(profile, inventory, runtime, str(emulator)), runtime, terminate_timeout=1)
    assert state.state == "interrupted" and state.pid is None
    assert state.termination_reason == "operator-interrupt"


def test_runtime_inside_read_only_directory_is_rejected(tmp_path: Path) -> None:
    profile, inventory, _ = _fixture(tmp_path)
    preserved = tmp_path / "preserved"
    preserved.mkdir()
    data = json.loads(inventory.read_text(encoding="utf-8"))
    data["assets"].append({"id": "library", "kind": "directory", "path": str(preserved), "trust_zone": "amiga-library-export"})
    profile_data = json.loads(profile.read_text(encoding="utf-8"))
    profile_data["mounts"].append({"id": "library", "device": "library", "source_asset": "library", "trust_zone": "amiga-library-export", "writable": False})
    _json(inventory, data); _json(profile, profile_data)
    plan = plan_session(profile, inventory, preserved / "runtime", str(_emulator(tmp_path)))
    with pytest.raises(ValueError, match="preservation zone"):
        launch_session(plan, preserved / "runtime")
    assert not (preserved / "runtime").exists()


def test_session_dry_run_does_not_create_state_or_execute(tmp_path: Path) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    marker = tmp_path / "executed"
    emulator = tmp_path / "fake"
    emulator.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    emulator.chmod(emulator.stat().st_mode | stat.S_IXUSR)
    command = [sys.executable, "scripts/amigalab.py", "session-launch", str(profile), "--inventory", str(inventory),
               "--runtime-root", str(runtime), "--fs-uae", str(emulator), "--dry-run"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)
    assert completed.returncode == 0
    assert "Session directory:" in completed.stdout and "Command:" in completed.stdout
    assert not marker.exists() and not runtime.exists()


def test_missing_emulator_creates_no_session(tmp_path: Path) -> None:
    profile, inventory, runtime = _fixture(tmp_path)
    command = [sys.executable, "scripts/amigalab.py", "session-launch", str(profile), "--inventory", str(inventory),
               "--runtime-root", str(runtime), "--fs-uae", "definitely-not-an-emulator"]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)
    assert completed.returncode == 3
    assert "executable not found" in completed.stderr
    assert not runtime.exists()
