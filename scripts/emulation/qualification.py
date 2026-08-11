"""Read-only host observations and deterministic M3.0 qualification results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import grp
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import stat
import subprocess
from typing import Any, Iterable

from .appliance import ApplianceConfig
from .sessions import session_status


QUALIFICATION_SCHEMA_VERSION = 1
PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
HUMAN_REQUIRED = "HUMAN_REQUIRED"


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    evidence: str
    automated: bool = True
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(argv: list[str]) -> dict[str, Any]:
    """Run a bounded, read-only observation command."""
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"argv": argv, "available": False, "returncode": None, "output": str(error)}
    output = (completed.stdout or completed.stderr).strip()
    return {"argv": argv, "available": True, "returncode": completed.returncode, "output": output[:4096]}


def _command(name: str) -> str | None:
    return shutil.which(name)


def _service_state(unit: str, *, user: bool = False) -> dict[str, Any]:
    executable = _command("systemctl")
    if not executable:
        return {"detectable": False, "unit": unit, "active": None, "enabled": None}
    prefix = [executable] + (["--user"] if user else [])
    active = _run(prefix + ["is-active", unit])
    enabled = _run(prefix + ["is-enabled", unit])
    return {
        "detectable": True,
        "unit": unit,
        "active": active["output"] if active["returncode"] == 0 else "inactive-or-unavailable",
        "enabled": enabled["output"] if enabled["returncode"] == 0 else "disabled-or-unavailable",
    }


def _input_devices(path: Path = Path("/proc/bus/input/devices")) -> list[dict[str, Any]]:
    try:
        blocks = path.read_text(encoding="utf-8", errors="replace").split("\n\n")
    except OSError:
        return []
    devices = []
    for block in blocks:
        if not block.strip():
            continue
        lines = block.splitlines()
        name = next((line.split("Name=", 1)[1].strip('"') for line in lines if "Name=" in line), "unknown")
        handlers = next((line.split("Handlers=", 1)[1].split() for line in lines if "Handlers=" in line), [])
        identity = next((line[3:] for line in lines if line.startswith("I: ")), "")
        devices.append({"name": name, "handlers": handlers, "identity": identity})
    return devices


def _device_nodes(devices: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({f"/dev/input/{handler}" for device in devices for handler in device["handlers"] if handler.startswith(("event", "js"))})


def _identity(user: str) -> dict[str, Any]:
    try:
        account = pwd.getpwnam(user)
    except KeyError:
        return {"exists": False, "user": user, "uid": None, "groups": []}
    groups = {grp.getgrgid(account.pw_gid).gr_name}
    groups.update(group.gr_name for group in grp.getgrall() if user in group.gr_mem)
    return {"exists": True, "user": user, "uid": account.pw_uid, "gid": account.pw_gid, "groups": sorted(groups)}


def _can_access(path: Path, identity: dict[str, Any], *, write: bool = False) -> bool | None:
    if not identity["exists"]:
        return None
    try:
        info = path.stat()
    except OSError:
        return None
    directory = stat.S_ISDIR(info.st_mode)
    bits = (stat.S_IWUSR | (stat.S_IXUSR if directory else 0)) if write else stat.S_IRUSR
    if info.st_uid == identity["uid"]:
        return info.st_mode & bits == bits
    group_ids = {identity["gid"]}
    for name in identity["groups"]:
        try:
            group_ids.add(grp.getgrnam(name).gr_gid)
        except KeyError:
            pass
    bits = (stat.S_IWGRP | (stat.S_IXGRP if directory else 0)) if write else stat.S_IRGRP
    if info.st_gid in group_ids:
        return info.st_mode & bits == bits
    bits = (stat.S_IWOTH | (stat.S_IXOTH if directory else 0)) if write else stat.S_IROTH
    return info.st_mode & bits == bits


def _runtime_access(path: Path, identity: dict[str, Any]) -> dict[str, Any]:
    candidate = path.resolve(strict=False)
    existing = candidate
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    return {
        "path": str(candidate),
        "exists": candidate.is_dir(),
        "checked_path": str(existing),
        "writable_by_appliance_user": _can_access(existing, identity, write=True),
    }


def _audio_observation(identity: dict[str, Any]) -> dict[str, Any]:
    commands = {name: _command(name) for name in ("wpctl", "pactl", "aplay")}
    backend = None
    detail = None
    if commands["wpctl"]:
        backend, detail = "pipewire", _run([commands["wpctl"], "status"])
    elif commands["pactl"]:
        backend, detail = "pulseaudio-compatible", _run([commands["pactl"], "info"])
    elif commands["aplay"]:
        backend, detail = "alsa", _run([commands["aplay"], "-l"])
    nodes = sorted(str(path) for path in Path("/dev/snd").glob("*")) if Path("/dev/snd").is_dir() else []
    return {
        "backend": backend,
        "probe": detail,
        "device_nodes": nodes,
        "readable_nodes": [node for node in nodes if _can_access(Path(node), identity) is True],
        "note": "FS-UAE outputs through OpenAL; process-level playback requires human confirmation",
    }


def _removable_observation() -> dict[str, Any]:
    executable = _command("lsblk")
    if not executable:
        return {"detectable": False, "devices": []}
    result = _run([executable, "--json", "--output", "NAME,TYPE,TRAN,RM,RO,MOUNTPOINTS,VENDOR,MODEL,SERIAL"])
    devices: list[dict[str, Any]] = []
    if result["returncode"] == 0:
        try:
            value = json.loads(result["output"])
            devices = [item for item in value.get("blockdevices", []) if item.get("tran") == "usb" or item.get("rm") is True]
        except (TypeError, json.JSONDecodeError):
            pass
    return {"detectable": True, "devices": devices, "probe_returncode": result["returncode"]}


def observe_host(executable: str, runtime_root: Path, appliance_user: str = "amigalab-appliance") -> dict[str, Any]:
    """Collect host facts without creating files, changing services, or opening devices."""
    identity = _identity(appliance_user)
    fs_uae = shutil.which(executable) if not Path(executable).is_absolute() else (executable if os.access(executable, os.X_OK) else None)
    version = _run([fs_uae, "--version"]) if fs_uae else None
    joysticks = _run([fs_uae, "--list-joysticks"]) if fs_uae else None
    inputs = _input_devices()
    input_nodes = _device_nodes(inputs)
    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "host": {"node": platform.node(), "system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "appliance_user": identity,
        "fs_uae": {"path": fs_uae, "version_probe": version, "joystick_probe": joysticks},
        "x11": {
            "lightdm_path": _command("lightdm"), "xorg_path": _command("Xorg"),
            "session_file": Path("/usr/share/xsessions/amigalab-appliance.desktop").is_file(),
            "lightdm_config": Path("/etc/lightdm/lightdm.conf.d/50-amigalab-appliance.conf").is_file(),
            "display": os.environ.get("DISPLAY"), "xauthority": os.environ.get("XAUTHORITY"),
            "lightdm_service": _service_state("lightdm.service"),
        },
        "audio": _audio_observation(identity),
        "input": {
            "devices": inputs, "device_nodes": input_nodes,
            "readable_nodes": [node for node in input_nodes if _can_access(Path(node), identity) is True],
        },
        "runtime": _runtime_access(runtime_root, identity),
        "recovery": {
            "tty2_device": Path("/dev/tty2").exists(), "getty_template": Path("/lib/systemd/system/getty@.service").is_file(),
            "ssh": _service_state("ssh.service"),
        },
        "removable_media": _removable_observation(),
        "session": session_status(runtime_root),
    }


def _input_classes(devices: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "keyboard": [item for item in devices if any(value.startswith("kbd") for value in item["handlers"])],
        "mouse": [item for item in devices if any(value.startswith("mouse") for value in item["handlers"])],
        "controller": [item for item in devices if any(value.startswith("js") for value in item["handlers"])],
    }


def qualification_report(config: ApplianceConfig | None, config_error: str | None,
                         appliance: dict[str, Any] | None, observation: dict[str, Any]) -> dict[str, Any]:
    """Turn host observations into stable automated and human-required checks."""
    checks: list[Check] = []
    checks.append(Check("appliance-config", FAIL if config_error else PASS,
                        config_error or f"schema 1; enabled={config.enabled}; profile={config.profile_id or 'none'}"))
    ready = bool(appliance and appliance.get("ready"))
    checks.append(Check("profile-preflight", PASS if ready else FAIL,
                        "canonical profile and assets passed preflight" if ready else "appliance readiness/preflight failed",
                        details={"issues": appliance.get("issues", []) if appliance else []}))
    fs_uae = observation["fs_uae"]
    checks.append(Check("fs-uae", PASS if fs_uae["path"] else FAIL,
                        f"executable: {fs_uae['path'] or 'not found'}", details={"version_probe": fs_uae["version_probe"]}))
    version_ok = bool(fs_uae["version_probe"] and fs_uae["version_probe"].get("returncode") == 0 and fs_uae["version_probe"].get("output"))
    checks.append(Check("fs-uae-version", PASS if version_ok else FAIL,
                        str(fs_uae["version_probe"].get("output")) if version_ok else "FS-UAE version could not be read"))
    x11 = observation["x11"]
    x_ready = bool(x11["lightdm_path"] and x11["xorg_path"] and x11["session_file"] and x11["lightdm_config"])
    checks.append(Check("x11-lightdm-prerequisites", PASS if x_ready else FAIL,
                        "LightDM, Xorg, AmigaLab session, and managed configuration present" if x_ready else "one or more graphical prerequisites absent", details=x11))
    checks.append(Check("display-session", PASS if x11["display"] else SKIP,
                        f"DISPLAY={x11['display']}" if x11["display"] else "no DISPLAY in this diagnostic shell; inspect from graphical appliance session"))
    audio = observation["audio"]
    audio_visible = bool(audio["backend"] and (audio["device_nodes"] or audio.get("probe", {}).get("returncode") == 0))
    checks.append(Check("audio-visibility", PASS if audio_visible else FAIL,
                        f"host audio backend: {audio['backend'] or 'not detected'}", details=audio))
    audio_access = not audio["device_nodes"] or bool(audio["readable_nodes"])
    checks.append(Check("audio-device-permissions", PASS if audio_access else FAIL,
                        "audio nodes are readable by the appliance user or no direct nodes were exposed" if audio_access else "audio nodes exist but none are readable by the appliance user"))
    classes = _input_classes(observation["input"]["devices"])
    for kind in ("keyboard", "mouse"):
        visible = bool(classes[kind])
        checks.append(Check(f"{kind}-visibility", PASS if visible else FAIL,
                            f"{len(classes[kind])} Linux {kind} device(s) detected", details={"devices": classes[kind]}))
    controllers = classes["controller"]
    checks.append(Check("controller-visibility", PASS if controllers else SKIP,
                        f"{len(controllers)} Linux joystick device(s) detected" if controllers else "no optional controller present",
                        details={"devices": controllers}))
    joystick_probe = fs_uae.get("joystick_probe")
    probe_output = str(joystick_probe.get("output", "")).casefold() if joystick_probe else ""
    fs_controller_seen = bool(controllers and joystick_probe and joystick_probe.get("returncode") == 0 and any(
        str(controller["name"]).casefold() in probe_output for controller in controllers))
    checks.append(Check("fs-uae-controller-discovery",
                        PASS if fs_controller_seen else (SKIP if not controllers else FAIL),
                        "FS-UAE listed controller input" if fs_controller_seen else
                        ("no optional Linux controller present" if not controllers else "Linux sees a controller but FS-UAE did not list one"),
                        details={"probe": joystick_probe}))
    input_access = not observation["input"]["device_nodes"] or bool(observation["input"]["readable_nodes"])
    checks.append(Check("input-device-permissions", PASS if input_access else FAIL,
                        "input nodes are readable by the appliance user or no nodes were exposed" if input_access else "input nodes exist but none are readable by the appliance user"))
    identity = observation["appliance_user"]
    required_groups = {"audio", "video", "input"}
    group_ok = identity["exists"] and required_groups.issubset(set(identity["groups"]))
    checks.append(Check("appliance-user-permissions", PASS if group_ok else FAIL,
                        "dedicated user has audio, video, and input groups" if group_ok else "appliance user or required groups missing", details=identity))
    runtime = observation["runtime"]
    checks.append(Check("runtime-writable", PASS if runtime["writable_by_appliance_user"] else FAIL,
                        "runtime path (or existing parent) is writable by appliance user" if runtime["writable_by_appliance_user"] else "runtime path is not demonstrably writable by appliance user", details=runtime))
    preservation_safe = bool(appliance and appliance.get("profile_preflight") and all(
        not item["writable"] or item["trust_zone"] == "mutable-workstation-state"
        for item in appliance["profile_preflight"].get("mounts", [])))
    checks.append(Check("preservation-zone-safety", PASS if preservation_safe else FAIL,
                        "all reported writable mounts are mutable workstation state" if preservation_safe else "preflight did not establish safe writable mounts"))
    recovery = observation["recovery"]
    tty = recovery["tty2_device"] and recovery["getty_template"]
    checks.append(Check("recovery-tty", PASS if tty else FAIL,
                        "TTY2 device and getty unit template detected" if tty else "expected TTY2/getty prerequisite absent", details=recovery))
    checks.append(Check("ssh-information", SKIP, "SSH is informational and independently configured", details=recovery["ssh"]))
    checks.append(Check("appliance-session-state", PASS, "active/recent state inspected", details=observation["session"]))
    checks.append(Check("removable-media-policy", PASS,
                        "removable media is host-only unless explicitly represented by a canonical inventory asset and profile mount",
                        details=observation["removable_media"]))
    for check_id, evidence in (
        ("cold-boot", "reboot and automatic profile launch must be observed"),
        ("fullscreen-display", "fullscreen image, ownership, resolution, and return behavior require visual confirmation"),
        ("paula-audio", "audible emulator output must be heard; visibility alone is insufficient"),
        ("keyboard-use", "Amiga key input, reserved shortcuts, and Ctrl-Alt-F2 recovery require confirmation"),
        ("mouse-use", "Amiga pointer movement, buttons, capture, and release require confirmation"),
        ("controller-use", "if a controller is present, FS-UAE discovery and in-Amiga use require confirmation"),
        ("clean-exit", "normal FS-UAE exit and recovery console require confirmation"),
        ("controlled-interruption", "systemd stop and coherent interrupted session state require confirmation"),
        ("reboot-repeat", "a second successful startup after reboot requires confirmation"),
        ("safe-failure-recovery", "one intentionally unavailable dependency and TTY recovery require confirmation"),
    ):
        status = SKIP if check_id == "controller-use" and not controllers else HUMAN_REQUIRED
        checks.append(Check(check_id, status, evidence, automated=False))
    counts = {status: sum(item.status == status for item in checks) for status in (PASS, FAIL, SKIP, HUMAN_REQUIRED)}
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "generated_at": observation["observed_at"],
        "profile_id": config.profile_id if config else None,
        "host": observation["host"],
        "summary": counts,
        "automated_ready": counts[FAIL] == 0,
        "hardware_qualified": False,
        "status": "M3.0 implementation complete; hardware qualification pending",
        "checks": [item.to_dict() for item in checks],
    }
