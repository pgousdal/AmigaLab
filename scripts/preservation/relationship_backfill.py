"""Plan-only relationship backfill for legacy imports.

This intentionally proposes metadata actions only; execution is deferred until
an explicit, audited migration workflow is available.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from .verification_reports import verify_collection
from .external.storage import stable_id


def create_plan(collection: str, root: Path, metadata_root: Path) -> dict[str, Any]:
    report = verify_collection(collection, root, metadata_root, "metadata-only")
    actions = []
    for object_id in report.missing_import_events:
        actions.append({"action": "create-missing-import-event-reference", "object_id": object_id})
    for object_id in report.missing_verification_events:
        actions.append({"action": "create-missing-verification-event-reference", "object_id": object_id})
    return {"id": stable_id({"collection": collection, "actions": actions}),
            "collection": collection, "status": "draft", "actions": actions,
            "read_only": True, "content_modification": False,
            "blocking_findings": list(report.blocking_findings)}
