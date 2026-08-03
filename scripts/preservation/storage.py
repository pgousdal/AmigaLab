"""Serialize separate preservation metadata without touching collections."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from .models import ImportEvent, PreservationObject, Source, VerificationEvent


class MetadataStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure_layout(self) -> None:
        for directory in ("collections", "objects", "sources", "imports", "verification"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def _write(self, category: str, identifier: str, value: object) -> Path:
        self.ensure_layout()
        path = self.root / category / f"{sha256(identifier.encode()).hexdigest()}.json"
        path.write_text(json.dumps(asdict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def save_source(self, source: Source) -> Path:
        return self._write("sources", source.id, source)

    def save_object(self, object_: PreservationObject) -> Path:
        return self._write("objects", object_.id, object_)

    def save_import(self, event: ImportEvent) -> Path:
        return self._write("imports", event.id, event)

    def save_verification(self, event: VerificationEvent) -> Path:
        return self._write("verification", event.id, event)
