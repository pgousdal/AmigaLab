"""Local boot-appliance intent and read-only readiness checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from .profiles import preflight


APPLIANCE_SCHEMA_VERSION = 1
PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class ApplianceConfig:
    schema_version: int
    enabled: bool
    profile_id: str
    session_mode: str = "fullscreen"
    restart_policy: str = "none"
    graphical_session: str = "lightdm-x11"
    startup_delay_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_appliance_config(path: Path, *, missing_ok: bool = False) -> ApplianceConfig:
    if missing_ok and not path.is_file():
        return ApplianceConfig(APPLIANCE_SCHEMA_VERSION, False, "")
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version", "enabled", "profile_id", "session_mode", "restart_policy",
                "graphical_session", "startup_delay_seconds"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("appliance configuration has missing or unknown fields")
    config = ApplianceConfig(**value)
    if config.schema_version != APPLIANCE_SCHEMA_VERSION:
        raise ValueError("unsupported appliance configuration schema")
    if not isinstance(config.enabled, bool):
        raise ValueError("enabled must be boolean")
    if config.profile_id and not PROFILE_ID.fullmatch(config.profile_id):
        raise ValueError("profile_id must be a canonical lower-case profile ID")
    if config.enabled and not config.profile_id:
        raise ValueError("enabled appliance configuration requires profile_id")
    if config.session_mode != "fullscreen" or config.restart_policy != "none":
        raise ValueError("M3.0.3 supports only fullscreen mode with no restart")
    if config.graphical_session != "lightdm-x11" or config.startup_delay_seconds != 0:
        raise ValueError("unsupported graphical session or startup delay")
    return config


def save_appliance_config(path: Path, config: ApplianceConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def appliance_check(config: ApplianceConfig, repository: Path, inventory: Path,
                    runtime_root: Path, executable: str = "fs-uae") -> dict[str, Any]:
    profile_path = repository / "profiles" / f"{config.profile_id}.json" if config.profile_id else None
    result: dict[str, Any] = {
        "enabled": config.enabled, "profile_id": config.profile_id or None,
        "session_mode": config.session_mode, "restart_policy": config.restart_policy,
        "graphical_session": config.graphical_session,
        "service": "amigalab-appliance.service (systemd user unit; Restart=no)",
        "runtime_user": "amigalab-appliance", "fs_uae": shutil.which(executable),
        "profile_preflight": None, "ready": False,
        "recovery": ["Ctrl-Alt-F2 then log in", "SSH if independently configured", "appliance-disable then reconcile Ansible"],
    }
    if profile_path is None or not profile_path.is_file():
        result["issues"] = ["selected canonical profile does not exist"]
        return result
    profile, _, checked = preflight(profile_path, inventory, runtime_root)
    result["profile_preflight"] = checked.to_dict()
    issues = []
    if not checked.launchable:
        issues.append("profile preflight failed")
    try:
        inventory_value = json.loads(inventory.read_text(encoding="utf-8"))
        if any(not Path(item.get("path", "")).is_absolute() for item in inventory_value.get("assets", ())):
            issues.append("appliance inventory paths must be absolute so Ansible deployment preserves their meaning")
    except (OSError, TypeError, json.JSONDecodeError):
        pass  # Preflight already reports the actionable inventory error.
    if profile is not None and (profile.launch["mode"] != "fullscreen" or not profile.display["fullscreen"]):
        issues.append("selected profile is not declared fullscreen")
    if result["fs_uae"] is None:
        issues.append(f"FS-UAE executable not found: {executable}")
    result["issues"] = issues
    result["ready"] = not issues
    return result
