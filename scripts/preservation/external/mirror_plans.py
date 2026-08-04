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
    return MirrorPlan(stable_id({"fingerprint": fingerprint}), source_id, snapshot.id, previous_snapshot_id, datetime.now(timezone.utc).isoformat(), policy, "blocked" if warnings else "draft", tuple(selected), tuple(excluded), "unknown", tuple(warnings), (), fingerprint, snapshot_fingerprint=snapshot.fingerprint)


def validate_mirror_plan(plan: MirrorPlan, snapshot: ExternalSnapshot) -> tuple[str, ...]:
    issues: list[str] = []
    if not snapshot.completed: issues.append("snapshot is not completed")
    if plan.snapshot_id != snapshot.id or (plan.snapshot_fingerprint and plan.snapshot_fingerprint != snapshot.fingerprint): issues.append("snapshot fingerprint mismatch")
    known = {(item.identifier, file.name) for item in snapshot.items for file in item.files}
    selected = [(str(item.get("item")), str(item.get("filename"))) for item in plan.selected_files]
    if len(selected) != len(set(selected)): issues.append("duplicate selected file identity")
    for identity in selected:
        if identity not in known: issues.append(f"selected file missing from snapshot: {identity[0]}/{identity[1]}")
        if not safe_name(identity[1]): issues.append(f"unsafe filename: {identity[1]}")
    if plan.status in {"cancelled", "superseded", "approved"}: issues.append(f"plan status is {plan.status}")
    return tuple(sorted(set(issues)))


def review_mirror_plan(plan: MirrorPlan) -> dict[str, object]:
    return {"plan_id": plan.id, "selected_file_count": len(plan.selected_files), "expected_bytes": sum(int(item.get("size") or 0) for item in plan.selected_files), "excluded_file_count": len(plan.excluded_files), "warnings": list(plan.warnings), "blocking_issues": list(plan.blocking_issues), "upstream_hash_coverage": sum(bool(item.get("md5") or item.get("sha1")) for item in plan.selected_files), "unknown_license": True, "future_import_mode": "media-only"}


class MirrorPlanStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, plan): return self.storage.put("mirror-plans", plan.id, plan)
    def get(self, plan_id): return self.storage.get("mirror-plans", plan_id)
