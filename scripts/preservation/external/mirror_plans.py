from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from .models import ExternalSnapshot, MirrorPlan
from .storage import stable_id, ExternalStorage


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name and not path.is_absolute() and ".." not in path.parts and not any(ord(char) < 32 for char in name))


def create_mirror_plan(source_id: str, snapshot: ExternalSnapshot, policy: str = "original-media", previous_snapshot_id: str = "") -> MirrorPlan:
    selected, excluded, warnings = [], [], []
    for item in snapshot.items:
        for file in item.files:
            record = {"item": item.identifier, "filename": file.name, "size": file.size, "md5": file.md5, "sha1": file.sha1, "locator": file.locator}
            if not safe_name(file.name):
                warnings.append(f"unsafe filename: {file.name}"); excluded.append(record)
            elif file.classification == "derivative" or file.name.endswith(("_thumb.jpg", ".torrent")):
                excluded.append(record)
            else:
                selected.append(record)
    content = {"source_id": source_id, "snapshot_id": snapshot.id, "previous_snapshot_id": previous_snapshot_id, "policy": policy, "selected_files": selected, "excluded_files": excluded, "target_category": "unknown", "warnings": warnings}
    fingerprint = stable_id(content)
    return MirrorPlan(stable_id({"fingerprint": fingerprint}), source_id, snapshot.id, previous_snapshot_id, datetime.now(timezone.utc).isoformat(), policy, "blocked" if warnings else "draft", tuple(selected), tuple(excluded), "unknown", tuple(warnings), (), fingerprint)


class MirrorPlanStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, plan): return self.storage.put("mirror-plans", plan.id, plan)
    def get(self, plan_id): return self.storage.get("mirror-plans", plan_id)
