"""Structured, non-destructive import conflict reports."""

from __future__ import annotations

from pathlib import Path

from .importer import _primary_paths
from .manifest import preserved_file
from .models import Source
from .storage import MetadataStore


def conflict_report(location: Path, collection: str, archive_root: Path, source_id: str, store: MetadataStore) -> list[dict[str, str]]:
    report: list[dict[str, str]] = []
    for relative_path in _primary_paths(location):
        destination = archive_root / collection / relative_path
        if not destination.is_file():
            continue
        incoming = preserved_file(collection, location, relative_path).hashes.sha256
        existing = preserved_file(collection, archive_root / collection, relative_path).hashes.sha256
        if incoming != existing:
            report.append({"conflict_type": "same-path-different-hash", "source_path": relative_path, "target_path": str(destination), "incoming_sha256": incoming, "existing_sha256": existing, "source_id": source_id})
    return report
