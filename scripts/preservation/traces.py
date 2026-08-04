"""Read-only trace and metadata reconciliation helpers."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .storage import MetadataStore
from .external.storage import stable_id


def _objects(metadata_root: Path):
    return MetadataStore(metadata_root).list_objects()


def object_trace(object_id: str, metadata_root: Path) -> dict[str, Any]:
    obj = next((o for o in _objects(metadata_root) if o.id == object_id), None)
    if obj is None:
        return {"object_id": object_id, "found": False, "missing": ["object"]}
    return {"object_id": object_id, "found": True, "object": asdict(obj),
            "references": {"source_ids": list(obj.provenance_source_ids),
                           "import_event_ids": list(obj.import_event_ids),
                           "verification_event_ids": list(obj.verification_event_ids)}}


def file_trace(file_id: str, metadata_root: Path) -> dict[str, Any]:
    for obj in _objects(metadata_root):
        for file in obj.files:
            # File records predate independent IDs; accept deterministic record id
            candidate = stable_id({"object_id": obj.id, "path": file.original_relative_path})
            if file_id in {candidate, file.original_relative_path, file.original_filename}:
                return {"file_id": file_id, "found": True, "object_id": obj.id,
                        "object": asdict(obj), "file": asdict(file),
                        "source_ids": list(obj.provenance_source_ids),
                        "import_event_ids": list(obj.import_event_ids),
                        "verification_event_ids": list(obj.verification_event_ids)}
    return {"file_id": file_id, "found": False, "missing": ["file"]}


def media_trace(media_id: str, metadata_root: Path) -> dict[str, Any]:
    media = [m for m in MetadataStore(metadata_root)._read_json("media") if m.get("id") == media_id]
    analyses = [a for a in _json_dir(metadata_root / "media-analyses") if a.get("media_id") == media_id]
    links = [p for p in _json_dir(metadata_root / "media-import-plan-links") if p.get("media_id") == media_id]
    return {"media_id": media_id, "found": bool(media), "media": media[0] if media else None,
            "analysis": analyses, "import_plan_links": links}


def _json_dir(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    import json
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]
