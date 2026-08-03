"""Media registry records and conservative ROM/Workbench discovery."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import md5, sha1, sha256, sha512
from pathlib import Path
from uuid import uuid4

from .models import Hashes, MediaRecord
from .policy import validate_license_profile


def hash_file(path: Path) -> Hashes:
    digests = (md5(), sha1(), sha256(), sha512())
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            for digest in digests:
                digest.update(chunk)
    return Hashes(*(digest.hexdigest() for digest in digests))


def register_media(path: Path, source_id: str, title: str, license_profile: str = "unknown", classification: str = "unknown", notes: str = "") -> MediaRecord:
    validate_license_profile(license_profile)
    stat = path.stat()
    return MediaRecord(str(uuid4()), title, path.name, stat.st_size, hash_file(path), license_profile, classification, source_id=source_id, original_path=str(path), imported_at=datetime.now(timezone.utc).isoformat(), notes=notes, redistributable=license_profile == "redistributable", export_allowed=False)


def discover_candidates(root: Path) -> list[dict[str, object]]:
    results = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in {".rom", ".adf", ".hdf", ".hdf"}:
            results.append({"path": path.relative_to(root).as_posix(), "kind": suffix[1:], "evidence": f"filename suffix {suffix}", "confidence": "candidate", "hashes": hash_file(path).__dict__})
    return results
