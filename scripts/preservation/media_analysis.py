"""Read-only analysis of verified local mirror media."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import zipfile
import tarfile

from .external.mirror_execution import MirrorExecutionStore, local_hashes
from .external.storage import ExternalStorage, stable_id
from .sources import adapter_for

SIDECARS = {".readme", ".info", ".txt", ".nfo", ".diz"}
AMINET_CATEGORIES = {"biz", "comm", "demo", "dev", "disk", "docs", "game", "gfx", "hard", "misc", "mods", "mus", "pix", "text", "util"}


@dataclass(frozen=True)
class AnalysisMember:
    original_identifier: str
    original_relative_path: str
    canonical_path: str
    member_type: str
    size: int
    extension: str
    sidecar_role: str = ""
    unsafe: bool = False
    eligible: bool = True
    evidence: str = ""


@dataclass(frozen=True)
class MediaAnalysis:
    id: str
    media_id: str
    acquisition_execution_id: str
    acquisition_entry_id: str
    mirror_plan_id: str
    external_source_id: str
    snapshot_id: str
    local_media_path: str
    local_media_hashes: dict[str, str]
    media_size: int
    container_type: str
    detection_evidence: tuple[str, ...]
    confidence: str
    members: tuple[AnalysisMember, ...]
    sidecar_groups: tuple[dict[str, object], ...]
    unsafe_entries: tuple[str, ...]
    duplicate_members: tuple[str, ...]
    candidate_collections: tuple[dict[str, object], ...]
    recommended_import_mode: str
    license_profile: str
    media_classification: str
    warnings: tuple[str, ...] = ()
    blocking_findings: tuple[str, ...] = ()
    rom_candidates: tuple[dict[str, object], ...] = ()
    workbench_candidates: tuple[dict[str, object], ...] = ()
    created_at: str = ""
    completed_at: str = ""
    fingerprint: str = ""
    schema_version: int = 1


class MediaAnalysisStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, analysis): return self.storage.put("media-analyses", analysis.id, analysis)
    def get(self, analysis_id):
        raw = self.storage.get("media-analyses", analysis_id)
        raw["members"] = tuple(AnalysisMember(**item) for item in raw.get("members", ()))
        for key in ("detection_evidence", "sidecar_groups", "unsafe_entries", "duplicate_members", "candidate_collections", "warnings", "blocking_findings", "rom_candidates", "workbench_candidates"):
            raw[key] = tuple(raw.get(key, ()))
        return MediaAnalysis(**raw)
    def list(self): return tuple(self.get(Path(path).stem) for path in sorted((self.storage.root / "media-analyses").glob("*.json"))) if (self.storage.root / "media-analyses").is_dir() else ()


def detect_container(path: Path) -> tuple[str, tuple[str, ...], str]:
    evidence = []
    with path.open("rb") as stream: magic = stream.read(512)
    if magic.startswith(b"PK\x03\x04"):
        return "zip", ("ZIP magic",), "high"
    if len(magic) > 265 and magic[257:262] == b"ustar":
        return "tar", ("TAR ustar signature",), "high"
    if magic[1:6] == b"CD001":
        return "iso", ("ISO9660 signature",), "high"
    suffix = path.suffix.lower()
    if suffix in {".iso", ".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".adf", ".hdf", ".lha", ".lzh", ".dms"}:
        return suffix.lstrip("."), (f"extension:{suffix}",), "low"
    return "unknown", (), "unknown"


def _safe(path: str) -> bool:
    candidate = Path(path)
    return bool(path and not candidate.is_absolute() and ".." not in candidate.parts and not any(ord(c) < 32 for c in path))


def analyze_media(media_id: str, entry, execution, source, plan_id: str, snapshot_id: str, *, media_root: Path) -> MediaAnalysis:
    path = Path(entry.final_path)
    if execution.state not in {"completed", "completed-with-skips"} or entry.state not in {"completed", "reused"}:
        raise ValueError("acquisition is not complete")
    if not path.is_file() or not path.resolve().is_relative_to(media_root.resolve()): raise ValueError("media path is invalid or outside media root")
    hashes, size = local_hashes(path)
    if entry.local_hashes and hashes != entry.local_hashes: raise ValueError("acquired media hash changed")
    container, evidence, confidence = detect_container(path)
    members: list[AnalysisMember] = []; unsafe: list[str] = []; duplicates: list[str] = []
    if container == "zip":
        try:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    safe = _safe(info.filename) and not info.is_dir()
                    members.append(AnalysisMember(info.filename, info.filename, Path(info.filename).as_posix(), "file", info.file_size, Path(info.filename).suffix.lower(), Path(info.filename).suffix.lower() if Path(info.filename).suffix.lower() in SIDECARS else "", not safe, safe, "ZIP member"))
        except (zipfile.BadZipFile, OSError) as error:
            evidence = (*evidence, f"invalid ZIP: {error}"); container, confidence = "unknown", "unknown"
    elif container == "tar":
        try:
            with tarfile.open(path, "r:*") as archive:
                for info in archive.getmembers():
                    safe = _safe(info.name) and info.isfile()
                    members.append(AnalysisMember(info.name, info.name, Path(info.name).as_posix(), "file" if info.isfile() else "special", info.size, Path(info.name).suffix.lower(), Path(info.name).suffix.lower() if Path(info.name).suffix.lower() in SIDECARS else "", not safe, safe, "TAR member"))
        except (tarfile.TarError, OSError) as error:
            evidence = (*evidence, f"invalid TAR: {error}"); container, confidence = "unknown", "unknown"
    else:
        try:
            adapter = adapter_for(path, container)
            for item in adapter.entries(): members.append(AnalysisMember(item.path, item.path, item.path, "file" if item.is_file else "special", item.size, Path(item.path).suffix.lower(), Path(item.path).suffix.lower() if Path(item.path).suffix.lower() in SIDECARS else "", bool(item.unsupported_reason), item.is_file and not item.unsupported_reason, "adapter"))
            adapter.close()
        except Exception as error:
            if container not in {"unknown", "adf", "hdf", "dms", "lha", "lzh"}: raise
            evidence = (*evidence, str(error))
    names = {member.canonical_path for member in members}
    duplicates = sorted(path for path in names if sum(item.canonical_path == path for item in members) > 1)
    unsafe = sorted(member.original_identifier for member in members if member.unsafe)
    aminets = sum(Path(member.canonical_path).parts[:1][0] in AMINET_CATEGORIES for member in members if member.canonical_path)
    aminet = source.upstream_identifier == "aminetcd" or aminets >= 2
    sidecars = []
    for member in members:
        if member.sidecar_role:
            primary = str(Path(member.canonical_path).with_suffix(""))
            sidecars.append({"group_id": stable_id({"primary": primary, "sidecar": member.canonical_path}), "primary": primary, "sidecar": member.canonical_path, "method": "matching-stem", "confidence": "high"})
    candidates = ({"collection": "aminet", "confidence": "high" if aminet else "low", "evidence": "Aminet hierarchy/source"},) if aminet else ()
    mode = "manual-review" if unsafe or duplicates else ("media-and-members" if aminet and container in {"zip", "tar", "iso"} else "media-only" if source.license_profile != "redistributable" else "members-only")
    roms = tuple({"path": member.canonical_path, "confidence": "low", "evidence": "filename only", "warning": "version not established"} for member in members if "kick" in member.canonical_path.lower() or member.canonical_path.lower().endswith(".rom"))
    workbench = tuple({"path": member.canonical_path, "confidence": "low", "evidence": "filename only"} for member in members if "workbench" in member.canonical_path.lower() or member.canonical_path.lower().endswith(".adf"))
    content = {"media_id": media_id, "entry": entry.id, "hashes": hashes, "size": size, "container": container, "members": [asdict(member) for member in members], "sidecars": sidecars, "candidates": candidates, "mode": mode, "unsafe": unsafe, "duplicates": duplicates}
    fingerprint = stable_id(content)
    return MediaAnalysis(stable_id({"media": media_id, "fingerprint": fingerprint}), media_id, execution.id, entry.id, plan_id, source.id, snapshot_id, str(path), hashes, size, container, tuple(evidence), confidence, tuple(sorted(members, key=lambda item: item.original_relative_path)), tuple(sidecars), tuple(unsafe), tuple(duplicates), tuple(candidates), mode, source.license_profile, source.media_classification, warnings=("unknown licensing" if source.license_profile == "unknown" else "",), blocking_findings=(), rom_candidates=roms, workbench_candidates=workbench, created_at=datetime.now(timezone.utc).isoformat(), completed_at=datetime.now(timezone.utc).isoformat(), fingerprint=fingerprint)
