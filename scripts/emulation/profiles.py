"""Load, validate, preflight, and render canonical FS-UAE profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = 1
TRUST_ZONES = {
    "preservation-original",
    "canonical-derived",
    "amiga-library-export",
    "mutable-workstation-state",
}
READ_ONLY_ZONES = {
    "preservation-original",
    "canonical-derived",
    "amiga-library-export",
}
SUPPORTED_MACHINES = {"A500", "A600", "A1200", "A3000", "A4000"}
SUPPORTED_CPU = {"68000", "68010", "68020", "68030", "68040", "68060"}
SUPPORTED_CHIPSET = {"OCS", "ECS", "AGA"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class Asset:
    id: str
    kind: str
    path: Path
    sha256: str | None = None
    trust_zone: str | None = None


@dataclass(frozen=True)
class Mount:
    id: str
    device: str
    source_asset: str
    trust_zone: str
    writable: bool
    volume: str = ""


@dataclass(frozen=True)
class Profile:
    schema_version: int
    id: str
    name: str
    machine: str
    cpu: str
    chipset: str
    chip_ram_mb: int
    fast_ram_mb: int
    kickstart_asset: str
    system_disk: dict[str, Any] | None
    display: dict[str, Any]
    sound: dict[str, Any]
    input: dict[str, Any]
    media: tuple[dict[str, Any], ...]
    mounts: tuple[Mount, ...]
    launch: dict[str, Any]
    runtime: dict[str, str]
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


@dataclass(frozen=True)
class AssetCheck:
    id: str
    kind: str
    path: str
    exists: bool
    hash_status: str
    trust_zone: str | None


@dataclass(frozen=True)
class PreflightResult:
    profile_id: str
    profile_name: str
    schema_version: int
    machine: str
    assets: tuple[AssetCheck, ...]
    mounts: tuple[dict[str, Any], ...]
    config_path: str
    runtime_path: str
    issues: tuple[ValidationIssue, ...]
    launchable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _object(value: Any, path: str, issues: list[ValidationIssue]) -> dict[str, Any]:
    if not isinstance(value, dict):
        issues.append(ValidationIssue("invalid-type", path, "must be an object"))
        return {}
    return value


def _keys(value: dict[str, Any], allowed: set[str], path: str, issues: list[ValidationIssue]) -> None:
    for key in sorted(set(value) - allowed):
        issues.append(ValidationIssue("unknown-field", f"{path}.{key}", "field is not supported"))


def _identifier(value: Any, path: str, issues: list[ValidationIssue]) -> str:
    text = value if isinstance(value, str) else ""
    if not ID_PATTERN.fullmatch(text):
        issues.append(ValidationIssue("invalid-id", path, "must match [a-z0-9][a-z0-9._-]{0,63}"))
    return text


def _string(value: Any, path: str, issues: list[ValidationIssue]) -> str:
    if not isinstance(value, str) or not value:
        issues.append(ValidationIssue("required-string", path, "must be a non-empty string"))
        return ""
    return value


def load_profile(path: Path) -> tuple[Profile | None, tuple[ValidationIssue, ...]]:
    issues: list[ValidationIssue] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, (ValidationIssue("profile-load", "$", str(error)),)
    root = _object(raw, "$", issues)
    _keys(root, {"schema_version", "id", "name", "machine", "cpu", "chipset", "memory", "kickstart_asset", "system_disk", "display", "sound", "input", "media", "mounts", "launch", "runtime", "capabilities", "notes"}, "$", issues)
    required = {"schema_version", "id", "name", "machine", "cpu", "chipset", "memory", "kickstart_asset", "display", "sound", "input", "media", "mounts", "launch", "runtime"}
    for key in sorted(required - set(root)):
        issues.append(ValidationIssue("missing-field", f"$.{key}", "field is required"))
    schema = root.get("schema_version")
    if schema != SCHEMA_VERSION:
        issues.append(ValidationIssue("schema-version", "$.schema_version", f"must be {SCHEMA_VERSION}"))
    profile_id = _identifier(root.get("id"), "$.id", issues)
    name = _string(root.get("name"), "$.name", issues)
    machine = root.get("machine", "")
    if machine not in SUPPORTED_MACHINES:
        issues.append(ValidationIssue("unsupported-machine", "$.machine", f"must be one of {sorted(SUPPORTED_MACHINES)}"))
    cpu = root.get("cpu", "")
    if cpu not in SUPPORTED_CPU:
        issues.append(ValidationIssue("unsupported-cpu", "$.cpu", f"must be one of {sorted(SUPPORTED_CPU)}"))
    chipset = root.get("chipset", "")
    if chipset not in SUPPORTED_CHIPSET:
        issues.append(ValidationIssue("unsupported-chipset", "$.chipset", f"must be one of {sorted(SUPPORTED_CHIPSET)}"))
    expected_chipsets = {"A500": {"OCS", "ECS"}, "A600": {"ECS"}, "A1200": {"AGA"}, "A3000": {"ECS"}, "A4000": {"AGA"}}
    if machine in expected_chipsets and chipset not in expected_chipsets[machine]:
        issues.append(ValidationIssue("machine-chipset-conflict", "$.chipset", f"{machine} requires one of {sorted(expected_chipsets[machine])}"))
    memory = _object(root.get("memory"), "$.memory", issues)
    _keys(memory, {"chip_mb", "fast_mb"}, "$.memory", issues)
    chip = memory.get("chip_mb")
    fast = memory.get("fast_mb")
    if not isinstance(chip, int) or isinstance(chip, bool) or chip not in {1, 2, 4, 8}:
        issues.append(ValidationIssue("invalid-memory", "$.memory.chip_mb", "must be one of 1, 2, 4, 8"))
    if not isinstance(fast, int) or isinstance(fast, bool) or fast < 0 or fast > 512:
        issues.append(ValidationIssue("invalid-memory", "$.memory.fast_mb", "must be an integer from 0 to 512"))
    kickstart = _identifier(root.get("kickstart_asset"), "$.kickstart_asset", issues)
    system_raw = root.get("system_disk")
    system = None
    if system_raw is not None:
        system_value = _object(system_raw, "$.system_disk", issues)
        _keys(system_value, {"asset", "trust_zone", "writable"}, "$.system_disk", issues)
        system = {
            "asset": _identifier(system_value.get("asset"), "$.system_disk.asset", issues),
            "trust_zone": system_value.get("trust_zone"),
            "writable": system_value.get("writable"),
        }
        _validate_zone(system["trust_zone"], system["writable"], "$.system_disk", issues)
    display = _object(root.get("display"), "$.display", issues)
    _keys(display, {"fullscreen", "scaling"}, "$.display", issues)
    if not isinstance(display.get("fullscreen"), bool):
        issues.append(ValidationIssue("invalid-display", "$.display.fullscreen", "must be boolean"))
    if display.get("scaling") not in {"auto", "integer", "none"}:
        issues.append(ValidationIssue("invalid-display", "$.display.scaling", "must be auto, integer, or none"))
    sound = _object(root.get("sound"), "$.sound", issues)
    _keys(sound, {"enabled"}, "$.sound", issues)
    if not isinstance(sound.get("enabled"), bool):
        issues.append(ValidationIssue("invalid-sound", "$.sound.enabled", "must be boolean"))
    input_ = _object(root.get("input"), "$.input", issues)
    _keys(input_, {"mouse_integration"}, "$.input", issues)
    if not isinstance(input_.get("mouse_integration"), bool):
        issues.append(ValidationIssue("invalid-input", "$.input.mouse_integration", "must be boolean"))
    launch = _object(root.get("launch"), "$.launch", issues)
    _keys(launch, {"mode"}, "$.launch", issues)
    if launch.get("mode") not in {"windowed", "fullscreen"}:
        issues.append(ValidationIssue("invalid-launch", "$.launch.mode", "must be windowed or fullscreen"))
    if isinstance(display.get("fullscreen"), bool) and launch.get("mode") in {"windowed", "fullscreen"} and display["fullscreen"] != (launch["mode"] == "fullscreen"):
        issues.append(ValidationIssue("contradictory-launch", "$.launch.mode", "must agree with display.fullscreen"))
    runtime = _object(root.get("runtime"), "$.runtime", issues)
    _keys(runtime, {"config_dir", "state_dir"}, "$.runtime", issues)
    for key in ("config_dir", "state_dir"):
        value = runtime.get(key)
        if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
            issues.append(ValidationIssue("unsafe-runtime-path", f"$.runtime.{key}", "must be a single stable relative path component"))
    raw_media = root.get("media", [])
    media: list[dict[str, Any]] = []
    if not isinstance(raw_media, list):
        issues.append(ValidationIssue("invalid-type", "$.media", "must be an array"))
    else:
        seen_media: set[tuple[str, int]] = set()
        for index, item_raw in enumerate(raw_media):
            item = _object(item_raw, f"$.media[{index}]", issues)
            _keys(item, {"type", "drive", "asset", "trust_zone", "writable"}, f"$.media[{index}]", issues)
            kind, drive = item.get("type"), item.get("drive")
            if kind not in {"floppy", "cd"} or not isinstance(drive, int) or isinstance(drive, bool) or drive < 0 or drive > 3:
                issues.append(ValidationIssue("invalid-media-device", f"$.media[{index}]", "type must be floppy or cd and drive must be 0..3"))
            elif (kind, drive) in seen_media:
                issues.append(ValidationIssue("duplicate-device", f"$.media[{index}]", f"duplicate {kind} drive {drive}"))
            else:
                seen_media.add((kind, drive))
            asset_id = _identifier(item.get("asset"), f"$.media[{index}].asset", issues)
            zone = item.get("trust_zone")
            writable = item.get("writable")
            _validate_zone(zone, writable, f"$.media[{index}]", issues)
            media.append({"type": kind, "drive": drive, "asset": asset_id, "trust_zone": zone, "writable": writable})
    if system is not None and ("floppy", 0) in seen_media:
        issues.append(ValidationIssue("duplicate-device", "$.system_disk", "system disk and media both target floppy drive 0"))
    floppy_permissions = [bool(item["writable"]) for item in media if item["type"] == "floppy" and isinstance(item["writable"], bool)]
    if system is not None and isinstance(system["writable"], bool):
        floppy_permissions.append(system["writable"])
    if len(set(floppy_permissions)) > 1:
        issues.append(ValidationIssue("mixed-floppy-permissions", "$.media", "FS-UAE controls write-through globally; all floppy mounts must use the same writable intent"))
    for index, item in enumerate(media):
        if item["type"] == "cd" and item["writable"] is True:
            issues.append(ValidationIssue("unsupported-permission", f"$.media[{index}].writable", "FS-UAE CD media cannot be mounted writable"))
    raw_mounts = root.get("mounts", [])
    mounts: list[Mount] = []
    seen_ids: set[str] = set()
    seen_devices: set[str] = set()
    seen_volumes: set[str] = set()
    if not isinstance(raw_mounts, list):
        issues.append(ValidationIssue("invalid-type", "$.mounts", "must be an array"))
    else:
        for index, item_raw in enumerate(raw_mounts):
            item = _object(item_raw, f"$.mounts[{index}]", issues)
            _keys(item, {"id", "device", "source_asset", "trust_zone", "writable", "volume"}, f"$.mounts[{index}]", issues)
            mount_id = _identifier(item.get("id"), f"$.mounts[{index}].id", issues)
            device = _identifier(item.get("device"), f"$.mounts[{index}].device", issues)
            asset_id = _identifier(item.get("source_asset"), f"$.mounts[{index}].source_asset", issues)
            if mount_id in seen_ids:
                issues.append(ValidationIssue("duplicate-mount", f"$.mounts[{index}].id", f"duplicate mount ID {mount_id!r}"))
            if device in seen_devices:
                issues.append(ValidationIssue("duplicate-device", f"$.mounts[{index}].device", f"duplicate device {device!r}"))
            seen_ids.add(mount_id); seen_devices.add(device)
            zone, writable = item.get("trust_zone"), item.get("writable")
            _validate_zone(zone, writable, f"$.mounts[{index}]", issues)
            volume = item.get("volume", "")
            if volume and (not isinstance(volume, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,31}", volume)):
                issues.append(ValidationIssue("invalid-volume", f"$.mounts[{index}].volume", "must contain only letters, digits, underscore, or hyphen"))
            elif volume and volume.casefold() in seen_volumes:
                issues.append(ValidationIssue("destination-collision", f"$.mounts[{index}].volume", f"duplicate guest volume {volume!r}"))
            elif isinstance(volume, str) and volume:
                seen_volumes.add(volume.casefold())
            mounts.append(Mount(mount_id, device, asset_id, zone, writable, volume if isinstance(volume, str) else ""))
    capabilities_raw = root.get("capabilities", [])
    if not isinstance(capabilities_raw, list) or not all(isinstance(value, str) for value in capabilities_raw):
        issues.append(ValidationIssue("invalid-capabilities", "$.capabilities", "must be an array of strings"))
        capabilities_raw = []
    profile = Profile(schema if isinstance(schema, int) else 0, profile_id, name, machine, cpu, chipset, chip if isinstance(chip, int) else 0, fast if isinstance(fast, int) else 0, kickstart, system, display, sound, input_, tuple(media), tuple(mounts), launch, {str(k): str(v) for k, v in runtime.items()}, tuple(capabilities_raw), str(root.get("notes", "")))
    return profile, tuple(issues)


def _validate_zone(zone: Any, writable: Any, path: str, issues: list[ValidationIssue]) -> None:
    if zone not in TRUST_ZONES:
        issues.append(ValidationIssue("unknown-trust-zone", f"{path}.trust_zone", f"must be one of {sorted(TRUST_ZONES)}"))
    if not isinstance(writable, bool):
        issues.append(ValidationIssue("invalid-permission", f"{path}.writable", "must be boolean"))
    elif writable and zone in READ_ONLY_ZONES:
        issues.append(ValidationIssue("trust-zone-write", f"{path}.writable", f"{zone} may not be mounted writable"))


def load_inventory(path: Path) -> tuple[dict[str, Asset], tuple[ValidationIssue, ...]]:
    issues: list[ValidationIssue] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, (ValidationIssue("inventory-load", "$", str(error)),)
    root = _object(raw, "$", issues)
    _keys(root, {"schema_version", "assets"}, "$", issues)
    if root.get("schema_version") != 1:
        issues.append(ValidationIssue("inventory-schema-version", "$.schema_version", "must be 1"))
    raw_assets = root.get("assets", [])
    if not isinstance(raw_assets, list):
        return {}, tuple(issues + [ValidationIssue("invalid-type", "$.assets", "must be an array")])
    assets: dict[str, Asset] = {}
    for index, item_raw in enumerate(raw_assets):
        item = _object(item_raw, f"$.assets[{index}]", issues)
        _keys(item, {"id", "kind", "path", "sha256", "trust_zone"}, f"$.assets[{index}]", issues)
        asset_id = _identifier(item.get("id"), f"$.assets[{index}].id", issues)
        if asset_id in assets:
            issues.append(ValidationIssue("duplicate-asset", f"$.assets[{index}].id", f"duplicate asset ID {asset_id!r}"))
            continue
        kind = item.get("kind")
        if kind not in {"kickstart", "system-disk", "floppy", "cd", "directory", "hdf"}:
            issues.append(ValidationIssue("invalid-asset-kind", f"$.assets[{index}].kind", "unsupported asset kind"))
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value or "\x00" in path_value:
            issues.append(ValidationIssue("invalid-asset-path", f"$.assets[{index}].path", "must be a non-empty filesystem path"))
            resolved = path.parent
        else:
            candidate = Path(path_value).expanduser()
            resolved = (candidate if candidate.is_absolute() else path.parent / candidate).resolve(strict=False)
        digest = item.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            issues.append(ValidationIssue("invalid-sha256", f"$.assets[{index}].sha256", "must be 64 lowercase hexadecimal characters"))
        zone = item.get("trust_zone")
        if kind in {"directory", "hdf", "system-disk", "floppy", "cd"} and zone not in TRUST_ZONES:
            issues.append(ValidationIssue("unknown-trust-zone", f"$.assets[{index}].trust_zone", "mountable assets require a known trust zone"))
        assets[asset_id] = Asset(asset_id, str(kind), resolved, digest if isinstance(digest, str) else None, zone if isinstance(zone, str) else None)
    return assets, tuple(issues)


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def preflight(profile_path: Path, inventory_path: Path, runtime_root: Path) -> tuple[Profile | None, dict[str, Asset], PreflightResult]:
    profile, profile_issues = load_profile(profile_path)
    assets, inventory_issues = load_inventory(inventory_path)
    issues = list(profile_issues + inventory_issues)
    if profile is None:
        return None, assets, PreflightResult("", "", 0, "", (), (), "", str(runtime_root.resolve(strict=False)), tuple(issues), False)
    referenced = {profile.kickstart_asset}
    if profile.system_disk:
        referenced.add(str(profile.system_disk["asset"]))
    referenced.update(str(item["asset"]) for item in profile.media)
    referenced.update(mount.source_asset for mount in profile.mounts)
    checks: list[AssetCheck] = []
    for asset_id in sorted(referenced):
        asset = assets.get(asset_id)
        if asset is None:
            issues.append(ValidationIssue("missing-asset-reference", "$.assets", f"inventory has no asset {asset_id!r}"))
            checks.append(AssetCheck(asset_id, "unknown", "", False, "not-checked", None))
            continue
        exists = asset.path.is_file() if asset.kind not in {"directory"} else asset.path.is_dir()
        status = "not-declared"
        if not exists:
            issues.append(ValidationIssue("missing-asset", asset_id, f"asset path does not exist: {asset.path}"))
            status = "missing"
        elif asset.sha256:
            if not asset.path.is_file():
                issues.append(ValidationIssue("hash-not-file", asset_id, "SHA-256 can only verify a regular file"))
                status = "not-checked"
            elif _hash_file(asset.path) != asset.sha256:
                issues.append(ValidationIssue("hash-mismatch", asset_id, f"SHA-256 mismatch for {asset.path}"))
                status = "mismatch"
            else:
                status = "verified"
        checks.append(AssetCheck(asset.id, asset.kind, str(asset.path), exists, status, asset.trust_zone))
    expected_kinds = [(profile.kickstart_asset, {"kickstart"}, "kickstart")]
    if profile.system_disk:
        expected_kinds.append((str(profile.system_disk["asset"]), {"system-disk", "floppy"}, "system disk"))
    for asset_id, kinds, label in expected_kinds:
        if asset_id in assets and assets[asset_id].kind not in kinds:
            issues.append(ValidationIssue("asset-kind-mismatch", asset_id, f"{label} requires kind {sorted(kinds)}"))
    mount_report: list[dict[str, Any]] = []
    for mount in profile.mounts:
        asset = assets.get(mount.source_asset)
        if asset and asset.kind not in {"directory", "hdf"}:
            issues.append(ValidationIssue("asset-kind-mismatch", mount.id, "filesystem mount requires directory or hdf asset"))
        if asset and asset.trust_zone != mount.trust_zone:
            issues.append(ValidationIssue("trust-zone-mismatch", mount.id, f"profile declares {mount.trust_zone}, inventory declares {asset.trust_zone}"))
        mount_report.append({"id": mount.id, "device": mount.device, "asset": mount.source_asset, "path": str(asset.path) if asset else "", "trust_zone": mount.trust_zone, "writable": mount.writable})
    if profile.system_disk:
        asset = assets.get(str(profile.system_disk["asset"]))
        if asset and asset.trust_zone != profile.system_disk["trust_zone"]:
            issues.append(ValidationIssue("trust-zone-mismatch", "system_disk", f"profile declares {profile.system_disk['trust_zone']}, inventory declares {asset.trust_zone}"))
        mount_report.append({"id": "system-disk", "device": "floppy0", "asset": profile.system_disk["asset"], "path": str(asset.path) if asset else "", "trust_zone": profile.system_disk["trust_zone"], "writable": profile.system_disk["writable"]})
    for index, medium in enumerate(profile.media):
        asset = assets.get(str(medium["asset"]))
        expected_kind = {"floppy", "system-disk"} if medium["type"] == "floppy" else {"cd"}
        if asset and asset.kind not in expected_kind:
            issues.append(ValidationIssue("asset-kind-mismatch", f"media[{index}]", f"{medium['type']} requires kind {sorted(expected_kind)}"))
        if asset and asset.trust_zone != medium["trust_zone"]:
            issues.append(ValidationIssue("trust-zone-mismatch", f"media[{index}]", f"profile declares {medium['trust_zone']}, inventory declares {asset.trust_zone}"))
    runtime = runtime_root.resolve(strict=False)
    config_path = runtime / profile.runtime.get("config_dir", "invalid") / f"{profile.id}.fs-uae"
    state_path = runtime / profile.runtime.get("state_dir", "invalid")
    return profile, assets, PreflightResult(profile.id, profile.name, profile.schema_version, profile.machine, tuple(checks), tuple(mount_report), str(config_path), str(state_path), tuple(issues), not issues)


def _fs_path(path: Path) -> str:
    text = str(path)
    if "\n" in text or "\r" in text:
        raise ValueError("FS-UAE paths may not contain newlines")
    return text.replace("\\", "\\\\")


def render_fs_uae(profile: Profile, assets: dict[str, Asset], state_path: Path) -> str:
    """Return deterministic FS-UAE text for an already successful preflight."""
    values: dict[str, str] = {
        "amiga_model": profile.machine,
        "chip_memory": str(profile.chip_ram_mb * 1024),
        "cpu": profile.cpu,
        "fast_memory": str(profile.fast_ram_mb * 1024),
        "fullscreen": "1" if profile.display["fullscreen"] else "0",
        "keep_aspect": "1" if profile.display["scaling"] != "none" else "0",
        "kickstart_file": _fs_path(assets[profile.kickstart_asset].path),
        "mouse_integration": "1" if profile.input["mouse_integration"] else "0",
        "state_dir": _fs_path(state_path.resolve(strict=False)),
        "uae_sound_output": "exact" if profile.sound["enabled"] else "none",
    }
    if profile.system_disk:
        values["floppy_drive_0"] = _fs_path(assets[str(profile.system_disk["asset"])].path)
    for medium in profile.media:
        prefix = "floppy_drive" if medium["type"] == "floppy" else "cdrom_drive"
        values[f"{prefix}_{medium['drive']}"] = _fs_path(assets[str(medium["asset"])].path)
    floppy_writable = bool(profile.system_disk and profile.system_disk["writable"]) or any(item["type"] == "floppy" and item["writable"] for item in profile.media)
    values["writable_floppy_images"] = "1" if floppy_writable else "0"
    for index, mount in enumerate(profile.mounts):
        values[f"hard_drive_{index}"] = _fs_path(assets[mount.source_asset].path)
        values[f"hard_drive_{index}_read_only"] = "0" if mount.writable else "1"
        if mount.volume:
            values[f"hard_drive_{index}_label"] = mount.volume
    lines = ["# Generated by AmigaLab; edit the canonical profile, not this file."]
    lines.extend(f"{key} = {values[key]}" for key in sorted(values))
    return "\n".join(lines) + "\n"
