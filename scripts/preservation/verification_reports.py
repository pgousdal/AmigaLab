"""Read-only collection verification, reconciliation, and trace reports."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from .models import Hashes
from .services import hash_file
from .storage import MetadataStore
from .external.storage import ExternalStorage, stable_id


@dataclass(frozen=True)
class VerificationReport:
    id: str
    collection: str
    verified_at: str
    policy: str
    file_count: int
    object_count: int
    sidecar_count: int
    verified_bytes: int
    successful_files: tuple[str, ...]
    missing_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    hash_mismatches: tuple[str, ...]
    metadata_only_records: tuple[str, ...]
    untracked_files: tuple[str, ...]
    missing_import_events: tuple[str, ...]
    missing_verification_events: tuple[str, ...]
    missing_relationships: tuple[str, ...]
    hierarchy_findings: tuple[str, ...]
    warnings: tuple[str, ...]
    blocking_findings: tuple[str, ...]
    result: str
    fingerprint: str


def verify_collection(collection: str, root: Path, metadata_root: Path, policy: str = "full-hashes") -> VerificationReport:
    store = MetadataStore(metadata_root)
    objects = tuple(item for item in store.list_objects() if item.original_collection == collection)
    successful, missing, changed, mismatches, metadata_only = [], [], [], [], []
    import_missing, verification_missing, relationship_missing = [], [], []
    relationship_objects: set[str] = set()
    relationship_dir = metadata_root / "media-relationships"
    if relationship_dir.is_dir():
        import json
        for relationship_path in relationship_dir.glob("*.json"):
            try:
                value = json.loads(relationship_path.read_text(encoding="utf-8"))
                if value.get("object_id"):
                    relationship_objects.add(str(value["object_id"]))
            except (OSError, ValueError):
                continue
    expected_paths: set[str] = set(); verified_bytes = 0; sidecars = 0
    for object_ in objects:
        for file_record in object_.files:
            relative = file_record.original_relative_path; expected_paths.add(relative)
            path = root / relative
            if Path(relative).suffix.lower() in {".readme", ".info", ".txt", ".nfo", ".diz"}: sidecars += 1
            if not path.exists() or not path.is_file(): missing.append(relative); continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()): changed.append(relative); continue
            hashes, size = hash_file(path) if policy != "metadata-only" else (file_record.hashes, path.stat().st_size)
            if size != file_record.size: mismatches.append(relative)
            elif policy == "full-hashes" and hashes != file_record.hashes: mismatches.append(relative)
            elif policy == "sha256" and hashes.sha256 != file_record.hashes.sha256: mismatches.append(relative)
            else: successful.append(relative); verified_bytes += size
            if not object_.import_event_ids: import_missing.append(object_.id)
            if not object_.verification_event_ids: verification_missing.append(object_.id)
        if object_.provenance_source_ids and relationship_dir.is_dir() and object_.id not in relationship_objects:
            relationship_missing.append(object_.id)
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()} if root.is_dir() else set()
    untracked = sorted(actual - expected_paths)
    hierarchy = [relative for relative in sorted(expected_paths) if Path(relative).is_absolute() or ".." in Path(relative).parts]
    blocking = tuple(sorted(set(missing + changed + mismatches + hierarchy)))
    fingerprint = stable_id({"collection": collection, "successful": sorted(successful), "missing": sorted(missing), "changed": sorted(changed), "mismatches": sorted(mismatches), "untracked": untracked, "relationships": sorted(relationship_missing)})
    blocking = tuple(sorted(set(blocking).union(relationship_missing)))
    return VerificationReport(stable_id({"collection": collection, "fingerprint": fingerprint}), collection, datetime.now(timezone.utc).isoformat(), policy, len(expected_paths), len(objects), sidecars, verified_bytes, tuple(sorted(successful)), tuple(sorted(missing)), tuple(sorted(changed)), tuple(sorted(mismatches)), tuple(metadata_only), tuple(untracked), tuple(sorted(set(import_missing))), tuple(sorted(set(verification_missing))), tuple(sorted(set(relationship_missing))), tuple(hierarchy), (), blocking, "failed" if blocking else "success", fingerprint)


class VerificationReportStore:
    def __init__(self, root): self.storage = ExternalStorage(root)
    def save(self, report): return self.storage.put("verification-reports", report.id, report)
    def get(self, report_id): return self.storage.get("verification-reports", report_id)
    def list(self): return self.storage.list("verification-reports")


def reconciliation(collection: str, root: Path, metadata_root: Path) -> dict[str, object]:
    report = verify_collection(collection, root, metadata_root, "metadata-only")
    return {"collection": collection, "missing": report.missing_files, "changed": report.changed_files, "hash_mismatches": report.hash_mismatches, "untracked": report.untracked_files, "missing_import_events": report.missing_import_events, "missing_verification_events": report.missing_verification_events, "blocking": report.blocking_findings, "read_only": True}


def repair_plan(collection: str, root: Path, metadata_root: Path) -> dict[str, object]:
    findings = reconciliation(collection, root, metadata_root)
    actions = []
    for object_id in findings["missing_import_events"]: actions.append({"action": "create-missing-import-event-reference", "object_id": object_id})
    for object_id in findings["missing_verification_events"]: actions.append({"action": "create-missing-verification-event-reference", "object_id": object_id})
    return {"id": stable_id({"collection": collection, "actions": actions}), "collection": collection, "status": "draft" if actions else "validated", "actions": actions, "content_modification": False}
