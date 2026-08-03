"""Record verification outcomes for immutable preservation objects."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import new
from pathlib import Path
from uuid import uuid4

from .models import PreservationObject, VerificationEvent


def verify_object(object_: PreservationObject, collection_root: Path, algorithm: str = "sha256") -> VerificationEvent:
    failures: list[str] = []
    for file_record in object_.files:
        path = collection_root / file_record.original_relative_path
        if not path.is_file():
            failures.append(f"missing: {file_record.original_relative_path}")
            continue
        digest = new(algorithm, path.read_bytes()).hexdigest()
        if digest != getattr(file_record.hashes, algorithm):
            failures.append(f"hash mismatch: {file_record.original_relative_path}")
    return VerificationEvent(str(uuid4()), datetime.now(timezone.utc).isoformat(), object_.id, algorithm, not failures, "; ".join(failures) if failures else None)


def append_verification(object_: PreservationObject, event: VerificationEvent) -> PreservationObject:
    """Return a new object retaining all earlier verification event IDs."""
    return replace(object_, verification_event_ids=tuple(dict.fromkeys(object_.verification_event_ids + (event.id,))))
